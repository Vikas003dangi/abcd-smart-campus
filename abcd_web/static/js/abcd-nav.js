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
        window._abcdTwaDiag = { msgs: [], portSet: false };
        window.addEventListener('message', function(event) {
            try {
                window._abcdTwaDiag.msgs.push({
                    t: Date.now(), origin: event.origin || '',
                    data: typeof event.data === 'string' ? event.data.slice(0, 60) : typeof event.data,
                    ports: event.ports ? event.ports.length : 0
                });
                if (window._abcdTwaDiag.msgs.length > 20) window._abcdTwaDiag.msgs.shift();
            } catch(e) {}
            if (event.ports && event.ports.length > 0) {
                window._abcdTwaPort = event.ports[0];
                window._abcdTwaDiag.portSet = true;
                if (window._abcdTwaPort && typeof window._abcdTwaPort.start === 'function') {
                    try { window._abcdTwaPort.start(); } catch(e) {}
                }
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
                els.confirmBtn.addEventListener('click', function() { self.doActualExit(); });
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
    // POSTMESSAGE DEBUG OVERLAY — activate: ?abcd_debug=1  deactivate: ?abcd_debug=0
    // =====================================================================
    (function() {
        var on = window.location.search.indexOf('abcd_debug=1') > -1;
        if (on) try { sessionStorage.setItem('abcd_debug', '1'); } catch(e) {}
        if (window.location.search.indexOf('abcd_debug=0') > -1) {
            try { sessionStorage.removeItem('abcd_debug'); } catch(e) {}
            return;
        }
        if (!on) try { on = sessionStorage.getItem('abcd_debug') === '1'; } catch(e) {}
        if (!on) return;

        window._abcdDebugLog = [];
        window._abcdDlog = function(msg) {
            window._abcdDebugLog.push(new Date().toLocaleTimeString() + ' ' + msg);
            if (window._abcdDebugLog.length > 40) window._abcdDebugLog.shift();
        };

        function render() {
            var el = document.getElementById('abcdDbg');
            if (!el) {
                el = document.createElement('div');
                el.id = 'abcdDbg';
                el.style.cssText = 'position:fixed;bottom:0;left:0;right:0;background:rgba(0,0,0,0.92);color:#0f0;' +
                    'font:11px/1.4 monospace;padding:8px 10px;z-index:99999999;max-height:40vh;overflow-y:auto;';
                (document.body || document.documentElement).appendChild(el);
            }
            var cv = 0;
            try { var m = navigator.userAgent.match(/Chrome\/(\d+)/); if (m) cv = parseInt(m[1]); } catch(e) {}
            var dm = 'browser';
            try {
                if (window.matchMedia('(display-mode: standalone)').matches) dm = 'standalone';
                else if (window.matchMedia('(display-mode: fullscreen)').matches) dm = 'fullscreen';
            } catch(e) {}
            var diag = window._abcdTwaDiag || { msgs: [], portSet: false };
            var h = '<b style="color:#ff0">ABCD PostMessage Debug</b> ' +
                '<span onclick="sessionStorage.removeItem(\'abcd_debug\');location.reload()" ' +
                'style="float:right;cursor:pointer;color:#f66">[close]</span><br>' +
                'Chrome: <b>' + (cv || '?') + '</b> ' + (cv >= 115 ? '\u2705' : '\u274C need \u2265115') +
                ' | display: ' + dm + '<br>' +
                'isApp: ' + (window.ABCDNav ? window.ABCDNav.detectAndroidApp() : '?') +
                ' | msgs rcvd: ' + diag.msgs.length +
                ' | port: <b style="color:' + (window._abcdTwaPort ? '#0f0' : '#f66') + '">' +
                (window._abcdTwaPort ? 'SET \u2705' : 'NOT SET \u274C') + '</b><br>';
            if (diag.msgs.length) {
                var last = diag.msgs[diag.msgs.length - 1];
                h += 'last msg: data=' + last.data + ' origin=' + last.origin + ' ports=' + last.ports + '<br>';
            }
            if (window._abcdDebugLog.length) {
                h += '<br>' + window._abcdDebugLog.join('<br>');
            }
            el.innerHTML = h;
        }
        if (document.body) render(); else document.addEventListener('DOMContentLoaded', render);
        setInterval(render, 1500);
    })();

})(window, document);
