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
    try {
      const saved = localStorage.getItem('theme');
      if (saved === 'dark' || saved === 'dark-theme') return true;
      if (saved === 'light' || saved === 'light-theme') return false;
    } catch (e) {}
    if (document.documentElement && document.documentElement.classList) {
      if (document.documentElement.classList.contains('dark-theme') || document.documentElement.classList.contains('dark')) {
        return true;
      }
    }
    if (document.body && document.body.classList) {
      if (document.body.classList.contains('dark-theme') || document.body.classList.contains('dark')) {
        return true;
      }
    }
    return false;
  }

  function applyStatusBarColor(color, isDark) {
    const head = document.head || document.documentElement;
    if (!head) return;

    // 1. Set color-scheme meta explicitly to 'light' or 'dark'.
    let colorSchemeMeta = document.getElementById('color-scheme-meta') || document.querySelector('meta[name="color-scheme"]');
    if (!colorSchemeMeta) {
      colorSchemeMeta = document.createElement('meta');
      colorSchemeMeta.name = 'color-scheme';
      colorSchemeMeta.id = 'color-scheme-meta';
      head.appendChild(colorSchemeMeta);
    }
    const targetScheme = isDark ? 'dark' : 'light';
    const currentScheme = colorSchemeMeta.getAttribute('content');
    if (currentScheme !== targetScheme) {
      colorSchemeMeta.setAttribute('content', targetScheme);
    }

    // Fast check: if primary meta tag already matches target color, avoid DOM thrashing
    const existingDefault = document.getElementById('theme-color-meta');
    if (existingDefault && existingDefault.getAttribute('content') === color && currentScheme === targetScheme) {
      return;
    }

    // 2. Remove ALL existing theme-color meta tags
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
    const metaDark = document.createElement('meta');
    metaDark.name = 'theme-color';
    metaDark.media = '(prefers-color-scheme: dark)';
    metaDark.content = color;
    head.appendChild(metaDark);
  }

  let isSyncing = false;

  function sync() {
    if (isSyncing) return;
    isSyncing = true;
    try {
      const isDark = isDarkThemeActive();
      if (document.documentElement) {
        if (isDark) {
          if (!document.documentElement.classList.contains('dark-theme')) {
            document.documentElement.classList.add('dark-theme');
          }
          if (document.documentElement.getAttribute('data-theme') !== 'dark') {
            document.documentElement.setAttribute('data-theme', 'dark');
          }
        } else {
          if (document.documentElement.classList.contains('dark-theme')) {
            document.documentElement.classList.remove('dark-theme');
          }
          if (document.documentElement.getAttribute('data-theme') !== 'light') {
            document.documentElement.setAttribute('data-theme', 'light');
          }
        }
      }
      if (document.body) {
        if (isDark) {
          if (!document.body.classList.contains('dark-theme')) {
            document.body.classList.add('dark-theme');
          }
        } else {
          if (document.body.classList.contains('dark-theme')) {
            document.body.classList.remove('dark-theme');
          }
        }
      }
      applyStatusBarColor(getTargetColor(isDark), isDark);
    } finally {
      isSyncing = false;
    }
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
      if (isSyncing) return;
      for (let i = 0; i < mutations.length; i++) {
        if (mutations[i].attributeName === 'class') {
          const isDark = isDarkThemeActive();
          const hasDark = document.body && document.body.classList.contains('dark-theme');
          if (isDark !== hasDark) {
            sync();
          }
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
