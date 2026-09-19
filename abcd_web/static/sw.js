// static/sw.js - ABCD & Guidy PWA Service Worker for Background Web Push & App Badging

self.addEventListener('install', function (event) {
    self.skipWaiting();
});

self.addEventListener('activate', function (event) {
    event.waitUntil(
        caches.keys().then(function (keys) {
            return Promise.all(
                keys.filter(function (key) {
                    return key !== STATIC_CACHE_NAME;
                }).map(function (key) {
                    return caches.delete(key);
                })
            );
        }).then(function () {
            return self.clients.claim();
        })
    );
});

let activeChatState = { chatType: null, chatId: null, timestamp: 0 };

// Normalized helper for robust Guidy classification across push and click events
function isGuidyPayload(obj, fallbackUrl) {
    if (!obj && !fallbackUrl) return false;
    const o = obj || {};
    const cat = String(o.category || '').toLowerCase().trim();
    const src = String(o.source || '').toLowerCase().trim();
    const tag = String(o.tag || '').toLowerCase().trim();
    const url = String(o.url || fallbackUrl || '').toLowerCase().trim();
    return (
        cat === 'guidy' ||
        src === 'guidy' ||
        tag.startsWith('guidy-') ||
        tag.includes('guidy') ||
        url.includes('/guidy')
    );
}

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
    const badge = data.badge || '/static/data/favicon/badge-mono.png';

    const catLower = (data.category || '').toLowerCase().trim();
    const titleLower = (title || '').toLowerCase().trim();
    const tagLower = (data.tag || '').toLowerCase().trim();

    // Check if this notification is for a Guidy chat (fully normalized)
    const isGuidy = isGuidyPayload(data);

    // Distinguish alarm vs simple reminder cleanly - Guidy is NEVER an alarm or reminder!
    let isAlarm = false;
    let isReminder = false;
    if (!isGuidy) {
        if (typeof data.is_alarm === 'boolean') {
            isAlarm = data.is_alarm;
        } else {
            isAlarm = (catLower === 'alarm' || (data.source === 'todo' && tagLower.includes('alarm')));
        }
        if (typeof data.is_reminder === 'boolean') {
            isReminder = data.is_reminder;
        } else {
            isReminder = !isAlarm && (catLower === 'reminder' || catLower.includes('reminder') || tagLower.includes('reminder') || (data.source === 'todo' && Boolean(data.task_id)));
        }
    }

    const isAudioAlert = isAlarm || isReminder;
    const isTodo = (data.source === 'todo') || (data.url && data.url.includes('/todo')) || Boolean(data.task_id);

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
        sound: sound,
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
                { action: 'stop', title: 'Stop ⏹' },
                { action: 'snooze', title: 'Snooze 15m ⏱' },
                { action: 'open_alarm', title: 'Open ↗' }
              ]
            : (isReminder
                ? [
                    { action: 'open_reminder', title: 'Open ↗' },
                    { action: 'stop', title: 'Dismiss ✕' }
                  ]
                : [
                    { action: 'open', title: 'Open ↗' }
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
            // 1. Broadcast to open tabs:
            if (clientList && clientList.length > 0) {
                if ((isAlarm || isReminder) && !isGuidy) {
                    clientList.forEach(function (client) {
                        try {
                            client.postMessage({
                                type: 'ABCD_ALARM_PUSH',
                                title: title,
                                body: data.body,
                                sound: sound,
                                isAlarm: isAlarm,
                                isReminder: isReminder,
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
                } else {
                    // General PWA Notification -> broadcast so open tab chimes PWA.mp3
                    clientList.forEach(function (client) {
                        try {
                            client.postMessage({
                                type: 'ABCD_NOTIFICATION_PUSH',
                                title: title,
                                body: data.body,
                                sound: sound || '/static/audio/PWA.mp3',
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

    const notifData = (event.notification && event.notification.data) ? event.notification.data : {};

    if (event.action === 'stop' || event.action === 'dismiss') {
        if (notifData.taskId) {
            event.waitUntil(
                fetch('/todo/reminder/' + encodeURIComponent(notifData.taskId) + '/action/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'stop' })
                }).catch(function () {})
            );
        }
        return;
    }

    if (event.action === 'snooze') {
        if (notifData.taskId) {
            event.waitUntil(
                fetch('/todo/reminder/' + encodeURIComponent(notifData.taskId) + '/action/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'snooze', minutes: 15 })
                }).catch(function () {})
            );
        }
        return;
    }
    let targetUrl = notifData.url || '/';

    const isNotifGuidy = isGuidyPayload(notifData, targetUrl);

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

// -----------------------------------------------------------------------------
// LIGHTWEIGHT CACHE FOR INSTANT APP LAUNCH (<100ms)
// -----------------------------------------------------------------------------
const STATIC_CACHE_NAME = 'abcd-static-shell-v3';

self.addEventListener('fetch', function (event) {
    const request = event.request;
    if (request.method !== 'GET') return;

    let url;
    try {
        url = new URL(request.url);
    } catch (e) {
        return;
    }

    // Only cache local static assets (CSS, JS, Fonts, Icons)
    // Exclude audio (.mp3) to prevent large storage usage
    if (url.origin === self.location.origin && url.pathname.startsWith('/static/')) {
        if (url.pathname.endsWith('.mp3') || url.pathname.endsWith('.mp4') || url.pathname.endsWith('.webm')) {
            return;
        }

        // For critical interactive scripts and manifest, use Network-First to guarantee fresh updates
        const isCriticalScript = url.pathname.includes('abcd-sound.js') || 
                                 url.pathname.includes('custom-popup.js') || 
                                 url.pathname.includes('abcd-theme.js') ||
                                 url.pathname.includes('site.webmanifest');

        if (isCriticalScript) {
            event.respondWith(
                fetch(request).then(function (networkResponse) {
                    if (networkResponse && networkResponse.status === 200) {
                        const copy = networkResponse.clone();
                        caches.open(STATIC_CACHE_NAME).then(function (cache) {
                            cache.put(request, copy);
                        });
                    }
                    return networkResponse;
                }).catch(function () {
                    return caches.match(request);
                })
            );
            return;
        }

        // Stale-while-revalidate for fonts, images, stylesheets
        event.respondWith(
            caches.open(STATIC_CACHE_NAME).then(function (cache) {
                return cache.match(request).then(function (cachedResponse) {
                    const fetchPromise = fetch(request).then(function (networkResponse) {
                        if (networkResponse && networkResponse.status === 200) {
                            cache.put(request, networkResponse.clone());
                        }
                        return networkResponse;
                    }).catch(function () {
                        return cachedResponse;
                    });
                    return cachedResponse || fetchPromise;
                });
            })
        );
    }
});

