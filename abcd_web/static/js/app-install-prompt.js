/* static/js/app-install-prompt.js - Premium VIP PWA Install App Modal */

(function () {
    'use strict';

    const DISMISS_SESSION_KEY = 'abcd_install_dismissed_session';
    const INSTALLED_KEY = 'abcd_app_installed';

    // Check if current page is in the blacklist where NO install popups should EVER show
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
        return;
    }

    // 1. If already installed or dismissed this session, don't show automatically
    if (localStorage.getItem(INSTALLED_KEY) === 'true') {
        return;
    }

    // Check if running in standalone mode (already installed PWA)
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches || 
                         window.navigator.standalone === true;
    if (isStandalone) {
        localStorage.setItem(INSTALLED_KEY, 'true');
        return;
    }

    // Detect iOS
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;

    let deferredPrompt = null;
    let installModal = null;
    let installOverlay = null;

    // 2. Intercept browser's native beforeinstallprompt to suppress default browser prompt
    window.addEventListener('beforeinstallprompt', (e) => {
        // Prevent default mini-infobar or bottom sheet
        e.preventDefault();
        deferredPrompt = e;
        window.deferredInstallPrompt = e;

        // Session check: Don't nag if dismissed in this session
        if (sessionStorage.getItem(DISMISS_SESSION_KEY) === 'true') {
            return;
        }

        // Wait a few seconds so user engages with the page first
        setTimeout(() => {
            // Coordinate with notification prompt if active
            if (window.__abcd_active_prompt) {
                const checkInterval = setInterval(() => {
                    if (!window.__abcd_active_prompt) {
                        clearInterval(checkInterval);
                        setTimeout(showInstallModal, 2500);
                    }
                }, 1000);
            } else {
                showInstallModal();
            }
        }, 4000);
    });

    // Detect appinstalled event
    window.addEventListener('appinstalled', () => {
        localStorage.setItem(INSTALLED_KEY, 'true');
        hideInstallModal();
    });

    // 3. Inject Styles for the VIP Install Modal
    function injectStyles() {
        if (document.getElementById('abcd-install-styles')) return;
        const style = document.createElement('style');
        style.id = 'abcd-install-styles';
        style.textContent = `
            .abcd-install-overlay {
                position: fixed;
                inset: 0;
                background: rgba(10, 15, 30, 0.65);
                backdrop-filter: blur(10px);
                -webkit-backdrop-filter: blur(10px);
                z-index: 999998;
                opacity: 0;
                visibility: hidden;
                transition: opacity 0.35s ease, visibility 0.35s ease;
            }
            .abcd-install-overlay.visible {
                opacity: 1;
                visibility: visible;
            }
            .abcd-install-modal {
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -46%) scale(0.95);
                width: min(92vw, 480px);
                background: linear-gradient(145deg, #ffffff 0%, #f8faff 100%);
                border: 1.5px solid rgba(255, 255, 255, 0.8);
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
            .abcd-install-modal.visible {
                opacity: 1;
                visibility: visible;
                transform: translate(-50%, -50%) scale(1);
            }
            body.dark-theme .abcd-install-modal {
                background: linear-gradient(145deg, #1e1533 0%, #110d22 100%);
                border: 1.5px solid rgba(168, 85, 247, 0.25);
                box-shadow: 0 25px 70px rgba(0, 0, 0, 0.6), 0 0 50px rgba(147, 51, 234, 0.25);
                color: #f1f5f9;
            }
            .abcd-install-ambient-glow {
                position: absolute;
                top: -80px;
                right: -80px;
                width: 220px;
                height: 220px;
                background: radial-gradient(circle, rgba(124, 58, 237, 0.22) 0%, transparent 70%);
                border-radius: 50%;
                pointer-events: none;
            }
            .abcd-install-badge {
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
            body.dark-theme .abcd-install-badge {
                background: linear-gradient(135deg, rgba(168, 85, 247, 0.2), rgba(99, 102, 241, 0.2));
                border-color: rgba(168, 85, 247, 0.4);
                color: #c084fc;
            }
            .abcd-install-header {
                display: flex;
                align-items: flex-start;
                gap: 16px;
                margin-bottom: 14px;
            }
            .abcd-install-icon-wrap {
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
            .abcd-install-title {
                font-size: 1.35rem;
                font-weight: 800;
                color: #0f172a;
                line-height: 1.25;
                margin-bottom: 4px;
            }
            body.dark-theme .abcd-install-title {
                color: #ffffff;
            }
            .abcd-install-subtitle {
                font-size: 0.88rem;
                color: #64748b;
                line-height: 1.4;
            }
            body.dark-theme .abcd-install-subtitle {
                color: #94a3b8;
            }
            .abcd-install-benefits {
                margin: 18px 0 22px 0;
                display: flex;
                flex-direction: column;
                gap: 10px;
            }
            .abcd-install-benefit-item {
                display: flex;
                align-items: center;
                gap: 12px;
                font-size: 0.88rem;
                color: #334155;
            }
            body.dark-theme .abcd-install-benefit-item {
                color: #cbd5e1;
            }
            .abcd-install-benefit-icon {
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
            body.dark-theme .abcd-install-benefit-icon {
                background: rgba(168, 85, 247, 0.15);
                color: #c084fc;
            }
            .abcd-install-actions {
                display: flex;
                flex-direction: column;
                gap: 10px;
                margin-top: 6px;
            }
            .abcd-install-btn-main {
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
            }
            .abcd-install-btn-main:hover {
                transform: translateY(-2px);
                box-shadow: 0 12px 30px rgba(102, 126, 234, 0.5);
            }
            .abcd-install-btn-sec {
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
            .abcd-install-btn-sec:hover {
                color: #0f172a;
            }
            body.dark-theme .abcd-install-btn-sec {
                color: #94a3b8;
            }
            body.dark-theme .abcd-install-btn-sec:hover {
                color: #ffffff;
            }
            .abcd-install-close-btn {
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
            .abcd-install-close-btn:hover {
                background: rgba(0, 0, 0, 0.06);
                color: #0f172a;
            }
            body.dark-theme .abcd-install-close-btn:hover {
                background: rgba(255, 255, 255, 0.1);
                color: #ffffff;
            }
            @media (max-width: 480px) {
                .abcd-install-modal {
                    padding: 26px 20px;
                    border-radius: 24px;
                }
                .abcd-install-icon-wrap {
                    width: 52px;
                    height: 52px;
                    font-size: 1.7rem;
                }
                .abcd-install-title {
                    font-size: 1.2rem;
                }
            }
        `;
        document.head.appendChild(style);
    }

    // 4. Build Modal Elements
    function buildModal() {
        if (installModal) return;
        injectStyles();

        installOverlay = document.createElement('div');
        installOverlay.className = 'abcd-install-overlay';
        installOverlay.id = 'abcdInstallOverlay';

        installModal = document.createElement('div');
        installModal.className = 'abcd-install-modal';
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
            <div class="abcd-install-ambient-glow"></div>
            <button class="abcd-install-close-btn" id="abcdInstallCloseBtn" aria-label="Close">&times;</button>
            <div class="abcd-install-badge">
                <i class='bx bxs-star'></i> VIP Learning Experience
            </div>
            <div class="abcd-install-header">
                <div class="abcd-install-icon-wrap">
                    <i class='bx bxs-graduation'></i>
                </div>
                <div>
                    <h3 class="abcd-install-title">Install ABCD Smart App</h3>
                    <p class="abcd-install-subtitle">Your dedicated campus portal, engineered for top focus & performance.</p>
                </div>
            </div>
            <div class="abcd-install-benefits">
                <div class="abcd-install-benefit-item">
                    <div class="abcd-install-benefit-icon"><i class='bx bx-zap'></i></div>
                    <div><strong>2x Faster Performance:</strong> Instant load times with zero browser clutter.</div>
                </div>
                <div class="abcd-install-benefit-item">
                    <div class="abcd-install-benefit-icon"><i class='bx bx-bell'></i></div>
                    <div><strong>Priority Notifications:</strong> Real-time seat updates, fee reminders & Guidy alerts.</div>
                </div>
                <div class="abcd-install-benefit-item">
                    <div class="abcd-install-benefit-icon"><i class='bx bx-wifi-off'></i></div>
                    <div><strong>Offline Preparedness:</strong> Rapid access to key schedules anytime, anywhere.</div>
                </div>
            </div>
            ${helperNote}
            <div class="abcd-install-actions">
                <button class="abcd-install-btn-main" id="abcdInstallAppBtn">
                    ${installBtnText}
                </button>
                <button class="abcd-install-btn-sec" id="abcdInstallLaterBtn">
                    Continue in Browser
                </button>
            </div>
        `;

        document.body.appendChild(installOverlay);
        document.body.appendChild(installModal);

        // Click outside closes
        installOverlay.addEventListener('click', hideInstallModal);

        // Close button
        document.getElementById('abcdInstallCloseBtn').addEventListener('click', hideInstallModal);

        // Later button
        document.getElementById('abcdInstallLaterBtn').addEventListener('click', hideInstallModal);

        // Install button
        document.getElementById('abcdInstallAppBtn').addEventListener('click', async () => {
            if (deferredPrompt) {
                deferredPrompt.prompt();
                const choice = await deferredPrompt.userChoice;
                if (choice && choice.outcome === 'accepted') {
                    localStorage.setItem(INSTALLED_KEY, 'true');
                }
                deferredPrompt = null;
                window.deferredInstallPrompt = null;
                hideInstallModal();
            } else if (isIOS) {
                if (window.CustomPopup) {
                    CustomPopup.alert('On Safari iOS: Tap the Share button at the bottom of your screen and choose "Add to Home Screen".', '📱 Install Instructions');
                }
                hideInstallModal();
            } else {
                // Fallback prompt explanation
                if (window.CustomPopup) {
                    CustomPopup.alert('To install ABCD on desktop or mobile, look for the "Install" icon in your browser URL address bar.', '📲 Install ABCD App');
                }
                hideInstallModal();
            }
        });
    }

    function showInstallModal() {
        buildModal();
        window.__abcd_active_prompt = 'install';
        requestAnimationFrame(() => {
            installOverlay.classList.add('visible');
            installModal.classList.add('visible');
        });
    }

    function hideInstallModal() {
        sessionStorage.setItem(DISMISS_SESSION_KEY, 'true');
        if (installOverlay) installOverlay.classList.remove('visible');
        if (installModal) installModal.classList.remove('visible');
        setTimeout(() => {
            if (window.__abcd_active_prompt === 'install') {
                window.__abcd_active_prompt = null;
            }
        }, 300);
    }

    // Expose global manual trigger so any button can launch it
    window.showABCDInstallPrompt = function () {
        showInstallModal();
    };

})();
