// =============================================================================
// ABCD DYNAMIC STATUS BAR & THEME CONTROLLER
// Automatically synchronizes native mobile status bar (time, battery, wifi)
// with the active app theme in real-time, just like YouTube and Twitter.
// =============================================================================
(function () {
  'use strict';

  // Harmonized theme colors matching ABCD's design system:
  // Light: #ffffff yields crisp dark system status bar icons (time, battery, wifi)
  // Dark: Deep night tones yield crisp white system status bar icons
  const COLOR_LIGHT = '#ffffff';
  const COLOR_DARK_DEFAULT = '#0b1329';    // Dark navy for home page & common views
  const COLOR_DARK_GUIDY = '#0f172a';      // Slate-900 matching Guidy chats header
  const COLOR_DARK_DASHBOARD = '#17022c';  // Rich plum night matching dashboard header

  function getActiveThemeColor() {
    // 1. Determine if dark theme is currently active
    const saved = localStorage.getItem('theme');
    let isDark = false;
    if (document.body) {
      isDark = document.body.classList.contains('dark-theme') || 
               document.body.classList.contains('dark') ||
               saved === 'dark' || saved === 'dark-theme';
    } else {
      isDark = saved === 'dark' || saved === 'dark-theme';
    }

    if (!isDark) {
      return COLOR_LIGHT;
    }

    // 2. Select page-appropriate dark header color
    const path = window.location.pathname || '';
    if (path.includes('/guidy') || 
        (document.body && document.body.dataset && document.body.dataset.pageKey === 'guidy') ||
        !!document.querySelector('.g-wrapper')) {
      return COLOR_DARK_GUIDY;
    }

    if (path.includes('/dashboard') || 
        (document.body && document.body.dataset && document.body.dataset.pageKey && document.body.dataset.pageKey.includes('dashboard'))) {
      return COLOR_DARK_DASHBOARD;
    }

    return COLOR_DARK_DEFAULT;
  }

  function syncThemeColor() {
    const color = getActiveThemeColor();
    let metas = document.querySelectorAll('meta[name="theme-color"]');

    if (!metas || metas.length === 0) {
      const meta = document.createElement('meta');
      meta.name = 'theme-color';
      meta.content = color;
      document.head.appendChild(meta);
    } else {
      metas.forEach(function (m) {
        m.setAttribute('content', color);
      });
    }
  }

  // 1. Synchronous early execution
  syncThemeColor();

  // 2. Execute on DOM ready and full window load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', syncThemeColor);
  }
  window.addEventListener('load', syncThemeColor);

  // 3. MutationObserver on <body> to catch dynamic theme switches (sun/moon button)
  function initObserver() {
    if (!document.body) return;
    syncThemeColor();

    const observer = new MutationObserver(function (mutations) {
      for (let i = 0; i < mutations.length; i++) {
        if (mutations[i].attributeName === 'class') {
          syncThemeColor();
          break;
        }
      }
    });

    observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
  }

  if (document.body) {
    initObserver();
  } else {
    document.addEventListener('DOMContentLoaded', initObserver);
  }

  // 4. Listen for storage changes across tabs
  window.addEventListener('storage', function (e) {
    if (e.key === 'theme') {
      syncThemeColor();
    }
  });

  // Expose helper globally
  window.syncThemeColor = syncThemeColor;
})();
