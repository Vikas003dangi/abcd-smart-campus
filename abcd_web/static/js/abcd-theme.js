// =============================================================================
// ABCD HIGH-PERFORMANCE STATUS BAR THEME SYNC (APP-DRIVEN, NOT DEVICE-DRIVEN)
// Status bar color and icons strictly follow the ABCD APP theme (light/dark toggle)
// and NEVER get overridden by the mobile device's system dark mode setting.
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

  function isDarkThemeActive() {
    if (document.body && document.body.classList) {
      if (document.body.classList.contains('dark-theme') || document.body.classList.contains('dark')) {
        return true;
      }
    }
    if (document.documentElement && document.documentElement.classList) {
      if (document.documentElement.classList.contains('dark-theme') || document.documentElement.classList.contains('dark')) {
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

  function applyStatusBarColor(color, isDark) {
    const head = document.head || document.documentElement;
    if (!head) return;

    // 1. Purge any media-query theme-color tags (these cause Android to lock to device OS dark mode)
    const mediaTags = document.querySelectorAll('meta[name="theme-color"][media]');
    mediaTags.forEach(function (tag) {
      tag.remove();
    });

    // 2. Set color-scheme meta explicitly to 'light' or 'dark' (NOT 'light dark').
    // This instructs Android OS WindowInsetsController to set:
    // - Dark icons (time, battery, wifi in black) when 'light'
    // - Light icons (time, battery, wifi in white) when 'dark'
    let colorSchemeMeta = document.getElementById('color-scheme-meta') || document.querySelector('meta[name="color-scheme"]');
    if (!colorSchemeMeta) {
      colorSchemeMeta = document.createElement('meta');
      colorSchemeMeta.name = 'color-scheme';
      colorSchemeMeta.id = 'color-scheme-meta';
      head.appendChild(colorSchemeMeta);
    }
    const targetScheme = isDark ? 'dark' : 'light';
    if (colorSchemeMeta.getAttribute('content') !== targetScheme) {
      colorSchemeMeta.setAttribute('content', targetScheme);
    }

    // 3. Single canonical theme-color meta tag
    // Removing and re-inserting or updating the tag guarantees that Chromium's C++
    // WebContentsImpl::DidUpdateThemeColor() notifies the Android Activity to change the status bar.
    let themeMeta = document.getElementById('theme-color-meta') || document.querySelector('meta[name="theme-color"]:not([media])');
    if (!themeMeta) {
      themeMeta = document.createElement('meta');
      themeMeta.name = 'theme-color';
      themeMeta.id = 'theme-color-meta';
      head.appendChild(themeMeta);
    }
    if (themeMeta.getAttribute('content') !== color) {
      themeMeta.setAttribute('content', color);
    }
  }

  function sync() {
    const isDark = isDarkThemeActive();
    applyStatusBarColor(getTargetColor(isDark), isDark);
  }

  // Expose globally so any theme toggle function can call window.syncThemeColor() directly
  window.syncThemeColor = sync;

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

  // 1. Initial fast synchronous execution in <head>
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
        }
      }, { once: true });
    }
  }
})();
