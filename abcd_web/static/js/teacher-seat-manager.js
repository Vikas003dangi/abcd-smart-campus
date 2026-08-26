
// --- XSS Prevention: HTML Escape Utility ---
function escapeHTML(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

document.addEventListener('DOMContentLoaded', () => {
  // --- Quick safety checks ---
  if (typeof CSRF_TOKEN === 'undefined' ||
    typeof API_GET_SEATS_URL === 'undefined' ||
    typeof API_GET_STUDENTS_URL === 'undefined' ||
    typeof STUDENT_DETAILS_URL_BASE === 'undefined' ||
    typeof API_SEAT_ACTION_URL === 'undefined') {
    console.warn("Warning: one or more template constants are missing.");
  }

  // --- DOM refs ---
  const floorSelector = document.getElementById('floorSelector');
  const loadingMessage = document.getElementById('loadingMessage');
  const groundFloorWrapper = document.getElementById('ground-floor-wrapper');
  const firstFloorWrapper = document.getElementById('first-floor-wrapper');

  // --- PREMIUM CUSTOM SELECT LOGIC ---
  function initCustomSelects() {
    document.querySelectorAll('select.form-control').forEach(select => {
      if (select.dataset.customized) return;
      select.dataset.customized = "true";
      select.style.display = 'none';

      const wrapper = document.createElement('div');
      wrapper.className = 'abcd-select-wrapper';

      const trigger = document.createElement('div');
      trigger.className = 'abcd-select-trigger';
      // Find currently selected option or first option
      const selectedOption = select.options[select.selectedIndex] || select.options[0];
      trigger.innerHTML = `<span>${selectedOption ? selectedOption.text : 'Select...'}</span><i class='bx bx-chevron-down'></i>`;

      const dropdown = document.createElement('div');
      dropdown.className = 'abcd-select-dropdown';

      Array.from(select.options).forEach(option => {
        const optDiv = document.createElement('div');
        optDiv.className = 'abcd-select-option';
        if (option.selected) optDiv.classList.add('selected');
        optDiv.textContent = option.text;
        optDiv.dataset.value = option.value;

        optDiv.addEventListener('click', () => {
          select.value = option.value;
          trigger.querySelector('span').textContent = option.text;
          dropdown.querySelectorAll('.abcd-select-option').forEach(o => o.classList.remove('selected'));
          optDiv.classList.add('selected');
          wrapper.classList.remove('open');

          // Trigger native change event
          select.dispatchEvent(new Event('change'));
        });
        dropdown.appendChild(optDiv);
      });

      trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = wrapper.classList.contains('open');
        document.querySelectorAll('.abcd-select-wrapper').forEach(w => w.classList.remove('open'));
        if (!isOpen) wrapper.classList.add('open');
      });

      wrapper.appendChild(trigger);
      wrapper.appendChild(dropdown);
      select.parentNode.insertBefore(wrapper, select.nextSibling);
    });

    // Close all dropdowns when clicking outside
    document.addEventListener('click', () => {
      document.querySelectorAll('.abcd-select-wrapper').forEach(w => w.classList.remove('open'));
    });
  }

  /**
   * Helper to refresh the custom select UI when the underlying select changes
   * @param {HTMLSelectElement} select 
   */
  function refreshCustomSelect(select) {
    if (!select) return;
    if (typeof window.enhanceSelectElements === 'function') {
      window.enhanceSelectElements(select);
    }
  }


  // Handle floor selector changes
  if (floorSelector) {
    floorSelector.addEventListener('change', () => {
      if (floorSelector.value) {
        loadSeatLayout(floorSelector.value);
        if (seatSearchInput) seatSearchInput.value = '';
        document.querySelectorAll('.seat').forEach(seat => {
          seat.classList.remove('search-match', 'active-match');
        });
        const seatSearchNav = document.getElementById('seatSearchNav');
        if (seatSearchNav) seatSearchNav.style.display = 'none';
      }
    });
  }

  // Sidebar Drawer Collapsible logic
  const sidebar = document.getElementById('hubSidebar');
  const sidebarToggleBtn = document.getElementById('sidebarToggleBtn');
  if (sidebar && sidebarToggleBtn) {
    sidebarToggleBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      sidebar.classList.toggle('active');
    });

    document.addEventListener('click', (e) => {
      if (window.innerWidth <= 900 && sidebar.classList.contains('active')) {
        if (e.target.closest && e.target.closest('.abcd-tour-popover, .abcd-tour-launcher, .abcd-tour-overlay, .abcd-tour-spotlight')) {
          return;
        }
        if (!sidebar.contains(e.target) && !sidebarToggleBtn.contains(e.target)) {
          sidebar.classList.remove('active');
        }
      }
    });
  }


  // HUB NAVIGATION & SEARCH
  const hubSearchWrapper = document.getElementById('hubSearchWrapper');
  const hubSearchBtn = document.getElementById('hubSearchBtn');
  const seatSearchInput = document.getElementById('seatSearchInput');

  // MODALS & OVERLAYS
  const modalOverlay = document.getElementById('admissionModalOverlay');
  const seatDetailsModal = document.getElementById('teacherPremiumSeatDetailsModal');
  const assignStudentModal = document.getElementById('teacherPremiumAssignModal');
  const holdModal = document.getElementById('teacherPremiumHoldModal');
  const conflictModal = document.getElementById('teacherPremiumConflictModal');
  
  const allModals = document.querySelectorAll('.admission-modal');
  const allCloseButtons = document.querySelectorAll('.modal-close-btn');
  const hubLayout = document.querySelector('.hub-layout');

  // Confirmation Modal
  const confirmModal = document.getElementById('teacherPremiumConfirmModal');
  const confirmModalTitle = document.getElementById('confirmModalTitle');
  const confirmModalMainText = document.getElementById('confirmModalMainText');
  const confirmModalSubText = document.getElementById('confirmModalSubText');
  const confirmModalIcon = document.getElementById('confirmModalIcon');
  const actionFinalConfirm = document.getElementById('actionFinalConfirm');
  const actionCancelConfirm = document.getElementById('actionCancelConfirm');

  // seat modal controls/buttons
  const seatDetailsTitle = document.getElementById('seatDetailsTitle');
  const seatDetailsContent = document.getElementById('seatDetailsContent');
  const actionAssignStudent = document.getElementById('actionAssignStudent');
  const actionViewStudent = document.getElementById('actionViewStudent');
  const actionMakeAvailable = document.getElementById('actionMakeAvailable');
  const actionApprovePending = document.getElementById('actionApprovePending');
  const actionRejectPending = document.getElementById('actionRejectPending');
  const actionPutOnHold = document.getElementById('actionPutOnHold');
  const actionEndHold = document.getElementById('actionEndHold');

  const holdStartDate = document.getElementById('holdStartDate');
  const holdDurationInput = document.getElementById('holdDurationInput');
  const holdConfirmBtn = document.getElementById('holdConfirmBtn');

  // assign modal controls
  const assignStudentTitle = document.getElementById('assignStudentTitle');
  const studentAssignType = document.getElementById('studentAssignType'); 
  const studentAssignSelect = document.getElementById('studentAssignSelect'); 
  const studentAssignWrap = document.getElementById('studentAssignWrap'); 
  const manualAssignDiv = document.getElementById('manualAssignDiv'); 
  const manualAssignFirstName = document.getElementById('manualAssignFirstName');
  const manualAssignLastName = document.getElementById('manualAssignLastName');
  const manualAssignUsername = document.getElementById('manualAssignUsername');
  const manualAssignPassword = document.getElementById('manualAssignPassword');
  const manualAssignMobile = document.getElementById('manualAssignMobile');
  const manualAssignWhatsapp = document.getElementById('manualAssignWhatsapp');
  const manualAssignWhatsappSame = document.getElementById('manualAssignWhatsappSame');
  const manualAssignEmail = document.getElementById('manualAssignEmail');
  const manualAssignSex = document.getElementById('manualAssignSex');
  const manualAssignDOB = document.getElementById('manualAssignDOB');
  const manualAssignPhotoInput = document.getElementById('manualAssignPhotoInput');
  const manualAssignPhotoPreview = document.getElementById('manualAssignPhotoPreview');
  const manualAssignPhotoPlaceholder = document.getElementById('manualAssignPhotoPlaceholder');
  let manualAssignPhotoBase64 = null;
  const actionConfirmAssign = document.getElementById('actionConfirmAssign');

  /**
   * Helper to format seat number based on floor
   * @param {string|number} num - Optional seat number (defaults to currentSeatData)
   * @returns {string} - e.g. "G-42" or "F-42"
   */
  function getFormattedSeatNumber(num = null) {
    const seatNum = num || (currentSeatData ? currentSeatData.seat_number : null);
    if (!seatNum) return '';
    const floor = currentSeatData ? currentSeatData.floor : (floorSelector ? floorSelector.value : '');
    const prefix = floor === 'Ground Floor' ? 'G-' : 'F-';
    return prefix + seatNum;
  }

  /**
   * Helper to show the premium confirmation modal
   */
  window.showConfirmation = function({ title, mainText, subText, iconClass = 'bx-help-circle', confirmLabel = 'Confirm', theme = 'primary' }) {
    confirmModalTitle.textContent = title || 'Confirm Action';
    confirmModalMainText.textContent = mainText || 'Are you sure?';
    confirmModalSubText.textContent = subText || 'Do you wish to continue?';
    
    // Set icon
    confirmModalIcon.innerHTML = `<i class='bx ${iconClass}'></i>`;
    
    // Set theme (gradient)
    const header = document.getElementById('confirmModalHeader');
    if (theme === 'danger') {
      header.style.background = 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)';
      confirmModalIcon.style.color = '#ef4444';
      actionFinalConfirm.className = 'btn btn-danger';
    } else if (theme === 'warning') {
      header.style.background = 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)';
      confirmModalIcon.style.color = '#f59e0b';
      actionFinalConfirm.className = 'btn btn-warning';
    } else if (theme === 'success') {
      header.style.background = 'linear-gradient(135deg, #10b981 0%, #059669 100%)';
      confirmModalIcon.style.color = '#10b981';
      actionFinalConfirm.className = 'btn btn-success';
    } else {
      header.style.background = 'linear-gradient(135deg, #6366f1 0%, #4338ca 100%)';
      confirmModalIcon.style.color = '#6366f1';
      actionFinalConfirm.className = 'btn btn-primary';
    }

    actionFinalConfirm.innerHTML = `<i class='bx bx-check'></i> ${confirmLabel}`;
    
    window.openSmallModal(confirmModal);

    return new Promise((resolve) => {
      const handleConfirm = (e) => {
        if (e) { e.preventDefault(); e.stopPropagation(); }
        if (typeof window.setButtonLoading === 'function' && actionFinalConfirm) {
          const isDanger = theme === 'danger' || confirmLabel.toLowerCase().includes('delete') || confirmLabel.toLowerCase().includes('unlock');
          window.setButtonLoading(actionFinalConfirm, true, isDanger ? 'Processing...' : 'Confirming...');
        }
        resolve(true);
      };

      const handleCancel = (e) => {
        if (e) { e.preventDefault(); e.stopPropagation(); }
        cleanup();
        closeSmallModal(confirmModal);
        resolve(false);
      };

      const cleanup = () => {
        if (actionFinalConfirm) actionFinalConfirm.onclick = null;
        if (actionCancelConfirm) actionCancelConfirm.onclick = null;
        const closeBtn = document.getElementById('closeConfirmModal');
        if (closeBtn) closeBtn.onclick = null;
      };

      if (actionFinalConfirm) actionFinalConfirm.onclick = handleConfirm;
      if (actionCancelConfirm) actionCancelConfirm.onclick = handleCancel;
      const closeBtn = document.getElementById('closeConfirmModal');
      if (closeBtn) closeBtn.onclick = handleCancel;
    });
  };


  // --- HUB SEARCH LOGIC ---
  if (hubSearchBtn && hubSearchWrapper && seatSearchInput) {
    // Floating search nav elements
    const seatSearchNav = document.getElementById('seatSearchNav');
    const seatSearchCount = document.getElementById('seatSearchCount');
    const seatSearchPrev = document.getElementById('seatSearchPrev');
    const seatSearchNext = document.getElementById('seatSearchNext');

    let matchedSeats = [];
    let matchedIndex = 0;
    let searchTimer = null;

    // Helper to switch floor cleanly
    function switchFloor(floorName) {
      if (floorSelector && floorSelector.value !== floorName) {
        floorSelector.value = floorName;
        floorSelector.dispatchEvent(new Event('change'));
        refreshCustomSelect(floorSelector);
      }
    }

    // Helper to parse English words for numbers (e.g. "forty-five" -> 45)
    function wordsToNumber(str) {
      const cleanStr = str.toLowerCase().replace(/[^a-z0-9]/g, ' ').trim();
      if (!cleanStr) return null;

      const ones = {
        'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9
      };
      const teens = {
        'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
        'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19
      };
      const tens = {
        'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 
        'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90
      };

      if (ones[cleanStr] !== undefined) return ones[cleanStr];
      if (teens[cleanStr] !== undefined) return teens[cleanStr];
      if (tens[cleanStr] !== undefined) return tens[cleanStr];

      for (const [tenWord, tenVal] of Object.entries(tens)) {
        if (cleanStr.startsWith(tenWord)) {
          const remainder = cleanStr.substring(tenWord.length).trim();
          if (remainder === '') return tenVal;
          if (ones[remainder] !== undefined) return tenVal + ones[remainder];
        }
      }

      const parts = cleanStr.split(/\s+/);
      let total = 0;
      let currentVal = 0;

      for (let i = 0; i < parts.length; i++) {
        const p = parts[i];
        if (p === 'and') continue;

        if (ones[p] !== undefined) {
          currentVal += ones[p];
        } else if (teens[p] !== undefined) {
          currentVal += teens[p];
        } else if (tens[p] !== undefined) {
          currentVal += tens[p];
        } else {
          return null;
        }
      }

      total += currentVal;
      return total > 0 ? total : null;
    }

    // Helper to clear highlights and hide popup
    function clearSeatSearchHighlights() {
      document.querySelectorAll('.seat').forEach(seat => {
        seat.classList.remove('search-match', 'active-match');
      });
      if (seatSearchNav) seatSearchNav.style.display = 'none';
      matchedSeats = [];
      matchedIndex = 0;
    }

    // Create keyword suggestions popup
    const keywordPopup = document.createElement('div');
    keywordPopup.className = 'seat-keyword-popup';
    keywordPopup.style.display = 'none';
    
    // Append to the parent container (hub-nav-right) to avoid overflow clipping
    const navRight = hubSearchWrapper.parentElement;
    if (navRight) {
      navRight.appendChild(keywordPopup);
    }

    function renderKeywordSuggestions(val) {
      const suggestions = [
        { key: '/First-floor', label: 'First Floor Layout', action: () => switchFloor('1st Floor') },
        { key: '/Ground-Floor', label: 'Ground Floor Layout', action: () => switchFloor('Ground Floor') }
      ];
      const filtered = suggestions.filter(s => s.key.toLowerCase().startsWith(val.toLowerCase()));
      if (filtered.length === 0) {
        keywordPopup.style.display = 'none';
        return;
      }
      keywordPopup.innerHTML = '';
      filtered.forEach((s, idx) => {
        const item = document.createElement('div');
        item.className = 'seat-keyword-item' + (idx === 0 ? ' active' : '');
        item.innerHTML = `<span style="font-weight:700;">${s.key}</span><span style="font-size:10px;opacity:0.7;">${s.label}</span>`;
        item.addEventListener('click', (evt) => {
          evt.stopPropagation();
          s.action();
          keywordPopup.style.display = 'none';
          seatSearchInput.value = '';
          clearSeatSearchHighlights();
        });
        keywordPopup.appendChild(item);
      });
      keywordPopup.style.display = 'block';
    }

    // Handle clicks outside dropdowns and popup
    document.addEventListener('click', (e) => {
      if (hubSearchWrapper && !hubSearchWrapper.contains(e.target) && keywordPopup && !keywordPopup.contains(e.target)) {
        keywordPopup.style.display = 'none';
      }
    });

    hubSearchBtn.addEventListener('click', () => {
      hubSearchWrapper.classList.toggle('expanded');
      const icon = hubSearchBtn.querySelector('i');
      if (hubSearchWrapper.classList.contains('expanded')) {
        seatSearchInput.focus();
        if (icon) {
          icon.className = 'bx bx-x';
        }
      } else {
        seatSearchInput.value = '';
        if (icon) {
          icon.className = 'bx bx-search';
        }
        keywordPopup.style.display = 'none';
        clearSeatSearchHighlights();
      }
    });

    // Keyboard navigation in keyword popup
    seatSearchInput.addEventListener('keydown', (e) => {
      if (keywordPopup.style.display === 'block') {
        const items = keywordPopup.querySelectorAll('.seat-keyword-item');
        let activeIdx = Array.from(items).findIndex(item => item.classList.contains('active'));
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          if (items.length > 0) {
            if (activeIdx !== -1) items[activeIdx].classList.remove('active');
            activeIdx = (activeIdx + 1) % items.length;
            items[activeIdx].classList.add('active');
          }
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          if (items.length > 0) {
            if (activeIdx !== -1) items[activeIdx].classList.remove('active');
            activeIdx = (activeIdx - 1 + items.length) % items.length;
            items[activeIdx].classList.add('active');
          }
        } else if (e.key === 'Enter' || e.key === 'Tab') {
          e.preventDefault();
          if (items.length > 0 && activeIdx !== -1) {
            items[activeIdx].click();
          }
        } else if (e.key === 'Escape') {
          e.preventDefault();
          keywordPopup.style.display = 'none';
        }
      }
    });

    function navigateMatch(direction) {
      if (matchedSeats.length === 0) return;

      matchedSeats.forEach(seat => {
        seat.classList.remove('active-match');
      });

      if (direction === 'next') {
        matchedIndex = (matchedIndex + 1) % matchedSeats.length;
      } else {
        matchedIndex = (matchedIndex - 1 + matchedSeats.length) % matchedSeats.length;
      }

      const activeSeat = matchedSeats[matchedIndex];
      if (activeSeat) {
        activeSeat.classList.add('active-match');
        activeSeat.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
      }

      if (seatSearchCount) {
        seatSearchCount.textContent = (matchedIndex + 1) + ' / ' + matchedSeats.length;
      }
    }

    if (seatSearchPrev) {
      seatSearchPrev.addEventListener('click', (e) => {
        e.stopPropagation();
        navigateMatch('prev');
      });
    }

    if (seatSearchNext) {
      seatSearchNext.addEventListener('click', (e) => {
        e.stopPropagation();
        navigateMatch('next');
      });
    }

    seatSearchInput.addEventListener('input', (e) => {
      const rawVal = e.target.value;
      const clean = rawVal.toLowerCase().trim();

      // Handoff to keyword suggestions if typing slash
      if (rawVal.startsWith('/')) {
        renderKeywordSuggestions(rawVal);
        clearSeatSearchHighlights();
        return;
      } else {
        keywordPopup.style.display = 'none';
      }

      // If empty query, reset search UI
      if (clean.length === 0) {
        clearTimeout(searchTimer);
        clearSeatSearchHighlights();
        return;
      }

      // Immediate floor layout exact word checks (case-insensitive)
      if (clean === 'first floor' || clean === 'frist floor' || clean === '1st floor' || clean === 'first' || clean === '1st') {
        clearTimeout(searchTimer);
        switchFloor('1st Floor');
        seatSearchInput.value = '';
        clearSeatSearchHighlights();
        return;
      }
      if (clean === 'ground floor' || clean === 'ground') {
        clearTimeout(searchTimer);
        switchFloor('Ground Floor');
        seatSearchInput.value = '';
        clearSeatSearchHighlights();
        return;
      }

      // Debounce the general search by 300ms
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        // Clear all previous highlight classes
        document.querySelectorAll('.seat').forEach(seat => {
          seat.classList.remove('search-match', 'active-match');
        });

        // Search ONLY on the currently selected floor
        const currentWrapperId = (floorSelector && floorSelector.value === 'Ground Floor') ? 'ground-floor-wrapper' : 'first-floor-wrapper';
        const activeFloorWrapper = document.getElementById(currentWrapperId);
        const allSeats = activeFloorWrapper ? activeFloorWrapper.querySelectorAll('.seat') : [];

        matchedSeats = [];
        matchedIndex = 0;

        // Parse single-digit seat number if applicable (e.g. "4" or "04")
        let exactSeatNum = null;
        const isDigitPattern = /^[0-9]+$/;
        if (isDigitPattern.test(clean)) {
          const numVal = parseInt(clean, 10);
          if (numVal >= 1 && numVal <= 9) {
            exactSeatNum = String(numVal);
          }
        } else {
          // Check if clean matches English number words (e.g. "forty five" or "two")
          const numVal = wordsToNumber(clean);
          if (numVal !== null) {
            exactSeatNum = String(numVal);
          }
        }

        allSeats.forEach(seat => {
          let match = false;
          const studentName = seat.getAttribute('data-student-name') || '';
          const seatId = seat.getAttribute('data-seat-id') || '';
          const seatText = (seat.querySelector('.seat-number')?.innerText || seat.innerText || '').trim();
          
          if (exactSeatNum) {
            // For single-digit seat queries, perform exact match on seatId or seat number text
            if (seatId === exactSeatNum || seatText === exactSeatNum) {
              match = true;
            }
          } else {
            // General query matching
            if (studentName.toLowerCase().includes(clean) || 
                seatId.toLowerCase() === clean || 
                seatId.toLowerCase().includes(clean) ||
                seatText.toLowerCase().includes(clean)) {
              match = true;
            }

            // Check assignments JSON
            const assignmentsStr = seat.getAttribute('data-assignments');
            if (!match && assignmentsStr) {
              try {
                const assignments = JSON.parse(assignmentsStr);
                if (assignments.some(a => a.student_name && a.student_name.toLowerCase().includes(clean))) {
                  match = true;
                }
              } catch(err) {}
            }

            // Check seat status (legend match with partial search support)
            if (!match && clean.length >= 2) {
              const seatClasses = Array.from(seat.classList).map(c => c.toLowerCase());
              
              if ('available'.includes(clean) && seatClasses.includes('available')) match = true;
              
              if (('occupied'.includes(clean) || 'shift_occupied'.includes(clean) || 'shift occupied'.includes(clean)) && 
                  (seatClasses.includes('occupied') || seatClasses.includes('shift_occupied'))) {
                match = true;
              }
              
              if ('pending'.includes(clean) && seatClasses.includes('pending')) match = true;
              
              if (('on hold'.includes(clean) || 'on_hold'.includes(clean) || 'hold'.includes(clean)) && 
                  seatClasses.includes('on_hold')) {
                match = true;
              }
              
              if ('temporary'.includes(clean) && seatClasses.includes('temporary')) match = true;

              // Locked seat & shift search support
              const isLockedSeat = seatClasses.includes('locked') || 
                                   seatClasses.includes('locked-morning') || 
                                   seatClasses.includes('locked-evening') || 
                                   seat.getAttribute('data-locked') === 'true' ||
                                   seat.querySelector('.locked, .status-locked, .seat-half.locked') !== null;

              const seatLabelsText = Array.from(seat.querySelectorAll('.seat-label, .seat-morning-label, .seat-evening-label'))
                .map(el => (el.textContent || '').toLowerCase());
              const hasLockedLabel = seatLabelsText.some(t => t.includes('locked') || t.includes('🔒') || t.includes('lock'));

              const isLockKeyword = 'locked'.includes(clean) || 
                                    'lock'.includes(clean) || 
                                    'seat locked'.includes(clean) || 
                                    'shift locked'.includes(clean) || 
                                    'locked seat'.includes(clean) || 
                                    'locked shift'.includes(clean);

              if (isLockKeyword && (isLockedSeat || hasLockedLabel)) {
                match = true;
              }
            }
          }

          if (match) {
            seat.classList.add('search-match');
            matchedSeats.push(seat);
          }
        });

        // Show search nav popup
        if (seatSearchNav) {
          seatSearchNav.style.display = 'flex';
        }

        if (matchedSeats.length === 0) {
          if (seatSearchCount) {
            seatSearchCount.textContent = 'No results';
            seatSearchCount.style.color = '#ef4444';
          }
          if (seatSearchPrev) seatSearchPrev.style.display = 'none';
          if (seatSearchNext) seatSearchNext.style.display = 'none';
        } else {
          if (seatSearchCount) {
            seatSearchCount.textContent = '1 / ' + matchedSeats.length;
            seatSearchCount.style.color = '';
          }

          // Toggle visibility of navigation arrows
          if (matchedSeats.length > 1) {
            if (seatSearchPrev) seatSearchPrev.style.display = 'flex';
            if (seatSearchNext) seatSearchNext.style.display = 'flex';
          } else {
            if (seatSearchPrev) seatSearchPrev.style.display = 'none';
            if (seatSearchNext) seatSearchNext.style.display = 'none';
          }

          // Scroll to the first match
          const firstSeat = matchedSeats[0];
          if (firstSeat) {
            firstSeat.classList.add('active-match');
            firstSeat.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
          }
        }
      }, 300);
    });
  }

  // --- Coming from Teacher Dashboard "Edit Seat" flow ---
  const urlParams = new URLSearchParams(window.location.search);
  let dashboardStudentId = urlParams.get('student_id') || null;
  let dashboardStudentName = urlParams.get('student_name') || '';
  let dashboardSeatNumber = urlParams.get('seat') || null;
  let dashboardFloor = urlParams.get('floor') || null;

  // --- Sanitize URL parameters to prevent DOM XSS ---
  if (dashboardStudentId) dashboardStudentId = dashboardStudentId.replace(/[^a-zA-Z0-9_\-]/g, '');
  if (dashboardSeatNumber) dashboardSeatNumber = dashboardSeatNumber.replace(/[^a-zA-Z0-9_\-]/g, '');
  if (dashboardFloor) dashboardFloor = dashboardFloor.replace(/[^a-zA-Z0-9 ]/g, '');

  // Optional: show a small hint somewhere if you want
  if (dashboardStudentId) {
    console.log('Seat Manager opened for student:', dashboardStudentId, dashboardStudentName);
  }


  // --- State ---
  let currentFloor = null;
  let currentSeatData = {}; // { floor, seat_number, status, student_id, student_name }
  let studentListCache = { library: null, coaching: null, alumni: null }; // cache per type
  let lastAssignShift = 'full';

  const shiftLabelMap = {
    full: 'Full Day',
    morning: 'Morning Shift',
    evening: 'Evening Shift'
  };

  // --- Date Formatter ---
  function formatDateFriendly(isoStr) {
    if (!isoStr) return 'Unknown Date';
    const date = new Date(isoStr);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    const dDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());

    if (dDate.getTime() === today.getTime()) return 'Today';
    if (dDate.getTime() === yesterday.getTime()) return 'Yesterday';

    // DD/MM/YYYY
    const d = String(date.getDate()).padStart(2, '0');
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const y = date.getFullYear();
    return `${d}/${m}/${y}`;
  }

  // --- ABCD Standard Name Normalizer Formula ---
  function abcdFormatName(name) {
    if (!name) return "";
    return name.split(/\s+/).map(part => {
      if (!part) return "";
      return part.charAt(0).toUpperCase() + part.slice(1).toLowerCase();
    }).filter(p => p).join(' ');
  }

  // --- HELPERS: Modal Placement ---
  window.ensureModalInBody = function() {
    try {
      const modals = [modalOverlay, seatDetailsModal, assignStudentModal, holdModal, conflictModal];
      modals.forEach(m => {
        if (m && m.parentElement !== document.body) {
          document.body.appendChild(m);
        }
      });
    } catch (err) {
      console.warn('Modal placement error:', err);
    }
  };
  window.ensureModalInBody();

  // --- Layout load/update ---
  async function loadSeatLayout(floor) {
    closeSeatDetailsModal();
    if (!floor) {
      if (groundFloorWrapper) groundFloorWrapper.style.display = 'none';
      if (firstFloorWrapper) firstFloorWrapper.style.display = 'none';
      if (loadingMessage) loadingMessage.style.display = 'none';
      return;
    }
    currentFloor = floor;
    if (loadingMessage) loadingMessage.style.display = 'block';
    if (groundFloorWrapper) groundFloorWrapper.style.display = 'none';
    if (firstFloorWrapper) firstFloorWrapper.style.display = 'none';

    const wrapper = (floor === 'Ground Floor') ? groundFloorWrapper : firstFloorWrapper;

    try {
      const res = await fetch(`${API_GET_SEATS_URL}?floor=${encodeURIComponent(floor)}`);
      if (!res.ok) throw new Error(`Seats fetch failed: ${res.status} ${res.statusText}`);
      const data = await res.json();
      updateLayout(floor, data.seats || []);
      if (wrapper) wrapper.style.display = 'block';

      // Auto-open seat when coming from dashboard
      if (dashboardSeatNumber && wrapper) {
        setTimeout(() => {
          const seatEl = wrapper.querySelector(`.seat[data-seat-id="${dashboardSeatNumber}"]`);
          if (seatEl) {
            openSeatDetailsModal(seatEl);
          } else {
            console.warn('Dashboard seat not found in layout:', dashboardSeatNumber);
          }
        }, 300); // wait for DOM paint
      }
    } catch (err) {
      console.error('loadSeatLayout error:', err);
      if (loadingMessage) loadingMessage.textContent = 'Error loading layout. Check console.';
      // Show base layout even if API fails so the page isn't blank
      if (wrapper) wrapper.style.display = 'block';
    } finally {
      if (loadingMessage) loadingMessage.style.display = 'none';
    }
  }

  function updateLayout(floor, seats) {
    const wrapper = (floor === 'Ground Floor') ? groundFloorWrapper : firstFloorWrapper;
    if (!wrapper) return;

    seats.forEach(seat => {
      const seatEl = wrapper.querySelector(`.seat[data-seat-id="${seat.seat_number}"]`);
      if (!seatEl) return;

      // 1. Reset Classes to base state
      seatEl.className = 'seat';
      if (seat.is_shift_enabled) {
        seatEl.classList.add('shift-seat');
      }

      // Handle shift elements & locked classes
      let topHalf = seatEl.querySelector('.seat-half.seat-morning');
      let bottomHalf = seatEl.querySelector('.seat-half.seat-evening');
      const lockedShiftsList = (seat.locked_shifts || '').split(',').filter(Boolean);
      const isFullyLocked = seat.is_locked || lockedShiftsList.includes('full');

      if (seat.is_shift_enabled) {
        if (!topHalf) {
          topHalf = document.createElement('div');
          topHalf.className = 'seat-half seat-morning';
          seatEl.prepend(topHalf);
        }
        if (!bottomHalf) {
          bottomHalf = document.createElement('div');
          bottomHalf.className = 'seat-half seat-evening';
          seatEl.insertBefore(bottomHalf, topHalf.nextSibling);
        }

        topHalf.className = 'seat-half seat-morning';
        topHalf.dataset.locked = 'false';
        bottomHalf.className = 'seat-half seat-evening';
        bottomHalf.dataset.locked = 'false';

        if (isFullyLocked) {
          seatEl.classList.add('locked');
          seatEl.dataset.locked = 'true';
          topHalf.classList.add('locked');
          topHalf.dataset.locked = 'true';
          bottomHalf.classList.add('locked');
          bottomHalf.dataset.locked = 'true';
        } else {
          if (lockedShiftsList.includes('morning')) {
            topHalf.classList.add('locked');
            topHalf.dataset.locked = 'true';
            seatEl.classList.add('locked-morning');
          }
          if (lockedShiftsList.includes('evening')) {
            bottomHalf.classList.add('locked');
            bottomHalf.dataset.locked = 'true';
            seatEl.classList.add('locked-evening');
          }
        }
      } else {
        if (isFullyLocked) {
          seatEl.classList.add('locked');
          seatEl.dataset.locked = 'true';
        }
      }


      // 2. VISUALS: Apply Colors (Shift-Aware)
      if (seat.is_shift_enabled) {
        const assignments = seat.assignments || [];
        const pendingAssignments = assignments.filter(a => a.is_pending || a.student_status === 'pending');

        // Detect partial/hold states
        const morningAssigns = assignments.filter(a => a.shift === 'morning');
        const eveningAssigns = assignments.filter(a => a.shift === 'evening');
        const fullAssigns = assignments.filter(a => a.shift === 'full');

        const morningPartial = morningAssigns.some(a => a.is_partial && !a.is_pending && a.student_status !== 'pending');
        const eveningPartial = eveningAssigns.some(a => a.is_partial && !a.is_pending && a.student_status !== 'pending');
        const fullHold = fullAssigns.some(a => a.hold_status === 'active' && !a.is_partial);
        const morningHold = morningAssigns.some(a => a.hold_status === 'active' && !a.is_partial) || fullHold;
        const eveningHold = eveningAssigns.some(a => a.hold_status === 'active' && !a.is_partial) || fullHold;

        const pendingMorning = pendingAssignments.find(a => a.shift === 'morning');
        const pendingEvening = pendingAssignments.find(a => a.shift === 'evening');
        const pendingFull = pendingAssignments.find(a => a.shift === 'full');
        const hasPending = pendingAssignments.length > 0;

        if (hasPending && !seat.full_day_taken && !seat.morning_taken && !seat.evening_taken) {
          if (pendingFull || (pendingMorning && pendingEvening)) {
            // Check for temporary pending request
            if ((pendingFull && pendingFull.is_partial) || (pendingMorning && pendingMorning.is_partial && pendingEvening && pendingEvening.is_partial)) {
              seatEl.classList.add('shift-pending-temp-full');
            } else {
              seatEl.classList.add('shift-pending-full');
            }
          } else if (pendingMorning) {
            if (pendingMorning.is_partial) seatEl.classList.add('shift-pending-temp-morning');
            else seatEl.classList.add('shift-pending-morning');
            // Also need to handle 'evening available' visual if strictly needed, 
            // but the CSS 'shift-pending-morning' handles the morning part.
            // Ensure we don't accidentally add 'available' class which might override
          } else if (pendingEvening) {
            if (pendingEvening.is_partial) seatEl.classList.add('shift-pending-temp-evening');
            else seatEl.classList.add('shift-pending-evening');
          }
        } else if (pendingMorning && !seat.morning_taken) {
          // Mixed Case: Morning Pending, Evening Occupied/Hold
          if (pendingMorning.is_partial) seatEl.classList.add('shift-pending-temp-morning');
          else seatEl.classList.add('shift-pending-morning');

          if (seat.evening_taken) {
            if (eveningHold && eveningPartial) seatEl.classList.add('hold-evening-temp-evening');
            else if (eveningPartial) seatEl.classList.add('shift-partial');
            else if (eveningHold) seatEl.classList.add('hold-evening');
            else seatEl.classList.add('occupied-evening');
          }
        } else if (pendingEvening && !seat.evening_taken) {
          // Mixed Case: Evening Pending, Morning Occupied/Hold
          if (pendingEvening.is_partial) seatEl.classList.add('shift-pending-temp-evening');
          else seatEl.classList.add('shift-pending-evening');

          if (seat.morning_taken) {
            if (morningHold && morningPartial) seatEl.classList.add('hold-morning-temp-morning');
            else if (morningPartial) seatEl.classList.add('shift-partial');
            else if (morningHold) seatEl.classList.add('hold-morning');
            else seatEl.classList.add('occupied-morning');
          }
        } else if (seat.full_day_taken) {
          // Check if full day is on hold first
          const fullHold = fullAssigns.some(a => a.hold_status === 'active' && !a.is_partial);
          const fullPartial = fullAssigns.some(a => a.is_partial);

          const mHold = morningHold || fullHold;
          const eHold = eveningHold || fullHold;

          const pendingFullTempRequest = pendingFull && pendingFull.is_partial;
          const pendingMorningTempRequest = pendingMorning && pendingMorning.is_partial;
          const pendingEveningTempRequest = pendingEvening && pendingEvening.is_partial;

          if (pendingFullTempRequest) {
            // PENDING Full-Day Temp request over a shift-seat hold.
            // Visual per user images:
            //   - Morning on hold + pending temp → morning half = orange|pink gradient, evening half = pink
            //   - Evening on hold + pending temp → morning half = pink, evening half = pink|orange gradient
            //   - Both holds + pending temp → full pink both halves (T34/T35)
            if (mHold && eHold) {
              seatEl.classList.add('shift-pending-temp-full'); // Both halves pink
            } else if (mHold) {
              seatEl.classList.add('pending-hold-morning-with-temp'); // Top=orange|pink, Bottom=pink
            } else if (eHold) {
              seatEl.classList.add('pending-hold-evening-with-temp'); // Top=pink, Bottom=pink|orange
            } else {
              seatEl.classList.add('shift-pending-temp-full'); // Fallback full pink
            }
          } else if (pendingMorningTempRequest) {
            if (eveningPartial && eHold) {
              seatEl.classList.add('shift-pending-temp-morning', 'hold-evening-temp-evening');
            } else {
              seatEl.classList.add('shift-pending-temp-morning', 'hold-evening');
            }
          } else if (pendingEveningTempRequest) {
            if (morningPartial && mHold) {
              seatEl.classList.add('shift-pending-temp-evening', 'hold-morning-temp-morning');
            } else {
              seatEl.classList.add('shift-pending-temp-evening', 'hold-morning');
            }
          } else if (fullPartial) {
            // APPROVED Full-Day Temp over a shift-seat hold.
            if (mHold && eHold) {
              seatEl.classList.add('hold-partial'); // Full day diagonal split
            } else if (mHold) {
              seatEl.classList.add('hold-morning-with-temp'); // Top=orange|pink gradient, Bottom=solid pink
            } else if (eHold) {
              seatEl.classList.add('hold-evening-with-temp'); // Top=solid pink, Bottom=pink|orange gradient
            } else {
              seatEl.classList.add('partial'); // Full pink, no hold context
            }
          } else if (morningPartial && eveningPartial) {
            if (mHold && eHold) {
              seatEl.classList.add('hold-morning-temp-morning', 'hold-evening-temp-evening');
            } else if (mHold) {
              seatEl.classList.add('hold-morning-temp-morning', 'shift-partial');
            } else if (eHold) {
              seatEl.classList.add('hold-evening-temp-evening', 'shift-partial');
            } else {
              seatEl.classList.add('shift-both-partial');
            }
          } else if (morningPartial) {
            if (mHold && eHold) {
              seatEl.classList.add('hold-morning-temp-morning', 'hold-evening');
            } else {
              seatEl.classList.add('shift-partial');
            }
          } else if (eveningPartial) {
            if (mHold && eHold) {
              seatEl.classList.add('hold-evening-temp-evening', 'hold-morning');
            } else {
              seatEl.classList.add('shift-partial');
            }
          } else if (pendingMorning && pendingMorning.is_partial && pendingEvening && pendingEvening.is_partial) {
            seatEl.classList.add('shift-both-partial');
          } else if (pendingMorning && pendingMorning.is_partial) {
            // Apply pending temp pink on morning, keep evening orange (from hold)
            seatEl.classList.add('shift-pending-temp-morning', 'hold-evening');
          } else if (pendingEvening && pendingEvening.is_partial) {
            // Apply pending temp pink on evening, keep morning orange
            seatEl.classList.add('shift-pending-temp-evening', 'hold-morning');
          } else if (fullHold) {
            seatEl.classList.add('on_hold'); // Full orange
          } else {
            seatEl.classList.add('occupied-full'); // Full purple
          }
        } else if (seat.morning_taken && seat.evening_taken) {
          // Both shifts occupied - check if both partial
          if (morningPartial && eveningPartial) {
            seatEl.classList.add('shift-both-partial'); // Pink/Orange quadrants
          } else {
            // Use granular classes for mixed occupied
            if (morningPartial && morningHold) {
              seatEl.classList.add('hold-morning-temp-morning');
            } else if (morningHold) {
              seatEl.classList.add('hold-morning');
            } else {
              seatEl.classList.add('occupied-morning');
            }

            if (eveningPartial && eveningHold) {
              seatEl.classList.add('hold-evening-temp-evening');
            } else if (eveningHold) {
              seatEl.classList.add('hold-evening');
            } else {
              seatEl.classList.add('occupied-evening');
            }

            // CRITICAL: Overrides for pending temporary requests
            const pendingMorningTemp = pendingMorning && pendingMorning.is_partial;
            const pendingEveningTemp = pendingEvening && pendingEvening.is_partial;

            if (pendingMorningTemp && pendingEveningTemp) {
              // Both shifts have pending temp requests
              seatEl.classList.remove('hold-morning', 'occupied-morning', 'hold-evening', 'occupied-evening', 'hold-morning-temp-morning', 'hold-evening-temp-evening');
              seatEl.classList.add('shift-both-partial'); // Solid pink
            } else if (pendingMorningTemp) {
              // Morning has pending temp request
              seatEl.classList.remove('hold-morning', 'occupied-morning', 'hold-morning-temp-morning');
              seatEl.classList.add('shift-pending-temp-morning');
            } else if (pendingEveningTemp) {
              // Evening has pending temp request
              seatEl.classList.remove('hold-evening', 'occupied-evening', 'hold-evening-temp-evening');
              seatEl.classList.add('shift-pending-temp-evening');
            }
          }
        } else if (seat.morning_taken) {
          // Morning occupied - check for partial or hold
          if (morningPartial && morningHold) {
            seatEl.classList.add('hold-morning-temp-morning');
          } else if (morningPartial) {
            if (eveningHold) {
              seatEl.classList.add('diagonal-hold-partial'); // Diagonal orange/pink if some other weird logic
            } else {
              seatEl.classList.add('shift-partial'); // Purple/pink split
            }
          } else {
            // Check for pending temporary requests on Morning
            const pendingMorningTempRequest = pendingMorning && pendingMorning.is_partial;

            if (pendingMorningTempRequest) {
              seatEl.classList.add('shift-pending-temp-morning');
            } else if (morningHold) {
              seatEl.classList.add('hold-morning');
            } else {
              seatEl.classList.add('occupied-morning');
            }

            if (!seat.evening_taken && !morningHold && !pendingMorningTempRequest && !morningPartial) {
              seatEl.classList.add('shift-morning-only'); // transparent bottom half
            }
          }
        } else if (seat.evening_taken) {
          // Evening occupied - check for partial or hold
          if (eveningPartial && eveningHold) {
            seatEl.classList.add('hold-evening-temp-evening');
          } else if (eveningPartial) {
            if (morningHold) {
              seatEl.classList.add('diagonal-hold-partial'); // Diagonal orange/pink
            } else {
              seatEl.classList.add('shift-partial'); // Purple/pink split
            }
          } else {
            // Check for pending temporary requests on Evening
            const pendingEveningTempRequest = pendingEvening && pendingEvening.is_partial;

            if (pendingEveningTempRequest) {
              seatEl.classList.add('shift-pending-temp-evening');
            } else if (eveningHold) {
              // Evening on hold
              if (morningAssigns.length > 0 && !morningHold) {
                seatEl.classList.add('shift-occupied-hold'); // Purple (occupied) / Orange (hold)
              } else {
                seatEl.classList.add('hold-evening'); // Just hold evening
              }
            } else {
              // Evening occupied (not hold, not partial)
              seatEl.classList.add('shift-evening-only'); // Purple top half
            }
          }
        } else {
          // Not fully taken by shifts, check standard status (e.g. 'on_hold' or 'pending')
          let rawStatus = seat.status || 'available';
          if (rawStatus === 'on-hold') rawStatus = 'on_hold';
          seatEl.classList.add(rawStatus);
        }
      } else {
        // Standard Seat (Non-Shift)
        let rawStatus = seat.status || 'available';
        if (rawStatus === 'on-hold') rawStatus = 'on_hold';

        // Check if it's a partial allotment (temporary tenant)
        const assignments = seat.assignments || [];
        const activeAssigns = assignments.filter(a => !a.is_pending && a.student_status !== 'pending' && (a.is_active !== false));
        const pendingAssigns = assignments.filter(a => a.is_pending || a.student_status === 'pending');

        const isPartial = activeAssigns.some(a => a.is_partial && a.shift === 'full');
        const hasHold = activeAssigns.some(a => a.hold_status === 'active' && !a.is_partial);
        const hasActive = activeAssigns.length > 0;
        const hasPending = pendingAssigns.length > 0;

        // Prioritize status: pending-temp > hold-partial > partial > on_hold > occupied > pending > available
        const pendingTempRequest = pendingAssigns.find(a => a.is_partial);
        const isPendingTemp = !!pendingTempRequest;

        if (isPendingTemp) {
          seatEl.classList.add('pending-temp');
        } else if (isPartial && hasHold) {
          seatEl.classList.add('hold-partial'); // Diagonal split
        } else if (isPartial) {
          seatEl.classList.add('partial'); // Pink
        } else if (hasHold) {
          seatEl.classList.add('on_hold'); // Orange
        } else if (hasActive) {
          seatEl.classList.add('occupied'); // Green
        } else if (hasPending) {
          seatEl.classList.add('pending'); // Blue
        } else {
          seatEl.classList.add('available'); // Black/Grey
        }
      }

      // 3. DATA: Store Attributes for Click Handlers
      // Normalize status string for dataset
      let dataStatus = seat.status || 'available';
      if (dataStatus === 'on-hold') dataStatus = 'on_hold';

      seatEl.dataset.seatId = seat.seat_number;
      seatEl.dataset.status = dataStatus;
      seatEl.dataset.studentName = seat.student_name || '';
      seatEl.dataset.studentId = (seat.student_ids && seat.student_ids.length > 0) ? seat.student_ids[0] : '';
      seatEl.dataset.shiftEnabled = seat.is_shift_enabled;
      seatEl.dataset.assignments = JSON.stringify(seat.assignments || []);
      seatEl.dataset.info = JSON.stringify(seat);
      seatEl.dataset.locked = seat.is_locked ? 'true' : 'false';
      seatEl.dataset.lockedShifts = seat.locked_shifts || '';


      // 4. LABEL: Update Text (Names or Status) - TEACHER VIEW shows FIRST NAMES
      const labelEl = seatEl.querySelector('.seat-label');
      if (labelEl) {
        labelEl.classList.remove('student-name');
        labelEl.style.fontSize = '';
        labelEl.style.lineHeight = '';

        // Reset dynamic labels first
        seatEl.querySelectorAll('.seat-morning-label, .seat-evening-label').forEach(el => el.remove());
        labelEl.style.display = ''; // Reset visibility

        let displayText = '';

        // --- NEW LOGIC FOR LABELS ---
        if (seat.is_shift_enabled) {
          const assignments = seat.assignments || [];
          const activeAssigns = assignments.filter(a => !a.is_pending && a.student_status !== 'pending');
          const pendingAssigns = assignments.filter(a => a.is_pending || a.student_status === 'pending');

          const activeFull = activeAssigns.find(a => a.shift === 'full');
          const activeMorning = activeAssigns.find(a => a.shift === 'morning');
          const activeEvening = activeAssigns.find(a => a.shift === 'evening');

          const pendingMorning = pendingAssigns.find(a => a.shift === 'morning');
          const pendingEvening = pendingAssigns.find(a => a.shift === 'evening');
          const pendingFull = pendingAssigns.find(a => a.shift === 'full');

          // --- REFACTORED LABEL LOGIC (Prioritize Holds) ---
          // Backend API returns 'hold_days' on each assignment object

          const lockedList = (seat.locked_shifts || '').split(',').filter(Boolean);
          const isFullLocked = seat.is_locked || lockedList.includes('full');

          // 1. Determine Text for Each Shift
          let mText = 'Available';
          const isMHold = activeMorning && activeMorning.hold_status === 'active';

          if (lockedList.includes('morning') || isFullLocked) {
            mText = '🔒 Locked';
          } else if (isMHold) {
            // Check for pending temporary override
            if (pendingMorning && pendingMorning.is_partial) {
              mText = "Pending";
            } else {
              const name = abcdFormatName(activeMorning.student_name).split(' ')[0];
              const days = activeMorning.hold_days;
              mText = (days !== undefined && days !== null) ? `${name}(${days})` : `${name}(M)`;
            }
          } else if (activeMorning) {
            const name = abcdFormatName(activeMorning.student_name).split(' ')[0] || 'Occupied';
            mText = `${name}(M)`;
          } else if (pendingMorning) {
            // If it's a pending temp request on an empty seat
            mText = pendingMorning.is_partial ? "Pending" : "Pending(M)";
          }

          let eText = 'Available';
          const isEHold = activeEvening && activeEvening.hold_status === 'active';

          if (lockedList.includes('evening') || isFullLocked) {
            eText = '🔒 Locked';
          } else if (isEHold) {
            // Check for pending temporary override
            if (pendingEvening && pendingEvening.is_partial) {
              eText = "Pending";
            } else {
              const name = abcdFormatName(activeEvening.student_name).split(' ')[0];
              const days = activeEvening.hold_days;
              eText = (days !== undefined && days !== null) ? `${name}(${days})` : `${name}(E)`;
            }
          } else if (activeEvening) {
            const name = abcdFormatName(activeEvening.student_name).split(' ')[0] || 'Occupied';
            eText = `${name}(E)`;
          } else if (pendingEvening) {
            // If it's a pending temp request on an empty seat
            eText = pendingEvening.is_partial ? "Pending" : "Pending(E)";
          }


          // 2. Render Labels based on Combined State
          const isFullHold = activeAssigns.some(a => a.shift === 'full' && a.hold_status === 'active' && !a.is_partial);
          const isFullPartial = activeAssigns.some(a => a.shift === 'full' && a.is_partial);
          const isPendingFullPartial = pendingFull && pendingFull.is_partial;

          // Apply full day partial/temp labels.
          // Key: for full_day_taken seats, isMHold/isEHold are derived from shift-specific
          // morning/evening assignments. But isFullHold covers both shifts.
          // So we compute effective hold per shift:
          const effectiveMorningHeld = isMHold || isFullHold;
          const effectiveEveningHeld = isEHold || isFullHold;

          if (isFullPartial || isPendingFullPartial) {
            if (effectiveMorningHeld && effectiveEveningHeld) {
              // Both shifts held (full-day hold or both individual holds): both show "Temp."
              mText = isPendingFullPartial ? "Pending" : "Temp.";
              eText = isPendingFullPartial ? "Pending" : "Temp.";
            } else if (effectiveMorningHeld) {
              // Only morning held: morning gets temp label, evening stays available
              mText = isPendingFullPartial ? "Pending" : "Temp.";
              // eText stays "Available" (it has no assignment)
            } else if (effectiveEveningHeld) {
              // Only evening held: evening gets temp label, morning stays available
              eText = isPendingFullPartial ? "Pending" : "Temp.";
              // mText stays "Available"
            } else {
              // No shifts held: show both as "Temp." (e.g. temp without hold)
              mText = isPendingFullPartial ? "Pending" : "Temp.";
              eText = isPendingFullPartial ? "Pending" : "Temp.";
            }
          }

          if (isFullHold) {
            const fullHoldAssign = activeAssigns.find(a => a.shift === 'full' && a.hold_status === 'active' && !a.is_partial);
            const name = abcdFormatName(fullHoldAssign.student_name).split(' ')[0];
            const days = fullHoldAssign.hold_days;

            const hasAnyTemp = isFullPartial || isPendingFullPartial ||
              (activeMorning && activeMorning.is_partial) || (pendingMorning && pendingMorning.is_partial) ||
              (activeEvening && activeEvening.is_partial) || (pendingEvening && pendingEvening.is_partial);

            if (hasAnyTemp) {
              const hasMorningP = pendingMorning && pendingMorning.is_partial;
              const hasEveningP = pendingEvening && pendingEvening.is_partial;
              const onlyFullPending = isPendingFullPartial && !hasMorningP && !hasEveningP;

              if (onlyFullPending) {
                // Display one central pending label since all requests are full day
                displayText = "Pending";
                labelEl.style.display = '';
              } else if (isFullPartial && !hasMorningP && !hasEveningP) {
                // Approved full-day temp on a full-day hold -> Diagonal labels (Owner + Temp)
                displayText = "";
                labelEl.style.display = 'none';

                const ownerLabel = (days !== undefined && days !== null) ? `${name}(${days})` : name;

                const mLabel = document.createElement('span');
                mLabel.className = 'seat-morning-label';
                mLabel.textContent = ownerLabel;
                seatEl.appendChild(mLabel);

                const eLabel = document.createElement('span');
                eLabel.className = 'seat-evening-label';
                eLabel.textContent = "Temp.";
                seatEl.appendChild(eLabel);
              } else {
                // NO labels at all unless it's a strictly pending temporary request that needs identifying
                displayText = "";
                labelEl.style.display = 'none';

                const mIsPending = isPendingFullPartial || hasMorningP;
                const eIsPending = isPendingFullPartial || hasEveningP;

                if (mIsPending) {
                  const mLabel = document.createElement('span');
                  mLabel.className = 'seat-morning-label';
                  mLabel.textContent = "Pending";
                  seatEl.appendChild(mLabel);
                }
                if (eIsPending) {
                  const eLabel = document.createElement('span');
                  eLabel.className = 'seat-evening-label';
                  eLabel.textContent = "Pending";
                  seatEl.appendChild(eLabel);
                }
              }
            } else {
              displayText = (days !== undefined && days !== null) ? `${name}(${days})` : `${name}(Hold)`;
            }
          }
          else if (activeAssigns.some(a => a.shift === 'full' && !a.is_partial)) {
            // Full Day Occupied (Permanent)
            const fullPermAssign = activeAssigns.find(a => a.shift === 'full' && !a.is_partial);
            const name = abcdFormatName(fullPermAssign.student_name).split(' ')[0] || 'Occupied';
            displayText = `${name}(F)`;
          }
          else if (pendingFull && !isPendingFullPartial) {
            displayText = 'Pending';
          }
          else if (isFullPartial || isPendingFullPartial) {
            // It's a full-day temp request WITHOUT a full-day hold.
            // This means one shift is hold, the other is not. We MUST split the view.
            if (mText !== 'Available' || eText !== 'Available') {
              labelEl.style.display = 'none'; // Hide main label

              const mLabel = document.createElement('span');
              mLabel.className = 'seat-morning-label';
              mLabel.textContent = mText;
              seatEl.appendChild(mLabel);

              const eLabel = document.createElement('span');
              eLabel.className = 'seat-evening-label';
              eLabel.textContent = eText;
              seatEl.appendChild(eLabel);

              displayText = "";
            } else {
              // Edge case: someone submitted temp request with NO holds on the seat.
              displayText = "Temp.";
            }
          }
          else if (mText !== 'Available' || eText !== 'Available') {
            // SPLIT VIEW REQUIRED (If either shift is not available)
            labelEl.style.display = 'none'; // Hide main label

            // Morning Label
            const mLabel = document.createElement('span');
            mLabel.className = 'seat-morning-label';
            mLabel.textContent = mText;
            seatEl.appendChild(mLabel);

            // Evening Label
            const eLabel = document.createElement('span');
            eLabel.className = 'seat-evening-label';
            eLabel.textContent = eText;
            seatEl.appendChild(eLabel);

            displayText = ""; // Handled by split labels
          }
          else {
            // Both shifts available -> Main "Available" label
            displayText = 'Available';
          }

        } else {
          // STANDARD SEAT (Non-Shift)
          const assignments = seat.assignments || [];
          const activeAssigns = assignments.filter(a => !a.is_pending && a.student_status !== 'pending');
          const holdOwner = activeAssigns.find(a => a.hold_status === 'active' && !a.is_partial);
          const tempTenant = activeAssigns.find(a => a.is_partial);
          const pendingAssigns = assignments.filter(a => a.is_pending || a.student_status === 'pending');
          const isPendingTemp = pendingAssigns.some(a => a.is_partial);

          // Check if fully locked
          const isNonShiftLocked = seat.is_locked || (seat.locked_shifts || '').split(',').filter(Boolean).includes('full');

          if (isNonShiftLocked) {
            displayText = '🔒 Locked';
          } else if (holdOwner && (tempTenant || isPendingTemp)) {
            // HOLD + TEMP (or HOLD + pending temp): Show diagonal split labels
            const ownerName = abcdFormatName(holdOwner.student_name).split(' ')[0] || 'Hold';
            const days = holdOwner.hold_days;
            const ownerLabel = (days !== undefined && days !== null) ? `${ownerName}(${days})` : ownerName;

            labelEl.style.display = 'none'; // Hide main label

            const mLabel = document.createElement('span');
            mLabel.className = 'seat-morning-label';
            mLabel.textContent = ownerLabel;
            seatEl.appendChild(mLabel);

            const eLabel = document.createElement('span');
            eLabel.className = 'seat-evening-label';
            eLabel.textContent = 'Temp.';
            seatEl.appendChild(eLabel);

            displayText = '';
            labelEl.classList.add('student-name');
          } else if (holdOwner) {
            const name = abcdFormatName(holdOwner.student_name).split(' ')[0] || 'Hold';
            const days = holdOwner.hold_days;
            displayText = (days !== undefined && days !== null) ? `${name}(${days})` : name;
            labelEl.classList.add('student-name');
          } else if (tempTenant) {
            const name = abcdFormatName(tempTenant.student_name).split(' ')[0] || 'Temp';
            displayText = name;
            labelEl.classList.add('student-name');
          } else if (activeAssigns.length > 0) {
            const activeAssign = activeAssigns[0];
            const name = abcdFormatName(activeAssign.student_name).split(' ')[0] || 'Occupied';
            
            if (activeAssign.hold_status === 'active') {
                const days = activeAssign.hold_days || 0;
                displayText = `${name}(${days})`;
            } else {
                displayText = name;
            }
            labelEl.classList.add('student-name');
          } else if (dataStatus === 'pending') {
            displayText = 'Pending';
            labelEl.classList.add('student-name');
          } else if (dataStatus === 'on_hold') {
            // Seat-level hold with no active assignment
            const days = seat.remaining_days;
            displayText = (days !== undefined && days !== null) ? `Hold(${days})` : 'On Hold';
            labelEl.classList.add('student-name');
          } else {
            displayText = 'Available';
          }
        }

        // Handle partial color-only overrides (hide text if partial)
        if (seatEl.classList.contains('shift-both-partial') ||
          seatEl.classList.contains('hold-partial') ||
          seatEl.classList.contains('diagonal-hold-partial') ||
          seatEl.classList.contains('partial')) {
          // For partials, we might want to hide text or show specific partial text
          // The previous code hid text.
          // But SKILL.md images T39/A37 (Partial) usually have no text or "Temp"?
          // Let's keep existing logic: hide text if it's purely partial color coding
          // UNLESS we want to show "Temp"
          // But here we are setting STUDENT NAMES. 
          // If a seat is partially occupied by a student, we probably want to show their name?
          // The user's previous code hid it: "displayText = ''; // Color only, no text"

          // However, for Mixed states (one occupied, one partial), we handled occupied text above.
          // If completely partial (Pink), maybe show "Temp"?
          // User didn't specify. I will stick to what I just generated, but safeguard against overwriting if strict partial logic existed.
          // Actually, the previous code had a block to clear displayText for partials.
          // I'll add a check: if it's purely partial (both shifts temp), maybe clear text.
          // But if mixed (Occupied + Temp), we want to show the Occupied name!
          // My logic above handles Mixed Occupied/Pending.
          // It does NOT explicitly handle Mixed Occupied/Temp in the text generation part,
          // but `activeAssigns` logic usually covers it if the temp allotment is considered an "active assignment".
          // (Temp assignments typically have `is_partial=true` but are still assignments).

          // If `activeAssigns` includes partials, they will get names shown. 
          // If we want to hide names for partials, we should filter them out or check `is_partial`.
          // Re-reading SKILL.md for T39 (Temp Allotment): "Pink. Icon Pink." Text?
          // Usually "Temp" or Name.
          // I'll assume showing Name is better than nothing if available for Teacher.
        }

        // Append Hold Days if applicable and On Hold
        if (displayText === 'On Hold' && typeof seat.remaining_days === 'number' && !isNaN(seat.remaining_days)) {
          const days = Math.max(seat.remaining_days, 0);
          displayText = `Hold(${days})`;
        }

        // Render Text
        labelEl.textContent = displayText;

        // Auto-shrink text
        if (displayText.length > 10) {
          labelEl.style.fontSize = '0.65rem';
          labelEl.style.lineHeight = '1.1';
        } else {
          labelEl.style.fontSize = '0.8rem';
        }
      }
    });
  }

  const studentAssignTypeEl = studentAssignType; // keep original name mapping in case used elsewhere


  // --- Student list load/populate (UPDATED) ---
  // We now support 3 modes: library, coaching, manual.

  async function loadStudentList(type = 'library') {
    // type: 'library' | 'coaching'
    if (type === 'manual') {
      // nothing to fetch for manual (we show manual form)
      populateStudentDropdown([]); // clear select
      return;
    }
    if (!studentAssignSelect) return;

    // use cache
    if (studentListCache[type]) {
      populateStudentDropdown(studentListCache[type]);
      return;
    }

    // show loading
    studentAssignSelect.textContent = '';
    const loadingOpt = document.createElement('option');
    loadingOpt.value = '';
    loadingOpt.textContent = 'Loading students...';
    studentAssignSelect.appendChild(loadingOpt);
    refreshCustomSelect(studentAssignSelect);

    try {
      // --- Build correct URL for our Django API ---
      // Backend expects ?type=library, ?type=coaching or ?type=alumni
      let fetchUrl;

      if (type === 'coaching') {
        // if a dedicated coaching URL is ever defined, use it
        if (typeof API_GET_COACHING_STUDENTS_URL !== 'undefined') {
          fetchUrl = API_GET_COACHING_STUDENTS_URL;
        } else {
          fetchUrl = `${API_GET_STUDENTS_URL}?type=coaching`;
        }
      } else if (type === 'alumni') {
        fetchUrl = `${API_GET_STUDENTS_URL}?type=alumni`;
      } else {
        // default: library students
        fetchUrl = `${API_GET_STUDENTS_URL}?type=library`;
      }

      let res = await fetch(fetchUrl);

      // If that call fails, fall back to base endpoint and filter on client
      if (!res.ok) {
        const txt = await res.text().catch(() => null);
        console.warn(
          'Primary students endpoint returned non-ok; trying fallback.',
          res.status,
          txt
        );

        const fallback = await fetch(`${API_GET_STUDENTS_URL}?type=all`);
        if (!fallback.ok) {
          throw new Error(`Student list API returned ${fallback.status}`);
        }
        const baseData = await fallback.json();
        const studentsAll = baseData.students || [];

        let studentsFiltered = [];
        if (type === 'coaching') {
          studentsFiltered = studentsAll.filter(
            (s) => (s.service_type || '').toLowerCase() === 'coaching'
          );
        } else if (type === 'alumni') {
          // Fallback case: if client-side fallback happens, alumni are returned from the backend's ?type=alumni.
          // In fallback ?type=all we might not have all alumni if they are not admitted students,
          // so we don't apply service_type filter.
          studentsFiltered = studentsAll;
        } else {
          studentsFiltered = studentsAll.filter((s) => {
            const st = (s.service_type || '').toLowerCase();
            return st === 'library' || !st;
          });
        }

        studentListCache[type] = studentsFiltered;
        populateStudentDropdown(studentsFiltered);
        return;
      }

      // Normal successful response
      const data = await res.json();
      let students = data.students || [];

      // Extra safety: filter again by service_type in case backend returns mixed data
      if (type === 'coaching') {
        students = students.filter(
          (s) => (s.service_type || '').toLowerCase() === 'coaching'
        );
      } else if (type === 'library') {
        students = students.filter((s) => {
          const st = (s.service_type || '').toLowerCase();
          return st === 'library' || !st;
        });
      }

      studentListCache[type] = students;
      populateStudentDropdown(students);
    } catch (err) {
      console.error('loadStudentList error:', err);
      studentAssignSelect.textContent = '';
      const errOpt = document.createElement('option');
      errOpt.value = '';
      errOpt.textContent = 'Error loading students';
      studentAssignSelect.appendChild(errOpt);
      refreshCustomSelect(studentAssignSelect); // Sync error state to custom UI
    }
  }



  function populateStudentDropdown(students) {
    if (!studentAssignSelect) return;
    studentAssignSelect.textContent = '';
    
    const defaultOpt = document.createElement('option');
    defaultOpt.value = '';
    defaultOpt.textContent = '-- Select a student --';
    studentAssignSelect.appendChild(defaultOpt);

    if (!students || students.length === 0) {
      studentAssignSelect.textContent = '';
      const noStudentsOpt = document.createElement('option');
      noStudentsOpt.value = '';
      const mode = studentAssignType ? studentAssignType.value : 'library';
      if (mode === 'alumni') {
        noStudentsOpt.textContent = 'No alumni found';
      } else if (mode === 'coaching') {
        noStudentsOpt.textContent = 'No coaching students found';
      } else {
        noStudentsOpt.textContent = 'No admitted students found';
      }
      studentAssignSelect.appendChild(noStudentsOpt);
      refreshCustomSelect(studentAssignSelect);
      return;
    }

    const mode = studentAssignType ? studentAssignType.value : 'library';

    if (mode === 'library') {
      const groundFloor = [];
      const firstFloor = [];
      const holdStudents = [];
      const noSeatStudents = [];
      const otherFloors = {};

      students.forEach(s => {
        if (s.is_hold_owner) {
          holdStudents.push(s);
        } else if (!s.seat_number) {
          noSeatStudents.push(s);
        } else {
          const fl = s.floor ? s.floor.trim() : '';
          if (fl === 'Ground Floor') {
            groundFloor.push(s);
          } else if (fl === '1st Floor') {
            firstFloor.push(s);
          } else {
            if (!otherFloors[fl]) {
              otherFloors[fl] = [];
            }
            otherFloors[fl].push(s);
          }
        }
      });

      const appendGroup = (label, list) => {
        if (list.length === 0) return;
        const optgroup = document.createElement('optgroup');
        optgroup.label = label;
        list.forEach(s => {
          const opt = document.createElement('option');
          opt.value = s.id;
          const seatInfo = s.seat_number ? ` (Current: ${s.seat_number})` : ' (No Seat)';
          opt.textContent = `${abcdFormatName(s.full_name)}${seatInfo}`;
          optgroup.appendChild(opt);
        });
        studentAssignSelect.appendChild(optgroup);
      };

      appendGroup('Ground Floor', groundFloor);
      appendGroup('1st Floor', firstFloor);

      Object.keys(otherFloors).sort().forEach(fl => {
        appendGroup(fl || 'Other Floor', otherFloors[fl]);
      });

      appendGroup('Hold Students', holdStudents);
      appendGroup('No Seat Students', noSeatStudents);
    } else {
      // Flat list for other types (coaching/alumni)
      students.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        const seatInfo = s.seat_number ? ` (Current: ${s.seat_number})` : ' (No Seat)';
        opt.textContent = `${abcdFormatName(s.full_name)}${seatInfo}`;
        studentAssignSelect.appendChild(opt);
      });
    }
    
    // CRITICAL: Refresh the custom UI to reflect the new student list
    refreshCustomSelect(studentAssignSelect);
  }

  // ===========================================================================
  // REAL-TIME SEAT AVAILABILITY CHECK
  // ===========================================================================
  // This function fetches the current seat status from the API to check if
  // the requested shift is still available. Used before approving any pending
  // request to prevent conflicts when multiple teachers approve simultaneously.
  // ===========================================================================
  async function checkRealTimeSeatAvailability(floor, seatNumber, requestedShift) {
    try {
      // Use the public API which returns current seat status
      const apiUrl = typeof API_GET_SEATS_URL !== 'undefined'
        ? API_GET_SEATS_URL
        : '/users/api/get_teacher_seat_status/';

      const response = await fetch(`${apiUrl}?floor=${encodeURIComponent(floor)}`);
      if (!response.ok) {
        console.error('Failed to fetch seat status:', response.status);
        return { available: true, error: 'Failed to check availability' }; // Allow on error
      }

      const data = await response.json();
      const seats = data.seats || [];
      const seat = seats.find(s => String(s.seat_number) === String(seatNumber));

      if (!seat) {
        return { available: true, error: 'Seat not found' };
      }

      // Check if requested shift is available
      const shift = (requestedShift || 'full').toLowerCase();
      let isConflict = false;
      let conflictMessage = '';

      // For non-shift seats, the seat status itself determines availability
      const isStandardSeat = !seat.is_shift_enabled;

      if (isStandardSeat) {
        // Standard seat - check if occupied or full_day_taken
        if ((seat.status === 'occupied' || seat.full_day_taken || seat.morning_taken || seat.evening_taken) && !seat.can_request_partial) {
          isConflict = true;
          conflictMessage = 'This seat is already occupied by another student.';
        }
      } else if (shift === 'full' || shift === 'full_day') {
        // Full day request - check if any shift is taken
        if ((seat.morning_taken || seat.evening_taken || seat.full_day_taken) && !seat.can_request_partial) {
          isConflict = true;
          if (seat.full_day_taken) {
            conflictMessage = 'This seat is already occupied for full day.';
          } else {
            const parts = [];
            if (seat.morning_taken) parts.push('Morning');
            if (seat.evening_taken) parts.push('Evening');
            conflictMessage = `${parts.join(' and ')} shift is already occupied.`;
          }
        }
      } else if (shift === 'morning') {
        // Morning request - check if morning or full is taken
        if ((seat.morning_taken || seat.full_day_taken) && !seat.can_request_partial) {
          isConflict = true;
          conflictMessage = seat.full_day_taken
            ? 'This seat is already occupied for full day.'
            : 'Morning shift is already occupied.';
        }
      } else if (shift === 'evening') {
        // Evening request - check if evening or full is taken
        if ((seat.evening_taken || seat.full_day_taken) && !seat.can_request_partial) {
          isConflict = true;
          conflictMessage = seat.full_day_taken
            ? 'This seat is already occupied for full day.'
            : 'Evening shift is already occupied.';
        }
      }

      return {
        available: !isConflict,
        isConflict: isConflict,
        message: conflictMessage,
        seatData: seat
      };
    } catch (err) {
      console.error('checkRealTimeSeatAvailability error:', err);
      return { available: true, error: err.message }; // Allow on error to not block
    }
  }

  // --- seat details population (Strict SKILL Implementation) ---
  function showSeatDetails(seatEl, refreshOnly = false) {
    try {
      if (!refreshOnly && !seatEl) return;
      
      let seatNumber, seatStatus, isShiftEnabled, assignments, isLocked, lockedShifts;
      
      if (refreshOnly) {
        if (!currentSeatData || !currentSeatData.seat_number) return;
        seatNumber = currentSeatData.seat_number;
        seatStatus = currentSeatData.status;
        isShiftEnabled = currentSeatData.is_shift_enabled;
        assignments = currentSeatData.assignments || [];
        isLocked = !!currentSeatData.is_locked;
        lockedShifts = currentSeatData.locked_shifts || '';
      } else {
        seatNumber = seatEl.dataset.seatId;
        seatStatus = seatEl.dataset.status || 'available';
        isShiftEnabled = (seatEl.dataset.shiftEnabled === 'true');
        assignments = JSON.parse(seatEl.dataset.assignments || "[]");

        let rawInfo = {};
        if (seatEl.dataset.info) {
          try { rawInfo = JSON.parse(seatEl.dataset.info); } catch(e){}
        }

        isLocked = !!rawInfo.is_locked || seatEl.dataset.locked === 'true';
        lockedShifts = rawInfo.locked_shifts || '';

        currentSeatData = {
          seat_id: rawInfo.id,
          floor: rawInfo.floor || currentFloor,
          seat_number: seatNumber,
          status: seatStatus,
          is_shift_enabled: isShiftEnabled,
          is_locked: isLocked,
          locked_shifts: lockedShifts,
          assignments: assignments
        };
      }

      // Helper to generate buttons
      const btn = (label, action, cls = 'btn-primary', payload = {}) => {
        const safeLabel = escapeHTML(label);
        const safeAction = escapeHTML(action);
        const safeCls = escapeHTML(cls);
        const payloadStr = JSON.stringify(payload).replace(/"/g, '&quot;');
        return `<button class="btn-action ${safeCls}" onclick="window.handleSeatAction('${safeAction}', ${payloadStr})">${safeLabel}</button>`;
      };
      window._btn = btn; // Export for internal use

      // Analyze Shift State
      const morning = assignments.find(a => a.shift === 'morning');
      const evening = assignments.find(a => a.shift === 'evening');
      const full = assignments.find(a => a.shift === 'full');

      // Identify Pending Requests
      const allPendingMorning = assignments.filter(a => a.shift === 'morning' && a.student_status === 'pending');
      const allPendingEvening = assignments.filter(a => a.shift === 'evening' && a.student_status === 'pending');
      const allPendingFull = assignments.filter(a => a.shift === 'full' && a.student_status === 'pending');

      const pendingMorning = allPendingMorning[0];
      const pendingEvening = allPendingEvening[0];
      const pendingFull = allPendingFull[0];

      const hasPending = allPendingMorning.length > 0 || allPendingEvening.length > 0 || allPendingFull.length > 0;

      // Identify Active (non-pending) assignments for shift seats
      const activeMorning = assignments.find(a => a.shift === 'morning' && a.student_status !== 'pending' && (a.is_active !== false));
      const activeEvening = assignments.find(a => a.shift === 'evening' && a.student_status !== 'pending' && (a.is_active !== false));
      const activeFull = assignments.find(a => a.shift === 'full' && a.student_status !== 'pending' && (a.is_active !== false));

      const activeAssigns = assignments.filter(a => !a.is_pending && a.student_status !== 'pending' && (a.is_active !== false));
      const hasActive = activeAssigns.length > 0;

      let title = `Seat ${getFormattedSeatNumber(seatNumber)}`;
      let content = "";

      // =================================================================================
      // STATUS #0: FULLY LOCKED SEAT
      // =================================================================================
      if (isLocked || lockedShifts === 'full') {
        const formattedSeat = getFormattedSeatNumber(seatNumber);
        title = `Seat ${formattedSeat} - Locked`;
        content = `
          <div class="modal-section" style="padding-top: 10px; text-align:center;">
            <div style="font-size:2.5rem; margin-bottom:8px;">🔒</div>
            <p style="margin-bottom:15px; font-size:1.1rem; color: #dc2626; font-weight: 600;">This seat is locked by the Librarian</p>
            <p style="font-size:0.9rem; color: var(--text-muted); margin-bottom:20px;">No one can be assigned to this seat until it is unlocked by the Librarian.</p>
            <div class="modal-actions-col">
              ${btn('🔓 Unlock Seat', 'unlock_seat', 'btn-success', { shift: 'full' })}
            </div>
          </div>`;
      }

      // =================================================================================
      // STATUS #1: PENDING (ONLY IF NO ACTIVE OCCUPANTS ON SEAT)
      // =================================================================================
      else if (!hasActive && hasPending) {
        title = `Seat ${getFormattedSeatNumber(seatNumber)} - ${assignments.filter(a => a.student_status === 'pending').length} Pending Requests`;
        content = '<div class="pending-requests-list">';

        const activeMorningOccupied = assignments.find(a => a.shift === 'morning' && a.student_status !== 'pending' && a.is_active);
        const activeEveningOccupied = assignments.find(a => a.shift === 'evening' && a.student_status !== 'pending' && a.is_active);
        const activeFullOccupied = assignments.find(a => a.shift === 'full' && a.student_status !== 'pending' && a.is_active);

        const pReqs = assignments.filter(a => a.student_status === 'pending');
        pReqs.forEach((p, idx) => {
          const shiftLabel = shiftLabelMap[p.shift] || p.shift;
          const dateStr = formatDateFriendly(p.created_at);

          let isShiftConflict = false;
          if (p.shift === 'full') {
            isShiftConflict = !!(activeMorningOccupied || activeEveningOccupied || activeFullOccupied);
          } else if (p.shift === 'morning') {
            isShiftConflict = !!(activeMorningOccupied || activeFullOccupied);
          } else if (p.shift === 'evening') {
            isShiftConflict = !!(activeEveningOccupied || activeFullOccupied);
          }

          let actionButtons = '';
          if (p.is_special_request) {
            actionButtons = `
              ${btn('Reject Temp', 'reject_partial_request', 'btn-danger', { request_id: p.request_id })} 
              ${btn('Approve Temp', 'approve_partial_request', 'btn-primary', { request_id: p.request_id })}
            `;
            isShiftConflict = false;
          } else if (isShiftConflict) {
            actionButtons = `
              ${btn('Delete', 'delete_request', 'btn-danger btn-sm', { request_id: p.student_id, shift: p.shift })}
              ${btn('Approve w/o Seat', 'approve_without_seat', 'btn-warning', { request_id: p.student_id, shift: p.shift })}
              ${btn('Edit Seat', 'edit_pending_seat', 'btn-info', { request_id: p.student_id, shift: p.shift })}
            `;
          } else {
            actionButtons = `
              ${btn('Delete Request', 'delete_request', 'btn-danger', { request_id: p.student_id, shift: p.shift })} 
              ${btn('Approve', 'approve_pending', 'btn-primary', { request_id: p.student_id, shift: p.shift })}
            `;
          }

          content += `
                <div class="request-card ${isShiftConflict ? 'conflict' : 'normal'}">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                        <div>
                        <div style="display:flex; align-items:center; gap:12px;">
                            <div class="request-avatar-wrap">
                                ${p.photo_url 
                                    ? `<img src="${p.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                                    : `<i class='bx bxs-user' style="font-size:1.5rem; color:#cbd5e1;"></i>`
                                }
                            </div>
                            <div>
                                <p class="request-student-name">
                                    <strong>${escapeHTML(abcdFormatName(p.student_name))}</strong>
                                </p>
                                <p class="request-shift-info">
                                    ${p.is_special_request ? 'Temporary Request:' : 'Requested:'} ${shiftLabel}
                                </p>
                            </div>
                        </div>
                        ${isShiftConflict ? `
                        <p class="conflict-warning-badge">
                            ⚠️ <strong>Conflict:</strong> This shift is already occupied.
                        </p>
                        ` : ''}
                        </div>
                        <span class="request-date-badge">${dateStr}</span>
                    </div>
                    <div class="modal-actions-row" style="margin-top:12px;">
                        ${actionButtons}
                    </div>
                </div>
             `;
        });
        content += '</div>';

        if (isShiftEnabled) {
          const activeMorning = assignments.find(a => a.shift === 'morning' && a.student_status !== 'pending' && a.is_active);
          const activeEvening = assignments.find(a => a.shift === 'evening' && a.student_status !== 'pending' && a.is_active);
          const activeFull = assignments.find(a => a.shift === 'full' && a.student_status !== 'pending' && a.is_active);

          if (activeMorning || activeEvening || activeFull) {
            content += `<h4 style="margin:20px 0 10px; font-size:0.95rem; color:#555; border-bottom:1px solid #eee; padding-bottom:5px;">Current Occupancy</h4>`;

            const renderActiveRow = (a, label) => {
              const formattedName = abcdFormatName(a.student_name);
              const statusStr = a.hold_status === 'active' ? `On Hold by ${escapeHTML(formattedName)}` : `Occupied by ${escapeHTML(formattedName)}`;
              return `
                <div class="shift-block" style="background:#f5f5f5; padding:12px 15px; margin-bottom:10px; border-radius:8px;">
                    <div style="display:flex; align-items:center; gap:12px;">
                        <div style="width:36px; height:36px; border-radius:50%; overflow:hidden; border:2px solid white; box-shadow:0 2px 5px rgba(0,0,0,0.1); flex-shrink:0; background:#fff; display:flex; align-items:center; justify-content:center;">
                            ${a.photo_url 
                                ? `<img src="${a.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                                : `<i class='bx bxs-user' style="font-size:1.2rem; color:#cbd5e1;"></i>`
                            }
                        </div>
                        <p style="margin:0; font-size:0.9rem;"><strong>${label}</strong>: ${statusStr}</p>
                    </div>
                    <div class="modal-actions-row small-gap" style="margin-top:8px;">
                        ${btn('Details', 'view_student', 'btn-info btn-sm', { student_id: a.student_id })}
                        ${a.hold_status === 'active'
                  ? btn('End Hold', 'end_hold', 'btn-warning btn-sm', { student_id: a.student_id })
                  : btn('Hold', 'open_hold', 'btn-warning btn-sm', { student_id: a.student_id, shift: a.shift })
                }
                    </div>
                </div>`;
            };

            if (activeFull) content += renderActiveRow(activeFull, 'Full Day');
            if (activeMorning) content += renderActiveRow(activeMorning, 'Morning');
            if (activeEvening) content += renderActiveRow(activeEvening, 'Evening');
          }

          const hasMorning = assignments.some(a => (a.shift === 'morning' || a.shift === 'full') && a.student_status !== 'pending' && a.is_active);
          const hasEvening = assignments.some(a => (a.shift === 'evening' || a.shift === 'full') && a.student_status !== 'pending' && a.is_active);
          const lockedArr = lockedShifts.split(',').filter(Boolean);

          let availableHTML = "";
          if (!hasMorning) {
            if (lockedArr.includes('morning')) {
              availableHTML += `<div class="shift-option-row" style="margin-bottom:10px;">
                  <span style="font-size:0.9rem; color:#dc2626; font-weight:600;">🔒 Morning shift is locked</span>
                  ${btn('🔓 Unlock Morning', 'unlock_seat', 'btn-success btn-sm', { shift: 'morning' })}
                </div>`;
            } else {
              availableHTML += `<div class="shift-option-row" style="margin-bottom:10px;">
                  <span style="font-size:0.9rem; font-weight:600;">Morning Shift:</span>
                  <div class="shift-option-btn-wrap">
                    ${btn('Assign Morning', 'open_assign', 'btn-primary btn-sm', { shift: 'morning' })}
                    ${btn('🔒 Lock Morning', 'lock_seat', 'btn-lock btn-sm', { shift: 'morning' })}
                  </div>
                </div>`;
            }
          }
          if (!hasEvening) {
            if (lockedArr.includes('evening')) {
              availableHTML += `<div class="shift-option-row">
                  <span style="font-size:0.9rem; color:#dc2626; font-weight:600;">🔒 Evening shift is locked</span>
                  ${btn('🔓 Unlock Evening', 'unlock_seat', 'btn-success btn-sm', { shift: 'evening' })}
                </div>`;
            } else {
              availableHTML += `<div class="shift-option-row">
                  <span style="font-size:0.9rem; font-weight:600;">Evening Shift:</span>
                  <div class="shift-option-btn-wrap">
                    ${btn('Assign Evening', 'open_assign', 'btn-primary btn-sm', { shift: 'evening' })}
                    ${btn('🔒 Lock Evening', 'lock_seat', 'btn-lock btn-sm', { shift: 'evening' })}
                  </div>
                </div>`;
            }
          }

          if (availableHTML) {
            content += `<h4 style="margin:20px 0 10px; font-size:0.95rem; color:#555; border-bottom:1px solid #eee; padding-bottom:5px;">Available Shifts</h4>`;
            content += `<div class="available-shifts-card" style="display:flex; flex-direction:column; gap:10px;">${availableHTML}</div>`;
          }
        }
      }

      // =================================================================================
      // STATUS #2: AVAILABLE SEAT (ALL SHIFTS FREE)
      // =================================================================================
      else if (seatStatus === 'available') {
        const formattedSeat = getFormattedSeatNumber(seatNumber);
        
        if (!isShiftEnabled) {
          title = `Seat ${formattedSeat} - Available`;
          content = `
                <p style="margin-bottom:20px; text-align:center; color: var(--text-main); font-weight:500;">Seat ${formattedSeat} is free to allot any student</p>
                <div class="modal-actions-row" style="display:flex; gap:12px; flex-wrap:wrap; justify-content:center; padding: 0 10px;">
                    ${btn('Assign Seat', 'open_assign', 'btn-primary', { shift: 'full' })}
                    ${btn('🔒 Lock Seat', 'lock_seat', 'btn-lock', { shift: 'full' })}
                </div>`;
        } else {
          const lockedArr = lockedShifts.split(',').filter(Boolean);
          const isAnyShiftLocked = lockedArr.length > 0;
          title = isAnyShiftLocked ? `Seat ${formattedSeat} - Shift Locked` : `Seat ${formattedSeat} - All Shifts Available`;
          
          content = `
              <div class="modal-section" style="padding-top: 10px;">
                <p style="margin-bottom:20px; font-size:1.1rem; text-align:center; color: var(--text-main); font-weight: 500;">
                  ${isAnyShiftLocked ? `Seat ${formattedSeat} has a locked shift.` : `All shifts of Seat ${formattedSeat} are free to allot any student`}
                </p>
                <div style="height: 1px; background: linear-gradient(90deg, transparent, rgba(118, 75, 162, 0.2), transparent); margin: 20px 0;"></div>
                <div class="modal-actions-col" style="padding: 0 10px; gap:12px;">
                    <div class="shift-option-row">
                      <span style="font-weight:600;">Morning Shift:</span>
                      ${lockedArr.includes('morning')
                          ? btn('🔓 Unlock Morning', 'unlock_seat', 'btn-success btn-sm', { shift: 'morning' })
                          : `<div class="shift-option-btn-wrap">${btn('Assign Morning', 'open_assign', 'btn-primary btn-sm', { shift: 'morning' })}${btn('🔒 Lock Morning', 'lock_seat', 'btn-lock btn-sm', { shift: 'morning' })}</div>`
                      }
                    </div>
                    <div class="shift-option-row">
                      <span style="font-weight:600;">Evening Shift:</span>
                      ${lockedArr.includes('evening')
                          ? btn('🔓 Unlock Evening', 'unlock_seat', 'btn-success btn-sm', { shift: 'evening' })
                          : `<div class="shift-option-btn-wrap">${btn('Assign Evening', 'open_assign', 'btn-primary btn-sm', { shift: 'evening' })}${btn('🔒 Lock Evening', 'lock_seat', 'btn-lock btn-sm', { shift: 'evening' })}</div>`
                      }
                    </div>
                    ${!isAnyShiftLocked ? `
                    <div style="height: 1px; background: linear-gradient(90deg, transparent, rgba(118, 75, 162, 0.2), transparent); margin: 15px 0;"></div>
                    <div style="display:flex; flex-direction:column; gap:10px; padding:0 5px;">
                      ${btn('Assign Full Day', 'open_assign', 'btn-primary', { shift: 'full' })}
                      ${btn('🔒 Lock Full Seat', 'lock_seat', 'btn-lock', { shift: 'full' })}
                    </div>` : ''}
                </div>
              </div>`;
        }

      }




      // =================================================================================
      // STATUS #3, #4, #5: OCCUPIED / HOLD
      // =================================================================================
      else {
        if (!isShiftEnabled) {
          // Find hold owner and temp tenant across ALL assignments (not just [0])
          const owner = assignments.find(x => x.hold_status === 'active' && !x.is_partial);
          const tenant = assignments.find(x => x.is_partial && !x.is_pending && x.student_status !== 'pending');
          const pendingTenant = assignments.find(x => x.is_partial && (x.is_pending || x.student_status === 'pending'));
          const regularOccupant = assignments.find(x => !x.is_partial && x.hold_status !== 'active' && !x.is_pending && x.student_status !== 'pending');

          if (owner && tenant) {
            // Case: Hold + Active Temporary Tenant
            title = `Seat ${getFormattedSeatNumber(seatNumber)} - Hold + Temp`;
            const ownerPhotoHtml = `
                <div style="width:36px; height:36px; border-radius:50%; overflow:hidden; border:2px solid #f39c12; flex-shrink:0; background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                    ${owner.photo_url 
                        ? `<img src="${owner.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                        : `<i class='bx bxs-user' style="font-size:1.1rem; color:#cbd5e1;"></i>`
                    }
                </div>`;
            const tenantPhotoHtml = `
                <div style="width:36px; height:36px; border-radius:50%; overflow:hidden; border:2px solid #3498db; flex-shrink:0; background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                    ${tenant.photo_url 
                        ? `<img src="${tenant.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                        : `<i class='bx bxs-user' style="font-size:1.1rem; color:#cbd5e1;"></i>`
                    }
                </div>`;

            content = `
                <div class="shift-block" style="background: rgba(243, 156, 18, 0.05); border-radius: 12px; padding: 15px; margin-bottom: 12px; border: 1px solid rgba(243, 156, 18, 0.15);">
                    <div style="display:flex; align-items:center; gap:12px;">
                        ${ownerPhotoHtml}
                        <p style="margin:0; font-size:0.95rem; color:var(--text-main);">Held by <strong>${escapeHTML(abcdFormatName(owner.student_name))}</strong> (${owner.hold_days} days left)</p>
                    </div>
                </div>
                <div class="shift-block" style="background: rgba(52, 152, 219, 0.05); border-radius: 12px; padding: 15px; margin-bottom: 15px; border: 1px solid rgba(52, 152, 219, 0.15);">
                    <div style="display:flex; align-items:center; gap:12px;">
                        ${tenantPhotoHtml}
                        <p style="margin:0; font-size:0.95rem; color:var(--text-main);">Temp Tenant: <strong>${escapeHTML(abcdFormatName(tenant.student_name))}</strong></p>
                    </div>
                </div>
                <div class="modal-actions-row small-gap">
                    ${btn('End Hold', 'end_hold', 'btn-warning btn-sm', { student_id: owner.student_id })}
                    ${btn('Free Temp', 'free', 'btn-warning btn-sm', { student_id: tenant.student_id })}
                    ${btn('Free Seat', 'free', 'btn-danger btn-sm', { force: true })}
                </div>`;
          } else if (owner && pendingTenant) {
            // Case: Hold + Pending Temporary Request
            title = `Seat ${getFormattedSeatNumber(seatNumber)} - On Hold (Temp Pending)`;
            const ownerPhotoHtml = `
                <div style="width:36px; height:36px; border-radius:50%; overflow:hidden; border:2px solid #f39c12; flex-shrink:0; background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                    ${owner.photo_url 
                        ? `<img src="${owner.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                        : `<i class='bx bxs-user' style="font-size:1.1rem; color:#cbd5e1;"></i>`
                    }
                </div>`;
            const pendingPhotoHtml = `
                <div style="width:36px; height:36px; border-radius:50%; overflow:hidden; border:2px solid #ec4899; flex-shrink:0; background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                    ${pendingTenant.photo_url 
                        ? `<img src="${pendingTenant.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                        : `<i class='bx bxs-user' style="font-size:1.1rem; color:#cbd5e1;"></i>`
                    }
                </div>`;

            content = `
                <div class="shift-block" style="background: rgba(243, 156, 18, 0.05); border-radius: 12px; padding: 15px; margin-bottom: 12px; border: 1px solid rgba(243, 156, 18, 0.15);">
                    <div style="display:flex; align-items:center; gap:12px;">
                        ${ownerPhotoHtml}
                        <p style="margin:0; font-size:0.95rem; color:var(--text-main);">Held by <strong>${escapeHTML(abcdFormatName(owner.student_name))}</strong> (${owner.hold_days} days left)</p>
                    </div>
                </div>
                <div class="shift-block" style="background: rgba(236, 72, 153, 0.05); border-radius: 12px; padding: 15px; margin-bottom: 15px; border: 1px solid rgba(236, 72, 153, 0.15);">
                    <div style="display:flex; align-items:center; gap:12px;">
                        ${pendingPhotoHtml}
                        <p style="margin:0; font-size:0.95rem; color:var(--text-main);">Pending Temp: <strong>${escapeHTML(abcdFormatName(pendingTenant.student_name))}</strong></p>
                    </div>
                </div>
                <div class="modal-actions-row small-gap">
                    ${btn('Allot Temp', 'open_assign', 'btn-primary btn-sm', { shift: 'full' })}
                    ${btn('End Hold', 'end_hold', 'btn-warning btn-sm', { student_id: owner.student_id, student_name: owner.student_name })}
                    ${btn('Free Seat', 'free', 'btn-danger btn-sm', { force: true })}
                </div>`;
          } else if (owner) {
            // Case: Hold only (no temp)
            title = `Seat ${getFormattedSeatNumber(seatNumber)} - On Hold`;
            const ownerPhotoHtml = `
                <div style="width:36px; height:36px; border-radius:50%; overflow:hidden; border:2px solid #f39c12; flex-shrink:0; background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                    ${owner.photo_url 
                        ? `<img src="${owner.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                        : `<i class='bx bxs-user' style="font-size:1.1rem; color:#cbd5e1;"></i>`
                    }
                </div>`;

            content = `
                <div class="shift-block" style="background: rgba(243, 156, 18, 0.05); border-radius: 12px; padding: 15px; margin-bottom: 15px; border: 1px solid rgba(243, 156, 18, 0.15);">
                    <div style="display:flex; align-items:center; gap:12px;">
                        ${ownerPhotoHtml}
                        <p style="margin:0; font-size:0.95rem; color:var(--text-main);">Held by <strong>${escapeHTML(abcdFormatName(owner.student_name))}</strong> (${owner.hold_days} days left)</p>
                    </div>
                </div>
                <div class="modal-actions-row small-gap">
                    ${btn('Allot Temp', 'open_assign', 'btn-primary btn-sm', { shift: 'full' })}
                    ${btn('End Hold', 'end_hold', 'btn-warning btn-sm', { student_id: owner.student_id, student_name: owner.student_name })}
                    ${btn('Free Seat', 'free', 'btn-danger btn-sm', { force: true })}
                </div>`;
          } else if (regularOccupant) {
            // Check for teacher-scheduled future hold (hold_start_date set but not yet active)
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const hasScheduledHold = regularOccupant.hold_start_date &&
              regularOccupant.hold_status !== 'active' &&
              new Date(regularOccupant.hold_start_date) > today;

            if (hasScheduledHold) {
              // Case: Occupied + Upcoming Scheduled Hold (New Request: Show button instead of details)
              const formattedSeat = getFormattedSeatNumber(seatNumber);
              title = `Seat ${formattedSeat} - Occupied`;
              const photoHtml = `
                  <div style="width:40px; height:40px; border-radius:50%; overflow:hidden; border:2px solid #6366f1; box-shadow:0 2px 6px rgba(0,0,0,0.1); flex-shrink:0; background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                      ${regularOccupant.photo_url 
                          ? `<img src="${regularOccupant.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                          : `<i class='bx bxs-user' style="font-size:1.2rem; color:#cbd5e1;"></i>`
                      }
                  </div>`;

              content = `
                <div class="shift-block occupied" style="padding:15px; margin-bottom:15px;">
                  <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
                      ${photoHtml}
                      <p style="margin:0; font-size:1rem; color:var(--text-main);">Occupied by <strong>${escapeHTML(abcdFormatName(regularOccupant.student_name))}</strong></p>
                  </div>
                  <div class="modal-actions-row small-gap">
                    ${btn('📅 Coming Hold Details', 'view_scheduled_hold', 'btn-info btn-sm', { 
                        student_id: regularOccupant.student_id, 
                        student_name: regularOccupant.student_name,
                        hold_start_date: regularOccupant.hold_start_date,
                        hold_end_date: regularOccupant.hold_end_date,
                        shift: 'full'
                    })}
                    ${btn('Put On Hold', 'open_hold', 'btn-warning btn-sm', { student_id: regularOccupant.student_id, shift: 'full' })}
                    ${btn('Free Seat', 'free', 'btn-danger btn-sm', { force: true })}
                  </div>
                </div>`;
            } else {
              // Case: Occupied (no hold, no scheduled hold)
              const formattedSeat = getFormattedSeatNumber(seatNumber);
              title = `Seat ${formattedSeat} - Occupied`;
              const photoHtml = `
                  <div style="width:50px; height:50px; border-radius:50%; overflow:hidden; border:2px solid #6366f1; box-shadow:0 4px 10px rgba(99,102,241,0.2); flex-shrink:0; background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                      ${regularOccupant.photo_url 
                          ? `<img src="${regularOccupant.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                          : `<i class='bx bxs-user' style="font-size:1.8rem; color:#cbd5e1;"></i>`
                      }
                  </div>`;

              content = `
                    <div class="shift-block occupied" style="padding:15px; margin-bottom:15px;">
                        <div style="display:flex; align-items:center; gap:15px;">
                            ${photoHtml}
                            <p style="margin:0; font-size:1.1rem; color:var(--text-main);">Occupied by <strong>${escapeHTML(abcdFormatName(regularOccupant.student_name))}</strong></p>
                        </div>
                    </div>
                    <div class="modal-actions-row small-gap">
                        ${btn('Put On Hold', 'open_hold', 'btn-warning btn-sm', { student_id: regularOccupant.student_id, shift: 'full' })}
                        ${btn('Free Seat', 'free', 'btn-danger btn-sm', { force: true })}
                    </div>`;
            }
          } else if (assignments.length > 0) {
            // Fallback: some assignment exists but doesn't match above cases
            const a = assignments[0];
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            const hasScheduledHold = a.hold_start_date &&
              a.hold_status !== 'active' &&
              new Date(a.hold_start_date) > today;

            const photoHtml = `
                <div style="width:40px; height:40px; border-radius:50%; overflow:hidden; border:2px solid #6366f1; box-shadow:0 2px 6px rgba(0,0,0,0.1); flex-shrink:0; background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                    ${a.photo_url 
                        ? `<img src="${a.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                        : `<i class='bx bxs-user' style="font-size:1.2rem; color:#cbd5e1;"></i>`
                    }
                </div>`;

            if (hasScheduledHold) {
              const formattedSeat = getFormattedSeatNumber(seatNumber);
              title = `Seat ${formattedSeat} - Occupied`;
              content = `
                <div class="shift-block occupied" style="padding:15px; margin-bottom:15px;">
                  <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
                      ${photoHtml}
                      <p style="margin:0; font-size:1rem; color:var(--text-main);">Occupied by <strong>${escapeHTML(abcdFormatName(a.student_name))}</strong></p>
                  </div>
                  <div class="modal-actions-row small-gap">
                    ${btn('📅 Coming Hold Details', 'view_scheduled_hold', 'btn-info btn-sm', { 
                        student_id: a.student_id, 
                        student_name: a.student_name,
                        hold_start_date: a.hold_start_date,
                        hold_end_date: a.hold_end_date,
                        shift: 'full'
                    })}
                    ${btn('Put On Hold', 'open_hold', 'btn-warning btn-sm', { student_id: a.student_id, shift: 'full' })}
                    ${btn('Free Seat', 'free', 'btn-danger btn-sm', { force: true })}
                  </div>
                </div>`;
            } else {
              const formattedSeat = getFormattedSeatNumber(seatNumber);
              title = `Seat ${formattedSeat} - Occupied`;
              content = `
                <div class="shift-block occupied" style="padding:15px; margin-bottom:15px;">
                  <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
                      ${photoHtml}
                      <p style="margin:0; font-size:1rem; color:var(--text-main);">Occupied by <strong>${escapeHTML(abcdFormatName(a.student_name))}</strong></p>
                  </div>
                </div>
                <div class="modal-actions-row small-gap">
                    ${btn('Put On Hold', 'open_hold', 'btn-warning btn-sm', { student_id: a.student_id, shift: 'full' })}
                    ${btn('Free Seat', 'free', 'btn-danger btn-sm', { force: true })}
                </div>`;
            }
          } else {
            content = "<p>Error: Status occupied but no assignment data.</p>";
          }
        }
        else {              // Shift Logic (Complex)
          if (activeFull) {
            const a = activeFull;
            // Check for underlying holds (Case 5c context)
            // If 'a' is a partial tenant, look for owners on hold
            const ownersOnHold = assignments.filter(x => x.hold_status === 'active' && !x.is_partial);

            if (a.is_partial && ownersOnHold.length > 0) {
              // Case 5c: Shift Seat - Both Hold (Different) + One Full Day Temp
              const morningOwner = ownersOnHold.find(x => x.shift === 'morning');
              const eveningOwner = ownersOnHold.find(x => x.shift === 'evening');
              const fullOwner = ownersOnHold.find(x => x.shift === 'full');

              const formattedSeat = getFormattedSeatNumber(seatNumber);
              title = `Seat ${formattedSeat} - Hold + Full Temporary`;
              content = "";

              // Helper for owner rows
              const renderOwnerRow = (owner, label, borderHex) => {
                const ownerName = escapeHTML(abcdFormatName(owner.student_name));
                return `
                  <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
                      <div style="width:36px; height:36px; border-radius:50%; overflow:hidden; border:2px solid ${borderHex}; flex-shrink:0; background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                          ${owner.photo_url 
                              ? `<img src="${owner.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                              : `<i class='bx bxs-user' style="font-size:1.1rem; color:#cbd5e1;"></i>`
                          }
                      </div>
                      <p style="margin:0; font-size:0.9rem; color:var(--text-main);"><strong>${label} Hold</strong> (${owner.hold_days} days): ${ownerName}</p>
                  </div>`;
              };

              content += `<div class="shift-block" style="background: rgba(243, 156, 18, 0.05); border-radius: 12px; padding: 15px; margin-bottom: 15px; border: 1px solid rgba(243, 156, 18, 0.15);">`;
              if (fullOwner) {
                content += renderOwnerRow(fullOwner, 'Full Day', '#f39c12');
              } else {
                if (morningOwner) content += renderOwnerRow(morningOwner, 'Morning', '#f39c12');
                if (eveningOwner) content += renderOwnerRow(eveningOwner, 'Evening', '#f39c12');
              }
              content += `</div>`;

              // Render Temporary Tenant Row
              const tempPhotoHtml = `
                  <div style="width:40px; height:40px; border-radius:50%; overflow:hidden; border:2px solid #3498db; box-shadow:0 2px 6px rgba(0,0,0,0.1); flex-shrink:0; background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                      ${a.photo_url 
                          ? `<img src="${a.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                          : `<i class='bx bxs-user' style="font-size:1.4rem; color:#cbd5e1;"></i>`
                      }
                  </div>`;
              
              content += `
                <div class="shift-block" style="background: rgba(52, 152, 219, 0.05); border-radius: 12px; padding: 15px; margin-bottom: 15px; border: 1px solid rgba(52, 152, 219, 0.15);">
                    <p style="margin-bottom:10px; font-weight:700; color: var(--text-main);">Temporary Tenant</p>
                    <div style="display:flex; align-items:center; gap:12px;">
                        ${tempPhotoHtml}
                        <p style="margin:0; font-size:0.95rem; color:var(--text-main);">Fully Occupied (Temp) by <strong>${escapeHTML(abcdFormatName(a.student_name))}</strong></p>
                    </div>
                </div>
                <div class="modal-actions-row small-gap">
                    <a href="/student/${encodeURIComponent(a.student_id)}" target="_blank" class="btn-action btn-sm btn-info" style="text-decoration:none;">View Temp</a>
                    ${morningOwner ? btn('End M-Hold', 'end_hold', 'btn-warning btn-sm', { student_id: morningOwner.student_id }) : ''}
                    ${eveningOwner ? btn('End E-Hold', 'end_hold', 'btn-warning btn-sm', { student_id: eveningOwner.student_id }) : ''}
                    ${fullOwner ? btn('End Hold', 'end_hold', 'btn-warning btn-sm', { student_id: fullOwner.student_id }) : ''}
                    ${btn('End Temp Allot', 'free', 'btn-danger btn-sm', { student_id: a.student_id })}
                </div>`;
            }
            else if (a.is_partial && ownersOnHold.length === 0) {
              const formattedSeat = getFormattedSeatNumber(seatNumber);
              title = `Seat ${formattedSeat} - Temporary Tenant (No Owner)`;
              const tempPhotoHtml = `
                  <div style="width:40px; height:40px; border-radius:50%; overflow:hidden; border:2px solid #3498db; box-shadow:0 2px 6px rgba(0,0,0,0.1); flex-shrink:0; background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                      ${a.photo_url 
                          ? `<img src="${a.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                          : `<i class='bx bxs-user' style="font-size:1.4rem; color:#cbd5e1;"></i>`
                      }
                  </div>`;
              content = `
                <div class="shift-block" style="background: rgba(52, 152, 219, 0.05); border-radius: 12px; padding: 15px; margin-bottom: 15px; border: 1px solid rgba(52, 152, 219, 0.15);">
                    <div style="display:flex; align-items:center; gap:12px; margin-bottom:10px;">
                        ${tempPhotoHtml}
                        <p style="margin:0; font-size:0.95rem; color:var(--text-main);">Occupied temporarily by <strong>${escapeHTML(abcdFormatName(a.student_name))}</strong></p>
                    </div>
                    <p style="font-size:0.8rem; color:#e74c3c; margin:0;">⚠️ The original owner has been removed.</p>
                </div>
                <div class="modal-actions-row small-gap">
                    ${btn('End Temp', 'free', 'btn-warning btn-sm', { student_id: a.student_id })}
                </div>`;
            }
            else if (a.hold_status === 'active') { // 4c
              const mTenant = assignments.find(x => x.shift === 'morning' && x.is_partial && x.student_status !== 'pending' && !x.is_pending);
              const eTenant = assignments.find(x => x.shift === 'evening' && x.is_partial && x.student_status !== 'pending' && !x.is_pending);

              const formattedSeat = getFormattedSeatNumber(seatNumber);
              title = `Seat ${formattedSeat} - Full Day Hold`;
              
              const ownerPhotoHtml = `
                  <div style="width:40px; height:40px; border-radius:50%; overflow:hidden; border:2px solid #f39c12; box-shadow:0 2px 6px rgba(0,0,0,0.1); flex-shrink:0; background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                      ${a.photo_url 
                          ? `<img src="${a.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                          : `<i class='bx bxs-user' style="font-size:1.4rem; color:#cbd5e1;"></i>`
                      }
                  </div>`;
                  
              content = `
                <div class="shift-block" style="background: rgba(243, 156, 18, 0.05); border-radius: 12px; padding: 15px; margin-bottom: 15px; border: 1px solid rgba(243, 156, 18, 0.15);">
                    <p style="margin-bottom:10px; font-weight:700; color: var(--text-main);">Full Day: <span style="color:#f39c12;">Hold</span></p>
                    <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
                        ${ownerPhotoHtml}
                        <p style="margin:0; font-size:0.95rem; color:var(--text-main);">Full-day hold by <strong>${escapeHTML(abcdFormatName(a.student_name))}</strong></p>
                    </div>
                </div>`;

              if (mTenant || eTenant || (!mTenant || !eTenant)) {
                content += `<div style="height:1px; background:#eee; margin:15px 0;"></div>`;
                
                // Render Morning Temp Section
                content += `<div class="shift-block" style="background: rgba(52, 152, 219, 0.05); border-radius: 12px; padding: 15px; margin-bottom: 12px; border: 1px solid rgba(52, 152, 219, 0.1);">`;
                if (mTenant) {
                  const mTenantPhotoHtml = `
                      <div style="width:36px; height:36px; border-radius:50%; overflow:hidden; border:2px solid #3498db; box-shadow:0 2px 6px rgba(0,0,0,0.1); flex-shrink:0; background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                          ${mTenant.photo_url 
                              ? `<img src="${mTenant.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                              : `<i class='bx bxs-user' style="font-size:1.2rem; color:#cbd5e1;"></i>`
                          }
                      </div>`;
                  content += `
                    <p style="margin-bottom:10px; font-weight:700; color: var(--text-main);">Morning: <span style="color:#3498db;">Temp</span></p>
                    <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
                        ${mTenantPhotoHtml}
                        <p style="margin:0; font-size:0.95rem; color:var(--text-main);">Morning Temp: <strong>${escapeHTML(abcdFormatName(mTenant.student_name))}</strong></p>
                    </div>
                    <div class="modal-actions-row small-gap">
                        ${btn('End M-Temp', 'free', 'btn-warning btn-sm', { student_id: mTenant.student_id })}
                    </div>`;
                } else {
                  content += `
                    <p style="margin-bottom:10px; font-weight:700; color: var(--text-main);">Morning: <span style="color:#2ecc71;">Available</span></p>
                    <div class="modal-actions-row small-gap">
                        ${btn('Turn Full Day Temp', 'open_assign', 'btn-primary btn-sm', { shift: 'morning' })}
                    </div>`;
                }
                content += `</div>`;

                // Render Evening Temp Section
                content += `<div class="shift-block" style="background: rgba(52, 152, 219, 0.05); border-radius: 12px; padding: 15px; margin-bottom: 12px; border: 1px solid rgba(52, 152, 219, 0.1);">`;
                if (eTenant) {
                  const eTenantPhotoHtml = `
                      <div style="width:36px; height:36px; border-radius:50%; overflow:hidden; border:2px solid #3498db; box-shadow:0 2px 6px rgba(0,0,0,0.1); flex-shrink:0; background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                          ${eTenant.photo_url 
                              ? `<img src="${eTenant.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                              : `<i class='bx bxs-user' style="font-size:1.2rem; color:#cbd5e1;"></i>`
                          }
                      </div>`;
                  content += `
                    <p style="margin-bottom:10px; font-weight:700; color: var(--text-main);">Evening: <span style="color:#3498db;">Temp</span></p>
                    <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
                        ${eTenantPhotoHtml}
                        <p style="margin:0; font-size:0.95rem; color:var(--text-main);">Evening Temp: <strong>${escapeHTML(abcdFormatName(eTenant.student_name))}</strong></p>
                    </div>
                    <div class="modal-actions-row small-gap">
                        ${btn('End E-Temp', 'free', 'btn-warning btn-sm', { student_id: eTenant.student_id })}
                    </div>`;
                } else {
                  content += `
                    <p style="margin-bottom:10px; font-weight:700; color: var(--text-main);">Evening: <span style="color:#2ecc71;">Available</span></p>
                    <div class="modal-actions-row small-gap">
                        ${btn('Turn Full Day Temp', 'open_assign', 'btn-primary btn-sm', { shift: 'evening' })}
                    </div>`;
                }
                content += `</div>`;
              }

              content += `
                <div style="height:1px; background:#eee; margin:15px 0;"></div>
                <div class="modal-actions-row small-gap">
                    ${!mTenant && !eTenant ? btn('Allot Temp', 'open_assign', 'btn-primary btn-sm', { shift: 'full' }) : ''}
                    ${btn('End Hold', 'end_hold', 'btn-warning btn-sm', { student_id: a.student_id, student_name: a.student_name })}
                    ${btn('Free Seat', 'free', 'btn-danger btn-sm', { force: true })}
                </div>`;
            } else { // 3c
              const formattedSeat = getFormattedSeatNumber(seatNumber);
              title = `Seat ${formattedSeat} - Full Day`;
              const photoHtml = `
                  <div style="width:50px; height:50px; border-radius:50%; overflow:hidden; border:2px solid #6366f1; box-shadow:0 4px 10px rgba(99,102,241,0.2); flex-shrink:0; background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                      ${a.photo_url 
                          ? `<img src="${a.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                          : `<i class='bx bxs-user' style="font-size:1.8rem; color:#cbd5e1;"></i>`
                      }
                  </div>`;
              content = `
                <div class="shift-block occupied" style="padding:15px; margin-bottom:15px;">
                    <div style="display:flex; align-items:center; gap:15px;">
                        ${photoHtml}
                        <p style="margin:0; font-size:1.1rem; color:var(--text-main);">Fully occupied by <strong>${escapeHTML(abcdFormatName(a.student_name))}</strong></p>
                    </div>
                </div>
                <div class="modal-actions-row small-gap">
                    ${btn('Put On Hold', 'open_hold', 'btn-warning btn-sm', { student_id: a.student_id, shift: 'full' })}
                    ${btn('Free Seat', 'free', 'btn-danger btn-sm', { force: true })}
                </div>`;
            }
          } else {
            // Split Shifts
            ['morning', 'evening'].forEach((shift, idx) => {
              const shiftDisplay = shift.charAt(0).toUpperCase() + shift.slice(1);
              const shiftAssigns = assignments.filter(a => a.shift === shift && a.student_status !== 'pending');
              const owner = shiftAssigns.find(a => !a.is_partial);
              const tenant = shiftAssigns.find(a => a.is_partial);

              // Check if the other shift is available
              const otherShift = (shift === 'morning') ? 'evening' : 'morning';
              const otherAssigns = assignments.filter(a => a.shift === otherShift && a.student_status !== 'pending');
              const otherOwner = otherAssigns.find(a => !a.is_partial);
              const otherTenant = otherAssigns.find(a => a.is_partial);
              const isOtherShiftAvailable = !otherOwner && !otherTenant;

              const showAssignFullDay = owner && isOtherShiftAvailable;

              content += `<div class="shift-block" style="background: rgba(240, 247, 255, 0.5); border-radius: 12px; padding: 15px; margin-bottom: 12px; border: 1px solid rgba(52, 152, 219, 0.1);">`;
              
              if (!owner && !tenant) {
                content += `
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <p style="margin:0; font-weight:700; color: var(--text-main);">${shiftDisplay}: <span style="color:#2ecc71;">Available</span></p>
                        ${btn('Assign', 'open_assign', 'btn-primary btn-sm', { shift: shift })}
                    </div>`;
              } else if (owner && !tenant) {
                const ownerName = escapeHTML(abcdFormatName(owner.student_name));
                const photoHtml = `
                    <div style="width:36px; height:36px; border-radius:50%; overflow:hidden; border:2px solid ${owner.hold_status === 'active' ? '#f39c12' : '#6366f1'}; box-shadow:0 2px 6px rgba(0,0,0,0.1); flex-shrink:0; background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                        ${owner.photo_url 
                            ? `<img src="${owner.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                            : `<i class='bx bxs-user' style="font-size:1.2rem; color:#cbd5e1;"></i>`
                        }
                    </div>`;

                if (owner.hold_status === 'active') {
                  content += `
                    <p style="margin-bottom:10px; font-weight:700; color: var(--text-main);">${shiftDisplay}: <span style="color:#f39c12;">Hold</span></p>
                    <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
                        ${photoHtml}
                        <p style="margin:0; font-size:0.95rem; color:var(--text-main);">On Hold by <strong>${ownerName}</strong></p>
                    </div>
                    <div class="modal-actions-row small-gap">
                        ${btn('Temp', 'open_assign', 'btn-primary btn-sm', { shift })}
                        ${btn('End Hold', 'end_hold', 'btn-warning btn-sm', { student_id: owner.student_id })}
                        ${showAssignFullDay ? btn('Assign full day', 'assign_full_day', 'btn-success btn-sm', { student_id: owner.student_id, student_name: owner.student_name }) : ''}
                        ${btn('Free', 'free_shift', 'btn-danger btn-sm', { shift })}
                    </div>`;
                } else {
                  content += `
                    <p style="margin-bottom:10px; font-weight:700; color: var(--text-main);">${shiftDisplay}: <span style="color:#2ecc71;">Occupied</span></p>
                    <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
                        ${photoHtml}
                        <p style="margin:0; font-size:0.95rem; color:var(--text-main);">Occupied by <strong>${ownerName}</strong></p>
                    </div>
                    <div class="modal-actions-row small-gap">
                        ${btn('Hold', 'open_hold', 'btn-warning btn-sm', { student_id: owner.student_id, shift })}
                        ${showAssignFullDay ? btn('Assign full day', 'assign_full_day', 'btn-success btn-sm', { student_id: owner.student_id, student_name: owner.student_name }) : ''}
                        ${btn('Free', 'free_shift', 'btn-danger btn-sm', { shift })}
                    </div>`;
                }
              } else if (owner && tenant) {
                const ownerName = escapeHTML(abcdFormatName(owner.student_name));
                const tenantName = escapeHTML(abcdFormatName(tenant.student_name));
                const ownerPhotoHtml = `
                    <div style="width:28px; height:28px; border-radius:50%; overflow:hidden; border:2px solid #f39c12; flex-shrink:0; background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                        ${owner.photo_url 
                            ? `<img src="${owner.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                            : `<i class='bx bxs-user' style="font-size:1rem; color:#cbd5e1;"></i>`
                        }
                    </div>`;
                const tenantPhotoHtml = `
                    <div style="width:28px; height:28px; border-radius:50%; overflow:hidden; border:2px solid #3498db; flex-shrink:0; background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                        ${tenant.photo_url 
                            ? `<img src="${tenant.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                            : `<i class='bx bxs-user' style="font-size:1rem; color:#cbd5e1;"></i>`
                        }
                    </div>`;

                content += `
                    <p style="margin-bottom:10px; font-weight:700; color: var(--text-main);">${shiftDisplay}: <span style="color:#f39c12;">Hold</span> + <span style="color:#3498db;">Temp</span></p>
                    <div style="display:flex; flex-direction:column; gap:8px; margin-bottom:12px;">
                        <div style="display:flex; align-items:center; gap:8px;">
                            ${ownerPhotoHtml}
                            <p style="margin:0; font-size:0.85rem; color:#666;">Owner: <strong>${ownerName}</strong></p>
                        </div>
                        <div style="display:flex; align-items:center; gap:8px;">
                            ${tenantPhotoHtml}
                            <p style="margin:0; font-size:0.85rem; color:#666;">Temp: <strong>${tenantName}</strong></p>
                        </div>
                    </div>
                    <div class="modal-actions-row small-gap">
                        ${btn('End Hold', 'end_hold', 'btn-warning btn-sm', { student_id: owner.student_id })} 
                        ${btn('End Temp', 'free', 'btn-warning btn-sm', { student_id: tenant.student_id })}
                    </div>`;
              } else if (!owner && tenant) {
                const tenantName = escapeHTML(abcdFormatName(tenant.student_name));
                const tenantPhotoHtml = `
                    <div style="width:36px; height:36px; border-radius:50%; overflow:hidden; border:2px solid #3498db; box-shadow:0 2px 6px rgba(0,0,0,0.1); flex-shrink:0; background:#f8fafc; display:flex; align-items:center; justify-content:center;">
                        ${tenant.photo_url 
                            ? `<img src="${tenant.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                            : `<i class='bx bxs-user' style="font-size:1.2rem; color:#cbd5e1;"></i>`
                        }
                    </div>`;

                content += `
                    <p style="margin-bottom:10px; font-weight:700; color: var(--text-main);">${shiftDisplay}: <span style="color:#3498db;">Temp</span></p>
                    <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
                        ${tenantPhotoHtml}
                        <p style="margin:0; font-size:0.95rem; color:var(--text-main);">Temp: <strong>${tenantName}</strong> <span style="color:#e74c3c; font-size:0.8rem;">(No Owner)</span></p>
                    </div>
                    <div class="modal-actions-row small-gap">
                        ${btn('End Temp', 'free', 'btn-warning btn-sm', { student_id: tenant.student_id })}
                    </div>`;
              }
              content += `</div>`;
              if (idx === 0) content += `<div style="height:1px; background:#eee; margin:10px 0;"></div>`;
            });
          }
        }
      }

      // Append remaining pending requests at bottom if seat is occupied/on_hold but still has pending requests
      const remainingPending = assignments.filter(a => a.is_pending || a.student_status === 'pending');
      if (remainingPending.length > 0 && !content.includes('pending-requests-list')) {
        content += `<h4 style="margin:22px 0 10px; font-size:0.95rem; font-weight:700; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:5px; color: var(--text-main);">Pending Requests (${remainingPending.length})</h4>`;
        
        content += `<div class="pending-requests-list">`;
        remainingPending.forEach(p => {
          const shiftLabel = shiftLabelMap[p.shift] || p.shift;
          const dateStr = formatDateFriendly(p.created_at);
          
          let actionButtons = `
            ${btn('Delete Request', 'delete_request', 'btn-danger btn-sm', { request_id: p.student_id, shift: p.shift })} 
            ${btn('Approve w/o Seat', 'approve_without_seat', 'btn-warning btn-sm', { request_id: p.student_id, shift: p.shift })}
          `;
          if (p.is_special_request) {
            actionButtons = `
              ${btn('Reject Temp', 'reject_partial_request', 'btn-danger btn-sm', { request_id: p.request_id })} 
              ${btn('Approve Temp', 'approve_partial_request', 'btn-primary btn-sm', { request_id: p.request_id })}
            `;
          }

          content += `
            <div class="request-card conflict">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <div>
                    <div style="display:flex; align-items:center; gap:12px;">
                        <div class="request-avatar-wrap">
                            ${p.photo_url 
                                ? `<img src="${p.photo_url}" style="width:100%; height:100%; object-fit:cover;">` 
                                : `<i class='bx bxs-user' style="font-size:1.5rem; color:#cbd5e1;"></i>`
                            }
                        </div>
                        <div>
                            <p class="request-student-name">
                                <strong>${escapeHTML(abcdFormatName(p.student_name))}</strong>
                            </p>
                            <p class="request-shift-info">
                                ${p.is_special_request ? 'Temporary Request:' : 'Requested:'} ${shiftLabel}
                            </p>
                        </div>
                    </div>
                    <p class="conflict-warning-badge">
                        ⚠️ <strong>Conflict / Pending:</strong> Seat currently occupied by active student.
                    </p>
                    </div>
                    <span class="request-date-badge">${dateStr}</span>
                </div>
                <div class="modal-actions-row" style="margin-top:12px;">
                    ${actionButtons}
                </div>
            </div>
          `;
        });
        content += `</div>`;
      }

      // Update UI
      if (seatDetailsTitle) seatDetailsTitle.textContent = title;
      if (seatDetailsContent) seatDetailsContent.innerHTML = content;

      // DO NOT call openSeatDetailsModal here to avoid recursion.
    } catch (err) {
      console.error('showSeatDetails error:', err);
    }
  }

  // --- Seat Action Handler (Window level) ---
  window.handleSeatAction = async function (action, payload) {
    console.log('Action:', action, payload);

    if (action === 'view_scheduled_hold') {
      const p = payload || {};
      const startStr = new Date(p.hold_start_date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
      const endStr = p.hold_end_date
        ? new Date(p.hold_end_date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
        : '—';
      
      const btn = window._btn || ((l, a, c, pl) => `<button class="btn-action ${c}" onclick="window.handleSeatAction('${a}', ${JSON.stringify(pl).replace(/"/g, '&quot;')})">${l}</button>`);

      const contentHTML = `
        <div class="premium-card" style="border-left: 4px solid #f39c12; background: #fffcf5;">
          <h4 style="margin-bottom: 20px; color: #e67e22; font-weight: 800; display: flex; align-items: center; gap: 10px; font-family: 'Outfit', sans-serif;">
            <i class='bx bx-calendar-event' style='font-size: 1.5rem;'></i> UPCOMING HOLD
          </h4>
          <div class="info-grid" style="margin-bottom: 12px; display: grid; grid-template-columns: 100px 1fr; gap: 10px; font-size: 0.95rem;">
            <span style="color: #64748b; font-weight: 600;">Student:</span>
            <strong style="color: #1e293b;">${escapeHTML(abcdFormatName(p.student_name))}</strong>
          </div>
          <div class="info-grid" style="margin-bottom: 12px; display: grid; grid-template-columns: 100px 1fr; gap: 10px; font-size: 0.95rem;">
            <span style="color: #64748b; font-weight: 600;">Starts:</span>
            <strong style="color: #1e293b;">${startStr}</strong>
          </div>
          <div class="info-grid" style="margin-bottom: 12px; display: grid; grid-template-columns: 100px 1fr; gap: 10px; font-size: 0.95rem;">
            <span style="color: #64748b; font-weight: 600;">Ends:</span>
            <strong style="color: #1e293b;">${endStr}</strong>
          </div>
          <div style="background: rgba(243, 156, 18, 0.08); padding: 15px; border-radius: 12px; margin-top: 15px; border: 1px solid rgba(243, 156, 18, 0.2);">
            <p style="font-size: 0.85rem; color: #d35400; font-weight: 600; margin: 0; line-height: 1.5;">
              <i class='bx bx-alarm'></i> This hold is scheduled but not yet active. It will automatically take effect on the start date.
            </p>
          </div>
        </div>
        <div class="modal-actions-grid" style="margin-top: 25px;">
          ${btn('✏️ Edit Dates', 'open_hold', 'btn-warning', { student_id: p.student_id, shift: p.shift, edit_mode: true })}
          ${btn('🗑️ Delete Hold', 'delete_scheduled_hold', 'btn-danger', { student_id: p.student_id })}
        </div>
        <button class="btn-action btn-secondary" style="margin-top: 20px; width: auto; align-self: center; padding: 10px 25px;" onclick="showSeatDetails(null, true)">
            <i class='bx bx-arrow-back'></i> Back to Seat
        </button>
      `;
      
      if (seatDetailsTitle) seatDetailsTitle.textContent = `Coming Hold - Seat ${getFormattedSeatNumber()}`;
      if (seatDetailsContent) {
        seatDetailsContent.innerHTML = contentHTML;
        // Scroll to top
        seatDetailsContent.parentElement.scrollTop = 0;
      }
      return;
    }

    if (action === 'lock_seat') {
      const p = payload || {};
      const shiftName = p.shift ? (p.shift === 'full' ? 'Full Seat' : p.shift.toUpperCase() + ' Shift') : 'Seat';
      const targetSeatNumber = currentSeatData.seat_number || p.seat_number || '';
      const targetFloor = currentSeatData.floor || currentFloor || 'Ground Floor';
      const targetSeatId = currentSeatData.seat_id || p.seat_id || null;

      const confirmed = await window.showConfirmation({
        title: 'Lock Seat Confirmation',
        mainText: `Lock ${shiftName}?`,
        subText: `Are you sure you want to lock Seat ${targetSeatNumber} (${shiftName})? No student or teacher will be able to occupy this seat until unlocked.`,
        theme: 'warning',
        iconClass: 'bx-lock-alt',
        confirmLabel: 'Yes, Lock Seat'
      });

      if (confirmed) {
        try {
          const resp = await fetch('/api/toggle_seat_lock/', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': CSRF_TOKEN
            },
            body: JSON.stringify({
              seat_id: targetSeatId,
              floor: targetFloor,
              seat_number: targetSeatNumber,
              action: 'lock',
              shift: p.shift || 'full'
            })
          });
          const res = await resp.json();
          if (res.status === 'success') {
            if (window.showToast) window.showToast(res.message, 'success');
            window.closeAllModals();
            currentSeatData = {};
            loadSeatLayout(currentFloor);
          } else {
            window.showStyledPopup({
              title: 'Cannot Lock Seat',
              message: res.message || 'Error locking seat.',
              type: 'error'
            });
          }
        } catch (e) {
          console.error(e);
          if (window.showToast) window.showToast('Failed to lock seat.', 'error');
        }
      }
      return;
    }

    if (action === 'unlock_seat') {
      const p = payload || {};
      const shiftName = p.shift ? (p.shift === 'full' ? 'Full Seat' : p.shift.toUpperCase() + ' Shift') : 'Seat';
      const targetSeatNumber = currentSeatData.seat_number || p.seat_number || '';
      const targetFloor = currentSeatData.floor || currentFloor || 'Ground Floor';
      const targetSeatId = currentSeatData.seat_id || p.seat_id || null;

      const confirmed = await window.showConfirmation({
        title: 'Unlock Seat Confirmation',
        mainText: `Unlock ${shiftName}?`,
        subText: `Are you sure you want to unlock Seat ${targetSeatNumber} (${shiftName})? It will become available for assignment again.`,
        theme: 'primary',
        iconClass: 'bx-lock-open-alt',
        confirmLabel: 'Yes, Unlock Seat'
      });

      if (confirmed) {
        try {
          const resp = await fetch('/api/toggle_seat_lock/', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': CSRF_TOKEN
            },
            body: JSON.stringify({
              seat_id: targetSeatId,
              floor: targetFloor,
              seat_number: targetSeatNumber,
              action: 'unlock',
              shift: p.shift || 'full'
            })
          });
          const res = await resp.json();
          if (res.status === 'success') {
            if (window.showToast) window.showToast(res.message, 'success');
            window.closeAllModals();
            currentSeatData = {};
            loadSeatLayout(currentFloor);
          } else {

            window.showStyledPopup({
              title: 'Cannot Unlock Seat',
              message: res.message || 'Error unlocking seat.',
              type: 'error'
            });
          }
        } catch (e) {
          console.error(e);
          if (window.showToast) window.showToast('Failed to unlock seat.', 'error');
        }
      }
      return;
    }


    if (action === 'assign_full_day') {

      const p = payload || {};
      const studentName = p.student_name || 'the student';
      const confirmed = await window.showConfirmation({
        title: 'Assign Full Day',
        mainText: `Assign Full Day?`,
        subText: `This will upgrade ${abcdFormatName(studentName)} to a Full Day shift on Seat ${currentSeatData.seat_number}.`,
        theme: 'primary',
        iconClass: 'bx-user-check',
        confirmLabel: 'Assign Full Day'
      });
      if (confirmed) {
        await sendSeatAction('allot', p.student_id, true, { shift: 'full' });
      }
      return;
    }

    if (action === 'open_assign') {
      // Check Dashboard Context for Quick Assign
      if (dashboardStudentId) {
        // If we are here, the user clicked "Assign" inside the modal while having a pending dashboard student.
        // Usually, they'd want to assign THAT student.
        const shiftReq = payload.shift || 'full';
        const name = dashboardStudentName || 'Dashboard Student';

        const confirmed = await window.CustomPopup.confirm(
          `Assign ${name} to Seat ${currentSeatData.seat_number} (${shiftReq})?`,
          'Confirm Assignment'
        );
        if (confirmed) {
          sendSeatAction('allot', dashboardStudentId, true, { shift: shiftReq });
        }
        return; // Skip opening modal
      }

      // Normal Flow: Open Assign Modal
      const p = payload || {};
      const targetShift = p.shift || 'full';

      // Check shift locks for current seat
      const lockedShiftsList = (currentSeatData.locked_shifts || '').split(',').filter(Boolean);
      const isFullLocked = !!currentSeatData.is_locked || lockedShiftsList.includes('full');
      const isMorningLocked = isFullLocked || lockedShiftsList.includes('morning');
      const isEveningLocked = isFullLocked || lockedShiftsList.includes('evening');

      // Prevent opening assign modal for locked shifts
      if (targetShift === 'morning' && isMorningLocked) {
        await window.CustomPopup.alert('Morning shift is locked. Please unlock the Morning shift first.', 'Shift Locked');
        return;
      }
      if (targetShift === 'evening' && isEveningLocked) {
        await window.CustomPopup.alert('Evening shift is locked. Please unlock the Evening shift first.', 'Shift Locked');
        return;
      }
      if (targetShift === 'full') {
        if (isMorningLocked && isEveningLocked) {
          await window.CustomPopup.alert(`Seat G-${currentSeatData.seat_number} is locked. Please unlock the seat first.`, 'Seat Locked');
          return;
        }
        if (isMorningLocked) {
          await window.CustomPopup.alert('Morning shift is locked. Please unlock the Morning shift first before assigning Full Day.', 'Shift Locked');
          return;
        }
        if (isEveningLocked) {
          await window.CustomPopup.alert('Evening shift is locked. Please unlock the Evening shift first before assigning Full Day.', 'Shift Locked');
          return;
        }
      }

      window.closeSeatDetailsModal();

      const shiftLabel = p.shift ? shiftLabelMap[p.shift] || p.shift : '';
      if (assignStudentTitle) assignStudentTitle.textContent = `Assign Seat ${currentSeatData.seat_number} ${shiftLabel ? '(' + shiftLabel + ')' : ''}`;

      const shiftWrapper = document.getElementById('assignShiftWrapper');
      const shiftSelect = document.getElementById('assignShiftSelect');

      // PRE-RESET: Clear state before opening
      resetAssignModal();

      if (currentSeatData.is_shift_enabled) {
        if (shiftWrapper) shiftWrapper.style.display = 'block';
        if (shiftSelect) {
          const morningAssign = currentSeatData.assignments ? currentSeatData.assignments.find(a => a.shift === 'morning' && a.student_status !== 'pending') : null;
          const eveningAssign = currentSeatData.assignments ? currentSeatData.assignments.find(a => a.shift === 'evening' && a.student_status !== 'pending') : null;
          
          const isMorningAvailable = !morningAssign && !isMorningLocked;
          const isEveningAvailable = !eveningAssign && !isEveningLocked;
          const isFullAvailable = isMorningAvailable && isEveningAvailable;

          // Rebuild options dynamically based on availability AND lock status
          let optionsHtml = '';
          if (isFullAvailable) {
            optionsHtml += '<option value="full">Full Day (Shift Seat)</option>';
          }
          if (isMorningAvailable) {
            optionsHtml += '<option value="morning">Morning Shift (8 AM - 2 PM)</option>';
          }
          if (isEveningAvailable) {
            optionsHtml += '<option value="evening">Evening Shift (2 PM - 8 PM)</option>';
          }

          if (!optionsHtml) {
            let lockReason = 'All shifts are assigned or locked.';
            if (isMorningLocked && isEveningLocked) lockReason = 'Both shifts are locked. Please unlock a shift first.';
            else if (isMorningLocked) lockReason = 'Morning shift is locked and Evening shift is assigned.';
            else if (isEveningLocked) lockReason = 'Evening shift is locked and Morning shift is assigned.';
            await window.CustomPopup.alert(lockReason, 'Shift Locked');
            return;
          }

          shiftSelect.innerHTML = optionsHtml;
          if (p.shift && shiftSelect.querySelector(`option[value="${p.shift}"]`)) {
            shiftSelect.value = p.shift;
          } else {
            shiftSelect.selectedIndex = 0;
          }
          refreshCustomSelect(shiftSelect);
        }
      } else {
        if (shiftWrapper) shiftWrapper.style.display = 'none';
        if (shiftSelect) {
          shiftSelect.value = 'full';
          refreshCustomSelect(shiftSelect);
        }
      }

      const selectedShift = (shiftSelect && shiftSelect.value) ? shiftSelect.value : (p.shift || 'full');
      lastAssignShift = selectedShift;
      updateAssignTitle(selectedShift);

      // default to library
      if (studentAssignType) {
        studentAssignType.value = 'library';
        refreshCustomSelect(studentAssignType);
      }
      
      toggleAssignModeUI(); 
      loadStudentList('library');
      window.openSmallModal(assignStudentModal);
      return;
    }

    if (action === 'open_hold') {
      window.closeSeatDetailsModal();
      holdConfirmBtn.dataset.studentId = payload.student_id;
      holdConfirmBtn.dataset.shift = payload.shift || 'full';

      // Pre-fill dates if editing an existing scheduled hold
      if (payload.edit_mode) {
        // Find the assignment for this student from current seat data
        const assignee = currentSeatData.assignments
          ? currentSeatData.assignments.find(a => String(a.student_id) === String(payload.student_id))
          : null;
        if (assignee && assignee.hold_start_date && holdStartDate) {
          holdStartDate.value = assignee.hold_start_date;
        }
        if (assignee && assignee.hold_end_date && holdDurationInput) {
          // Calculate days from start to end and fill as duration hint
          const start = new Date(assignee.hold_start_date);
          const end = new Date(assignee.hold_end_date);
          const diffDays = Math.round((end - start) / (1000 * 60 * 60 * 24));
          holdDurationInput.value = diffDays;
        }
      }

      window.openSmallModal(holdModal);
      return;
    }

    if (action === 'delete_scheduled_hold') {
      const confirmed = await window.CustomPopup.confirm(
        '🗑️ Delete this scheduled future hold?<br><br>The student\'s seat remains, but the upcoming hold will be <strong>removed</strong>. The seat stays occupied as normal.',
        'Delete Scheduled Hold',
        true
      );
      if (!confirmed) return;

      sendSeatAction('delete_scheduled_hold', payload.student_id, false, { student_id: payload.student_id });
      return;
    }

    // Handle approve_without_seat - Approve student but don't assign the conflicted seat
    if (action === 'approve_without_seat') {
      const studentId = payload.request_id;
      const studentName = payload.student_name || 'this student';

      const confirmed = await window.CustomPopup.confirm(
        `Approve ${studentName} WITHOUT assigning a seat?<br><br>They will be admitted to the library but will need to have a seat assigned later.`,
        'Approve Without Seat'
      );
      if (!confirmed) {
        return;
      }

      sendSeatAction('approve_without_seat', studentId, false, { skip_seat: true });
      return;
    }

    // Handle edit_pending_seat - Redirect to seat manager to assign a different seat
    if (action === 'edit_pending_seat') {
      const studentId = payload.request_id;
      closeSeatDetailsModal();

      // Set the dashboard context to this student so when they click a seat, it assigns to them
      dashboardStudentId = studentId;
      dashboardStudentName = payload.student_name || 'Student';

      // Update UI to show edit mode
      if (editModeBar) {
        const nameSpan = editModeBar.querySelector('.edit-mode-student-name');
        if (nameSpan) nameSpan.textContent = abcdFormatName(dashboardStudentName);
        editModeBar.style.display = 'flex';
      }

      await window.CustomPopup.alert(
        `Now click on any available seat to assign it to ${dashboardStudentName}.<br><br>Click the ✕ in the yellow bar to cancel.`,
        'Edit Seat Mode'
      );
      return;
    }

    // Direct API Actions
    let apiAction = action;
    let bodyPayload = payload;

    if (['delete_request', 'free', 'free_shift', 'end_hold'].includes(action)) {
      let confirmed = false;
      const studentName = payload ? (payload.student_name || 'this student') : 'this student';

      const getAssignmentRelation = (a) => {
        const shiftLabel = a.shift === 'full' ? 'Full Day' : (a.shift === 'morning' ? 'Morning Shift' : 'Evening Shift');
        if (a.hold_status === 'active') {
          return `${shiftLabel} (Owner on Hold)`;
        } else if (a.is_partial) {
          return `${shiftLabel} (Temporary Tenant)`;
        } else {
          return `${shiftLabel} (Permanent Occupant)`;
        }
      };

      if (action === 'delete_request') {
        confirmed = await window.showConfirmation({
          title: 'Delete Seat Request',
          mainText: `Delete request for ${abcdFormatName(studentName)}?`,
          subText: `This will decline and remove the pending seat request for Seat ${currentSeatData.seat_number}.`,
          theme: 'danger',
          iconClass: 'bx-trash',
          confirmLabel: 'Delete Request'
        });
      } else if (action === 'end_hold') {
        confirmed = await window.showConfirmation({
          title: 'End Seat Hold',
          mainText: `End hold for ${abcdFormatName(studentName)}?`,
          subText: `This will end the hold and restore the student's status on Seat ${currentSeatData.seat_number}.`,
          theme: 'warning',
          iconClass: 'bx-calendar-minus',
          confirmLabel: 'End Hold'
        });
      } else if (action === 'free_shift') {
        const shift = payload.shift;
        const shiftDisplay = shift === 'morning' ? 'Morning Shift' : 'Evening Shift';
        const assigns = currentSeatData.assignments 
          ? currentSeatData.assignments.filter(a => a.shift === shift && a.student_status !== 'pending' && !a.is_pending)
          : [];
        
        let relationsHtml = '';
        if (assigns.length > 0) {
          relationsHtml = '<ul style="text-align: left; margin: 15px 0; padding-left: 20px; font-size: 0.95rem; color: #475569;">';
          assigns.forEach(a => {
            relationsHtml += `<li><strong>${escapeHTML(abcdFormatName(a.student_name))}</strong> - ${getAssignmentRelation(a)}</li>`;
          });
          relationsHtml += '</ul>';
        }

        confirmed = await window.showConfirmation({
          title: `Free ${shiftDisplay}`,
          mainText: `Are you sure you want to free the ${shiftDisplay}?`,
          subText: assigns.length > 0 
            ? `This will remove the following student(s) from this shift on Seat ${currentSeatData.seat_number}:<br>${relationsHtml}`
            : `This will clear all assignments on the ${shiftDisplay} for Seat ${currentSeatData.seat_number}.`,
          theme: 'danger',
          iconClass: 'bx-trash',
          confirmLabel: 'Free Shift'
        });
      } else if (action === 'free') {
        if (payload && payload.force) {
          // Free Entire Seat
          const activeAssigns = currentSeatData.assignments 
            ? currentSeatData.assignments.filter(a => a.student_status !== 'pending' && !a.is_pending)
            : [];
          
          let relationsHtml = '';
          if (activeAssigns.length > 0) {
            relationsHtml = '<ul style="text-align: left; margin: 15px 0; padding-left: 20px; font-size: 0.95rem; color: #475569;">';
            activeAssigns.forEach(a => {
              relationsHtml += `<li><strong>${escapeHTML(abcdFormatName(a.student_name))}</strong> - ${getAssignmentRelation(a)}</li>`;
            });
            relationsHtml += '</ul>';
          }

          confirmed = await window.showConfirmation({
            title: 'Free Entire Seat',
            mainText: `Are you sure you want to free Seat ${currentSeatData.seat_number}?`,
            subText: `This will completely free the seat and remove ALL related student assignments:<br>${relationsHtml}`,
            theme: 'danger',
            iconClass: 'bx-trash',
            confirmLabel: 'Free Seat'
          });
        } else {
          // Free Single Temp Tenant
          confirmed = await window.showConfirmation({
            title: 'End Temporary Allotment',
            mainText: `End temporary allotment for ${abcdFormatName(studentName)}?`,
            subText: `This will remove the temporary tenant from Seat ${currentSeatData.seat_number}. The permanent owner's hold status will be preserved.`,
            theme: 'warning',
            iconClass: 'bx-user-minus',
            confirmLabel: 'End Allotment'
          });
        }
      }

      if (!confirmed) return;
    }

    // =======================================================================
    // REAL-TIME AVAILABILITY CHECK FOR APPROVE_PENDING
    // =======================================================================
    const targetStudentId = (action === 'free' && payload && payload.force) ? null : (payload ? payload.student_id : null);

    if (action === 'approve_pending' && currentSeatData && currentSeatData.floor && currentSeatData.seat_number) {
      const requestedShift = payload.shift || 'full';

      // Show loading indicator
      if (seatDetailsContent) {
        seatDetailsContent.innerHTML += '<div id="checkingAvailability" style="position:absolute; top:0; left:0; right:0; bottom:0; background:rgba(255,255,255,0.9); display:flex; align-items:center; justify-content:center; z-index:100;"><span style="font-size:1rem; color:#333;">⏳ Checking availability...</span></div>';
      }

      try {
        const result = await checkRealTimeSeatAvailability(
          currentSeatData.floor,
          currentSeatData.seat_number,
          requestedShift
        );

        const checkingEl = document.getElementById('checkingAvailability');
        if (checkingEl) checkingEl.remove();

        if (result.isConflict) {
          const conflictMsg = result.message || 'This seat/shift is already occupied.';

          const safeConflictMsg = escapeHTML(conflictMsg);
          const safeRequestId = escapeHTML(payload.request_id);
          const safeShift = escapeHTML(payload.shift);
          const safeFloor = escapeHTML(currentSeatData.floor);
          const conflictHTML = `
            <div style="background:#fff3cd; border:1px solid #f0ad4e; border-radius:8px; padding:20px; margin:10px 0;">
              <p style="color:#856404; font-weight:600; font-size:1.1rem; margin-bottom:10px;">⚠️ Seat Conflict Detected!</p>
              <p style="color:#856404; margin-bottom:15px;">${safeConflictMsg}</p>
              <p style="color:#856404; font-size:0.9rem; margin-bottom:15px;">
                The seat was taken while this request was pending. You can:
              </p>
              <div style="display:flex; gap:10px; flex-wrap:wrap;">
                <button class="btn-action btn-warning" onclick="window.handleSeatAction('approve_without_seat', {request_id: '${safeRequestId}', shift: '${safeShift}'})">Approve w/o Seat</button>
                <button class="btn-action btn-info" onclick="window.handleSeatAction('edit_pending_seat', {request_id: '${safeRequestId}', shift: '${safeShift}'})">Edit Seat</button>
                <button class="btn-action btn-secondary" onclick="loadSeatLayout('${safeFloor}')">Refresh View</button>
              </div>
            </div>
          `;

          if (seatDetailsContent) {
            seatDetailsContent.innerHTML = conflictHTML;
          }
          return;
        }

        window.sendSeatAction(apiAction, targetStudentId, false, bodyPayload);
      } catch (err) {
        console.error('Real-time check error:', err);
        const checkingEl = document.getElementById('checkingAvailability');
        if (checkingEl) checkingEl.remove();
        const proceed = await window.CustomPopup.confirm(
          'Could not verify seat availability. Proceed with approval anyway?',
          'Seat Check Failed'
        );
        if (proceed) {
          window.sendSeatAction(apiAction, targetStudentId, false, bodyPayload);
        }
      }
      return;
    }

    window.sendSeatAction(apiAction, targetStudentId, false, bodyPayload);
  };


  // --- Helpers for Modal ---
  window.openSeatDetailsModal = function(seatEl) {
    if (!seatDetailsModal || !modalOverlay) return;
    
    // Populate details first
    showSeatDetails(seatEl);

    // Use openSmallModal to ensure consistent overlay logic
    window.openSmallModal(seatDetailsModal);
  };

  window.closeSeatDetailsModal = function() {
    window.closeSmallModal(seatDetailsModal);
  };

  // Centralized Modal State Sync
  window.syncGlobalModalState = function(closingEl = null) {
    const allModals = Array.from(document.querySelectorAll('.admission-modal.active, .teacher-modal.open, .seat-modal-container.open'));
    const activeModals = closingEl ? allModals.filter(m => m !== closingEl) : allModals;
    const activePopup = document.querySelector('.custom-popup.visible');
    
    const isAnyActive = activeModals.length > 0 || activePopup;

    if (isAnyActive) {
      document.body.classList.add('modal-open');
      if (modalOverlay) {
        modalOverlay.style.display = 'block';
        modalOverlay.classList.add('active');
      }
    } else {
      // 🚀 INSTANT BLUR REMOVAL (User Requirement)
      document.body.classList.remove('modal-open');
      if (modalOverlay) modalOverlay.classList.remove('active');

      // Clear any pending cleanup timeout
      if (window._overlayCloseTimeout) {
        clearTimeout(window._overlayCloseTimeout);
      }
      
      // Separate cleanup for display:none and structural pieces (can be delayed for transitions)
      window._overlayCloseTimeout = setTimeout(() => {
        const stillActiveModals = document.querySelectorAll('.admission-modal.active, .teacher-modal.open, .seat-modal-container.open');
        const stillActivePopup = document.querySelector('.custom-popup.visible');
        
        if (stillActiveModals.length === 0 && !stillActivePopup) {
          if (modalOverlay) modalOverlay.style.display = 'none';
          
          // Cleanup all hidden modals
          document.querySelectorAll('.admission-modal, .teacher-modal').forEach(m => {
            if (!m.classList.contains('active') && !m.classList.contains('open')) {
              m.style.display = 'none';
            }
          });
        }
        window._overlayCloseTimeout = null;
      }, 350); 
    }
  };

  window.openSmallModal = function(modalEl) {
    if (!modalEl) return;
    
    // Dim and blur all currently active lower modals
    const activeModals = Array.from(document.querySelectorAll('.admission-modal.active, .teacher-modal.open, .seat-modal-container.open'));
    activeModals.forEach(m => {
      if (m !== modalEl) {
        m.classList.add('modal-stacked-parent');
      }
    });

    // Dynamic z-index for top modal elevation
    const stackLevel = activeModals.length + 1;
    modalEl.style.zIndex = 2000 + (stackLevel * 10);
    
    modalEl.style.display = 'flex';
    modalEl.offsetHeight; // force reflow
    modalEl.classList.add('active');
    modalEl.classList.remove('modal-stacked-parent');
    
    window.syncGlobalModalState();
  };

  window.closeSmallModal = function(modalEl) {
    if (!modalEl) return;
    modalEl.classList.remove('active', 'modal-stacked-parent');

    if (typeof window.setButtonLoading === 'function' && actionFinalConfirm) {
      window.setButtonLoading(actionFinalConfirm, false);
    }
    
    // Restore focus to top remaining modal
    const remainingModals = Array.from(document.querySelectorAll('.admission-modal.active, .teacher-modal.open, .seat-modal-container.open'))
      .filter(m => m !== modalEl);
    if (remainingModals.length > 0) {
      const topModal = remainingModals[remainingModals.length - 1];
      topModal.classList.remove('modal-stacked-parent');
    }

    // 🚀 INSTANT SYNC (Remove blur immediately)
    window.syncGlobalModalState(modalEl);

    // Delayed display:none for animation
    setTimeout(() => {
      if (!modalEl.classList.contains('active')) {
        modalEl.style.display = 'none';
        modalEl.style.zIndex = '';
      }
    }, 350);
  };

  // 🚀 AUTOMATICALLY CLOSE ALL MODALS ON ACTION EXECUTION
  window.closeAllModals = function() {
    if (typeof window.setButtonLoading === 'function' && actionFinalConfirm) {
      window.setButtonLoading(actionFinalConfirm, false);
    }
    const allModals = document.querySelectorAll('.admission-modal, .teacher-modal, .seat-modal-container, .custom-popup');
    allModals.forEach(m => {
      m.classList.remove('active', 'open', 'visible', 'modal-stacked-parent');
      m.style.display = 'none';
      m.style.zIndex = '';
    });
    const overlay = document.getElementById('admissionModalOverlay') || document.getElementById('teacherPremiumOverlay');
    if (overlay) {
      overlay.classList.remove('active', 'visible');
      overlay.style.display = 'none';
    }
    document.body.classList.remove('modal-open');
  };

  window.openModal = window.openSmallModal;

  /**
   * Reset Assign Modal State
   */
  function resetAssignModal() {
    // 1. Reset manual form fields
    resetManualForm();
    
    // 2. Reset student source
    if (studentAssignType) {
      studentAssignType.value = 'library';
      refreshCustomSelect(studentAssignType);
    }
    
    // 3. Reset student select
    if (studentAssignSelect) {
      studentAssignSelect.innerHTML = '<option value="">-- Select a student --</option>';
      studentAssignSelect.value = '';
      refreshCustomSelect(studentAssignSelect);
    }

    // 4. Sync UI
    toggleAssignModeUI();
  }

  function updateAssignTitle(shiftValue) {
    const label = shiftLabelMap[shiftValue] || shiftValue || '';
    if (assignStudentTitle) {
      assignStudentTitle.textContent = `Assign Seat ${getFormattedSeatNumber()} ${label ? '(' + label + ')' : ''}`.trim();
    }
  }

  // -------------------------------------------------------------------------
  // API ACTIONS (Attached to window so HTML buttons can see them)
  // -------------------------------------------------------------------------
  window.sendSeatAction = async function (action, studentId = null, reassign = false, customPayload = {}) {
    if (!currentSeatData || !currentSeatData.seat_number) {
      await window.CustomPopup.alert('No seat selected.', 'Error');
      return;
    }
    const body = {
      floor: currentSeatData.floor,
      seat_number: currentSeatData.seat_number,
      action,
      student_id: studentId,
      confirm_reassign: reassign,
      payload: customPayload
    };
    try {
      if (seatDetailsModal) seatDetailsModal.querySelectorAll('.btn-action').forEach(b => b.disabled = true);
      const res = await fetch(API_SEAT_ACTION_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
        body: JSON.stringify(body)
      });
      const result = await res.json().catch(() => ({ message: 'Invalid JSON in response' }));

      if (!res.ok) {
        if (result.status === 'conflict' || res.status === 409) {
          showConflictResolution(result);
          return;
        }
        throw new Error(result.message || `Server returned ${res.status}`);
      }

      await window.CustomPopup.showResult(result.message || 'Action completed', true);
      window.closeAllModals();
      currentSeatData = {};
      loadSeatLayout(currentFloor);
      studentListCache = { library: null, coaching: null, alumni: null }; // clear cache
    } catch (err) {
      console.error('sendSeatAction error:', err);
      // Don't show redundant error if we already showed conflict modal
      if (!conflictModal?.classList.contains('open')) {
        await window.CustomPopup.showResult('Error: ' + (err.message || err), false);
      }
    } finally {
      if (seatDetailsModal) seatDetailsModal.querySelectorAll('.btn-action').forEach(b => b.disabled = false);
    }
  };

  /**
   * Conflict Resolution Modal handler
   * Handles multiple conflict types:
   * - student_has_seat: Student being assigned already has another seat
   * - seat_occupied: Target seat has existing occupant
   */
  async function showConflictResolution(data) {
    const conflictType = data.conflict_type || 'seat_occupied';

    // Handle 'student_has_seat' conflict with custom popup
    if (conflictType === 'student_has_seat') {
      const studentName = data.student_name || 'This student';
      const existingSeat = data.existing_seat || '?';
      const studentId = data.student_id;

      const result = await window.CustomPopup.show({
        title: '⚠️ Student Has Existing Seat',
        message: `
          <div style="background: linear-gradient(135deg, #fff8e1 0%, #ffecb3 100%); padding: 20px; border-radius: 12px; border-left: 4px solid #ff9800;">
            <p style="font-size: 1.05rem; margin-bottom: 12px; color: #e65100; font-weight: 600;">
              <strong>${studentName}</strong> already has Seat ${existingSeat}
            </p>
            <p style="font-size: 0.95rem; line-height: 1.6; color: #5d4037; margin-bottom: 8px;">
              Do you want to remove their current seat and assign them to this new seat?
            </p>
            <p style="font-size: 0.85rem; color: #795548; font-style: italic;">
              This will deactivate their current assignment and any pending requests.
            </p>
          </div>
        `,
        type: 'confirm',
        buttons: [
          { label: '✓ Yes, Reassign', value: 'reassign', class: 'btn-primary' },
          { label: '✕ Cancel', value: null, class: 'btn-secondary' }
        ]
      });

      if (result === 'reassign') {
        // Retry with force flag
        const shift = lastAssignShift || 'full';
        await window.sendSeatAction('allot', studentId, true, { shift: shift, force: true });
      }
      return;
    }

    // Original conflict handling for seat_occupied
    const modal = conflictModal;
    const content = document.getElementById('conflictResolutionContent');
    const reallotSection = document.getElementById('conflictReallotmentSection');

    if (!modal || !content) {
      // Fallback to custom popup if modal not found
      const occupierName = abcdFormatName(data.occupier?.name) || 'another student';
      const seatNum = data.seat_number || currentSeatData?.seat_number;

      const result = await window.CustomPopup.show({
        title: '🔴 Seat Conflict',
        message: `
          <div style="background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%); padding: 20px; border-radius: 12px; border-left: 4px solid #f44336;">
            <p style="font-size: 1.05rem; margin-bottom: 12px; color: #c62828; font-weight: 600;">
              Seat ${seatNum} is already occupied by <strong>${occupierName}</strong>
            </p>
            <p style="font-size: 0.95rem; line-height: 1.6; color: #5d4037; margin-bottom: 8px;">
              Would you like to remove them and assign this seat to the new student?
            </p>
          </div>
        `,
        type: 'confirm',
        buttons: [
          { label: '🔄 Force Reassign', value: 'force', class: 'btn-warning' },
          { label: '📝 Pick Different Seat', value: 'pick_new', class: 'btn-info' },
          { label: '✕ Cancel', value: null, class: 'btn-secondary' }
        ]
      });

      if (result === 'force' && data.student_id) {
        await window.sendSeatAction('allot', data.student_id, true, {
          shift: data.requested_student?.shift || 'full',
          force: true
        });
      } else if (result === 'pick_new' && data.requested_student?.id) {
        dashboardStudentId = data.requested_student.id;
        dashboardStudentName = data.requested_student.name || 'Student';
        if (editModeBar) {
          const nameSpan = editModeBar.querySelector('.edit-mode-student-name');
          if (nameSpan) nameSpan.textContent = abcdFormatName(dashboardStudentName);
          editModeBar.style.display = 'flex';
        }
        await window.CustomPopup.alert(
          `Now click on any available seat to assign it to ${dashboardStudentName}.<br><br>Click the ✕ in the yellow bar to cancel.`,
          'Edit Seat Mode'
        );
      }
      return;
    }

    // Fill Content for existing modal
    const sName = escapeHTML(abcdFormatName(data.requested_student?.name) || "the student");
    const oName = escapeHTML(abcdFormatName(data.occupier?.name) || "another student");
    const shift = escapeHTML(data.occupier?.shift || data.requested_student?.shift || "the same");

    // --- Build conflict modal with safe DOM construction (XSS prevention) ---
    content.textContent = ''; // Clear safely

    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%); padding: 20px; border-radius: 12px; border-left: 4px solid #f44336;';

    const titleP = document.createElement('p');
    titleP.style.cssText = 'font-size: 1.1rem; margin-bottom: 15px; color: #c62828; font-weight: 600;';
    titleP.textContent = `⚠️ Seat ${data.seat_number || ''} Conflict`;
    wrapper.appendChild(titleP);

    const descP = document.createElement('p');
    descP.style.cssText = 'font-size: 0.95rem; line-height: 1.6; color: #333; margin-bottom: 10px;';
    const descStrong = document.createElement('strong');
    descStrong.textContent = oName;
    descP.appendChild(descStrong);
    descP.appendChild(document.createTextNode(` is already assigned to this ${shift} shift.`));
    wrapper.appendChild(descP);

    const actionP = document.createElement('p');
    actionP.style.cssText = 'font-size: 0.95rem; line-height: 1.6; color: #555; margin-bottom: 15px;';
    actionP.appendChild(document.createTextNode('Choose an action for '));
    const actionStrong = document.createElement('strong');
    actionStrong.textContent = sName;
    actionP.appendChild(actionStrong);
    actionP.appendChild(document.createTextNode(':'));
    wrapper.appendChild(actionP);

    const btnDiv = document.createElement('div');
    btnDiv.className = 'modal-actions-row';
    btnDiv.style.marginTop = '15px';

    const forceBtnEl = document.createElement('button');
    forceBtnEl.id = 'conflictForceBtn';
    forceBtnEl.className = 'btn-action btn-warning';
    forceBtnEl.style.cssText = 'padding: 10px 18px; border-radius: 8px;';
    forceBtnEl.textContent = `🔄 Force Assign (Remove ${oName})`;
    btnDiv.appendChild(forceBtnEl);

    const rejectBtnEl = document.createElement('button');
    rejectBtnEl.id = 'conflictRejectBtn2';
    rejectBtnEl.className = 'btn-action btn-danger';
    rejectBtnEl.style.cssText = 'padding: 10px 18px; border-radius: 8px;';
    rejectBtnEl.textContent = '🗑️ Reject Request';
    btnDiv.appendChild(rejectBtnEl);

    const pickBtnEl = document.createElement('button');
    pickBtnEl.id = 'conflictPickBtn';
    pickBtnEl.className = 'btn-action btn-info';
    pickBtnEl.style.cssText = 'padding: 10px 18px; border-radius: 8px;';
    pickBtnEl.textContent = '📝 Pick Different Seat';
    btnDiv.appendChild(pickBtnEl);

    wrapper.appendChild(btnDiv);
    content.appendChild(wrapper);

    if (reallotSection) reallotSection.style.display = 'none'; // Hide old buttons

    const closeModal = () => {
      modal.classList.remove('open');
      modal.style.display = 'none';
      if (modalOverlay) modalOverlay.classList.remove('visible');
      document.body.classList.remove('modal-open');
    };

    // Wire up new buttons
    const forceBtn = document.getElementById('conflictForceBtn');
    const rejectBtn2 = document.getElementById('conflictRejectBtn2');
    const pickBtn = document.getElementById('conflictPickBtn');
    const closeX = document.getElementById('closeConflictModal');

    if (forceBtn) {
      forceBtn.onclick = async () => {
        const confirmed = await window.CustomPopup.confirm(
          `This will remove <strong>${oName}</strong> from the seat and assign it to <strong>${sName}</strong>.<br><br>Are you sure?`,
          'Confirm Force Assign'
        );
        if (confirmed) {
          closeModal();
          await window.sendSeatAction('allot', data.requested_student?.id || data.student_id, true, {
            shift: shift,
            force: true
          });
        }
      };
    }

    if (rejectBtn2) {
      rejectBtn2.onclick = async () => {
        const confirmed = await window.CustomPopup.confirm(
          `Reject ${sName}'s request for this seat?`,
          'Reject Request'
        );
        if (confirmed) {
          closeModal();
          await window.sendSeatAction('delete_request', data.requested_student?.id, false, {
            shift: data.requested_student?.shift || 'full',
            request_id: data.requested_student?.request_id
          });
        }
      };
    }

    if (pickBtn) {
      pickBtn.onclick = () => {
        closeModal();
        dashboardStudentId = data.requested_student?.id;
        dashboardStudentName = sName;
        if (editModeBar) {
          const nameSpan = editModeBar.querySelector('.edit-mode-student-name');
          if (nameSpan) nameSpan.textContent = abcdFormatName(dashboardStudentName);
          editModeBar.style.display = 'flex';
        }
        window.CustomPopup.alert(
          `Now click on any available seat to assign it to ${sName}.<br><br>Click the ✕ in the yellow bar to cancel.`,
          'Edit Seat Mode'
        );
      };
    }

    if (closeX) closeX.onclick = closeModal;

    // Open Modal
    modal.classList.add('open');
    modal.style.display = 'block';
    if (modalOverlay) modalOverlay.classList.add('visible');
    document.body.classList.add('modal-open');
  }

  // --- Helper for Scenario A (Stranger taking Hold Seat) ---
  window.assignFullDayTempFromSeat = function () {
    // 1. Close the detail modal
    closeSeatDetailsModal();

    // 2. Open the Assign Modal
    if (assignStudentTitle) assignStudentTitle.textContent = `Assign Temp Full Day (Seat ${currentSeatData.seat_number})`;

    // 3. Force "Full Day" in the logic (hide selection to avoid confusion)
    const shiftSelect = document.getElementById('assignShiftSelect');
    const shiftWrapper = document.getElementById('assignShiftWrapper');

    if (shiftSelect) shiftSelect.value = 'full';
    if (shiftWrapper) shiftWrapper.style.display = 'none';

    // 4. Load list and show
    if (studentAssignType) studentAssignType.value = 'library';
    toggleAssignModeUI();
    loadStudentList('library');
    openSmallModal(assignStudentModal);
  };


  // Close icons (top-right X button)
  document.getElementById("closeSeatDetails")?.addEventListener("click", closeSeatDetailsModal);

  document.getElementById("closeAssignModal")?.addEventListener("click", () => {
    resetAssignModal(); // Reset state on close
    window.closeSmallModal(assignStudentModal);
  });


  // --- Event listeners & delegation ---
  if (floorSelector) floorSelector.addEventListener('change', () => loadSeatLayout(floorSelector.value));

  function attachSeatClicks(wrapper) {
    if (!wrapper) return;
    wrapper.addEventListener('click', (e) => {
      const seatEl = e.target.closest('.seat');
      if (!seatEl) return;
      if (seatEl.classList.contains('empty-space') || seatEl.classList.contains('special')) return;
      if (window.getComputedStyle(wrapper).display === 'none') return;
      openSeatDetailsModal(seatEl);
    });
  }
  attachSeatClicks(groundFloorWrapper);
  attachSeatClicks(firstFloorWrapper);

  // close buttons (global)
  if (allCloseButtons && allCloseButtons.length) {
    allCloseButtons.forEach(btn => btn.addEventListener('click', (ev) => {
      ev.preventDefault();
      const parentModal = btn.closest('.teacher-modal, .admission-modal');
      if (!parentModal) return;
      window.closeSmallModal(parentModal);
    }));
  }

  if (modalOverlay) modalOverlay.addEventListener('click', window.closeSeatDetailsModal);

  if (allModals && allModals.length) {
    allModals.forEach(m => m.addEventListener('click', e => e.stopPropagation()));
  }



  // --- Assign flow (UPDATED with Shift Support) ---
  if (actionAssignStudent) {
    actionAssignStudent.addEventListener('click', async () => {
      if (!currentSeatData || !currentSeatData.seat_number) return;

      // 🔹 Special case: came from Teacher Dashboard "Edit seat" button
      if (dashboardStudentId) {
        if (currentSeatData.status !== 'available') {
          await window.CustomPopup.alert(
            'This seat is not available. Please click on an empty (available) seat to allot.',
            'Seat Unavailable'
          );
          return;
        }
        const name = dashboardStudentName || 'this student';
        const floorLabel = currentSeatData.floor || currentFloor || '';

        // Simple prompt for shift if in dashboard mode (since we skip the modal)
        let shiftReq = 'full';
        // You could add a prompt here, but for simplicity we default to 'full' or ask via confirm
        // To keep it robust, let's just ask:
        if (currentSeatData.is_shift_enabled) {

          const shiftChoice = await window.CustomPopup.show({
            title: 'Select Shift',
            message: `Choose the shift for <strong>${name}</strong> on Seat ${currentSeatData.seat_number}.`,
            type: 'confirm',
            buttons: [
              { label: 'Morning', value: 'morning', class: 'btn-primary' },
              { label: 'Evening', value: 'evening', class: 'btn-primary' },
              { label: 'Full Day', value: 'full', class: 'btn-primary' },
              { label: 'Cancel', value: null, class: 'btn-secondary' }
            ]
          });
          if (!shiftChoice) return;
          shiftReq = shiftChoice;
        }

        const msg = `Allot Seat ${currentSeatData.seat_number} (${floorLabel}) [${shiftReq}] to "${name}"?`;
        const confirmed = await window.CustomPopup.confirm(msg, 'Confirm Allotment');
        if (!confirmed) return;

        // Pass shift in customPayload
        await sendSeatAction('allot', dashboardStudentId, true, { shift: shiftReq });
        return;
      }

      // PRE-RESET
      resetAssignModal();

      // Ensure we have a valid shift
      const payloadShift = payload && payload.shift ? payload.shift : 'full';
      updateAssignTitle(payloadShift);


      // --- NEW: Toggle Shift Dropdown Visibility ---
      const shiftWrapper = document.getElementById('assignShiftWrapper');
      const shiftSelect = document.getElementById('assignShiftSelect');

      // --------------------------------------------------
      // STEP 2.4 — Enforce shift availability (Teacher UI)
      // --------------------------------------------------
      if (shiftWrapper && shiftSelect) {

        // Reset all options first
        Array.from(shiftSelect.options).forEach(opt => {
          opt.disabled = false;
        });

        const seatEl = document.querySelector(
          `.seat[data-seat-id="${currentSeatData.seat_number}"]`
        );

        if (seatEl) {
          const morningTaken = seatEl.classList.contains('shift-morning') || seatEl.classList.contains('shift-split');
          const eveningTaken = seatEl.classList.contains('shift-evening') || seatEl.classList.contains('shift-split');
          const fullTaken = seatEl.classList.contains('occupied');

          // Full-day not allowed if any shift is occupied
          if (morningTaken || eveningTaken) {
            const fullOpt = shiftSelect.querySelector('option[value="full"]');
            if (fullOpt) fullOpt.disabled = true;
          }

          // Disable individual shifts if occupied
          if (morningTaken) {
            const opt = shiftSelect.querySelector('option[value="morning"]');
            if (opt) opt.disabled = true;
          }

          if (eveningTaken) {
            const opt = shiftSelect.querySelector('option[value="evening"]');
            if (opt) opt.disabled = true;
          }

          // Auto-select first enabled option
          const firstValid = Array.from(shiftSelect.options).find(o => !o.disabled);
          if (firstValid) shiftSelect.value = firstValid.value;
        }

        const initialShift = shiftSelect.value || lastAssignShift || 'full';
        lastAssignShift = initialShift;
        updateAssignTitle(initialShift);
        refreshCustomSelect(shiftSelect); // Sync shift select
      }

      // default to library list
      if (studentAssignType) {
        studentAssignType.value = 'library';
        refreshCustomSelect(studentAssignType);
      }
      toggleAssignModeUI();
      loadStudentList('library');
      openSmallModal(assignStudentModal);
    });
  }

  function resetManualForm() {
    if (manualAssignFirstName) manualAssignFirstName.value = '';
    if (manualAssignLastName) manualAssignLastName.value = '';
    if (manualAssignUsername) manualAssignUsername.value = '';
    if (manualAssignPassword) manualAssignPassword.value = '';
    if (manualAssignMobile) manualAssignMobile.value = '';
    if (manualAssignWhatsapp) {
      manualAssignWhatsapp.value = '';
      manualAssignWhatsapp.removeAttribute('readonly');
    }
    if (manualAssignWhatsappSame) manualAssignWhatsappSame.checked = false;
    if (manualAssignEmail) manualAssignEmail.value = '';
    if (manualAssignDOB) manualAssignDOB.value = '';
    if (manualAssignSex) {
      manualAssignSex.value = 'Male';
      refreshCustomSelect(manualAssignSex);
    }
    
    if (manualAssignPhotoPreview) {
      manualAssignPhotoPreview.src = ""; 
      manualAssignPhotoPreview.style.display = 'none';
    }
    if (manualAssignPhotoPlaceholder) manualAssignPhotoPlaceholder.style.display = 'flex';
    if (manualAssignPhotoInput) manualAssignPhotoInput.value = '';
    manualAssignPhotoBase64 = null;
  }

  // Profile Photo Upload Handling
  if (manualAssignPhotoInput && manualAssignPhotoPreview) {
    manualAssignPhotoInput.addEventListener('change', function(e) {
      const file = e.target.files[0];
      if (file) {
        if (file.size > 2 * 1024 * 1024) {
          window.CustomPopup.alert('Image size should be less than 2MB', 'File Too Large');
          manualAssignPhotoInput.value = '';
          return;
        }

        const reader = new FileReader();
        reader.onload = function(event) {
          manualAssignPhotoPreview.src = event.target.result;
          manualAssignPhotoPreview.style.display = 'block';
          if (manualAssignPhotoPlaceholder) manualAssignPhotoPlaceholder.style.display = 'none';
          manualAssignPhotoBase64 = event.target.result;
        };
        reader.readAsDataURL(file);
      }
    });
  }


  // Toggle UI when changing type select (library/coaching/manual)
  if (studentAssignType) {
    studentAssignType.addEventListener('change', () => {
      toggleAssignModeUI();
      const mode = studentAssignType.value || 'library';
      if (mode === 'manual') {
        // manual mode doesn't need student list
        populateStudentDropdown([]);
      } else {
        loadStudentList(mode);
      }
    });
  }

  if (manualAssignWhatsappSame && manualAssignWhatsapp && manualAssignMobile) {
    manualAssignWhatsappSame.addEventListener('change', () => {
      if (manualAssignWhatsappSame.checked) {
        manualAssignWhatsapp.value = manualAssignMobile.value || '';
        manualAssignWhatsapp.setAttribute('readonly', 'readonly');
      } else {
        manualAssignWhatsapp.removeAttribute('readonly');
      }
    });

    manualAssignMobile.addEventListener('input', () => {
      if (manualAssignWhatsappSame.checked) {
        manualAssignWhatsapp.value = manualAssignMobile.value || '';
      }
    });
  }

  const shiftSelect = document.getElementById('assignShiftSelect');
  let previousShiftValue = 'full'; // Track previous value for reset

  if (shiftSelect) {
    shiftSelect.addEventListener('change', async () => {
      const shiftValue = shiftSelect.value || 'full';
      updateAssignTitle(shiftValue);

      // --- CONFLICT CHECK: Check for pending request on the selected shift ---
      if (!currentSeatData || !currentSeatData.assignments) {
        lastAssignShift = shiftValue;
        previousShiftValue = shiftValue;
        return;
      }

      const assignments = currentSeatData.assignments || [];

      // Find pending request that conflicts with user's selected shift
      let conflictingPending = null;

      for (const a of assignments) {
        if (a.is_pending || a.student_status === 'pending') {
          // Check if this pending request conflicts with selected shift
          if (a.shift === shiftValue || shiftValue === 'full' || a.shift === 'full') {
            conflictingPending = a;
            break;
          }
        }
      }

      if (conflictingPending) {
        const studentName = conflictingPending.student_name || 'A student';
        const pendingShift = shiftLabelMap[conflictingPending.shift] || conflictingPending.shift;
        const dateStr = formatDateFriendly(conflictingPending.created_at);

        // Use custom popup instead of browser confirm
        const result = await window.CustomPopup.showConflictPopup({
          studentName,
          shift: pendingShift,
          date: dateStr
        });

        if (result === 'delete') {
          // User chose to delete the request and continue
          try {
            await window.sendSeatAction('delete_request', conflictingPending.student_id, false, {
              shift: conflictingPending.shift,
              request_id: conflictingPending.student_id
            });
            // Refresh seat data
            loadSeatLayout(currentFloor);
            lastAssignShift = shiftValue;
            previousShiftValue = shiftValue;
          } catch (e) {
            console.error('Failed to delete pending request:', e);
            // Revert dropdown
            shiftSelect.value = previousShiftValue;
            updateAssignTitle(previousShiftValue);
          }
        } else {
          // User cancelled - revert to previous shift
          shiftSelect.value = previousShiftValue;
          updateAssignTitle(previousShiftValue);
        }
      } else {
        // No conflict - proceed normally
        lastAssignShift = shiftValue;
        previousShiftValue = shiftValue;
      }
    });
  }

  function toggleAssignModeUI() {
    const mode = studentAssignType ? studentAssignType.value : 'library';
    if (mode === 'manual') {
      if (studentAssignWrap) studentAssignWrap.style.display = 'none';
      if (manualAssignDiv) manualAssignDiv.style.display = 'block';
      if (manualAssignWhatsappSame) manualAssignWhatsappSame.checked = false;
      if (manualAssignWhatsapp && manualAssignMobile) {
        manualAssignWhatsapp.value = '';
        manualAssignWhatsapp.removeAttribute('readonly');
      }
    } else {
      if (studentAssignWrap) studentAssignWrap.style.display = 'block';
      if (manualAssignDiv) manualAssignDiv.style.display = 'none';
    }

    const shiftSelect = document.getElementById('assignShiftSelect');
    if (shiftSelect) {
      const shiftValue = shiftSelect.value || lastAssignShift || 'full';
      updateAssignTitle(shiftValue);
    }
  }

  // Confirm assign (handles all three modes)
  if (actionConfirmAssign) {
    actionConfirmAssign.addEventListener('click', async () => {
      const mode = studentAssignType ? studentAssignType.value : 'library';

      // --- NEW: Capture Selected Shift ---
      const shiftSelect = document.getElementById('assignShiftSelect');
      // If the dropdown is visible, take its value. Otherwise default to 'full'.
      const shiftWrapper = document.getElementById('assignShiftWrapper');
      const selectedShift = (shiftWrapper && shiftWrapper.offsetParent !== null && shiftSelect) ? shiftSelect.value : 'full';

      // Lock Validation before assigning
      if (currentSeatData) {
        const lockedShiftsList = (currentSeatData.locked_shifts || '').split(',').filter(Boolean);
        const isFullLocked = !!currentSeatData.is_locked || lockedShiftsList.includes('full');
        const isMorningLocked = isFullLocked || lockedShiftsList.includes('morning');
        const isEveningLocked = isFullLocked || lockedShiftsList.includes('evening');

        if (selectedShift === 'full' && (isMorningLocked || isEveningLocked)) {
          const lockedShiftName = (isMorningLocked && isEveningLocked) ? 'Morning & Evening' : (isMorningLocked ? 'Morning' : 'Evening');
          await window.CustomPopup.alert(`Cannot assign Full Day because ${lockedShiftName} shift is locked. Please unlock it first.`, 'Shift Locked');
          return;
        }
        if (selectedShift === 'morning' && isMorningLocked) {
          await window.CustomPopup.alert('Morning shift is locked. Please unlock the Morning shift first.', 'Shift Locked');
          return;
        }
        if (selectedShift === 'evening' && isEveningLocked) {
          await window.CustomPopup.alert('Evening shift is locked. Please unlock the Evening shift first.', 'Shift Locked');
          return;
        }
      }

      // We will send this in the payload
      const customPayload = { shift: selectedShift };

      if (mode === 'manual') {
        // validate manual fields
        const username = manualAssignUsername ? manualAssignUsername.value.trim() : '';
        const password = manualAssignPassword ? manualAssignPassword.value : '';
        const firstName = manualAssignFirstName ? manualAssignFirstName.value.trim() : '';
        const lastName = manualAssignLastName ? manualAssignLastName.value.trim() : '';
        const mobile = manualAssignMobile ? manualAssignMobile.value.trim() : '';
        const whatsapp = manualAssignWhatsapp ? manualAssignWhatsapp.value.trim() : '';
        const email = manualAssignEmail ? manualAssignEmail.value.trim() : '';
        const fullName = [firstName, lastName].filter(Boolean).join(' ').trim();

        if (!firstName || !lastName) {
          await window.CustomPopup.alert('Please enter first and last name.', 'Missing Details');
          return;
        }
        if (!username) {
          await window.CustomPopup.alert('Please enter a username.', 'Missing Details');
          return;
        }
        if (!password) {
          await window.CustomPopup.alert('Please enter a password.', 'Missing Details');
          return;
        }
        if (!mobile && !whatsapp) {
          await window.CustomPopup.alert('Please enter mobile or whatsapp.', 'Missing Details');
          return;
        }

        const dob = manualAssignDOB ? manualAssignDOB.value : '';
        const sex = manualAssignSex ? manualAssignSex.value : 'Male';

        // Add manual fields to payload
        Object.assign(customPayload, {
          first_name: firstName,
          last_name: lastName,
          full_name: fullName,
          mobile_number: mobile || whatsapp,
          whatsapp_number: whatsapp || mobile,
          email: email || '',
          dob: dob || null,
          sex: sex,
          username: username || '',
          password: password || '',
          profile_photo: manualAssignPhotoBase64
        });

        const confirmed = await window.CustomPopup.confirm(
          `Confirm manually create student "${fullName}" and assign Seat ${currentSeatData.seat_number} (${selectedShift})?`,
          'Confirm Manual Assignment'
        );
        if (!confirmed) return;

        await sendSeatAction('assign_manual', null, false, customPayload);
        return;
      }

      // else library or coaching selected
      if (!studentAssignSelect) {
        await window.CustomPopup.alert('Student list not loaded.', 'Error');
        return;
      }
      const selectedStudentId = studentAssignSelect.value;
      if (!selectedStudentId) {
        await window.CustomPopup.alert('Please select a student.', 'Missing Selection');
        return;
      }

      let reassign = false;
      const selectedCache = studentListCache[mode] || [];
      const selectedStudent = selectedCache ? selectedCache.find(s => String(s.id) === String(selectedStudentId)) : null;

      // --- NEW: GUARDS for Hold Owner / Tenant ---
      if (selectedStudent) {
        // Guard 1: Block Hold Owner
        if (selectedStudent.is_hold_owner) {
          await window.CustomPopup.alert(
            `Action Blocked: ${selectedStudent.full_name} is currently a Hold Owner on another seat/shift.<br><br>You must End Hold on their existing seat first.`,
            'Hold Owner'
          );
          return;
        }
        // Guard 2: Confirm Tenant Switch
        if (selectedStudent.is_tenant) {
          const proceedTenant = await window.CustomPopup.confirm(
            `Warning: ${selectedStudent.full_name} is currently a Temporary Tenant on Seat ${selectedStudent.seat_number || '?'}.

Do you want to switch them to this seat permanently?`,
            'Temporary Tenant'
          );
          if (!proceedTenant) {
            return;
          }
          // Implicit reassign set to true
          reassign = true;
        }

        if (selectedStudent.seat_number) reassign = true;
      }

      // --- Intercept Coaching / Alumni Allotment (Case Three) ---
      let actionScope = null;
      if (selectedStudent && (selectedStudent.has_alumni || selectedStudent.has_coaching)) {
        const interceptModal = document.getElementById('teacherPremiumAllotInterceptModal');
        const interceptText = document.getElementById('interceptModalText');
        const interceptWarning = document.getElementById('interceptModalWarningText');
        
        if (interceptModal && interceptText && interceptWarning) {
          let text = '';
          let warning = '';
          if (selectedStudent.has_alumni && selectedStudent.has_coaching) {
            text = `The selected user <strong>${selectedStudent.full_name}</strong> is an alumni/achiever and also coaching student too. Would you like to switch the service to library only or want to add him/her as library student too?`;
            warning = `⚠️ If you switch him/her to library only then it will delete all of his/her existing profiles as an alumni and coaching student from everywhere, leaving only the library student profile. Adding will merge coaching and library services in one dashboard, preserving the alumni profile.`;
          } else if (selectedStudent.has_coaching) {
            text = `The selected user <strong>${selectedStudent.full_name}</strong> is currently a coaching student. Would you like to switch the service to library only or want to add him/her as library student too?`;
            warning = `⚠️ If you switch him/her to library student only then he/she will only be library student, and the current coaching profile gets disabled and coaching data will be deleted.`;
          } else {
            text = `The selected user <strong>${selectedStudent.full_name}</strong> is currently an alumni. Would you like to switch the service to library only or want to add him/her as library student too?`;
            warning = `⚠️ If you switch him/her to library student only then he/she will only be library student, and the alumni profile gets deleted.`;
          }
          
          interceptText.innerHTML = text;
          interceptWarning.textContent = warning;
          
          // Open Modal
          window.openSmallModal(interceptModal);
          
          // Wait for button selection
          const choice = await new Promise((resolve) => {
            const switchBtn = document.getElementById('interceptSwitchBtn');
            const addBtn = document.getElementById('interceptAddBtn');
            const closeBtn = document.getElementById('interceptCloseBtn');
            const headerCloseBtn = document.getElementById('closeAllotInterceptModal');
            
            function cleanUp() {
              switchBtn.replaceWith(switchBtn.cloneNode(true));
              addBtn.replaceWith(addBtn.cloneNode(true));
              closeBtn.replaceWith(closeBtn.cloneNode(true));
              headerCloseBtn.replaceWith(headerCloseBtn.cloneNode(true));
            }
            
            document.getElementById('interceptSwitchBtn').addEventListener('click', () => {
              cleanUp();
              window.closeSmallModal(interceptModal);
              resolve('switch');
            });
            document.getElementById('interceptAddBtn').addEventListener('click', () => {
              cleanUp();
              window.closeSmallModal(interceptModal);
              resolve('add');
            });
            document.getElementById('interceptCloseBtn').addEventListener('click', () => {
              cleanUp();
              window.closeSmallModal(interceptModal);
              resolve('close');
            });
            document.getElementById('closeAllotInterceptModal').addEventListener('click', () => {
              cleanUp();
              window.closeSmallModal(interceptModal);
              resolve('close');
            });
          });
          
          if (choice === 'close') {
            return;
          }
          actionScope = choice;
        }
      }
      
      if (actionScope) {
        customPayload.action_scope = actionScope;
      }

      const confirmTitle = reassign ? 'Reassign Student' : 'Confirm Assignment';
      const confirmMain = reassign
        ? `Student ${selectedStudent.full_name} Already Assigned`
        : `Confirm Allotment to ${selectedStudent ? selectedStudent.full_name : 'Student'}`;
      const confirmSub = reassign
        ? `${selectedStudent.full_name} is already assigned/tenant on Seat ${getFormattedSeatNumber(selectedStudent.seat_number) || '?'}. Reassign them to Seat ${getFormattedSeatNumber()} (${selectedShift})?`
        : `Would you like to allot Seat ${getFormattedSeatNumber()} (${selectedShift}) to ${selectedStudent ? selectedStudent.full_name : 'the selected student'}?`;

      const finalConfirm = await window.showConfirmation({
        title: confirmTitle,
        mainText: confirmMain,
        subText: confirmSub,
        theme: reassign ? 'warning' : 'primary',
        iconClass: reassign ? 'bx-transfer' : 'bx-user-check',
        confirmLabel: 'Confirm Assignment'
      });

      if (finalConfirm) {
        await sendSeatAction('allot', selectedStudentId, reassign, customPayload);
      }
    });
  }

  if (actionMakeAvailable) actionMakeAvailable.addEventListener('click', async () => {
    if (!currentSeatData || !currentSeatData.seat_number) return;
    const confirmed = await window.showConfirmation({
      title: 'Free Seat',
      mainText: `Free Seat ${getFormattedSeatNumber()}?`,
      subText: `The student (${currentSeatData.student_name || 'Occupant'}) will be unassigned and moved to the "No Seat" section.`,
      theme: 'danger',
      iconClass: 'bx-user-minus',
      confirmLabel: 'Confirm Free'
    });
    if (confirmed) sendSeatAction('free');
  });

  if (actionApprovePending) actionApprovePending.addEventListener('click', async () => {
    if (!currentSeatData || !currentSeatData.student_id) return;
    const confirmed = await window.showConfirmation({
      title: 'Approve Admission',
      mainText: `Approve ${currentSeatData.student_name || 'Request'}?`,
      subText: `This will officially allot Seat ${currentSeatData.seat_number} to the student.`,
      theme: 'success',
      iconClass: 'bx-check-circle',
      confirmLabel: 'Confirm Approve'
    });
    if (confirmed) sendSeatAction('approve_pending');
  });

  if (actionRejectPending) actionRejectPending.addEventListener('click', async () => {
    if (!currentSeatData || !currentSeatData.student_id) return;
    const confirmed = await window.showConfirmation({
      title: 'Reject Request',
      mainText: `Reject ${currentSeatData.student_name || 'Request'}?`,
      subText: `Are you sure you want to delete this admission request for Seat ${getFormattedSeatNumber()}?`,
      theme: 'danger',
      iconClass: 'bx-x-circle',
      confirmLabel: 'Confirm Reject'
    });
    if (confirmed) sendSeatAction('delete_request');
  });



  // Open Hold modal instead of prompt()
  if (actionPutOnHold && holdModal && holdStartDate && holdDurationInput) {
    actionPutOnHold.addEventListener('click', async () => {
      if (!currentSeatData || !currentSeatData.seat_number) return;

      if (!currentSeatData.student_id) {
        await window.CustomPopup.alert('Seat must be owned by a student before placing on hold.', 'Hold Not Allowed');
        return;
      }

      const assignments = JSON.parse(
        document.querySelector(`.seat[data-seat-id="${currentSeatData.seat_number}"]`).dataset.assignments || "[]"
      );

      const hasPartial = assignments.some(a => a.is_partial);

      if (hasPartial) {
        await window.CustomPopup.alert(
          'Seat has temporary/partial students. End partial assignments before placing on hold.',
          'Hold Not Allowed'
        );
        return;
      }

      // default start = today
      const todayStr = new Date().toISOString().slice(0, 10);
      holdStartDate.value = todayStr;
      holdDurationInput.value = '';

      const holdModalTitle = document.getElementById('holdModalTitle');
      if (holdModalTitle) holdModalTitle.textContent = `Put Seat ${getFormattedSeatNumber()} on Hold`;

      openSmallModal(holdModal);
    });
  }

  // Confirm button inside Hold modal
  if (holdConfirmBtn && holdStartDate && holdDurationInput) {
    holdConfirmBtn.addEventListener('click', async () => {
      if (!currentSeatData || !currentSeatData.seat_number) return;

      const startDate = holdStartDate.value;
      const durationStr = holdDurationInput.value.trim();

      if (!startDate) {
        await window.CustomPopup.alert('Please select a hold start date.', 'Missing Date');
        return;
      }
      if (!/^\d{4}-\d{2}-\d{2}$/.test(startDate)) {
        await window.CustomPopup.alert('Start date format looks invalid.', 'Invalid Date');
        return;
      }
      if (!durationStr) {
        await window.CustomPopup.alert('Please enter a hold duration (e.g. "20 days" or "1 month 5 days").', 'Missing Duration');
        return;
      }

      // lightweight validation: any duration 1+ days (NO RESTRICTIONS FOR TEACHERS)
      const estDays = estimateDurationDays(durationStr);
      if (estDays === null) {
        await window.CustomPopup.alert('Please enter duration like "1 day", "20 days", or "1 month 5 days".', 'Invalid Duration');
        return;
      }
      if (estDays < 1) {
        await window.CustomPopup.alert('Hold duration must be at least 1 day.', 'Invalid Duration');
        return;
      }

      window.closeSmallModal(holdModal);

      await sendSeatAction('put_on_hold', holdConfirmBtn.dataset.studentId, false, {
        start_date: startDate,
        duration: durationStr,
        shift: holdConfirmBtn.dataset.shift
      });
    });
  }

  // helper to convert "1 month 5 days" etc into approx days
  function estimateDurationDays(text) {
    const s = text.toLowerCase();
    let total = 0;
    const mMatch = s.match(/(\d+)\s*(month|months|mon|m)/);
    if (mMatch) total += parseInt(mMatch[1], 10) * 30;   // approx

    const dMatch = s.match(/(\d+)\s*(day|days|d)/);
    if (dMatch) total += parseInt(dMatch[1], 10);

    if (!mMatch && !dMatch) return null;
    return total;
  }


  if (actionEndHold) actionEndHold.addEventListener('click', async () => {
    const confirmed = await window.showConfirmation({
      title: 'End Hold',
      mainText: 'End Hold for this Seat?',
      subText: 'The seat will return to its previous status (Available or Occupied).',
      theme: 'warning',
      iconClass: 'bx-play-circle',
      confirmLabel: 'Confirm End Hold'
    });
    if (confirmed) sendSeatAction('end_hold');
  });


  // initial load
  if (floorSelector) {
    if (typeof dashboardFloor !== 'undefined' && dashboardFloor) {
      floorSelector.value = dashboardFloor;
    } else if (!floorSelector.value) {
      floorSelector.value = 'Ground Floor';
    }
    initCustomSelects();
    loadSeatLayout(floorSelector.value);
  }
});


// Robust delegated close-handler (works even if modal/close icon is moved to body)
document.body.addEventListener('click', function (ev) {
  const btn = ev.target.closest && ev.target.closest('.modal-close-btn, .teacher-modal-close, .seat-modal-close-btn, .seat-modal-close');
  if (!btn) return;
  // prevent accidental propagation
  ev.preventDefault();
  ev.stopPropagation();

  // find enclosing modal
  const parentModal = btn.closest('.admission-modal, .teacher-premium-modal, .teacher-modal, .seat-modal-container');

  if (parentModal) {
    if (parentModal.id === 'teacherPremiumSeatDetailsModal') {
      window.closeSeatDetailsModal();
      return;
    }
    // Generic check for all premium modals
    if (parentModal.classList.contains('admission-modal') || parentModal.id.includes('Modal')) {
      window.closeSmallModal(parentModal);
      return;
    }
    // generic close fallback
    parentModal.classList.remove('active');
    parentModal.classList.remove('open');
    const ov = document.getElementById('admissionModalOverlay') || document.getElementById('teacherPremiumOverlay');
    if (ov) {
      ov.classList.remove('active');
      ov.classList.remove('visible');
    }
    document.body.classList.remove('modal-open');
    // Special reset for assign modal
    if (parentModal.id === 'teacherPremiumAssignModal') {
      resetAssignModal();
    }
    return;
  }

  // if no parent modal found, still call canonical close
  window.closeSeatDetailsModal();
});

