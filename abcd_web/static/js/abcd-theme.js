// =============================================================================
// ABCD DYNAMIC STATUS BAR & THEME CONTROLLER
// Automatically synchronizes native mobile status bar (time, battery, wifi)
// with the active app theme in real-time, matching YouTube and Twitter.
// =============================================================================
(function () {
  'use strict';

  // Harmonized theme colors matching ABCD's design system & gradients:
  // Dashboard views: top body gradient is #fff2de (light) & #17022c (dark plum)
  // Guidy views: slate-900 header is #0f172a (dark) & #ffffff (light)
  // Home & other views: clean white #ffffff (light) & dark navy #0b1329 (dark)
  const COLOR_LIGHT_DEFAULT   = '#ffffff';
  const COLOR_LIGHT_DASHBOARD = '#fff2de';
  const COLOR_DARK_DEFAULT    = '#0b1329';
  const COLOR_DARK_GUIDY      = '#0f172a';
  const COLOR_DARK_DASHBOARD  = '#17022c';

  function isDarkActive() {
    const saved = localStorage.getItem('theme');
    if (saved === 'dark' || saved === 'dark-theme') return true;
    if (saved === 'light' || saved === 'light-theme') return false;

    if (document.body) {
      if (document.body.classList.contains('dark-theme') || document.body.classList.contains('dark')) {
        return true;
      }
    }
    if (document.documentElement) {
      if (document.documentElement.classList.contains('dark-theme') || document.documentElement.classList.contains('dark')) {
        return true;
      }
    }
    return false;
  }

  function getActiveThemeColor() {
    const isDark = isDarkActive();
    const path = (window.location.pathname || '').toLowerCase();
    const pageKey = (document.body && document.body.dataset && document.body.dataset.pageKey) ? document.body.dataset.pageKey.toLowerCase() : '';

    const isDashboard = path.includes('dashboard') ||
                        path.includes('seat') ||
                        pageKey.includes('dashboard') ||
                        pageKey.includes('seat') ||
                        !!document.querySelector('.top-nav-menu');

    const isGuidy = path.includes('guidy') ||
                    pageKey.includes('guidy') ||
                    !!document.querySelector('.g-wrapper');

    if (isDark) {
      if (isGuidy) return COLOR_DARK_GUIDY;
      if (isDashboard) return COLOR_DARK_DASHBOARD;
      return COLOR_DARK_DEFAULT;
    } else {
      if (isDashboard) return COLOR_LIGHT_DASHBOARD;
      return COLOR_LIGHT_DEFAULT;
    }
  }

  function syncThemeColor() {
    const isDark = isDarkActive();
    const color = getActiveThemeColor();

    // 1. Maintain dark-theme class on root element to prevent white flicker
    if (isDark) {
      if (!document.documentElement.classList.contains('dark-theme')) {
        document.documentElement.classList.add('dark-theme');
      }
    } else {
      if (document.documentElement.classList.contains('dark-theme')) {
        document.documentElement.classList.remove('dark-theme');
      }
    }

    // 2. Manage single canonical meta[name="theme-color"]
    let targetMeta = document.getElementById('theme-color-meta');
    const allMetas = document.querySelectorAll('meta[name="theme-color"]');

    if (!targetMeta && allMetas.length > 0) {
      targetMeta = allMetas[0];
      targetMeta.id = 'theme-color-meta';
    }

    // Remove any conflicting or secondary meta tags (especially with media attributes)
    allMetas.forEach(function (m) {
      if (m !== targetMeta) {
        m.remove();
      }
    });

    if (!targetMeta) {
      targetMeta = document.createElement('meta');
      targetMeta.name = 'theme-color';
      targetMeta.id = 'theme-color-meta';
      if (document.head) {
        document.head.appendChild(targetMeta);
      } else {
        document.documentElement.appendChild(targetMeta);
      }
    }

    // Crucial: remove media query attribute so Chrome on Android dynamically respects content
    if (targetMeta.hasAttribute('media')) {
      targetMeta.removeAttribute('media');
    }

    if (targetMeta.getAttribute('content') !== color) {
      targetMeta.setAttribute('content', color);
    }
  }

  // 1. Synchronous early execution in <head>
  syncThemeColor();

  // 2. Re-sync on DOM ready and window load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', syncThemeColor);
  }
  window.addEventListener('load', syncThemeColor);

  // 3. MutationObserver on <html> and <body> for reactive class changes
  function initObservers() {
    syncThemeColor();

    const observer = new MutationObserver(function (mutations) {
      for (let i = 0; i < mutations.length; i++) {
        if (mutations[i].attributeName === 'class') {
          syncThemeColor();
          break;
        }
      }
    });

    if (document.documentElement) {
      observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    }
    if (document.body) {
      observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
    }
  }

  if (document.body) {
    initObservers();
  } else {
    document.addEventListener('DOMContentLoaded', initObservers);
  }

  // 4. Global click listener on theme toggle controls for instant response
  document.addEventListener('click', function (e) {
    const btn = e.target.closest('#themeToggle, #themeBtn, .theme-toggle-btn, .theme-toggle, [onclick*="toggleTheme"]');
    if (btn) {
      setTimeout(syncThemeColor, 0);
      setTimeout(syncThemeColor, 100);
    }
  }, true);

  // 5. Storage event for cross-tab sync
  window.addEventListener('storage', function (e) {
    if (e.key === 'theme') {
      syncThemeColor();
    }
  });

  // 6. Custom event support
  window.addEventListener('themechange', syncThemeColor);
  window.addEventListener('themeChanged', syncThemeColor);

  // Expose globally
  window.syncThemeColor = syncThemeColor;
  window.updateThemeColor = syncThemeColor;
})();
