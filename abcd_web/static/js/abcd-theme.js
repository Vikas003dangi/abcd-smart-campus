// =============================================================================
// ABCD DYNAMIC STATUS BAR & THEME CONTROLLER
// Real-time synchronization of native mobile status bar (time, battery, wifi)
// with the active app theme, engineered for Chrome, WebAPK, and Android TWAs.
// =============================================================================
(function () {
  'use strict';

  // Harmonized theme colors matching ABCD's design tokens:
  // Dashboard / Seats: top gradient slice is #fff2de (light) & #17022c (dark plum)
  // Guidy: slate-900 header #0f172a (dark) & #ffffff (light)
  // Home & other views: clean white #ffffff (light) & dark navy #0b1329 (dark)
  const COLOR_LIGHT_DEFAULT   = '#ffffff';
  const COLOR_LIGHT_DASHBOARD = '#fff2de';
  const COLOR_DARK_DEFAULT    = '#0b1329';
  const COLOR_DARK_GUIDY      = '#0f172a';
  const COLOR_DARK_DASHBOARD  = '#17022c';

  let currentAppliedColor = null;

  function isDarkActive() {
    try {
      const saved = localStorage.getItem('theme');
      if (saved === 'dark' || saved === 'dark-theme') return true;
      if (saved === 'light' || saved === 'light-theme') return false;
    } catch (e) {}

    if (document.body && (document.body.classList.contains('dark-theme') || document.body.classList.contains('dark'))) {
      return true;
    }
    if (document.documentElement && (document.documentElement.classList.contains('dark-theme') || document.documentElement.classList.contains('dark'))) {
      return true;
    }
    return false;
  }

  function getActiveThemeColor() {
    const isDark = isDarkActive();
    const path = (window.location.pathname || '').toLowerCase();
    const pageKey = (document.body && document.body.dataset && document.body.dataset.pageKey) ? document.body.dataset.pageKey.toLowerCase() : '';

    const isDashboard = path.includes('dashboard') ||
                        path.includes('seat') ||
                        path.includes('calendar') ||
                        path.includes('admission') ||
                        path.includes('register') ||
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

  // Forces Android Chrome / TWA to update the system status bar by replacing the meta node
  function updateThemeColorMeta(color) {
    if (currentAppliedColor === color) {
      const existing = document.getElementById('theme-color-meta');
      if (existing && existing.getAttribute('content') === color) {
        return;
      }
    }
    currentAppliedColor = color;

    // Remove all existing theme-color meta tags
    const existingMetas = document.querySelectorAll('meta[name="theme-color"]');
    existingMetas.forEach(function (m) {
      try { m.remove(); } catch (e) {}
    });

    // Create a fresh new meta element (triggers Chrome Android WebContents node-added observer)
    const newMeta = document.createElement('meta');
    newMeta.name = 'theme-color';
    newMeta.id = 'theme-color-meta';
    newMeta.content = color;

    const targetContainer = document.head || document.documentElement;
    if (targetContainer) {
      targetContainer.appendChild(newMeta);
    }
  }

  function syncThemeColor() {
    const isDark = isDarkActive();
    const color = getActiveThemeColor();

    // 1. Maintain dark-theme class on root element to prevent white flicker
    if (document.documentElement) {
      if (isDark && !document.documentElement.classList.contains('dark-theme')) {
        document.documentElement.classList.add('dark-theme');
      } else if (!isDark && document.documentElement.classList.contains('dark-theme')) {
        document.documentElement.classList.remove('dark-theme');
      }
    }

    // 2. Dispatch the fresh theme-color meta node
    updateThemeColorMeta(color);
  }

  // 1. Immediate execution in <head>
  syncThemeColor();

  // 2. Execution on DOM stages
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', syncThemeColor);
  }
  window.addEventListener('load', syncThemeColor);

  // 3. Intercept localStorage.setItem('theme') so ANY in-app toggle updates status bar instantly
  try {
    const origSetItem = localStorage.setItem.bind(localStorage);
    localStorage.setItem = function (key, val) {
      origSetItem(key, val);
      if (key === 'theme') {
        setTimeout(syncThemeColor, 0);
        setTimeout(syncThemeColor, 60);
      }
    };
  } catch (e) {}

  // 4. MutationObserver on <html> and <body> for reactive class updates
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

  // 5. Global click listener for all theme toggle buttons across the app
  document.addEventListener('click', function (e) {
    const btn = e.target.closest('#theme-toggle, #themeToggle, #themeBtn, .theme-toggle, .theme-toggle-btn, [onclick*="toggleTheme"]');
    if (btn) {
      setTimeout(syncThemeColor, 0);
      setTimeout(syncThemeColor, 60);
      setTimeout(syncThemeColor, 200);
    }
  }, true);

  // 6. Cross-tab storage and custom events
  window.addEventListener('storage', function (e) {
    if (e.key === 'theme') {
      syncThemeColor();
    }
  });

  window.addEventListener('themechange', syncThemeColor);
  window.addEventListener('themeChanged', syncThemeColor);

  // Expose globally
  window.syncThemeColor = syncThemeColor;
  window.updateThemeColor = syncThemeColor;
})();
