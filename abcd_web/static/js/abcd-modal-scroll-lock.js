/**
 * ABCD Smart Campus - Universal Modal & Nested Modal Background Scroll Lock Engine
 * 
 * Guarantees that whenever ANY modal, popup, or nested popup opens across ANY page:
 * 1. The underlying background page is frozen from scrolling up or down.
 * 2. Nested popups (e.g. popup inside a popup / wheel picker inside task modal) maintain
 *    the background lock until the very last popup is dismissed.
 * 3. Mobile touch-drag and overscroll bouncing cannot cascade from modal to background.
 * 4. Content within all modals, panels (Broadcast, Notifications), sidebars, and drawers
 *    remains smoothly scrollable with laptop touchpads (2-finger scroll), mouse wheels, and touch.
 * 5. When all popups close, the background's exact scroll position is seamlessly restored.
 */
(function() {
  'use strict';

  if (window.__ABCD_MODAL_SCROLL_LOCK__) return;

  const activeModals = new Set();
  let isLocked = false;
  let savedScrollY = 0;
  let prevBodyOverflow = '';
  let prevDocOverflow = '';
  let prevBodyTouchAction = '';
  let prevBodyPaddingRight = '';

  // Inject CSS rules for overscroll containment and smooth touchpad/touch scrolling
  const styleEl = document.createElement('style');
  styleEl.id = 'abcd-modal-scroll-lock-styles';
  styleEl.textContent = `
    html.abcd-scroll-locked,
    body.abcd-scroll-locked {
      overflow: hidden !important;
    }

    /* Dimmed static backdrop overlays prevent background touch dragging */
    .modal-overlay,
    .todo-modal-overlay,
    .picker-overlay,
    .custom-modal-overlay,
    .popup-overlay,
    .seat-modal-overlay,
    .seat-interest-overlay,
    .choice-modal-overlay,
    .reg-success-overlay,
    .student-banner-overlay,
    .fp-overlay,
    .alert-overlay,
    .custom-alert-overlay,
    .banner-popup-overlay,
    .broadcast-overlay,
    .teacher-notif-overlay,
    .notif-overlay,
    #logoutConfirmOverlay {
      touch-action: none;
    }
    
    /* Ensure all modal, panel, drawer, and sidebar containers contain their own scroll
       and allow high-precision laptop touchpad 2-finger panning and mobile touch scrolling */
    .modal,
    .modal-dialog,
    .modal-content,
    .modal-body,
    .todo-modal,
    .todo-modal-body,
    .picker-card,
    .drums-container,
    .drum-column,
    .custom-modal,
    .custom-modal-card,
    .custom-modal-body,
    .layout-modal,
    .seat-modal,
    .seat-modal-container,
    .seat-modal-body,
    .styled-modal-box,
    .choice-modal-card,
    .reg-success-card,
    .student-banner-card,
    .alert-card,
    .custom-alert-card,
    .fp-card,
    .broadcast-panel-container,
    .broadcast-panel,
    .broadcast-body,
    .teacher-notif-panel,
    .teacher-notif-body,
    .notif-panel,
    .notif-body,
    .sidebar-wrapper,
    #sidebar,
    .nav-sidebar,
    #hubSidebar,
    .hub-sidebar,
    .g-sidebar,
    #gSidebar,
    .g-side-body,
    .g-chat-list,
    .g-chat-messages,
    .g-messages-area,
    .g-chats-list,
    .g-requests-list,
    .g-notes-list,
    .scrollable-modal-content,
    [data-modal-scrollable="true"],
    [role="dialog"],
    dialog {
      overscroll-behavior: contain !important;
      -webkit-overflow-scrolling: touch !important;
      touch-action: pan-y !important;
    }
  `;
  (document.head || document.documentElement).appendChild(styleEl);

  function getScrollbarWidth() {
    return window.innerWidth - document.documentElement.clientWidth;
  }

  function isScrollableElement(elem) {
    if (!elem || elem === document.body || elem === document.documentElement) return false;
    try {
      const style = window.getComputedStyle(elem);
      const overflowY = style.overflowY;
      const overflowX = style.overflowX;
      const canScrollY = (overflowY === 'auto' || overflowY === 'scroll') && (elem.scrollHeight > elem.clientHeight);
      const canScrollX = (overflowX === 'auto' || overflowX === 'scroll') && (elem.scrollWidth > elem.clientWidth);
      return canScrollY || canScrollX;
    } catch (err) {
      return false;
    }
  }

  function findScrollableParent(el, root) {
    let curr = el;
    while (curr && curr !== document.body && curr !== document.documentElement) {
      if (isScrollableElement(curr)) return curr;
      if (root && curr === root) break;
      curr = curr.parentElement;
    }
    return null;
  }

  // Touchmove event blocker for mobile / tablet devices
  function onTouchMove(e) {
    if (!isLocked) return;

    // 1. NEVER block touch interactions on sidebar, hamburger, or navigation
    if (e.target.closest(
      '.sidebar-wrapper, #sidebar, .nav-sidebar, #hubSidebar, .hub-sidebar, ' +
      '.g-sidebar, #gSidebar, .top-nav-menu, .bottom-nav-menu, #mobileNav, #guestMobileNav, ' +
      '#sidebarOverlay, .hamburger-icon'
    )) {
      return;
    }

    // 2. NEVER block touch interactions on panels
    if (e.target.closest('.broadcast-panel-container, .broadcast-panel, .teacher-notif-panel, .notif-panel')) {
      return;
    }

    // 3. Check if the touch happened inside any active modal or dialog element
    const insideActiveModal = Array.from(activeModals).some(m => {
      if (!m || !m.isConnected) return false;
      if (m.contains(e.target)) return true;
      if (m.id === 'broadcastOverlay') {
        const p = document.getElementById('broadcastPanel');
        if (p && p.contains(e.target)) return true;
      }
      if (m.id === 'teacherNotifOverlay') {
        const p = document.getElementById('teacherNotifPanel');
        if (p && p.contains(e.target)) return true;
      }
      if (m.id === 'notifOverlay') {
        const p = document.getElementById('notifPanel');
        if (p && p.contains(e.target)) return true;
      }
      return false;
    });

    const insideDialogElement = !!e.target.closest(
      '.modal, .modal-dialog, .modal-content, .modal-body, .todo-modal, .picker-card, ' +
      '.seat-modal-container, .seat-modal-body, .choice-modal-card, .reg-success-card, ' +
      '.student-banner-card, .alert-card, .custom-alert-card, .fp-card, [role="dialog"], ' +
      'dialog, .drum-column, .drums-container, .scrollable-modal-content, [data-modal-scrollable="true"]'
    );

    if (insideActiveModal || insideDialogElement) {
      return; // Permit smooth touch scrolling inside active modal
    }

    // 4. Touching the static backdrop overlay outside all dialogs: freeze background scroll
    if (e.cancelable) {
      e.preventDefault();
    }
  }

  // Wheel event handler for desktop mouse & laptop touchpad 2-finger scroll
  function onWheel(e) {
    if (!isLocked) return;

    // 1. Sidebar & Navigation Drawers: NEVER block touchpad or wheel scrolling!
    if (e.target.closest(
      '.sidebar-wrapper, #sidebar, .nav-sidebar, #hubSidebar, .hub-sidebar, ' +
      '.g-sidebar, #gSidebar, .top-nav-menu, .bottom-nav-menu, #mobileNav, #guestMobileNav'
    )) {
      return;
    }

    // 2. Broadcast Panel: allow native touchpad scrolling, or delegate if hovering header/tabs
    const broadcastPanel = e.target.closest('.broadcast-panel-container, .broadcast-panel');
    if (broadcastPanel) {
      const bBody = broadcastPanel.querySelector('.broadcast-body');
      if (bBody && !e.target.closest('.broadcast-body') && (bBody.scrollHeight > bBody.clientHeight)) {
        bBody.scrollTop += e.deltaY;
        if (e.cancelable) e.preventDefault();
      }
      return; // Allow native touchpad / wheel scrolling inside broadcast panel!
    }

    // 3. Teacher Notification Panel: allow native touchpad scrolling, or delegate if hovering header
    const teacherNotifPanel = e.target.closest('.teacher-notif-panel');
    if (teacherNotifPanel) {
      const tnBody = teacherNotifPanel.querySelector('.teacher-notif-body');
      if (tnBody && !e.target.closest('.teacher-notif-body') && (tnBody.scrollHeight > tnBody.clientHeight)) {
        tnBody.scrollTop += e.deltaY;
        if (e.cancelable) e.preventDefault();
      }
      return; // Allow native touchpad / wheel scrolling inside teacher notif panel!
    }

    // 4. Student / Guest Notification Panel: allow native touchpad scrolling, or delegate if hovering header
    const notifPanel = e.target.closest('.notif-panel');
    if (notifPanel) {
      const snBody = notifPanel.querySelector('.notif-body');
      if (snBody && !e.target.closest('.notif-body') && (snBody.scrollHeight > snBody.clientHeight)) {
        snBody.scrollTop += e.deltaY;
        if (e.cancelable) e.preventDefault();
      }
      return; // Allow native touchpad / wheel scrolling inside notif panel!
    }

    // 5. Check if target is inside ANY active modal dialog, popup card, drum column, or scrollable area
    const insideActiveModal = Array.from(activeModals).some(m => {
      if (!m || !m.isConnected) return false;
      if (m.contains(e.target)) return true;
      if (m.id === 'broadcastOverlay') {
        const p = document.getElementById('broadcastPanel');
        if (p && p.contains(e.target)) return true;
      }
      if (m.id === 'teacherNotifOverlay') {
        const p = document.getElementById('teacherNotifPanel');
        if (p && p.contains(e.target)) return true;
      }
      if (m.id === 'notifOverlay') {
        const p = document.getElementById('notifPanel');
        if (p && p.contains(e.target)) return true;
      }
      return false;
    });

    const insideDialogElement = !!e.target.closest(
      '.modal, .modal-dialog, .modal-content, .modal-body, .todo-modal, .picker-card, ' +
      '.seat-modal-container, .seat-modal-body, .choice-modal-card, .reg-success-card, ' +
      '.student-banner-card, .alert-card, .custom-alert-card, .fp-card, [role="dialog"], ' +
      'dialog, .drum-column, .drums-container, .scrollable-modal-content, [data-modal-scrollable="true"]'
    );

    if (insideActiveModal || insideDialogElement) {
      // Inside active modal/dialog: allow native smooth touchpad / mouse wheel scrolling!
      return;
    }

    // 6. Check if target or any ancestor is scrollable anywhere on the screen
    const scrollable = findScrollableParent(e.target, document.body);
    if (scrollable) {
      return; // Has a scrollable container, allow native scroll!
    }

    // 7. Otherwise, the wheel event occurred on the static dimmed backdrop overlay or dead background:
    // Block wheel event to prevent background page scroll chaining!
    if (e.cancelable) {
      e.preventDefault();
    }
  }

  function applyLock() {
    if (isLocked) return;
    isLocked = true;

    savedScrollY = window.pageYOffset || document.documentElement.scrollTop || document.body.scrollTop || 0;

    prevBodyOverflow = document.body.style.overflow;
    prevDocOverflow = document.documentElement.style.overflow;
    prevBodyTouchAction = document.body.style.touchAction;
    prevBodyPaddingRight = document.body.style.paddingRight;

    const sbWidth = getScrollbarWidth();
    if (sbWidth > 0) {
      const currentPadding = parseFloat(window.getComputedStyle(document.body).paddingRight) || 0;
      document.body.style.paddingRight = `${currentPadding + sbWidth}px`;
    }

    document.documentElement.classList.add('abcd-scroll-locked');
    document.body.classList.add('abcd-scroll-locked');

    document.body.style.overflow = 'hidden';
    document.documentElement.style.overflow = 'hidden';

    window.addEventListener('touchmove', onTouchMove, { passive: false });
    window.addEventListener('wheel', onWheel, { passive: false });
  }

  function applyUnlock() {
    if (!isLocked) return;
    isLocked = false;

    document.documentElement.classList.remove('abcd-scroll-locked');
    document.body.classList.remove('abcd-scroll-locked');

    document.body.style.overflow = prevBodyOverflow;
    document.documentElement.style.overflow = prevDocOverflow;
    document.body.style.touchAction = prevBodyTouchAction;
    document.body.style.paddingRight = prevBodyPaddingRight;

    window.removeEventListener('touchmove', onTouchMove, { passive: false });
    window.removeEventListener('wheel', onWheel, { passive: false });

    // Restore scroll position cleanly
    if (savedScrollY > 0) {
      window.scrollTo({ top: savedScrollY, behavior: 'instant' });
    }
  }

  function lockModal(modalEl) {
    const el = modalEl || document.body;
    activeModals.add(el);
    applyLock();
  }

  function unlockModal(modalEl) {
    if (modalEl) {
      activeModals.delete(modalEl);
    } else {
      activeModals.clear();
    }

    // Only unlock background if NO modals or popups are still open!
    if (activeModals.size === 0) {
      applyUnlock();
    }
  }

  // Modal matching selector
  const MODAL_SELECTOR = [
    '.modal',
    '.modal-overlay',
    '.todo-modal-overlay',
    '.picker-overlay',
    '.custom-modal-overlay',
    '.popup-overlay',
    '.layout-modal',
    '.seat-modal',
    '.seat-modal-overlay',
    '.seat-interest-overlay',
    '.choice-modal-overlay',
    '.reg-success-overlay',
    '.student-banner-overlay',
    '.fp-overlay',
    '.alert-overlay',
    '.custom-alert-overlay',
    '.tour-popup',
    '.banner-popup-overlay',
    '.broadcast-overlay',
    '.broadcast-panel-container',
    '.teacher-notif-overlay',
    '.teacher-notif-panel',
    '.notif-overlay',
    '.notif-panel',
    '#logoutConfirmOverlay',
    '#logoutConfirmModal',
    '[class*="-modal"]',
    '[role="dialog"]',
    'dialog'
  ].join(',');

  function isElementModalOpen(el) {
    if (!el || !el.isConnected) return false;

    // Never treat sidebar elements, navigation drawers, or search menus as background-locking modals
    if (el.classList.contains('sidebar-overlay') ||
        el.classList.contains('sidebar-wrapper') ||
        el.classList.contains('nav-sidebar') ||
        el.classList.contains('hub-sidebar') ||
        el.classList.contains('g-sidebar') ||
        el.classList.contains('mobile-search-overlay') ||
        el.classList.contains('hero-overlay-static') ||
        el.id === 'sidebarOverlay' ||
        el.id === 'sidebar' ||
        el.id === 'hubSidebar' ||
        el.id === 'gSidebar' ||
        el.closest('.sidebar-wrapper') ||
        el.closest('.top-nav-menu') ||
        el.closest('.bottom-nav-menu') ||
        el.closest('.g-sidebar')) {
      return false;
    }

    // Check if element is closed via explicit closed classes
    if (el.classList.contains('choice-modal-closed') ||
        el.classList.contains('modal-closed') ||
        el.classList.contains('popup-closed')) {
      return false;
    }

    // Check computed style display and visibility
    try {
      const cs = window.getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') {
        return false;
      }
    } catch(err) {}

    // Check specific class-based activations
    if (el.classList.contains('active') ||
        el.classList.contains('show') ||
        el.classList.contains('open') ||
        el.classList.contains('visible') ||
        el.classList.contains('in')) {
      return true;
    }

    // Check dialog open attribute
    if (el.tagName === 'DIALOG' && el.open) {
      return true;
    }

    // Check aria-hidden
    if (el.getAttribute('aria-hidden') === 'false' && el.getAttribute('role') === 'dialog') {
      return true;
    }

    return false;
  }

  function scanAndSyncModals() {
    try {
      // First clean up disconnected or closed modals from activeModals
      for (const m of activeModals) {
        if (!m || !m.isConnected || !isElementModalOpen(m)) {
          activeModals.delete(m);
        }
      }

      const candidateElements = document.querySelectorAll(MODAL_SELECTOR);
      let foundAnyOpen = false;

      candidateElements.forEach(el => {
        if (isElementModalOpen(el)) {
          foundAnyOpen = true;
          activeModals.add(el);
        } else {
          activeModals.delete(el);
        }
      });

      if (activeModals.size > 0) {
        applyLock();
      } else if (isLocked && !foundAnyOpen) {
        applyUnlock();
      }
    } catch(e) {}
  }

  // MutationObserver to automatically detect when any popup/modal opens or closes
  const observer = new MutationObserver(mutations => {
    let shouldScan = false;
    for (const m of mutations) {
      if (m.type === 'attributes') {
        const target = m.target;
        if (target && target.matches && target.matches(MODAL_SELECTOR)) {
          shouldScan = true;
          break;
        }
        if (m.attributeName === 'class' || m.attributeName === 'style' || m.attributeName === 'hidden') {
          shouldScan = true;
          break;
        }
      } else if (m.type === 'childList') {
        shouldScan = true;
        break;
      }
    }

    if (shouldScan) {
      scanAndSyncModals();
    }
  });

  // Start observing once DOM is available
  function initObserver() {
    if (!document.body) return;

    observer.observe(document.body, {
      attributes: true,
      attributeFilter: ['class', 'style', 'hidden', 'open', 'aria-hidden'],
      childList: true,
      subtree: true
    });

    scanAndSyncModals();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initObserver);
  } else {
    initObserver();
  }

  // Listen to Bootstrap modal events if Bootstrap is present on page
  document.addEventListener('show.bs.modal', function(e) { lockModal(e.target); }, true);
  document.addEventListener('shown.bs.modal', function(e) { lockModal(e.target); }, true);
  document.addEventListener('hide.bs.modal', function(e) { unlockModal(e.target); }, true);
  document.addEventListener('hidden.bs.modal', function(e) { unlockModal(e.target); }, true);

  // Expose global API
  window.__ABCD_MODAL_SCROLL_LOCK__ = {
    lock: lockModal,
    unlock: unlockModal,
    sync: scanAndSyncModals,
    isLocked: () => isLocked,
    getActiveCount: () => activeModals.size
  };

  window.lockModalScroll = lockModal;
  window.unlockModalScroll = unlockModal;
  window.syncModalScrollLock = scanAndSyncModals;

})();
