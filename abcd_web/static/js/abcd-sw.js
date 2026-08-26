// ABCD Service Worker for Learning Reminders
const CACHE_NAME = 'abcd-cache-v1';

self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(self.clients.claim());
});

// Periodic check for reminders
// Note: Real Periodic Sync API is limited. 
// For this demo, we'll use a simple interval when a tab is open,
// but the Service Worker itself can also listen for Push events.

self.addEventListener('push', (event) => {
    const data = event.data ? event.data.json() : {};
    const title = data.title || 'ABCD Learning Reminder';
    const options = {
        body: data.message || 'Time to get back to your course!',
        icon: '/static/data/favicon/favicon.ico',
        badge: '/static/data/favicon/favicon.ico',
        data: { url: data.url || '/' }
    };

    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    event.waitUntil(
        clients.openWindow(event.notification.data.url)
    );
});

// We can't do an infinite loop here reliably without Push, 
// but we'll implement a 'sync' event handler if needed.
