/**
 * ABCD Request Handler - Production-Grade Request Manager
 * ========================================================
 * Handles:
 * - Button debouncing and double-click prevention
 * - Request queue for sequential processing
 * - Automatic retry with exponential backoff for database locks
 * - Loading states and visual feedback
 * - Race condition prevention
 * 
 * @author ABCD Development Team
 * @version 1.0.0
 */

(function () {
    'use strict';

    // =========================================================================
    // CONFIGURATION
    // =========================================================================
    const CONFIG = {
        // Debounce delay in milliseconds
        DEBOUNCE_DELAY: 300,

        // Minimum time to show loading state (prevents flashing)
        MIN_LOADING_TIME: 500,

        // Retry configuration for database lock errors
        MAX_RETRIES: 3,
        INITIAL_RETRY_DELAY: 500,
        RETRY_BACKOFF_MULTIPLIER: 2,

        // Request timeout in milliseconds
        REQUEST_TIMEOUT: 30000,

        // Queue processing delay between requests
        QUEUE_PROCESS_DELAY: 100
    };

    // =========================================================================
    // REQUEST STATE TRACKER
    // =========================================================================
    const RequestTracker = {
        // Track buttons currently processing
        processingButtons: new Set(),

        // Request queue for sequential processing
        requestQueue: [],
        isProcessingQueue: false,

        // Track forms that have been submitted
        submittedForms: new WeakSet(),

        /**
         * Check if a button is currently processing
         */
        isProcessing(buttonId) {
            return this.processingButtons.has(buttonId);
        },

        /**
         * Mark button as processing
         */
        startProcessing(buttonId) {
            this.processingButtons.add(buttonId);
        },

        /**
         * Mark button as finished processing
         */
        endProcessing(buttonId) {
            this.processingButtons.delete(buttonId);
        },

        /**
         * Check and mark form as submitted (returns false if already submitted)
         */
        trySubmitForm(form) {
            if (this.submittedForms.has(form)) {
                return false;
            }
            this.submittedForms.add(form);
            return true;
        },

        /**
         * Unmark form as submitted (for retry scenarios)
         */
        resetForm(form) {
            this.submittedForms.delete(form);
        }
    };

    // =========================================================================
    // BUTTON STATE MANAGER
    // =========================================================================
    const ButtonStateManager = {
        originalStates: new WeakMap(),

        /**
         * Set button to loading state
         */
        setLoading(button, loadingText = 'Processing...') {
            if (!button) return;

            // Store original state
            if (!this.originalStates.has(button)) {
                this.originalStates.set(button, {
                    innerHTML: button.innerHTML,
                    disabled: button.disabled,
                    className: button.className
                });
            }

            // Apply loading state
            button.disabled = true;
            button.classList.add('btn-loading');
            button.setAttribute('data-loading', 'true');

            // Store original text and show loading
            const originalText = button.textContent.trim();
            button.innerHTML = `
                <span class="btn-spinner"></span>
                <span class="btn-text">${loadingText}</span>
            `;
            button.setAttribute('data-original-text', originalText);
        },

        /**
         * Restore button to original state
         */
        restore(button) {
            if (!button) return;

            const original = this.originalStates.get(button);
            if (original) {
                button.innerHTML = original.innerHTML;
                button.disabled = original.disabled;
                button.className = original.className;
                this.originalStates.delete(button);
            }

            button.classList.remove('btn-loading');
            button.removeAttribute('data-loading');
        },

        /**
         * Set button to success state briefly
         */
        showSuccess(button, message = 'Done!') {
            if (!button) return;

            if (window.playABCDSound) {
                window.playABCDSound('done');
            }

            const originalText = button.getAttribute('data-original-text') || button.textContent;
            button.innerHTML = `✓ ${message}`;
            button.classList.add('btn-success-flash');

            setTimeout(() => {
                button.classList.remove('btn-success-flash');
                this.restore(button);
            }, 1500);
        },

        /**
         * Set button to error state briefly
         */
        showError(button, message = 'Error') {
            if (!button) return;

            if (window.playABCDSound) {
                window.playABCDSound('error');
            }

            button.innerHTML = `✗ ${message}`;
            button.classList.add('btn-error-flash');

            setTimeout(() => {
                button.classList.remove('btn-error-flash');
                this.restore(button);
            }, 2000);
        }
    };

    // =========================================================================
    // DEBOUNCE UTILITY
    // =========================================================================
    function debounce(func, wait, options = {}) {
        let timeoutId = null;
        let lastArgs = null;
        let lastThis = null;
        let result = null;

        const leading = options.leading || false;
        const trailing = options.trailing !== false;

        function invokeFunc() {
            const args = lastArgs;
            const thisArg = lastThis;
            lastArgs = lastThis = undefined;
            result = func.apply(thisArg, args);
            return result;
        }

        function shouldInvoke(time) {
            return timeoutId === null;
        }

        function trailingEdge() {
            timeoutId = null;
            if (trailing && lastArgs) {
                return invokeFunc();
            }
            lastArgs = lastThis = undefined;
            return result;
        }

        function debounced(...args) {
            lastArgs = args;
            lastThis = this;

            if (timeoutId === null && leading) {
                return invokeFunc();
            }

            if (timeoutId) {
                clearTimeout(timeoutId);
            }

            timeoutId = setTimeout(trailingEdge, wait);
            return result;
        }

        debounced.cancel = function () {
            if (timeoutId) {
                clearTimeout(timeoutId);
            }
            timeoutId = lastArgs = lastThis = undefined;
        };

        return debounced;
    }

    // =========================================================================
    // RETRY WITH EXPONENTIAL BACKOFF
    // =========================================================================
    async function retryWithBackoff(fn, options = {}) {
        const maxRetries = options.maxRetries || CONFIG.MAX_RETRIES;
        const initialDelay = options.initialDelay || CONFIG.INITIAL_RETRY_DELAY;
        const backoffMultiplier = options.backoffMultiplier || CONFIG.RETRY_BACKOFF_MULTIPLIER;
        const shouldRetry = options.shouldRetry || ((error) => isDatabaseLockError(error));

        let lastError;
        let delay = initialDelay;

        for (let attempt = 0; attempt <= maxRetries; attempt++) {
            try {
                return await fn();
            } catch (error) {
                lastError = error;

                if (attempt === maxRetries || !shouldRetry(error)) {
                    throw error;
                }

                console.warn(`Request failed (attempt ${attempt + 1}/${maxRetries + 1}), retrying in ${delay}ms...`, error.message);

                await sleep(delay);
                delay *= backoffMultiplier;
            }
        }

        throw lastError;
    }

    /**
     * Check if error is a database lock error
     */
    function isDatabaseLockError(error) {
        if (!error) return false;

        const message = (error.message || error.toString()).toLowerCase();
        return message.includes('database is locked') ||
            message.includes('locked') ||
            message.includes('busy') ||
            message.includes('timeout');
    }

    /**
     * Sleep utility
     */
    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // =========================================================================
    // FORM SUBMISSION HANDLER
    // =========================================================================

    /**
     * Safely submit a form with debouncing and retry logic
     */
    async function safeFormSubmit(form, options = {}) {
        if (!form) return;

        // Get the submit button
        const submitBtn = options.button || form.querySelector('button[type="submit"], .approve-btn, .btn-success');
        const buttonId = submitBtn?.id || `form-${Date.now()}`;

        // Check if already processing
        if (RequestTracker.isProcessing(buttonId)) {
            console.log('Request already in progress, ignoring duplicate click');
            return false;
        }

        // Check if form already submitted
        if (!RequestTracker.trySubmitForm(form)) {
            console.log('Form already submitted, ignoring duplicate submission');
            return false;
        }

        try {
            RequestTracker.startProcessing(buttonId);

            if (submitBtn) {
                ButtonStateManager.setLoading(submitBtn, options.loadingText || 'Processing...');
            }

            // Actually submit the form
            const startTime = Date.now();

            form.submit();

            // Ensure minimum loading time to prevent flash
            const elapsed = Date.now() - startTime;
            if (elapsed < CONFIG.MIN_LOADING_TIME) {
                await sleep(CONFIG.MIN_LOADING_TIME - elapsed);
            }

            return true;

        } catch (error) {
            console.error('Form submission error:', error);

            if (submitBtn) {
                ButtonStateManager.showError(submitBtn, 'Error');
            }

            // Reset form for retry
            RequestTracker.resetForm(form);

            throw error;

        } finally {
            RequestTracker.endProcessing(buttonId);
        }
    }

    // =========================================================================
    // AJAX REQUEST HANDLER
    // =========================================================================

    /**
     * Make a safe AJAX request with retry logic
     */
    async function safeRequest(url, options = {}) {
        const button = options.button;
        const buttonId = button?.id || `request-${Date.now()}`;

        // Check if already processing
        if (button && RequestTracker.isProcessing(buttonId)) {
            console.log('Request already in progress, ignoring duplicate');
            return null;
        }

        if (button) {
            RequestTracker.startProcessing(buttonId);
            ButtonStateManager.setLoading(button, options.loadingText || 'Processing...');
        }

        try {
            const response = await retryWithBackoff(async () => {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), CONFIG.REQUEST_TIMEOUT);

                try {
                    const fetchOptions = {
                        method: options.method || 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': options.csrfToken || window.CSRF_TOKEN || getCsrfToken(),
                            ...options.headers
                        },
                        body: options.body ? JSON.stringify(options.body) : undefined,
                        signal: controller.signal
                    };

                    const response = await fetch(url, fetchOptions);

                    if (!response.ok) {
                        const errorText = await response.text().catch(() => '');
                        const error = new Error(`Request failed: ${response.status} ${response.statusText}`);
                        error.response = response;
                        error.responseText = errorText;

                        // Check for database lock in response
                        if (errorText.toLowerCase().includes('database is locked')) {
                            error.isDatabaseLock = true;
                        }

                        throw error;
                    }

                    return response;
                } finally {
                    clearTimeout(timeoutId);
                }
            }, {
                shouldRetry: (error) => {
                    return isDatabaseLockError(error) || error.isDatabaseLock;
                }
            });

            const data = await response.json().catch(() => ({ success: true }));

            if (button) {
                ButtonStateManager.showSuccess(button, 'Done!');
            }

            return data;

        } catch (error) {
            console.error('Request failed:', error);

            if (button) {
                ButtonStateManager.showError(button, 'Error');
            }

            throw error;

        } finally {
            if (button) {
                RequestTracker.endProcessing(buttonId);
            }
        }
    }

    /**
     * Get CSRF token from cookie or meta tag
     */
    function getCsrfToken() {
        // Try cookie first
        const cookieMatch = document.cookie.match(/csrftoken=([^;]+)/);
        if (cookieMatch) return cookieMatch[1];

        // Try meta tag
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) return metaTag.content;

        // Try hidden input
        const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (input) return input.value;

        return '';
    }

    // =========================================================================
    // AUTO-INITIALIZE PROTECTION
    // =========================================================================
    function initializeProtection() {
        // Protect all forms with approve buttons
        document.querySelectorAll('.approve-form, form[data-protected="true"]').forEach(form => {
            protectForm(form);
        });

        // Protect all action buttons
        document.querySelectorAll('.btn-action, .approve-btn, [data-action-btn]').forEach(button => {
            protectButton(button);
        });

        // Observe for dynamically added forms/buttons
        observeDynamicElements();
    }

    /**
     * Protect a form from double submission
     */
    function protectForm(form) {
        if (form.hasAttribute('data-protection-initialized')) return;
        form.setAttribute('data-protection-initialized', 'true');

        form.addEventListener('submit', function (e) {
            // If form is already being submitted, prevent duplicate
            if (!RequestTracker.trySubmitForm(form)) {
                e.preventDefault();
                console.log('Prevented duplicate form submission');
                return false;
            }

            // Disable all submit buttons in the form
            form.querySelectorAll('button[type="submit"], .approve-btn').forEach(btn => {
                ButtonStateManager.setLoading(btn, 'Submitting...');
            });
        });
    }

    /**
     * Protect a button from rapid clicks
     */
    function protectButton(button) {
        if (button.hasAttribute('data-click-protected')) return;
        button.setAttribute('data-click-protected', 'true');

        const originalHandler = button.onclick;

        // Create debounced click handler
        const debouncedHandler = debounce(function (e) {
            const buttonId = button.id || `btn-${Date.now()}`;

            if (RequestTracker.isProcessing(buttonId)) {
                e.preventDefault();
                e.stopPropagation();
                console.log('Button click ignored - already processing');
                return false;
            }

            if (originalHandler) {
                return originalHandler.call(button, e);
            }
        }, CONFIG.DEBOUNCE_DELAY, { leading: true, trailing: false });

        button.onclick = null;
        button.addEventListener('click', debouncedHandler, true);
    }

    /**
     * Observe for dynamically added elements
     */
    function observeDynamicElements() {
        const observer = new MutationObserver(mutations => {
            mutations.forEach(mutation => {
                mutation.addedNodes.forEach(node => {
                    if (node.nodeType !== Node.ELEMENT_NODE) return;

                    // Check if the node itself matches
                    if (node.matches && node.matches('.approve-form, form[data-protected="true"]')) {
                        protectForm(node);
                    }
                    if (node.matches && node.matches('.btn-action, .approve-btn, [data-action-btn]')) {
                        protectButton(node);
                    }

                    // Check children
                    if (node.querySelectorAll) {
                        node.querySelectorAll('.approve-form, form[data-protected="true"]').forEach(protectForm);
                        node.querySelectorAll('.btn-action, .approve-btn, [data-action-btn]').forEach(protectButton);
                    }
                });
            });
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    // =========================================================================
    // CSS INJECTION
    // =========================================================================
    function injectStyles() {
        if (document.getElementById('request-handler-styles')) return;

        const styles = document.createElement('style');
        styles.id = 'request-handler-styles';
        styles.textContent = `
            /* Loading button spinner */
            .btn-loading {
                position: relative;
                pointer-events: none !important;
                cursor: wait !important;
                opacity: 0.8;
            }

            .btn-loading .btn-spinner {
                display: inline-block;
                width: 14px;
                height: 14px;
                border: 2px solid currentColor;
                border-right-color: transparent;
                border-radius: 50%;
                animation: btn-spin 0.6s linear infinite;
                margin-right: 6px;
                vertical-align: middle;
            }

            .btn-loading .btn-text {
                vertical-align: middle;
            }

            @keyframes btn-spin {
                to { transform: rotate(360deg); }
            }

            /* Success/Error flash states */
            .btn-success-flash {
                background: linear-gradient(135deg, #28a745 0%, #20c997 100%) !important;
                color: white !important;
                animation: successPulse 0.3s ease-out;
            }

            .btn-error-flash {
                background: linear-gradient(135deg, #dc3545 0%, #c82333 100%) !important;
                color: white !important;
                animation: errorShake 0.3s ease-out;
            }

            @keyframes successPulse {
                0% { transform: scale(1); }
                50% { transform: scale(1.05); }
                100% { transform: scale(1); }
            }

            @keyframes errorShake {
                0%, 100% { transform: translateX(0); }
                25% { transform: translateX(-4px); }
                75% { transform: translateX(4px); }
            }

            /* Disabled form submission indicator */
            form[data-submitting="true"] {
                pointer-events: none;
                opacity: 0.7;
            }
        `;
        document.head.appendChild(styles);
    }

    // =========================================================================
    // INITIALIZATION
    // =========================================================================
    function init() {
        injectStyles();

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initializeProtection);
        } else {
            initializeProtection();
        }
    }

    // =========================================================================
    // EXPORT TO WINDOW
    // =========================================================================
    window.ABCD_RequestHandler = {
        // Core utilities
        safeFormSubmit,
        safeRequest,
        retryWithBackoff,
        debounce,

        // State managers
        RequestTracker,
        ButtonStateManager,

        // Protection
        protectForm,
        protectButton,

        // Initialization
        init,

        // Configuration (allow runtime modification)
        CONFIG
    };

    // Auto-initialize
    init();

    console.log('✅ ABCD Request Handler initialized - Double-click protection active');

})();
