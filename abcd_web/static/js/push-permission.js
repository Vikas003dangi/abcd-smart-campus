/* static/js/push-permission.js - Non-intrusive Custom PWA Web Push Permission UI */

(function () {
    'use strict';

    // 1. Check feature support
    if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
        return;
    }

    const ALLOWED_KEY = 'abcd_push_allowed';
    const DISMISS_SESSION_KEY = 'abcd_push_prompt_dismissed_session';

    // 2. Check if already granted or allowed permanently
    if (Notification.permission === 'granted' || localStorage.getItem(ALLOWED_KEY) === 'true') {
        registerServiceWorkerAndSync();
        return;
    }

    // 3. If explicitly blocked by browser settings, do not prompt
    if (Notification.permission === 'denied') {
        return;
    }

    // 4. Session check: If user clicked "Not Now" or closed in this session, wait until next visit
    if (sessionStorage.getItem(DISMISS_SESSION_KEY) === 'true') {
        return;
    }

    // 4. Inject CSS styles for the floating bubble UI
    const style = document.createElement('style');
    style.textContent = `
        .abcd-push-bubble {
            position: fixed;
            bottom: 24px;
            right: 24px;
            max-width: 360px;
            width: calc(100vw - 32px);
            background: rgba(17, 24, 39, 0.95);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 18px;
            padding: 18px 20px;
            color: #ffffff;
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.4), 0 0 20px rgba(108, 99, 255, 0.2);
            z-index: 999999;
            transform: translateY(120%);
            opacity: 0;
            transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.4s ease;
        }
        .abcd-push-bubble.show {
            transform: translateY(0);
            opacity: 1;
        }
        .abcd-push-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 8px;
        }
        .abcd-push-title {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.98rem;
            font-weight: 700;
            color: #ffffff;
        }
        .abcd-push-title i {
            font-size: 1.2rem;
            color: #6c63ff;
        }
        .abcd-push-close {
            background: transparent;
            border: none;
            color: #9ca3af;
            font-size: 1.2rem;
            cursor: pointer;
            padding: 2px 6px;
            border-radius: 50%;
            transition: color 0.2s;
        }
        .abcd-push-close:hover {
            color: #ffffff;
        }
        .abcd-push-body {
            font-size: 0.85rem;
            color: #9ca3af;
            line-height: 1.45;
            margin-bottom: 14px;
        }
        .abcd-push-actions {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .abcd-push-btn-allow {
            flex: 1;
            background: linear-gradient(135deg, #6c63ff 0%, #8b5cf6 100%);
            color: #ffffff;
            border: none;
            padding: 9px 14px;
            border-radius: 10px;
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(108, 99, 255, 0.4);
            transition: transform 0.15s, box-shadow 0.15s;
        }
        .abcd-push-btn-allow:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(108, 99, 255, 0.5);
        }
        .abcd-push-btn-later {
            background: rgba(255, 255, 255, 0.08);
            color: #d1d5db;
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 9px 14px;
            border-radius: 10px;
            font-size: 0.85rem;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.2s, color 0.2s;
        }
        .abcd-push-btn-later:hover {
            background: rgba(255, 255, 255, 0.15);
            color: #ffffff;
        }
        @media (max-width: 480px) {
            .abcd-push-bubble {
                bottom: 16px;
                right: 16px;
                left: 16px;
                width: auto;
                padding: 16px;
            }
        }
    `;
    document.head.appendChild(style);

    // 5. Build and attach HTML bubble element
    const bubble = document.createElement('div');
    bubble.className = 'abcd-push-bubble';
    bubble.innerHTML = `
        <div class="abcd-push-header">
            <div class="abcd-push-title">
                <i class="bx bxs-bell-ring"></i>
                <span>Enable Notifications</span>
            </div>
            <button class="abcd-push-close" id="abcdPushCloseBtn" aria-label="Close">&times;</button>
        </div>
        <div class="abcd-push-body">
            Get instant Guidy message alerts and important site updates even when the page is closed.
        </div>
        <div class="abcd-push-actions">
            <button class="abcd-push-btn-allow" id="abcdPushAllowBtn">Allow Notifications</button>
            <button class="abcd-push-btn-later" id="abcdPushLaterBtn">Not Now</button>
        </div>
    `;

    // 6. Show bubble after a gentle delay (2.5 seconds)
    window.addEventListener('DOMContentLoaded', () => {
        setTimeout(() => {
            document.body.appendChild(bubble);
            requestAnimationFrame(() => {
                bubble.classList.add('show');
            });
        }, 2500);
    });

    // 7. Event listeners
    document.addEventListener('click', (e) => {
        if (e.target && e.target.id === 'abcdPushAllowBtn') {
            requestNotificationPermission();
        } else if (e.target && (e.target.id === 'abcdPushLaterBtn' || e.target.id === 'abcdPushCloseBtn')) {
            dismissPrompt();
        }
    });

    function dismissPrompt(isSessionDismiss = true) {
        if (isSessionDismiss) {
            sessionStorage.setItem(DISMISS_SESSION_KEY, 'true');
        }
        bubble.classList.remove('show');
        setTimeout(() => {
            if (bubble.parentNode) bubble.parentNode.removeChild(bubble);
        }, 400);
    }

    async function requestNotificationPermission() {
        try {
            const permission = await Notification.requestPermission();
            if (permission === 'granted') {
                localStorage.setItem(ALLOWED_KEY, 'true');
                dismissPrompt(false);
                await registerServiceWorkerAndSync();
            } else {
                dismissPrompt(true);
            }
        } catch (e) {
            console.error('Error requesting notification permission:', e);
            dismissPrompt(true);
        }
    }

    async function registerServiceWorkerAndSync() {
        try {
            // Register service worker at root scope /sw.js
            const reg = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
            await navigator.serviceWorker.ready;

            let vapidPublicKey = window.VAPID_PUBLIC_KEY || getVapidKeyFromMeta();
            if (!vapidPublicKey) {
                try {
                    const res = await fetch('/api/vapid-public-key/');
                    const kData = await res.json();
                    if (kData && kData.vapid_public_key) {
                        vapidPublicKey = kData.vapid_public_key;
                        window.VAPID_PUBLIC_KEY = vapidPublicKey;
                    }
                } catch (e) {
                    console.warn('Failed to fetch VAPID public key:', e);
                }
            }

            if (!vapidPublicKey) {
                console.warn('VAPID public key missing. Web Push subscription postponed.');
                return;
            }

            let sub = await reg.pushManager.getSubscription();
            if (!sub) {
                const convertedKey = urlB64ToUint8Array(vapidPublicKey);
                sub = await reg.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: convertedKey
                });
            }

            // Sync subscription with backend Django API
            const csrfToken = getCsrfToken();
            await fetch('/api/save-push-subscription/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify(sub)
            });
        } catch (err) {
            console.error('Failed to register Web Push Subscription:', err);
        }
    }

    // Global launcher icon app badging utility
    window.updateAppBadge = function (count) {
        if ('setAppBadge' in navigator) {
            const num = parseInt(count, 10);
            if (!isNaN(num) && num > 0) {
                navigator.setAppBadge(num).catch(function () {});
            } else {
                navigator.clearAppBadge().catch(function () {});
            }
        }
    };

    function getVapidKeyFromMeta() {
        const meta = document.querySelector('meta[name="vapid-public-key"]');
        return meta ? meta.getAttribute('content') : null;
    }

    function getCsrfToken() {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, 10) === ('csrftoken=')) {
                    cookieValue = decodeURIComponent(cookie.substring(10));
                    break;
                }
            }
        }
        return cookieValue || '';
    }

    function urlB64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding).replace(/\-/g, '+').replace(/_/g, '/');
        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);
        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }
})();
