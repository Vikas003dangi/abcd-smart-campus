/* showStyledPopup is defined globally in admission_form.html.
   Fallback in case this JS is used on a page without the inline definition: */
if (typeof window.showStyledPopup === 'undefined') {
    window.showStyledPopup = function({ title = 'Notice', message = '', type = 'info', onOk = null, okText = 'OK' } = {}) {
        const existing = document.getElementById('styledPopupOverlay');
        if (existing) existing.remove();
        const colors = {
            warning: { border: '#ffc107', icon: '⚠️', titleColor: '#856404' },
            error: { border: '#dc3545', icon: '❌', titleColor: '#721c24' },
            info: { border: '#17a2b8', icon: 'ℹ️', titleColor: '#0c5460' },
            success: { border: '#28a745', icon: '✅', titleColor: '#155724' }
        };
        const c = colors[type] || colors.info;

        if (window.playABCDSound) {
            if (type === 'success') {
                window.playABCDSound('done');
            } else if (type === 'error' || type === 'warning') {
                window.playABCDSound('error');
            }
        }

        const overlay = document.createElement('div');
        overlay.id = 'styledPopupOverlay';
        overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:100000;display:flex;align-items:center;justify-content:center;animation:fadeIn 0.2s ease';
        const box = document.createElement('div');
        box.style.cssText = 'background:#fff;border-radius:16px;padding:30px;max-width:420px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,0.3);text-align:center;animation:popIn 0.25s ease';
        box.innerHTML = '<div style="font-size:2.5rem;margin-bottom:10px">' + c.icon + '</div>'
            + '<h3 style="color:' + c.titleColor + ';margin-bottom:12px;font-size:1.2rem">' + title + '</h3>'
            + '<p style="color:#555;font-size:0.95rem;line-height:1.6;margin-bottom:22px">' + message + '</p>'
            + '<button id="styledPopupOkBtn" style="background:' + c.border + ';color:#fff;border:none;padding:10px 32px;border-radius:8px;font-size:1rem;font-weight:600;cursor:pointer;transition:opacity 0.2s">' + okText + '</button>';
        overlay.appendChild(box);
        document.body.appendChild(overlay);
        const okBtn = document.getElementById('styledPopupOkBtn');
        const closePopup = function () { overlay.remove(); if (onOk) onOk(); };
        okBtn.addEventListener('click', closePopup);
        overlay.addEventListener('click', function (e) { if (e.target === overlay) closePopup(); });
    };
    if (typeof showStyledPopup === 'undefined') {
        showStyledPopup = window.showStyledPopup;
    }
}

document.addEventListener('DOMContentLoaded', () => {

    // Prevent click propagation on shift overlay
    const shiftOverlay = document.getElementById('shiftSelectOverlay');
    if (shiftOverlay) {
        shiftOverlay.addEventListener('click', e => e.stopPropagation());
    }

    // --- 1. Get all required elements from the page ---
    const admissionForm = document.getElementById('admissionForm');
    if (!admissionForm) {
        return; // Not on the admission form, do nothing
    }

    const serviceSelect = document.getElementById('id_service_type');
    const registrationTypeSelect = document.getElementById('id_is_new_registration');
    const libraryOptionsDiv = document.getElementById('library-options');

    if (!libraryOptionsDiv) {
        console.error('Seat Selector: Could not find #library-options div.');
        return;
    }

    const floorRadioContainer = libraryOptionsDiv.querySelector('.radio-button-group');

    if (!floorRadioContainer) {
        console.error('Seat Selector: Could not find .radio-button-group div.');
        return;
    }

    const hiddenSeatInput = document.getElementById('id_selected_seat');
    const hiddenFloorInput = admissionForm.querySelector('input[name="floor"][type="hidden"]');
    if (!hiddenFloorInput) {
        console.error('Seat Selector: Could not find hidden floor input.');
        return;
    }

    // Seat Modal elements
    const modalOverlay = document.getElementById('seatModalOverlay');
    const modalContainer = document.getElementById('seatModalContainer');
    const modalCloseBtn = document.getElementById('seatModalCloseBtn');
    const modalTitle = document.getElementById('seatModalTitle');
    const confirmSeatBtn = document.getElementById('confirmSeatBtn');

    // Partial Request Overlay elements
    const partialRequestOverlay = document.getElementById('partialRequestOverlay');
    const partialRequestText = document.getElementById('partialRequestText');
    const confirmPartialRequestBtn = document.getElementById('confirmPartialRequestBtn');
    const cancelPartialRequestBtn = document.getElementById('cancelPartialRequestBtn');

    // --- Scroll indicator logic + clickable/touchable handlers ---
    const modalBody = document.querySelector('#seatModalBody');
    const scrollUp = document.querySelector('.scroll-indicator.up');
    const scrollDown = document.querySelector('.scroll-indicator.down');

    function safeSmoothScrollTo(y) {
        try {
            modalBody.scrollTo({ top: Math.max(0, Math.floor(y)), behavior: 'smooth' });
        } catch (e) {
            modalBody.scrollTop = Math.max(0, Math.floor(y));
        }
    }

    function scrollToTop() {
        safeSmoothScrollTo(0);
    }

    function scrollToBottom() {
        const bottom = modalBody.scrollHeight - modalBody.clientHeight;
        safeSmoothScrollTo(bottom);
    }

    function addIndicatorInteractivity(indicatorEl, onActivate) {
        if (!indicatorEl) return;

        indicatorEl.setAttribute('role', 'button');
        indicatorEl.setAttribute('tabindex', '0');
        indicatorEl.setAttribute('aria-hidden', 'false');

        indicatorEl.addEventListener('click', (e) => {
            e.preventDefault();
            onActivate();
        }, { passive: false });

        indicatorEl.addEventListener('touchstart', (e) => {
            e.preventDefault();
            onActivate();
        }, { passive: false });

        indicatorEl.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onActivate();
            }
        });
    }

    function handleModalScroll() {
        if (!modalBody || !scrollUp || !scrollDown) return;

        const scrollableDistance = Math.max(0, modalBody.scrollHeight - modalBody.clientHeight);
        if (scrollableDistance === 0) {
            scrollUp.classList.remove('visible');
            scrollDown.classList.remove('visible');
            scrollUp.classList.remove('interactive');
            scrollDown.classList.remove('interactive');
            return;
        }

        const current = modalBody.scrollTop;
        const TOP_MARGIN = 0.05;
        const BOTTOM_MARGIN = 0.05;

        const topHideThreshold = scrollableDistance * TOP_MARGIN;
        const bottomHideThreshold = scrollableDistance * (1 - BOTTOM_MARGIN);

        const showUp = current > topHideThreshold;
        const showDown = current < bottomHideThreshold;

        scrollUp.classList.toggle('visible', showUp);
        scrollDown.classList.toggle('visible', showDown);

        scrollUp.classList.toggle('interactive', showUp);
        scrollDown.classList.toggle('interactive', showDown);
    }

    document.querySelectorAll('[data-action="scroll-top"]').forEach(el => {
        el.addEventListener('click', (e) => { e.preventDefault(); safeSmoothScrollTo(0); }, { passive: false });
        el.addEventListener('touchstart', (e) => { e.preventDefault(); safeSmoothScrollTo(0); }, { passive: false });
    });
    document.querySelectorAll('[data-action="scroll-bottom"]').forEach(el => {
        el.addEventListener('click', (e) => { e.preventDefault(); safeSmoothScrollTo(modalBody.scrollHeight - modalBody.clientHeight); }, { passive: false });
        el.addEventListener('touchstart', (e) => { e.preventDefault(); safeSmoothScrollTo(modalBody.scrollHeight - modalBody.clientHeight); }, { passive: false });
    });

    function initScrollIndicatorsWithClicks() {
        if (!modalBody) return;

        modalBody.removeEventListener('scroll', handleModalScroll);
        modalBody.addEventListener('scroll', handleModalScroll, { passive: true });

        window.removeEventListener('resize', handleModalScroll);
        window.addEventListener('resize', handleModalScroll);

        if (window._seatModalMutationObserver) window._seatModalMutationObserver.disconnect();
        window._seatModalMutationObserver = new MutationObserver(() => setTimeout(handleModalScroll, 70));
        window._seatModalMutationObserver.observe(modalBody, { childList: true, subtree: true });

        addIndicatorInteractivity(scrollUp, scrollToTop);
        addIndicatorInteractivity(scrollDown, scrollToBottom);

        setTimeout(handleModalScroll, 80);
    }

    initScrollIndicatorsWithClicks();

    // Seat Layout wrappers
    const groundFloorWrapper = document.getElementById('ground-floor-wrapper');
    const firstFloorWrapper = document.getElementById('first-floor-wrapper');

    let openModalButton = null;
    let currentlySelectedSeat = null;
    let pendingSelection = null; // Transactional state

    // --- 2. Create the Modal Trigger Button ---

    function createModalTriggerButton() {
        if (document.getElementById('openSeatModalBtn')) {
            return;
        }

        const button = document.createElement('button');
        button.setAttribute('type', 'button');
        button.setAttribute('id', 'openSeatModalBtn');
        button.textContent = 'Select Seat Preference';
        button.className = 'btn btn-primary';
        button.style.width = '100%';
        button.style.padding = '12px';
        button.style.fontSize = '1.1rem';
        button.style.marginTop = '10px';
        button.style.display = 'none';

        const floorGroup = floorRadioContainer.closest('.form-group');
        if (floorGroup) {
            floorGroup.insertAdjacentElement('afterend', button);
        } else {
            floorRadioContainer.insertAdjacentElement('afterend', button);
        }

        openModalButton = button;
        openModalButton.addEventListener('click', openSeatModal);
    }

    function updateButtonVisibilityAndText() {
        if (!openModalButton) return;

        const isLibrary = serviceSelect.value === 'Library';
        const isNewStudent = registrationTypeSelect.value === 'True';

        if (isLibrary) {
            if (isNewStudent) {
                openModalButton.textContent = 'Select Seat Preference';
            } else {
                openModalButton.textContent = 'Choose Your Occupied Seat';
            }
            openModalButton.style.display = 'block';
        } else {
            openModalButton.style.display = 'none';
        }
    }

    /**
     * INTELLIGENT GUARD: When registration type changes, strictly clear ANY
     * existing seat selection because the selection logic, availability, and 
     * allowed operations depend entirely on whether they are a New or Admitted student.
     */
    function onRegistrationTypeChange() {
        const isNewStudent = registrationTypeSelect.value === 'True';
        const tempInput = document.getElementById('id_is_temporary_request');
        const hasSeatSelected = hiddenSeatInput && hiddenSeatInput.value !== '';

        // If switching registration types and a seat was already selected → CLEAR IT
        if (hasSeatSelected) {
            // Clear all seat-related hidden inputs
            if (hiddenSeatInput) hiddenSeatInput.value = '';
            if (tempInput) tempInput.value = 'false';
            const shiftInput = document.getElementById('id_shift_preference');
            if (shiftInput) shiftInput.value = 'full';
            const daysInput = document.getElementById('id_temp_hold_days');
            if (daysInput) daysInput.value = '0';

            // Clear visual selection
            clearAllSelections();
            pendingSelection = null;

            // Reset button
            if (openModalButton) {
                openModalButton.textContent = isNewStudent ? 'Select Seat Preference' : 'Choose Your Occupied Seat';
                openModalButton.style.background = '';
                openModalButton.style.borderColor = '';
            }

            // Reset preview
            const preview = document.getElementById('selectedSeatPreview');
            if (preview) {
                preview.textContent = 'No seat selected';
                preview.style.color = '#dc3545';
            }

            // Show generic re-selection warning popup
            showStyledPopup({
                title: 'Seat Selection Cleared',
                message: 'You changed your <strong>Registration Type</strong>.<br><br>Because seat availability rules are different for New vs. Already Admitted students, your previous seat selection has been automatically cleared.<br><br>Please select your seat again.',
                type: 'warning'
            });
        }
    }

    // --- 3. Modal Open/Close Logic ---

    function positionUpIndicatorBelowHeader() {
        const header = document.querySelector('.seat-modal-header');
        const up = document.querySelector('#scrollIndicatorUp');
        const container = document.querySelector('.seat-modal-container');

        if (!header || !up || !container) return;

        const headerRect = header.getBoundingClientRect();
        const headerHeight = headerRect.height;
        const GAP = 12;
        const topOffset = headerHeight + GAP;

        up.style.top = topOffset + 'px';
        up.style.transform = 'translateX(-50%) translateY(-6px)';
    }

    window.addEventListener('resize', positionUpIndicatorBelowHeader);

    async function openSeatModal() {
        const selectedFloorRadio = floorRadioContainer.querySelector('input[name="floor_radio"]:checked');

        if (!selectedFloorRadio) {
            showStyledPopup({ title: 'Floor Not Selected', message: 'Please select a library floor first before choosing a seat.', type: 'warning' });
            return;
        }

        const floor = selectedFloorRadio.value;

        modalTitle.textContent = `Loading ${floor} Layout...`;

        // Force visibility
        modalOverlay.style.display = 'block';
        modalOverlay.classList.add('visible');

        if (modalContainer) {
            modalContainer.style.display = 'block';
            modalContainer.style.opacity = '1';
        }

        confirmSeatBtn.disabled = true;
        confirmSeatBtn.textContent = 'Confirm Seat'; // Reset text to avoid stale state
        confirmSeatBtn.style.background = '';        // Reset background
        confirmSeatBtn.style.borderColor = '';       // Reset border

        // --- TRANSACTIONAL INIT ---
        // Initialize pendingSelection from current form state (if any)
        // This ensures if user confirms without changing, it stays same.
        pendingSelection = null;
        if (hiddenSeatInput && hiddenSeatInput.value && hiddenFloorInput && hiddenFloorInput.value === floor) {
            const currentShift = document.getElementById('id_shift_preference')?.value || 'full';
            const currentIsTemp = document.getElementById('id_is_temporary_request')?.value === 'true';
            const currentHoldDays = document.getElementById('id_temp_hold_days')?.value || 0;

            pendingSelection = {
                seat: hiddenSeatInput.value,
                floor: hiddenFloorInput.value,
                shift: currentShift,
                isTemp: currentIsTemp,
                holdDays: currentHoldDays
            };
            // confirmSeatBtn.disabled = false; // Will be enabled by updateLayout highlighting
        }

        try {
            const response = await fetch(`/api/get_public_seat_status/?floor=${encodeURIComponent(floor)}`);
            if (!response.ok) {
                throw new Error('Failed to load seat data.');
            }
            const seatData = await response.json();
            updateLayout(floor, seatData.seats);
            groundFloorWrapper.style.display = (floor === 'Ground Floor') ? 'block' : 'none';
            firstFloorWrapper.style.display = (floor === '1st Floor') ? 'block' : 'none';
            modalTitle.textContent = `Select Your Seat (${floor})`;

            setTimeout(handleModalScroll, 120);

        } catch (error) {
            console.error(error);
            showStyledPopup({ title: 'Loading Error', message: 'Error loading library layout. Please try again.', type: 'error' });
            closeSeatModal();
        }
        setTimeout(positionUpIndicatorBelowHeader, 80);
    }

    function closeSeatModal() {
        if (modalOverlay) {
            modalOverlay.classList.remove('visible');
            modalOverlay.style.display = '';
        }
        if (modalContainer) {
            modalContainer.style.display = '';
            modalContainer.style.opacity = '';
        }

        if (currentlySelectedSeat) {
            currentlySelectedSeat.classList.remove('selected');
        }
        currentlySelectedSeat = null;

        if (scrollUp) scrollUp.classList.remove('visible');
        if (scrollDown) scrollDown.classList.remove('visible');
    }

    // Helper to clear all selections
    function clearAllSelections() {
        document.querySelectorAll('.seat').forEach(seat => {
            seat.classList.remove(
                'selected',
                'selected-morning',
                'selected-evening',
                'selected-full',
                'selected-temp',
                'selected-temp-morning',
                'selected-temp-evening',
                'selected-temp-full'
            );

            // 1. Restore Morning Label
            const morningLabel = seat.querySelector('.seat-morning-label');
            if (morningLabel) {
                if (morningLabel.classList.contains('dynamic-label')) {
                    morningLabel.remove();
                } else {
                    if (morningLabel.dataset.originalText) {
                        morningLabel.textContent = morningLabel.dataset.originalText;
                        delete morningLabel.dataset.originalText;
                    }
                    morningLabel.style.display = ''; // Ensure visible
                }
            }

            // 2. Restore Evening Label
            const eveningLabel = seat.querySelector('.seat-evening-label');
            if (eveningLabel) {
                if (eveningLabel.classList.contains('dynamic-label')) {
                    eveningLabel.remove();
                } else {
                    if (eveningLabel.dataset.originalText) {
                        eveningLabel.textContent = eveningLabel.dataset.originalText;
                        delete eveningLabel.dataset.originalText;
                    }
                    eveningLabel.style.display = ''; // Ensure visible
                }
            }

            // 3. Restore Main Label
            const labelEl = seat.querySelector('.seat-label');
            if (labelEl) {
                if (labelEl.dataset.originalText) {
                    labelEl.textContent = labelEl.dataset.originalText;
                    delete labelEl.dataset.originalText;
                } else if (labelEl.textContent === 'Selected' || labelEl.textContent === 'Temp.') {
                    labelEl.textContent = 'Select';
                }

                // Restore Visibility: Hide if static split labels exist
                const hasStaticMorning = seat.querySelector('.seat-morning-label:not(.dynamic-label)');
                const hasStaticEvening = seat.querySelector('.seat-evening-label:not(.dynamic-label)');

                if (hasStaticMorning || hasStaticEvening) {
                    labelEl.style.display = 'none';
                } else {
                    labelEl.style.display = '';
                }
            }
        });

        currentlySelectedSeat = null;
    }

    // --- 4. Layout Update and Click Logic ---

    function updateLayout(floor, seats) {
        const wrapper = (floor === 'Ground Floor') ? groundFloorWrapper : firstFloorWrapper;
        if (!wrapper) return;

        // ---------- RESET ALL SEATS ----------
        wrapper.querySelectorAll('.seat').forEach(seatEl => {
            if (seatEl.classList.contains('special') || seatEl.classList.contains('empty-space')) return;

            // PRESERVE: seat-icon-group must stay!
            seatEl.classList.remove(
                'available', 'occupied-full', 'occupied-morning', 'occupied-evening',
                'on_hold', 'hold-full', 'hold-morning', 'hold-evening',
                'shift-seat', 'shift-partial', 'shift-both-partial',
                'diagonal-hold-partial', 'hold-morning-temp-morning', 'hold-evening-temp-evening',
                'selected', 'selected-morning', 'selected-evening', 'selected-full'
            );
            seatEl.classList.add('available');

            const label = seatEl.querySelector('.seat-label');
            if (label) label.textContent = 'Select';

            delete seatEl.dataset.status;
            delete seatEl.dataset.info;

            seatEl.querySelectorAll('.seat-half').forEach(h => h.remove());
        });

        // ---------- APPLY API DATA ----------
        for (const seat of seats) {

            const seatEl = wrapper.querySelector(`.seat[data-seat-id="${seat.seat_number}"]`);
            if (!seatEl) continue;

            seatEl.dataset.info = JSON.stringify(seat);

            // =====================================================
            // SHIFT SEATS (40–53 Ground Floor)
            // =====================================================
            // Cleanup existing dynamic labels and restore main label visibility
            seatEl.querySelectorAll('.seat-morning-label, .seat-evening-label').forEach(el => el.remove());
            const lbl = seatEl.querySelector('.seat-label');
            if (lbl) lbl.style.display = '';

            // =====================================================
            // SHIFT SEATS (40–53 Ground Floor)
            // =====================================================
            if (seat.is_shift_enabled) {

                seatEl.classList.add('shift-seat');
                seatEl.classList.remove('available'); // Remove default; actual status set below

                const topHalf = document.createElement('div');
                topHalf.className = 'seat-half seat-morning';

                const bottomHalf = document.createElement('div');
                bottomHalf.className = 'seat-half seat-evening';

                const lockedShiftsList = (seat.locked_shifts || '').split(',').filter(Boolean);
                if (lockedShiftsList.includes('morning')) {
                    topHalf.classList.add('locked');
                    topHalf.dataset.locked = 'true';
                    seatEl.classList.add('locked-morning');
                } else {
                    topHalf.classList.add('shift-available');
                }

                if (lockedShiftsList.includes('evening')) {
                    bottomHalf.classList.add('locked');
                    bottomHalf.dataset.locked = 'true';
                    seatEl.classList.add('locked-evening');
                } else {
                    bottomHalf.classList.add('shift-available');
                }

                if (seat.is_locked || lockedShiftsList.includes('full')) {
                    seatEl.classList.add('locked');
                    seatEl.dataset.locked = 'true';
                }

                seatEl.prepend(bottomHalf);
                seatEl.prepend(topHalf);


                // ---- ON HOLD (detect by shift-wise holds) ----
                const hasHolds = seat.morning_hold || seat.evening_hold || seat.full_day_hold;

                // If there's an assignment (even if on hold), morning_taken will be true.
                // We treat a shift as strictly occupied if it's taken AND NOT on hold, OR if it's on hold BUT a temp tenant holds it.
                const isStrictlyOccupiedM = seat.morning_taken && (!seat.morning_hold || seat.morning_temp_allotted);
                const isStrictlyOccupiedE = seat.evening_taken && (!seat.evening_hold || seat.evening_temp_allotted);

                if (hasHolds && !isStrictlyOccupiedM && !isStrictlyOccupiedE && !seat.full_day_taken) {
                    // Seat is on hold (shift-wise) - no shifts strictly occupied yet

                    // PRIORITIZE SPLIT CHECK: If both shifts have holds, show split view
                    // This handles distinct holds (different days/students) better than generic full hold
                    if (seat.morning_hold && seat.evening_hold) {
                        // DUAL HOLD: Show both shift holds separately
                        seatEl.classList.add('hold-morning');
                        seatEl.classList.add('hold-evening');
                        seatEl.dataset.status = 'on_hold';

                        // Hide main label
                        const lbl = seatEl.querySelector('.seat-label');
                        if (lbl) lbl.style.display = 'none';

                        // Create Morning Label
                        const mLabel = document.createElement('span');
                        mLabel.className = 'seat-morning-label';
                        const mDays = seat.morning_hold_remaining_days;
                        mLabel.textContent = (mDays && mDays > 0) ? `Hold M(${mDays})` : 'Hold M';
                        seatEl.appendChild(mLabel);

                        // Create Evening Label
                        const eLabel = document.createElement('span');
                        eLabel.className = 'seat-evening-label';
                        const eDays = seat.evening_hold_remaining_days;
                        eLabel.textContent = (eDays && eDays > 0) ? `Hold E(${eDays})` : 'Hold E';
                        seatEl.appendChild(eLabel);
                    }
                    else if (seat.full_day_hold) {
                        seatEl.classList.add('hold-full');
                        seatEl.dataset.status = 'on_hold';
                        const days = seat.full_day_hold_remaining_days || seat.remaining_days;
                        if (typeof days === 'number' && !isNaN(days) && days > 0) {
                            seatEl.querySelector('.seat-label').textContent = `Hold(${days})`;
                        } else {
                            seatEl.querySelector('.seat-label').textContent = 'Hold';
                        }
                    }
                    else if (seat.morning_hold) {
                        seatEl.classList.add('hold-morning');
                        seatEl.dataset.status = 'on_hold';

                        const lbl = seatEl.querySelector('.seat-label');
                        if (lbl) lbl.style.display = 'none';

                        const mLabel = document.createElement('span');
                        mLabel.className = 'seat-morning-label';
                        const days = seat.morning_hold_remaining_days;
                        mLabel.textContent = (days && days > 0) ? `Hold M(${days})` : 'Hold M';
                        seatEl.appendChild(mLabel);

                        const eLabel = document.createElement('span');
                        eLabel.className = 'seat-evening-label';
                        eLabel.textContent = 'Select';
                        seatEl.appendChild(eLabel);
                    } else if (seat.evening_hold) {
                        seatEl.classList.add('hold-evening');
                        seatEl.dataset.status = 'on_hold';

                        const lbl = seatEl.querySelector('.seat-label');
                        if (lbl) lbl.style.display = 'none';

                        const mLabel = document.createElement('span');
                        mLabel.className = 'seat-morning-label';
                        mLabel.textContent = 'Select';
                        seatEl.appendChild(mLabel);

                        const eLabel = document.createElement('span');
                        eLabel.className = 'seat-evening-label';
                        const days = seat.evening_hold_remaining_days;
                        eLabel.textContent = (days && days > 0) ? `Hold E(${days})` : 'Hold E';
                        seatEl.appendChild(eLabel);
                    }
                    continue;
                }

                // ---- OCCUPIED (with awareness of temporary allotments) ----
                const morningTaken = seat.morning_taken;
                const eveningTaken = seat.evening_taken;
                const fullDayTaken = seat.full_day_taken;
                const morningTemp = seat.morning_temp_allotted;
                const eveningTemp = seat.evening_temp_allotted;

                if (fullDayTaken) {
                    if (seat.full_day_hold) {
                        if (morningTemp && eveningTemp) {
                            seatEl.classList.add('hold-morning-temp-morning', 'hold-evening-temp-evening');
                            seatEl.dataset.status = 'occupied';
                        } else if (morningTemp) {
                            seatEl.classList.add('hold-morning-temp-morning', 'hold-evening');
                            seatEl.dataset.status = 'on_hold';
                        } else if (eveningTemp) {
                            seatEl.classList.add('hold-evening-temp-evening', 'hold-morning');
                            seatEl.dataset.status = 'on_hold';
                        } else {
                            // Full day is strictly on hold
                            seatEl.classList.add('on_hold');
                            seatEl.dataset.status = 'on_hold';
                        }

                        // Handle labels for hold
                        const lbl = seatEl.querySelector('.seat-label');
                        if (lbl) lbl.style.display = 'none'; // CSS handles hiding, but JS ensures it's clear

                        const days = seat.full_day_hold_remaining_days || seat.remaining_days;
                        const holdText = (typeof days === 'number' && !isNaN(days) && days > 0) ? `Hold F(${days})` : 'Hold F';

                        if (morningTemp && eveningTemp) {
                            // Do nothing, both are temp occupied, no hold label
                        } else if (morningTemp) {
                            // Morning is temp, put holdText on Evening
                            const eLabel = document.createElement('span');
                            eLabel.className = 'seat-evening-label';
                            eLabel.textContent = holdText;
                            seatEl.appendChild(eLabel);
                        } else if (eveningTemp) {
                            // Evening is temp, put holdText on Morning
                            const mLabel = document.createElement('span');
                            mLabel.className = 'seat-morning-label';
                            mLabel.textContent = holdText;
                            seatEl.appendChild(mLabel);
                        } else {
                            if (lbl) {
                                lbl.style.display = '';
                                lbl.textContent = holdText;
                            }
                        }
                    } else if (morningTemp && eveningTemp) {
                        seatEl.classList.add('shift-both-partial');
                        seatEl.dataset.status = 'occupied';
                        seatEl.querySelector('.seat-label').textContent = 'Occupied(F)';
                    } else {
                        seatEl.classList.add('occupied-full');
                        seatEl.dataset.status = 'occupied';
                        seatEl.querySelector('.seat-label').textContent = 'Occupied(F)';
                    }
                }
                else if (morningTaken && eveningTaken) {
                    // BOTH SHIFTS TAKEN (Split Visuals)
                    if (morningTemp && eveningTemp) {
                        seatEl.classList.add('shift-both-partial');
                    } else if (morningTemp || eveningTemp) {
                        seatEl.classList.add('shift-partial');
                    } else {
                        // Use granular classes
                        if (morningTemp && seat.morning_hold) {
                            seatEl.classList.add('hold-morning-temp-morning');
                        } else if (seat.morning_hold) {
                            seatEl.classList.add('hold-morning');
                        } else {
                            seatEl.classList.add('occupied-morning');
                        }

                        if (eveningTemp && seat.evening_hold) {
                            seatEl.classList.add('hold-evening-temp-evening');
                        } else if (seat.evening_hold) {
                            seatEl.classList.add('hold-evening');
                        } else {
                            seatEl.classList.add('occupied-evening');
                        }
                    }

                    // Strict Label Logic: Split Labels
                    seatEl.querySelector('.seat-label').style.display = 'none';

                    const mLabel = document.createElement('span');
                    mLabel.className = 'seat-morning-label';
                    if (seat.morning_hold) {
                        const mDays = seat.morning_hold_remaining_days;
                        mLabel.textContent = (mDays && mDays > 0) ? `Hold M(${mDays})` : 'Hold M';
                    } else {
                        mLabel.textContent = 'Occupied(M)';
                    }
                    seatEl.appendChild(mLabel);

                    const eLabel = document.createElement('span');
                    eLabel.className = 'seat-evening-label';
                    if (seat.evening_hold) {
                        const eDays = seat.evening_hold_remaining_days;
                        eLabel.textContent = (eDays && eDays > 0) ? `Hold E(${eDays})` : 'Hold E';
                    } else {
                        eLabel.textContent = 'Occupied(E)';
                    }
                    seatEl.appendChild(eLabel);

                    seatEl.dataset.status = (seat.morning_hold || seat.evening_hold) ? 'on_hold' : 'occupied';

                } else if (morningTaken) {
                    if (morningTemp && seat.morning_hold) {
                        seatEl.classList.add('hold-morning-temp-morning');
                    } else if (morningTemp) {
                        if (seat.evening_hold) {
                            seatEl.classList.add('diagonal-hold-partial');
                        } else {
                            seatEl.classList.add('shift-partial');
                        }
                    } else if (seat.morning_hold) {
                        seatEl.classList.add('hold-morning');
                    } else {
                        seatEl.classList.add('occupied-morning');
                    }

                    // Check if the unoccupied shift is on hold
                    let evenStatus = 'Select';
                    if (seat.evening_hold) {
                        seatEl.dataset.status = 'on_hold';
                        const eDays = seat.evening_hold_remaining_days;
                        evenStatus = (eDays && eDays > 0) ? `Hold E(${eDays})` : 'Hold E';
                    } else {
                        seatEl.dataset.status = 'partial';
                    }

                    // Strict Label Logic: Split Labels
                    seatEl.querySelector('.seat-label').style.display = 'none';

                    const mLabel = document.createElement('span');
                    mLabel.className = 'seat-morning-label';
                    if (seat.morning_hold) {
                        const mDays = seat.morning_hold_remaining_days;
                        mLabel.textContent = (mDays && mDays > 0) ? `Hold M(${mDays})` : 'Hold M';
                    } else {
                        mLabel.textContent = 'Occupied(M)';
                    }
                    seatEl.appendChild(mLabel);

                    const eLabel = document.createElement('span');
                    eLabel.className = 'seat-evening-label';
                    eLabel.textContent = evenStatus;
                    seatEl.appendChild(eLabel);

                } else if (eveningTaken) {
                    if (eveningTemp && seat.evening_hold) {
                        seatEl.classList.add('hold-evening-temp-evening');
                    } else if (eveningTemp) {
                        if (seat.morning_hold) {
                            seatEl.classList.add('diagonal-hold-partial');
                        } else {
                            seatEl.classList.add('shift-partial');
                        }
                    } else if (seat.evening_hold) {
                        seatEl.classList.add('hold-evening');
                    } else {
                        seatEl.classList.add('occupied-evening');
                    }

                    // Check if the unoccupied shift is on hold
                    let mornStatus = 'Select';
                    if (seat.morning_hold) {
                        seatEl.dataset.status = 'on_hold';
                        const mDays = seat.morning_hold_remaining_days;
                        mornStatus = (mDays && mDays > 0) ? `Hold M(${mDays})` : 'Hold M';
                    } else {
                        seatEl.dataset.status = 'partial';
                    }

                    // Strict Label Logic: Split Labels
                    seatEl.querySelector('.seat-label').style.display = 'none';

                    const mLabel = document.createElement('span');
                    mLabel.className = 'seat-morning-label';
                    mLabel.textContent = mornStatus;
                    seatEl.appendChild(mLabel);

                    const eLabel = document.createElement('span');
                    eLabel.className = 'seat-evening-label';
                    if (seat.evening_hold) {
                        const eDays = seat.evening_hold_remaining_days;
                        eLabel.textContent = (eDays && eDays > 0) ? `Hold E(${eDays})` : 'Hold E';
                    } else {
                        eLabel.textContent = 'Occupied(E)';
                    }
                    seatEl.appendChild(eLabel);

                } else {
                    // Both shifts free - check if any shift is locked
                    const lockedShiftsList = (seat.locked_shifts || '').split(',').filter(Boolean);
                    const isMLocked = lockedShiftsList.includes('morning') || seat.is_locked;
                    const isELocked = lockedShiftsList.includes('evening') || seat.is_locked;

                    if (isMLocked || isELocked) {
                        seatEl.querySelector('.seat-label').style.display = 'none';
                        
                        const mLabel = document.createElement('span');
                        mLabel.className = 'seat-morning-label ' + (isMLocked ? 'status-locked' : 'status-available');
                        mLabel.textContent = isMLocked ? '🔒 Locked' : 'Available';
                        seatEl.appendChild(mLabel);

                        const eLabel = document.createElement('span');
                        eLabel.className = 'seat-evening-label ' + (isELocked ? 'status-locked' : 'status-available');
                        eLabel.textContent = isELocked ? '🔒 Locked' : 'Available';
                        seatEl.appendChild(eLabel);

                        if (!isMLocked || !isELocked) {
                            seatEl.classList.add('available');
                            seatEl.dataset.status = 'partial_available';
                        } else {
                            seatEl.classList.add('locked');
                            seatEl.dataset.status = 'locked';
                        }
                    } else {
                        seatEl.classList.add('available');
                        seatEl.dataset.status = 'available';
                        seatEl.querySelector('.seat-label').textContent = 'Available';
                    }
                }


            }

            // =====================================================
            // NORMAL SEATS
            // =====================================================
            else {

                const status = seat.status;
                const hasHold = seat.is_on_hold || seat.full_day_hold || seat.morning_hold;
                const hasTemp = seat.morning_temp_allotted || seat.evening_temp_allotted;
                const hasPendingTemp = seat.has_pending_temp_request;

                if (seat.is_locked || seat.locked_shifts === 'full') {
                    seatEl.classList.remove('available');
                    seatEl.classList.add('locked');
                    seatEl.dataset.locked = 'true';
                    const lbl = seatEl.querySelector('.seat-label');
                    if (lbl) lbl.textContent = '🔒 Locked';
                }
                // Determine correct CSS class
                else if (hasHold && hasTemp) {

                    // Hold + Active Temp Tenant → Diagonal orange/pink split
                    seatEl.classList.remove('available');
                    seatEl.classList.add('hold-partial');
                    seatEl.dataset.status = 'hold_partial';

                    // Show hold days + "Temp." labels
                    const lbl = seatEl.querySelector('.seat-label');
                    if (lbl) lbl.style.display = 'none';

                    const days = seat.remaining_days || seat.full_day_hold_remaining_days || seat.morning_hold_remaining_days || 0;
                    const mLabel = document.createElement('span');
                    mLabel.className = 'seat-morning-label';
                    mLabel.textContent = (days && days > 0) ? `Hold(${days})` : 'Hold';
                    seatEl.appendChild(mLabel);

                    const eLabel = document.createElement('span');
                    eLabel.className = 'seat-evening-label';
                    eLabel.textContent = 'Temp.';
                    seatEl.appendChild(eLabel);

                } else if (hasHold && hasPendingTemp) {
                    // Hold + Pending Temp Request → show as on_hold with pending indication
                    seatEl.classList.remove('available');
                    seatEl.classList.add('pending-temp');
                    seatEl.dataset.status = 'on_hold';
                    const days = seat.remaining_days || seat.full_day_hold_remaining_days || 0;
                    if (typeof days === 'number' && !isNaN(days) && days > 0) {
                        seatEl.querySelector('.seat-label').textContent = `Hold(${days})`;
                    } else {
                        seatEl.querySelector('.seat-label').textContent = 'On Hold';
                    }
                } else {
                    // In admission form: pending seats shown as available
                    // (pending is only shown in teacher seat manager)
                    if (status === 'pending') {
                        // Keep as available - multiple students can request same seat
                        seatEl.dataset.status = 'available';
                        seatEl.querySelector('.seat-label').textContent = 'Available';
                    } else {
                        seatEl.classList.remove('available');
                        seatEl.classList.add(status);
                        seatEl.dataset.status = status;

                        let labelText = 'Available';
                        if (status === 'occupied') labelText = 'Occupied';
                        if (status === 'partial') labelText = 'Occupied';
                        if (status === 'on_hold') {
                            // Per SKILL.md: Show "Hold(X)" where X = remaining days
                            const days = seat.remaining_days || seat.hold_days;
                            if (typeof days === 'number' && !isNaN(days) && days > 0) {
                                labelText = `Hold(${days})`;
                            } else {
                                labelText = 'On Hold';
                            }
                        }

                        seatEl.querySelector('.seat-label').textContent = labelText;
                    }
                }
            }

            // --- PERSISTENCE RESTORE IN MODAL ---
            // If this seat matches the hidden input, visually select it
            if (hiddenSeatInput.value === seat.seat_number && floor === hiddenFloorInput.value) {
                const shiftInput = document.getElementById('id_shift_preference');
                const shiftValue = shiftInput ? shiftInput.value : 'full';
                const tempInput = document.getElementById('id_is_temporary_request');
                const isTemp = tempInput ? tempInput.value === 'true' : false;

                // We use selectSeatWithShift logic but without triggering side effects if possible
                // Actually, calling selectSeatWithShift is safe as it just updates hidden inputs to what they already are
                // But we need to handle the "Temp" vs "Normal" visual distinction

                // However, selectSeatWithShift doesn't handle "Temp" visual class application fully for all cases
                // (saveTemporarySelection does that).

                if (isTemp) {
                    // Apply temp visuals manually since saveTemporarySelection does UI + Input update
                    // And we don't want to re-append inputs.
                    if (seat.is_shift_enabled) {
                        if (shiftValue === 'morning') seatEl.classList.add('selected-temp-morning');
                        else if (shiftValue === 'evening') seatEl.classList.add('selected-temp-evening');
                        else seatEl.classList.add('selected-temp-full');

                        if (shiftValue === 'morning') {
                            let morningLabel = seatEl.querySelector('.seat-morning-label');
                            if (!morningLabel) {
                                morningLabel = document.createElement('span');
                                morningLabel.className = 'seat-morning-label seat-morning-label-temp';
                                seatEl.appendChild(morningLabel);
                            }
                            morningLabel.textContent = 'Temp.';
                            const label = seatEl.querySelector('.seat-label');
                            if (label && label.textContent === 'Select') label.style.display = 'none';
                        }
                        else if (shiftValue === 'full') {
                            // Full day temp: HIDE split labels, show single 'Temp.' label
                            seatEl.querySelectorAll('.seat-morning-label, .seat-evening-label').forEach(el => el.style.display = 'none');
                            const label = seatEl.querySelector('.seat-label');
                            if (label) { label.style.display = ''; label.textContent = 'Temp.'; }
                        }
                        else {
                            const label = seatEl.querySelector('.seat-label');
                            if (label) label.textContent = 'Temp.';
                        }
                    } else {
                        seatEl.classList.add('selected-temp');
                        const label = seatEl.querySelector('.seat-label');
                        if (label) label.textContent = 'Temp.';
                    }
                    currentlySelectedSeat = seatEl;

                    // Update modal button logic
                    confirmSeatBtn.disabled = false;
                    const floorPrefix = floor === 'Ground Floor' ? 'G' : 'F';
                    let btnText = `Confirm Seat ${floorPrefix} ${seat.seat_number}`;
                    const shiftCap = shiftValue === 'full' ? '' : shiftValue.charAt(0).toUpperCase() + shiftValue.slice(1);
                    btnText += shiftValue === 'full' ? ' (Temporary)' : ` (Temp. ${shiftCap})`;
                    confirmSeatBtn.textContent = btnText;
                    confirmSeatBtn.style.background = '#ff9abe';
                    confirmSeatBtn.style.borderColor = '#ff7aa5';

                } else {
                    // Normal selection
                    selectSeatWithShift(seatEl, shiftValue);
                }
            }
        }
    }



    // --- Seat Click Handling for non-available seat notifications ---
    function sendSeatInterest(seatNumber, floor, requestedShift = null) {
        fetch('/api/seat-interest/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            },
            body: JSON.stringify({
                seat_number: seatNumber,
                floor: floor,
                requested_shift: requestedShift
            })

        }).catch(err => {
            console.warn('Seat interest tracking failed', err);
        });
    }

    /**
     * Save temporary selection locally without API call (Transactional)
     * Updates Pending Selection & Visuals
     */
    function saveTemporarySelection(seatNumber, floor, requestedShift, alertConfig) {
        // 1. Update Pending Selection (DO NOT TOUCH HIDDEN INPUTS)
        const days = alertConfig.holdDays || alertConfig.morningHoldDays || 0;

        pendingSelection = {
            seat: seatNumber,
            floor: floor,
            shift: requestedShift,
            isTemp: true,
            holdDays: days
        };
        console.log('✅ Temporary selection pending:', pendingSelection);

        // 2. Update Visuals (Select the seat) - Use PINK for temporary selections
        const wrapper = (floor === 'Ground Floor') ? groundFloorWrapper : firstFloorWrapper;
        const seatEl = wrapper?.querySelector(`.seat[data-seat-id="${seatNumber}"]`);

        clearAllSelections();
        if (seatEl) {
            const seatInfo = seatEl.dataset.info ? JSON.parse(seatEl.dataset.info) : null;
            const labelEl = seatEl.querySelector('.seat-label');

            if (seatInfo && seatInfo.is_shift_enabled) {
                // Use TEMPORARY selection classes (light pink) for hold seats
                if (requestedShift === 'morning') {
                    seatEl.classList.add('selected-temp-morning');
                    // For morning temp: show "Temp." in the morning half
                    let morningLabel = seatEl.querySelector('.seat-morning-label');
                    if (!morningLabel) {
                        morningLabel = document.createElement('span');
                        morningLabel.className = 'seat-morning-label seat-morning-label-temp dynamic-label';
                        // Append to seat element directly for proper z-index
                        seatEl.appendChild(morningLabel);
                    } else {
                        if (!morningLabel.dataset.originalText) morningLabel.dataset.originalText = morningLabel.textContent;
                    }
                    morningLabel.textContent = 'Temp.';
                    // Styling is handled by CSS classes

                    // If evening shift shows "Select" (free), hide the bottom label
                    if (labelEl) {
                        if (labelEl.style.display !== 'none') labelEl.style.display = 'none';
                    }
                }
                else if (requestedShift === 'evening') {
                    seatEl.classList.add('selected-temp-evening');
                    // Check for evening label to override
                    let eveningLabel = seatEl.querySelector('.seat-evening-label');
                    if (!eveningLabel) {
                        // Usually evening label implies split view.
                        // If no evening label, we might need to rely on main label or create one?
                        // For shift seat, usually creating split labels is safer visually.
                        if (labelEl) {
                            if (!labelEl.dataset.originalText) labelEl.dataset.originalText = labelEl.textContent;
                            labelEl.textContent = 'Temp.';
                        }
                    } else {
                        if (!eveningLabel.dataset.originalText) eveningLabel.dataset.originalText = eveningLabel.textContent;
                        eveningLabel.textContent = 'Temp.';
                    }
                }
                else {
                    seatEl.classList.add('selected-temp-full');
                    // Full day temp: HIDE split labels, show single 'Temp.' label
                    seatEl.querySelectorAll('.seat-morning-label, .seat-evening-label').forEach(el => el.style.display = 'none');
                    if (labelEl) {
                        if (!labelEl.dataset.originalText) labelEl.dataset.originalText = labelEl.textContent;
                        labelEl.style.display = '';
                        labelEl.textContent = 'Temp.';
                    }
                }
            } else {
                // Non-shift seat: use temporary selection class (light pink)
                seatEl.classList.add('selected-temp');
                if (labelEl) {
                    if (!labelEl.dataset.originalText) labelEl.dataset.originalText = labelEl.textContent;
                    labelEl.textContent = 'Temp.';
                }
            }
            currentlySelectedSeat = seatEl;
        }

        // 3. Update Button B text
        // Format: Confirm Seat G 44 (temp. morning)
        const floorPrefix = floor === 'Ground Floor' ? 'G' : 'F';
        let btnText = `Confirm Seat ${floorPrefix} ${seatNumber}`;

        if (requestedShift === 'full') {
            btnText += ` (Temporary)`;
        } else {
            const shiftCapitalized = requestedShift.charAt(0).toUpperCase() + requestedShift.slice(1);
            btnText += ` (Temp. ${shiftCapitalized})`;
        }

        confirmSeatBtn.textContent = btnText;
        confirmSeatBtn.disabled = false;

        // Match pink style for temporary selection
        confirmSeatBtn.style.background = '#ff9abe';
        confirmSeatBtn.style.borderColor = '#ff7aa5';


    }

    /**
     * Show confirmation alert before sending temporary allotment request
     * Displays hold details and asks for confirmation
     * UI matches: image 1.1.1, 1.2.1, 1.3.1, 1.3.2, 1.3.3, 1.4.1, 1.5.1, 1.6.1
     */
    function showConfirmationAlert(seatNumber, floor, requestedShift, alertConfig) {
        const overlay = document.getElementById('partialRequestOverlay');
        const titleEl = document.getElementById('partialRequestTitle');
        const text = document.getElementById('partialRequestText');
        const confirmBtn = document.getElementById('confirmPartialRequestBtn');
        const cancelBtn = document.getElementById('cancelPartialRequestBtn');

        // Set title with warning icon
        if (titleEl) {
            titleEl.innerHTML = '<span style="color: #dc3545;">⚠️</span> Alert';
        }

        // Build alert message based on config
        let alertMessage = '';

        switch (alertConfig.case) {
            case 'normal-hold':
                // Normal seat on hold
                alertMessage = `<strong>${alertConfig.holdDays}</strong> days are left to end hold on seat <strong>${seatNumber}</strong>.<br><br>After ending hold, you will not have any access, Until Librarian allots you another seat.<br><br><strong>Would you send request?</strong>`;
                break;

            case 4:
                // Case 4: One available + One on hold (image 1.1.1)
                alertMessage = `<strong>${alertConfig.holdDays}</strong> days are left to end hold on <strong>${alertConfig.holdShift}</strong> shift on seat <strong>${seatNumber}</strong>.<br><br>After ending hold, you will not have any access, Until Librarian allots you another seat.<br><br><strong>Would you send request?</strong>`;
                break;

            case 5:
                // Case 5: One occupied + One on hold (image 1.2.1)
                alertMessage = `<strong>${alertConfig.holdDays}</strong> days are left to end hold on <strong>${alertConfig.holdShift}</strong> shift on seat <strong>${seatNumber}</strong>.<br><br>After ending hold, you will not have any access, Until Librarian allots you another seat.<br><br><strong>Would you send request?</strong>`;
                break;

            case 6:
                // Case 6A: Both on hold (different students) - (image 1.3.1, 1.3.2, 1.3.3)
                if (requestedShift === 'morning') {
                    alertMessage = `<strong>${alertConfig.morningHoldDays}</strong> days are left to end hold on <strong>morning</strong> shift on seat <strong>${seatNumber}</strong>.<br><br>After ending hold, you will not have any access, Until Librarian allots you another seat.<br><br><strong>Would you send request?</strong>`;
                } else if (requestedShift === 'evening') {
                    alertMessage = `<strong>${alertConfig.eveningHoldDays}</strong> days are left to end hold on <strong>evening</strong> shift on seat <strong>${seatNumber}</strong>.<br><br>After ending hold, you will not have any access, Until Librarian allots you another seat.<br><br><strong>Would you send request?</strong>`;
                } else if (requestedShift === 'full') {
                    alertMessage = `<strong>${alertConfig.morningHoldDays}</strong> days of morning shift & <strong>${alertConfig.eveningHoldDays}</strong> days of evening shift are left to end hold on seat <strong>${seatNumber}</strong>.<br><br>After ending hold on any shift, you will not have any access, Until Librarian allots you another seat.<br><br><strong>Would you send request?</strong>`;
                }
                break;

            case 'case6b':
                // Case 6B: Both on hold + one temp allotted (image 1.5.1)
                alertMessage = `<strong>${alertConfig.holdDays}</strong> days are left to end hold on <strong>${alertConfig.availableShift}</strong> shift on seat <strong>${seatNumber}</strong>.<br><br>After ending hold, you will not have any access, Until Librarian allots you another seat.<br><br><strong>Would you send request?</strong>`;
                break;

            case 7:
                // Case 7A: Full day on hold (image 1.4.1)
                alertMessage = `<strong>${alertConfig.holdDays}</strong> days are left to end hold on <strong>Full day</strong> shift on seat <strong>${seatNumber}</strong>.<br><br>After ending hold, you will not have any access, Until Librarian allots you another seat.<br><br><strong>Would you send request?</strong>`;
                break;

            case 'case7b':
                // Case 7B: Full day on hold + one temp allotted (image 1.6.1)
                alertMessage = `<strong>${alertConfig.holdDays}</strong> days are left to end hold on <strong>${alertConfig.availableShift}</strong> Shift on seat <strong>${seatNumber}</strong>.<br><br>After ending hold, you will not have any access, Until Librarian allots you another seat.<br><br><strong>Would you send request?</strong>`;
                break;
        }

        text.innerHTML = alertMessage;

        // Style buttons
        cancelBtn.textContent = 'Cancel';
        confirmBtn.textContent = 'Yes';

        // Handle confirmation
        confirmBtn.onclick = () => {
            overlay.classList.add('hidden');
            saveTemporarySelection(seatNumber, floor, requestedShift, alertConfig);
        };

        cancelBtn.onclick = () => {
            overlay.classList.add('hidden');
        };

        overlay.classList.remove('hidden');
    }

    /**
     * Show shift selection popup for seats with hold conditions
     * UI matches: image 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
     */
    function showTemporaryPopup(seatNumber, floor, caseConfig) {
        const overlay = document.getElementById('shiftSelectOverlay');
        const titleEl = document.getElementById('shiftSelectTitle');
        const text = document.getElementById('shiftSelectText');
        const buttonsDiv = document.getElementById('shiftSelectButtons');
        const cancelBtn = document.getElementById('shiftSelectCancel');

        buttonsDiv.innerHTML = '';

        let title = '';
        let message = '';
        const buttons = [];

        switch (caseConfig.case) {
            case 4:
                // Case 4: One Available + One On Hold (image 1.1)
                title = 'Select Shift';
                message = `Choose available shift for seat ${seatNumber}:`;

                // Available shift button (primary color)
                const availShiftLabel = caseConfig.availableShift === 'morning'
                    ? 'Morning (8 AM – 2 PM)'
                    : 'Evening (2 PM – 8 PM)';
                buttons.push({
                    label: availShiftLabel,
                    shift: caseConfig.availableShift,
                    isTemp: false,
                    isPrimary: true
                });

                // OR separator and warning message
                buttons.push({
                    type: 'separator',
                    warningText: `⚠ ${caseConfig.holdShift.charAt(0).toUpperCase() + caseConfig.holdShift.slice(1)} Shift is Currently on hold for ${caseConfig.holdDays} days. You may request Temporary allotement Until hold ends.`
                });

                // Temporary hold shift button
                buttons.push({
                    label: `Request Temporary ${caseConfig.holdShift.charAt(0).toUpperCase() + caseConfig.holdShift.slice(1)}`,
                    shift: caseConfig.holdShift,
                    isTemp: true,
                    expiration: caseConfig.holdDays
                });

                // Temporary full button
                buttons.push({
                    label: 'Request Temporary Full',
                    shift: 'full',
                    isTemp: true,
                    expiration: caseConfig.holdDays
                });
                break;

            case 5:
                // Case 5: One Occupied + One On Hold (image 1.2)
                title = 'Seat not Available';
                message = 'All Shifts are occupied.';

                // Warning message
                buttons.push({
                    type: 'warning',
                    warningText: `⚠ But ${caseConfig.holdShift} shift is on hold for ${caseConfig.holdDays} days. You may request temporary allotment until hold ends.`
                });

                // Single temporary button
                buttons.push({
                    label: 'Request Temporary Seat',
                    shift: caseConfig.holdShift,
                    isTemp: true,
                    expiration: caseConfig.holdDays
                });
                break;

            case 6:
                // Case 6A: Both On Hold - Different Students (image 1.3)
                title = 'Only Temporary Available';
                message = `On Seat "${seatNumber}" morning shift is on hold for ${caseConfig.morningHoldDays} days & evening shift is on hold for ${caseConfig.eveningHoldDays} days. You may request a shift temporary allotment until hold ends.`;

                buttons.push({
                    label: 'Temporary Morning (8 AM - 2 PM)',
                    shift: 'morning',
                    isTemp: true,
                    expiration: caseConfig.morningHoldDays
                });
                buttons.push({
                    label: 'Temporary Evening (2 PM - 8 PM)',
                    shift: 'evening',
                    isTemp: true,
                    expiration: caseConfig.eveningHoldDays
                });
                buttons.push({
                    label: 'Temporary full day',
                    shift: 'full',
                    isTemp: true,
                    expiration: Math.min(caseConfig.morningHoldDays, caseConfig.eveningHoldDays)
                });
                break;

            case 'case6b':
                // Case 6B: Both On Hold + One Already Temporary Allotted (image 1.5)
                title = 'Only Temporary Available';
                message = `On Seat "${seatNumber}" ${caseConfig.availableShift} Shift is on hold for ${caseConfig.holdDays} days, you may request this Shift for Temporary allotement until hold ends.`;

                buttons.push({
                    label: `Temporary ${caseConfig.availableShift.charAt(0).toUpperCase() + caseConfig.availableShift.slice(1)}`,
                    shift: caseConfig.availableShift,
                    isTemp: true,
                    expiration: caseConfig.holdDays
                });
                break;

            case 7:
                // Case 7A: Full Day On Hold (image 1.4)
                title = 'Only Temporary Available';
                message = `Seat "${seatNumber}" is on full day hold for ${caseConfig.holdDays} days. You may request any shift temporary allotment until hold ends.`;

                buttons.push({
                    label: 'Temporary Morning (8AM-2PM)',
                    shift: 'morning',
                    isTemp: true,
                    expiration: caseConfig.holdDays
                });
                buttons.push({
                    label: 'Temporary Evening (2PM-8PM)',
                    shift: 'evening',
                    isTemp: true,
                    expiration: caseConfig.holdDays
                });
                buttons.push({
                    label: 'Temporary full day',
                    shift: 'full',
                    isTemp: true,
                    expiration: caseConfig.holdDays
                });
                break;

            case 'case7b':
                // Case 7B: Full Day On Hold + One Shift Temporary Allotted (image 1.6)
                title = 'Only Temporary Available';
                message = `Seat "${seatNumber}" is currently on hold for ${caseConfig.holdDays} days you may request this Shift for Temporary allotement until hold ends.`;

                buttons.push({
                    label: `Temporary ${caseConfig.availableShift.charAt(0).toUpperCase() + caseConfig.availableShift.slice(1)}`,
                    shift: caseConfig.availableShift,
                    isTemp: true,
                    expiration: caseConfig.holdDays
                });
                break;
        }

        // Set title
        if (titleEl) {
            titleEl.textContent = title;
        }

        // Set message
        text.innerHTML = message;

        // Create dynamic buttons
        buttons.forEach(btn => {
            if (btn.type === 'separator') {
                // OR separator with warning text
                const separatorDiv = document.createElement('div');
                separatorDiv.className = 'shift-popup-separator';
                separatorDiv.innerHTML = `
                    <div class="separator-line">OR</div>
                    <div class="separator-warning">${btn.warningText}</div>
                `;
                buttonsDiv.appendChild(separatorDiv);
            } else if (btn.type === 'warning') {
                // Warning text only
                const warningDiv = document.createElement('div');
                warningDiv.className = 'shift-popup-warning';
                warningDiv.innerHTML = btn.warningText;
                buttonsDiv.appendChild(warningDiv);
            } else {
                // Regular button
                const buttonEl = document.createElement('button');
                buttonEl.className = btn.isPrimary ? 'btn btn-primary shift-btn' : 'btn btn-primary shift-btn-temp';
                buttonEl.innerText = btn.label;

                buttonEl.onclick = () => {
                    overlay.classList.add('hidden');

                    // For temporary requests, show confirmation alert first
                    if (btn.isTemp) {
                        // GUARD: Already-admitted students cannot request temporary allotment.
                        // They may still select available (non-held) shifts freely.
                        const isExistingStudent = registrationTypeSelect && registrationTypeSelect.value === 'False';
                        if (isExistingStudent) {
                            showAlreadyAdmittedPopup();
                            return;
                        }

                        const alertConfig = {
                            case: caseConfig.case,
                            holdDays: btn.expiration || caseConfig.holdDays,
                            holdShift: caseConfig.holdShift,
                            availableShift: caseConfig.availableShift,
                            morningHoldDays: caseConfig.morningHoldDays,
                            eveningHoldDays: caseConfig.eveningHoldDays
                        };
                        showConfirmationAlert(seatNumber, floor, btn.shift, alertConfig);
                    } else {
                        // For regular confirmations, proceed directly with seat selection
                        const wrapper = (floor === 'Ground Floor') ? groundFloorWrapper : firstFloorWrapper;
                        const seatEl = wrapper?.querySelector(`.seat[data-seat-id="${seatNumber}"]`);
                        if (seatEl) {
                            selectSeatWithShift(seatEl, btn.shift);
                        }
                    }
                };

                buttonsDiv.appendChild(buttonEl);
            }
        });

        cancelBtn.onclick = () => overlay.classList.add('hidden');
        overlay.classList.remove('hidden');
    }

    /**
     * Show popup informing already-admitted students they cannot request temporary allotment.
     * Only new (non-admitted) students may request temporary seats on a held seat.
     */
    function showAlreadyAdmittedPopup() {
        const overlay = document.getElementById('alreadyAdmittedOverlay');
        if (!overlay) return;

        const okBtn = document.getElementById('alreadyAdmittedOk');
        const backBtn = document.getElementById('alreadyAdmittedBack');

        const close = () => overlay.classList.add('hidden');

        if (okBtn) okBtn.onclick = close;
        if (backBtn) backBtn.onclick = close;

        overlay.classList.remove('hidden');
    }

    // --- Seat Click Handling ---
    function onSeatClick(event) {
        const seatEl = event.target.closest('.seat');

        // Basic validation
        if (!seatEl || !seatEl.dataset.seatId || seatEl.classList.contains('empty-space') || seatEl.classList.contains('special')) {
            return;
        }

        // Retrieve the full seat data we stored during updateLayout
        let seatInfo = null;
        if (seatEl.dataset.info) {
            try {
                seatInfo = JSON.parse(seatEl.dataset.info);
            } catch (e) {
                console.error("JSON parse error", e);
            }
        }

        // --- LOCKED SEAT GUARD ---
        const isLockedSeat = seatEl.classList.contains('locked') || seatEl.dataset.locked === 'true' || (seatInfo && (seatInfo.is_locked || seatInfo.locked_shifts === 'full'));
        const clickedHalf = event.target.closest('.seat-half');
        const isLockedHalf = clickedHalf && (clickedHalf.classList.contains('locked') || clickedHalf.dataset.locked === 'true');
        
        let clickedShiftLocked = false;
        if (seatInfo && seatInfo.locked_shifts) {
            const lockedArr = seatInfo.locked_shifts.split(',');
            if (clickedHalf) {
                if (clickedHalf.classList.contains('seat-morning') && lockedArr.includes('morning')) clickedShiftLocked = true;
                if (clickedHalf.classList.contains('seat-evening') && lockedArr.includes('evening')) clickedShiftLocked = true;
            }
            if (lockedArr.includes('full')) clickedShiftLocked = true;
        }

        if (isLockedSeat || isLockedHalf || clickedShiftLocked) {
            event.preventDefault();
            event.stopPropagation();
            showStyledPopup({
                title: '🔒 Seat Locked by Librarian',
                message: 'This seat/shift is locked by the Librarian. You cannot select or pick this seat until it is unlocked by the Librarian.',
                type: 'error'
            });
            return false;
        }


        // Removed restriction preventing multiple students from requesting the same temporary shift,
        // allowing teachers to choose from multiple competing requests.

        const seatNumber = parseInt(seatEl.dataset.seatId, 10);
        const floorInput = floorRadioContainer.querySelector('input[name="floor_radio"]:checked');
        const currentFloor = floorInput ? floorInput.value : '';

        // -----------------------------------------------------------
        // STRICT DEFINITION: SHIFT SEAT = Ground Floor AND 40-53
        // -----------------------------------------------------------
        const isShiftSeat = (currentFloor === 'Ground Floor' && seatNumber >= 40 && seatNumber <= 53);


        // ============================================================
        // BRANCH 1: SHIFT SEATS (Ground 40-53)
        // ============================================================
        if (isShiftSeat) {

            // If for some reason seatInfo thinks it's NOT shift enabled, rely on our strict rule
            // but we need the occupancy data from seatInfo.

            const amTaken = seatInfo ? seatInfo.morning_taken : false;
            const pmTaken = seatInfo ? seatInfo.evening_taken : false;
            const fullTaken = seatInfo ? seatInfo.full_day_taken : false;

            const amHoldDays = seatInfo ? (seatInfo.morning_hold_remaining_days || 0) : 0;
            const pmHoldDays = seatInfo ? (seatInfo.evening_hold_remaining_days || 0) : 0;
            const fullHoldDays = seatInfo ? (seatInfo.full_day_hold_remaining_days || 0) : 0;

            // Only consider it a valid hold if days > 0
            const amHold = (seatInfo && seatInfo.morning_hold);
            const pmHold = (seatInfo && seatInfo.evening_hold);
            const fullHold = (seatInfo && seatInfo.full_day_hold);
            const amTempAllotted = seatInfo ? seatInfo.morning_temp_allotted : false;
            const pmTempAllotted = seatInfo ? seatInfo.evening_temp_allotted : false;
            const hasAnyHold = amHold || pmHold || fullHold;

            // --- A. HANDLE HOLD / PARTIAL REQUEST FOR SHIFT SEATS (CASES 4-7B) ---
            if (seatInfo && hasAnyHold) {
                // If BOTH are temp allotted, it's fully occupied, don't show hold popups
                if (amTempAllotted && pmTempAllotted) {
                    // Proceed to full occupancy check below
                }
                // ====================================
                // CASE 7A / 7B: Full Day On Hold
                // ====================================
                else if (fullHold) {
                    if (amTempAllotted || pmTempAllotted) {
                        const availableShift = amTempAllotted ? 'evening' : 'morning';
                        showTemporaryPopup(seatNumber, currentFloor, {
                            case: 'case7b',
                            availableShift: availableShift,
                            holdDays: fullHoldDays,
                            seatInfo: seatInfo
                        });
                        return;
                    }

                    showTemporaryPopup(seatNumber, currentFloor, {
                        case: 7,
                        holdDays: fullHoldDays,
                        seatInfo: seatInfo
                    });
                    return;
                }

                // ====================================
                // CASE 6A / 6B: Both Shifts On Hold
                // ====================================
                else if (amHold && pmHold) {
                    if (amTempAllotted || pmTempAllotted) {
                        const availableShift = amTempAllotted ? 'evening' : 'morning';
                        const holdDays = amTempAllotted ? pmHoldDays : amHoldDays;
                        showTemporaryPopup(seatNumber, currentFloor, {
                            case: 'case6b',
                            availableShift: availableShift,
                            holdDays: holdDays,
                            seatInfo: seatInfo
                        });
                        return;
                    }

                    const sameHoldOwner = seatInfo.morning_hold_student_id && seatInfo.evening_hold_student_id
                        ? seatInfo.morning_hold_student_id === seatInfo.evening_hold_student_id
                        : false;

                    // Allow the full 3-option popup whether or not owners match.
                    showTemporaryPopup(seatNumber, currentFloor, {
                        case: 6,
                        morningHoldDays: amHoldDays,
                        eveningHoldDays: pmHoldDays,
                        seatInfo: seatInfo,
                        sameHoldOwner: sameHoldOwner
                    });
                    return;
                }

                // ====================================
                // CASE 4: One Available + One On Hold
                // ====================================
                else if (amHold && !amTempAllotted && !pmHold && !pmTaken) {
                    showTemporaryPopup(seatNumber, currentFloor, {
                        case: 4,
                        availableShift: 'evening',
                        holdShift: 'morning',
                        holdDays: amHoldDays,
                        seatInfo: seatInfo
                    });
                    return;
                }

                else if (pmHold && !pmTempAllotted && !amHold && !amTaken) {
                    showTemporaryPopup(seatNumber, currentFloor, {
                        case: 4,
                        availableShift: 'morning',
                        holdShift: 'evening',
                        holdDays: pmHoldDays,
                        seatInfo: seatInfo
                    });
                    return;
                }

                // ====================================
                // CASE 5: One Occupied + One On Hold
                // ====================================
                else if (amHold && !amTempAllotted && pmTaken && !pmHold) {
                    showTemporaryPopup(seatNumber, currentFloor, {
                        case: 5,
                        holdShift: 'morning',
                        holdDays: amHoldDays,
                        seatInfo: seatInfo
                    });
                    return;
                }

                else if (pmHold && !pmTempAllotted && amTaken && !amHold) {
                    showTemporaryPopup(seatNumber, currentFloor, {
                        case: 5,
                        holdShift: 'evening',
                        holdDays: pmHoldDays,
                        seatInfo: seatInfo
                    });
                    return;
                }
            }

            // --- B. HANDLE FULL OCCUPANCY ---
            const isFullyOccupied = seatInfo && (
                fullTaken || (amTaken && pmTaken)
            );

            // If not fully occupied, show shift selection
            if (!isFullyOccupied) {

                // Check locked shifts
                const lockedArr = seatInfo ? (seatInfo.locked_shifts || '').split(',').filter(Boolean) : [];
                const isFullyLocked = seatInfo && (seatInfo.is_locked || lockedArr.includes('full'));
                const amLocked = isFullyLocked || lockedArr.includes('morning');
                const pmLocked = isFullyLocked || lockedArr.includes('evening');

                // If all available shifts are locked, show locked popup
                const amAvail = !amTaken && !amLocked;
                const pmAvail = !pmTaken && !pmLocked;
                if (!amAvail && !pmAvail) {
                    showStyledPopup({
                        title: '🔒 Seat Locked by Librarian',
                        message: 'This seat/shift is locked by the Librarian. You cannot select or pick this seat until it is unlocked by the Librarian.',
                        type: 'error'
                    });
                    return;
                }

                const overlay = document.getElementById('shiftSelectOverlay');
                const text = document.getElementById('shiftSelectText');
                const buttonsDiv = document.getElementById('shiftSelectButtons');
                const cancelBtn = document.getElementById('shiftSelectCancel');

                // Reset
                buttonsDiv.innerHTML = '';
                text.innerText = `Choose available shift for Seat ${seatNumber}:`;

                // Helper to add button
                function addShiftButton(label, shiftValue) {
                    const btn = document.createElement('button');
                    btn.className = 'btn btn-primary';
                    btn.style.marginRight = '8px';
                    btn.innerText = label;

                    btn.onclick = () => {
                        overlay.classList.add('hidden');
                        selectSeatWithShift(seatEl, shiftValue);
                    };

                    buttonsDiv.appendChild(btn);
                }

                // Morning (only if not taken AND not locked)
                if (!amTaken && !amLocked) {
                    addShiftButton('Morning (8 AM – 2 PM)', 'morning');
                }

                // Evening (only if not taken AND not locked)
                if (!pmTaken && !pmLocked) {
                    addShiftButton('Evening (2 PM – 8 PM)', 'evening');
                }

                // Full Day only if BOTH free AND NEITHER locked
                if (!amTaken && !pmTaken && !amLocked && !pmLocked) {
                    addShiftButton('Full Day (8 AM – 8 PM)', 'full');
                }

                cancelBtn.onclick = () => {
                    overlay.classList.add('hidden');
                };

                overlay.classList.remove('hidden');
                return;
            } else {
                // If the shift seat is Fully Occupied (even if via temp tenants over holds), we MUST not fall through 
                // to Branch 2's generic `on_hold` logic because we cannot offer temporary allotments on fully occupied seats.
                const overlay = document.getElementById('seatInterestOverlay');
                const text = document.getElementById('seatInterestText');
                const confirmBtn = document.getElementById('seatInterestConfirm');
                const cancelBtn = document.getElementById('seatInterestCancel');

                text.innerText = `Seat ${seatNumber} is currently fully occupied.\nWould you like an email alert when it becomes available?`;
                confirmBtn.textContent = 'Yes, Notify Me';

                overlay.classList.remove('hidden');

                confirmBtn.onclick = () => {
                    sendSeatInterest(seatNumber, currentFloor);
                    overlay.classList.add('hidden');
                };

                cancelBtn.onclick = () => {
                    overlay.classList.add('hidden');
                };
                return;
            }
        }

        // ============================================================
        // BRANCH 2: STANDARD SEATS & FALLBACKS
        // ============================================================

        const status = seatEl.dataset.status;

        // -------- NORMAL SEAT (NON-SHIFT) HOLD → PARTIAL REQUEST --------
        // For seats 1-39 on Ground Floor and ALL seats on 1st Floor
        // UI matches: image 7c20a5 (Seat is Occupied But on hold)
        if (status === 'on_hold') {
            const holdDays = seatInfo?.remaining_days || 0;

            // Show the "Seat is Occupied But on hold" popup using shiftSelectOverlay
            const overlay = document.getElementById('shiftSelectOverlay');
            const titleEl = document.getElementById('shiftSelectTitle');
            const text = document.getElementById('shiftSelectText');
            const buttonsDiv = document.getElementById('shiftSelectButtons');
            const cancelBtn = document.getElementById('shiftSelectCancel');

            // Set title as per image 7c20a5
            if (titleEl) {
                titleEl.textContent = 'Seat is Occupied But on hold';
            }

            // Set message with warning icon
            text.innerHTML = `⚠ Seat ${seatNumber} is currently on hold for <strong>${holdDays}</strong> days. You may request temporary allotment until hold ends.`;

            // Clear and add button
            buttonsDiv.innerHTML = '';

            const requestBtn = document.createElement('button');
            requestBtn.className = 'btn btn-primary shift-btn-temp';
            requestBtn.textContent = 'Request Temporary Seat';
            requestBtn.onclick = () => {
                overlay.classList.add('hidden');

                // GUARD: Already-admitted students cannot request temporary allotment.
                const isExistingStudent = registrationTypeSelect && registrationTypeSelect.value === 'False';
                if (isExistingStudent) {
                    showAlreadyAdmittedPopup();
                    return;
                }

                // Show confirmation alert (image 51cd20)
                const alertConfig = {
                    case: 'normal-hold',
                    holdDays: holdDays,
                    holdShift: 'full'
                };
                showConfirmationAlert(seatNumber, currentFloor, 'full', alertConfig);
            };
            buttonsDiv.appendChild(requestBtn);

            cancelBtn.onclick = () => overlay.classList.add('hidden');
            overlay.classList.remove('hidden');
            return;
        }

        // If Occupied/Partial/HoldPartial -> Show "Notify Me" Overlay
        if (status === 'occupied' || status === 'partial' || status === 'hold_partial') {
            const overlay = document.getElementById('seatInterestOverlay');
            const text = document.getElementById('seatInterestText');
            const confirmBtn = document.getElementById('seatInterestConfirm');
            const cancelBtn = document.getElementById('seatInterestCancel');

            text.innerText = `Seat ${seatNumber} is currently in use.\nWould you like an email alert when it becomes available?`;

            // Fix confirm button text in case it was changed by hold logic previously
            confirmBtn.textContent = 'Yes, Notify Me';

            overlay.classList.remove('hidden');

            confirmBtn.onclick = () => {
                sendSeatInterest(seatNumber, currentFloor);
                overlay.classList.add('hidden');
            };

            cancelBtn.onclick = () => {
                overlay.classList.add('hidden');
            };
            return;
        }

        // -------------------------------------------
        // AVAILABLE SEAT SELECTION (FORCE FULL DAY)
        // -------------------------------------------

        clearAllSelections();
        // Since we are not in shift branch, force 'full'
        selectSeatWithShift(seatEl, 'full');
    }

    // Helper to handle selection visuals and hidden input
    function selectSeatWithShift(seatEl, shiftValue) {

        clearAllSelections();

        // Update Pending Selection (Normal)
        const floor = floorRadioContainer.querySelector('input[name="floor_radio"]:checked')?.value || 'Ground Floor';
        pendingSelection = {
            seat: seatEl.dataset.seatId,
            floor: floor,
            shift: shiftValue,
            isTemp: false,
            holdDays: 0
        };
        console.log('✅ Normal selection pending:', pendingSelection);

        const seatInfo = seatEl.dataset.info ? JSON.parse(seatEl.dataset.info) : null;

        // -------- SHIFT SEATS --------
        if (seatInfo && seatInfo.is_shift_enabled) {
            const labelEl = seatEl.querySelector('.seat-label');

            if (shiftValue === 'morning') {
                seatEl.classList.add('selected-morning');
                
                // 1. Morning Label (Top): Set to 'Selected'
                let morningLabel = seatEl.querySelector('.seat-morning-label');
                if (!morningLabel) {
                    morningLabel = document.createElement('span');
                    morningLabel.className = 'seat-morning-label dynamic-label';
                    seatEl.appendChild(morningLabel);
                } else {
                    if (!morningLabel.dataset.originalText) morningLabel.dataset.originalText = morningLabel.textContent;
                }
                morningLabel.textContent = 'Selected';

                // 2. Evening Label (Bottom): Ensure present so shift seat layout height stays balanced
                let eveningLabel = seatEl.querySelector('.seat-evening-label');
                if (!eveningLabel) {
                    eveningLabel = document.createElement('span');
                    eveningLabel.className = 'seat-evening-label dynamic-label';
                    eveningLabel.textContent = 'Available';
                    seatEl.appendChild(eveningLabel);
                }

                if (labelEl) labelEl.style.display = 'none';
            }
            else if (shiftValue === 'evening') {
                seatEl.classList.add('selected-evening');
                
                // 1. Evening Label (Bottom): Set to 'Selected'
                let eveningLabel = seatEl.querySelector('.seat-evening-label');
                if (!eveningLabel) {
                    eveningLabel = document.createElement('span');
                    eveningLabel.className = 'seat-evening-label dynamic-label';
                    seatEl.appendChild(eveningLabel);
                } else {
                    if (!eveningLabel.dataset.originalText) eveningLabel.dataset.originalText = eveningLabel.textContent;
                }
                eveningLabel.textContent = 'Selected';

                // 2. Morning Label (Top): Ensure present so shift seat layout height stays balanced
                let morningLabel = seatEl.querySelector('.seat-morning-label');
                if (!morningLabel) {
                    morningLabel = document.createElement('span');
                    morningLabel.className = 'seat-morning-label dynamic-label';
                    morningLabel.textContent = 'Available';
                    seatEl.appendChild(morningLabel);
                }

                if (labelEl) labelEl.style.display = 'none';
            }
            else {
                seatEl.classList.add('selected-full');
                // For full day: update the main label
                if (labelEl) {
                    if (!labelEl.dataset.originalText) labelEl.dataset.originalText = labelEl.textContent;
                    labelEl.textContent = 'Selected';
                }
            }

        }
        // -------- NORMAL SEATS --------
        else {
            seatEl.classList.add('selected');
            // Update label to "Selected"
            const labelEl = seatEl.querySelector('.seat-label');
            if (labelEl) {
                if (!labelEl.dataset.originalText) labelEl.dataset.originalText = labelEl.textContent;
                labelEl.textContent = 'Selected';
            }
        }

        currentlySelectedSeat = seatEl;
        confirmSeatBtn.disabled = false;

        // Get floor for prefix
        // const floor = ... (already defined above)
        const floorPrefix = floor === 'Ground Floor' ? 'G' : 'F';

        let label = `Confirm Seat ${floorPrefix} ${seatEl.dataset.seatId}`;
        if (shiftValue !== 'full') {
            const shiftCapitalized = shiftValue.charAt(0).toUpperCase() + shiftValue.slice(1);
            label += ` (${shiftCapitalized})`;
        }
        confirmSeatBtn.textContent = label;
        confirmSeatBtn.disabled = false;

        // Reset to default blue style for normal selection
        confirmSeatBtn.style.background = '#667eea';
        confirmSeatBtn.style.borderColor = '#667eea';


    }


    // Helper to show/hide ground floor seat notice
    function toggleShiftSeatNotice(floor) {
        const notice = document.getElementById('shiftSeatNotice');
        if (!notice) return;
        notice.style.display = (floor === 'Ground Floor') ? 'block' : 'none';
    }

    toggleShiftSeatNotice(
        floorRadioContainer.querySelector('input[name="floor_radio"]:checked')?.value
    );


    // --- 5. Confirmation Logic ---
    function confirmSelection() {
        if (!pendingSelection) {
            showStyledPopup({ title: 'No Seat Selected', message: 'Please select a seat from the layout before confirming.', type: 'error' });
            return;
        }

        const { seat, floor, shift, isTemp, holdDays } = pendingSelection;

        // INTELLIGENT GUARD: Block confirming temporary allotment if user is "Already Admitted"
        const isNewStudent = registrationTypeSelect && registrationTypeSelect.value === 'True';
        if (isTemp && !isNewStudent) {
            showStyledPopup({
                title: 'Cannot Use Temporary Allotment',
                message: 'You are registered as an <strong>Already Admitted Student</strong>.<br><br>Temporary allotments are only available for <strong>new students</strong>. Please select your own occupied seat instead.',
                type: 'error'
            });
            return;
        }

        // 1. Commit to hidden inputs
        if (hiddenSeatInput) hiddenSeatInput.value = seat;
        if (hiddenFloorInput) hiddenFloorInput.value = floor;

        let shiftInput = document.getElementById('id_shift_preference');
        if (!shiftInput) {
            shiftInput = document.createElement('input');
            shiftInput.type = 'hidden';
            shiftInput.name = 'shift_preference';
            shiftInput.id = 'id_shift_preference';
            admissionForm.appendChild(shiftInput);
        }
        shiftInput.value = shift;

        let partialInput = document.getElementById('id_is_temporary_request');
        if (!partialInput) {
            partialInput = document.createElement('input');
            partialInput.type = 'hidden';
            partialInput.name = 'is_temporary_request';
            partialInput.id = 'id_is_temporary_request';
            admissionForm.appendChild(partialInput);
        }
        partialInput.value = isTemp ? 'true' : 'false';

        let daysInput = document.getElementById('id_temp_hold_days');
        if (!daysInput) {
            daysInput = document.createElement('input');
            daysInput.type = 'hidden';
            daysInput.name = 'temp_hold_days';
            daysInput.id = 'id_temp_hold_days';
            admissionForm.appendChild(daysInput);
        }
        daysInput.value = holdDays;


        // 2. Update Main Button Text
        const floorPrefix = floor === 'Ground Floor' ? 'G' : 'F';
        let btnText = `Seat ${floorPrefix} ${seat}`;

        if (isTemp) {
            // Temporary selection format
            if (shift === 'full') {
                btnText += ` (Temp. - Full Day) Selected`;
            } else {
                const shiftCapitalized = shift.charAt(0).toUpperCase() + shift.slice(1);
                btnText += ` (Temp. - ${shiftCapitalized}) Selected`;
            }
            openModalButton.style.background = '#ff9abe';
            openModalButton.style.borderColor = '#ff7aa5';
        } else {
            // Permanent selection format
            if (shift && shift !== 'full') {
                const shiftCapitalized = shift.charAt(0).toUpperCase() + shift.slice(1);
                btnText += ` (${shiftCapitalized}) Selected`;
            } else {
                btnText += ` Selected`;
            }
            openModalButton.style.background = '#2ecc71';
            openModalButton.style.borderColor = '#2ecc71';
        }

        openModalButton.textContent = btnText;

        // 3. Update Preview Text (restoreSelectionState does this but we can do it here too to be instant)
        const preview = document.getElementById('selectedSeatPreview');
        if (preview) {
            let text = `Seat ${seat} (${floor}) selected`;
            if (isTemp) {
                const shiftCap = shift === 'full' ? 'Full Day' : shift.charAt(0).toUpperCase() + shift.slice(1);
                text += ` - Temporary ${shiftCap}`;
                preview.style.color = '#e84393';
            } else {
                if (shift && shift !== 'full') {
                    const shiftCap = shift.charAt(0).toUpperCase() + shift.slice(1);
                    text += ` - ${shiftCap}`;
                }
                preview.style.color = '';
            }
            preview.textContent = text;
        }

        closeSeatModal();
    }

    // --- 6. Initial Setup and Event Listeners ---
    createModalTriggerButton();

    if (serviceSelect) serviceSelect.addEventListener('change', updateButtonVisibilityAndText);
    if (registrationTypeSelect) {
        registrationTypeSelect.addEventListener('change', () => {
            updateButtonVisibilityAndText();
            onRegistrationTypeChange();
        });
    }

    updateButtonVisibilityAndText();

    if (modalOverlay) modalOverlay.addEventListener('click', closeSeatModal);
    if (modalCloseBtn) modalCloseBtn.addEventListener('click', closeSeatModal);
    if (confirmSeatBtn) confirmSeatBtn.addEventListener('click', confirmSelection);

    if (modalBody) modalBody.addEventListener('scroll', handleModalScroll);

    if (groundFloorWrapper) groundFloorWrapper.addEventListener('click', onSeatClick);
    if (firstFloorWrapper) firstFloorWrapper.addEventListener('click', onSeatClick);

    if (modalContainer) modalContainer.addEventListener('click', (e) => e.stopPropagation());

    floorRadioContainer.querySelectorAll('input[name="floor_radio"]').forEach(radio => {
        radio.addEventListener('change', () => {
            // Only clear if the floor actually changed from what was hidden
            if (hiddenFloorInput.value && hiddenFloorInput.value !== radio.value) {
                hiddenSeatInput.value = '';

                // Clear shift and temp inputs too
                const shiftInput = document.getElementById('id_shift_preference');
                if (shiftInput) shiftInput.value = 'full';
                const tempInput = document.getElementById('id_is_temporary_request');
                if (tempInput) tempInput.value = 'false';

                const preview = document.getElementById('selectedSeatPreview');
                if (preview) {
                    preview.textContent = 'No seat selected';
                    preview.style.color = '';
                }
            }

            if (radio.checked) {
                hiddenFloorInput.value = radio.value;
            }

            const isNewStudent = registrationTypeSelect.value === 'True';
            openModalButton.textContent = isNewStudent ? 'Select Seat Preference' : 'Choose/Change Your Occupied Seat';
            openModalButton.style.background = '';
            openModalButton.style.borderColor = '';

            toggleShiftSeatNotice(radio.value);

        });
    });

    // --- 7. Persistence Logic: Restore Selection on Page Load ---
    function restoreSelectionState() {
        const seatVal = hiddenSeatInput.value;
        const floorVal = hiddenFloorInput.value;

        if (!seatVal || !floorVal) return;

        // Ensure the correct radio is checked
        const radio = floorRadioContainer.querySelector(`input[value="${floorVal}"]`);
        if (radio) radio.checked = true;

        // Get other hidden values
        const shiftInput = document.getElementById('id_shift_preference');
        const shiftValue = shiftInput ? shiftInput.value : 'full';
        const tempInput = document.getElementById('id_is_temporary_request');
        const isTemp = tempInput ? tempInput.value === 'true' : false;

        // Construct Button Text
        const floorPrefix = floorVal === 'Ground Floor' ? 'G' : 'F';
        let btnText = `Seat ${floorPrefix} ${seatVal}`;

        if (isTemp) {
            if (shiftValue === 'full') {
                btnText += ` (Temp. - Full Day) Selected`;
            } else {
                const shiftCapitalized = shiftValue.charAt(0).toUpperCase() + shiftValue.slice(1);
                btnText += ` (Temp. - ${shiftCapitalized}) Selected`;
            }
            openModalButton.style.background = '#ff9abe'; // Pink for temp
            openModalButton.style.borderColor = '#ff7aa5';
        } else {
            if (shiftValue && shiftValue !== 'full') {
                const shiftCapitalized = shiftValue.charAt(0).toUpperCase() + shiftValue.slice(1);
                btnText += ` (${shiftCapitalized}) Selected`;
            } else {
                btnText += ` Selected`;
            }
            openModalButton.style.background = '#2ecc71'; // Green for normal
            openModalButton.style.borderColor = '#2ecc71';
        }

        openModalButton.textContent = btnText;
        // Make sure button is visible
        updateButtonVisibilityAndText();
        // Force the text we just set (updateButtonVisibilityAndText might have reset it)
        openModalButton.textContent = btnText;


        // Update Preview Text
        const preview = document.getElementById('selectedSeatPreview');
        if (preview) {
            let text = `Seat ${seatVal} (${floorVal}) selected`;
            if (isTemp) {
                const shiftCapitalized = shiftValue === 'full' ? 'Full Day' : shiftValue.charAt(0).toUpperCase() + shiftValue.slice(1);
                text += ` - Temporary ${shiftCapitalized}`;
                preview.style.color = '#e84393';
            } else {
                if (shiftValue && shiftValue !== 'full') {
                    const shiftCapitalized = shiftValue.charAt(0).toUpperCase() + shiftValue.slice(1);
                    text += ` - ${shiftCapitalized}`;
                }
                preview.style.color = '';
            }
            preview.textContent = text;
        }
    }

    // Call restore immediately
    restoreSelectionState();

});
