/**
 * ABCD Smart Campus - Universal Modal & Nested Modal Background Scroll Lock Engine
 * 
 * Guarantees that whenever ANY modal, popup, or nested popup opens across ANY page:
 * 1. The underlying background page is frozen from scrolling up or down.
 * 2. Nested popups (e.g. popup inside a popup / wheel picker inside task modal) maintain
 *    the background lock until the very last popup is dismissed.
 * 3. Mobile touch-drag and overscroll bouncing cannot cascade from modal to background.
 * 4. Content within the modal/popup remains smoothly scrollable.
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

  // Inject CSS rules for overscroll containment
  const styleEl = document.createElement('style');
  styleEl.id = 'abcd-modal-scroll-lock-styles';
  styleEl.textContent = `
    html.abcd-scroll-locked,
    body.abcd-scroll-locked {
      overflow: hidden !important;
      touch-action: none !important;
      -ms-touch-action: none !important;
    }
    
    /* Ensure modal containers contain their own scroll and don't chain to body */
    .modal,
    .modal-overlay,
    .todo-modal-overlay,
    .picker-overlay,
    .custom-modal-overlay,
    .popup-overlay,
    .layout-modal,
    .seat-modal,
    .alert-overlay,
    [role="dialog"],
    dialog,
    .todo-modal,
    .picker-card,
    .modal-dialog,
    .modal-content,
    .modal-body {
      overscroll-behavior: contain !important;
      -webkit-overflow-scrolling: touch;
    }

    /* Permit touch scrolling inside modal scrollable areas */
    .todo-modal-body,
    .modal-body,
    .drums-container,
    .drum-column,
    .scrollable-modal-content,
    [data-modal-scrollable="true"] {
      touch-action: pan-y !important;
    }
  `;
  (document.head || document.documentElement).appendChild(styleEl);

  function getScrollbarWidth() {
    return window.innerWidth - document.documentElement.clientWidth;
  }

  function findScrollableParent(el, root) {
    let curr = el;
    while (curr && curr !== root && curr !== document.body && curr !== document.documentElement) {
      const style = window.getComputedStyle(curr);
      const overflowY = style.overflowY;
      const isScrollable = (overflowY === 'auto' || overflowY === 'scroll') && (curr.scrollHeight > curr.clientHeight);
      if (isScrollable) return curr;
      curr = curr.parentElement;
    }
    return null;
  }

  // Touchmove event blocker for mobile / tablet devices
  function onTouchMove(e) {
    if (!isLocked) return;

    // Find the topmost open modal
    let topModal = null;
    for (const m of activeModals) {
      topModal = m;
    }

    if (!topModal) {
      e.preventDefault();
      return;
    }

    // Check if the touch happened inside the top modal
    const isInsideTopModal = topModal.contains(e.target);
    if (!isInsideTopModal) {
      // Touching the backdrop or outside: freeze scroll completely
      if (e.cancelable) e.preventDefault();
      return;
    }

    // Check if the touch is on a drum column or scrollable container
    const scrollable = findScrollableParent(e.target, topModal);
    if (!scrollable && !e.target.closest('.drum-column')) {
      // In modal header/footer or non-scrollable area: prevent page scrolling
      if (e.cancelable && !['INPUT', 'TEXTAREA', 'BUTTON', 'SELECT', 'A'].includes(e.target.tagName)) {
        // e.preventDefault();
      }
    }
  }

  // Wheel event handler for desktop mouse
  function onWheel(e) {
    if (!isLocked) return;

    let topModal = null;
    for (const m of activeModals) {
      topModal = m;
    }

    if (!topModal) {
      e.preventDefault();
      return;
    }

    const isInside = topModal.contains(e.target);
    if (!isInside) {
      e.preventDefault();
      return;
    }

    const scrollable = findScrollableParent(e.target, topModal);
    if (!scrollable && !e.target.closest('.drum-column')) {
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
    document.body.style.touchAction = 'none';

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
    '.alert-overlay',
    '.custom-alert-overlay',
    '.tour-popup',
    '.banner-popup-overlay',
    '.broadcast-overlay',
    '.teacher-notif-overlay',
    '.notif-overlay',
    '[class*="-modal"]',
    '[role="dialog"]',
    'dialog'
  ].join(',');

  function isElementModalOpen(el) {
    if (!el || !el.isConnected) return false;

    // Never treat sidebar elements, overlays, or top navigation as background-locking modals
    if (el.classList.contains('sidebar-overlay') ||
        el.classList.contains('sidebar-wrapper') ||
        el.classList.contains('nav-sidebar') ||
        el.classList.contains('mobile-search-overlay') ||
        el.classList.contains('hero-overlay-static') ||
        el.id === 'sidebarOverlay' ||
        el.id === 'sidebar' ||
        el.closest('.sidebar-wrapper') ||
        el.closest('.top-nav-menu')) {
      return false;
    }

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
