/**
 * Global Button Loading Helper
 * Dynamically toggles button spinning animation & disabled state during async operations
 */
window.setButtonLoading = function(button, isLoading, loadingText) {
    if (!button) return;
    if (isLoading) {
        if (!button.dataset.originalHtml) {
            button.dataset.originalHtml = button.innerHTML;
        }
        button.disabled = true;
        button.style.pointerEvents = 'none';
        button.style.opacity = '0.85';
        const text = loadingText || 'Processing...';
        button.innerHTML = `<i class='bx bx-loader-alt bx-spin' style='margin-right:6px;font-size:1.1em;vertical-align:middle;display:inline-block;'></i><span>${text}</span>`;
    } else {
        if (button.dataset.originalHtml) {
            button.innerHTML = button.dataset.originalHtml;
            delete button.dataset.originalHtml;
        }
        button.disabled = false;
        button.style.pointerEvents = '';
        button.style.opacity = '';
    }
};

window.hasModalCard = function(el) {
    if (!el || !el.children || el.children.length === 0) return false;
    return !!el.querySelector(
        '.choice-modal-card, .todo-modal, .modal-container, .abcd-modal-container, ' +
        '.seat-modal-container, .seat-interest-modal, .seat-interest-box, .student-banner-card, ' +
        '.welcome-modal-card, .reg-success-card, .fp-card, .status-modal-card, .custom-popup, ' +
        '.modal-card, .popup-modal, .admission-modal, .admission-modal-styled, .chg-pwd-modal, ' +
        '.rating-modal, .share-modal-content, .fees-modal-content, .picker-card, .conf-content, ' +
        '.broadcast-modal-container, .modal-content, .popup-hdr, .modal-header, .popup-body, .modal-body, ' +
        '[class*="-card"], [class*="-container"], [class*="-box"]'
    );
};

window.isPureBackdrop = function(el) {
    if (!el) return false;
    // If it contains an inner modal card/container, it's a modal wrapper (Pattern A), NOT a pure backdrop!
    if (window.hasModalCard(el)) return false;

    const elId = (el.id || '').toLowerCase();
    const elClasses = (el.className || '').toLowerCase();

    // Check if ID or class explicitly marks it as an overlay or backdrop
    if (elId.includes('overlay') || elId.includes('backdrop') || elId.includes('scrim') || elId.includes('dimmer') ||
        elClasses.includes('overlay') || elClasses.includes('backdrop') || elClasses.includes('scrim') || elClasses.includes('dimmer')) {
        return true;
    }

    // Hardcoded known overlay IDs/classes
    if (elId === 'admissionmodaloverlay' || elId === 'teacherpremiumoverlay' || elId === 'custompopupoverlay' || 
        elId === 'seatmodaloverlay' || elId === 'statusmodaloverlay' || elId === 'logoutconfirmoverlay' ||
        elId === 'pwdoverlay' || elId === 'holdoverlay' || elId === 'cropoverlay' || elId === 'photoactionoverlay' ||
        elId === 'photomanageroverlay' || elId === 'deletemodaloverlay' || elId === 'modaloverlay' ||
        elId === 'deletescopemodaloverlay' || elId === 'dismissexpiredmodaloverlay') {
        return true;
    }

    // Empty modal element with 0 children
    if (el.children.length === 0 && (elClasses.includes('modal') || elClasses.includes('popup') || elClasses.includes('overlay'))) {
        return true;
    }

    return false;
};

window.getModalPair = function(element) {
    if (!element) return { dialog: null, overlay: null };

    let dialog = null;
    let overlay = null;

    if (window.isPureBackdrop(element)) {
        overlay = element;
        // 1. Check next siblings
        let sibling = element.nextElementSibling;
        while (sibling) {
            if (!window.isPureBackdrop(sibling) && (
                sibling.matches('[class*="modal"], [class*="popup"], [class*="-card"], [id*="Modal"], [id*="modal"], [id*="Popup"], [id*="popup"]') || 
                window.hasModalCard(sibling)
            )) {
                dialog = sibling;
                break;
            }
            sibling = sibling.nextElementSibling;
        }
        // 2. Check previous siblings
        if (!dialog) {
            sibling = element.previousElementSibling;
            while (sibling) {
                if (!window.isPureBackdrop(sibling) && (
                    sibling.matches('[class*="modal"], [class*="popup"], [class*="-card"], [id*="Modal"], [id*="modal"], [id*="Popup"], [id*="popup"]') || 
                    window.hasModalCard(sibling)
                )) {
                    dialog = sibling;
                    break;
                }
                sibling = sibling.previousElementSibling;
            }
        }
        // 3. Check by ID matching
        if (!dialog && element.id) {
            const rawId = element.id;
            const candidates = [
                rawId.replace(/Overlay$/i, ''),
                rawId.replace(/ModalOverlay$/i, 'Modal'),
                rawId.replace(/Overlay$/i, 'Modal'),
                rawId + 'Modal',
                rawId.replace(/Overlay$/i, 'Card'),
                rawId.replace(/Overlay$/i, 'ConfirmModal'),
                rawId.replace(/ModalOverlay$/i, 'ConfirmModal'),
                rawId.replace(/Overlay$/i, 'ScopeModal')
            ];
            for (let i = 0; i < candidates.length; i++) {
                const found = document.getElementById(candidates[i]);
                if (found && found !== element && !window.isPureBackdrop(found)) {
                    dialog = found;
                    break;
                }
            }
        }
    } else {
        dialog = element;
        // Check if element is nested inside an overlay (Pattern A)
        if (element.parentElement && window.isPureBackdrop(element.parentElement)) {
            overlay = element.parentElement;
        } else {
            // Sibling overlay (Pattern B)
            // 1. Check previous siblings
            let sibling = element.previousElementSibling;
            while (sibling) {
                if (window.isPureBackdrop(sibling)) {
                    overlay = sibling;
                    break;
                }
                sibling = sibling.previousElementSibling;
            }
            // 2. Check next siblings
            if (!overlay) {
                sibling = element.nextElementSibling;
                while (sibling) {
                    if (window.isPureBackdrop(sibling)) {
                        overlay = sibling;
                        break;
                    }
                    sibling = sibling.nextElementSibling;
                }
            }
            // 3. Check by ID matching
            if (!overlay && element.id) {
                const rawId = element.id;
                const candidates = [
                    rawId + 'Overlay',
                    rawId.replace(/Modal$/i, 'Overlay'),
                    rawId.replace(/Modal$/i, 'ModalOverlay'),
                    rawId.replace(/Card$/i, 'Overlay'),
                    rawId.replace(/ConfirmModal$/i, 'ModalOverlay'),
                    rawId.replace(/ConfirmModal$/i, 'Overlay'),
                    rawId.replace(/ScopeModal$/i, 'ScopeModalOverlay')
                ];
                for (let i = 0; i < candidates.length; i++) {
                    const found = document.getElementById(candidates[i]);
                    if (found && found !== element && window.isPureBackdrop(found)) {
                        overlay = found;
                        break;
                    }
                }
            }
        }
    }

    return { dialog, overlay };
};

var CustomPopup = window.CustomPopup || (function () {
    'use strict';

    // Auto-inject stylesheet if not already present on page
    (function ensurePopupStyles() {
        if (typeof document !== 'undefined' && document.head) {
            if (!document.querySelector('link[href*="custom-popup.css"]')) {
                const link = document.createElement('link');
                link.rel = 'stylesheet';
                link.href = '/static/css/custom-popup.css';
                document.head.appendChild(link);
            }
        }
    })();

    let popupOverlay = null;
    let popupContainer = null;
    let resolveCallback = null;

    /**
     * Initialize the popup DOM structure (called once on first use)
     */
    function init() {
        if (popupOverlay) return;

        // Ensure stylesheet exists
        if (typeof document !== 'undefined' && document.head && !document.querySelector('link[href*="custom-popup.css"]')) {
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = '/static/css/custom-popup.css';
            document.head.appendChild(link);
        }

        // Create overlay
        popupOverlay = document.createElement('div');
        popupOverlay.className = 'custom-popup-overlay';
        popupOverlay.id = 'customPopupOverlay';
        popupOverlay.style.setProperty('display', 'none', 'important');
        popupOverlay.style.setProperty('backdrop-filter', 'none', 'important');
        popupOverlay.style.setProperty('-webkit-backdrop-filter', 'none', 'important');
        popupOverlay.style.setProperty('z-index', '-1', 'important');
        popupOverlay.style.setProperty('pointer-events', 'none', 'important');

        // Create popup container
        popupContainer = document.createElement('div');
        popupContainer.className = 'custom-popup';
        popupContainer.id = 'customPopup';

        popupContainer.innerHTML = `
      <div class="custom-popup-header">
        <span class="custom-popup-title" id="customPopupTitle"></span>
        <button class="custom-popup-close" id="customPopupClose">&times;</button>
      </div>
      <div class="custom-popup-body" id="customPopupBody"></div>
      <div class="custom-popup-actions" id="customPopupActions"></div>
    `;

        document.body.appendChild(popupOverlay);
        document.body.appendChild(popupContainer);

        // Close on overlay click
        popupOverlay.addEventListener('click', () => {
            hide(null);
        });

        // Close button handler
        document.getElementById('customPopupClose').addEventListener('click', () => {
            hide(null);
        });

        // ESC key handler
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && popupOverlay && popupOverlay.classList.contains('visible')) {
                hide(null);
            }
        });
    }

    /**
     * Dynamically calculates the highest z-index on screen to ensure newly opened popup B is ALWAYS on top of existing modal A
     */
    function getHighestZIndex(excludeElement = null) {
        let maxZ = 3000000;
        const selector = [
            '.fees-modal', '.modal', '.custom-modal', '.admission-modal', 
            '.teacher-modal', '.popup', '.custom-popup', '.abcd-modal-overlay',
            '.seat-interest-overlay', '.choice-modal-overlay', '.choice-modal-card',
            '.reg-success-overlay', '.reg-success-card', '.alert-overlay', '.welcome-modal-card',
            '.student-banner-overlay', '.student-banner-card', '.notif-panel', '.notif-overlay',
            '.todo-modal-overlay', '.todo-modal', '.picker-overlay', '.styled-modal-overlay',
            '.fp-overlay', '.fp-card', '#logoutConfirmModal', '#logoutConfirmOverlay',
            '[role="dialog"]', 'dialog',
            'div[id*="Modal"]', 'div[id*="Popup"]', 'div[class*="modal"]',
            'div[class*="popup"]'
        ].join(',');

        let excludeList = Array.isArray(excludeElement) 
            ? [...excludeElement] 
            : (excludeElement ? [excludeElement] : []);

        const additionalExcludes = [];
        excludeList.forEach(el => {
            if (el && typeof window.getModalPair === 'function') {
                const pair = window.getModalPair(el);
                if (pair.dialog && !excludeList.includes(pair.dialog)) additionalExcludes.push(pair.dialog);
                if (pair.overlay && !excludeList.includes(pair.overlay)) additionalExcludes.push(pair.overlay);
            }
        });
        excludeList = excludeList.concat(additionalExcludes);

        const elements = document.querySelectorAll(selector);
        elements.forEach(el => {
            if (el === popupOverlay || el === popupContainer) return;
            for (let i = 0; i < excludeList.length; i++) {
                const ex = excludeList[i];
                if (ex && (el === ex || ex.contains(el) || el.contains(ex))) return;
            }

            // Ignore pure backdrop overlays that are not active or visible
            if (typeof window.isPureBackdrop === 'function' && window.isPureBackdrop(el)) {
                const elClasses = (el.className || '').toLowerCase();
                if (!elClasses.includes('active') && !elClasses.includes('visible') && !elClasses.includes('show') && el.style.display === 'none') return;
            }

            const style = window.getComputedStyle(el);
            if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
                const z = parseInt(style.zIndex, 10);
                if (!isNaN(z) && z > maxZ) {
                    maxZ = z;
                }
            }
        });
        return maxZ;
    }
    window.getHighestZIndex = getHighestZIndex;

    /**
     * Show the popup
     * @param {Object} options - Popup configuration
     * @param {string} options.title - Popup title
     * @param {string} options.message - Popup message (supports HTML)
     * @param {Array} options.buttons - Array of button configs [{label, value, class}]
     * @param {string} options.type - 'alert', 'confirm', 'custom', 'warning', 'error', 'success'
     * @returns {Promise} - Resolves with button value when closed
     */
    function show(options = {}) {
        init();

        const {
            title = 'Notice',
            message = '',
            buttons = [{ label: 'OK', value: true, class: 'btn-primary' }],
            type = 'alert'
        } = options;

        // Set title
        const titleEl = document.getElementById('customPopupTitle');
        titleEl.textContent = title;

        // Set message
        const bodyEl = document.getElementById('customPopupBody');
        bodyEl.innerHTML = message;

        // Set type class for styling
        popupContainer.className = 'custom-popup';
        popupContainer.classList.add(`custom-popup-${type}`);

        // Create buttons
        const actionsEl = document.getElementById('customPopupActions');
        actionsEl.innerHTML = '';

        buttons.forEach((btn) => {
            const buttonEl = document.createElement('button');
            buttonEl.className = `custom-popup-btn ${btn.class || 'btn-secondary'}`;
            buttonEl.textContent = btn.label;
            buttonEl.dataset.value = btn.value;

            buttonEl.addEventListener('click', () => {
                hide(btn.value);
            });

            actionsEl.appendChild(buttonEl);
        });

        // Dynamic Z-Index Stacking: Ensure newly opened popup B is ALWAYS on top of existing modal A
        const highestZ = getHighestZIndex([popupOverlay, popupContainer]);
        popupOverlay.style.setProperty('z-index', (highestZ + 10).toString(), 'important');
        popupContainer.style.setProperty('z-index', (highestZ + 11).toString(), 'important');

        // Show
        popupOverlay.style.setProperty('display', 'block', 'important');
        popupOverlay.style.setProperty('backdrop-filter', 'blur(4px)', 'important');
        popupOverlay.style.setProperty('-webkit-backdrop-filter', 'blur(4px)', 'important');
        popupOverlay.style.setProperty('pointer-events', 'auto', 'important');
        popupOverlay.classList.add('visible');
        popupContainer.classList.add('visible');
        document.body.classList.add('modal-open');

        // Play appropriate sound effect
        if (window.playABCDSound) {
            if (type === 'success') {
                window.playABCDSound('done');
            } else if (type === 'error' || type === 'warning') {
                window.playABCDSound('error');
            }
        }

        // Return promise
        return new Promise((resolve) => {
            resolveCallback = resolve;
        });
    }


    /**
     * Hide the popup
     * @param {*} value - Value to resolve the promise with
     */
    function hide(value) {
        if (!popupOverlay) return;

        // 🚀 INSTANT VISUAL FEEDBACK
        popupOverlay.classList.remove('visible');
        popupContainer.classList.remove('visible');
        popupOverlay.style.setProperty('display', 'none', 'important');
        popupOverlay.style.setProperty('backdrop-filter', 'none', 'important');
        popupOverlay.style.setProperty('-webkit-backdrop-filter', 'none', 'important');
        popupOverlay.style.setProperty('z-index', '-1', 'important');
        popupOverlay.style.setProperty('pointer-events', 'none', 'important');
        
        if (typeof window.purgeClosedModalOverlays === 'function') {
            window.purgeClosedModalOverlays();
        }

        // If teacher-seat-manager is loaded, let it orchestrate the global state sync
        if (typeof window.syncGlobalModalState === 'function') {
            window.syncGlobalModalState();
        } else {
            // Fallback for other pages where teacher-seat-manager isn't present
            const otherModals = document.querySelectorAll('.admission-modal.active, .teacher-modal.active, .teacher-modal.open');
            if (otherModals.length === 0) {
                document.body.classList.remove('modal-open');
            }
        }

        if (resolveCallback) {
            resolveCallback(value);
            resolveCallback = null;
        }
    }

    /**
     * Show an alert-style popup (single OK button)
     * @param {string} message - Alert message
     * @param {string} title - Optional title
     * @returns {Promise}
     */
    function alert(message, title = 'Notice') {
        return show({
            title,
            message: `<p>${message}</p>`,
            type: 'alert',
            buttons: [
                { label: 'OK', value: true, class: 'btn-primary' }
            ]
        });
    }

    /**
     * Show a confirm-style popup (OK/Cancel buttons)
     * @param {string} message - Confirm message  
     * @param {string} title - Optional title
     * @returns {Promise<boolean>} - true if confirmed, false/null if cancelled
     */
    function confirm(message, title = 'Confirm') {
        return show({
            title,
            message: `<p>${message}</p>`,
            type: 'confirm',
            buttons: [
                { label: 'Cancel', value: false, class: 'btn-secondary' },
                { label: 'OK', value: true, class: 'btn-primary' }
            ]
        });
    }

    /**
     * Show a prompt-style popup (input field with OK/Cancel buttons)
     * @param {string} message - Prompt message
     * @param {string} title - Optional title
     * @param {string} defaultValue - Default input value
     * @returns {Promise<string|null>}
     */
    function prompt(message, title = 'Input Required', defaultValue = '') {
        const inputId = 'customPopupPromptInput';
        const htmlMessage = `
            <p>${message}</p>
            <div style="margin-top: 14px;">
                <input type="text" id="${inputId}" class="custom-popup-input" value="${defaultValue || ''}" autocomplete="off">
            </div>
        `;

        const promise = show({
            title,
            message: htmlMessage,
            type: 'confirm',
            buttons: [
                { label: 'Cancel', value: null, class: 'btn-secondary' },
                { label: 'OK', value: '__SUBMIT_INPUT__', class: 'btn-primary' }
            ]
        });

        setTimeout(() => {
            const inputEl = document.getElementById(inputId);
            if (inputEl) {
                inputEl.focus();
                if (defaultValue) {
                    inputEl.select();
                }
                inputEl.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') {
                        hide(inputEl.value);
                    }
                });
            }
        }, 50);

        return promise.then((res) => {
            if (res === '__SUBMIT_INPUT__') {
                const el = document.getElementById(inputId);
                return el ? el.value : '';
            }
            return res;
        });
    }

    /**
     * Show a conflict resolution popup for pending requests
     * @param {Object} options
     * @param {string} options.studentName - Name of student with pending request
     * @param {string} options.shift - Shift name (Morning/Evening/Full Day)
     * @param {string} options.date - Date string
     * @returns {Promise<string|null>} - 'delete', 'cancel', or null
     */
    function showConflictPopup({ studentName, shift, date }) {
        return show({
            title: 'Pending Request Conflict',
            message: `
        <div class="popup-conflict-message">
          <p><strong>${studentName}</strong> has already requested <strong>${shift}</strong> shift (${date}).</p>
          <p>To proceed with manual assignment, you must handle the pending request first.</p>
          <div class="popup-options">
            <p>• Click <strong>"Delete Request"</strong> to delete the pending request and continue assigning.</p>
            <p>• Click <strong>"Cancel"</strong> to go back.</p>
          </div>
        </div>
      `,
            type: 'warning',
            buttons: [
                { label: 'Cancel', value: 'cancel', class: 'btn-secondary' },
                { label: 'Delete Request & Continue', value: 'delete', class: 'btn-danger' }
            ]
        });
    }

    /**
     * Show an action result popup (success/error)
     * @param {string} message - Result message
     * @param {boolean} success - Whether action succeeded
     * @returns {Promise}
     */
    function showResult(message, success = true) {
        return show({
            title: success ? 'Success' : 'Error',
            message: `<p>${message}</p>`,
            type: success ? 'success' : 'error',
            buttons: [
                { label: 'OK', value: true, class: success ? 'btn-success' : 'btn-danger' }
            ]
        });
    }

    // Public API
    return {
        show,
        hide,
        alert,
        confirm,
        prompt,
        showConflictPopup,
        showResult
    };

})();

// Make globally available
window.CustomPopup = CustomPopup;

// Automatically bridge standard browser dialogs to CustomPopup for seamless compatibility
window.alert = function (message) {
    const title = arguments.length > 1 ? arguments[1] : 'Notice';
    return CustomPopup.alert(message, title);
};

window.confirm = function (message) {
    const title = arguments.length > 1 ? arguments[1] : 'Confirmation';
    return CustomPopup.confirm(message, title);
};

window.prompt = function (message, defaultVal) {
    return CustomPopup.prompt(message, 'Input Required', defaultVal);
};

window.showStyledAlert = function (title, message) {
    return CustomPopup.alert(message, title);
};

window.showStyledConfirm = function (title, message) {
    return CustomPopup.confirm(message, title);
};

window.showStyledPopup = function (opts) {
    if (!opts) return Promise.resolve(false);
    const type = opts.type || 'alert';
    const isConfirm = type === 'confirm' || opts.showCancel === true;
    const title = opts.title || (type === 'error' ? 'Error' : (type === 'warning' ? 'Warning' : (isConfirm ? 'Confirmation' : 'Notice')));
    const msg = opts.message || '';
    const okBtnClass = type === 'error' ? 'btn-danger' : (type === 'warning' ? 'btn-warning' : (type === 'success' ? 'btn-success' : 'btn-primary'));
    const confirmLabel = opts.confirmText || opts.okText || (isConfirm ? 'Confirm' : 'OK');
    const cancelLabel = opts.cancelText || 'Cancel';
    const confirmBtnClass = opts.confirmBtnClass || (opts.type === 'confirm' && (confirmLabel === 'Delete' || opts.isDestructive) ? 'btn-danger' : okBtnClass);

    const buttons = [];
    if (isConfirm) {
        buttons.push({ label: cancelLabel, value: false, class: 'btn-secondary' });
        buttons.push({ label: confirmLabel, value: true, class: confirmBtnClass });
    } else {
        buttons.push({ label: confirmLabel, value: true, class: okBtnClass });
    }
    
    return CustomPopup.show({
        title: title,
        message: msg,
        type: type,
        buttons: buttons
    }).then((val) => {
        if (val) {
            if (typeof opts.onConfirm === 'function') {
                opts.onConfirm(val);
            }
            if (typeof opts.onOk === 'function') {
                opts.onOk(val);
            }
        } else {
            if (typeof opts.onCancel === 'function') {
                opts.onCancel(val);
            }
        }
        return val;
    });
};

window.showABCDModal = function (opts) {
    if (!opts) return;
    return window.showStyledPopup(opts);
};

// Global Helper & Mutation Observer to ensure ANY newly opened Modal B is ALWAYS on top of Modal A
(function() {
    window.bringToFront = function(element) {
        if (!element) return;

        const pair = (typeof window.getModalPair === 'function') 
            ? window.getModalPair(element) 
            : { dialog: element, overlay: null };

        const targetDialog = pair.dialog || element;
        const targetOverlay = pair.overlay;

        // CRITICAL: On pages with teacher-seat-manager, openSmallModal manages admission-modal & teacher-modal z-indices
        const dialogClasses = ((targetDialog && targetDialog.className) || '').toLowerCase();
        if (typeof window.syncGlobalModalState === 'function' && (dialogClasses.includes('admission-modal') || dialogClasses.includes('teacher-modal'))) {
            return;
        }

        const excludeList = [element];
        if (targetDialog) excludeList.push(targetDialog);
        if (targetOverlay) excludeList.push(targetOverlay);

        const highestZ = (typeof window.getHighestZIndex === 'function') 
            ? window.getHighestZIndex(excludeList) 
            : 3000000;

        const baseZ = Math.max(highestZ + 10, 3000000);

        // 1. PAIRED OVERLAY is ALWAYS set to baseZ (rendered BEHIND the dialog!)
        if (targetOverlay) {
            targetOverlay.style.setProperty('z-index', baseZ.toString(), 'important');
            targetOverlay.dataset.stackedTime = Date.now().toString();
        }

        // 2. DIALOG is ALWAYS set to baseZ + 1 (rendered IN FRONT of the overlay!)
        if (targetDialog) {
            targetDialog.style.setProperty('z-index', (baseZ + 1).toString(), 'important');
            targetDialog.dataset.stackedTime = Date.now().toString();

            // 3. INNER CARD (if any) is elevated to baseZ + 2
            const innerCard = targetDialog.querySelector(
                '.choice-modal-card, .todo-modal, .modal-container, .abcd-modal-container, ' +
                '.seat-modal-container, .seat-interest-modal, .seat-interest-box, .student-banner-card, ' +
                '.welcome-modal-card, .reg-success-card, .fp-card, .status-modal-card, .custom-popup, ' +
                '.modal-card, .popup-modal, .admission-modal, .admission-modal-styled, .chg-pwd-modal, ' +
                '.rating-modal, .share-modal-content, .fees-modal-content, .picker-card, ' +
                '[class*="-card"], [class*="-container"], [class*="-box"]'
            );
            if (innerCard && innerCard !== targetDialog) {
                innerCard.style.setProperty('z-index', (baseZ + 2).toString(), 'important');
            }
        }
    };

    // Global Auto-Enhancer for all select elements in modals, forms, and popups
    window.enhanceSelectElements = function(container, forceRefresh = false) {
        const parent = container || document;
        let selects = [];
        if (parent.tagName === 'SELECT') {
            selects = [parent];
        } else if (parent.querySelectorAll) {
            selects = Array.from(parent.querySelectorAll('select:not([data-no-enhance]):not([multiple])'));
        }
        
        selects.forEach(select => {
            // Ignore if explicitly marked to skip enhancement or if within a custom manual dropdown component
            if (select.getAttribute('data-no-enhance') === 'true') return;
            if (select.closest('.custom-dropdown, .mob-custom-dropdown')) return;

            // Enforce select hiding
            select.dataset.enhanced = 'true';
            select.dataset.customized = 'true';
            select.style.setProperty('display', 'none', 'important');
            select.style.setProperty('visibility', 'hidden', 'important');
            select.style.setProperty('opacity', '0', 'important');
            select.style.setProperty('position', 'absolute', 'important');
            select.style.setProperty('pointer-events', 'none', 'important');

            // Find existing wrapper directly following this select
            let existingWrapper = null;
            if (select.nextElementSibling && select.nextElementSibling.classList.contains('abcd-select-wrapper')) {
                existingWrapper = select.nextElementSibling;
            }

            // Clean up any extra/duplicate wrappers
            let nextEl = existingWrapper ? existingWrapper.nextElementSibling : select.nextElementSibling;
            while (nextEl && nextEl.classList.contains('abcd-select-wrapper')) {
                const toRemove = nextEl;
                nextEl = nextEl.nextElementSibling;
                toRemove.remove();
            }

            if (existingWrapper && !forceRefresh) {
                // Keep the trigger text up to date with currently selected option
                const selectedOpt = select.options[select.selectedIndex] || select.options[0];
                const triggerSpan = existingWrapper.querySelector('.abcd-select-trigger span');
                if (triggerSpan) {
                    triggerSpan.textContent = selectedOpt ? selectedOpt.text : 'Select...';
                }
                return;
            }

            let wrapper = existingWrapper;
            let trigger = null;
            let dropdown = null;

            if (wrapper) {
                trigger = wrapper.querySelector('.abcd-select-trigger');
                dropdown = wrapper.querySelector('.abcd-select-dropdown');
                if (dropdown) dropdown.innerHTML = '';
            } else {
                wrapper = document.createElement('div');
                wrapper.className = 'abcd-select-wrapper';

                trigger = document.createElement('div');
                trigger.className = 'abcd-select-trigger';

                dropdown = document.createElement('div');
                dropdown.className = 'abcd-select-dropdown';

                trigger.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const isOpen = wrapper.classList.contains('open');
                    document.querySelectorAll('.abcd-select-wrapper').forEach(w => w.classList.remove('open'));
                    if (!isOpen) wrapper.classList.add('open');
                });

                wrapper.appendChild(trigger);
                wrapper.appendChild(dropdown);
                
                if (select.parentNode) {
                    select.parentNode.insertBefore(wrapper, select.nextSibling);
                }
            }

            const selectedOpt = select.options[select.selectedIndex] || select.options[0];
            const selectedText = selectedOpt ? selectedOpt.text : 'Select...';
            trigger.innerHTML = `<span>${typeof escapeHTML === 'function' ? escapeHTML(selectedText) : selectedText}</span><i class='bx bx-chevron-down'></i>`;

            Array.from(select.options).forEach(option => {
                const optDiv = document.createElement('div');
                optDiv.className = 'abcd-select-option';
                if (option.selected) optDiv.classList.add('selected');
                optDiv.textContent = option.text;
                optDiv.dataset.value = option.value;

                optDiv.addEventListener('click', (e) => {
                    e.stopPropagation();
                    select.value = option.value;
                    const triggerSpan = trigger.querySelector('span');
                    if (triggerSpan) triggerSpan.textContent = option.text;
                    dropdown.querySelectorAll('.abcd-select-option').forEach(o => o.classList.remove('selected'));
                    optDiv.classList.add('selected');
                    wrapper.classList.remove('open');
                    
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                });
                dropdown.appendChild(optDiv);
            });
        });
    };

    function initAutoStacking() {
        const handleVisibilityChange = (el) => {
            if (!el || !el.matches) return;
            const selector = '.modal, .fees-modal, .admission-modal, .teacher-modal, .abcd-modal-overlay, .seat-interest-overlay, .choice-modal-overlay, .choice-modal-card, .reg-success-overlay, .reg-success-card, .alert-overlay, .welcome-modal-card, .student-banner-overlay, .student-banner-card, .notif-panel, .notif-overlay, .todo-modal-overlay, .todo-modal, .picker-overlay, .styled-modal-overlay, .fp-overlay, .fp-card, [id*="Modal"], [id*="modal"], [id*="Popup"], [id*="popup"], div[class*="modal"], div[class*="popup"], [role="dialog"], dialog';
            if (el.matches(selector)) {
                window.enhanceSelectElements(el);
                if (el.id === 'customPopupOverlay' || el.id === 'customPopup') return;
                
                // Never auto-stack closed elements
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;

                // CRITICAL: If element is a pure backdrop overlay, never bring it to front alone.
                // Instead, find its paired modal dialog and bring that to front (which sets overlay at Z, dialog at Z+1).
                if (typeof window.isPureBackdrop === 'function' && window.isPureBackdrop(el)) {
                    if (typeof window.getModalPair === 'function') {
                        const pair = window.getModalPair(el);
                        if (pair.dialog && pair.dialog !== el) {
                            const dStyle = window.getComputedStyle(pair.dialog);
                            if (dStyle.display !== 'none' && dStyle.visibility !== 'hidden' && dStyle.opacity !== '0') {
                                const now = Date.now();
                                const lastStacked = parseInt(pair.dialog.dataset.stackedTime, 10) || 0;
                                if (now - lastStacked > 150) {
                                    window.bringToFront(pair.dialog);
                                }
                            }
                        }
                    }
                    return;
                }

                // CRITICAL: On pages with teacher-seat-manager, openSmallModal manages admission-modal & teacher-modal z-indices
                const elClasses = (el.className || '').toLowerCase();
                if (typeof window.syncGlobalModalState === 'function' && (elClasses.includes('admission-modal') || elClasses.includes('teacher-modal'))) return;

                const now = Date.now();
                const lastStacked = parseInt(el.dataset.stackedTime, 10) || 0;
                if (now - lastStacked > 150) {
                    window.bringToFront(el);
                }
            }
        };

        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === 'attributes' && (mutation.attributeName === 'style' || mutation.attributeName === 'class')) {
                    handleVisibilityChange(mutation.target);
                } else if (mutation.type === 'childList') {
                    mutation.addedNodes.forEach((node) => {
                        if (node.nodeType === 1) {
                            handleVisibilityChange(node);
                        }
                    });
                }
            });
        });

        if (document.body) {
            observer.observe(document.body, {
                attributes: true,
                childList: true,
                subtree: true,
                attributeFilter: ['style', 'class']
            });
        }

        window.enhanceSelectElements(document);
    }

    document.addEventListener('click', (e) => {
        document.querySelectorAll('.abcd-select-wrapper').forEach(w => w.classList.remove('open'));
        
        // Delegate click for file upload zones if clicked child element
        const zone = e.target.closest('.tc-upload-zone, .upload-zone, .file-upload-zone');
        if (zone && !e.target.matches('input[type="file"]') && !e.target.closest('.tc-upload-preview, .upload-preview')) {
            const fileInput = zone.querySelector('input[type="file"]');
            if (fileInput) {
                fileInput.click();
            }
        }
    });


    window.purgeClosedModalOverlays = function() {
        try {
            const closedSelectors = [
                '.choice-modal-overlay.choice-modal-closed',
                '.choice-modal-overlay:not(.choice-modal-open)',
                '.student-banner-overlay:not(.banner-show)',
                '.custom-popup-overlay:not(.visible)',
                '.alert-overlay:not(.visible)',
                '.reg-success-overlay:not(.active)',
                '.ach-modal-overlay:not(.active)',
                '#logoutConfirmOverlay:not(.active)',
                '#logoutConfirmOverlay'
            ];
            
            closedSelectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => {
                    if (el.id === 'admissionChoiceModal' && el.classList.contains('choice-modal-closed')) {
                        try { el.remove(); } catch(e) {}
                        return;
                    }
                    if (el.id === 'regSuccessOverlay' && !el.classList.contains('active')) {
                        try { el.remove(); } catch(e) {}
                        return;
                    }
                    if (el.id === 'logoutConfirmOverlay') {
                        const isVisible = el.style.display === 'block' && el.style.opacity === '1';
                        if (!isVisible) {
                            el.style.setProperty('backdrop-filter', 'none', 'important');
                            el.style.setProperty('-webkit-backdrop-filter', 'none', 'important');
                            el.style.setProperty('display', 'none', 'important');
                            el.style.setProperty('pointer-events', 'none', 'important');
                            el.style.setProperty('z-index', '-1', 'important');
                        }
                        return;
                    }
                    el.style.setProperty('backdrop-filter', 'none', 'important');
                    el.style.setProperty('-webkit-backdrop-filter', 'none', 'important');
                    el.style.setProperty('display', 'none', 'important');
                    el.style.setProperty('pointer-events', 'none', 'important');
                    el.style.setProperty('z-index', '-1', 'important');
                });
            });

            document.querySelectorAll('.modal-overlay, .custom-modal-overlay, .fp-overlay, .todo-modal-overlay, .picker-overlay, .tc-modal-bg, #statusModalOverlay, .choice-modal-overlay, .student-banner-overlay, .custom-popup-overlay, .alert-overlay, .ach-modal-overlay').forEach(el => {
                if (el.classList.contains('sidebar-overlay') || el.id === 'sidebarOverlay' || el.closest('.sidebar-wrapper')) return;
                const cs = window.getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0' || (!el.classList.contains('active') && !el.classList.contains('visible') && !el.classList.contains('show') && !el.classList.contains('choice-modal-open') && !el.classList.contains('banner-show'))) {
                    el.style.setProperty('backdrop-filter', 'none', 'important');
                    el.style.setProperty('-webkit-backdrop-filter', 'none', 'important');
                    el.style.setProperty('pointer-events', 'none', 'important');
                    if (parseInt(cs.zIndex, 10) > 1000) {
                        el.style.setProperty('z-index', '-1', 'important');
                    }
                }
            });

            // Ensure sidebarOverlay is never infected with leftover inline styles
            const cleanSidebarOverlay = document.getElementById('sidebarOverlay');
            if (cleanSidebarOverlay) {
                cleanSidebarOverlay.style.removeProperty('display');
                cleanSidebarOverlay.style.removeProperty('pointer-events');
                cleanSidebarOverlay.style.removeProperty('z-index');
                cleanSidebarOverlay.style.removeProperty('backdrop-filter');
                cleanSidebarOverlay.style.removeProperty('-webkit-backdrop-filter');
            }

            // Ensure no-profile-popup elements are never infected with leftover inline styles
            document.querySelectorAll('.no-profile-popup').forEach(el => {
                el.style.removeProperty('display');
                el.style.removeProperty('pointer-events');
                el.style.removeProperty('z-index');
                el.style.removeProperty('backdrop-filter');
                el.style.removeProperty('-webkit-backdrop-filter');
            });

            // Unlock any stuck scroll / modal-open states
            const openModals = document.querySelectorAll('.choice-modal-open, .banner-show, .custom-popup-overlay.visible, .reg-success-overlay.active, .ach-modal-overlay.active, .alert-overlay.visible, .admission-modal.active, .teacher-modal.active');
            if (openModals.length === 0) {
                document.body.classList.remove('modal-open');
                document.body.classList.remove('abcd-scroll-locked');
                document.documentElement.classList.remove('abcd-scroll-locked');
            }

            if (typeof window.syncModalScrollLock === 'function') {
                window.syncModalScrollLock();
            }
        } catch(e) {}
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            initAutoStacking();
            window.purgeClosedModalOverlays();
        });
    } else {
        initAutoStacking();
        window.purgeClosedModalOverlays();
    }
    window.addEventListener('pageshow', () => {
        window.purgeClosedModalOverlays();
    });
})();


