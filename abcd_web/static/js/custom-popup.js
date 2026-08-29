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

const CustomPopup = (function () {
    'use strict';

    let popupOverlay = null;
    let popupContainer = null;
    let resolveCallback = null;

    /**
     * Initialize the popup DOM structure (called once on first use)
     */
    function init() {
        if (popupOverlay) return;

        // Create overlay
        popupOverlay = document.createElement('div');
        popupOverlay.className = 'custom-popup-overlay';
        popupOverlay.id = 'customPopupOverlay';

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
     * Show the popup
     * @param {Object} options - Popup configuration
     * @param {string} options.title - Popup title
     * @param {string} options.message - Popup message (supports HTML)
     * @param {Array} options.buttons - Array of button configs [{label, value, class}]
     * @param {string} options.type - 'alert', 'confirm', 'custom', 'warning', 'error', 'success'
     * @returns {Promise} - Resolves with button value when closed
     */
    /**
     * Dynamically calculates the highest z-index on screen to ensure newly opened popup B is ALWAYS on top of existing modal A
     */
    function getHighestZIndex() {
        let maxZ = 10000;
        const selector = [
            '.fees-modal', '.modal', '.custom-modal', '.admission-modal', 
            '.teacher-modal', '.modal-overlay', '.popup', '.popup-overlay',
            'div[id*="Modal"]', 'div[id*="Popup"]', 'div[class*="modal"]',
            'div[class*="popup"]', 'div[class*="overlay"]'
        ].join(',');

        const elements = document.querySelectorAll(selector);
        elements.forEach(el => {
            if (el !== popupOverlay && el !== popupContainer) {
                const style = window.getComputedStyle(el);
                if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
                    const z = parseInt(style.zIndex, 10);
                    if (!isNaN(z) && z > maxZ) {
                        maxZ = z;
                    }
                }
            }
        });
        return maxZ;
    }

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
        const highestZ = getHighestZIndex();
        popupOverlay.style.zIndex = (highestZ + 10).toString();
        popupContainer.style.zIndex = (highestZ + 11).toString();

        // Show
        popupOverlay.classList.add('visible');
        popupContainer.classList.add('visible');
        document.body.classList.add('modal-open');

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
    return CustomPopup.alert(message);
};

window.confirm = function (message) {
    return CustomPopup.confirm(message);
};

window.prompt = function (message, defaultVal) {
    return CustomPopup.prompt(message, 'Input Required', defaultVal);
};

// Global Helper & Mutation Observer to ensure ANY newly opened Modal B is ALWAYS on top of Modal A
(function() {
    window.bringToFront = function(element) {
        if (!element) return;
        const elClasses = (element.className || '').toLowerCase();
        const elId = (element.id || '').toLowerCase();
        if (elClasses.includes('overlay') || elId.includes('overlay')) return;

        let maxZ = 10000;
        const selector = [
            '.fees-modal', '.modal', '.custom-modal', '.admission-modal', 
            '.teacher-modal', '.popup',
            'div[id*="Modal"]', 'div[id*="Popup"]', 'div[class*="modal"]',
            'div[class*="popup"]'
        ].join(',');

        const elements = document.querySelectorAll(selector);
        elements.forEach(el => {
            const currentClasses = (el.className || '').toLowerCase();
            const currentId = (el.id || '').toLowerCase();
            if (currentClasses.includes('overlay') || currentId.includes('overlay')) return;

            if (el !== element && !element.contains(el) && !el.contains(element)) {
                const style = window.getComputedStyle(el);
                if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
                    const z = parseInt(style.zIndex, 10);
                    if (!isNaN(z) && z > maxZ) {
                        maxZ = z;
                    }
                }
            }
        });

        element.style.zIndex = (maxZ + 10).toString();
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
            select.style.setProperty('position', 'absolute', 'important');
            select.style.setProperty('width', '0', 'important');
            select.style.setProperty('height', '0', 'important');
            select.style.setProperty('opacity', '0', 'important');
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
            if (el.matches && el.matches('.modal, .fees-modal, .admission-modal, .teacher-modal, [id*="Modal"], [id*="Popup"], div[class*="modal"], div[class*="popup"]')) {
                window.enhanceSelectElements(el);
                if (el.id === 'customPopupOverlay' || el.id === 'customPopup') return;
                
                // CRITICAL: Never auto-stack overlay elements - they must stay BELOW their modals
                const elClasses = (el.className || '').toLowerCase();
                const elId = (el.id || '').toLowerCase();
                if (elClasses.includes('overlay') || elId.includes('overlay')) return;

                // CRITICAL: On pages with teacher-seat-manager, openSmallModal manages admission-modal & teacher-modal z-indices. Do not override them!
                if (typeof window.syncGlobalModalState === 'function' && (elClasses.includes('admission-modal') || elClasses.includes('teacher-modal'))) return;

                const style = window.getComputedStyle(el);
                if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
                    const now = Date.now();
                    const lastStacked = parseInt(el.dataset.stackedTime, 10) || 0;
                    if (now - lastStacked > 300) {
                        window.bringToFront(el);
                        el.dataset.stackedTime = now.toString();
                    }
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


    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAutoStacking);
    } else {
        initAutoStacking();
    }
})();


