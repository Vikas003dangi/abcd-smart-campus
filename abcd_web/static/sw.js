// static/sw.js - ABCD & Guidy PWA Service Worker for Web Push Notifications

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
            data = { title: 'ABCD Notification', body: event.data.text() };
        }
    }

    const title = data.title || 'ABCD Coaching & Library';
    const icon = data.icon || '/static/data/favicon/favicon-96x96.png';
    const badge = data.badge || '/static/data/favicon/favicon-32x32.png';

    const options = {
        body: data.body || 'You have a new update.',
        icon: icon,
        badge: badge,
        vibrate: [200, 100, 200],
        tag: data.tag || 'abcd-general-notif',
        renotify: true,
        data: {
            url: data.url || '/',
            timestamp: data.timestamp || Date.now()
        },
        actions: [
            { action: 'open', title: 'Open' }
        ]
    };

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();
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
