// =============================================================================
// ABCD HIGH-PERFORMANCE STATUS BAR THEME SYNC (ZERO LAG, BUTTERY SMOOTH)
// Lightweight, non-blocking synchronization of mobile status bar theme-color
// without DOM thrashing or UI thread overhead.
// =============================================================================
(function () {
  'use strict';

  const COLOR_LIGHT_DASHBOARD = '#fff2de';
  const COLOR_LIGHT_DEFAULT   = '#ffffff';
  const COLOR_DARK_DASHBOARD  = '#17022c';
  const COLOR_DARK_GUIDY      = '#0f172a';
  const COLOR_DARK_DEFAULT    = '#0b1329';

  function getTargetColor(isDark) {
    const path = (window.location.pathname || '').toLowerCase();
    const isDashboard = path.includes('dashboard') ||
                        path.includes('seat') ||
                        path.includes('calendar') ||
                        path.includes('admission') ||
                        path.includes('register') ||
                        (document.body && document.body.dataset && document.body.dataset.pageKey && document.body.dataset.pageKey.includes('dashboard')) ||
                        document.querySelector('.top-nav-menu') !== null;

    if (isDark) {
      if (path.includes('guidy')) return COLOR_DARK_GUIDY;
      if (isDashboard) return COLOR_DARK_DASHBOARD;
      return COLOR_DARK_DEFAULT;
    } else {
      if (isDashboard) return COLOR_LIGHT_DASHBOARD;
      return COLOR_LIGHT_DEFAULT;
    }
  }

  function applyStatusBarColor(color) {
    let meta = document.getElementById('theme-color-meta');
    if (!meta) {
      meta = document.querySelector('meta[name="theme-color"]');
    }
    if (!meta) {
      meta = document.createElement('meta');
      meta.name = 'theme-color';
      meta.id = 'theme-color-meta';
      const container = document.head || document.documentElement;
      if (container) container.appendChild(meta);
    }
    if (meta && meta.getAttribute('content') !== color) {
      meta.setAttribute('content', color);
    }
  }

  function sync() {
    let isDark = false;
    if (document.body) {
      isDark = document.body.classList.contains('dark-theme');
    } else {
      try {
        const saved = localStorage.getItem('theme');
        isDark = (saved === 'dark' || saved === 'dark-theme');
      } catch (e) {}
    }
    applyStatusBarColor(getTargetColor(isDark));
  }

  // 1. Initial fast synchronous execution
  sync();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', sync, { once: true });
  }
  window.addEventListener('load', sync, { once: true });

  // 2. Single passive MutationObserver exclusively on <body> class attribute
  // Guaranteed zero thrashing: sync() never modifies <body> class, so no feedback loops occur.
  if (window.MutationObserver) {
    const observer = new MutationObserver(function (mutations) {
      for (let i = 0; i < mutations.length; i++) {
        if (mutations[i].attributeName === 'class') {
          sync();
          break;
        }
      }
    });

    if (document.body) {
      observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
    } else {
      document.addEventListener('DOMContentLoaded', function () {
        if (document.body) {
          observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
          sync();
        }
      }, { once: true });
    }
  }

  // 3. Simple cross-tab storage listener
  window.addEventListener('storage', function (e) {
    if (e.key === 'theme') {
      sync();
    }
  });

  window.syncThemeColor = sync;
})();
