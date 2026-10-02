// static/sw.js - ABCD & Guidy PWA Service Worker for Background Web Push & App Badging

const STATIC_CACHE_NAME = 'abcd-static-v20260920-v9';

// ── Persistent TWA mode flag (IndexedDB) ─────────────────────────────────
// Survives Service Worker restarts, unlike the in-memory isTwaMode variable.
const TWA_IDB_NAME = 'abcd_sw_state';
const TWA_IDB_STORE = 'flags';
const TWA_FLAG_KEY = 'twa_mode';
const TWA_FLAG_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

function openTwaIdb() {
    return new Promise(function (resolve, reject) {
        var req = indexedDB.open(TWA_IDB_NAME, 1);
        req.onupgradeneeded = function (e) { e.target.result.createObjectStore(TWA_IDB_STORE); };
        req.onsuccess = function (e) { resolve(e.target.result); };
        req.onerror = function (e) { reject(e.target.error); };
    });
}

function getPersistedTwaMode() {
    return openTwaIdb().then(function (db) {
        return new Promise(function (resolve) {
            var tx = db.transaction(TWA_IDB_STORE, 'readonly');
            var req = tx.objectStore(TWA_IDB_STORE).get(TWA_FLAG_KEY);
            req.onsuccess = function () {
                var val = req.result;
                if (val && val.active && (Date.now() - val.timestamp) < TWA_FLAG_TTL_MS) {
                    resolve(true);
                } else {
                    resolve(false);
                }
            };
            req.onerror = function () { resolve(false); };
        });
    }).catch(function () { return false; });
}

function setPersistedTwaMode(active) {
    return openTwaIdb().then(function (db) {
        var tx = db.transaction(TWA_IDB_STORE, 'readwrite');
        tx.objectStore(TWA_IDB_STORE).put({ active: active, timestamp: Date.now() }, TWA_FLAG_KEY);
    }).catch(function () {});
}

// ── Per-Task Native Scheduling Store (IndexedDB) ─────────────────────────
// Tracks the exact set of tasks confirmed as scheduled in native AlarmManager on THIS device.
const TWA_NATIVE_TASKS_KEY = 'native_scheduled_tasks';

function getNativeScheduledTasks() {
    return openTwaIdb().then(function (db) {
        return new Promise(function (resolve) {
            var tx = db.transaction(TWA_IDB_STORE, 'readonly');
            var req = tx.objectStore(TWA_IDB_STORE).get(TWA_NATIVE_TASKS_KEY);
            req.onsuccess = function () {
                var val = req.result;
                resolve((val && typeof val === 'object') ? val : {});
            };
            req.onerror = function () { resolve({}); };
        });
    }).catch(function () { return {}; });
}

function saveNativeScheduledTasks(tasksMap) {
    return openTwaIdb().then(function (db) {
        var tx = db.transaction(TWA_IDB_STORE, 'readwrite');
        tx.objectStore(TWA_IDB_STORE).put(tasksMap, TWA_NATIVE_TASKS_KEY);
    }).catch(function () {});
}

function removeNativeScheduledTask(taskId) {
    if (!taskId) return Promise.resolve();
    return getNativeScheduledTasks().then(function (tasks) {
        if (tasks[String(taskId)]) {
            delete tasks[String(taskId)];
            return saveNativeScheduledTasks(tasks);
        }
    }).catch(function () {});
}

function clearNativeScheduledTasks() {
    return saveNativeScheduledTasks({});
}

function isTaskNativelyScheduled(taskId) {
    if (!taskId) return Promise.resolve(false);
    return getNativeScheduledTasks().then(function (tasks) {
        var task = tasks[String(taskId)];
        if (!task) return false;
        // Require confirmed exact alarm scheduling: if exact is false or missing, do NOT suppress push
        if (task.exact !== true) {
            return false;
        }
        var now = Date.now();
        // Invalidate if scheduled trigger time is in the past by more than 24 hours
        if (task.triggerAt && now > (task.triggerAt + 24 * 60 * 60 * 1000)) {
            return false;
        }
        return true;
    }).catch(function () { return false; });
}

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

let isTwaMode = false;

self.addEventListener('message', function (event) {
    if (event.data && event.data.type === 'ACTIVE_CHAT_UPDATE') {
        activeChatState = {
            chatType: event.data.chatType,
            chatId: event.data.chatId ? String(event.data.chatId) : null,
            timestamp: Date.now()
        };
    } else if (event.data && event.data.type === 'SET_TWA_MODE') {
        isTwaMode = Boolean(event.data.isTwa);
        setPersistedTwaMode(isTwaMode);
        if (Array.isArray(event.data.tasks)) {
            var tasksMap = {};
            var now = Date.now();
            event.data.tasks.forEach(function (t) {
                if (t && t.id) {
                    tasksMap[String(t.id)] = {
                        triggerAt: Number(t.triggerAt) || 0,
                        addedAt: now
                    };
                }
            });
            saveNativeScheduledTasks(tasksMap);
        }
    } else if (event.data && event.data.type === 'SYNC_NATIVE_TASKS') {
        if (Array.isArray(event.data.tasks)) {
            var syncMap = {};
            var syncNow = Date.now();
            event.data.tasks.forEach(function (t) {
                if (t && t.id) {
                    syncMap[String(t.id)] = {
                        triggerAt: Number(t.triggerAt) || 0,
                        addedAt: syncNow
                    };
                }
            });
            saveNativeScheduledTasks(syncMap);
        }
    } else if (event.data && event.data.type === 'CONFIRM_NATIVE_TASK') {
        if (event.data.id) {
            var confTaskId = String(event.data.id);
            var isExact = Boolean(event.data.exact);
            getNativeScheduledTasks().then(function (tasks) {
                var existing = tasks[confTaskId] || {};
                tasks[confTaskId] = {
                    triggerAt: existing.triggerAt || 0,
                    exact: isExact,
                    confirmedAt: Date.now()
                };
                saveNativeScheduledTasks(tasks);
            });
        }
    } else if (event.data && event.data.type === 'REMOVE_NATIVE_TASK') {
        if (event.data.taskId) {
            removeNativeScheduledTask(String(event.data.taskId));
        }
    } else if (event.data && event.data.type === 'CLEAR_NATIVE_TASKS') {
        clearNativeScheduledTasks();
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
            taskId: data.task_id || null,
            actionToken: data.action_token || null
        },
        actions: (Array.isArray(data.actions) && data.actions.length > 0)
            ? data.actions
            : (isAlarm
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
            )
    };

    // Update Launcher Icon Badge on Android PWA / Desktop (e.g. 999+ or 1)
    if ('setAppBadge' in self.navigator) {
        const count = parseInt(data.badge_count, 10) || 1;
        self.navigator.setAppBadge(count).catch(function () {});
    }

    event.waitUntil(
        // Check persistent TWA mode and confirmed per-task native scheduling
        Promise.all([
            getPersistedTwaMode(),
            isTaskNativelyScheduled(data.task_id)
        ]).then(function (results) {
            var persistedTwaMode = results[0];
            var isNativelyScheduledHere = results[1];
            var effectiveTwaMode = isTwaMode || persistedTwaMode;

            return clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
            if (data.action === 'ACCOUNT_DELETED') {
                if (clientList && clientList.length > 0) {
                    clientList.forEach(function (client) {
                        try {
                            client.postMessage({ type: 'ABCD_ACCOUNT_DELETED' });
                        } catch (e) {}
                    });
                }
                return;
            }

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

            // PER-TASK NATIVE CONFIRMATION SUPPRESSION:
            // Suppress Web Push IF AND ONLY IF this exact task_id is confirmed as
            // scheduled natively in Android AlarmManager on THIS device.
            // If the task was created on another device (or native scheduling failed),
            // isNativelyScheduledHere is false, so Web Push is NOT suppressed!
            if (isAudioAlert && !isGuidy && isNativelyScheduledHere) {
                return;  // Native AlarmReceiver → AlarmPlaybackService handles this on this device
            }

            // Suppress duplicate push card if the alarm is already ringing in active foreground tab
            if ((isAlarm || isReminder) && !isGuidy && clientList && clientList.length > 0) {
                var hasVisibleClient = clientList.some(function (client) {
                    return client.visibilityState === 'visible';
                });
                if (hasVisibleClient) {
                    return;
                }
            }

            // Check if this notification is for a Guidy chat currently open & visible in this browser
            if (isGuidy && clientList && clientList.length > 0) {
                var targetParam = '';
                if (data.url && data.url.includes('?')) {
                    targetParam = data.url.substring(data.url.indexOf('?') + 1);
                }

                var isRecentState = (Date.now() - activeChatState.timestamp) < 120000;
                var activeId = activeChatState.chatId;
                var matchesActiveChat = isRecentState && activeId && (
                    (targetParam && targetParam.includes(activeId)) ||
                    (data.tag && String(data.tag).includes(activeId)) ||
                    (data.url && data.url.includes(activeId))
                );

                var hasVisibleGuidyTab = clientList.some(function (client) {
                    return client.url && client.url.includes('/guidy') && client.visibilityState === 'visible';
                });

                if (hasVisibleGuidyTab && matchesActiveChat) {
                    return;
                }

                var isChatActiveAndVisible = clientList.some(function (client) {
                    if (!client.url || !client.url.includes('/guidy')) return false;
                    if (client.visibilityState !== 'visible') return false;
                    if (targetParam) {
                        return client.url.includes(targetParam);
                    }
                    return false;
                });

                if (isChatActiveAndVisible) {
                    return;
                }
            }

            return self.registration.showNotification(title, options);
        });
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
            const bodyObj = { action: 'stop' };
            if (notifData.actionToken) bodyObj.action_token = notifData.actionToken;
            event.waitUntil(
                fetch('/todo/reminder/' + encodeURIComponent(notifData.taskId) + '/action/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(bodyObj)
                }).catch(function () {})
            );
        }
        return;
    }

    if (event.action === 'snooze') {
        if (notifData.taskId) {
            const bodyObj = { action: 'snooze', minutes: 15 };
            if (notifData.actionToken) bodyObj.action_token = notifData.actionToken;
            event.waitUntil(
                fetch('/todo/reminder/' + encodeURIComponent(notifData.taskId) + '/action/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(bodyObj)
                }).catch(function () {})
            );
        }
        return;
    }
    let targetUrl = notifData.url || '/';

    // Route contextual action buttons
    if (event.action === 'open_todo') {
        targetUrl = notifData.url || '/todo/';
    } else if (event.action === 'open_course') {
        targetUrl = notifData.url || '/courses/';
    } else if (event.action === 'open_guidy') {
        targetUrl = notifData.url || '/guidy/';
    } else if (event.action === 'open_seat') {
        targetUrl = notifData.url || '/dashboard/';
    } else if (event.action === 'open_complaint') {
        targetUrl = notifData.url || '/student/complaints/';
    } else if (event.action === 'open_fees' || event.action === 'view_receipt') {
        targetUrl = notifData.url || '/student/fees/';
    } else if (event.action === 'open_broadcast') {
        targetUrl = notifData.url || '/dashboard/';
    }

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
// LIGHTWEIGHT CACHE FOR INSTANT APP LAUNCH (<100ms) & OFFLINE RESILIENCE
// -----------------------------------------------------------------------------

self.addEventListener('fetch', function (event) {
    const request = event.request;
    if (request.method !== 'GET') return;

    let url;
    try {
        url = new URL(request.url);
    } catch (e) {
        return;
    }

    // 1. Navigation requests (HTML pages): Network-first with branded offline fallback
    if (request.mode === 'navigate') {
        event.respondWith(
            fetch(request).catch(function () {
                return caches.match(request).then(function (cached) {
                    if (cached) return cached;
                    return new Response(
                        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Offline - ABCD Campus</title><style>body{margin:0;padding:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#17022c;color:#fff;font-family:system-ui,-apple-system,sans-serif;text-align:center;box-sizing:border-box;padding:20px}.card{max-width:360px;width:100%;padding:32px 24px;border-radius:24px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);backdrop-filter:blur(10px)}h2{margin:0 0 8px;font-size:1.4rem}p{color:rgba(255,255,255,0.7);font-size:0.95rem;line-height:1.5;margin:0 0 24px}button{background:linear-gradient(135deg,#6c63ff,#764ba2);color:#fff;border:none;padding:12px 28px;border-radius:30px;font-size:1rem;font-weight:600;cursor:pointer;box-shadow:0 4px 14px rgba(108,99,255,0.4);transition:transform .15s}button:active{transform:scale(0.96)}</style></head><body><div class="card"><div style="font-size:3rem;margin-bottom:12px">📡</div><h2>You Are Offline</h2><p>Please check your internet or Wi-Fi connection and tap below to retry.</p><button onclick="window.location.reload()">Retry Connection</button></div></body></html>',
                        { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
                    );
                });
            })
        );
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

