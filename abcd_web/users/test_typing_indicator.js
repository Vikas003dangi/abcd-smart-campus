/**
 * test_typing_indicator.js
 * Node.js test suite for Guidy Chat live typing indicator client logic:
 * 1. Name formatting (1, 2, 3, 4+ users, truncation, escaping)
 * 2. Expiry timers (~4.0s)
 * 3. Throttle behavior (2.5s) & whitespace filtering
 * 4. Immediate removal on message arrival and offline signals
 */

const assert = require('assert');

// ── 1. Name Formatting Helper Under Test ──
function formatTypingNames(names) {
  if (!names || names.length === 0) return '';
  const firstNames = names.map(n => {
    const raw = String(n || '').trim().split(/\s+/)[0] || 'User';
    return raw.length > 15 ? raw.slice(0, 14) + '…' : raw;
  });
  const count = firstNames.length;
  if (count === 1) {
    return firstNames[0];
  } else if (count === 2) {
    return `${firstNames[0]} & ${firstNames[1]}`;
  } else if (count === 3) {
    return `${firstNames[0]}, ${firstNames[1]} & ${firstNames[2]}`;
  } else {
    return `${firstNames[0]}, ${firstNames[1]} & ${count - 2} others`;
  }
}

function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ── 2. Mock Typing State Manager for Timers & Message Removal ──
class TypingStateManager {
  constructor(currentUserId) {
    this.currentUserId = currentUserId;
    this.currentChatTypingUsers = new Map();
    this.renderCount = 0;
  }

  handleIncomingTypingIndicator(data) {
    if (!data) return;
    const senderId = parseInt(data.sender_id || '0');
    if (!senderId || senderId === this.currentUserId) return;

    const isTyping = !!data.is_typing;
    const firstName = data.first_name || (data.sender_name ? data.sender_name.trim().split(/\s+/)[0] : 'User');

    if (isTyping) {
      if (this.currentChatTypingUsers.has(senderId)) {
        clearTimeout(this.currentChatTypingUsers.get(senderId).timer);
      }
      const timer = setTimeout(() => {
        this.currentChatTypingUsers.delete(senderId);
        this.renderCount++;
      }, 4000);

      this.currentChatTypingUsers.set(senderId, {
        name: firstName,
        timer: timer,
        timestamp: Date.now()
      });
    } else {
      if (this.currentChatTypingUsers.has(senderId)) {
        clearTimeout(this.currentChatTypingUsers.get(senderId).timer);
        this.currentChatTypingUsers.delete(senderId);
      }
    }
    this.renderCount++;
  }

  onMessageReceived(senderId) {
    const uid = parseInt(senderId);
    if (this.currentChatTypingUsers.has(uid)) {
      clearTimeout(this.currentChatTypingUsers.get(uid).timer);
      this.currentChatTypingUsers.delete(uid);
      this.renderCount++;
    }
  }

  onUserOffline(userId) {
    const uid = parseInt(userId);
    if (this.currentChatTypingUsers.has(uid)) {
      clearTimeout(this.currentChatTypingUsers.get(uid).timer);
      this.currentChatTypingUsers.delete(uid);
      this.renderCount++;
    }
  }

  getActiveNames() {
    return Array.from(this.currentChatTypingUsers.values()).map(u => u.name);
  }
}

// ── 3. Throttle Controller Under Test ──
class TypingThrottleController {
  constructor(onSend) {
    this.onSend = onSend;
    this.lastTypingSentTs = 0;
    this.isCurrentlyTyping = false;
    this.throttledTimer = null;
    this.stopTimer = null;
  }

  onInput(rawText) {
    const text = String(rawText || '').trim();
    if (!text) {
      if (this.isCurrentlyTyping) {
        this.stop();
      }
      return;
    }

    const now = Date.now();
    if (!this.isCurrentlyTyping || (now - this.lastTypingSentTs >= 2500)) {
      this.isCurrentlyTyping = true;
      this.lastTypingSentTs = now;
      this.onSend(true);
    } else {
      if (!this.throttledTimer) {
        const wait = Math.max(0, 2500 - (now - this.lastTypingSentTs));
        this.throttledTimer = setTimeout(() => {
          this.throttledTimer = null;
          this.lastTypingSentTs = Date.now();
          this.onSend(true);
        }, wait);
      }
    }

    if (this.stopTimer) clearTimeout(this.stopTimer);
    this.stopTimer = setTimeout(() => {
      this.stop();
    }, 3500);
  }

  stop() {
    if (this.stopTimer) {
      clearTimeout(this.stopTimer);
      this.stopTimer = null;
    }
    if (this.throttledTimer) {
      clearTimeout(this.throttledTimer);
      this.throttledTimer = null;
    }
    if (this.isCurrentlyTyping) {
      this.isCurrentlyTyping = false;
      this.onSend(false);
    }
  }
}

// ── Run Tests ──
async function runTests() {
  console.log('Running Guidy Typing Indicator JS stub tests...\n');

  // Test 1: Name Formatting
  assert.strictEqual(formatTypingNames([]), '');
  assert.strictEqual(formatTypingNames(['Rahul']), 'Rahul');
  assert.strictEqual(formatTypingNames(['Rahul Sharma']), 'Rahul');
  assert.strictEqual(formatTypingNames(['Rahul', 'Priya']), 'Rahul & Priya');
  assert.strictEqual(formatTypingNames(['Rahul', 'Priya', 'Aman']), 'Rahul, Priya & Aman');
  assert.strictEqual(formatTypingNames(['Rahul', 'Priya', 'Aman', 'Sita']), 'Rahul, Priya & 2 others');
  assert.strictEqual(formatTypingNames(['Rahul', 'Priya', 'Aman', 'Sita', 'Gita']), 'Rahul, Priya & 3 others');
  assert.strictEqual(formatTypingNames(['VeryLongFirstNameThatExceedsLimit']), 'VeryLongFirstN…');
  console.log('✔ Test 1: Name formatting passed (1, 2, 3, 4+ users, truncation)');

  // Test 2: Safe HTML Escaping (no XSS injection)
  const xssNames = ['<script>alert(1)</script>', '<b>Priya</b>'];
  const formattedXss = formatTypingNames(xssNames);
  const escaped = escHtml(formattedXss);
  assert.ok(!escaped.includes('<script>'));
  assert.ok(escaped.includes('&lt;script&gt;'));
  console.log('✔ Test 2: Safe HTML escaping verified');

  // Test 3: Receiver State & Own User Exclusion
  const state = new TypingStateManager(100); // Current user is 100
  state.handleIncomingTypingIndicator({ sender_id: 100, sender_name: 'Me', is_typing: true });
  assert.strictEqual(state.getActiveNames().length, 0, 'Self typing must never be added');

  state.handleIncomingTypingIndicator({ sender_id: 201, sender_name: 'Rahul', is_typing: true });
  assert.deepStrictEqual(state.getActiveNames(), ['Rahul']);

  state.handleIncomingTypingIndicator({ sender_id: 202, sender_name: 'Priya', is_typing: true });
  assert.deepStrictEqual(state.getActiveNames(), ['Rahul', 'Priya']);
  console.log('✔ Test 3: Receiver state management & self exclusion passed');

  // Test 4: Removal on Message Arrival
  state.onMessageReceived(201);
  assert.deepStrictEqual(state.getActiveNames(), ['Priya']);
  console.log('✔ Test 4: Immediate removal on message arrival passed');

  // Test 5: Removal on User Going Offline
  state.onUserOffline(202);
  assert.deepStrictEqual(state.getActiveNames(), []);
  console.log('✔ Test 5: Immediate removal on offline status passed');

  // Test 6: Auto-expiry Timer (~4s)
  state.handleIncomingTypingIndicator({ sender_id: 301, sender_name: 'Aman', is_typing: true });
  assert.strictEqual(state.getActiveNames().length, 1);
  await new Promise(r => setTimeout(r, 4100));
  assert.strictEqual(state.getActiveNames().length, 0, 'User should expire automatically after 4 seconds');
  console.log('✔ Test 6: Auto-expiry timer (~4.0s) passed');

  // Test 7: Throttle & Whitespace Filtering
  const sentSignals = [];
  const throttle = new TypingThrottleController(val => sentSignals.push(val));

  // Empty input should NOT send typing
  throttle.onInput('');
  throttle.onInput('   \n\t  ');
  assert.strictEqual(sentSignals.length, 0, 'Whitespace input must never trigger typing');

  // First keystroke -> immediate true
  throttle.onInput('H');
  assert.deepStrictEqual(sentSignals, [true]);

  // Rapid typing within 2.5s window -> throttled (no duplicate immediate true)
  throttle.onInput('He');
  throttle.onInput('Hel');
  throttle.onInput('Hell');
  throttle.onInput('Hello');
  assert.strictEqual(sentSignals.length, 1, 'Should not spam typing frames within 2.5s');

  // Clearing input -> immediate stop false
  throttle.onInput('');
  assert.deepStrictEqual(sentSignals, [true, false], 'Clearing input must immediately send stop');
  console.log('✔ Test 7: Throttle behavior (2.5s) & whitespace filtering passed');

  console.log('\nAll JS stub tests PASSED successfully!');
}

runTests().catch(err => {
  console.error('JS stub test FAILED:', err);
  process.exit(1);
});
