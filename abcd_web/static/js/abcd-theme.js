// =============================================================================
// ABCD HIGH-PERFORMANCE STATUS BAR THEME SYNC (ZERO LAG, BUTTERY SMOOTH)
// Lightweight, non-blocking synchronization of mobile status bar theme-color
// with full prefers-color-scheme and system dark mode override support.
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

  function applyStatusBarColor(color, isDark) {
    const head = document.head || document.documentElement;
    if (!head) return;

    // 1. Color-scheme meta to communicate page theme mode to OS / browser chrome
    let colorSchemeMeta = document.querySelector('meta[name="color-scheme"]');
    if (!colorSchemeMeta) {
      colorSchemeMeta = document.createElement('meta');
      colorSchemeMeta.name = 'color-scheme';
      head.appendChild(colorSchemeMeta);
    }
    const targetScheme = isDark ? 'dark' : 'light';
    if (colorSchemeMeta.getAttribute('content') !== targetScheme) {
      colorSchemeMeta.setAttribute('content', targetScheme);
    }

    // 2. Query all existing theme-color meta tags
    let defaultMeta = document.getElementById('theme-color-meta') || document.querySelector('meta[name="theme-color"]:not([media])');
    let lightMeta   = document.querySelector('meta[name="theme-color"][media*="light"]');
    let darkMeta    = document.querySelector('meta[name="theme-color"][media*="dark"]');

    if (!defaultMeta) {
      defaultMeta = document.createElement('meta');
      defaultMeta.name = 'theme-color';
      defaultMeta.id = 'theme-color-meta';
      head.appendChild(defaultMeta);
    }
    if (!lightMeta) {
      lightMeta = document.createElement('meta');
      lightMeta.name = 'theme-color';
      lightMeta.setAttribute('media', '(prefers-color-scheme: light)');
      head.appendChild(lightMeta);
    }
    if (!darkMeta) {
      darkMeta = document.createElement('meta');
      darkMeta.name = 'theme-color';
      darkMeta.setAttribute('media', '(prefers-color-scheme: dark)');
      head.appendChild(darkMeta);
    }

    // Update all 3 meta tags to the active color.
    // Setting the dark-media tag to the light color when in light mode is CRITICAL:
    // It forces Chrome on Android (even when system dark mode is active) to evaluate
    // the matching dark query and render the light cream status bar!
    if (defaultMeta.getAttribute('content') !== color) defaultMeta.setAttribute('content', color);
    if (lightMeta.getAttribute('content') !== color) lightMeta.setAttribute('content', color);
    if (darkMeta.getAttribute('content') !== color) darkMeta.setAttribute('content', color);
  }

  function isDarkThemeActive() {
    if (document.body && document.body.classList) {
      if (document.body.classList.contains('dark-theme') || document.body.classList.contains('dark')) {
        return true;
      }
    }
    try {
      const saved = localStorage.getItem('theme');
      if (saved === 'dark' || saved === 'dark-theme') return true;
      if (saved === 'light' || saved === 'light-theme') return false;
    } catch (e) {}
    return false;
  }

  function sync() {
    const isDark = isDarkThemeActive();
    applyStatusBarColor(getTargetColor(isDark), isDark);
  }

  // Early class assignment to avoid white flash on dark reload
  try {
    const saved = localStorage.getItem('theme');
    if (saved === 'dark' || saved === 'dark-theme') {
      if (document.body) {
        document.body.classList.add('dark-theme');
      } else {
        document.documentElement.classList.add('dark-theme');
      }
    }
  } catch (e) {}

  // 1. Initial fast synchronous execution
  sync();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      if (document.documentElement.classList.contains('dark-theme') && document.body && !document.body.classList.contains('dark-theme')) {
        document.body.classList.add('dark-theme');
      }
      sync();
    }, { once: true });
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
