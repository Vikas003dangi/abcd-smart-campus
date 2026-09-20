/**
 * ABCD Smart Campus - Lightweight Modal Scroll Lock Helper
 * Featherlight, passive scroll lock without DOM thrashing or event interception.
 */
(function() {
  'use strict';

  if (window.__ABCD_MODAL_SCROLL_LOCK__) return;

  let lockCount = 0;
  let savedScrollY = 0;

  function lockModal() {
    lockCount++;
    if (lockCount === 1) {
      savedScrollY = window.pageYOffset || document.documentElement.scrollTop || 0;
      document.body.classList.add('abcd-scroll-locked');
      document.documentElement.classList.add('abcd-scroll-locked');
    }
  }

  function unlockModal() {
    if (lockCount > 0) lockCount--;
    if (lockCount === 0) {
      document.body.classList.remove('abcd-scroll-locked');
      document.documentElement.classList.remove('abcd-scroll-locked');
      if (savedScrollY > 0) {
        window.scrollTo({ top: savedScrollY, behavior: 'instant' });
      }
    }
  }

  function syncModalScrollLock() {
    // No-op passive stub to prevent errors from callers
  }

  // Expose global API
  window.__ABCD_MODAL_SCROLL_LOCK__ = {
    lock: lockModal,
    unlock: unlockModal,
    sync: syncModalScrollLock,
    isLocked: () => lockCount > 0,
    getActiveCount: () => lockCount
  };

  window.lockModalScroll = lockModal;
  window.unlockModalScroll = unlockModal;
  window.syncModalScrollLock = syncModalScrollLock;
})();
