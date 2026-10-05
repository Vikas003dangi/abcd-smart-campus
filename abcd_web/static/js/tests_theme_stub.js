// =============================================================================
// ABCD THEME & LONG-PRESS NODE STUB TEST
// Validates unified toggle, event dispatching, and contextmenu input guard.
// =============================================================================
const assert = require('assert');
const fs = require('fs');
const path = require('path');

console.log('Running ABCD Theme & Contextmenu Node Stub Tests...');

// 1. Build Mock Browser DOM Environment
class MockClassList {
  constructor() {
    this.classes = new Set();
  }
  add(c) { this.classes.add(c); }
  remove(c) { this.classes.delete(c); }
  contains(c) { return this.classes.has(c); }
  toggle(c, force) {
    if (typeof force === 'boolean') {
      if (force) this.classes.add(c);
      else this.classes.delete(c);
      return force;
    }
    if (this.classes.has(c)) {
      this.classes.delete(c);
      return false;
    } else {
      this.classes.add(c);
      return true;
    }
  }
}

class MockElement {
  constructor(tagName, id = '', className = '') {
    this.tagName = (tagName || 'DIV').toUpperCase();
    this.id = id;
    this.className = className;
    this.classList = new MockClassList();
    if (className) {
      className.split(/\s+/).filter(Boolean).forEach(c => this.classList.add(c));
    }
    this.attributes = {};
    this.style = {};
    this.children = [];
    this.parentElement = null;
    this.content = '';
    this.dataset = {};
  }
  setAttribute(k, v) { this.attributes[k] = String(v); if (k === 'content') this.content = String(v); }
  getAttribute(k) { return this.attributes[k] !== undefined ? this.attributes[k] : null; }
  hasAttribute(k) { return this.attributes[k] !== undefined; }
  appendChild(child) {
    this.children.push(child);
    child.parentElement = this;
    return child;
  }
  closest(selector) {
    let curr = this;
    const parts = selector.split(',').map(s => s.trim());
    while (curr) {
      for (const part of parts) {
        if (part === 'input' && curr.tagName === 'INPUT') return curr;
        if (part === 'textarea' && curr.tagName === 'TEXTAREA') return curr;
        if (part.includes('[contenteditable') && (curr.getAttribute('contenteditable') === 'true' || curr.getAttribute('contenteditable') === '')) return curr;
        if (part.includes('[data-allow-context') && (curr.hasAttribute('data-allow-context') || curr.dataset.allowContext !== undefined)) return curr;
        if (part.startsWith('.') && curr.classList.contains(part.substring(1))) return curr;
      }
      curr = curr.parentElement;
    }
    return null;
  }
  querySelector(sel) {
    for (const c of this.children) {
      if (sel.startsWith('.') && c.classList.contains(sel.substring(1))) return c;
      if (sel.startsWith('#') && c.id === sel.substring(1)) return c;
      if (sel.toUpperCase() === c.tagName) return c;
    }
    return null;
  }
}

const mockStorage = {
  store: {},
  getItem(k) { return this.store[k] || null; },
  setItem(k, v) { this.store[k] = String(v); },
  removeItem(k) { delete this.store[k]; }
};

const listeners = {};
function addEventListener(targetName, type, fn, opts) {
  const key = `${targetName}:${type}`;
  if (!listeners[key]) listeners[key] = [];
  listeners[key].push({ fn, capture: opts && opts.capture });
}

function dispatchEvent(targetName, event) {
  const key = `${targetName}:${event.type}`;
  const list = listeners[key] || [];
  for (const item of list) {
    item.fn(event);
  }
}

class MockCustomEvent {
  constructor(type, init = {}) {
    this.type = type;
    this.detail = init.detail || null;
    this.defaultPrevented = false;
  }
  preventDefault() {
    this.defaultPrevented = true;
  }
}

const htmlElem = new MockElement('HTML');
const headElem = new MockElement('HEAD');
const bodyElem = new MockElement('BODY');
htmlElem.appendChild(headElem);
htmlElem.appendChild(bodyElem);

const colorSchemeMeta = new MockElement('META', 'color-scheme-meta');
colorSchemeMeta.setAttribute('name', 'color-scheme');
headElem.appendChild(colorSchemeMeta);

const themeColorMeta = new MockElement('META', 'theme-color-meta');
themeColorMeta.setAttribute('name', 'theme-color');
headElem.appendChild(themeColorMeta);

const earlyStyle = new MockElement('STYLE', 'abcd-early-theme-style');
headElem.appendChild(earlyStyle);

global.window = {
  location: { pathname: '/dashboard/teacher/' },
  addEventListener: (t, fn, opts) => addEventListener('window', t, fn, opts),
  dispatchEvent: (e) => dispatchEvent('window', e),
};
global.document = {
  documentElement: htmlElem,
  head: headElem,
  body: bodyElem,
  readyState: 'complete',
  createElement: (tag) => new MockElement(tag),
  getElementById: (id) => {
    if (id === 'color-scheme-meta') return colorSchemeMeta;
    if (id === 'theme-color-meta') return themeColorMeta;
    if (id === 'abcd-early-theme-style') return earlyStyle;
    return null;
  },
  querySelector: (sel) => {
    if (sel === 'meta[name="color-scheme"]') return colorSchemeMeta;
    if (sel === 'meta[name="theme-color"]') return themeColorMeta;
    return null;
  },
  querySelectorAll: (sel) => {
    if (sel === 'meta[name="theme-color"]') return [themeColorMeta];
    return [];
  },
  addEventListener: (t, fn, opts) => addEventListener('document', t, fn, opts),
  dispatchEvent: (e) => dispatchEvent('document', e),
};
global.localStorage = mockStorage;
global.CustomEvent = MockCustomEvent;

// 2. Load and execute abcd-theme.js
const themeScriptPath = path.join(__dirname, 'abcd-theme.js');
const scriptCode = fs.readFileSync(themeScriptPath, 'utf8');
eval(scriptCode);

// 3. Test: Unified Toggle function exists and works
assert(typeof window.abcdToggleTheme === 'function', 'window.abcdToggleTheme must be a function');
assert(typeof window.toggleTheme === 'function', 'window.toggleTheme must alias window.abcdToggleTheme');

// Toggle to Dark
let dispatchedEvents = [];
window.addEventListener('abcd-theme-change', (e) => {
  dispatchedEvents.push(e);
});

const isDarkAfterToggle = window.abcdToggleTheme(true);
assert.strictEqual(isDarkAfterToggle, true, 'abcdToggleTheme(true) should return true');
assert.strictEqual(mockStorage.getItem('theme'), 'dark', 'localStorage theme must be set to dark');
assert(htmlElem.classList.contains('dark-theme'), 'html must have dark-theme class');
assert(bodyElem.classList.contains('dark-theme'), 'body must have dark-theme class');
assert.strictEqual(htmlElem.style.colorScheme, 'dark', 'root colorScheme must be dark');
assert.strictEqual(colorSchemeMeta.getAttribute('content'), 'dark', 'color-scheme meta must be dark');
assert(themeColorMeta.getAttribute('content') === '#17022c', 'theme-color meta must match dark dashboard');
assert.strictEqual(dispatchedEvents.length, 1, 'abcd-theme-change event must be dispatched');
assert.strictEqual(dispatchedEvents[0].detail.isDark, true, 'event detail.isDark must be true');

// Toggle to Light
const isLightAfterToggle = window.abcdToggleTheme(false);
assert.strictEqual(isLightAfterToggle, false, 'abcdToggleTheme(false) should return false');
assert.strictEqual(mockStorage.getItem('theme'), 'light', 'localStorage theme must be set to light');
assert(!htmlElem.classList.contains('dark-theme'), 'html must not have dark-theme class');
assert(!bodyElem.classList.contains('dark-theme'), 'body must not have dark-theme class');
assert.strictEqual(htmlElem.style.colorScheme, 'light', 'root colorScheme must be light');
assert.strictEqual(colorSchemeMeta.getAttribute('content'), 'light', 'color-scheme meta must be light');
assert.strictEqual(themeColorMeta.getAttribute('content'), '#fff2de', 'theme-color meta must match light dashboard');
assert.strictEqual(dispatchedEvents.length, 2, 'second abcd-theme-change event must be dispatched');
assert.strictEqual(dispatchedEvents[1].detail.isDark, false, 'second event detail.isDark must be false');

// 4. Test: Contextmenu event guard
function simulateContextMenu(targetElement) {
  const evt = new MockCustomEvent('contextmenu');
  evt.target = targetElement;
  dispatchEvent('document', evt);
  return evt;
}

// Interactive & content elements outside forms MUST be prevented (no Chrome callout)
const linkEl = new MockElement('A');
bodyElem.appendChild(linkEl);
assert.strictEqual(simulateContextMenu(linkEl).defaultPrevented, true, 'Links must have contextmenu prevented');

const imgEl = new MockElement('IMG');
bodyElem.appendChild(imgEl);
assert.strictEqual(simulateContextMenu(imgEl).defaultPrevented, true, 'Images must have contextmenu prevented');

const cardEl = new MockElement('DIV', '', 'card');
bodyElem.appendChild(cardEl);
assert.strictEqual(simulateContextMenu(cardEl).defaultPrevented, true, 'Cards must have contextmenu prevented');

const navBtn = new MockElement('BUTTON', '', 'btn');
bodyElem.appendChild(navBtn);
assert.strictEqual(simulateContextMenu(navBtn).defaultPrevented, true, 'Buttons must have contextmenu prevented');

// Inputs, textareas, contenteditable, and [data-allow-context] MUST NOT be prevented (allow typing/paste)
const inputEl = new MockElement('INPUT');
bodyElem.appendChild(inputEl);
assert.strictEqual(simulateContextMenu(inputEl).defaultPrevented, false, 'Input fields must NOT have contextmenu prevented');

const textareaEl = new MockElement('TEXTAREA');
bodyElem.appendChild(textareaEl);
assert.strictEqual(simulateContextMenu(textareaEl).defaultPrevented, false, 'Textareas must NOT have contextmenu prevented');

const editableEl = new MockElement('DIV');
editableEl.setAttribute('contenteditable', 'true');
bodyElem.appendChild(editableEl);
assert.strictEqual(simulateContextMenu(editableEl).defaultPrevented, false, 'contenteditable elements must NOT have contextmenu prevented');

const allowContextEl = new MockElement('P');
allowContextEl.setAttribute('data-allow-context', 'true');
bodyElem.appendChild(allowContextEl);
assert.strictEqual(simulateContextMenu(allowContextEl).defaultPrevented, false, 'data-allow-context elements must NOT have contextmenu prevented');

console.log('ALL NODE STUB TESTS PASSED SUCCESSFULLY! (Toggle, Events, Contextmenu Guard)');
