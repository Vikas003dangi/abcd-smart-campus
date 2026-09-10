/* static/js/app-install-prompt.js - VIP PWA Smart App Detection & Launch Modal */

(function () {
    'use strict';

    const DISMISS_INSTALL_SESSION_KEY = 'abcd_install_dismissed_session';
    const DISMISS_OPEN_APP_SESSION_KEY = 'abcd_open_app_dismissed_session';
    const INSTALLED_KEY = 'abcd_app_installed';

    // Check if current page is in the blacklist where NO popups should show
    function isPageExcluded() {
        if (window.__disablePermissionPrompts === true || window.__disableInstallPrompts === true) {
            return true;
        }
        if (document.querySelector('meta[name="disable-permission-prompts"]') ||
            document.querySelector('meta[name="disable-install-prompts"]')) {
            return true;
        }
        if (document.body && (
            document.body.dataset.disablePermissionPrompts === 'true' ||
            document.body.dataset.disableInstallPrompts === 'true' ||
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
            document.querySelector('.form-container') ||
            document.getElementById('seatModalOverlay') ||
            document.getElementById('seatModalContainer') ||
            document.getElementById('seatInterestOverlay')) {
            return true;
        }

        return false;
    }

    if (isPageExcluded()) {
        window.showABCDInstallPrompt = function () {};
        window.showABCDOpenInAppPrompt = function () {};
        return;
    }

    // Check if currently running inside the installed PWA standalone mode
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches || 
                         window.navigator.standalone === true ||
                         document.referrer.includes('android-app://');

    if (isStandalone) {
        // User is ALREADY using the installed app!
        localStorage.setItem(INSTALLED_KEY, 'true');
        window.showABCDInstallPrompt = function () {};
        window.showABCDOpenInAppPrompt = function () {};
        return;
    }

    // Detect iOS Safari
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;

    let deferredPrompt = null;
    let pwaOverlay = null;
    let installModal = null;
    let openInAppModal = null;

    // 1. Inject Styles for the VIP Modals
    function injectStyles() {
        if (document.getElementById('abcd-pwa-styles')) return;
        const style = document.createElement('style');
        style.id = 'abcd-pwa-styles';
        style.textContent = `
            .abcd-pwa-overlay {
                position: fixed;
                inset: 0;
                background: rgba(10, 15, 30, 0.68);
                backdrop-filter: blur(10px);
                -webkit-backdrop-filter: blur(10px);
                z-index: 999998;
                opacity: 0;
                visibility: hidden;
                transition: opacity 0.35s ease, visibility 0.35s ease;
            }
            .abcd-pwa-overlay.visible {
                opacity: 1;
                visibility: visible;
            }
            .abcd-pwa-modal {
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -46%) scale(0.95);
                width: min(92vw, 480px);
                background: linear-gradient(145deg, #ffffff 0%, #f8faff 100%);
                border: 1.5px solid rgba(255, 255, 255, 0.85);
                border-radius: 28px;
                padding: 32px 28px;
                box-shadow: 0 25px 70px rgba(0, 0, 0, 0.25), 0 0 40px rgba(108, 99, 255, 0.15);
                color: #1e293b;
                z-index: 999999;
                opacity: 0;
                visibility: hidden;
                transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.35s ease, visibility 0.35s ease;
                font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
                overflow: hidden;
            }
            .abcd-pwa-modal.visible {
                opacity: 1;
                visibility: visible;
                transform: translate(-50%, -50%) scale(1);
            }
            body.dark-theme .abcd-pwa-modal {
                background: linear-gradient(145deg, #1e1533 0%, #110d22 100%);
                border: 1.5px solid rgba(168, 85, 247, 0.25);
                box-shadow: 0 25px 70px rgba(0, 0, 0, 0.6), 0 0 50px rgba(147, 51, 234, 0.25);
                color: #f1f5f9;
            }
            .abcd-pwa-ambient-glow {
                position: absolute;
                top: -80px;
                right: -80px;
                width: 220px;
                height: 220px;
                background: radial-gradient(circle, rgba(124, 58, 237, 0.22) 0%, transparent 70%);
                border-radius: 50%;
                pointer-events: none;
            }
            .abcd-pwa-badge {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 5px 14px;
                background: linear-gradient(135deg, rgba(124, 58, 237, 0.12), rgba(99, 102, 241, 0.12));
                border: 1px solid rgba(124, 58, 237, 0.25);
                color: #7c3aed;
                border-radius: 20px;
                font-size: 0.78rem;
                font-weight: 700;
                letter-spacing: 0.5px;
                text-transform: uppercase;
                margin-bottom: 16px;
            }
            body.dark-theme .abcd-pwa-badge {
                background: linear-gradient(135deg, rgba(168, 85, 247, 0.2), rgba(99, 102, 241, 0.2));
                border-color: rgba(168, 85, 247, 0.4);
                color: #c084fc;
            }
            .abcd-pwa-badge-installed {
                background: linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(5, 150, 105, 0.12));
                border-color: rgba(16, 185, 129, 0.35);
                color: #059669;
            }
            body.dark-theme .abcd-pwa-badge-installed {
                background: linear-gradient(135deg, rgba(16, 185, 129, 0.25), rgba(5, 150, 105, 0.2));
                border-color: rgba(16, 185, 129, 0.45);
                color: #34d399;
            }
            .abcd-pwa-header {
                display: flex;
                align-items: flex-start;
                gap: 16px;
                margin-bottom: 14px;
            }
            .abcd-pwa-icon-wrap {
                width: 62px;
                height: 62px;
                border-radius: 18px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                color: #ffffff;
                font-size: 2rem;
                box-shadow: 0 10px 25px rgba(102, 126, 234, 0.4);
                flex-shrink: 0;
            }
            .abcd-pwa-title {
                font-size: 1.35rem;
                font-weight: 800;
                color: #0f172a;
                line-height: 1.25;
                margin-bottom: 4px;
            }
            body.dark-theme .abcd-pwa-title {
                color: #ffffff;
            }
            .abcd-pwa-subtitle {
                font-size: 0.88rem;
                color: #64748b;
                line-height: 1.4;
            }
            body.dark-theme .abcd-pwa-subtitle {
                color: #94a3b8;
            }
            .abcd-pwa-benefits {
                margin: 18px 0 22px 0;
                display: flex;
                flex-direction: column;
                gap: 10px;
            }
            .abcd-pwa-benefit-item {
                display: flex;
                align-items: center;
                gap: 12px;
                font-size: 0.88rem;
                color: #334155;
            }
            body.dark-theme .abcd-pwa-benefit-item {
                color: #cbd5e1;
            }
            .abcd-pwa-benefit-icon {
                width: 28px;
                height: 28px;
                border-radius: 8px;
                background: rgba(124, 58, 237, 0.1);
                color: #7c3aed;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1rem;
                flex-shrink: 0;
            }
            body.dark-theme .abcd-pwa-benefit-icon {
                background: rgba(168, 85, 247, 0.15);
                color: #c084fc;
            }
            .abcd-pwa-actions {
                display: flex;
                flex-direction: column;
                gap: 10px;
                margin-top: 6px;
            }
            .abcd-pwa-btn-main {
                width: 100%;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: #ffffff;
                border: none;
                border-radius: 14px;
                padding: 13px 20px;
                font-size: 0.98rem;
                font-weight: 700;
                cursor: pointer;
                box-shadow: 0 8px 25px rgba(102, 126, 234, 0.35);
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                transition: transform 0.18s ease, box-shadow 0.18s ease;
                text-decoration: none;
            }
            .abcd-pwa-btn-main:hover {
                transform: translateY(-2px);
                box-shadow: 0 12px 30px rgba(102, 126, 234, 0.5);
                color: #ffffff;
            }
            .abcd-pwa-btn-sec {
                width: 100%;
                background: transparent;
                border: none;
                color: #64748b;
                padding: 8px;
                font-size: 0.85rem;
                font-weight: 600;
                cursor: pointer;
                transition: color 0.2s;
            }
            .abcd-pwa-btn-sec:hover {
                color: #0f172a;
            }
            body.dark-theme .abcd-pwa-btn-sec {
                color: #94a3b8;
            }
            body.dark-theme .abcd-pwa-btn-sec:hover {
                color: #ffffff;
            }
            .abcd-pwa-close-btn {
                position: absolute;
                top: 18px;
                right: 18px;
                background: transparent;
                border: none;
                color: #94a3b8;
                font-size: 1.4rem;
                cursor: pointer;
                border-radius: 50%;
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: background 0.2s, color 0.2s;
            }
            .abcd-pwa-close-btn:hover {
                background: rgba(0, 0, 0, 0.06);
                color: #0f172a;
            }
            body.dark-theme .abcd-pwa-close-btn:hover {
                background: rgba(255, 255, 255, 0.1);
                color: #ffffff;
            }
            @media (max-width: 480px) {
                .abcd-pwa-modal {
                    padding: 26px 20px;
                    border-radius: 24px;
                }
                .abcd-pwa-icon-wrap {
                    width: 52px;
                    height: 52px;
                    font-size: 1.7rem;
                }
                .abcd-pwa-title {
                    font-size: 1.2rem;
                }
            }
        `;
        document.head.appendChild(style);
    }

    function getOrCreateOverlay() {
        injectStyles();
        if (!pwaOverlay) {
            pwaOverlay = document.createElement('div');
            pwaOverlay.className = 'abcd-pwa-overlay';
            pwaOverlay.id = 'abcdPwaOverlay';
            document.body.appendChild(pwaOverlay);
            pwaOverlay.addEventListener('click', hideActiveModal);
        }
        return pwaOverlay;
    }

    function hideActiveModal() {
        if (pwaOverlay) pwaOverlay.classList.remove('visible');
        if (installModal) installModal.classList.remove('visible');
        if (openInAppModal) openInAppModal.classList.remove('visible');
        setTimeout(() => {
            if (window.__abcd_active_prompt === 'install' || window.__abcd_active_prompt === 'open_in_app') {
                window.__abcd_active_prompt = null;
            }
        }, 300);
    }

    // 2. Build and Show "Open in ABCD App" Modal (for devices where app is installed)
    function showOpenInAppModal() {
        if (sessionStorage.getItem(DISMISS_OPEN_APP_SESSION_KEY) === 'true') {
            return;
        }

        getOrCreateOverlay();

        if (!openInAppModal) {
            openInAppModal = document.createElement('div');
            openInAppModal.className = 'abcd-pwa-modal';
            openInAppModal.id = 'abcdOpenInAppModal';

            openInAppModal.innerHTML = `
                <div class="abcd-pwa-ambient-glow"></div>
                <button class="abcd-pwa-close-btn" id="abcdOpenCloseBtn" aria-label="Close">&times;</button>
                <div class="abcd-pwa-badge abcd-pwa-badge-installed">
                    <i class='bx bxs-check-shield'></i> App Installed on this Device
                </div>
                <div class="abcd-pwa-header">
                    <div class="abcd-pwa-icon-wrap">
                        <i class='bx bxs-graduation'></i>
                    </div>
                    <div>
                        <h3 class="abcd-pwa-title">Open in ABCD App</h3>
                        <p class="abcd-pwa-subtitle">Experience faster loading, loud alarm audio, and distraction-free study.</p>
                    </div>
                </div>
                <div class="abcd-pwa-benefits">
                    <div class="abcd-pwa-benefit-item">
                        <div class="abcd-pwa-benefit-icon"><i class='bx bx-bell'></i></div>
                        <div><strong>Guaranteed Alarm Audio:</strong> Full-volume alert tones even when screen is locked.</div>
                    </div>
                    <div class="abcd-pwa-benefit-item">
                        <div class="abcd-pwa-benefit-icon"><i class='bx bx-zap'></i></div>
                        <div><strong>2x Faster Performance:</strong> Instant tab transitions with zero browser lag.</div>
                    </div>
                    <div class="abcd-pwa-benefit-item">
                        <div class="abcd-pwa-benefit-icon"><i class='bx bx-fullscreen'></i></div>
                        <div><strong>Full Screen Focus:</strong> Clean study view without URL bars or extra tabs.</div>
                    </div>
                </div>
                <div class="abcd-pwa-actions">
                    <button class="abcd-pwa-btn-main" id="abcdLaunchAppBtn">
                        <i class='bx bx-link-external'></i> Open ABCD App Now
                    </button>
                    <button class="abcd-pwa-btn-sec" id="abcdOpenLaterBtn">
                        Continue in Browser
                    </button>
                </div>
            `;
            document.body.appendChild(openInAppModal);

            document.getElementById('abcdOpenCloseBtn').addEventListener('click', () => {
                sessionStorage.setItem(DISMISS_OPEN_APP_SESSION_KEY, 'true');
                hideActiveModal();
            });

            document.getElementById('abcdOpenLaterBtn').addEventListener('click', () => {
                sessionStorage.setItem(DISMISS_OPEN_APP_SESSION_KEY, 'true');
                hideActiveModal();
            });

            document.getElementById('abcdLaunchAppBtn').addEventListener('click', () => {
                sessionStorage.setItem(DISMISS_OPEN_APP_SESSION_KEY, 'true');
                hideActiveModal();
                // Navigating to current URL or start_url
                const currentUrl = window.location.href;
                window.location.href = currentUrl;
            });
        }

        window.__abcd_active_prompt = 'open_in_app';
        requestAnimationFrame(() => {
            pwaOverlay.classList.add('visible');
            openInAppModal.classList.add('visible');
        });
    }

    // 3. Build and Show "Install ABCD App" Modal (for devices where app is NOT installed)
    function showInstallModal() {
        if (sessionStorage.getItem(DISMISS_INSTALL_SESSION_KEY) === 'true') {
            return;
        }

        getOrCreateOverlay();

        if (!installModal) {
            installModal = document.createElement('div');
            installModal.className = 'abcd-pwa-modal';
            installModal.id = 'abcdInstallModal';

            const installBtnText = isIOS 
                ? `<i class='bx bx-export'></i> Add to Home Screen` 
                : `<i class='bx bxs-download'></i> Install ABCD App Now`;

            const helperNote = isIOS
                ? `<div style="font-size:0.8rem; color:#8b5cf6; margin-bottom:12px; text-align:center;">
                     Tap the <strong>Share</strong> button <i class='bx bx-share'></i> below and select <strong>'Add to Home Screen'</strong>.
                   </div>`
                : '';

            installModal.innerHTML = `
                <div class="abcd-pwa-ambient-glow"></div>
                <button class="abcd-pwa-close-btn" id="abcdInstallCloseBtn" aria-label="Close">&times;</button>
                <div class="abcd-pwa-badge">
                    <i class='bx bxs-star'></i> VIP Learning Experience
                </div>
                <div class="abcd-pwa-header">
                    <div class="abcd-pwa-icon-wrap">
                        <i class='bx bxs-graduation'></i>
                    </div>
                    <div>
                        <h3 class="abcd-pwa-title">Install ABCD Smart App</h3>
                        <p class="abcd-pwa-subtitle">Your dedicated campus portal, engineered for top focus & performance.</p>
                    </div>
                </div>
                <div class="abcd-pwa-benefits">
                    <div class="abcd-pwa-benefit-item">
                        <div class="abcd-pwa-benefit-icon"><i class='bx bx-zap'></i></div>
                        <div><strong>2x Faster Performance:</strong> Instant load times with zero browser clutter.</div>
                    </div>
                    <div class="abcd-pwa-benefit-item">
                        <div class="abcd-pwa-benefit-icon"><i class='bx bx-bell'></i></div>
                        <div><strong>Priority Notifications:</strong> Real-time seat updates, fee reminders & Guidy alerts.</div>
                    </div>
                    <div class="abcd-pwa-benefit-item">
                        <div class="abcd-pwa-benefit-icon"><i class='bx bx-alarm'></i></div>
                        <div><strong>Full Alarm Support:</strong> Ring loud reminder audio directly on your device.</div>
                    </div>
                </div>
                ${helperNote}
                <div class="abcd-pwa-actions">
                    <button class="abcd-pwa-btn-main" id="abcdInstallAppBtn">
                        ${installBtnText}
                    </button>
                    <button class="abcd-pwa-btn-sec" id="abcdInstallLaterBtn">
                        Continue in Browser
                    </button>
                </div>
            `;
            document.body.appendChild(installModal);

            document.getElementById('abcdInstallCloseBtn').addEventListener('click', () => {
                sessionStorage.setItem(DISMISS_INSTALL_SESSION_KEY, 'true');
                hideActiveModal();
            });

            document.getElementById('abcdInstallLaterBtn').addEventListener('click', () => {
                sessionStorage.setItem(DISMISS_INSTALL_SESSION_KEY, 'true');
                hideActiveModal();
            });

            document.getElementById('abcdInstallAppBtn').addEventListener('click', async () => {
                if (deferredPrompt) {
                    deferredPrompt.prompt();
                    const choice = await deferredPrompt.userChoice;
                    if (choice && choice.outcome === 'accepted') {
                        localStorage.setItem(INSTALLED_KEY, 'true');
                    }
                    deferredPrompt = null;
                    window.deferredInstallPrompt = null;
                    hideActiveModal();
                } else if (isIOS) {
                    if (window.CustomPopup) {
                        CustomPopup.alert('On Safari iOS: Tap the Share button at the bottom of your screen and choose "Add to Home Screen".', 'Install Instructions');
                    }
                    hideActiveModal();
                } else {
                    if (window.CustomPopup) {
                        CustomPopup.alert('To install ABCD on desktop or mobile, look for the "Install" icon in your browser URL address bar.', 'Install ABCD App');
                    }
                    hideActiveModal();
                }
            });
        }

        window.__abcd_active_prompt = 'install';
        requestAnimationFrame(() => {
            pwaOverlay.classList.add('visible');
            installModal.classList.add('visible');
        });
    }

    // 4. Smart Device Detection: Query getInstalledRelatedApps and localStorage
    async function checkDeviceAppStatus() {
        let isInstalled = (localStorage.getItem(INSTALLED_KEY) === 'true');

        if (!isInstalled && 'getInstalledRelatedApps' in navigator) {
            try {
                const relatedApps = await navigator.getInstalledRelatedApps();
                if (relatedApps && relatedApps.length > 0) {
                    isInstalled = true;
                    localStorage.setItem(INSTALLED_KEY, 'true');
                }
            } catch (e) {}
        }

        return isInstalled;
    }

    // Intercept native beforeinstallprompt
    window.addEventListener('beforeinstallprompt', (e) => {
        e.preventDefault();
        deferredPrompt = e;
        window.deferredInstallPrompt = e;

        // If not installed and not dismissed, show install prompt after short delay
        checkDeviceAppStatus().then((isInstalled) => {
            if (isInstalled) {
                // User already installed! Show Open in App instead
                if (sessionStorage.getItem(DISMISS_OPEN_APP_SESSION_KEY) !== 'true') {
                    setTimeout(showOpenInAppModal, 3000);
                }
            } else {
                if (sessionStorage.getItem(DISMISS_INSTALL_SESSION_KEY) !== 'true') {
                    setTimeout(() => {
                        if (window.__abcd_active_prompt) {
                            const checkInterval = setInterval(() => {
                                if (!window.__abcd_active_prompt) {
                                    clearInterval(checkInterval);
                                    setTimeout(showInstallModal, 2000);
                                }
                            }, 1000);
                        } else {
                            showInstallModal();
                        }
                    }, 3500);
                }
            }
        });
    });

    // Detect appinstalled event
    window.addEventListener('appinstalled', () => {
        localStorage.setItem(INSTALLED_KEY, 'true');
        hideActiveModal();
    });

    // Device check on load for browsers that do not fire beforeinstallprompt (e.g. already installed or iOS)
    setTimeout(async () => {
        const isInstalled = await checkDeviceAppStatus();
        if (isInstalled) {
            if (sessionStorage.getItem(DISMISS_OPEN_APP_SESSION_KEY) !== 'true') {
                if (!window.__abcd_active_prompt) {
                    showOpenInAppModal();
                }
            }
        }
    }, 4000);

    // Global manual triggers
    window.showABCDInstallPrompt = function () {
        showInstallModal();
    };

    window.showABCDOpenInAppPrompt = function () {
        showOpenInAppModal();
    };

})();
