/**
 * static/js/abcd-sound.js - ABCD Audio Engine
 * Provides unique high-fidelity sound effects for PWA, ToDo alarms,
 * button clicks, form completions, errors, and Guidy messages.
 */

(function () {
    'use strict';

    // Idempotent initialization guard
    if (window.__ABCD_SOUND_INITIALIZED) return;
    window.__ABCD_SOUND_INITIALIZED = true;

    const SOUND_STORAGE_KEY = 'abcd_sound_enabled';

    // Audio file definitions
    const SOUND_PATHS = {
        'button': '/static/audio/button.mp3',
        'send': '/static/audio/send.mp3',
        'receive': '/static/audio/receive.mp3',
        'done': '/static/audio/done.mp3',
        'success': '/static/audio/done.mp3',
        'error': '/static/audio/error.mp3',
        'alarm': '/static/audio/alarms and reminders.mp3',
        'reminder': '/static/audio/alarms and reminders.mp3',
        'pwa': '/static/audio/PWA.mp3'
    };

    // Cached Audio objects pool
    const audioPool = {};
    let isAudioUnlocked = false;
    let lastButtonSoundTime = 0;

    // Check user preference (enabled by default)
    function isSoundEnabled() {
        return localStorage.getItem(SOUND_STORAGE_KEY) !== 'false';
    }

    function setSoundEnabled(enabled) {
        localStorage.setItem(SOUND_STORAGE_KEY, enabled ? 'true' : 'false');
    }

    // Pre-cache sounds
    function initAudioPool() {
        Object.keys(SOUND_PATHS).forEach(function (key) {
            try {
                const audio = new Audio(SOUND_PATHS[key]);
                audio.preload = 'auto';
                audioPool[key] = audio;
            } catch (e) {
                // Ignore audio init errors
            }
        });
    }

    // Unlock audio context on first user interaction (browser autoplay policy)
    function unlockAudio() {
        if (isAudioUnlocked) return;

        try {
            const primer = audioPool['button'] || new Audio(SOUND_PATHS['button']);
            primer.volume = 0.01;
            const promise = primer.play();
            if (promise !== undefined) {
                promise.then(function () {
                    primer.pause();
                    primer.currentTime = 0;
                    primer.volume = 1.0;
                    isAudioUnlocked = true;
                    ['click', 'touchstart', 'keydown'].forEach(function (evt) {
                        document.removeEventListener(evt, unlockAudio, { capture: true });
                    });
                }).catch(function () {
                    // Keep listeners attached to retry on next user interaction
                });
            } else {
                isAudioUnlocked = true;
                ['click', 'touchstart', 'keydown'].forEach(function (evt) {
                    document.removeEventListener(evt, unlockAudio, { capture: true });
                });
            }
        } catch (e) {
            // Keep listeners attached to retry on next user interaction
        }
    }

    // Register interaction listeners to unlock
    ['click', 'touchstart', 'keydown'].forEach(function (evt) {
        document.addEventListener(evt, unlockAudio, { capture: true });
    });

    /**
     * Play an ABCD sound effect by name
     * @param {string} soundName - 'button' | 'send' | 'receive' | 'done' | 'error' | 'alarm' | 'pwa'
     * @param {number} [volume=1.0] - Volume between 0.0 and 1.0
     */
    function playABCDSound(soundName, volume) {
        if (!isSoundEnabled()) return;

        const vol = (volume === undefined) ? 1.0 : volume;
        const normalizedName = (soundName || '').toLowerCase().trim();
        const soundSrc = SOUND_PATHS[normalizedName];
        if (!soundSrc) return;

        try {
            const poolAudio = audioPool[normalizedName];
            if (poolAudio) {
                // If audio element is idle, reuse directly for instant playback
                if (poolAudio.paused || poolAudio.ended) {
                    poolAudio.currentTime = 0;
                    poolAudio.volume = Math.max(0, Math.min(1, vol));
                    const p = poolAudio.play();
                    if (p !== undefined) {
                        p.catch(function () {
                            const fresh = new Audio(soundSrc);
                            fresh.volume = Math.max(0, Math.min(1, vol));
                            fresh.play().catch(function () {});
                        });
                    }
                    return;
                } else {
                    // Overlapping sound: play via fresh Audio instance
                    const fresh = new Audio(soundSrc);
                    fresh.volume = Math.max(0, Math.min(1, vol));
                    const p = fresh.play();
                    if (p !== undefined) {
                        p.catch(function () {});
                    }
                    return;
                }
            }

            // Fresh instance fallback if pool entry is not ready
            const snd = new Audio(soundSrc);
            snd.volume = Math.max(0, Math.min(1, vol));
            const playPromise = snd.play();
            if (playPromise !== undefined) {
                playPromise.catch(function (err) {
                    console.debug('ABCD Audio playback note:', normalizedName, err.message);
                });
            }
        } catch (e) {
            // Audio not supported or failed
        }
    }

    // Comprehensive selector for interactive elements across all ABCD pages:
    // Buttons, action links, submit buttons, tabs, modal close X buttons, library seats, and controls
    const CLICKABLE_SELECTOR = [
        'button',
        '.btn',
        '.btn-action',
        '.action-btn',
        '[role="button"]',
        'input[type="submit"]',
        'input[type="button"]',
        'input[type="reset"]',
        '.nav-tab',
        '.tab-btn',
        '.dropdown-item',
        '.custom-popup-btn',
        '.modal-close-btn',
        '.modal-close',
        '.close',
        '.close-btn',
        '.seat-modal-close-btn',
        '.todo-modal-close',
        '.custom-popup-close',
        '.tc-modal-close',
        '[aria-label="Close"]',
        '[aria-label="close"]',
        '[data-close]',
        '.seat:not(.empty-space)',
        '[data-seat-id]:not(.empty-space)',
        '.wheel-item',
        '.abcd-select-option',
        '.icon-btn',
        '.hub-search-btn',
        '.bnav-item'
    ].join(', ');

    // Global click sound listener for interactive elements (Capture phase guarantees execution)
    document.addEventListener('click', function (e) {
        if (!isSoundEnabled()) return;

        const target = e.target;
        if (!target) return;

        // Skip elements explicitly marked with .no-sound
        if (target.closest('.no-sound, [data-no-sound="true"]')) return;

        // Trigger sound on any interactive button, seat, close X, or control
        const isClickable = target.closest(CLICKABLE_SELECTOR);
        if (isClickable) {
            const now = Date.now();
            // Debounce clicks slightly (60ms) to allow natural rapid clicks while preventing harsh machine-gun audio
            if (now - lastButtonSoundTime > 60) {
                lastButtonSoundTime = now;
                playABCDSound('button', 0.45);
            }
        }
    }, true);

    // -------------------------------------------------------------
    // Continuous Alarm Engine & Full-Screen Ringing Modal
    // -------------------------------------------------------------
    let activeAlarmAudio = null;
    let activeAlarmModal = null;
    let alarmAutoStopTimer = null;
    let alarmClockInterval = null;

    function ensureAlarmStyles() {
        if (document.getElementById('abcd-alarm-modal-styles')) return;
        const style = document.createElement('style');
        style.id = 'abcd-alarm-modal-styles';
        style.textContent = `
            @keyframes abcdAlarmBellRing {
                0% { transform: rotate(0deg) scale(1); }
                15% { transform: rotate(18deg) scale(1.15); }
                30% { transform: rotate(-18deg) scale(1.15); }
                45% { transform: rotate(14deg) scale(1.1); }
                60% { transform: rotate(-14deg) scale(1.1); }
                75% { transform: rotate(8deg) scale(1.05); }
                100% { transform: rotate(0deg) scale(1); }
            }
            @keyframes abcdAlarmGlow {
                0%, 100% { box-shadow: 0 0 25px rgba(239, 68, 68, 0.4), 0 0 50px rgba(245, 158, 11, 0.2); }
                50% { box-shadow: 0 0 45px rgba(239, 68, 68, 0.75), 0 0 85px rgba(245, 158, 11, 0.45); }
            }
            @keyframes abcdAlarmOverlayFade {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            @keyframes abcdAlarmCardPop {
                from { opacity: 0; transform: scale(0.85) translateY(20px); }
                to { opacity: 1; transform: scale(1) translateY(0); }
            }
            .abcd-alarm-overlay {
                position: fixed;
                inset: 0;
                z-index: 2147483647;
                background: rgba(10, 15, 30, 0.88);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
                animation: abcdAlarmOverlayFade 0.3s ease-out;
            }
            .abcd-alarm-card {
                background: linear-gradient(145deg, #1e1b4b, #0f172a);
                border: 2px solid rgba(245, 158, 11, 0.5);
                border-radius: 28px;
                padding: 32px 28px;
                width: 100%;
                max-width: 440px;
                text-align: center;
                color: #ffffff;
                animation: abcdAlarmCardPop 0.35s cubic-bezier(0.16, 1, 0.3, 1), abcdAlarmGlow 2s infinite ease-in-out;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            .abcd-alarm-bell-icon {
                width: 84px;
                height: 84px;
                background: linear-gradient(135deg, #ef4444, #f59e0b);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 2.8rem;
                margin: 0 auto 18px;
                animation: abcdAlarmBellRing 1.2s infinite ease-in-out;
                box-shadow: 0 8px 24px rgba(239, 68, 68, 0.5);
            }
            .abcd-alarm-clock {
                font-size: 2.2rem;
                font-weight: 900;
                letter-spacing: 2px;
                color: #fde047;
                margin-bottom: 8px;
                font-variant-numeric: tabular-nums;
            }
            .abcd-alarm-title {
                font-size: 1.35rem;
                font-weight: 800;
                color: #ffffff;
                margin-bottom: 8px;
                line-height: 1.3;
                word-break: break-word;
            }
            .abcd-alarm-note {
                font-size: 0.95rem;
                color: #94a3b8;
                margin-bottom: 26px;
                line-height: 1.5;
                max-height: 80px;
                overflow-y: auto;
            }
            .abcd-alarm-btn-stop {
                background: linear-gradient(135deg, #ef4444, #dc2626);
                color: #ffffff;
                border: none;
                border-radius: 16px;
                padding: 16px 28px;
                font-size: 1.15rem;
                font-weight: 800;
                width: 100%;
                cursor: pointer;
                box-shadow: 0 6px 20px rgba(239, 68, 68, 0.5);
                transition: transform 0.15s, opacity 0.15s;
                letter-spacing: 0.5px;
            }
            .abcd-alarm-btn-stop:hover {
                transform: scale(1.02);
                opacity: 0.95;
            }
            .abcd-alarm-btn-stop:active {
                transform: scale(0.98);
            }
            .abcd-alarm-btn-snooze {
                margin-top: 12px;
                background: rgba(255, 255, 255, 0.1);
                color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 14px;
                padding: 12px 20px;
                font-size: 0.95rem;
                font-weight: 600;
                width: 100%;
                cursor: pointer;
                transition: background 0.2s, color 0.2s;
            }
            .abcd-alarm-btn-snooze:hover {
                background: rgba(255, 255, 255, 0.18);
                color: #ffffff;
            }
        `;
        document.head.appendChild(style);
    }

    function formatCurrentTime() {
        const now = new Date();
        return now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true });
    }

    /**
     * Start continuous alarm sound & full-screen ringing UI
     * @param {string} title
    let currentAlarmTaskId = null;

    function getCsrfToken() {
        if (window.CSRF_TOKEN) return window.CSRF_TOKEN;
        const el = document.querySelector('[name=csrfmiddlewaretoken]');
        if (el && el.value) return el.value;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.startsWith('csrftoken=')) {
                    return decodeURIComponent(cookie.substring(10));
                }
            }
        }
        return '';
    }

    /**
     * Start alarm sound (plays 9s once) & interactive full-screen ringing UI
     * @param {string} title
     * @param {string} body
     * @param {number|string|null} taskId
     */
    function startABCDAlarm(title, body, taskId) {
        // If an alarm is ALREADY playing and modal is visible, do not re-trigger or restart sound!
        if (activeAlarmAudio && !activeAlarmAudio.paused && activeAlarmModal) {
            console.debug('Alarm is already actively playing; skipping duplicate trigger.');
            return;
        }

        stopABCDAlarm();
        if (!isSoundEnabled()) return;

        currentAlarmTaskId = taskId || null;
        ensureAlarmStyles();

        // 1. Play 9-second alarm audio ONCE at 100% volume (loop = false)
        try {
            const alarmSrc = SOUND_PATHS['alarm'] || '/static/audio/alarms and reminders.mp3';
            activeAlarmAudio = new Audio(alarmSrc);
            activeAlarmAudio.loop = false; // NEVER loop indefinitely! Plays 9 seconds once.
            activeAlarmAudio.volume = 1.0;
            activeAlarmAudio.onended = function () {
                activeAlarmAudio = null;
            };
            const p = activeAlarmAudio.play();
            if (p !== undefined) {
                p.catch(function (err) {
                    console.debug('Alarm audio autoplay waiting for user touch:', err.message);
                });
            }
        } catch (e) {
            console.error('Failed to init alarm audio:', e);
        }

        // 2. Auto-dismiss safety timeout: 30 seconds if unattended (audio finishes at 9s)
        alarmAutoStopTimer = setTimeout(function () {
            stopABCDAlarm();
        }, 30000);

        // 3. Build full-screen interactive Alarm UI
        const overlay = document.createElement('div');
        overlay.className = 'abcd-alarm-overlay';
        overlay.id = 'abcdActiveAlarmModal';

        const safeTitle = (title || '⏰ Reminder Alarm').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const safeBody = (body || 'Your scheduled reminder is ringing now!').replace(/</g, '&lt;').replace(/>/g, '&gt;');

        overlay.innerHTML = `
            <div class="abcd-alarm-card">
                <div class="abcd-alarm-bell-icon">🔔</div>
                <div class="abcd-alarm-clock" id="abcdAlarmClockDisplay">${formatCurrentTime()}</div>
                <div class="abcd-alarm-title">${safeTitle}</div>
                <div class="abcd-alarm-note">${safeBody}</div>
                <button type="button" class="abcd-alarm-btn-stop" id="abcdStopAlarmBtn">
                    STOP ALARM 🛑
                </button>
                <button type="button" class="abcd-alarm-btn-snooze" id="abcdSnoozeAlarmBtn">
                    Snooze 15 Min ⏳
                </button>
            </div>
        `;

        document.body.appendChild(overlay);
        activeAlarmModal = overlay;

        // Clock updater
        alarmClockInterval = setInterval(function () {
            const clockEl = document.getElementById('abcdAlarmClockDisplay');
            if (clockEl) clockEl.textContent = formatCurrentTime();
        }, 1000);

        // Wire Stop button: stop audio, dismiss modal, notify backend to stop permanently
        const stopBtn = document.getElementById('abcdStopAlarmBtn');
        if (stopBtn) {
            stopBtn.addEventListener('click', function () {
                const targetId = currentAlarmTaskId;
                stopABCDAlarm();
                if (targetId) {
                    fetch(`/todo/reminder/${targetId}/action/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken()
                        },
                        body: JSON.stringify({ action: 'stop' })
                    }).catch(function (err) {
                        console.error('Failed to notify server of alarm stop:', err);
                    });
                }
            });
        }

        // Wire Snooze button: stop audio, dismiss modal, notify backend to snooze 15 min
        const snoozeBtn = document.getElementById('abcdSnoozeAlarmBtn');
        if (snoozeBtn) {
            snoozeBtn.addEventListener('click', function () {
                const targetId = currentAlarmTaskId;
                stopABCDAlarm();
                if (targetId) {
                    fetch(`/todo/reminder/${targetId}/action/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken()
                        },
                        body: JSON.stringify({ action: 'snooze', minutes: 15 })
                    }).catch(function (err) {
                        console.error('Failed to notify server of alarm snooze:', err);
                    });
                }
                if (window.CustomPopup) {
                    CustomPopup.alert('Alarm snoozed for 15 minutes. It will ring again in 15 minutes.', '⏳ Snooze Active');
                }
            });
        }
    }

    /**
     * Stop continuous alarm audio & dismiss modal
     */
    function stopABCDAlarm() {
        if (alarmAutoStopTimer) {
            clearTimeout(alarmAutoStopTimer);
            alarmAutoStopTimer = null;
        }
        if (alarmClockInterval) {
            clearInterval(alarmClockInterval);
            alarmClockInterval = null;
        }
        if (activeAlarmAudio) {
            try {
                activeAlarmAudio.pause();
                activeAlarmAudio.currentTime = 0;
            } catch (e) {}
            activeAlarmAudio = null;
        }
        if (activeAlarmModal) {
            try {
                if (activeAlarmModal.parentNode) {
                    activeAlarmModal.parentNode.removeChild(activeAlarmModal);
                }
            } catch (e) {}
            activeAlarmModal = null;
        }
    }

    // Keyboard shortcut (Escape stops active alarm)
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && activeAlarmModal) {
            stopABCDAlarm();
        }
    });

    // Check URL parameters for instant tap-to-ring when opened via push notification
    function checkUrlAlarmTrigger() {
        try {
            const urlParams = new URLSearchParams(window.location.search);
            if (urlParams.get('ring_alarm') === '1') {
                const alarmTitle = urlParams.get('alarm_title') || '⏰ Scheduled Reminder';
                const alarmTaskId = urlParams.get('task_id');
                // Clean the URL param so refresh doesn't re-ring
                urlParams.delete('ring_alarm');
                urlParams.delete('alarm_title');
                urlParams.delete('task_id');
                const cleanSearch = urlParams.toString();
                const cleanUrl = window.location.pathname + (cleanSearch ? '?' + cleanSearch : '') + window.location.hash;
                window.history.replaceState({}, document.title, cleanUrl);

                setTimeout(function () {
                    startABCDAlarm(alarmTitle, 'Your scheduled reminder is ringing now!', alarmTaskId);
                }, 200);
            }
        } catch (e) {}
    }

    // Service Worker message listener for instant audio playback in open/minimized tabs
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.addEventListener('message', function (event) {
            if (event.data && event.data.type === 'ABCD_ALARM_PUSH') {
                if (event.data.isAlarm) {
                    startABCDAlarm(event.data.title, event.data.body, event.data.taskId);
                } else {
                    playABCDSound('pwa');
                }
            }
        });
    }

    // Listen for custom global events
    window.addEventListener('abcd:sound', function (e) {
        if (e && e.detail && e.detail.sound) {
            if (e.detail.sound === 'alarm' && e.detail.isRinging) {
                startABCDAlarm(e.detail.title, e.detail.body, e.detail.taskId);
            } else {
                playABCDSound(e.detail.sound, e.detail.volume || 1.0);
            }
        }
    });

    // Expose global methods on window
    window.playABCDSound = playABCDSound;
    window.playDoneSound = function () { playABCDSound('done'); };
    window.playErrorSound = function () { playABCDSound('error'); };
    window.playButtonSound = function () { playABCDSound('button', 0.45); };
    window.startABCDAlarm = startABCDAlarm;
    window.stopABCDAlarm = stopABCDAlarm;
    window.setABCDSoundEnabled = setSoundEnabled;
    window.isABCDSoundEnabled = isSoundEnabled;

    // Initialize preloading and URL trigger on DOM load or immediate
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            initAudioPool();
            checkUrlAlarmTrigger();
        });
    } else {
        initAudioPool();
        checkUrlAlarmTrigger();
    }
})();
