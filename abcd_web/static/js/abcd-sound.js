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
        'alarm': '/static/audio/alarm.mp3',
        'reminder': '/static/audio/PWA.mp3',
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
            // Prime essential audio elements so subsequent playback is permitted by browser policy
            ['button', 'alarm', 'reminder'].forEach(function (key) {
                const primer = audioPool[key] || new Audio(SOUND_PATHS[key]);
                audioPool[key] = primer;
                primer.volume = 0.001;
                const promise = primer.play();
                if (promise !== undefined) {
                    promise.then(function () {
                        primer.pause();
                        primer.currentTime = 0;
                        primer.volume = 1.0;
                    }).catch(function () {});
                }
            });
            isAudioUnlocked = true;
            ['click', 'touchstart', 'keydown'].forEach(function (evt) {
                document.removeEventListener(evt, unlockAudio, { capture: true });
            });
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
     * Start alarm sound or reminder sound (plays 9s once) & interactive full-screen UI
     * @param {string} title
     * @param {string} body
     * @param {number|string|null} taskId
     * @param {boolean} [isAlarm=true]
     */
    function startABCDAlarm(title, body, taskId, isAlarm) {
        // If an alarm or reminder is ALREADY playing and modal is visible, do not re-trigger or restart sound!
        if (activeAlarmAudio && !activeAlarmAudio.paused && activeAlarmModal) {
            console.debug('Alarm/reminder is already actively playing; skipping duplicate trigger.');
            return;
        }

        stopABCDAlarm();

        const isAlarmMode = (isAlarm !== false && isAlarm !== 'false' && isAlarm !== 0);
        currentAlarmTaskId = taskId || null;
        ensureAlarmStyles();

        // 1. Play appropriate sound: Alarm plays alarm.mp3 (loud 9s), Simple Reminder plays PWA.mp3 (gentle chime)
        // If Alarm is enabled, ONLY the alarm sound plays (never overlap both)
        const soundKey = isAlarmMode ? 'alarm' : 'reminder';
        const soundSrc = SOUND_PATHS[soundKey] || (isAlarmMode ? '/static/audio/alarm.mp3' : '/static/audio/PWA.mp3');

        function tryPlayAlarmAudio() {
            if (!isSoundEnabled()) return;
            try {
                if (!activeAlarmAudio) {
                    if (audioPool[soundKey]) {
                        activeAlarmAudio = audioPool[soundKey];
                    } else {
                        activeAlarmAudio = new Audio(soundSrc);
                        audioPool[soundKey] = activeAlarmAudio;
                    }
                    activeAlarmAudio.loop = false; // NEVER loop indefinitely!
                    activeAlarmAudio.volume = 1.0;
                    activeAlarmAudio.onended = function () {
                        activeAlarmAudio = null;
                    };
                }
                activeAlarmAudio.currentTime = 0;
                const p = activeAlarmAudio.play();
                if (p !== undefined) {
                    p.then(function () {
                        const banner = document.getElementById('abcdUnmuteBanner');
                        if (banner) banner.style.display = 'none';
                    }).catch(function (err) {
                        console.debug('Audio autoplay blocked by browser policy:', err.message);
                        const banner = document.getElementById('abcdUnmuteBanner');
                        if (banner) banner.style.display = 'flex';
                    });
                }
            } catch (e) {
                console.error('Failed to init alarm/reminder audio:', e);
            }
        }
        tryPlayAlarmAudio();

        // 2. Auto-dismiss safety timeout:
        // - Alarm: 30 seconds if unattended (audio finishes at 9s)
        // - Simple Reminder: 15 seconds if unattended (silences after 9s audio completes)
        const autoDismissMs = isAlarmMode ? 30000 : 15000;
        alarmAutoStopTimer = setTimeout(function () {
            stopABCDAlarm();
        }, autoDismissMs);

        // 3. Build full-screen interactive UI (ALWAYS displayed, regardless of audio state)
        const overlay = document.createElement('div');
        overlay.className = 'abcd-alarm-overlay';
        overlay.id = 'abcdActiveAlarmModal';

        const defaultTitle = isAlarmMode ? '⏰ Reminder Alarm' : '⏰ Reminder';
        const safeTitle = (title || defaultTitle).replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const safeBody = (body || (isAlarmMode ? 'Your scheduled alarm is ringing now!' : 'Your scheduled reminder is due now!')).replace(/</g, '&lt;').replace(/>/g, '&gt;');

        const stopBtnLabel = isAlarmMode ? 'STOP ALARM 🛑' : 'STOP REMINDER 🛑';
        const snoozeBtnHtml = isAlarmMode ? `
                <button type="button" class="abcd-alarm-btn-snooze" id="abcdSnoozeAlarmBtn">
                    Snooze 15 Min ⏳
                </button>
        ` : '';

        const iconHtml = isAlarmMode
            ? '<div class="abcd-alarm-bell-icon">🔔</div>'
            : '<div class="abcd-alarm-bell-icon" style="background: linear-gradient(135deg, #6366f1, #8b5cf6); box-shadow: 0 8px 24px rgba(99, 102, 241, 0.5);">⏰</div>';

        const unmuteLabel = isAlarmMode ? '🔊 Tap anywhere to play alarm sound 🔔' : '🔊 Tap anywhere to play reminder sound 🔔';

        overlay.innerHTML = `
            <div class="abcd-alarm-card">
                ${iconHtml}
                <div class="abcd-alarm-clock" id="abcdAlarmClockDisplay">${formatCurrentTime()}</div>
                <div class="abcd-alarm-title">${safeTitle}</div>
                <div class="abcd-alarm-note">${safeBody}</div>
                <div id="abcdUnmuteBanner" style="display:none; margin:10px 0; padding:12px 14px; background:rgba(239,68,68,0.15); border:2px dashed #ef4444; border-radius:12px; color:#f87171; font-size:0.92rem; font-weight:800; cursor:pointer; align-items:center; justify-content:center; gap:8px; text-align:center;">
                    ${unmuteLabel}
                </div>
                <button type="button" class="abcd-alarm-btn-stop" id="abcdStopAlarmBtn">
                    ${stopBtnLabel}
                </button>
                ${snoozeBtnHtml}
            </div>
        `;

        // Allow tapping unmute banner or card to unlock audio if autoplay blocked it
        overlay.addEventListener('click', function (e) {
            if (e.target.closest('#abcdStopAlarmBtn') || e.target.closest('#abcdSnoozeAlarmBtn')) return;
            tryPlayAlarmAudio();
        });

        document.body.appendChild(overlay);
        activeAlarmModal = overlay;

        // Clock updater
        alarmClockInterval = setInterval(function () {
            const clockEl = document.getElementById('abcdAlarmClockDisplay');
            if (clockEl) clockEl.textContent = formatCurrentTime();
        }, 1000);

        // Wire Stop button: stop audio immediately, dismiss modal, notify backend to stop permanently
        const stopBtn = document.getElementById('abcdStopAlarmBtn');
        if (stopBtn) {
            stopBtn.addEventListener('click', function () {
                const targetId = currentAlarmTaskId;
                stopABCDAlarm(); // Immediately pauses audio & resets currentTime = 0
                if (targetId) {
                    globalFiredAlarmIds.add(targetId);
                    try {
                        sessionStorage.setItem('firedAlarmIds', JSON.stringify(Array.from(globalFiredAlarmIds)));
                    } catch (e) {}

                    fetch(`/todo/reminder/${targetId}/action/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken()
                        },
                        body: JSON.stringify({ action: 'stop' })
                    }).catch(function (err) {
                        console.error('Failed to notify server of stop action:', err);
                    });
                }
            });
        }

        // Wire Snooze button (only present in Alarm mode)
        const snoozeBtn = document.getElementById('abcdSnoozeAlarmBtn');
        if (snoozeBtn) {
            snoozeBtn.addEventListener('click', function () {
                const targetId = currentAlarmTaskId;
                stopABCDAlarm();
                if (targetId) {
                    globalFiredAlarmIds.delete(targetId);
                    try {
                        sessionStorage.setItem('firedAlarmIds', JSON.stringify(Array.from(globalFiredAlarmIds)));
                    } catch (e) {}

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

    // ═════════════════════════════════════════════════════════════════════
    // GLOBAL IN-APP DUE ALARM CHECKER (Runs Across All Pages of ABCD)
    // ═════════════════════════════════════════════════════════════════════
    const globalFiredAlarmIds = new Set();
    try {
        const stored = sessionStorage.getItem('firedAlarmIds');
        if (stored) {
            JSON.parse(stored).forEach(function (id) { globalFiredAlarmIds.add(id); });
        }
    } catch (e) {}

    window.__abcdCachedReminders = [];
    let isCheckingGlobalAlarms = false;

    // High-precision 1-second in-memory checker: fires on the exact second with 0 latency
    function tickGlobalDueAlarmsInMemory() {
        const tasks = window.__abcdCachedReminders;
        if (!tasks || !Array.isArray(tasks) || tasks.length === 0) return;

        const nowMs = Date.now();
        tasks.forEach(function (task) {
            if (task.is_done || task.is_trash) return;

            const meta = task.metadata || task.reminder_meta || {};
            if (meta.alarm_status === 'stopped') return;
            if (globalFiredAlarmIds.has(task.id)) return;

            let isDueNow = false;
            const rec = meta.recurrence || 'once';

            if (rec === 'once') {
                const fireTarget = meta.fire_at || task.delete_at;
                if (fireTarget) {
                    const fireDt = new Date(fireTarget);
                    const fireMs = fireDt.getTime();
                    const elapsedSec = (nowMs - fireMs) / 1000;

                    // If due now or within the last 15 minutes (and not fired yet)
                    if (elapsedSec >= 0 && elapsedSec <= 900) {
                        isDueNow = true;
                    }
                }
            } else if (meta.time_str) {
                const parts = String(meta.time_str).split(':').map(Number);
                const now = new Date();
                const todayFireDt = new Date(now.getFullYear(), now.getMonth(), now.getDate(), parts[0] || 0, parts[1] || 0, 0);
                const elapsedSec = (nowMs - todayFireDt.getTime()) / 1000;

                if (elapsedSec >= 0 && elapsedSec <= 900) {
                    isDueNow = true;
                }
            }

            if (isDueNow) {
                globalFiredAlarmIds.add(task.id);
                try {
                    sessionStorage.setItem('firedAlarmIds', JSON.stringify(Array.from(globalFiredAlarmIds)));
                } catch (e) {}

                const title = task.title || meta.title || 'Reminder';
                const note = meta.note || '';
                const isAlarm = (meta.alarm_enabled !== false && meta.alarm_enabled !== 'false' && meta.alarm_enabled !== 0);

                startABCDAlarm(title, note, task.id, isAlarm);
            }
        });
    }

    function checkGlobalDueAlarms() {
        if (isCheckingGlobalAlarms) return;
        isCheckingGlobalAlarms = true;

        fetch('/todo/get-tasks/?category=REMINDER')
            .then(function (r) {
                if (!r || !r.ok || r.redirected) {
                    return null;
                }
                return r.json();
            })
            .then(function (data) {
                isCheckingGlobalAlarms = false;
                if (!data || !data.tasks || !Array.isArray(data.tasks)) return;

                window.__abcdCachedReminders = data.tasks;
                tickGlobalDueAlarmsInMemory();
            })
            .catch(function () {
                isCheckingGlobalAlarms = false;
            });
    }

    // High precision: Check memory every 1 second, fetch server every 10 seconds
    setInterval(tickGlobalDueAlarmsInMemory, 1000);
    setInterval(checkGlobalDueAlarms, 10000);
    setTimeout(checkGlobalDueAlarms, 1000);

    // Also run immediately on page visibility change or tab focus (e.g. mobile phone unlocked / tab resumed)
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible') {
            checkGlobalDueAlarms();
            tickGlobalDueAlarmsInMemory();
        }
    });
    window.addEventListener('focus', function () {
        checkGlobalDueAlarms();
        tickGlobalDueAlarmsInMemory();
    });

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
                const isAlarmParam = urlParams.get('is_alarm');
                const isAlarm = (isAlarmParam === null || isAlarmParam === '1' || isAlarmParam === 'true');
                // Clean the URL param so refresh doesn't re-ring
                urlParams.delete('ring_alarm');
                urlParams.delete('alarm_title');
                urlParams.delete('task_id');
                urlParams.delete('is_alarm');
                const cleanSearch = urlParams.toString();
                const cleanUrl = window.location.pathname + (cleanSearch ? '?' + cleanSearch : '') + window.location.hash;
                window.history.replaceState({}, document.title, cleanUrl);

                setTimeout(function () {
                    startABCDAlarm(alarmTitle, 'Your scheduled reminder is ringing now!', alarmTaskId, isAlarm);
                }, 200);
            }
        } catch (e) {}
    }

    // Service Worker message listener for instant audio playback in open/minimized tabs
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.addEventListener('message', function (event) {
            if (event.data && event.data.type === 'ABCD_ALARM_PUSH') {
                startABCDAlarm(event.data.title, event.data.body, event.data.taskId, event.data.isAlarm !== false);
            }
        });
    }

    // Listen for custom global events
    window.addEventListener('abcd:sound', function (e) {
        if (e && e.detail && e.detail.sound) {
            if (e.detail.sound === 'alarm' && e.detail.isRinging) {
                startABCDAlarm(e.detail.title, e.detail.body, e.detail.taskId, e.detail.isAlarm !== false);
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
    window.unlockABCDAudio = unlockAudio;

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
