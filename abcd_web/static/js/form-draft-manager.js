/**
 * static/js/form-draft-manager.js
 * ABCD Smart Campus - Universal Form Draft & Unsaved Changes Protection
 *
 * Protects users from accidental back gestures or button clicks when filling forms.
 * Supports:
 * - Detecting user input (dirty state)
 * - Safe client-side draft saving to localStorage (strictly excluding file inputs/photos)
 * - Custom popup dialog (Save & Go Back / Discard & Go Back / Keep Editing)
 * - Restoring draft values into text fields, dropdowns, radios, checkboxes, and dynamic rows
 * - Restored draft banner with one-click "Clear Draft"
 * - Automatic draft cleanup upon form submission
 */

(function () {
    'use strict';

    // Inject styles for draft banner and animations
    (function injectStyles() {
        if (typeof document === 'undefined' || !document.head) return;
        if (document.getElementById('abcdDraftBannerStyle')) return;

        const st = document.createElement('style');
        st.id = 'abcdDraftBannerStyle';
        st.textContent = `
            @keyframes abcdDraftFadeIn {
                from { opacity: 0; transform: translateY(-8px); }
                to { opacity: 1; transform: translateY(0); }
            }
            .abcd-draft-banner {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
                background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%);
                border: 1.5px solid #86efac;
                color: #166534;
                padding: 12px 18px;
                border-radius: 14px;
                margin-bottom: 24px;
                font-size: 0.92rem;
                font-weight: 600;
                box-shadow: 0 4px 15px rgba(22, 101, 52, 0.08);
                animation: abcdDraftFadeIn 0.35s ease;
                box-sizing: border-box;
                width: 100%;
            }
            .abcd-draft-clear-btn {
                background: #fee2e2;
                border: 1px solid #f87171;
                color: #991b1b;
                padding: 6px 14px;
                border-radius: 8px;
                font-size: 0.82rem;
                font-weight: 700;
                cursor: pointer;
                transition: all 0.2s ease;
                white-space: nowrap;
            }
            .abcd-draft-clear-btn:hover {
                background: #fecaca;
                transform: translateY(-1px);
            }
        `;
        document.head.appendChild(st);
    })();

    class FormDraftManager {
        /**
         * @param {Object} options
         * @param {string|HTMLFormElement} options.form - Form element or selector
         * @param {string} options.storageKey - Unique localStorage key
         * @param {string[]} [options.excludeFields] - Field names/IDs to exclude
         * @param {Function} [options.customSerializer] - Custom serialize hook (form) => extraData
         * @param {Function} [options.customRestorer] - Custom restore hook (form, savedData) => void
         * @param {string} [options.formName] - Friendly name for popup title/message
         */
        constructor(options) {
            this.form = typeof options.form === 'string' ? document.querySelector(options.form) : options.form;
            if (!this.form) return;

            this.storageKey = options.storageKey || 'abcd_form_draft_' + window.location.pathname;
            this.excludeFields = options.excludeFields || [];
            this.customSerializer = options.customSerializer || null;
            this.customRestorer = options.customRestorer || null;
            this.formName = options.formName || 'Form';

            this.isDirty = false;
            this.isSubmitting = false;
            this.draftSaved = false;

            this.init();
        }

        init() {
            // 1. Restore any existing draft
            this.restoreDraft();

            // 2. Track changes to detect if user has entered data
            this.trackChanges();

            // 3. Register smart back confirmation hooks
            this.registerBackInterceptors();

            // 4. Clean up draft when form is submitted
            this.form.addEventListener('submit', () => {
                this.isSubmitting = true;
                this.clearDraft();
            });
        }

        /**
         * Determine if field should be ignored
         */
        isFieldIgnored(el) {
            if (!el || !el.name) return true;
            if (el.type === 'file' || el.type === 'password' || el.name === 'csrfmiddlewaretoken') return true;
            if (this.excludeFields.includes(el.name) || this.excludeFields.includes(el.id)) return true;
            return false;
        }

        /**
         * Monitor all inputs to determine if form is dirty
         */
        trackChanges() {
            const markDirty = (e) => {
                if (this.isSubmitting) return;
                const target = e ? e.target : null;
                if (target && this.isFieldIgnored(target)) return;
                this.isDirty = true;
            };

            this.form.addEventListener('input', markDirty);
            this.form.addEventListener('change', markDirty);
            this.form.addEventListener('paste', markDirty);
        }

        /**
         * Check if form currently has meaningful user-entered data
         */
        hasEnteredData() {
            if (this.isDirty) return true;

            const elements = this.form.elements;
            for (let i = 0; i < elements.length; i++) {
                const el = elements[i];
                if (this.isFieldIgnored(el)) continue;

                if (el.type === 'checkbox' || el.type === 'radio') {
                    if (el.checked && !el.defaultChecked) return true;
                } else if (el.tagName === 'SELECT') {
                    if (el.selectedIndex > 0 && el.value !== '') return true;
                } else if (el.value && el.value.trim() !== '') {
                    return true;
                }
            }

            return false;
        }

        /**
         * Save form data to localStorage (EXCLUDING files/photos)
         */
        saveDraft() {
            try {
                const data = {};
                const elements = this.form.elements;

                for (let i = 0; i < elements.length; i++) {
                    const el = elements[i];
                    if (this.isFieldIgnored(el)) continue;

                    const name = el.name;
                    if (!name) continue;

                    if (el.type === 'checkbox') {
                        data[name] = el.checked;
                    } else if (el.type === 'radio') {
                        if (el.checked) {
                            data[name] = el.value;
                        }
                    } else if (name.endsWith('[]')) {
                        // Array of inputs (e.g. dynamic achievement rows)
                        if (!data[name]) data[name] = [];
                        data[name].push(el.value);
                    } else {
                        data[name] = el.value;
                    }
                }

                // Run custom serializer if provided
                if (typeof this.customSerializer === 'function') {
                    const extra = this.customSerializer(this.form);
                    if (extra && typeof extra === 'object') {
                        Object.assign(data, extra);
                    }
                }

                data._timestamp = Date.now();
                localStorage.setItem(this.storageKey, JSON.stringify(data));
                this.draftSaved = true;
                return true;
            } catch (e) {
                console.warn('Failed to save form draft to localStorage:', e);
                return false;
            }
        }

        /**
         * Restore draft values into the form
         */
        restoreDraft() {
            try {
                const raw = localStorage.getItem(this.storageKey);
                if (!raw) return false;

                const data = JSON.parse(raw);
                if (!data || typeof data !== 'object') return false;

                let restoredCount = 0;

                // Restore custom hook first (e.g. dynamic rows, special pickers)
                if (typeof this.customRestorer === 'function') {
                    this.customRestorer(this.form, data);
                }

                // Restore standard form fields
                for (const key in data) {
                    if (key.startsWith('_')) continue;
                    const val = data[key];

                    if (Array.isArray(val)) {
                        const fields = this.form.querySelectorAll(`[name="${key}"]`);
                        fields.forEach((field, idx) => {
                            if (val[idx] !== undefined && !this.isFieldIgnored(field)) {
                                field.value = val[idx];
                                restoredCount++;
                            }
                        });
                    } else {
                        const field = this.form.elements[key];
                        if (!field) continue;

                        if (field instanceof RadioNodeList || (field.length && field[0] && field[0].type === 'radio')) {
                            const radios = field.length ? field : [field];
                            for (let r = 0; r < radios.length; r++) {
                                if (radios[r].value === String(val)) {
                                    radios[r].checked = true;
                                    radios[r].dispatchEvent(new Event('change', { bubbles: true }));
                                    restoredCount++;
                                    break;
                                }
                            }
                        } else if (field.type === 'checkbox') {
                            field.checked = Boolean(val);
                            field.dispatchEvent(new Event('change', { bubbles: true }));
                            restoredCount++;
                        } else if (!this.isFieldIgnored(field)) {
                            if (val !== undefined && val !== null && val !== '') {
                                field.value = val;
                                field.dispatchEvent(new Event('input', { bubbles: true }));
                                field.dispatchEvent(new Event('change', { bubbles: true }));
                                restoredCount++;
                            }
                        }
                    }
                }

                if (restoredCount > 0) {
                    this.isDirty = true;
                    this.renderDraftBanner(data._timestamp);
                    return true;
                }
            } catch (e) {
                console.warn('Failed to restore form draft:', e);
            }
            return false;
        }

        /**
         * Render a clean indicator banner showing draft was restored
         */
        renderDraftBanner(timestamp) {
            let banner = document.getElementById('abcdDraftRestoreBanner');
            if (!banner) {
                banner = document.createElement('div');
                banner.id = 'abcdDraftRestoreBanner';
                banner.className = 'abcd-draft-banner';

                const timeStr = timestamp ? new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
                const dateStr = timestamp ? new Date(timestamp).toLocaleDateString() : '';

                banner.innerHTML = `
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span style="font-size:1.25rem;">📝</span>
                        <span>Restored your previously saved draft${timeStr ? ` (${dateStr} at ${timeStr})` : ''}</span>
                    </div>
                    <button type="button" id="abcdClearDraftBtn" class="abcd-draft-clear-btn">Clear Draft</button>
                `;

                this.form.parentNode.insertBefore(banner, this.form);

                const clearBtn = document.getElementById('abcdClearDraftBtn');
                if (clearBtn) {
                    clearBtn.addEventListener('click', () => {
                        this.clearDraft();
                        this.form.reset();
                        this.isDirty = false;
                        if (banner && banner.parentNode) {
                            banner.parentNode.removeChild(banner);
                        }
                        if (window.playABCDSound) window.playABCDSound('button');
                    });
                }
            }
        }

        /**
         * Permanently clear saved draft
         */
        clearDraft() {
            try {
                localStorage.removeItem(this.storageKey);
                const banner = document.getElementById('abcdDraftRestoreBanner');
                if (banner && banner.parentNode) {
                    banner.parentNode.removeChild(banner);
                }
            } catch (e) {}
        }

        /**
         * Mark submitting to prevent confirmation dialogs during form send
         */
        markSubmitting() {
            this.isSubmitting = true;
            this.clearDraft();
        }

        /**
         * Hook back buttons and browser history popstate
         */
        registerBackInterceptors() {
            // Hook window.customBackConfirm for _smart_back_redirect.html
            window.customBackConfirm = async () => {
                if (this.isSubmitting) return true;
                if (!this.hasEnteredData()) return true;

                return await this.showConfirmationDialog();
            };

            // Hook any UI back buttons with class .back-btn
            const backBtns = document.querySelectorAll('.back-btn, a[href*="dashboard"], a[href*="home"]');
            backBtns.forEach((btn) => {
                // Only hook buttons whose action is to leave the page
                if (btn.getAttribute('href') && !btn.getAttribute('href').startsWith('#')) {
                    btn.addEventListener('click', async (e) => {
                        if (this.isSubmitting) return;
                        if (!this.hasEnteredData()) return;

                        e.preventDefault();
                        const allowed = await this.showConfirmationDialog();
                        if (allowed) {
                            window.allowPageUnload = true;
                            window.location.href = btn.href;
                        }
                    });
                }
            });

            // Silent draft backup on tab close or refresh - NO browser leave site dialogs
            window.addEventListener('beforeunload', () => {
                if (window.allowPageUnload || this.isSubmitting) return;
                // If user entered data and has not discarded, silently save draft
                if (this.hasEnteredData() && this.isDirty) {
                    this.saveDraft();
                }
            });
        }

        /**
         * Present custom styled confirmation popup
         * @returns {Promise<boolean>} Resolves true if navigation should proceed, false to cancel
         */
        async showConfirmationDialog() {
            const title = 'Save Form Progress?';
            const message = `
                <div style="text-align:left; font-size:0.95rem; line-height:1.6; color:#334155;">
                    <p style="margin-bottom:12px;">
                        You have unsaved details in your <strong>${this.formName}</strong>.
                    </p>
                    <p style="margin-bottom:8px; font-size:0.9rem; color:#64748b;">
                        Would you like to <strong>save your details as a draft</strong> so you can continue where you left off, or discard your changes?
                    </p>
                    <p style="font-size:0.8rem; color:#94a3b8; margin-top:10px;">
                        <em>Note: Profile photos are not saved in draft and can be selected upon final submission.</em>
                    </p>
                </div>
            `;

            // If CustomPopup is available, use styled popup
            if (window.CustomPopup && typeof window.CustomPopup.show === 'function') {
                const choice = await window.CustomPopup.show({
                    title: title,
                    message: message,
                    buttons: [
                        { label: 'Save & Go Back', value: 'save', class: 'btn-primary' },
                        { label: 'Discard & Go Back', value: 'discard', class: 'btn-danger' },
                        { label: 'Keep Editing', value: 'cancel', class: 'btn-secondary' }
                    ],
                    type: 'warning'
                });

                if (choice === 'save') {
                    this.saveDraft();
                    this.isSubmitting = true;
                    window.allowPageUnload = true;
                    return true;
                } else if (choice === 'discard') {
                    this.clearDraft();
                    this.isDirty = false;
                    this.isSubmitting = true;
                    window.allowPageUnload = true;
                    return true;
                } else {
                    // Cancel / Keep Editing: Repush trap so back button remains active
                    try {
                        window.history.pushState({ abcd_back_trap: true }, document.title, window.location.href);
                    } catch (e) {}
                    return false;
                }
            } else {
                // Fallback: silently preserve progress without browser modal
                this.saveDraft();
                this.isSubmitting = true;
                window.allowPageUnload = true;
                return true;
            }
        }
    }

    // Expose to window
    window.ABCDFormDraftManager = FormDraftManager;
})();
