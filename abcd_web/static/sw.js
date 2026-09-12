// static/sw.js - ABCD & Guidy PWA Service Worker for Background Web Push & App Badging

self.addEventListener('install', function (event) {
    self.skipWaiting();
});

self.addEventListener('activate', function (event) {
    event.waitUntil(self.clients.claim());
});

let activeChatState = { chatType: null, chatId: null, timestamp: 0 };

self.addEventListener('message', function (event) {
    if (event.data && event.data.type === 'ACTIVE_CHAT_UPDATE') {
        activeChatState = {
            chatType: event.data.chatType,
            chatId: event.data.chatId ? String(event.data.chatId) : null,
            timestamp: Date.now()
        };
    }
});

self.addEventListener('push', function (event) {
    let data = {};
    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data = { title: 'ABCD Campus', body: event.data.text() };
        }
    }

    function sanitizeText(str) {
        if (!str) return '';
        return String(str)
            .replace(/[|]/g, ' - ')
            .replace(/^(?:ABCD\s*-\s*|Guidy\s*-\s*|ToDo\s*-\s*)+/i, '')
            .replace(/[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{2300}-\u{23FF}\u{2B50}\u{200D}\u{FE0F}]/gu, '')
            .replace(/\s+/g, ' ')
            .trim();
    }

    let rawTitle = sanitizeText(data.title) || 'ABCD Campus';
    const title = rawTitle;
    const bodyText = sanitizeText(data.body) || 'You have a new update.';
    const icon = data.icon || '/static/data/favicon/web-app-manifest-192x192.png';
    const badge = data.badge || '/static/data/favicon/favicon-96x96.png';

    const catLower = (data.category || '').toLowerCase();
    const titleLower = (title || '').toLowerCase();
    const tagLower = (data.tag || '').toLowerCase();

    // Check if this notification is for a Guidy chat
    const isGuidy = (data.category === 'guidy') ||
                    (data.source === 'guidy') ||
                    (data.tag && String(data.tag).startsWith('guidy-')) ||
                    (data.url && data.url.includes('/guidy'));

    // Distinguish alarm vs simple reminder cleanly - Guidy is NEVER an alarm or reminder!
    let isAlarm = false;
    let isReminder = false;
    if (!isGuidy) {
        if (typeof data.is_alarm === 'boolean') {
            isAlarm = data.is_alarm;
        } else {
            isAlarm = (catLower === 'alarm' || (data.source === 'todo' && tagLower.includes('alarm')));
        }
        isReminder = !isAlarm && ((catLower === 'reminder' && (data.source === 'todo' || data.task_id)) || (data.source === 'todo' && tagLower.includes('reminder')));
    }

    const isAudioAlert = isAlarm || isReminder;
    const isTodo = (data.source === 'todo') || (data.url && data.url.includes('/todo'));

    let sound = data.sound;
    if (!sound) {
        if (isAlarm) {
            sound = '/static/audio/alarm.mp3';
        } else if (isReminder) {
            sound = isTodo ? '/static/audio/PWA.mp3' : '/static/audio/alarms and reminders.mp3';
        } else if (isGuidy) {
            sound = '/static/audio/receive.mp3';
        } else {
            sound = '/static/audio/PWA.mp3';
        }
    }

    const alarmVibratePattern = [500, 200, 500, 200, 500];
    const reminderVibratePattern = [300, 150, 300];
    const defaultVibratePattern = [200, 100, 200];

    const options = {
        body: bodyText,
        icon: icon,
        badge: badge,
        tag: data.tag || (data.task_id ? 'abcd-reminder-' + data.task_id : (isAlarm ? 'abcd-alarm-active' : 'abcd-notification')),
        renotify: (isAlarm || isReminder) ? true : false,
        requireInteraction: isAlarm ? true : false,
        silent: false,
        vibrate: isAlarm ? alarmVibratePattern : (isReminder ? reminderVibratePattern : defaultVibratePattern),
        data: {
            url: data.url || '/',
            timestamp: data.timestamp || Date.now(),
            badge_count: data.badge_count || 1,
            isAlarm: isAlarm,
            isReminder: isReminder,
            sound: sound,
            title: title,
            body: data.body || '',
            taskId: data.task_id || null
        },
        actions: isAlarm
            ? [
                { action: 'open_alarm', title: 'Open' },
                { action: 'dismiss', title: 'Dismiss' }
              ]
            : (isReminder
                ? [
                    { action: 'open_reminder', title: 'Open' },
                    { action: 'dismiss', title: 'Dismiss' }
                  ]
                : [
                    { action: 'open', title: 'Open' }
                  ]
            )
    };

    // Update Launcher Icon Badge on Android PWA / Desktop (e.g. 999+ or 1)
    if ('setAppBadge' in self.navigator) {
        const count = parseInt(data.badge_count, 10) || 1;
        self.navigator.setAppBadge(count).catch(function () {});
    }

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
            // 1. Broadcast to open tabs: ONLY if it is an actual user alarm or reminder (NEVER for Guidy)!
            if (clientList && clientList.length > 0) {
                if ((isAlarm || isReminder) && !isGuidy && (data.task_id || data.is_alarm || data.source === 'todo')) {
                    clientList.forEach(function (client) {
                        try {
                            client.postMessage({
                                type: 'ABCD_ALARM_PUSH',
                                title: title,
                                body: data.body,
                                sound: sound,
                                isAlarm: isAlarm,
                                taskId: data.task_id || null,
                                url: data.url
                            });
                        } catch (err) {}
                    });
                } else if (isGuidy) {
                    clientList.forEach(function (client) {
                        try {
                            client.postMessage({
                                type: 'ABCD_GUIDY_MESSAGE',
                                title: title,
                                body: data.body,
                                url: data.url
                            });
                        } catch (err) {}
                    });
                }
            }

            // Check if this notification is for a Guidy chat currently open & visible in this browser
            if (isGuidy && clientList && clientList.length > 0) {
                let targetParam = '';
                if (data.url && data.url.includes('?')) {
                    targetParam = data.url.substring(data.url.indexOf('?') + 1); // e.g. "direct=27" or "session=12" or "group=5"
                }

                // Check 1: Direct active chat sync from Guidy client via postMessage
                const isRecentState = (Date.now() - activeChatState.timestamp) < 120000;
                const activeId = activeChatState.chatId;
                const matchesActiveChat = isRecentState && activeId && (
                    (targetParam && targetParam.includes(activeId)) ||
                    (data.tag && String(data.tag).includes(activeId)) ||
                    (data.url && data.url.includes(activeId))
                );

                const hasVisibleGuidyTab = clientList.some(function (client) {
                    return client.url && client.url.includes('/guidy') && client.visibilityState === 'visible';
                });

                if (hasVisibleGuidyTab && matchesActiveChat) {
                    // Chat is currently open and visible: suppress notification!
                    return;
                }

                // Check 2: Fallback URL inspection
                const isChatActiveAndVisible = clientList.some(function (client) {
                    if (!client.url || !client.url.includes('/guidy')) return false;
                    if (client.visibilityState !== 'visible') return false;

                    if (targetParam) {
                        return client.url.includes(targetParam);
                    }
                    return false;
                });

                if (isChatActiveAndVisible) {
                    // Suppress browser push popup: user is already reading this chat live
                    return;
                }
            }

            return self.registration.showNotification(title, options);
        })
    );
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();

    // Clear Launcher App Badge when notification is opened
    if ('clearAppBadge' in self.navigator) {
        self.navigator.clearAppBadge().catch(function () {});
    }

    if (event.action === 'dismiss') {
        return;
    }

    const notifData = (event.notification && event.notification.data) ? event.notification.data : {};
    let targetUrl = notifData.url || '/';

    const isNotifGuidy = (notifData.category === 'guidy') ||
                         (notifData.source === 'guidy') ||
                         (targetUrl && targetUrl.includes('/guidy'));

    const isAlarmClick = !isNotifGuidy && (notifData.isAlarm || event.action === 'open_alarm') && (notifData.taskId || notifData.source === 'todo');
    const isReminderClick = !isNotifGuidy && (notifData.isReminder || event.action === 'open_reminder') && (notifData.taskId || notifData.source === 'todo');

    // When opening an alarm or reminder, attach ring_alarm=1 param with is_alarm=1 or is_alarm=0
    if (isAlarmClick || isReminderClick) {
        const sep = targetUrl.includes('?') ? '&' : '?';
        const isAlarmVal = isAlarmClick ? '1' : '0';
        const taskParam = notifData.taskId ? `&task_id=${encodeURIComponent(notifData.taskId)}` : '';
        targetUrl = `${targetUrl}${sep}ring_alarm=1&alarm_title=${encodeURIComponent(notifData.title || 'Reminder')}&is_alarm=${isAlarmVal}${taskParam}`;
    }

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
            for (let i = 0; i < clientList.length; i++) {
                const client = clientList[i];
                if ('focus' in client) {
                    const clientBase = client.url.split('?')[0];
                    const targetBase = targetUrl.split('?')[0];
                    if (clientBase.includes(targetBase) || client.url.includes('/todo') || targetUrl.startsWith('/')) {
                        if (isAlarmClick || isReminderClick) {
                            try {
                                client.postMessage({
                                    type: 'ABCD_ALARM_PUSH',
                                    title: notifData.title,
                                    body: notifData.body,
                                    isAlarm: Boolean(isAlarmClick),
                                    sound: notifData.sound,
                                    taskId: notifData.taskId || null
                                });
                            } catch (e) {}
                            if ('navigate' in client && !client.url.includes('ring_alarm=1')) {
                                client.navigate(targetUrl).catch(function () {});
                            }
                        }
                        return client.focus();
                    }
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});
