// static/sw.js - ABCD & Guidy PWA Service Worker for Background Web Push & App Badging

self.addEventListener('install', function (event) {
    self.skipWaiting();
});

self.addEventListener('activate', function (event) {
    event.waitUntil(self.clients.claim());
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
    const sound = data.sound || '/static/audio/PWA.mp3';

    const options = {
        body: data.body || 'You have a new update.',
        icon: icon,
        badge: badge,
        sound: sound,
        vibrate: [200, 100, 200, 100, 200],
        tag: data.tag || 'abcd-notification',
        renotify: true,
        requireInteraction: true,
        data: {
            url: data.url || '/',
            timestamp: data.timestamp || Date.now(),
            badge_count: data.badge_count || 1
        },
        actions: [
            { action: 'open', title: 'Open' }
        ]
    };

    // Update Launcher Icon Badge on Android PWA / Desktop (e.g. 999+ or 1)
    if ('setAppBadge' in self.navigator) {
        const count = parseInt(data.badge_count, 10) || 1;
        self.navigator.setAppBadge(count).catch(function () {});
    }

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();

    // Clear Launcher App Badge when notification is opened
    if ('clearAppBadge' in self.navigator) {
        self.navigator.clearAppBadge().catch(function () {});
    }

    const targetUrl = (event.notification.data && event.notification.data.url) ? event.notification.data.url : '/';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
            for (let i = 0; i < clientList.length; i++) {
                const client = clientList[i];
                if ('focus' in client) {
                    if (client.url.includes(targetUrl) || targetUrl === '/') {
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
