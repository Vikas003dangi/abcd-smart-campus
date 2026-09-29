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
         * Platform-Aware Exit Execution
         *
         * Three environments:
         * 1. Android TWA / Standalone PWA — use native exit mechanisms
         * 2. Desktop browser — attempt window.close(), show in-modal fallback if blocked
         * 3. Mobile web (non-TWA) — same as desktop
         */
        doActualExit: function() {
            const self = this;
            self.state.isNavigating = true;

            // Detect TRUE TWA / Standalone (not just "any Android browser")
            const isTWA = Boolean(
                (document.referrer && document.referrer.startsWith('android-app://')) ||
                window.matchMedia('(display-mode: standalone)').matches ||
                window.matchMedia('(display-mode: fullscreen)').matches ||
                window.navigator.standalone === true ||
                window.location.search.includes('pwa_app=1')
            );

            // =========================================================================
            // ENVIRONMENT 1: ANDROID TWA / NATIVE APP WRAPPER
            // =========================================================================
            if (isTWA) {
                self.hideExitModal();

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

                // B. Primary: Intent URI targeting ExitActivity directly by component
                // This is more reliable than custom schemes inside Chrome Custom Tabs
                try {
                    window.location.href = "intent:#Intent;action=in.abcdcampus.app.EXIT;package=in.abcdcampus.app;component=in.abcdcampus.app/.ExitActivity;category=android.intent.category.DEFAULT;end";
                } catch(e) {}

                // C. Fallback: Custom scheme (registered only on ExitActivity)
                setTimeout(function() {
                    try {
                        window.location.href = "abcdexit://close";
                    } catch(e) {}
                }, 80);

                // D. Last resort: window.close() + history pop
                setTimeout(function() {
                    try { window.close(); } catch(e) {}
                    var steps = self.state.openedByBackButton ? -1 : -2;
                    try { window.history.go(steps); } catch(e) {}
                }, 200);
                return;
            }

            // =========================================================================
            // ENVIRONMENT 2: DESKTOP / MOBILE WEB (non-TWA)
            // =========================================================================
            // Do NOT hide the modal yet — we may need to show the fallback state.
            try {
                window.close();
            } catch(e) {}

            // If browser blocks closing (user-opened tab), transition to fallback view
            setTimeout(function() {
                if (!document.hidden) {
                    self.state.isNavigating = false;
                    self.showExitFallback();
                }
            }, 300);
        },

        /**
         * Show the "Close Tab" fallback instructions inside the existing Exit Modal.
         * Triggered when window.close() is blocked by the browser.
         */
        showExitFallback: function() {
            var self = this;
            var confirmView = document.getElementById('abcdExitConfirmView');
            var fallbackView = document.getElementById('abcdExitFallbackView');

            if (confirmView && fallbackView) {
                confirmView.style.display = 'none';
                fallbackView.style.display = 'block';

                // Detect platform for keyboard shortcut
                var isMac = /mac/i.test(navigator.platform || navigator.userAgent || '');
                var isMobile = /android|iphone|ipad|ipod|mobile/i.test(navigator.userAgent || '');
                var shortcutEl = document.getElementById('abcdExitShortcut');
                if (shortcutEl) {
                    if (isMobile) {
                        shortcutEl.innerHTML = 'Tap the <strong>tab switcher</strong> in your browser, then close this tab.';
                    } else if (isMac) {
                        shortcutEl.innerHTML = 'Press <kbd>\u2318</kbd> + <kbd>W</kbd> to close this tab.';
                    } else {
                        shortcutEl.innerHTML = 'Press <kbd>Ctrl</kbd> + <kbd>W</kbd> to close this tab.';
                    }
                }
            } else {
                // Fallback if modal elements are missing: re-arm and show toast-style message
                self.hideExitModal();
                self.armTrap();
            }
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

})(window, document);
