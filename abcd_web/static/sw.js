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
            data = { title: 'ABCD | Notification', body: event.data.text() };
        }
    }

    const title = data.title || 'ABCD | Notification';
    const icon = data.icon || '/static/data/favicon/web-app-manifest-192x192.png';
    const badge = data.badge || '/static/data/favicon/favicon-96x96.png';

    const catLower = (data.category || '').toLowerCase();
    const titleLower = (title || '').toLowerCase();
    const tagLower = (data.tag || '').toLowerCase();
    const isAlarm = (data.is_alarm === true ||
                     catLower === 'reminder' || catLower === 'alarm' ||
                     titleLower.includes('reminder') || titleLower.includes('alarm') ||
                     tagLower.includes('reminder') || tagLower.includes('alarm'));

    let sound = data.sound;
    if (!sound) {
        sound = isAlarm ? '/static/audio/alarms and reminders.mp3' : '/static/audio/PWA.mp3';
    } else if (isAlarm && sound === '/static/audio/PWA.mp3') {
        sound = '/static/audio/alarms and reminders.mp3';
    }

    const alarmVibratePattern = [500, 200, 500, 200, 500, 200, 1000, 500, 1000];
    const defaultVibratePattern = [200, 100, 200];

    const options = {
        body: data.body || 'You have a new update.',
        icon: icon,
        badge: badge,
        sound: sound,
        tag: data.tag || (isAlarm ? 'abcd-alarm-' + Date.now() : 'abcd-notification'),
        renotify: true,
        requireInteraction: isAlarm ? true : false,
        silent: false,
        vibrate: isAlarm ? alarmVibratePattern : defaultVibratePattern,
        data: {
            url: data.url || '/',
            timestamp: data.timestamp || Date.now(),
            badge_count: data.badge_count || 1,
            isAlarm: isAlarm,
            sound: sound,
            title: title,
            body: data.body || ''
        },
        actions: isAlarm
            ? [
                { action: 'open_alarm', title: '⏰ Open & Dismiss' },
                { action: 'dismiss', title: 'Close' }
              ]
            : [
                { action: 'open', title: 'Open' }
              ]
    };

    // Update Launcher Icon Badge on Android PWA / Desktop (e.g. 999+ or 1)
    if ('setAppBadge' in self.navigator) {
        const count = parseInt(data.badge_count, 10) || 1;
        self.navigator.setAppBadge(count).catch(function () {});
    }

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
            // 1. Broadcast to any open or background tabs so they immediately ring full audio
            if (clientList && clientList.length > 0) {
                clientList.forEach(function (client) {
                    try {
                        client.postMessage({
                            type: 'ABCD_ALARM_PUSH',
                            title: title,
                            body: data.body,
                            sound: sound,
                            isAlarm: isAlarm,
                            url: data.url
                        });
                    } catch (err) {}
                });
            }

            // Check if this notification is for a Guidy chat currently open & visible in this browser
            const isGuidy = (data.category === 'guidy') ||
                            (data.source === 'guidy') ||
                            (data.tag && String(data.tag).startsWith('guidy-')) ||
                            (data.url && data.url.includes('/guidy'));

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

    // When opening an alarm or clicking open_alarm action, attach ring_alarm=1 param so audio plays instantly
    if (notifData.isAlarm || event.action === 'open_alarm') {
        const sep = targetUrl.includes('?') ? '&' : '?';
        targetUrl = targetUrl + sep + 'ring_alarm=1&alarm_title=' + encodeURIComponent(notifData.title || 'Alarm');
    }

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
            for (let i = 0; i < clientList.length; i++) {
                const client = clientList[i];
                if ('focus' in client) {
                    const clientBase = client.url.split('?')[0];
                    const targetBase = targetUrl.split('?')[0];
                    if (clientBase.includes(targetBase) || client.url.includes('/todo') || targetUrl.startsWith('/')) {
                        if (notifData.isAlarm) {
                            try {
                                client.postMessage({
                                    type: 'ABCD_ALARM_PUSH',
                                    title: notifData.title,
                                    body: notifData.body,
                                    isAlarm: true,
                                    sound: notifData.sound
                                });
                            } catch (e) {}
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
