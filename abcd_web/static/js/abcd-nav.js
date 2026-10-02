/**
 * ABCD Smart Campus - Unified Navigation & Back Controller (ABCDNav)
 * 
 * Single source of truth for all back-navigation decisions across:
 * - Desktop browsers (Chrome, Firefox, Safari, Edge)
 * - Mobile browsers (Android Chrome, iOS Safari)
 * - Tablets
 * - Installed PWA / standalone modes
 * - Android Bubblewrap / Trusted Web Activity (TWA)
 * 
 * Pipeline:
 * 1. In-page modal / overlay open? -> Close modal, consume Back.
 * 2. Dirty form guard active? -> Show draft manager prompt (Save/Discard/Keep Editing).
 * 3. Stateful component back hook (e.g. Guidy chat/pane)? -> Consume Back in-page.
 * 4. Is Home Base page? -> Show Universal Exit confirmation modal.
 * 5. Sub-page -> Navigate to logical parent (parentUrl / context / path hierarchy / Home Base).
 *    Hardware Back and UI Back always converge to the same intentional destination.
 *    Browser history stack is NOT used as the navigation hierarchy.
 */

(function(window, document) {
    'use strict';

    // Capture Custom Tabs / TWA postMessage port or handshake early
    if (typeof window !== 'undefined' && !window._abcdTwaListenerAttached) {
        window._abcdTwaListenerAttached = true;
        window._abcdTwaDiag = {
            msgs: [],
            portSet: false,
            lastPortsLength: 0,
            nativeLogs: [],
            nativeSha256: null,
            exitAttempts: []
        };
        window.addEventListener('message', function(event) {
            try {
                var dStr = '';
                var isNativeLog = false;
                if (typeof event.data === 'string') {
                    dStr = event.data;
                    if (dStr.indexOf('abcd_native_log') > -1) {
                        try {
                            var parsed = JSON.parse(dStr);
                            if (parsed.type === 'abcd_native_log') {
                                isNativeLog = true;
                                window._abcdTwaDiag.nativeLogs = parsed.logs || [];
                                window._abcdTwaDiag.nativeSha256 = parsed.signing_sha256 || null;
                            }
                        } catch(e) {}
                    }
                } else if (event.data && typeof event.data === 'object') {
                    if (event.data.type === 'abcd_native_log') {
                        isNativeLog = true;
                        window._abcdTwaDiag.nativeLogs = event.data.logs || [];
                        window._abcdTwaDiag.nativeSha256 = event.data.signing_sha256 || null;
                    }
                    dStr = JSON.stringify(event.data);
                }
                var pLen = (event.ports && event.ports.length) ? event.ports.length : 0;
                window._abcdTwaDiag.lastPortsLength = pLen;
                window._abcdTwaDiag.msgs.push({
                    t: new Date().toLocaleTimeString(),
                    origin: event.origin || '',
                    data: dStr.slice(0, 60),
                    ports: pLen,
                    isNativeLog: isNativeLog
                });
                if (window._abcdTwaDiag.msgs.length > 20) window._abcdTwaDiag.msgs.shift();
            } catch(e) {}

            // FIX 3: accept new port each time and replace the old one
            if (event.ports && event.ports.length > 0) {
                window._abcdTwaPort = event.ports[0];
                window._abcdTwaDiag.portSet = true;
                if (window._abcdDlog) window._abcdDlog('New MessagePort received & assigned (ports=' + event.ports.length + ')');
                if (window._abcdTwaPort && typeof window._abcdTwaPort.start === 'function') {
                    try { window._abcdTwaPort.start(); } catch(e) {}
                }
                try {
                    window._abcdTwaPort.onmessage = function(portEvent) {
                        try {
                            if (portEvent.data) {
                                var pData = portEvent.data;
                                if (typeof pData === 'string' && pData.indexOf('abcd_native_log') > -1) {
                                    var pParsed = JSON.parse(pData);
                                    window._abcdTwaDiag.nativeLogs = pParsed.logs || [];
                                    window._abcdTwaDiag.nativeSha256 = pParsed.signing_sha256 || null;
                                }
                                if (window._abcdDlog) window._abcdDlog('Port onmsg: ' + String(pData).slice(0, 40));
                            }
                        } catch(e) {}
                    };
                } catch(e) {}
            }
        });
    }

    if (window.ABCDNav && window.ABCDNav.__initialized) {
        return;
    }

    const ABCDNav = {
        __initialized: true,
        version: '3.0.0',

        // Configuration populated by server/template
        config: {
            isBasePage: false,
            cleanPath: '/',
            parentUrl: '',
            contextAware: false,
            homeBaseUrl: '/',
            smartBackRouterUrl: '/smart-back/'
        },

        // Runtime state
        state: {
            isNavigating: false,
            trapArmed: false,
            exitModalVisible: false,
            openedByBackButton: false
        },

        // Registries for in-page consumers
        hooks: {
            inPageHandlers: [],
            dirtyGuards: [],
            modalCheckers: []
        },

        /**
         * Initialize the controller for the current page
         */
        init: function(options) {
            const self = this;
            options = options || {};

            // 1. Path detection & Base page normalization
            const rawPath = window.location.pathname.toLowerCase();
            const clean = rawPath.replace(/\/$/, '') || '/';
            self.config.cleanPath = clean;

            const isHardcodedBase = (
                clean === '' ||
                clean === '/' ||
                clean === '/home' ||
                clean === '/guest-home' ||
                clean === '/dashboard' ||
                clean === '/alumni/dashboard' ||
                clean === '/teacher'
            );

            self.config.isBasePage = (options.isBasePage !== undefined) ? Boolean(options.isBasePage) : isHardcodedBase;
            self.config.parentUrl = options.parentUrl || '';
            self.config.contextAware = Boolean(options.contextAware);
            self.config.homeBaseUrl = options.homeBaseUrl || self.config.homeBaseUrl;
            if (options.smartBackRouterUrl) {
                self.config.smartBackRouterUrl = options.smartBackRouterUrl;
            }

            // 2. Set origin tracking if on special hub pages (e.g. Hall of Fame)
            if (clean === '/hall-of-fame') {
                try {
                    sessionStorage.setItem('abcd_nav_origin_context', '/hall-of-fame/');
                } catch(e) {}
            }

            // 3. Arm single controlled history trap so hardware/browser Back executes executeBackPipeline
            self.armTrap();

            // 4. Attach single global popstate listener (once)
            if (!self._popstateAttached) {
                self._popstateAttached = true;
                window.addEventListener('popstate', function(event) {
                    self.onPopState(event);
                });
            }

            // 5. Handle bfcache restores (anti-stale / anti-loop)
            window.addEventListener('pageshow', function(e) {
                self.state.isNavigating = false;
                self.armTrap();
            });

            // 6. Bind modal controls if present
            self.bindExitModalEvents();

            // 7. Detect and persist Android app environment state
            self.detectAndroidApp();
        },

        /**
         * Ensures exactly ONE normalized trap entry in browser history per document.
         * Intercepts browser Back / Android hardware Back so executeBackPipeline() handles it.
         */
        armTrap: function() {
            if (this.state.isNavigating) return;
            try {
                const currentState = window.history.state;
                if (!currentState || (!currentState.abcd_base_trap && !currentState.abcd_sub_trap && !currentState.abcd_exit_trap && !currentState.abcd_nav_trap)) {
                    window.history.pushState({
                        abcd_nav_trap: true,
                        isBase: this.config.isBasePage,
                        path: this.config.cleanPath
                    }, document.title, window.location.href);
                }
                this.state.trapArmed = true;
            } catch(e) {
                // Silently ignore browser quota errors
            }
        },

        /**
         * Register an in-page back handler (e.g. Guidy chat closing or custom panes)
         * Handler should return true if back was consumed in-page, false otherwise.
         */
        registerInPageHandler: function(fn) {
            if (typeof fn === 'function' && !this.hooks.inPageHandlers.includes(fn)) {
                this.hooks.inPageHandlers.push(fn);
            }
        },

        /**
         * Register a dirty form guard (e.g. FormDraftManager)
         * Guard should return true if navigation is allowed, false to cancel navigation.
         */
        registerDirtyGuard: function(fn) {
            if (typeof fn === 'function' && !this.hooks.dirtyGuards.includes(fn)) {
                this.hooks.dirtyGuards.push(fn);
            }
        },

        /**
         * Global popstate event handler
         */
        onPopState: async function(event) {
            const self = this;

            // In-page hash changes within the same pathname are ignored
            const currentClean = window.location.pathname.toLowerCase().replace(/\/$/, '') || '/';
            if (window.location.hash && currentClean === self.config.cleanPath) {
                return;
            }

            if (self.state.isNavigating) {
                return;
            }

            self.state.trapArmed = false;
            await self.executeBackPipeline('popstate');
        },

        /**
         * Explicit programmatic or UI button Back trigger
         */
        handleBack: async function(e, source) {
            if (e && e.preventDefault) e.preventDefault();
            if (e && e.stopPropagation) e.stopPropagation();

            if (this.state.isNavigating) return;
            await this.executeBackPipeline(source || 'ui-button');
        },

        /**
         * The Unified Back Decision Pipeline
         */
        executeBackPipeline: async function(triggerSource) {
            const self = this;

            // -------------------------------------------------------------
            // STEP 1: Check Open In-Page Overlay Modals
            // -------------------------------------------------------------
            const activeModalOverlay = document.querySelector(
                '.todo-modal-overlay.active, .picker-overlay.active, #seatLayoutModal.active, #imageCropperOverlay.active'
            );
            if (activeModalOverlay && activeModalOverlay.id !== 'abcdExitOverlay') {
                if (typeof window.closeCurrentModal === 'function') {
                    window.closeCurrentModal();
                } else if (typeof window.closeModalOverlay === 'function') {
                    window.closeModalOverlay(activeModalOverlay);
                } else {
                    activeModalOverlay.classList.remove('active');
                    if (activeModalOverlay.style.display !== 'none') {
                        activeModalOverlay.style.display = 'none';
                    }
                }
                self.armTrap();
                return;
            }

            // -------------------------------------------------------------
            // STEP 2: Check Dirty Form Guards (e.g. Admission / Achievement draft)
            // -------------------------------------------------------------
            if (self.hooks.dirtyGuards.length > 0) {
                for (const guard of self.hooks.dirtyGuards) {
                    try {
                        const allowed = await guard();
                        if (!allowed) {
                            self.armTrap();
                            return;
                        }
                    } catch(err) {
                        console.warn('ABCDNav dirty guard error:', err);
                    }
                }
            } else if (typeof window.customBackConfirm === 'function') {
                try {
                    const allowed = await window.customBackConfirm();
                    if (!allowed) {
                        self.armTrap();
                        return;
                    }
                } catch(err) {
                    console.warn('customBackConfirm error:', err);
                }
            }

            // -------------------------------------------------------------
            // STEP 3: Check In-Page Stateful Component Hooks (e.g. Guidy)
            // -------------------------------------------------------------
            if (self.hooks.inPageHandlers.length > 0) {
                for (const handler of self.hooks.inPageHandlers) {
                    try {
                        const handled = await handler();
                        if (handled) {
                            self.armTrap();
                            return;
                        }
                    } catch(err) {
                        console.warn('ABCDNav in-page handler error:', err);
                    }
                }
            } else if (typeof window.handleCustomSmartBack === 'function') {
                try {
                    const handled = await window.handleCustomSmartBack();
                    if (handled) {
                        self.armTrap();
                        return;
                    }
                } catch(err) {
                    console.warn('handleCustomSmartBack error:', err);
                }
            }

            // -------------------------------------------------------------
            // STEP 4: Home Base Pages -> Show Exit Confirmation Modal
            // -------------------------------------------------------------
            if (self.config.isBasePage) {
                self.state.openedByBackButton = (triggerSource === 'popstate');
                self.showExitModal();
                return;
            }

            // -------------------------------------------------------------
            // STEP 5: Sub-Page -> Navigate to Logical Parent
            // -------------------------------------------------------------
            // Both hardware Back (popstate) and UI Back converge here.
            // We ALWAYS navigate to the intentional logical parent, never
            // rely on browser history stack for application navigation.
            const target = self.resolveTargetUrl();
            if (target) {
                self.state.isNavigating = true;
                window.location.replace(target);
            }
        },

        /**
         * Resolves safe fallback destination URL for deep-links or un-historied entries
         */
        resolveTargetUrl: function() {
            const self = this;
            let target = self.config.parentUrl;

            // Route map translation if named Django route was passed
            const routeMap = {
                'users:courses': '/courses/',
                'users:teacher_courses': '/teacher/courses/',
                'users:student_dashboard': '/dashboard/',
                'users:teacher_dashboard': '/teacher/',
                'users:alumni_dashboard': '/alumni/dashboard/',
                'users:home_page': '/',
                'users:guest_page': '/guest-home/',
                'users:student_complaints': '/complaints/',
                'users:hall_of_fame': '/hall-of-fame/'
            };
            if (routeMap[target]) {
                target = routeMap[target];
            }

            // Context-Aware Origin Check (e.g. Hall of Fame -> Achievement Detail)
            if (self.config.contextAware && !target) {
                let origin = '';
                try {
                    origin = sessionStorage.getItem('abcd_nav_origin_context') || '';
                } catch(e) {}

                if (origin === '/hall-of-fame/' || (document.referrer && document.referrer.includes('/hall-of-fame'))) {
                    target = '/hall-of-fame/';
                    try {
                        sessionStorage.removeItem('abcd_nav_origin_context');
                    } catch(e) {}
                }
            }

            // Path Hierarchy Fallback for Courses & Teacher Courses
            if (!target) {
                const cp = self.config.cleanPath;
                if (cp.startsWith('/courses/') && cp !== '/courses') {
                    target = '/courses/';
                } else if (cp.startsWith('/teacher/courses/') && cp !== '/teacher/courses') {
                    target = '/teacher/courses/';
                }
            }

            // Default fallback: Role-based Home Base or Smart Back Router
            if (!target) {
                target = self.config.homeBaseUrl || self.config.smartBackRouterUrl || '/dashboard/';
            }

            return target;
        },

        // =====================================================================
        // EXIT MODAL MANAGEMENT & PLATFORM-AWARE APP TERMINATION
        // =====================================================================

        getModalElements: function() {
            return {
                overlay: document.getElementById('abcdExitOverlay'),
                modal: document.getElementById('abcdExitModal'),
                cancelBtn: document.getElementById('abcdExitCancelBtn'),
                confirmBtn: document.getElementById('abcdExitConfirmBtn'),
                closeBtn: document.getElementById('abcdExitCloseBtn')
            };
        },

        INTENT_FALLBACK_URL: 'intent://close#Intent;scheme=abcdexit;package=in.abcdcampus.app;end',

        bindExitModalEvents: function() {
            const self = this;
            const els = self.getModalElements();
            if (!els.modal) return;

            if (els.cancelBtn && !els.cancelBtn._abcdBound) {
                els.cancelBtn._abcdBound = true;
                els.cancelBtn.addEventListener('click', function() { self.onCancelExit(); });
            }
            if (els.closeBtn && !els.closeBtn._abcdBound) {
                els.closeBtn._abcdBound = true;
                els.closeBtn.addEventListener('click', function() { self.onCancelExit(); });
            }
            if (els.overlay && !els.overlay._abcdBound) {
                els.overlay._abcdBound = true;
                els.overlay.addEventListener('click', function() { self.onCancelExit(); });
            }
            if (els.confirmBtn && !els.confirmBtn._abcdBound) {
                els.confirmBtn._abcdBound = true;

                // Ensure href is '#' by default
                els.confirmBtn.setAttribute('href', '#');

                // FIX 6: Set the intent href ONLY when fallback is primed (no port after 3s)
                setTimeout(function() {
                    const isApp = self.detectAndroidApp();
                    const intentFallbackAllowed = (typeof window.ABCD_EXIT_INTENT_FALLBACK === 'undefined' || window.ABCD_EXIT_INTENT_FALLBACK !== false);
                    if (isApp && !window._abcdTwaPort && intentFallbackAllowed && els.confirmBtn) {
                        els.confirmBtn.setAttribute('href', self.INTENT_FALLBACK_URL);
                        if (window._abcdDlog) window._abcdDlog('Intent fallback primed (no port after 3s)');
                    }
                }, 3000);

                els.confirmBtn.addEventListener('click', function(e) {
                    const isApp = self.detectAndroidApp();
                    const intentFallbackAllowed = (typeof window.ABCD_EXIT_INTENT_FALLBACK === 'undefined' || window.ABCD_EXIT_INTENT_FALLBACK !== false);
                    const currentHref = els.confirmBtn.getAttribute('href');

                    if (!isApp) {
                        // Normal browser path: execute standard web close & Google fallback
                        e.preventDefault();
                        self.doActualExit();
                        return;
                    }

                    // Android App path:
                    // If a port exists: preventDefault() and send port.postMessage('exit')
                    if (window._abcdTwaPort) {
                        e.preventDefault();
                        try {
                            window._abcdTwaPort.postMessage('exit');
                            if (window._abcdDlog) window._abcdDlog('EXIT: port.postMessage("exit") sent');
                            if (window._abcdTwaDiag && window._abcdTwaDiag.exitAttempts) {
                                window._abcdTwaDiag.exitAttempts.push(new Date().toLocaleTimeString() + ' - port.postMessage("exit") sent OK');
                            }
                        } catch(err) {
                            if (window._abcdDlog) window._abcdDlog('EXIT port err: ' + err.message);
                        }
                        self.doActualExit();
                        return;
                    }

                    // Fallback is primed (no port after 3s, href set to intent URL)
                    if (currentHref === self.INTENT_FALLBACK_URL && intentFallbackAllowed) {
                        if (window._abcdDlog) window._abcdDlog('fallback intent link used');
                        if (window._abcdTwaDiag && window._abcdTwaDiag.exitAttempts) {
                            window._abcdTwaDiag.exitAttempts.push(new Date().toLocaleTimeString() + ' - fallback intent link used');
                        }
                        // Natural user tap activates the intent link (no preventDefault, no scripted navigation)
                        return;
                    }

                    // Fallback not yet primed (tapped before 3s or href still '#'):
                    // FIX 3: Tolerate late port - show nothing destructive, log it, and retry for ~2 seconds
                    e.preventDefault();
                    if (window._abcdDlog) window._abcdDlog('EXIT tapped: port not ready, waiting up to 2s...');
                    if (window._abcdTwaDiag && window._abcdTwaDiag.exitAttempts) {
                        window._abcdTwaDiag.exitAttempts.push(new Date().toLocaleTimeString() + ' - port not ready, waiting up to 2s...');
                    }

                    var retryCount = 0;
                    var maxRetries = 20; // 20 * 100ms = 2000ms
                    var retryInterval = setInterval(function() {
                        retryCount++;
                        if (window._abcdTwaPort) {
                            clearInterval(retryInterval);
                            if (window._abcdDlog) window._abcdDlog('EXIT retry: port arrived late, sending postMessage');
                            if (window._abcdTwaDiag && window._abcdTwaDiag.exitAttempts) {
                                window._abcdTwaDiag.exitAttempts.push(new Date().toLocaleTimeString() + ' - port arrived late, sent exit OK');
                            }
                            self.doActualExit();
                            return;
                        }
                        if (retryCount >= maxRetries) {
                            clearInterval(retryInterval);
                            if (window._abcdDlog) window._abcdDlog('EXIT retry timeout: no port arrived');
                            if (intentFallbackAllowed && els.confirmBtn) {
                                els.confirmBtn.setAttribute('href', self.INTENT_FALLBACK_URL);
                            }
                            if (window._abcdTwaDiag && window._abcdTwaDiag.exitAttempts) {
                                window._abcdTwaDiag.exitAttempts.push(new Date().toLocaleTimeString() + ' - retry timeout (no port). Intent fallback primed for next tap.');
                            }
                        }
                    }, 100);
                });
            }

            // Bind "Got It" button in the fallback view
            var gotItBtn = document.getElementById('abcdExitFallbackGotItBtn');
            if (gotItBtn && !gotItBtn._abcdBound) {
                gotItBtn._abcdBound = true;
                gotItBtn.addEventListener('click', function() { self.onCancelExit(); });
            }

            document.addEventListener('keydown', function(e) {
                if (e.key === 'Escape' && self.state.exitModalVisible) {
                    self.onCancelExit();
                }
            });
        },

        showExitModal: function() {
            const els = this.getModalElements();
            if (!els.overlay || !els.modal) return;

            if (this.state.exitModalVisible) {
                els.modal.classList.remove('abcd-exit-modal-shake');
                void els.modal.offsetWidth;
                els.modal.classList.add('abcd-exit-modal-shake');
                return;
            }

            this.state.exitModalVisible = true;

            var highestZ = 3000100;
            if (typeof window.getHighestZIndex === 'function') {
                highestZ = Math.max(highestZ, window.getHighestZIndex([els.overlay, els.modal]));
            }
            els.overlay.style.setProperty('z-index', highestZ.toString(), 'important');
            els.modal.style.setProperty('z-index', (highestZ + 1).toString(), 'important');

            els.overlay.style.display = 'block';
            els.modal.style.display = 'block';
            void els.modal.offsetWidth;

            els.overlay.style.opacity = '1';
            els.overlay.style.pointerEvents = 'auto';
            els.modal.style.opacity = '1';
            els.modal.style.transform = 'translate(-50%, -50%) scale(1)';

            if (typeof window.syncModalScrollLock === 'function') {
                window.syncModalScrollLock();
            }

            if (els.cancelBtn) els.cancelBtn.focus();
        },

        hideExitModal: function() {
            const els = this.getModalElements();
            if (!els.overlay || !els.modal) return;

            this.state.exitModalVisible = false;
            els.overlay.style.opacity = '0';
            els.overlay.style.pointerEvents = 'none';
            els.modal.style.opacity = '0';
            els.modal.style.transform = 'translate(-50%, -50%) scale(0.92)';

            setTimeout(() => {
                if (!this.state.exitModalVisible) {
                    els.overlay.style.display = 'none';
                    els.modal.style.display = 'none';
                    if (typeof window.syncModalScrollLock === 'function') {
                        window.syncModalScrollLock();
                    }
                }
            }, 220);
        },

        onCancelExit: function() {
            this.resetExitModalView();
            this.hideExitModal();
            this.state.openedByBackButton = false;
            this.state.isNavigating = false;
            // Re-arm trap so future Back presses trigger modal again cleanly
            this.armTrap();
        },

        /**
         * Detect if running inside the Android TWA / Play App container.
         * Persists detection into sessionStorage so subsequent page navigations within
         * the app (e.g. Dashboard -> To-Do -> Form -> Dashboard) remain recognized as Android App.
         */
        detectAndroidApp: function() {
            let fromSession = false;
            try {
                fromSession = (sessionStorage.getItem('abcd_is_android_app') === '1');
            } catch(e) {}

            const isApp = Boolean(
                fromSession ||
                (document.referrer && document.referrer.startsWith('android-app://')) ||
                window.matchMedia('(display-mode: standalone)').matches ||
                window.matchMedia('(display-mode: fullscreen)').matches ||
                window.navigator.standalone === true ||
                window.location.search.includes('pwa_app=1') ||
                (window.AndroidApp && typeof window.AndroidApp.closeApp === 'function') ||
                (window.Android && (typeof window.Android.exitApp === 'function' || typeof window.Android.finish === 'function'))
            );

            if (isApp) {
                try {
                    sessionStorage.setItem('abcd_is_android_app', '1');
                } catch(e) {}
            }
            return isApp;
        },

        GOOGLE_SEARCH_FALLBACK_URL: 'https://www.google.com/search?q=' + encodeURIComponent('ABCD Smart Campus Coaching And Library Ganj Basoda'),

        /**
         * Platform-Aware Exit Execution
         *
         * ANDROID / PLAY APP CONTRACT:
         * Home Base -> Back -> Exit popup -> EXIT
         * Completely close the ABCD Campus Android app via native intent/custom scheme.
         * MUST NOT: navigate backward, use browser history, return to previous page,
         * open another webpage, show about:blank, show browser close-tab message.
         *
         * NORMAL WEBSITE / BROWSER CONTRACT:
         * Home Base -> Back -> Exit popup -> EXIT
         * Attempt to close the browser tab/window via window.close().
         * If the browser blocks window.close(), open Google search page for predefined query:
         * "ABCD Smart Campus Coaching And Library Ganj Basoda"
         * MUST NOT: use browser history as fallback, use history.back() or history.go(),
         * or navigate to a previous application page.
         */
        doActualExit: function() {
            const self = this;
            self.state.isNavigating = true;
            self.hideExitModal();

            const isAndroidApp = self.detectAndroidApp();

            // =========================================================================
            // ENVIRONMENT 1: ANDROID / PLAY APP
            // =========================================================================
            if (isAndroidApp) {
                // A. Check for injected WebView JS bridges
                if (window.AndroidApp && typeof window.AndroidApp.closeApp === 'function') {
                    try { window.AndroidApp.closeApp(); return; } catch(e) {}
                }
                if (window.Android && typeof window.Android.exitApp === 'function') {
                    try { window.Android.exitApp(); return; } catch(e) {}
                }
                if (window.Android && typeof window.Android.finish === 'function') {
                    try { window.Android.finish(); return; } catch(e) {}
                }

                // B. Primary: Custom Tabs / TWA postMessage Exit channel.
                // Communicates directly with LauncherActivity via CustomTabsCallback.onPostMessage.
                // Triggers native LauncherActivity.terminateApp(context) with zero Chrome dialogs
                // and zero external navigation prompts.
                function dispatchTwaExit() {
                    var sent = false;
                    if (window._abcdDlog) window._abcdDlog('EXIT: port=' + !!window._abcdTwaPort);
                    if (window._abcdTwaPort) {
                        try {
                            window._abcdTwaPort.postMessage('exit');
                            sent = true;
                            if (window._abcdDlog) window._abcdDlog('EXIT: port.postMessage OK');
                        } catch(e) {
                            if (window._abcdDlog) window._abcdDlog('EXIT err: ' + e.message);
                        }
                    }
                    try {
                        window.postMessage('exit', '*');
                        window.postMessage({ type: 'ABCD_EXIT', action: 'exit' }, '*');
                    } catch(e) {}
                    try {
                        if (window.parent && window.parent !== window) {
                            window.parent.postMessage('exit', '*');
                        }
                    } catch(e) {}
                    return sent;
                }

                dispatchTwaExit();

                var attempts = 0;
                var interval = setInterval(function() {
                    attempts++;
                    var done = dispatchTwaExit();
                    if (done || attempts >= 10) {
                        clearInterval(interval);
                    }
                }, 50);

                // CRITICAL CONTRACT: Under NO circumstances pop history stack backward!
                return;
            }

            // =========================================================================
            // ENVIRONMENT 2: NORMAL WEBSITE / BROWSER
            // =========================================================================
            try {
                window.close();
            } catch(e) {}

            // When browser blocks window.close() (standard for user-navigated tabs),
            // replace location with the predefined Google search fallback.
            // Using window.location.replace prevents adding a trap or allowing history-back loops.
            setTimeout(function() {
                if (!document.hidden) {
                    self.state.isNavigating = false;
                    window.location.replace(self.GOOGLE_SEARCH_FALLBACK_URL);
                }
            }, 100);
        },

        /**
         * Browser Fallback Handler: explicitly navigates to the predefined Google search fallback URL.
         */
        showExitFallback: function() {
            var self = this;
            self.hideExitModal();
            window.location.replace(self.GOOGLE_SEARCH_FALLBACK_URL);
        },

        /**
         * Reset the exit modal back to its default confirm view (for next use).
         */
        resetExitModalView: function() {
            var confirmView = document.getElementById('abcdExitConfirmView');
            var fallbackView = document.getElementById('abcdExitFallbackView');
            if (confirmView) confirmView.style.display = 'block';
            if (fallbackView) fallbackView.style.display = 'none';
        }
    };

    // Expose to window
    window.ABCDNav = ABCDNav;

    // Backward-compatible global helper for UI back buttons
    window.goBackOrHomeBase = function(e) {
        ABCDNav.handleBack(e, 'ui-button');
    };

    // =====================================================================
    // POSTMESSAGE DEBUG OVERLAY — activate: ?abcd_debug=1 or tap logo 5x in 3s
    // =====================================================================
    (function() {
        window._abcdDebugLog = window._abcdDebugLog || [];
        window._abcdDlog = function(msg) {
            window._abcdDebugLog.push(new Date().toLocaleTimeString() + ' ' + msg);
            if (window._abcdDebugLog.length > 50) window._abcdDebugLog.shift();
        };

        // Hidden trigger: tap page title or logo 5 times within 3 seconds
        var tapCount = 0;
        var lastTapTime = 0;
        document.addEventListener('click', function(e) {
            var target = e.target;
            if (!target) return;
            var isLogo = !!target.closest('header, nav, .logo, .logoImage, .site-logo, .brand, .brand-logo, h1, #abcdExitTitle, [data-logo], img[alt*="logo" i]');
            if (isLogo) {
                var now = Date.now();
                if (now - lastTapTime < 3000) {
                    tapCount++;
                } else {
                    tapCount = 1;
                }
                lastTapTime = now;
                if (tapCount >= 5) {
                    tapCount = 0;
                    try { sessionStorage.setItem('abcd_debug', '1'); } catch(e) {}
                    initOverlay();
                }
            }
        }, true);

        window.copyAbcdDebugLog = function() {
            var lines = [];
            lines.push('=== ABCD TWA / EXIT DIAGNOSTIC REPORT ===');
            lines.push('Timestamp: ' + new Date().toISOString());
            var cv = 0;
            try { var m = navigator.userAgent.match(/Chrome\/(\d+)/); if (m) cv = parseInt(m[1]); } catch(e) {}
            var dm = 'browser';
            try {
                if (window.matchMedia('(display-mode: standalone)').matches) dm = 'standalone';
                else if (window.matchMedia('(display-mode: fullscreen)').matches) dm = 'fullscreen';
            } catch(e) {}
            lines.push('Chrome: ' + (cv || '?'));
            lines.push('Display: ' + dm);
            lines.push('isApp: ' + (window.ABCDNav ? window.ABCDNav.detectAndroidApp() : '?'));
            lines.push('Port: ' + (window._abcdTwaPort ? 'SET' : 'NOT SET'));
            var diag = window._abcdTwaDiag || { msgs: [], portSet: false, lastPortsLength: 0, nativeLogs: [], exitAttempts: [] };
            lines.push('Messages received: ' + diag.msgs.length + ' (last ports.length: ' + diag.lastPortsLength + ')');
            lines.push('Fallback Intent Flag: ' + (typeof window.ABCD_EXIT_INTENT_FALLBACK !== 'undefined' ? window.ABCD_EXIT_INTENT_FALLBACK : true));
            lines.push('\n--- EXIT ATTEMPTS ---');
            if (diag.exitAttempts && diag.exitAttempts.length) {
                diag.exitAttempts.forEach(function(a) { lines.push(a); });
            } else {
                lines.push('(no exit attempts recorded)');
            }
            lines.push('\n--- WEB LOGS ---');
            (window._abcdDebugLog || []).forEach(function(l) { lines.push(l); });
            lines.push('\n--- NATIVE STAGE LOGS ---');
            if (diag.nativeLogs && diag.nativeLogs.length) {
                diag.nativeLogs.forEach(function(n) { lines.push(n); });
                if (diag.nativeSha256) lines.push('Cert SHA256: ' + diag.nativeSha256);
            } else {
                lines.push('native log unavailable - channel not established');
            }
            var text = lines.join('\n');
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(function() {
                    alert('ABCD Diagnostic Log copied to clipboard!');
                }).catch(function() {
                    prompt('Copy log below:', text);
                });
            } else {
                prompt('Copy log below:', text);
            }
        };

        function render() {
            var on = false;
            try {
                if (window.location.search.indexOf('abcd_debug=1') > -1) {
                    sessionStorage.setItem('abcd_debug', '1');
                    on = true;
                } else if (window.location.search.indexOf('abcd_debug=0') > -1) {
                    sessionStorage.removeItem('abcd_debug');
                    var old = document.getElementById('abcdDbg');
                    if (old) old.remove();
                    return;
                } else {
                    on = sessionStorage.getItem('abcd_debug') === '1';
                }
            } catch(e) {}

            if (!on) return;

            var el = document.getElementById('abcdDbg');
            if (!el) {
                el = document.createElement('div');
                el.id = 'abcdDbg';
                el.style.cssText = 'position:fixed;bottom:0;left:0;right:0;background:rgba(5,5,10,0.96);color:#0f0;' +
                    'font:11px/1.35 SFMono-Regular,Consolas,Menlo,monospace;padding:10px 12px;z-index:99999999;max-height:48vh;overflow-y:auto;' +
                    'border-top:2px solid #38bdf8;box-shadow:0 -4px 20px rgba(0,0,0,0.8);';
                (document.body || document.documentElement).appendChild(el);
            }

            var cv = 0;
            try { var m = navigator.userAgent.match(/Chrome\/(\d+)/); if (m) cv = parseInt(m[1]); } catch(e) {}
            var dm = 'browser';
            try {
                if (window.matchMedia('(display-mode: standalone)').matches) dm = 'standalone';
                else if (window.matchMedia('(display-mode: fullscreen)').matches) dm = 'fullscreen';
            } catch(e) {}
            var diag = window._abcdTwaDiag || { msgs: [], portSet: false, lastPortsLength: 0, nativeLogs: [], exitAttempts: [] };
            var isApp = window.ABCDNav ? window.ABCDNav.detectAndroidApp() : false;

            var h = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;border-bottom:1px solid #334155;padding-bottom:4px;">' +
                '<b style="color:#38bdf8;font-size:12px;">ABCD TWA PostMessage Debug</b>' +
                '<div>' +
                '<button type="button" onclick="window.copyAbcdDebugLog()" style="background:#2563eb;color:#fff;border:none;padding:2px 8px;border-radius:4px;cursor:pointer;font-size:11px;margin-right:8px;font-weight:600;">Copy Log</button>' +
                '<span onclick="sessionStorage.removeItem(\'abcd_debug\');document.getElementById(\'abcdDbg\').remove()" style="cursor:pointer;color:#f87171;font-weight:bold;">[close]</span>' +
                '</div></div>';

            h += '<div>' +
                'Chrome: <b style="color:#f1f5f9;">' + (cv || '?') + '</b> ' + (cv >= 115 ? '<span style="color:#4ade80;">\u2705</span>' : '<span style="color:#ef4444;">\u274C (need \u2265115)</span>') +
                ' | display: <b style="color:#f1f5f9;">' + dm + '</b>' +
                ' | isApp: <b style="color:' + (isApp ? '#4ade80' : '#f59e0b') + ';">' + isApp + '</b><br>' +
                'port: <b style="color:' + (window._abcdTwaPort ? '#4ade80' : '#ef4444') + '">' + (window._abcdTwaPort ? 'SET \u2705' : 'NOT SET \u274C') + '</b>' +
                ' (last ports.len: ' + diag.lastPortsLength + ')' +
                ' | msgs rcvd: <b>' + diag.msgs.length + '</b><br>' +
                'fallback flag: <b style="color:#94a3b8;">' + (typeof window.ABCD_EXIT_INTENT_FALLBACK !== 'undefined' ? window.ABCD_EXIT_INTENT_FALLBACK : true) + '</b>' +
                '</div>';

            // Exit attempts section
            h += '<div style="margin-top:6px;color:#fbbf24;"><b>Exit attempts:</b> ';
            if (diag.exitAttempts && diag.exitAttempts.length) {
                h += '<br>' + diag.exitAttempts.map(function(a) { return '<span style="color:#e2e8f0;">\u2022 ' + a + '</span>'; }).join('<br>');
            } else {
                h += '<span style="color:#94a3b8;">none yet</span>';
            }
            h += '</div>';

            // Native log section
            h += '<div style="margin-top:6px;border-top:1px dashed #475569;padding-top:4px;">' +
                '<b style="color:#c084fc;">Native Stage Log:</b><br>';
            if (diag.nativeLogs && diag.nativeLogs.length) {
                h += diag.nativeLogs.map(function(nl) { return '<span style="color:#e9d5ff;">' + nl + '</span>'; }).join('<br>');
                if (diag.nativeSha256) {
                    h += '<br><span style="color:#38bdf8;">Cert SHA256: ' + diag.nativeSha256 + '</span>';
                }
            } else {
                h += '<span style="color:#f87171;">native log unavailable - channel not established</span>';
            }
            h += '</div>';

            // Recent web events / logs
            if (window._abcdDebugLog && window._abcdDebugLog.length) {
                h += '<div style="margin-top:6px;border-top:1px dashed #475569;padding-top:4px;color:#94a3b8;">' +
                    '<b style="color:#94a3b8;">Web Log:</b><br>' +
                    window._abcdDebugLog.slice(-8).join('<br>') +
                    '</div>';
            }

            el.innerHTML = h;
        }

        function initOverlay() {
            render();
            if (!window._abcdOverlayInterval) {
                window._abcdOverlayInterval = setInterval(render, 1500);
            }
        }
        window._abcdInitDebugOverlay = initOverlay;

        var shouldInit = false;
        try {
            shouldInit = (window.location.search.indexOf('abcd_debug=1') > -1) || (sessionStorage.getItem('abcd_debug') === '1');
        } catch(e) {}
        if (shouldInit) {
            if (document.body) initOverlay();
            else document.addEventListener('DOMContentLoaded', initOverlay);
        }
    })();

})(window, document);
