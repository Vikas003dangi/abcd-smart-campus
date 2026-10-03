/**
 * ABCD Smart Campus - Avatar Resolution & Global Safety Net
 *
 * Provides central helper functions:
 *   - window.abcdGenderAvatar(sex)
 *   - window.abcdAvatar(photoUrl, sex)
 *
 * Plus an active capture-phase error listener & MutationObserver to guarantee
 * that any avatar image with a broken URL or missing src silently degrades
 * to the proper gender default avatar without displaying broken image icons or alt text.
 */
(function () {
  'use strict';

  const MALE_AVATAR = '/static/data/default_avatar_male.png';
  const FEMALE_AVATAR = '/static/data/default_avatar_female.png';
  const DEFAULT_AVATAR = '/static/data/default_avatar.png';

  window.abcdGenderAvatar = function (sex) {
    const s = (sex || '').toString().trim().toLowerCase();
    if (s === 'female' || s === 'f' || s.startsWith('fem')) {
      return FEMALE_AVATAR;
    }
    if (s === 'male' || s === 'm' || s.startsWith('mal')) {
      return MALE_AVATAR;
    }
    return DEFAULT_AVATAR;
  };

  window.abcdAvatar = function (photoUrl, sex) {
    if (photoUrl && typeof photoUrl === 'string') {
      const clean = photoUrl.trim();
      const lower = clean.toLowerCase();
      if (
        clean !== '' &&
        lower !== 'none' &&
        lower !== 'null' &&
        lower !== 'undefined' &&
        lower !== 'no_photo' &&
        lower !== 'false'
      ) {
        // If it's a generic default avatar and we have a specific gender, upgrade it
        if (clean.endsWith('/default_avatar.png') || clean === DEFAULT_AVATAR) {
          const genderAv = window.abcdGenderAvatar(sex);
          if (genderAv !== DEFAULT_AVATAR) {
            return genderAv;
          }
        }
        return clean;
      }
    }
    return window.abcdGenderAvatar(sex);
  };

  function isAvatarElement(el) {
    if (!el || el.tagName !== 'IMG') return false;

    // Direct attribute indicators
    if (el.hasAttribute('data-avatar-sex') || el.hasAttribute('data-sex') || el.hasAttribute('data-is-avatar')) {
      return true;
    }

    // Specific avatar class indicators
    if (
      el.classList.contains('avatar') ||
      el.classList.contains('profile-photo') ||
      el.classList.contains('user-avatar-img') ||
      el.classList.contains('student-photo') ||
      el.classList.contains('race-marker') ||
      el.classList.contains('header-avatar') ||
      el.classList.contains('mam-user-avatar') ||
      el.classList.contains('ach-photo') ||
      el.classList.contains('card-avatar') ||
      el.classList.contains('bnav-profile-circle') ||
      el.classList.contains('alumni-photo-small') ||
      el.classList.contains('cv-photo')
    ) {
      return true;
    }

    // Known avatar IDs
    if (['profile-img-main', 'alumni-profile-img', 'greetingAvatar', 'mamPhotoPreview', 'photoPreviewCustom'].includes(el.id)) {
      return true;
    }

    // Known avatar containers
    if (
      el.closest(
        '.notif-avatar-container, .expired-avatar, .request-avatar-wrap, .user-avatar-wrapper, .avatar-frame, .ach-photo-wrapper, .g-msg-avatar, .profile-avatar-wrap, .circle-view, .exp-photo-wrap'
      ) !== null
    ) {
      return true;
    }

    return false;
  }

  function isExcludedNonAvatar(el) {
    if (!el) return true;
    if (
      el.classList.contains('complaint-thumb') ||
      el.classList.contains('complaint-img') ||
      el.classList.contains('lb-img') ||
      el.id === 'lbTargetImg' ||
      el.id === 'ribbonImg' ||
      el.classList.contains('card-ribbon') ||
      el.classList.contains('card-logo') ||
      el.closest('.complaint-thumbs, .images-grid, .history-attachments-grid, .preview-attachments, [data-preview-media]') !== null
    ) {
      return true;
    }
    return false;
  }

  function resolveElementSex(el) {
    if (!el) return '';
    const direct = el.getAttribute('data-avatar-sex') || el.getAttribute('data-sex');
    if (direct) return direct;
    const parentWithSex = el.closest('[data-avatar-sex], [data-sex]');
    if (parentWithSex) {
      return parentWithSex.getAttribute('data-avatar-sex') || parentWithSex.getAttribute('data-sex') || '';
    }
    return '';
  }

  function applyAvatarFallback(img) {
    if (!img || img.dataset.avatarFallbackTried === 'true') return;

    const currentSrc = img.getAttribute('src') || '';
    if (
      currentSrc.includes('default_avatar_male.png') ||
      currentSrc.includes('default_avatar_female.png') ||
      currentSrc.includes('default_avatar.png')
    ) {
      return;
    }

    if (!isAvatarElement(img) || isExcludedNonAvatar(img)) {
      return;
    }

    // If an initial badge is being displayed as a fallback, don't overwrite
    const nextEl = img.nextElementSibling;
    if (nextEl && nextEl.classList && (nextEl.classList.contains('user-avatar-initial') || nextEl.classList.contains('student-photo-initials')) && img.style.display === 'none') {
      return;
    }

    img.dataset.avatarFallbackTried = 'true';
    const sex = resolveElementSex(img);
    img.src = window.abcdGenderAvatar(sex);
  }

  // 1. Capture-phase image error listener
  window.addEventListener('error', function (event) {
    const target = event.target;
    if (target && target.tagName === 'IMG') {
      applyAvatarFallback(target);
    }
  }, true);

  // 2. MutationObserver for dynamic insertions or src updates
  function inspectAndFixAvatarImg(img) {
    if (!img || img.tagName !== 'IMG') return;
    if (img.dataset.avatarFallbackTried === 'true') return;
    const src = img.getAttribute('src');
    if (src === '' || src === 'null' || src === 'undefined' || src === 'None') {
      if (isAvatarElement(img) && !isExcludedNonAvatar(img)) {
        img.dataset.avatarFallbackTried = 'true';
        const sex = resolveElementSex(img);
        img.src = window.abcdGenderAvatar(sex);
      }
    }
  }

  try {
    const avatarObserver = new MutationObserver(function (mutations) {
      for (let i = 0; i < mutations.length; i++) {
        const m = mutations[i];
        if (m.type === 'childList') {
          for (let j = 0; j < m.addedNodes.length; j++) {
            const node = m.addedNodes[j];
            if (node.nodeType === 1) {
              if (node.tagName === 'IMG') {
                inspectAndFixAvatarImg(node);
              } else if (node.querySelectorAll) {
                const imgs = node.querySelectorAll('img');
                for (let k = 0; k < imgs.length; k++) {
                  inspectAndFixAvatarImg(imgs[k]);
                }
              }
            }
          }
        } else if (m.type === 'attributes' && m.attributeName === 'src') {
          inspectAndFixAvatarImg(m.target);
        }
      }
    });

    if (document.body) {
      avatarObserver.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['src'] });
    } else {
      document.addEventListener('DOMContentLoaded', function () {
        if (document.body) {
          avatarObserver.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['src'] });
        }
      });
    }
  } catch (e) {
    // Graceful degradation if MutationObserver is unsupported
  }
})();
