// =============================================================================
// ABCD HIGH-PERFORMANCE UNIFIED THEME ENGINE & LONG-PRESS MANAGER
// Status bar color, color-scheme, document theme classes, and Chrome callouts
// are synchronously synchronized and event-driven across Web & Android TWA.
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

    // 1. Set color-scheme explicitly on root and meta
    if (document.documentElement) {
      document.documentElement.style.colorScheme = isDark ? 'dark' : 'light';
    }

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

    // 2. Update all existing theme-color meta tags
    const existingTags = document.querySelectorAll('meta[name="theme-color"]');
    if (existingTags.length > 0) {
      existingTags.forEach(function (tag) {
        tag.setAttribute('content', color);
      });
      return;
    }

    // 3. Otherwise create 3 fresh theme-color tags (default, light query, dark query)
    const metaDefault = document.createElement('meta');
    metaDefault.name = 'theme-color';
    metaDefault.id = 'theme-color-meta';
    metaDefault.content = color;
    head.appendChild(metaDefault);

    const metaLight = document.createElement('meta');
    metaLight.name = 'theme-color';
    metaLight.media = '(prefers-color-scheme: light)';
    metaLight.content = color;
    head.appendChild(metaLight);

    const metaDark = document.createElement('meta');
    metaDark.name = 'theme-color';
    metaDark.media = '(prefers-color-scheme: dark)';
    metaDark.content = color;
    head.appendChild(metaDark);
  }

  function updateToggleIcons(isDark) {
    // 1. Update img-based or class-based theme icons
    const icons = document.querySelectorAll('#themeIcon, .theme-icon, #theme-icon');
    icons.forEach(function (icon) {
      if (icon.tagName === 'IMG') {
        icon.src = isDark ? '/static/data/night.png' : '/static/data/day.png';
      } else {
        icon.className = isDark ? 'bx bx-sun' : 'bx bx-moon';
      }
    });

    // 2. Update button children
    const toggles = document.querySelectorAll('#theme-toggle, #themeToggle, #themeBtn, .theme-toggle-btn, .theme-toggle-fixed, .theme-btn');
    toggles.forEach(function (toggle) {
      const bx = toggle.querySelector('i');
      if (bx) {
        bx.className = isDark ? 'bx bx-sun' : 'bx bx-moon';
      }
      const img = toggle.querySelector('img');
      if (img) {
        img.src = isDark ? '/static/data/night.png' : '/static/data/day.png';
      }
    });

    // 3. Seat search input inline color sync if present
    const searchInput = document.getElementById('seatSearchInput');
    if (searchInput) {
      searchInput.style.color = isDark ? '#f8fafc' : '#1e293b';
    }
  }

  let isSyncing = false;

  function sync(forceDark) {
    if (isSyncing) return;
    isSyncing = true;
    try {
      const isDark = (typeof forceDark === 'boolean') ? forceDark : isDarkThemeActive();
      const root = document.documentElement;
      const body = document.body;

      if (root) {
        if (isDark) {
          if (!root.classList.contains('dark-theme')) root.classList.add('dark-theme');
          if (root.getAttribute('data-theme') !== 'dark') root.setAttribute('data-theme', 'dark');
          root.style.colorScheme = 'dark';
        } else {
          if (root.classList.contains('dark-theme')) root.classList.remove('dark-theme');
          if (root.getAttribute('data-theme') !== 'light') root.setAttribute('data-theme', 'light');
          root.style.colorScheme = 'light';
        }
      }

      if (body) {
        if (isDark) {
          if (!body.classList.contains('dark-theme')) body.classList.add('dark-theme');
          if (body.getAttribute('data-theme') !== 'dark') body.setAttribute('data-theme', 'dark');
        } else {
          if (body.classList.contains('dark-theme')) body.classList.remove('dark-theme');
          if (body.getAttribute('data-theme') !== 'light') body.setAttribute('data-theme', 'light');
        }
      }

      const targetColor = getTargetColor(isDark);
      applyStatusBarColor(targetColor, isDark);
      updateToggleIcons(isDark);

      // Update early inline guard style
      let guard = document.getElementById('abcd-early-theme-style');
      if (!guard) {
        guard = document.getElementById('abcd-early-theme-guard');
      }
      if (guard) {
        guard.textContent = isDark
          ? 'html, html.dark-theme { background-color: ' + targetColor + ' !important; color-scheme: dark !important; } html.dark-theme body { background-color: ' + targetColor + ' !important; background-image: none; color-scheme: dark !important; }'
          : 'html, html:not(.dark-theme) { background-color: ' + targetColor + ' !important; color-scheme: light !important; }';
      }
    } finally {
      isSyncing = false;
    }
  }

  // =============================================================================
  // SINGLE UNIFIED THEME TOGGLE FUNCTION
  // Updates classes, color-scheme, meta tags, localStorage, and dispatches events.
  // =============================================================================
  function abcdToggleTheme(forceTheme) {
    const currentlyDark = isDarkThemeActive();
    let makeDark;
    if (typeof forceTheme === 'boolean') {
      makeDark = forceTheme;
    } else if (typeof forceTheme === 'string') {
      makeDark = (forceTheme === 'dark' || forceTheme === 'dark-theme');
    } else {
      makeDark = !currentlyDark;
    }

    const themeStr = makeDark ? 'dark' : 'light';
    try {
      localStorage.setItem('theme', themeStr);
    } catch (e) {}

    // Perform immediate synchronous DOM & status bar update
    sync(makeDark);

    // Dispatch unified events for all listeners (charts, canvases, widgets)
    const targetColor = getTargetColor(makeDark);
    const evtDetail = { theme: themeStr, isDark: makeDark, color: targetColor };
    const evt1 = new CustomEvent('abcd-theme-change', { detail: evtDetail });
    const evt2 = new CustomEvent('theme-changed', { detail: evtDetail });

    try {
      window.dispatchEvent(evt1);
      document.dispatchEvent(evt1);
      window.dispatchEvent(evt2);
      document.dispatchEvent(evt2);
    } catch (e) {}

    return makeDark;
  }

  // Expose globally
  window.abcdToggleTheme = abcdToggleTheme;
  window.toggleTheme = abcdToggleTheme;
  window.syncThemeColor = sync;

  // Ultra-fast immediate theme application to prevent white/light flash
  (function initEarlyTheme() {
    try {
      const saved = localStorage.getItem('theme');
      const isDark = (saved === 'dark' || saved === 'dark-theme');
      const root = document.documentElement;

      if (root) {
        if (isDark) {
          root.classList.add('dark-theme');
          root.setAttribute('data-theme', 'dark');
          root.style.colorScheme = 'dark';
        } else if (saved === 'light' || saved === 'light-theme') {
          root.classList.remove('dark-theme');
          root.setAttribute('data-theme', 'light');
          root.style.colorScheme = 'light';
        }
      }

      const darkBg = getTargetColor(isDark);
      let guard = document.getElementById('abcd-early-theme-style');
      if (!guard) {
        guard = document.getElementById('abcd-early-theme-guard');
      }
      if (!guard) {
        guard = document.createElement('style');
        guard.id = 'abcd-early-theme-style';
        (document.head || root).appendChild(guard);
      }
      guard.textContent = isDark
        ? 'html, html.dark-theme { background-color: ' + darkBg + ' !important; color-scheme: dark !important; } html.dark-theme body { background-color: ' + darkBg + ' !important; background-image: none; color-scheme: dark !important; }'
        : 'html, html:not(.dark-theme) { background-color: ' + darkBg + ' !important; color-scheme: light !important; }';

      // Attach immediately to <body> before first paint
      if (document.body) {
        if (isDark) {
          document.body.classList.add('dark-theme');
          document.body.setAttribute('data-theme', 'dark');
        } else {
          document.body.classList.remove('dark-theme');
          document.body.setAttribute('data-theme', 'light');
        }
      } else if (window.MutationObserver) {
        const bodyObserver = new MutationObserver(function () {
          if (document.body) {
            if (isDark) {
              document.body.classList.add('dark-theme');
              document.body.setAttribute('data-theme', 'dark');
            } else {
              document.body.classList.remove('dark-theme');
              document.body.setAttribute('data-theme', 'light');
            }
            bodyObserver.disconnect();
          }
        });
        bodyObserver.observe(root, { childList: true });
      }
    } catch (e) {}
  })();

  // Synchronous initial run in <head>
  sync();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      sync();
    }, { once: true });
  }
  window.addEventListener('load', function () {
    sync();
  }, { once: true });

  // Passive MutationObserver on <body> class attribute for external modifications
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

  // =============================================================================
  // LONG-PRESS SUPPRESSION FOR LINKS, IMAGES, CARDS & PAGE CONTENT
  // Suppresses Chrome TWA long-press context menu ("Open in new tab", "Preview"...)
  // while preserving text typing, copy/paste, and input menus in forms and chat.
  // =============================================================================
  function isContextMenuAllowed(target) {
    if (!target || !target.closest) return false;
    return !!target.closest(
      'input, textarea, [contenteditable="true"], [contenteditable=""], [data-allow-context], [data-allow-context="true"], .allow-context-menu'
    );
  }

  // Delegated capture listener: intercept contextmenu on interactive/content elements outside forms
  document.addEventListener('contextmenu', function (e) {
    if (!isContextMenuAllowed(e.target)) {
      e.preventDefault();
    }
  }, { capture: true, passive: false });

  // Inject CSS rules for iOS/Android touch callout and drag prevention
  (function injectLongPressStyles() {
    const styleId = 'abcd-long-press-rules';
    if (document.getElementById(styleId)) return;
    const style = document.createElement('style');
    style.id = styleId;
    style.textContent = `
      a, img, button, [role="button"], .nav-item, .card, .menu-item,
      .btn, .icon-btn, .navbar, .bottom-nav-menu, .top-nav-menu, header, nav, footer {
        -webkit-touch-callout: none !important;
      }
      img {
        -webkit-user-drag: none;
      }
    `;
    (document.head || document.documentElement).appendChild(style);
  })();

  // Early Synchronous Avatar Resolvers for <head> scripts
  if (typeof window.abcdGenderAvatar !== 'function') {
    window.abcdGenderAvatar = function (sex) {
      const s = (sex || '').toString().trim().toLowerCase();
      if (s === 'female' || s === 'f' || s.startsWith('fem')) {
        return '/static/data/default_avatar_female.png';
      }
      if (s === 'male' || s === 'm' || s.startsWith('mal')) {
        return '/static/data/default_avatar_male.png';
      }
      return '/static/data/default_avatar.png';
    };
  }

  if (typeof window.abcdAvatar !== 'function') {
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
          if (clean.endsWith('/default_avatar.png') || clean === '/static/data/default_avatar.png') {
            const genderAv = window.abcdGenderAvatar(sex);
            if (genderAv !== '/static/data/default_avatar.png') {
              return genderAv;
            }
          }
          return clean;
        }
      }
      return window.abcdGenderAvatar(sex);
    };
  }
})();
