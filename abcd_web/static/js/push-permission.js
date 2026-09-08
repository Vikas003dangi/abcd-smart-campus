/* static/js/push-permission.js - Non-intrusive Custom PWA/TWA Web Push Permission UI */

(function () {
    'use strict';

    const ALLOWED_KEY = 'abcd_push_allowed';
    const DISMISS_SESSION_KEY = 'abcd_push_prompt_dismissed_session';
    const SNOOZE_KEY = 'abcd_push_snooze_until';
    const SNOOZE_DURATION_MS = 3 * 24 * 60 * 60 * 1000; // 3 days (occasional reminder)

    // 1. Check feature support
    if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
        return;
    }

    // Check if current page is in the blacklist where NO notification permission popups should EVER show
    function isPageExcluded() {
        if (window.__disablePermissionPrompts === true || window.__disablePushPrompts === true) {
            return true;
        }
        if (document.querySelector('meta[name="disable-permission-prompts"]') ||
            document.querySelector('meta[name="disable-push-prompts"]')) {
            return true;
        }
        if (document.body && (
            document.body.dataset.disablePermissionPrompts === 'true' ||
            document.body.dataset.disablePushPrompts === 'true' ||
            document.body.classList.contains('no-permission-prompts')
        )) {
            return true;
        }

        const path = (window.location.pathname || '').toLowerCase();
        const excludedPaths = [
            '/register',
            '/login',
            '/admission',
            '/achievement',
            '/seat',
            '/dashboard',
            '/student-dashboard',
            '/teacher-dashboard',
            '/alumni-dashboard',
            '/student_dashboard',
            '/teacher_dashboard',
            '/alumni_dashboard',
        ];
        for (let i = 0; i < excludedPaths.length; i++) {
            if (path.includes(excludedPaths[i])) return true;
        }

        if (document.getElementById('admissionForm') ||
            document.getElementById('achievementForm') ||
            document.getElementById('registrationForm') ||
            document.getElementById('loginForm') ||
            document.querySelector('.admission-form-container') ||
            document.querySelector('.achievement-form-container') ||
            document.getElementById('seatModalOverlay') ||
            document.getElementById('seatModalContainer') ||
            document.getElementById('seatInterestOverlay')) {
            return true;
        }

        return false;
    }

    if (isPageExcluded()) {
        window.promptNotificationForAction = function () { return Promise.resolve(false); };
        window.ensureNotificationPermission = window.promptNotificationForAction;
        window.showABCDNotificationPrompt = function () {};
        return;
    }

    let bubble = null;
    let pendingCallback = null;

    // Detect if running as standalone PWA or TWA (Play Store app container)
    function isRunningAsApp() {
        return window.matchMedia('(display-mode: standalone)').matches ||
               window.navigator.standalone === true ||
               document.referrer.includes('android-app://') ||
               window.matchMedia('(display-mode: fullscreen)').matches;
    }

    // 2. Inject CSS styles for the notification prompt (dual-theme supported)
    function injectStyles() {
        if (document.getElementById('abcd-push-styles')) return;
        const style = document.createElement('style');
        style.id = 'abcd-push-styles';
        style.textContent = `
            .abcd-push-bubble {
                position: fixed;
                bottom: 24px;
                right: 24px;
                max-width: 380px;
                width: calc(100vw - 36px);
                background: linear-gradient(145deg, #ffffff 0%, #f9fafb 100%);
                backdrop-filter: blur(16px);
                -webkit-backdrop-filter: blur(16px);
                border: 1.5px solid rgba(226, 232, 240, 0.9);
                border-radius: 20px;
                padding: 20px 22px;
                color: #1e293b;
                font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
                box-shadow: 0 20px 50px rgba(0, 0, 0, 0.18), 0 0 25px rgba(108, 99, 255, 0.15);
                z-index: 999997;
                transform: translateY(130%);
                opacity: 0;
                transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.4s ease;
            }
            .abcd-push-bubble.show {
                transform: translateY(0);
                opacity: 1;
            }
            body.dark-theme .abcd-push-bubble {
                background: linear-gradient(145deg, #1b132c 0%, #110d20 100%);
                border: 1.5px solid rgba(168, 85, 247, 0.25);
                color: #f1f5f9;
                box-shadow: 0 25px 60px rgba(0, 0, 0, 0.6), 0 0 30px rgba(124, 58, 237, 0.25);
            }
            .abcd-push-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 10px;
            }
            .abcd-push-title {
                display: flex;
                align-items: center;
                gap: 10px;
                font-size: 1.02rem;
                font-weight: 700;
                color: #0f172a;
            }
            body.dark-theme .abcd-push-title {
                color: #ffffff;
            }
            .abcd-push-bell-icon {
                width: 34px;
                height: 34px;
                border-radius: 10px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                color: #ffffff;
                font-size: 1.15rem;
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.35);
                animation: bellShake 3s infinite ease-in-out;
            }
            @keyframes bellShake {
                0%, 80%, 100% { transform: rotate(0deg); }
                85% { transform: rotate(14deg); }
                90% { transform: rotate(-14deg); }
                95% { transform: rotate(8deg); }
            }
            .abcd-push-close {
                background: transparent;
                border: none;
                color: #94a3b8;
                font-size: 1.3rem;
                cursor: pointer;
                padding: 4px;
                line-height: 1;
                border-radius: 50%;
                transition: color 0.2s, background 0.2s;
            }
            .abcd-push-close:hover {
                color: #0f172a;
                background: rgba(0, 0, 0, 0.05);
            }
            body.dark-theme .abcd-push-close:hover {
                color: #ffffff;
                background: rgba(255, 255, 255, 0.1);
            }
            .abcd-push-body {
                font-size: 0.86rem;
                color: #475569;
                line-height: 1.5;
                margin-bottom: 16px;
            }
            body.dark-theme .abcd-push-body {
                color: #cbd5e1;
            }
            .abcd-push-actions {
                display: flex;
                align-items: center;
                gap: 10px;
            }
            .abcd-push-btn-allow {
                flex: 1;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: #ffffff;
                border: none;
                padding: 10px 16px;
                border-radius: 12px;
                font-size: 0.88rem;
                font-weight: 700;
                cursor: pointer;
                box-shadow: 0 4px 15px rgba(102, 126, 234, 0.35);
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 6px;
                transition: transform 0.15s, box-shadow 0.15s;
            }
            .abcd-push-btn-allow:hover {
                transform: translateY(-1px);
                box-shadow: 0 6px 20px rgba(102, 126, 234, 0.5);
            }
            .abcd-push-btn-later {
                background: rgba(0, 0, 0, 0.04);
                color: #64748b;
                border: 1px solid rgba(0, 0, 0, 0.08);
                padding: 10px 14px;
                border-radius: 12px;
                font-size: 0.88rem;
                font-weight: 600;
                cursor: pointer;
                transition: background 0.2s, color 0.2s;
            }
            .abcd-push-btn-later:hover {
                background: rgba(0, 0, 0, 0.08);
                color: #0f172a;
            }
            body.dark-theme .abcd-push-btn-later {
                background: rgba(255, 255, 255, 0.08);
                color: #94a3b8;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            body.dark-theme .abcd-push-btn-later:hover {
                background: rgba(255, 255, 255, 0.15);
                color: #ffffff;
            }
            .abcd-push-guide-callout {
                display: flex;
                align-items: flex-start;
                gap: 12px;
                background: rgba(102, 126, 234, 0.08);
                border: 1px dashed rgba(102, 126, 234, 0.3);
                border-radius: 14px;
                padding: 12px 14px;
                font-size: 0.88rem;
                line-height: 1.5;
                color: #334155;
            }
            body.dark-theme .abcd-push-guide-callout {
                background: rgba(168, 85, 247, 0.1);
                border-color: rgba(168, 85, 247, 0.3);
                color: #e2e8f0;
            }
            .abcd-push-arrow-up {
                font-size: 1.4rem;
                line-height: 1;
                animation: floatUp 1.2s infinite ease-in-out alternate;
            }
            @keyframes floatUp {
                0% { transform: translateY(0); }
                100% { transform: translateY(-4px); }
            }
            @media (max-width: 480px) {
                .abcd-push-bubble {
                    bottom: 18px;
                    right: 14px;
                    left: 14px;
                    width: auto;
                    padding: 18px;
                }
            }
        `;
        document.head.appendChild(style);
    }

    // 3. Build and attach HTML bubble element with optional custom text
    function buildBubble(options = {}) {
        if (bubble) return;
        injectStyles();

        const title = options.title || 'Enable Notifications';
        const body = options.body || 'Get instant alerts for class updates, live library seat availability, and Guidy study support.';
        const allowBtnText = options.allowBtnText || 'Allow Alerts';

        bubble = document.createElement('div');
        bubble.className = 'abcd-push-bubble';
        bubble.id = 'abcdPushBubble';
        bubble.innerHTML = `
            <div class="abcd-push-header">
                <div class="abcd-push-title">
                    <div class="abcd-push-bell-icon">
                        <i class="bx bxs-bell-ring"></i>
                    </div>
                    <span>${title}</span>
                </div>
                <button class="abcd-push-close" id="abcdPushCloseBtn" aria-label="Close">&times;</button>
            </div>
            <div class="abcd-push-body">
                ${body}
            </div>
            <div class="abcd-push-actions">
                <button class="abcd-push-btn-allow" id="abcdPushAllowBtn">
                    <i class='bx bx-check-shield'></i> ${allowBtnText}
                </button>
                <button class="abcd-push-btn-later" id="abcdPushLaterBtn">Not Now</button>
            </div>
        `;

        document.body.appendChild(bubble);

        // Click listeners
        document.getElementById('abcdPushAllowBtn').addEventListener('click', requestNotificationPermission);
        document.getElementById('abcdPushLaterBtn').addEventListener('click', () => dismissPrompt(true));
        document.getElementById('abcdPushCloseBtn').addEventListener('click', () => dismissPrompt(true));
    }

    function showBubble(options = {}) {
        if (isPageExcluded()) return;
        if (window.__abcd_active_prompt && window.__abcd_active_prompt !== 'notification') {
            return;
        }
        if (bubble && bubble.parentNode) {
            bubble.parentNode.removeChild(bubble);
            bubble = null;
        }
        buildBubble(options);
        window.__abcd_active_prompt = 'notification';
        requestAnimationFrame(() => {
            if (bubble) bubble.classList.add('show');
        });
    }

    function showBrowserPromptGuide() {
        if (isPageExcluded() || !bubble) return;
        const isApp = isRunningAsApp();
        const guideText = isApp
            ? 'Please tap <strong>"Allow"</strong> on the device permission dialog to activate live notifications.'
            : 'Please click <strong>"Allow"</strong> on the browser prompt at the top-left to activate live notifications on this device.';

        bubble.innerHTML = `
            <div class="abcd-push-header">
                <div class="abcd-push-title">
                    <div class="abcd-push-bell-icon" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); animation: none;">
                        <i class='bx bx-check-circle'></i>
                    </div>
                    <span>Confirm Permission</span>
                </div>
            </div>
            <div class="abcd-push-body" style="margin-bottom: 0;">
                <div class="abcd-push-guide-callout">
                    <span class="abcd-push-arrow-up">👆</span>
                    <div>${guideText}</div>
                </div>
            </div>
        `;
    }

    function showDeniedInstructions() {
        if (isPageExcluded()) return;
        injectStyles();
        if (!bubble) {
            bubble = document.createElement('div');
            bubble.className = 'abcd-push-bubble';
            bubble.id = 'abcdPushBubble';
            document.body.appendChild(bubble);
        }
        window.__abcd_active_prompt = 'notification';

        const isApp = isRunningAsApp();
        const stepsHtml = isApp ? `
            <ol style="margin: 8px 0 0 16px; padding: 0; font-size: 0.85rem; line-height: 1.6;">
                <li>Open your device <strong>Settings</strong>.</li>
                <li>Tap <strong>Apps</strong> &gt; <strong>ABCD Smart Campus</strong>.</li>
                <li>Tap <strong>Notifications</strong> and switch to <strong>Allowed</strong>.</li>
            </ol>
        ` : `
            <ol style="margin: 8px 0 0 16px; padding: 0; font-size: 0.85rem; line-height: 1.6;">
                <li>Click the <strong>tune / lock icon (🔒)</strong> in your address bar next to the URL.</li>
                <li>Switch <strong>Notifications</strong> to <strong>Allow</strong>.</li>
                <li>Refresh the page to start receiving alerts.</li>
            </ol>
        `;

        bubble.innerHTML = `
            <div class="abcd-push-header">
                <div class="abcd-push-title">
                    <div class="abcd-push-bell-icon" style="background: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%); animation: none;">
                        <i class='bx bx-bell-off'></i>
                    </div>
                    <span>${isApp ? 'App Notifications Disabled' : 'Notifications Blocked'}</span>
                </div>
                <button class="abcd-push-close" id="abcdPushCloseBtn" aria-label="Close">&times;</button>
            </div>
            <div class="abcd-push-body">
                Notifications are currently turned off on your device. To enable them:
                ${stepsHtml}
            </div>
            <div class="abcd-push-actions">
                <button class="abcd-push-btn-allow" id="abcdPushDeniedCloseBtn" style="background: #475569;">
                    Got It
                </button>
            </div>
        `;
        requestAnimationFrame(() => {
            if (bubble) bubble.classList.add('show');
        });

        const closeBtn = document.getElementById('abcdPushCloseBtn');
        const gotItBtn = document.getElementById('abcdPushDeniedCloseBtn');
        if (closeBtn) closeBtn.addEventListener('click', () => dismissPrompt(true));
        if (gotItBtn) gotItBtn.addEventListener('click', () => dismissPrompt(true));
    }

    function dismissPrompt(isUserAction = true) {
        if (isUserAction) {
            sessionStorage.setItem(DISMISS_SESSION_KEY, 'true');
            try {
                // Snooze for 3 days so it reappears occasionally (not too fast, not too late)
                localStorage.setItem(SNOOZE_KEY, String(Date.now() + SNOOZE_DURATION_MS));
            } catch (e) {}
        }
        if (typeof pendingCallback === 'function') {
            pendingCallback(false);
            pendingCallback = null;
        }
        if (bubble) {
            bubble.classList.remove('show');
            setTimeout(() => {
                if (bubble && bubble.parentNode) bubble.parentNode.removeChild(bubble);
                bubble = null;
                if (window.__abcd_active_prompt === 'notification') {
                    window.__abcd_active_prompt = null;
                }
            }, 400);
        }
    }

    // Sound chime helper
    function playChime(src) {
        try {
            const audio = new Audio(src || '/static/audio/PWA.mp3');
            audio.volume = 0.85;
            audio.play().catch(function () {});
        } catch (e) {}
    }

    // Direct OS Device Notification Trigger
    async function triggerDeviceTestNotification(reg, title, body) {
        try {
            if (!reg) {
                reg = await navigator.serviceWorker.ready;
            }
            if (reg && 'showNotification' in reg) {
                await reg.showNotification(title || 'ABCD Smart Campus', {
                    body: body || '🔔 Live device notifications are working properly!',
                    icon: '/static/data/favicon/web-app-manifest-192x192.png',
                    badge: '/static/data/favicon/favicon-96x96.png',
                    tag: 'abcd-device-alert-' + Date.now(),
                    renotify: true,
                    requireInteraction: false,
                    vibrate: [200, 100, 200],
                    data: {
                        url: window.location.href,
                        timestamp: Date.now()
                    }
                });
            }
        } catch (e) {
            console.warn('Direct device notification display issue:', e);
        }
    }

    // 4. Permission Request Triggered on User Action
    async function requestNotificationPermission() {
        try {
            if (Notification.permission === 'denied') {
                showDeniedInstructions();
                if (typeof pendingCallback === 'function') {
                    pendingCallback(false);
                    pendingCallback = null;
                }
                return;
            }

            // Guide user to the browser/device prompt
            showBrowserPromptGuide();

            const permission = await Notification.requestPermission();
            if (permission === 'granted') {
                localStorage.setItem(ALLOWED_KEY, 'true');
                localStorage.setItem('abcd_push_user_consented', 'true');
                sessionStorage.setItem(DISMISS_SESSION_KEY, 'true');
                try { localStorage.removeItem(SNOOZE_KEY); } catch (e) {}
                dismissPrompt(false);

                const reg = await registerServiceWorkerAndSync({ sendWelcome: true });

                // Fire real device notification immediately
                await triggerDeviceTestNotification(
                    reg,
                    '🎉 Notifications Activated!',
                    'Your device is now connected for instant library seat & campus alerts.'
                );

                playChime('/static/audio/PWA.mp3');

                if (typeof pendingCallback === 'function') {
                    pendingCallback(true);
                    pendingCallback = null;
                }
            } else if (permission === 'denied') {
                showDeniedInstructions();
                if (typeof pendingCallback === 'function') {
                    pendingCallback(false);
                    pendingCallback = null;
                }
            } else {
                dismissPrompt(true);
            }
        } catch (e) {
            console.error('Error requesting notification permission:', e);
            dismissPrompt(true);
        }
    }

    async function registerServiceWorkerAndSync(options = {}) {
        try {
            if (Notification.permission !== 'granted') {
                return null;
            }

            let reg;
            try {
                reg = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
            } catch (swErr) {
                console.warn('Fallback registering /static/sw.js:', swErr);
                reg = await navigator.serviceWorker.register('/static/sw.js');
            }
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
                return reg;
            }

            let sub = await reg.pushManager.getSubscription();
            if (!sub) {
                try {
                    const convertedKey = urlB64ToUint8Array(vapidPublicKey);
                    sub = await reg.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: convertedKey
                    });
                } catch (subErr) {
                    console.warn('Subscription with converted key failed, retrying with raw key:', subErr);
                    try {
                        sub = await reg.pushManager.subscribe({
                            userVisibleOnly: true,
                            applicationServerKey: vapidPublicKey
                        });
                    } catch (rawErr) {
                        console.warn('Raw key subscribe failed:', rawErr);
                    }
                }
            }

            if (sub) {
                const csrfToken = getCsrfToken();
                const payload = sub.toJSON ? sub.toJSON() : JSON.parse(JSON.stringify(sub));
                if (options.sendWelcome) {
                    payload.send_welcome = true;
                }
                await fetch('/api/save-push-subscription/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify(payload)
                });
            }

            return reg;
        } catch (err) {
            console.error('Failed to register Web Push Subscription:', err);
            return null;
        }
    }

    // 5. Contextual Action Prompting & Manual Triggers
    window.promptNotificationForAction = function (actionType = 'general', customMessage = null) {
        if (Notification.permission === 'granted') {
            return Promise.resolve(true);
        }

        if (Notification.permission === 'denied') {
            showDeniedInstructions();
            return Promise.resolve(false);
        }

        let title = 'Enable Notifications';
        let body = 'Get instant live alerts on your device.';

        const act = (actionType || '').toLowerCase();
        if (act.includes('seat') || act.includes('hold') || act.includes('switch')) {
            title = 'Live Seat Alerts';
            body = customMessage || 'Enable device notifications to receive instant updates when your seat, shift, or hold status changes.';
        } else if (act.includes('guidy') || act.includes('chat') || act.includes('message')) {
            title = 'Guidy Study Alerts';
            body = customMessage || 'Enable notifications to get instant alerts when teachers or study mentors reply to your questions.';
        } else if (act.includes('reminder') || act.includes('alarm')) {
            title = 'Class & Study Reminders';
            body = customMessage || 'Enable notifications so you never miss scheduled study alarms and class timings.';
        } else if (customMessage) {
            body = customMessage;
        }

        return new Promise((resolve) => {
            pendingCallback = resolve;
            showBubble({
                title: title,
                body: body,
                allowBtnText: 'Allow Alerts'
            });
        });
    };

    window.ensureNotificationPermission = window.promptNotificationForAction;

    window.showABCDNotificationPrompt = function () {
        if (Notification.permission === 'denied') {
            showDeniedInstructions();
        } else if (Notification.permission === 'granted') {
            window.testDeviceNotification();
        } else {
            showBubble();
        }
    };

    window.testDeviceNotification = async function () {
        if (Notification.permission !== 'granted') {
            window.showABCDNotificationPrompt();
            return;
        }
        try {
            const reg = await registerServiceWorkerAndSync();
            await triggerDeviceTestNotification(
                reg,
                '⚡ ABCD Device Alert',
                'Live notifications are connected and working on this device!'
            );
            playChime('/static/audio/PWA.mp3');
            if (window.CustomPopup) {
                CustomPopup.alert('Test alert delivered to your device notification tray!', '🔔 Device Alert Verified');
            }
        } catch (e) {
            console.error('Test notification failed:', e);
        }
    };

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

    // 6. Permission State Sync & Tracking
    function syncPermissionState() {
        if (Notification.permission === 'granted') {
            localStorage.setItem(ALLOWED_KEY, 'true');
            localStorage.setItem('abcd_push_user_consented', 'true');
            try { localStorage.removeItem(SNOOZE_KEY); } catch (e) {}
            registerServiceWorkerAndSync();
        } else if (Notification.permission === 'denied') {
            // Only clear consent if user has actively DENIED (not just 'default' during navigation)
            localStorage.removeItem(ALLOWED_KEY);
            localStorage.removeItem('abcd_push_user_consented');
            sessionStorage.removeItem(DISMISS_SESSION_KEY);
        }
        // If permission is 'default', do NOT wipe existing consent — browser may
        // temporarily report 'default' during page navigation even when user already allowed.
    }

    // Listen on window focus & visibility changes (e.g. user toggled settings in Android settings and resumed app)
    window.addEventListener('focus', syncPermissionState);
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            syncPermissionState();
        }
    });

    // Dynamic Permission Tracking: detect if permission was revoked in browser settings
    if ('permissions' in navigator && navigator.permissions.query) {
        try {
            navigator.permissions.query({ name: 'notifications' }).then(function (permStatus) {
                permStatus.onchange = function () {
                    syncPermissionState();
                };
            }).catch(function () {});
        } catch (e) {}
    }

    function shouldShowPrompt() {
        if (Notification.permission === 'granted' || Notification.permission === 'denied') {
            return false;
        }
        // Once the user has ever allowed (even if browser forgets state temporarily during navigation)
        if (localStorage.getItem(ALLOWED_KEY) === 'true' || localStorage.getItem('abcd_push_user_consented') === 'true') {
            return false;
        }
        if (sessionStorage.getItem(DISMISS_SESSION_KEY) === 'true') {
            return false;
        }
        try {
            const snoozeUntil = parseInt(localStorage.getItem(SNOOZE_KEY) || '0', 10);
            if (snoozeUntil && Date.now() < snoozeUntil) {
                return false;
            }
        } catch (e) {}
        return true;
    }

    // Event delegation: auto-prompt when user interacts with elements that push notifications
    document.addEventListener('click', function (e) {
        const trigger = e.target.closest('[data-needs-notification], [data-push-action], .js-prompt-notification');
        if (trigger && Notification.permission !== 'granted') {
            const actionType = trigger.getAttribute('data-push-action') || 'general';
            const msg = trigger.getAttribute('data-push-message') || null;
            window.promptNotificationForAction(actionType, msg);
        }
    }, true);

    // 7. Initialization
    if (Notification.permission === 'granted') {
        localStorage.setItem(ALLOWED_KEY, 'true');
        localStorage.setItem('abcd_push_user_consented', 'true');
        try { localStorage.removeItem(SNOOZE_KEY); } catch (e) {}
        registerServiceWorkerAndSync();
    } else {
        // DO NOT wipe ALLOWED_KEY here — permission may temporarily read as 'default'
        // during page navigation even when the user has previously granted it.
        if (shouldShowPrompt()) {
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', () => {
                    setTimeout(showBubble, 2200);
                });
            } else {
                setTimeout(showBubble, 2200);
            }
        }
    }

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
