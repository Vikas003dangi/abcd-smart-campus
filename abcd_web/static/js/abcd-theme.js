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

    // 1. Set color-scheme meta explicitly to 'light' or 'dark'.
    // In Android WindowInsetsController, 'light' forces dark/black icons (time, battery),
    // and 'dark' forces light/white icons.
    let colorSchemeMeta = document.getElementById('color-scheme-meta') || document.querySelector('meta[name="color-scheme"]');
    if (!colorSchemeMeta) {
      colorSchemeMeta = document.createElement('meta');
      colorSchemeMeta.name = 'color-scheme';
      colorSchemeMeta.id = 'color-scheme-meta';
      head.appendChild(colorSchemeMeta);
    }
    const targetScheme = isDark ? 'dark' : 'light';
    colorSchemeMeta.setAttribute('content', targetScheme);

    // 2. Remove ALL existing theme-color meta tags (both with and without media queries).
    // In Chromium C++ / Android WebAPK, removing and appending fresh elements triggers
    // HTMLMetaElement::InsertedInto(), which calls Android's Window.setStatusBarColor().
    const oldTags = document.querySelectorAll('meta[name="theme-color"]');
    oldTags.forEach(function (tag) {
      tag.remove();
    });

    // 3. Create 3 fresh theme-color tags with the active color:
    // a) Default tag (for all standard browsers)
    const metaDefault = document.createElement('meta');
    metaDefault.name = 'theme-color';
    metaDefault.id = 'theme-color-meta';
    metaDefault.content = color;
    head.appendChild(metaDefault);

    // b) Light media query tag
    const metaLight = document.createElement('meta');
    metaLight.name = 'theme-color';
    metaLight.media = '(prefers-color-scheme: light)';
    metaLight.content = color;
    head.appendChild(metaLight);

    // c) Dark media query tag
    // CRITICAL: When the user's Android phone is in System Dark Mode,
    // Chromium checks this tag. Setting this to the current app color (even when light #fff2de)
    // forces Chromium on Android system dark mode to apply the app's chosen color!
    const metaDark = document.createElement('meta');
    metaDark.name = 'theme-color';
    metaDark.media = '(prefers-color-scheme: dark)';
    metaDark.content = color;
    head.appendChild(metaDark);
  }

  function sync() {
    const isDark = isDarkThemeActive();
    if (document.documentElement) {
      if (isDark) {
        document.documentElement.classList.add('dark-theme');
        document.documentElement.setAttribute('data-theme', 'dark');
      } else {
        document.documentElement.classList.remove('dark-theme');
        document.documentElement.setAttribute('data-theme', 'light');
      }
    }
    if (document.body) {
      if (isDark) {
        document.body.classList.add('dark-theme');
      } else {
        document.body.classList.remove('dark-theme');
      }
    }
    applyStatusBarColor(getTargetColor(isDark), isDark);
  }

  // Expose globally so any theme toggle function can call window.syncThemeColor() directly
  window.syncThemeColor = sync;

  // Ultra-fast immediate theme application to prevent white/light flash
  (function initEarlyTheme() {
    try {
      const saved = localStorage.getItem('theme');
      const isDark = (saved === 'dark' || saved === 'dark-theme');

      if (isDark) {
        document.documentElement.classList.add('dark-theme');
        document.documentElement.setAttribute('data-theme', 'dark');
        // Inject instant high-priority CSS guard to prevent any white flash during initial parse
        const darkBg = getTargetColor(true);
        let guard = document.getElementById('abcd-early-theme-guard');
        if (!guard) {
          guard = document.createElement('style');
          guard.id = 'abcd-early-theme-guard';
          guard.textContent = 'html.dark-theme, html.dark-theme body { background-color: ' + darkBg + ' !important; color: #f8fafc !important; }';
          (document.head || document.documentElement).appendChild(guard);
        }
      } else if (saved === 'light' || saved === 'light-theme') {
        document.documentElement.classList.remove('dark-theme');
        document.documentElement.setAttribute('data-theme', 'light');
      }

      // Fast-attach to <body> BEFORE first paint as soon as browser parser creates it
      if (document.body) {
        if (isDark) document.body.classList.add('dark-theme');
        else document.body.classList.remove('dark-theme');
      } else if (window.MutationObserver) {
        const bodyObserver = new MutationObserver(function (mutations, obs) {
          if (document.body) {
            if (isDark) document.body.classList.add('dark-theme');
            else document.body.classList.remove('dark-theme');
            obs.disconnect();
          }
        });
        bodyObserver.observe(document.documentElement, { childList: true });
      }
    } catch (e) {}
  })();

  // 1. Synchronous initial run in <head>
  sync();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
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
