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
        'pwa': '/static/audio/PWA.mp3',
        'alarms and reminders': '/static/audio/alarms and reminders.mp3',
        'alarms%20and%20reminders': '/static/audio/alarms and reminders.mp3',
        '/static/audio/alarms and reminders.mp3': '/static/audio/alarms and reminders.mp3',
        '/static/audio/alarms%20and%20reminders.mp3': '/static/audio/alarms and reminders.mp3',
        '/static/audio/alarm.mp3': '/static/audio/alarm.mp3',
        '/static/audio/pwa.mp3': '/static/audio/PWA.mp3',
        '/static/audio/PWA.mp3': '/static/audio/PWA.mp3',
        'course_reminder': '/static/audio/alarms and reminders.mp3'
    };

    // Cached Audio objects pool & Web Audio buffer cache
    const audioPool = {};
    const soundBuffers = {};
    const bufferLoadingPromises = {};
    let sharedAudioCtx = null;
    let isAudioUnlocked = false;
    let lastButtonSoundTime = 0;

    function getAudioContext() {
        if (!sharedAudioCtx) {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (AudioCtx) {
                try {
                    sharedAudioCtx = new AudioCtx();
                } catch (e) {}
            }
        }
        return sharedAudioCtx;
    }

    async function loadSoundBuffer(name, url) {
        if (soundBuffers[name]) return soundBuffers[name];
        if (bufferLoadingPromises[name]) return bufferLoadingPromises[name];

        bufferLoadingPromises[name] = (async function () {
            try {
                const ctx = getAudioContext();
                if (!ctx) return null;
                const res = await fetch(url);
                if (!res.ok) return null;
                const ab = await res.arrayBuffer();
                const decoded = await ctx.decodeAudioData(ab);
                soundBuffers[name] = decoded;
                return decoded;
            } catch (e) {
                return null;
            }
        })();

        return bufferLoadingPromises[name];
    }

    function playViaWebAudio(buffer, volume) {
        try {
            const ctx = getAudioContext();
            if (!ctx) return false;
            if (ctx.state === 'suspended') {
                ctx.resume().catch(function () {});
            }
            const source = ctx.createBufferSource();
            source.buffer = buffer;
            const gain = ctx.createGain();
            gain.gain.value = Math.max(0, Math.min(1, volume));
            source.connect(gain);
            gain.connect(ctx.destination);
            source.start(0);
            return true;
        } catch (e) {
            return false;
        }
    }

    // Check if an alarm or loud reminder is actively ringing
    function isAlarmOrLoudAlertPlaying() {
        if (activeAlarmAudio && !activeAlarmAudio.paused && !activeAlarmAudio.ended) return true;
        const poolAlarm = audioPool['alarm'];
        if (poolAlarm && !poolAlarm.paused && !poolAlarm.ended) return true;
        const poolAr = audioPool['alarms and reminders'] || audioPool['alarms%20and%20reminders'];
        if (poolAr && !poolAr.paused && !poolAr.ended) return true;
        return false;
    }

    // Check user preference (enabled by default)
    function isSoundEnabled() {
        return localStorage.getItem(SOUND_STORAGE_KEY) !== 'false';
    }

    function setSoundEnabled(enabled) {
        localStorage.setItem(SOUND_STORAGE_KEY, enabled ? 'true' : 'false');
    }

    // Pre-cache small UI interaction sounds (instantiate Audio objects with preload='none' so page load is superfast)
    function initAudioPool() {
        const smallSounds = ['button', 'send', 'receive', 'done', 'error', 'pwa'];
        smallSounds.forEach(function (key) {
            const soundPath = SOUND_PATHS[key];
            if (!soundPath) return;

            // Pre-instantiate HTML5 Audio elements without blocking initial page load
            try {
                if (!audioPool[key]) {
                    const audio = new Audio(soundPath);
                    audio.preload = 'none';
                    audioPool[key] = audio;
                }
            } catch (e) {}
        });
    }

    // Unlock audio context on first user interaction (browser autoplay policy)
    function unlockAudio() {
        try {
            const ctx = getAudioContext();
            if (ctx && ctx.state === 'suspended') {
                ctx.resume().catch(function () {});
            }

            if (!isAudioUnlocked) {
                // Pre-fetch & decode Web Audio buffers now that user has interacted
                const smallSounds = ['button', 'send', 'receive', 'done', 'error', 'pwa'];
                smallSounds.forEach(function (key) {
                    const soundPath = SOUND_PATHS[key];
                    if (soundPath) loadSoundBuffer(key, soundPath);
                });

                // Prime HTML5 Audio with an isolated scratch instance
                const scratch = new Audio(SOUND_PATHS['button']);
                scratch.volume = 0.01;
                const promise = scratch.play();
                if (promise !== undefined) {
                    promise.then(function () {
                        scratch.pause();
                        scratch.currentTime = 0;
                    }).catch(function () {});
                }
                isAudioUnlocked = true;
            }
        } catch (e) {}
    }

    // Register one-time interaction listener to unlock Web Audio on first user gesture
    ['click', 'touchstart', 'keydown'].forEach(function (evt) {
        document.addEventListener(evt, unlockAudio, { once: true, passive: true });
    });

    /**
     * Play an ABCD sound effect by name
     * @param {string} soundName - 'button' | 'send' | 'receive' | 'done' | 'error' | 'alarm' | 'reminder' | 'pwa' | 'alarms and reminders'
     * @param {number} [volume=1.0] - Volume between 0.0 and 1.0
     */
    function playABCDSound(soundName, volume) {
        if (!isSoundEnabled()) return;

        const vol = (volume === undefined) ? 1.0 : volume;
        const normalizedName = (soundName || '').toLowerCase().trim();
        const soundSrc = SOUND_PATHS[normalizedName];
        if (!soundSrc) return;

        // ZERO OVERLAP & AUDIO PRIORITY RULE:
        // If an alarm or reminder alert is actively playing, MUTE/SUPPRESS all gentle notification chimes (PWA, receive, reminder)
        if (isAlarmOrLoudAlertPlaying()) {
            if (['pwa', 'reminder', 'receive'].includes(normalizedName)) {
                console.debug('Muting/suppressing PWA sound because an alarm or reminder alert is actively playing.');
                return;
            }
        }

        // If an alarm or reminder alert is starting, immediately silence and reset any active gentle chimes
        if (['alarm', 'alarms and reminders', 'course_reminder'].includes(normalizedName)) {
            ['pwa', 'reminder', 'receive'].forEach(function (k) {
                const a = audioPool[k];
                if (a) {
                    try {
                        a.pause();
                        a.currentTime = 0;
                    } catch (e) {}
                }
            });
        }

        // 1. Try Web Audio buffer first (instant, 0 latency, immune to async autoplay restriction once unlocked)
        const buffer = soundBuffers[normalizedName];
        if (buffer && playViaWebAudio(buffer, vol)) {
            return;
        }

        // 2. If buffer is not decoded yet, kick off decoding in background for next time
        if (!buffer && !bufferLoadingPromises[normalizedName]) {
            loadSoundBuffer(normalizedName, soundSrc);
        }

        // 3. Fallback to HTMLAudioElement (works immediately on synchronous user gestures)
        try {
            const poolAudio = audioPool[normalizedName];
            if (poolAudio) {
                if (poolAudio.paused || poolAudio.ended) {
                    if (poolAudio.readyState > 0) {
                        try { poolAudio.currentTime = 0; } catch (e) {}
                    }
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
                    const fresh = new Audio(soundSrc);
                    fresh.volume = Math.max(0, Math.min(1, vol));
                    const p = fresh.play();
                    if (p !== undefined) {
                        p.catch(function () {});
                    }
                    return;
                }
            }

            const snd = new Audio(soundSrc);
            snd.volume = Math.max(0, Math.min(1, vol));
            const playPromise = snd.play();
            if (playPromise !== undefined) {
                playPromise.catch(function () {});
            }
        } catch (e) {}
    }

    // Comprehensive selector for interactive elements across all ABCD pages:
    // Buttons, action links, submit buttons, tabs, modal close X buttons, library seats, and controls
    const CLICKABLE_SELECTOR = [
        'button',
        '.btn',
        'a.btn',
        'a[class*="-btn"]',
        'a[class*="btn-"]',
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
        '.bnav-item',
        '.action-card',
        '.clickable',
        '[data-action]',
        '.tab',
        '.pill',
        '.chip',
        '.filter-btn',
        '.filter-chip',
        '.form-submit',
        '.submit-btn',
        '.save-btn',
        '.cancel-btn',
        '.custom-btn',
        '.g-btn',
        '.g-send-btn',
        '.g-chat-item',
        '.g-req-card',
        '.g-req-accept',
        '.g-req-reject',
        '[onclick]',
        '.floating-btn',
        '.quick-action-btn'
    ].join(', ');

    // Global click sound listener for interactive elements
    // Uses pointerdown in capture phase for instant 0ms tactile response on touches/clicks
    function handleInteractionButtonSound(e) {
        if (!isSoundEnabled()) return;

        const target = e.target;
        if (!target) return;

        // Skip elements explicitly marked with .no-sound
        if (target.closest && target.closest('.no-sound, [data-no-sound="true"]')) return;

        // Trigger sound on any interactive button, seat, close X, or control
        const isClickable = target.closest && target.closest(CLICKABLE_SELECTOR);
        if (isClickable) {
            const now = Date.now();
            if (now - lastButtonSoundTime > 80) {
                lastButtonSoundTime = now;
                playABCDSound('button', 0.85);
            }
        }
    }

    // Passive click sound listener on interactive elements
    document.addEventListener('click', handleInteractionButtonSound, { passive: true });

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
     */

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

    // Multi-alarm queue to prevent collisions and ensure zero reminders are lost
    const pendingAlarmQueue = [];

    /**
     * Start alarm sound or reminder sound (plays 9s once) & interactive full-screen UI
     * @param {string} title
     * @param {string} body
     * @param {number|string|null} taskId
     * @param {boolean} [isAlarm=true]
     * @param {string} [customSoundSrc]
     */
    function startABCDAlarm(title, body, taskId, isAlarm, customSoundSrc, skipAudio) {
        // STRICT SAFETY GUARD: Guidy messages are chat notifications and NEVER alarms or reminders!
        const titleStr = String(title || '');
        const bodyStr = String(body || '');
        if (titleStr.includes('Guidy') || titleStr.includes('ABCD Asst') || bodyStr.includes('ABCD Asst')) {
            console.warn('[ABCD Sound] Suppressed invalid alarm modal for Guidy chat message:', title);
            return;
        }

        // Multi-event queue safety: if an alarm/reminder modal is currently active, queue this event!
        if (activeAlarmModal && document.getElementById('abcdActiveAlarmModal')) {
            const isAlreadyQueued = pendingAlarmQueue.some(function (item) {
                return item.taskId && taskId && String(item.taskId) === String(taskId);
            });
            if (!isAlreadyQueued && String(currentAlarmTaskId) !== String(taskId)) {
                pendingAlarmQueue.push({
                    title: title,
                    body: body,
                    taskId: taskId,
                    isAlarm: isAlarm,
                    customSoundSrc: customSoundSrc
                });
                console.debug('[ABCD Sound] Queued concurrent reminder:', title, 'Queue depth:', pendingAlarmQueue.length);
            }
            return;
        }

        stopABCDAlarm();

        // ZERO OVERLAP RULE: Immediately mute/stop any active gentle chimes
        ['pwa', 'reminder', 'receive'].forEach(function (k) {
            const a = audioPool[k];
            if (a) {
                try {
                    a.pause();
                    a.currentTime = 0;
                } catch (e) {}
            }
        });

        const isAlarmMode = (isAlarm !== false && isAlarm !== 'false' && isAlarm !== 0);
        currentAlarmTaskId = taskId || null;
        ensureAlarmStyles();

        // Determine sound:
        // - customSoundSrc if specified (e.g. '/static/audio/alarms and reminders.mp3')
        // - To-Do Alarm: alarm.mp3
        // - To-Do Reminder without alarm: PWA.mp3
        let soundSrc;
        if (customSoundSrc) {
            soundSrc = SOUND_PATHS[customSoundSrc] || customSoundSrc;
        } else if (isAlarmMode) {
            soundSrc = SOUND_PATHS['alarm'] || '/static/audio/alarm.mp3';
        } else {
            soundSrc = SOUND_PATHS['pwa'] || '/static/audio/PWA.mp3';
        }

        function tryPlayAlarmAudio() {
            if (!isSoundEnabled()) return;
            try {
                if (!activeAlarmAudio) {
                    activeAlarmAudio = new Audio(soundSrc);
                    activeAlarmAudio.loop = false;
                    activeAlarmAudio.volume = 1.0;
                    activeAlarmAudio.onended = function () {
                        // Keep reference active so volume/stop can still control if needed
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
        if (!skipAudio) {
            tryPlayAlarmAudio();
        }

        // 2. Auto-dismiss timeout:
        // - Alarms: DO NOT auto-dismiss! The modal must remain on screen with STOP & SNOOZE buttons until acknowledged.
        // - Simple Reminders: 20 seconds auto-dismiss if unattended.
        if (!isAlarmMode) {
            alarmAutoStopTimer = setTimeout(function () {
                stopABCDAlarm();
            }, 20000);
        }

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

        // Allow tapping unmute banner or card on desktop or mobile touch to unlock audio if autoplay blocked it
        overlay.addEventListener('click', function (e) {
            if (e.target.closest('#abcdStopAlarmBtn') || e.target.closest('#abcdSnoozeAlarmBtn')) return;
            tryPlayAlarmAudio();
        });
        overlay.addEventListener('touchstart', function (e) {
            if (e.target.closest('#abcdStopAlarmBtn') || e.target.closest('#abcdSnoozeAlarmBtn')) return;
            tryPlayAlarmAudio();
        }, { passive: true });

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
                stopABCDAlarm({ persistStop: true }); // Explicit user action: persist stop locally & notify server
            });
        }

        // Wire Snooze button (only present in Alarm mode)
        const snoozeBtn = document.getElementById('abcdSnoozeAlarmBtn');
        if (snoozeBtn) {
            snoozeBtn.addEventListener('click', function () {
                const targetId = currentAlarmTaskId;
                stopABCDAlarm({ persistStop: false }); // Clean up modal/audio without permanently marking stopped
                if (targetId) {
                    locallyStoppedAlarmIds.add(targetId);
                    globalFiredAlarmIds.add(targetId);
                    saveStoredAlarmSet('locallyStoppedAlarmIds', locallyStoppedAlarmIds);
                    saveStoredAlarmSet('firedAlarmIds', globalFiredAlarmIds);

                    // Clear local stop after snooze expires (14 mins) so it can ring again
                    setTimeout(function () {
                        locallyStoppedAlarmIds.delete(targetId);
                        globalFiredAlarmIds.delete(targetId);
                        saveStoredAlarmSet('locallyStoppedAlarmIds', locallyStoppedAlarmIds);
                        saveStoredAlarmSet('firedAlarmIds', globalFiredAlarmIds);
                    }, 14 * 60 * 1000);

                    if (!String(targetId).startsWith('course_')) {
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
                    sendNativeTwaMessage('abcdalarm://snooze?id=' + encodeURIComponent(targetId) + '&minutes=15');
                }
                if (window.CustomPopup) {
                    CustomPopup.alert('Alarm snoozed for 15 minutes. It will ring again in 15 minutes.', '⏳ Snooze Active');
                }
            });
        }
    }

    /**
     * Mark an alarm stopped across all browser tabs (localStorage) and persist to server
     */
    function markAlarmStoppedLocallyAndRemotely(targetId) {
        if (!targetId) return;
        locallyStoppedAlarmIds.add(targetId);
        globalFiredAlarmIds.add(targetId);
        saveStoredAlarmSet('locallyStoppedAlarmIds', locallyStoppedAlarmIds);
        saveStoredAlarmSet('firedAlarmIds', globalFiredAlarmIds);

        // Immediately mutate cached reminders so alarm_status is never ringing locally
        if (window.__abcdCachedReminders && Array.isArray(window.__abcdCachedReminders)) {
            window.__abcdCachedReminders.forEach(function (t) {
                if (t && t.id == targetId) {
                    if (t.metadata) t.metadata.alarm_status = 'stopped';
                    if (t.reminder_meta) t.reminder_meta.alarm_status = 'stopped';
                }
            });
        }

        if (!String(targetId).startsWith('course_')) {
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
        if (navigator.serviceWorker && navigator.serviceWorker.controller) {
            navigator.serviceWorker.controller.postMessage({
                type: 'REMOVE_NATIVE_TASK',
                taskId: String(targetId)
            });
        }
        sendNativeTwaMessage('abcdalarm://cancel?id=' + encodeURIComponent(targetId));
    }

    /**
     * Stop continuous alarm audio & dismiss modal
     * @param {Object} [options]
     * @param {boolean} [options.persistStop=false] - When true, marks alarm stopped locally & notifies server
     */
    function stopABCDAlarm(options) {
        const opts = options || {};
        const shouldPersist = Boolean(opts.persistStop);
        const targetId = currentAlarmTaskId;

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
        if (shouldPersist && targetId) {
            markAlarmStoppedLocallyAndRemotely(targetId);
        }
        currentAlarmTaskId = null;

        // Process next queued alarm if available
        if (pendingAlarmQueue.length > 0) {
            const nextAlarm = pendingAlarmQueue.shift();
            if (nextAlarm) {
                setTimeout(function () {
                    startABCDAlarm(
                        nextAlarm.title,
                        nextAlarm.body,
                        nextAlarm.taskId,
                        nextAlarm.isAlarm,
                        nextAlarm.customSoundSrc
                    );
                }, 350);
            }
        }
    }

    // ═════════════════════════════════════════════════════════════════════
    // GLOBAL IN-APP DUE ALARM CHECKER (Runs Across All Pages of ABCD)
    // ═════════════════════════════════════════════════════════════════════
    function getStoredAlarmSet(key) {
        const set = new Set();
        // Merge alarm IDs from both localStorage and sessionStorage
        try {
            const localRaw = localStorage.getItem(key);
            if (localRaw) {
                const parsed = JSON.parse(localRaw);
                if (Array.isArray(parsed)) {
                    parsed.forEach(function (id) { set.add(id); });
                }
            }
        } catch (e) {}
        try {
            const sessionRaw = sessionStorage.getItem(key);
            if (sessionRaw) {
                const parsed = JSON.parse(sessionRaw);
                if (Array.isArray(parsed)) {
                    parsed.forEach(function (id) { set.add(id); });
                }
            }
        } catch (e) {}
        return set;
    }

    function saveStoredAlarmSet(key, set) {
        try {
            const arr = JSON.stringify(Array.from(set));
            localStorage.setItem(key, arr);
            sessionStorage.setItem(key, arr);
        } catch (e) {}
    }

    const globalFiredAlarmIds = getStoredAlarmSet('firedAlarmIds');
    const locallyStoppedAlarmIds = getStoredAlarmSet('locallyStoppedAlarmIds');

    // ═════════════════════════════════════════════════════════════════════
    // NATIVE ANDROID TWA SCHEDULE SYNCHRONIZATION BRIDGE
    // ═════════════════════════════════════════════════════════════════════
    function isRunningInAndroidTwa() {
        const isStandalone = window.matchMedia && window.matchMedia('(display-mode: standalone)').matches;
        const isAndroid = /Android/i.test(navigator.userAgent);
        const hasTwaQuery = window.location.search.includes('pwa_app=1');
        const isTwaReferrer = document.referrer && document.referrer.includes('android-app://in.abcdcampus.app');
        const isTwaUserAgent = navigator.userAgent.includes('ABCDApp') || navigator.userAgent.includes('in.abcdcampus.app');
        return isAndroid && (isStandalone || hasTwaQuery || isTwaReferrer || isTwaUserAgent);
    }

    function getTwaBridgeToken() {
        let token = sessionStorage.getItem('abcd_twa_bridge_token');
        if (!token) {
            try {
                const params = new URLSearchParams(window.location.search);
                token = params.get('bridge_token');
                if (token) {
                    sessionStorage.setItem('abcd_twa_bridge_token', token);
                    params.delete('bridge_token');
                    const newSearch = params.toString();
                    const newUrl = window.location.pathname + (newSearch ? '?' + newSearch : '') + window.location.hash;
                    window.history.replaceState({}, document.title, newUrl);
                }
            } catch (e) {}
        }
        return token || '';
    }

    function isNativeAlarmTwaActive() {
        return Boolean(isRunningInAndroidTwa() && getTwaBridgeToken());
    }

    let twaBridgeIframe = null;
    let twaDispatchQueue = [];
    let isDispatchingTwa = false;
    const pendingNativeAcks = {}; // taskId -> { uri, attempts, timer }

    function processTwaQueue() {
        if (isDispatchingTwa || twaDispatchQueue.length === 0) return;
        isDispatchingTwa = true;
        const nextUri = twaDispatchQueue.shift();
        sendNativeTwaMessageDirect(nextUri);
        setTimeout(function () {
            isDispatchingTwa = false;
            processTwaQueue();
        }, 75);
    }

    function sendNativeTwaMessageDirect(schemeUri) {
        if (!isNativeAlarmTwaActive()) return;
        try {
            const token = getTwaBridgeToken();
            const sep = schemeUri.includes('?') ? '&' : '?';
            const authedUri = schemeUri + sep + 'bridge_token=' + encodeURIComponent(token);

            if (!twaBridgeIframe) {
                twaBridgeIframe = document.createElement('iframe');
                twaBridgeIframe.style.display = 'none';
                twaBridgeIframe.id = 'abcd-native-twa-bridge';
                document.body.appendChild(twaBridgeIframe);
            }
            twaBridgeIframe.src = authedUri;
        } catch (e) {
            console.debug('[ABCD Sound] TWA bridge dispatch error:', e);
        }
    }

    function sendNativeTwaMessage(schemeUri) {
        twaDispatchQueue.push(schemeUri);
        processTwaQueue();
    }

    function handleNativeScheduleAck(ack) {
        if (!ack || !ack.id) return;
        const taskId = String(ack.id);
        if (pendingNativeAcks[taskId]) {
            clearTimeout(pendingNativeAcks[taskId].timer);
            delete pendingNativeAcks[taskId];
        }
        if (ack.ok) {
            if (navigator.serviceWorker && navigator.serviceWorker.controller) {
                navigator.serviceWorker.controller.postMessage({
                    type: 'CONFIRM_NATIVE_TASK',
                    id: taskId,
                    exact: Boolean(ack.exact)
                });
            }
        }
    }

    // ═════════════════════════════════════════════════════════════════════
    // SHARED TWA / NATIVE MESSAGEPORT BRIDGE & DIAGNOSTICS SINGLETON
    // ═════════════════════════════════════════════════════════════════════
    if (typeof window !== 'undefined') {
        window.ABCD_NATIVE = window.ABCD_NATIVE || (function () {
            var _port = window._abcdTwaPort || null;
            var _listeners = [];
            var _portReadyListeners = [];
            var _lastCmd = null;
            var _lastStatus = null;

            function setPort(p) {
                if (!p) return;
                _port = p;
                window._abcdTwaPort = p;
                if (typeof p.start === 'function') {
                    try { p.start(); } catch (e) {}
                }
                p.onmessage = function (ev) {
                    var d = ev ? ev.data : null;
                    dispatch(d);
                };
                var cbs = _portReadyListeners.slice();
                cbs.forEach(function (cb) {
                    try { cb(p); } catch (e) {}
                });
            }

            function dispatch(data) {
                _listeners.forEach(function (fn) {
                    try { fn(data); } catch (e) {}
                });
            }

            function send(payload) {
                var str = (typeof payload === 'string') ? payload : JSON.stringify(payload);
                _lastCmd = { time: new Date().toLocaleTimeString(), payload: str };
                var activePort = _port || window._abcdTwaPort;
                if (activePort && typeof activePort.postMessage === 'function') {
                    try {
                        activePort.postMessage(str);
                        return true;
                    } catch (e) {
                        console.warn('[ABCD_NATIVE] postMessage error:', e);
                    }
                }
                return false;
            }

            return {
                getPort: function () { return _port || window._abcdTwaPort || null; },
                setPort: setPort,
                send: send,
                onMessage: function (fn) {
                    if (typeof fn === 'function' && _listeners.indexOf(fn) === -1) {
                        _listeners.push(fn);
                    }
                },
                onPortReady: function (cb) {
                    if (typeof cb !== 'function') return;
                    var activePort = _port || window._abcdTwaPort;
                    if (activePort) {
                        try { cb(activePort); } catch (e) {}
                    } else {
                        _portReadyListeners.push(cb);
                    }
                },
                getLastCommand: function () { return _lastCmd; },
                getLastStatus: function () { return _lastStatus; },
                setLastStatus: function (s) { _lastStatus = s; }
            };
        })();
    }

    let cachedNativeStatus = null;
    let nativeStatusCallbacks = [];
    let statusTimeoutTimer = null;
    let portReadyRetryHooked = false;

    function handleIncomingNativeMessage(data) {
        if (!data) return;
        if (typeof data === 'string' && data.trim().startsWith('{')) {
            try { data = JSON.parse(data); } catch (e) {}
        }
        if (data.type === 'schedule_ack') {
            handleNativeScheduleAck(data);
        } else if (data.type === 'native_status') {
            handleNativeStatusResponse(data);
        }
    }

    if (typeof window !== 'undefined' && window.ABCD_NATIVE && typeof window.ABCD_NATIVE.onMessage === 'function') {
        window.ABCD_NATIVE.onMessage(handleIncomingNativeMessage);
    }

    window.addEventListener('message', function (event) {
        if (!event) return;
        if (event.ports && event.ports.length > 0) {
            if (window.ABCD_NATIVE && typeof window.ABCD_NATIVE.setPort === 'function') {
                window.ABCD_NATIVE.setPort(event.ports[0]);
            }
        }
        if (event.data) {
            handleIncomingNativeMessage(event.data);
        }
    });

    function postMessageToNative(jsonObj) {
        if (!jsonObj) return false;
        if (window.ABCD_NATIVE && typeof window.ABCD_NATIVE.send === 'function') {
            return window.ABCD_NATIVE.send(jsonObj);
        }
        var activePort = (window.ABCD_NATIVE && typeof window.ABCD_NATIVE.getPort === 'function')
            ? window.ABCD_NATIVE.getPort()
            : (window._abcdTwaPort || null);
        if (activePort && typeof activePort.postMessage === 'function') {
            try {
                var str = (typeof jsonObj === 'string') ? jsonObj : JSON.stringify(jsonObj);
                activePort.postMessage(str);
                return true;
            } catch (e) {
                console.warn('[ABCD Sound] postMessage error:', e);
            }
        }
        return false;
    }

    function getUnknownStatus() {
        const isXiaomi = /Xiaomi|Redmi|POCO/i.test(navigator.userAgent);
        return {
            is_twa: true,
            is_unknown: true,
            notifications_enabled: (typeof Notification !== 'undefined' && Notification.permission === 'granted') ? true : null,
            exact_alarm_allowed: null,
            battery_unrestricted: null,
            is_xiaomi: isXiaomi,
            autostart: 'unknown',
            channels: {}
        };
    }

    function handleNativeStatusResponse(status) {
        if (status && !status.is_unknown && statusTimeoutTimer) {
            clearTimeout(statusTimeoutTimer);
            statusTimeoutTimer = null;
        }
        cachedNativeStatus = status;
        window.__abcdNativeStatus = status;
        if (window.ABCD_NATIVE && typeof window.ABCD_NATIVE.setLastStatus === 'function') {
            window.ABCD_NATIVE.setLastStatus(status);
        }
        const cbs = nativeStatusCallbacks.slice();
        nativeStatusCallbacks = [];
        cbs.forEach(function (cb) {
            try { cb(status); } catch (e) {}
        });
        updateChecklistUI(status);
        updateAmberBannerUI(status);
    }

    function requestNativeStatus(callback) {
        if (typeof callback === 'function') {
            nativeStatusCallbacks.push(callback);
        }
        if (!isNativeAlarmTwaActive()) {
            const fallback = {
                is_twa: false,
                is_unknown: false,
                notifications_enabled: (typeof Notification !== 'undefined' && Notification.permission === 'granted'),
                exact_alarm_allowed: false,
                battery_unrestricted: false,
                is_xiaomi: false,
                autostart: 'unknown',
                channels: {}
            };
            handleNativeStatusResponse(fallback);
            return;
        }

        const token = getTwaBridgeToken();
        const payload = { cmd: 'get_status', bridge_token: token };
        const sent = postMessageToNative(payload);

        if (!sent && !portReadyRetryHooked && window.ABCD_NATIVE && typeof window.ABCD_NATIVE.onPortReady === 'function') {
            portReadyRetryHooked = true;
            window.ABCD_NATIVE.onPortReady(function () {
                portReadyRetryHooked = false;
                if (isNativeAlarmTwaActive()) {
                    const freshToken = getTwaBridgeToken();
                    postMessageToNative({ cmd: 'get_status', bridge_token: freshToken });
                }
            });
        }

        // 2-second timeout: reject/flush callbacks with unknown status if no response received
        if (statusTimeoutTimer) {
            clearTimeout(statusTimeoutTimer);
        }
        statusTimeoutTimer = setTimeout(function () {
            statusTimeoutTimer = null;
            if (!cachedNativeStatus || cachedNativeStatus.is_unknown) {
                console.debug('[ABCD Sound] Native get_status timed out (2s) - defaulting to unknown state');
                handleNativeStatusResponse(getUnknownStatus());
            } else {
                const cbs = nativeStatusCallbacks.slice();
                nativeStatusCallbacks = [];
                cbs.forEach(function (cb) {
                    try { cb(cachedNativeStatus); } catch (e) {}
                });
            }
        }, 2000);
    }

    function openNativeSettings(target) {
        target = target || 'app_details';
        if (!isNativeAlarmTwaActive()) {
            if (typeof showModalAlert === 'function') {
                showModalAlert('Settings Guidance', 'To configure notification permissions in your browser, tap the lock or tune icon in the address bar.');
            } else {
                alert('To configure notification permissions in your browser, tap the lock or tune icon in the address bar.');
            }
            return;
        }
        const token = getTwaBridgeToken();
        postMessageToNative({ cmd: 'open_settings', target: target, bridge_token: token });
        sendNativeTwaMessage(`abcdalarm://open_settings?target=${encodeURIComponent(target)}&bridge_token=${encodeURIComponent(token)}`);
    }

    function requestNativeNotifications() {
        if (isNativeAlarmTwaActive()) {
            const token = getTwaBridgeToken();
            postMessageToNative({ cmd: 'request_notifications', bridge_token: token });
            sendNativeTwaMessage(`abcdalarm://request_notifications?bridge_token=${encodeURIComponent(token)}`);
        }
        if (typeof Notification !== 'undefined' && typeof Notification.requestPermission === 'function') {
            Notification.requestPermission().then(function () {
                if (isNativeAlarmTwaActive()) {
                    setTimeout(requestNativeStatus, 400);
                }
            });
        }
    }

    const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000;
    function isAutostartConfirmed() {
        const ts = parseInt(localStorage.getItem('abcd_autostart_confirmed_at') || '0', 10);
        return (Date.now() - ts) < THIRTY_DAYS_MS;
    }
    function setAutostartConfirmed(val) {
        if (val) localStorage.setItem('abcd_autostart_confirmed_at', String(Date.now()));
        else localStorage.removeItem('abcd_autostart_confirmed_at');
        if (cachedNativeStatus) updateChecklistUI(cachedNativeStatus);
    }
    function isFloatingConfirmed() {
        const ts = parseInt(localStorage.getItem('abcd_floating_confirmed_at') || '0', 10);
        return (Date.now() - ts) < THIRTY_DAYS_MS;
    }
    function setFloatingConfirmed(val) {
        if (val) localStorage.setItem('abcd_floating_confirmed_at', String(Date.now()));
        else localStorage.removeItem('abcd_floating_confirmed_at');
        if (cachedNativeStatus) updateChecklistUI(cachedNativeStatus);
    }

    function evaluateStatus(status) {
        if (!status || status.is_unknown === true) {
            // Unknown status: NEVER block saving reminders!
            return {
                ok: true,
                is_twa: isNativeAlarmTwaActive(),
                is_unknown: true,
                missingRequired: [],
                missingRecommended: ['unknown_state'],
                status: status || null
            };
        }
        if (status.is_twa === false) {
            const ok = Boolean(status.notifications_enabled);
            return {
                ok: ok,
                is_twa: false,
                is_unknown: false,
                missingRequired: ok ? [] : ['notifications'],
                missingRecommended: [],
                status: status
            };
        }

        // TWA with valid native status received: only block if explicitly denied
        const missingRequired = [];
        if (status.notifications_enabled === false) missingRequired.push('notifications');
        if (status.exact_alarm_allowed === false) missingRequired.push('exact_alarm');

        const missingRecommended = [];
        if (status.battery_unrestricted === false) missingRecommended.push('battery');
        if (status.is_xiaomi && !isAutostartConfirmed()) missingRecommended.push('autostart');
        if (!isFloatingConfirmed()) missingRecommended.push('floating');

        return {
            ok: missingRequired.length === 0,
            is_twa: true,
            is_unknown: false,
            missingRequired: missingRequired,
            missingRecommended: missingRecommended,
            status: status
        };
    }

    function checkAlarmSetupStatus(callback) {
        try {
            if (!cachedNativeStatus) {
                requestNativeStatus(function (status) {
                    const res = evaluateStatus(status);
                    if (typeof callback === 'function') callback(res);
                });
                return evaluateStatus(null);
            }
            const res = evaluateStatus(cachedNativeStatus);
            if (typeof callback === 'function') callback(res);
            return res;
        } catch (e) {
            console.warn('[ABCD Sound] checkAlarmSetupStatus error:', e);
            const safeFallback = { ok: true, is_twa: false, is_unknown: true, missingRequired: [], missingRecommended: [], status: null };
            if (typeof callback === 'function') callback(safeFallback);
            return safeFallback;
        }
    }

    let currentChecklistOptions = null;

    function showAlarmSetupChecklist(options) {
        currentChecklistOptions = options || {};

        if (!isNativeAlarmTwaActive()) {
            const guideMsg =
                'Device Optimization Guide\n\n' +
                '1. Ensure Notifications are Allowed in your browser settings.\n' +
                '2. In Android Settings > Apps > Chrome (or your browser) > Battery, select "Unrestricted".\n\n' +
                'Note: Device settings (Exact Alarms, MIUI Autostart, Heads-Up Banners) can only be opened directly from the ABCD Campus Android App.\n\n' +
                'Use the ABCD Campus App for native background alarm ringing.';
            if (typeof showModalAlert === 'function') {
                showModalAlert('Device Optimization Guide', guideMsg);
            } else {
                alert(guideMsg);
            }
            if (currentChecklistOptions.onConfirmed) {
                try { currentChecklistOptions.onConfirmed(); } catch (e) {}
            }
            return;
        }

        let modal = document.getElementById('abcdAlarmSetupModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'abcdAlarmSetupModal';
            modal.style.cssText = 'position:fixed; inset:0; z-index:999999; background:rgba(15,23,42,0.85); backdrop-filter:blur(6px); display:flex; align-items:center; justify-content:center; padding:16px; animation:fadeIn 0.2s ease;';
            modal.innerHTML = `
            <div style="background:#1e1b4b; border:1px solid #4338ca; border-radius:18px; max-width:540px; width:100%; max-height:90vh; overflow-y:auto; box-shadow:0 20px 45px rgba(0,0,0,0.6); color:#f8fafc; font-family:inherit; padding:24px;">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px;">
                    <div>
                        <h3 style="margin:0 0 4px 0; font-size:1.25rem; font-weight:800; color:#fff; display:flex; align-items:center; gap:8px;">
                            <span>⚡</span> Device Alarm Setup
                        </h3>
                        <p style="margin:0; font-size:0.82rem; color:#94a3b8;">Ensure ABCD alarms ring on time when your screen is locked.</p>
                    </div>
                    <button type="button" id="abcdChecklistCloseBtn" onclick="closeAlarmSetupChecklist()" style="background:transparent; border:none; color:#94a3b8; font-size:1.5rem; cursor:pointer; line-height:1;">&times;</button>
                </div>

                <div id="abcdChecklistRowsContainer" style="display:flex; flex-direction:column; gap:12px; margin-bottom:20px;">
                    <div style="text-align:center; padding:20px; color:#94a3b8; font-size:0.85rem;">Checking device settings...</div>
                </div>

                <div style="display:flex; flex-direction:column; gap:8px;">
                    <button type="button" id="abcdChecklistConfirmBtn" onclick="confirmAlarmSetupChecklist()" style="background:#7b61ff; color:#fff; border:none; padding:13px; border-radius:12px; font-weight:700; font-size:0.95rem; cursor:pointer; box-shadow:0 4px 14px rgba(123,97,255,0.4); transition:all 0.2s;">
                        🔔 Confirm & Enable Device Ring
                    </button>
                    <button type="button" id="abcdChecklistSaveWithoutBtn" onclick="saveWithoutDeviceRingChecklist()" style="background:rgba(255,255,255,0.06); color:#cbd5e1; border:1px solid rgba(255,255,255,0.12); padding:10px; border-radius:12px; font-weight:600; font-size:0.85rem; cursor:pointer;">
                        Save without device ring (Web Push only)
                    </button>
                </div>
                <div style="margin-top:12px; text-align:center;">
                    <a href="javascript:void(0)" id="abcdChecklistDiagLink" onclick="showNativeDebugPanel()" style="font-size:0.75rem; color:#6366f1; text-decoration:none;">View Diagnostic Status</a>
                </div>
            </div>`;
            document.body.appendChild(modal);

            const cBtn = document.getElementById('abcdChecklistCloseBtn');
            if (cBtn) cBtn.addEventListener('click', closeAlarmSetupChecklist);
            const confBtn = document.getElementById('abcdChecklistConfirmBtn');
            if (confBtn) confBtn.addEventListener('click', confirmAlarmSetupChecklist);
            const noRingBtn = document.getElementById('abcdChecklistSaveWithoutBtn');
            if (noRingBtn) noRingBtn.addEventListener('click', saveWithoutDeviceRingChecklist);
            const dLink = document.getElementById('abcdChecklistDiagLink');
            if (dLink) dLink.addEventListener('click', showNativeDebugPanel);
        } else {
            modal.style.display = 'flex';
        }

        requestNativeStatus(function (status) {
            updateChecklistUI(status);
        });
    }

    function closeAlarmSetupChecklist() {
        const modal = document.getElementById('abcdAlarmSetupModal');
        if (modal) modal.style.display = 'none';
    }

    function confirmAlarmSetupChecklist() {
        const evalRes = evaluateStatus(cachedNativeStatus);
        if (!evalRes.ok) {
            alert('Please allow Notifications and Exact Alarms to enable device ring.');
            return;
        }
        closeAlarmSetupChecklist();
        if (currentChecklistOptions && typeof currentChecklistOptions.onConfirmed === 'function') {
            try { currentChecklistOptions.onConfirmed(); } catch (e) {}
        }
    }

    function saveWithoutDeviceRingChecklist() {
        closeAlarmSetupChecklist();
        if (currentChecklistOptions && typeof currentChecklistOptions.onSaveWithoutRing === 'function') {
            try { currentChecklistOptions.onSaveWithoutRing(); } catch (e) {}
        }
    }

    function updateChecklistUI(status) {
        const container = document.getElementById('abcdChecklistRowsContainer');
        if (!container || !status) return;

        const evalRes = evaluateStatus(status);
        const isNotifs = (status.notifications_enabled === true);
        const notifUnknown = (status.notifications_enabled === null || typeof status.notifications_enabled === 'undefined');
        const isExact = (status.exact_alarm_allowed === true);
        const exactUnknown = (status.exact_alarm_allowed === null || typeof status.exact_alarm_allowed === 'undefined');
        const isBattery = (status.battery_unrestricted === true);
        const batteryUnknown = (status.battery_unrestricted === null || typeof status.battery_unrestricted === 'undefined');
        const isXiaomi = Boolean(status.is_xiaomi);
        const isAuto = isAutostartConfirmed();
        const isFloat = isFloatingConfirmed();

        let rowsHtml = '';

        // Row 1: Notifications
        const notifBadgeColor = isNotifs ? 'rgba(16,185,129,0.2)' : (notifUnknown ? 'rgba(245,158,11,0.2)' : 'rgba(239,68,68,0.2)');
        const notifBadgeText = isNotifs ? '#34d399' : (notifUnknown ? '#fbbf24' : '#f87171');
        const notifIcon = isNotifs ? '✓' : (notifUnknown ? '?' : '✕');
        const notifIconColor = isNotifs ? '#10b981' : (notifUnknown ? '#f59e0b' : '#ef4444');
        const notifBorder = isNotifs ? 'rgba(16,185,129,0.4)' : (notifUnknown ? 'rgba(245,158,11,0.4)' : 'rgba(239,68,68,0.4)');

        rowsHtml += `
        <div style="background:rgba(255,255,255,0.04); border:1px solid ${notifBorder}; border-radius:12px; padding:12px 14px; display:flex; align-items:center; justify-content:space-between; gap:12px;">
            <div style="flex:1;">
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:1.1rem; color:${notifIconColor}; font-weight:800;">${notifIcon}</span>
                    <strong style="font-size:0.9rem; color:#fff;">1. Notifications Allowed</strong>
                    <span style="font-size:0.68rem; background:${notifBadgeColor}; color:${notifBadgeText}; padding:2px 6px; border-radius:4px; font-weight:700;">REQUIRED</span>
                </div>
                <div style="font-size:0.76rem; color:#94a3b8; margin-top:3px;">Needed so alarms and reminders ring when screen is locked.</div>
            </div>
            ${isNotifs ? '<span style="font-size:0.8rem; color:#10b981; font-weight:700;">Enabled</span>' :
            `<button type="button" id="abcdRowNotifBtn" onclick="requestNativeNotifications()" style="background:#f59e0b; color:#fff; border:none; padding:6px 12px; border-radius:8px; font-size:0.78rem; font-weight:700; cursor:pointer;">Allow</button>`}
        </div>`;

        // Row 2: Exact Alarms
        const exactBadgeColor = isExact ? 'rgba(16,185,129,0.2)' : (exactUnknown ? 'rgba(245,158,11,0.2)' : 'rgba(239,68,68,0.2)');
        const exactBadgeText = isExact ? '#34d399' : (exactUnknown ? '#fbbf24' : '#f87171');
        const exactIcon = isExact ? '✓' : (exactUnknown ? '?' : '✕');
        const exactIconColor = isExact ? '#10b981' : (exactUnknown ? '#f59e0b' : '#ef4444');
        const exactBorder = isExact ? 'rgba(16,185,129,0.4)' : (exactUnknown ? 'rgba(245,158,11,0.4)' : 'rgba(239,68,68,0.4)');

        rowsHtml += `
        <div style="background:rgba(255,255,255,0.04); border:1px solid ${exactBorder}; border-radius:12px; padding:12px 14px; display:flex; align-items:center; justify-content:space-between; gap:12px;">
            <div style="flex:1;">
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:1.1rem; color:${exactIconColor}; font-weight:800;">${exactIcon}</span>
                    <strong style="font-size:0.9rem; color:#fff;">2. Exact Alarms Allowed</strong>
                    <span style="font-size:0.68rem; background:${exactBadgeColor}; color:${exactBadgeText}; padding:2px 6px; border-radius:4px; font-weight:700;">REQUIRED</span>
                </div>
                <div style="font-size:0.76rem; color:#94a3b8; margin-top:3px;">Needed by Android so alarms trigger at the exact scheduled second.</div>
            </div>
            ${isExact ? '<span style="font-size:0.8rem; color:#10b981; font-weight:700;">Allowed</span>' :
            `<button type="button" id="abcdRowExactBtn" onclick="openNativeSettings('exact_alarm')" style="background:#f59e0b; color:#fff; border:none; padding:6px 12px; border-radius:8px; font-size:0.78rem; font-weight:700; cursor:pointer;">Open</button>`}
        </div>`;

        // Row 3: Battery No Restrictions
        const batteryIcon = isBattery ? '✓' : (batteryUnknown ? '?' : '!');
        const batteryIconColor = isBattery ? '#10b981' : '#f59e0b';
        const batteryBorder = isBattery ? 'rgba(16,185,129,0.4)' : 'rgba(245,158,11,0.4)';

        rowsHtml += `
        <div style="background:rgba(255,255,255,0.04); border:1px solid ${batteryBorder}; border-radius:12px; padding:12px 14px; display:flex; align-items:center; justify-content:space-between; gap:12px;">
            <div style="flex:1;">
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:1.1rem; color:${batteryIconColor}; font-weight:800;">${batteryIcon}</span>
                    <strong style="font-size:0.9rem; color:#fff;">3. Battery: No Restrictions</strong>
                    <span style="font-size:0.68rem; background:rgba(99,102,241,0.2); color:#a5b4fc; padding:2px 6px; border-radius:4px; font-weight:700;">RECOMMENDED</span>
                </div>
                <div style="font-size:0.76rem; color:#94a3b8; margin-top:3px;">Prevents Android Doze power saver from delaying background alarms.</div>
            </div>
            ${isBattery ? '<span style="font-size:0.8rem; color:#10b981; font-weight:700;">Unrestricted</span>' :
            `<button type="button" id="abcdRowBatteryBtn" onclick="openNativeSettings('battery')" style="background:#6366f1; color:#fff; border:none; padding:6px 12px; border-radius:8px; font-size:0.78rem; font-weight:700; cursor:pointer;">Open</button>`}
        </div>`;

        // Row 4: Xiaomi Autostart (if is_xiaomi)
        if (isXiaomi) {
            rowsHtml += `
            <div style="background:rgba(255,255,255,0.04); border:1px solid ${isAuto ? 'rgba(16,185,129,0.4)' : 'rgba(245,158,11,0.4)'}; border-radius:12px; padding:12px 14px;">
                <div style="display:flex; align-items:center; justify-content:space-between; gap:12px;">
                    <div style="flex:1;">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <span style="font-size:1.1rem; color:${isAuto ? '#10b981' : '#f59e0b'}; font-weight:800;">${isAuto ? '✓' : '!'}</span>
                            <strong style="font-size:0.9rem; color:#fff;">4. Xiaomi / MIUI Autostart</strong>
                            <span style="font-size:0.68rem; background:rgba(99,102,241,0.2); color:#a5b4fc; padding:2px 6px; border-radius:4px; font-weight:700;">RECOMMENDED</span>
                        </div>
                        <div style="font-size:0.76rem; color:#94a3b8; margin-top:3px;">MIUI kills background apps unless Autostart is turned on in Security settings.</div>
                    </div>
                    <button type="button" id="abcdRowAutostartBtn" onclick="openNativeSettings('autostart')" style="background:#6366f1; color:#fff; border:none; padding:6px 12px; border-radius:8px; font-size:0.78rem; font-weight:700; cursor:pointer;">Open</button>
                </div>
                <div style="margin-top:8px; padding-top:8px; border-top:1px solid rgba(255,255,255,0.08); display:flex; align-items:center; gap:8px;">
                    <input type="checkbox" id="abcdAutostartConfirmCb" ${isAuto ? 'checked' : ''} onchange="setAutostartConfirmed(this.checked)" style="accent-color:#7b61ff; cursor:pointer;">
                    <label for="abcdAutostartConfirmCb" style="font-size:0.78rem; color:#cbd5e1; cursor:pointer;">I turned ON Autostart in MIUI Settings</label>
                </div>
            </div>`;
        }

        // Row 5: Floating & Lock-screen notifications
        rowsHtml += `
        <div style="background:rgba(255,255,255,0.04); border:1px solid ${isFloat ? 'rgba(16,185,129,0.4)' : 'rgba(245,158,11,0.4)'}; border-radius:12px; padding:12px 14px;">
            <div style="display:flex; align-items:center; justify-content:space-between; gap:12px;">
                <div style="flex:1;">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <span style="font-size:1.1rem; color:${isFloat ? '#10b981' : '#f59e0b'}; font-weight:800;">${isFloat ? '✓' : '!'}</span>
                        <strong style="font-size:0.9rem; color:#fff;">5. Heads-Up & Lock Screen</strong>
                        <span style="font-size:0.68rem; background:rgba(99,102,241,0.2); color:#a5b4fc; padding:2px 6px; border-radius:4px; font-weight:700;">RECOMMENDED</span>
                    </div>
                    <div style="font-size:0.76rem; color:#94a3b8; margin-top:3px;">Shows floating banners over other apps and on lock screen.</div>
                </div>
                <button type="button" id="abcdRowChannelBtn" onclick="openNativeSettings('channel_alarm')" style="background:#6366f1; color:#fff; border:none; padding:6px 12px; border-radius:8px; font-size:0.78rem; font-weight:700; cursor:pointer;">Open</button>
            </div>
            <div style="margin-top:8px; padding-top:8px; border-top:1px solid rgba(255,255,255,0.08); display:flex; align-items:center; gap:8px;">
                <input type="checkbox" id="abcdFloatingConfirmCb" ${isFloat ? 'checked' : ''} onchange="setFloatingConfirmed(this.checked)" style="accent-color:#7b61ff; cursor:pointer;">
                <label for="abcdFloatingConfirmCb" style="font-size:0.78rem; color:#cbd5e1; cursor:pointer;">I allowed Floating & Lock-screen notifications</label>
            </div>
        </div>`;

        container.innerHTML = rowsHtml;

        // Attach listeners directly to created row elements
        const rNotifBtn = document.getElementById('abcdRowNotifBtn');
        if (rNotifBtn) rNotifBtn.addEventListener('click', requestNativeNotifications);
        const rExactBtn = document.getElementById('abcdRowExactBtn');
        if (rExactBtn) rExactBtn.addEventListener('click', function () { openNativeSettings('exact_alarm'); });
        const rBatteryBtn = document.getElementById('abcdRowBatteryBtn');
        if (rBatteryBtn) rBatteryBtn.addEventListener('click', function () { openNativeSettings('battery'); });
        const rAutostartBtn = document.getElementById('abcdRowAutostartBtn');
        if (rAutostartBtn) rAutostartBtn.addEventListener('click', function () { openNativeSettings('autostart'); });
        const rAutostartCb = document.getElementById('abcdAutostartConfirmCb');
        if (rAutostartCb) rAutostartCb.addEventListener('change', function () { setAutostartConfirmed(this.checked); });
        const rChannelBtn = document.getElementById('abcdRowChannelBtn');
        if (rChannelBtn) rChannelBtn.addEventListener('click', function () { openNativeSettings('channel_alarm'); });
        const rFloatingCb = document.getElementById('abcdFloatingConfirmCb');
        if (rFloatingCb) rFloatingCb.addEventListener('change', function () { setFloatingConfirmed(this.checked); });

        const confirmBtn = document.getElementById('abcdChecklistConfirmBtn');
        if (confirmBtn) {
            if (evalRes.ok) {
                confirmBtn.disabled = false;
                confirmBtn.style.opacity = '1';
                confirmBtn.style.cursor = 'pointer';
                confirmBtn.textContent = '🔔 Confirm & Enable Device Ring';
            } else {
                confirmBtn.disabled = true;
                confirmBtn.style.opacity = '0.5';
                confirmBtn.style.cursor = 'not-allowed';
                confirmBtn.textContent = '⚠️ Enable Required Items (1 & 2) First';
            }
        }
    }

    function updateAmberBannerUI(status) {
        const banners = document.querySelectorAll('#abcdAlarmWarningBanner');
        if (!banners || banners.length === 0) return;
        const evalRes = evaluateStatus(status);
        const shouldShow = evalRes.is_twa && evalRes.ok && (evalRes.missingRecommended.length > 0 || evalRes.is_unknown);
        banners.forEach(function (b) {
            b.style.display = shouldShow ? 'flex' : 'none';
        });
    }

    // ═════════════════════════════════════════════════════════════════════
    // ON-PHONE DEBUGGER & ERROR CAPTURE BOX
    // ═════════════════════════════════════════════════════════════════════
    window.__abcdErrors = window.__abcdErrors || [];
    window.addEventListener('error', function (e) {
        try {
            var item = {
                type: 'error',
                time: new Date().toLocaleTimeString(),
                msg: e.message || String(e),
                src: (e.filename ? e.filename.split('/').pop() : '') + ':' + (e.lineno || '?')
            };
            window.__abcdErrors.push(item);
            if (window.__abcdErrors.length > 30) window.__abcdErrors.shift();
            renderDebugErrorBox();
        } catch (err) {}
    });
    window.addEventListener('unhandledrejection', function (e) {
        try {
            var reason = e ? e.reason : '';
            var msg = (reason && (reason.message || reason.stack)) ? (reason.message || String(reason)) : String(reason);
            var item = {
                type: 'rejection',
                time: new Date().toLocaleTimeString(),
                msg: msg,
                src: 'promise'
            };
            window.__abcdErrors.push(item);
            if (window.__abcdErrors.length > 30) window.__abcdErrors.shift();
            renderDebugErrorBox();
        } catch (err) {}
    });

    function isDebugModeActive() {
        try {
            return window.location.search.includes('abcd_debug=1') || sessionStorage.getItem('abcd_debug') === '1';
        } catch (e) {
            return false;
        }
    }

    function renderDebugErrorBox() {
        if (!isDebugModeActive()) return;
        let box = document.getElementById('abcdDebugErrorBox');
        if (!box) {
            box = document.createElement('div');
            box.id = 'abcdDebugErrorBox';
            box.style.cssText = 'position:fixed; bottom:10px; left:10px; right:10px; z-index:99999999; background:rgba(15,23,42,0.95); border:1px solid #ef4444; border-radius:10px; padding:10px 12px; color:#f8fafc; font-family:monospace; font-size:11px; max-height:220px; overflow-y:auto; box-shadow:0 8px 24px rgba(0,0,0,0.7);';
            box.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:4px;">
                <strong style="color:#f87171;">🐞 ABCD Phone Debugger</strong>
                <div>
                    <button type="button" id="abcdDebugRefreshBtn" style="background:#3b82f6; color:#fff; border:none; padding:2px 6px; border-radius:4px; font-size:10px; cursor:pointer; margin-right:4px;">Status</button>
                    <button type="button" id="abcdDebugClearBtn" style="background:#475569; color:#fff; border:none; padding:2px 6px; border-radius:4px; font-size:10px; cursor:pointer; margin-right:4px;">Clear</button>
                    <button type="button" id="abcdDebugCloseBtn" style="background:transparent; color:#94a3b8; border:none; font-size:14px; cursor:pointer;">&times;</button>
                </div>
            </div>
            <div id="abcdDebugStatusRow" style="color:#38bdf8; margin-bottom:4px;"></div>
            <div id="abcdDebugErrorsList" style="display:flex; flex-direction:column; gap:4px;"></div>`;
            document.body.appendChild(box);

            const closeBtn = document.getElementById('abcdDebugCloseBtn');
            if (closeBtn) closeBtn.onclick = function () { box.style.display = 'none'; };
            const clearBtn = document.getElementById('abcdDebugClearBtn');
            if (clearBtn) clearBtn.onclick = function () { window.__abcdErrors = []; renderDebugErrorBox(); };
            const refreshBtn = document.getElementById('abcdDebugRefreshBtn');
            if (refreshBtn) refreshBtn.onclick = function () { requestNativeStatus(); renderDebugErrorBox(); };
        } else {
            box.style.display = 'block';
        }

        const statusRow = document.getElementById('abcdDebugStatusRow');
        if (statusRow) {
            const portActive = (window.ABCD_NATIVE && window.ABCD_NATIVE.getPort()) ? 'CONNECTED' : (window._abcdTwaPort ? 'CONNECTED' : 'DISCONNECTED');
            const lastCmd = (window.ABCD_NATIVE && window.ABCD_NATIVE.getLastCommand()) || null;
            const lastSt = (window.ABCD_NATIVE && window.ABCD_NATIVE.getLastStatus()) || cachedNativeStatus || null;
            statusRow.innerHTML = `Port: <b>${portActive}</b> | Token: <b>${Boolean(getTwaBridgeToken())}</b><br>` +
                (lastCmd ? `Last Cmd: <span style="color:#94a3b8;">${lastCmd.payload} (${lastCmd.time})</span><br>` : '') +
                (lastSt ? `Last Status: <span style="color:#a5b4fc;">notifs=${lastSt.notifications_enabled}, exact=${lastSt.exact_alarm_allowed}, unknown=${Boolean(lastSt.is_unknown)}</span>` : '');
        }

        const list = document.getElementById('abcdDebugErrorsList');
        if (list) {
            if (window.__abcdErrors.length === 0) {
                list.innerHTML = '<span style="color:#10b981;">No JS errors recorded.</span>';
            } else {
                list.innerHTML = window.__abcdErrors.map(function (err) {
                    return `<div style="background:rgba(239,68,68,0.15); padding:4px 6px; border-radius:4px; word-break:break-all;">
                        <span style="color:#f87171;">[${err.time}] ${err.type}</span>: ${err.msg} <span style="color:#94a3b8;">(${err.src || ''})</span>
                    </div>`;
                }).join('');
            }
        }
    }

    function showNativeDebugPanel() {
        let p = document.getElementById('abcdNativeDebugModal');
        if (!p) {
            p = document.createElement('div');
            p.id = 'abcdNativeDebugModal';
            p.style.cssText = 'position:fixed; inset:0; z-index:9999999; background:rgba(0,0,0,0.85); display:flex; align-items:center; justify-content:center; padding:16px;';
            p.innerHTML = `
            <div style="background:#0f172a; border:1px solid #334155; border-radius:14px; max-width:600px; width:100%; max-height:85vh; display:flex; flex-direction:column; padding:20px; color:#e2e8f0; font-family:monospace;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                    <strong style="color:#38bdf8;">Native Diagnostic Status (Debug)</strong>
                    <button type="button" id="abcdDiagModalCloseBtn" onclick="document.getElementById('abcdNativeDebugModal').style.display='none'" style="background:transparent; border:none; color:#94a3b8; font-size:1.4rem; cursor:pointer;">&times;</button>
                </div>
                <pre id="abcdNativeDebugJson" style="flex:1; overflow-y:auto; background:#020617; padding:12px; border-radius:8px; font-size:0.75rem; white-space:pre-wrap; word-break:break-all;"></pre>
                <div style="display:flex; gap:10px; margin-top:12px;">
                    <button type="button" id="abcdDiagRefreshBtn" onclick="requestNativeStatus()" style="flex:1; background:#6366f1; color:#fff; border:none; padding:8px; border-radius:6px; cursor:pointer; font-weight:700;">Refresh Status</button>
                    <button type="button" id="abcdDiagCloseFooterBtn" onclick="document.getElementById('abcdNativeDebugModal').style.display='none'" style="flex:1; background:#334155; color:#fff; border:none; padding:8px; border-radius:6px; cursor:pointer;">Close</button>
                </div>
            </div>`;
            document.body.appendChild(p);

            const cBtn = document.getElementById('abcdDiagModalCloseBtn');
            if (cBtn) cBtn.addEventListener('click', function () { p.style.display = 'none'; });
            const cFoot = document.getElementById('abcdDiagCloseFooterBtn');
            if (cFoot) cFoot.addEventListener('click', function () { p.style.display = 'none'; });
            const refBtn = document.getElementById('abcdDiagRefreshBtn');
            if (refBtn) refBtn.addEventListener('click', function () { requestNativeStatus(); });
        } else {
            p.style.display = 'flex';
        }

        const pre = document.getElementById('abcdNativeDebugJson');
        const portStatus = (window.ABCD_NATIVE && window.ABCD_NATIVE.getPort()) ? 'CONNECTED' : (window._abcdTwaPort ? 'CONNECTED' : 'DISCONNECTED');
        const diagSnapshot = {
            twa_active: isNativeAlarmTwaActive(),
            bridge_token_present: Boolean(getTwaBridgeToken()),
            port_status: portStatus,
            last_command_sent: (window.ABCD_NATIVE && window.ABCD_NATIVE.getLastCommand()) || null,
            last_status: (window.ABCD_NATIVE && window.ABCD_NATIVE.getLastStatus()) || cachedNativeStatus || null,
            recorded_js_errors: window.__abcdErrors || [],
            twa_diag: window._abcdTwaDiag || null
        };
        if (pre) {
            pre.textContent = JSON.stringify(diagSnapshot, null, 2);
        }
        requestNativeStatus(function (st) {
            diagSnapshot.last_status = st;
            if (pre) pre.textContent = JSON.stringify(diagSnapshot, null, 2);
        });
    }

    window.addEventListener('focus', function () {
        if (isNativeAlarmTwaActive()) requestNativeStatus();
    });
    window.addEventListener('pageshow', function () {
        if (isNativeAlarmTwaActive()) requestNativeStatus();
    });
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden && isNativeAlarmTwaActive()) {
            requestNativeStatus();
        }
    });
    if (window.ABCD_NATIVE && typeof window.ABCD_NATIVE.onPortReady === 'function') {
        window.ABCD_NATIVE.onPortReady(function () {
            if (isNativeAlarmTwaActive()) requestNativeStatus();
        });
    }

    let longPressTimer = null;
    document.addEventListener('touchstart', function (e) {
        if (e.target && (e.target.closest('#nav-app-logo') || e.target.closest('.brand') || e.target.closest('#reminderAlarmToggle'))) {
            longPressTimer = setTimeout(function () {
                showNativeDebugPanel();
            }, 2500);
        }
    }, { passive: true });
    document.addEventListener('touchend', function () {
        if (longPressTimer) {
            clearTimeout(longPressTimer);
            longPressTimer = null;
        }
    }, { passive: true });

    function trackPendingSchedule(taskId, uri) {
        if (pendingNativeAcks[taskId]) {
            clearTimeout(pendingNativeAcks[taskId].timer);
        }
        pendingNativeAcks[taskId] = {
            uri: uri,
            attempts: 1,
            timer: setTimeout(function () {
                retryUnacknowledgedSchedule(taskId);
            }, 3500)
        };
    }

    function retryUnacknowledgedSchedule(taskId) {
        const pending = pendingNativeAcks[taskId];
        if (!pending) return;
        if (pending.attempts < 2) {
            pending.attempts += 1;
            console.debug('[ABCD Sound] Retrying native alarm schedule for task:', taskId, 'attempt:', pending.attempts);
            sendNativeTwaMessage(pending.uri);
            pending.timer = setTimeout(function () {
                retryUnacknowledgedSchedule(taskId);
            }, 3500);
        } else {
            console.warn('[ABCD Sound] Native schedule ACK timed out for task:', taskId, '- leaving unconfirmed so Web Push remains active fallback.');
            delete pendingNativeAcks[taskId];
        }
    }

    function syncRemindersToNativeTwa(reminders) {
        if (!isNativeAlarmTwaActive() || !Array.isArray(reminders)) return;
        try {
            const scheduledTasks = [];
            const activeIds = [];

            reminders.forEach(function (rem) {
                if (!rem || rem.alarm_status === 'stopped') return;
                // Sync all alarms AND plain reminders AND course-source reminders to native.
                // Every sounding reminder gets native scheduling so it survives TWA being closed/killed.
                const isAlarmVal = rem.is_alarm ? 1 : 0;

                const taskId = (rem.source === 'course' && !String(rem.id).startsWith('course_')) ? 'course_' + rem.id : String(rem.id);
                activeIds.push(taskId);

                let triggerMillis = 0;
                if (rem.recurrence === 'once' && rem.fire_at) {
                    const dt = new Date(rem.fire_at);
                    if (!isNaN(dt.getTime()) && dt.getTime() > Date.now()) {
                        triggerMillis = dt.getTime();
                    }
                } else if (rem.time_str) {
                    const parts = String(rem.time_str).split(':').map(Number);
                    const now = new Date();
                    let target = new Date(now.getFullYear(), now.getMonth(), now.getDate(), parts[0] || 0, parts[1] || 0, 0);
                    if (target.getTime() <= now.getTime()) {
                        target.setDate(target.getDate() + 1);
                    }
                    triggerMillis = target.getTime();
                }

                if (triggerMillis > Date.now()) {
                    const cleanTitle = encodeURIComponent(rem.title || 'Scheduled Reminder');
                    const cleanNote = encodeURIComponent(rem.note || 'Your scheduled reminder is ringing now!');
                    const defaultSound = isAlarmVal ? '/static/audio/alarm.mp3' : '/static/audio/PWA.mp3';
                    const cleanSound = encodeURIComponent(rem.sound || defaultSound);
                    const cleanActionToken = encodeURIComponent(rem.action_token || '');
                    const cleanRecurrence = encodeURIComponent(rem.recurrence || 'once');
                    const cleanScheduleTime = encodeURIComponent(rem.time_str || '');
                    const cleanDaysOfWeek = encodeURIComponent(rem.days_of_week || '');
                    const cleanDayOfMonth = encodeURIComponent(rem.day_of_month || 1);
                    const cleanIntervalDays = encodeURIComponent(rem.interval_days || 1);
                    const cleanUntilDate = encodeURIComponent(rem.until_date || '');

                    const uri = `abcdalarm://schedule?id=${encodeURIComponent(taskId)}&time=${triggerMillis}&title=${cleanTitle}&body=${cleanNote}&is_alarm=${isAlarmVal}&sound=${cleanSound}&action_token=${cleanActionToken}&recurrence=${cleanRecurrence}&schedule_time=${cleanScheduleTime}&days_of_week=${cleanDaysOfWeek}&day_of_month=${cleanDayOfMonth}&interval_days=${cleanIntervalDays}&until_date=${cleanUntilDate}`;
                    sendNativeTwaMessage(uri);
                    trackPendingSchedule(taskId, uri);

                    scheduledTasks.push({ id: taskId, triggerAt: triggerMillis });
                }
            });

            // Reconcile active server tasks with native AlarmManager (cancel any removed tasks)
            if (activeIds.length > 0) {
                sendNativeTwaMessage(`abcdalarm://reconcile?active_ids=${encodeURIComponent(activeIds.join(','))}`);
            } else if (reminders.length === 0) {
                // Server explicitly confirmed 0 active reminders: send confirmed reconcile
                sendNativeTwaMessage('abcdalarm://reconcile?active_ids=&confirmed=1');
            }

            // Notify Service Worker of confirmed native tasks for exact per-task suppression
            if (navigator.serviceWorker && navigator.serviceWorker.controller) {
                navigator.serviceWorker.controller.postMessage({
                    type: 'SET_TWA_MODE',
                    isTwa: true,
                    tasks: scheduledTasks
                });
            }
        } catch (err) {
            console.debug('[ABCD Sound] Error synchronizing to native TWA:', err);
        }
    }

    window.__abcdCachedReminders = [];
    let isCheckingGlobalAlarms = false;

    // High-precision 1-second in-memory checker: fires on the exact second with 0 latency
    function tickGlobalDueAlarmsInMemory() {
        const tasks = window.__abcdCachedReminders;
        if (!tasks || !Array.isArray(tasks) || tasks.length === 0) return;

        const nowMs = Date.now();
        tasks.forEach(function (task) {
            if (!task || task.is_done || task.is_trash) return;

            const uniqueKey = (task.source === 'course') ? ('course_' + task.id) : task.id;

            // DO NOT reopen an alarm after a local stop action!
            if (locallyStoppedAlarmIds.has(uniqueKey)) return;

            const meta = task.metadata || task.reminder_meta || {};
            if (task.alarm_status === 'stopped' || meta.alarm_status === 'stopped') return;
            const isRinging = (task.alarm_status === 'ringing' || meta.alarm_status === 'ringing');
            if (globalFiredAlarmIds.has(uniqueKey) && !isRinging) return;

            let isDueNow = false;
            const rec = task.recurrence || meta.recurrence || 'once';

            if (isRinging) {
                // Backend scheduler marked it as ringing: only trigger if ringing was set in last 60 seconds
                const lastNotif = task.last_notified_at ? new Date(task.last_notified_at).getTime() : 0;
                const ringingElapsed = lastNotif ? (nowMs - lastNotif) / 1000 : 999;
                if (ringingElapsed >= 0 && ringingElapsed <= 60) {
                    isDueNow = true;
                }
            } else if (rec === 'once') {
                const fireTarget = task.fire_at || meta.fire_at || task.delete_at;
                if (fireTarget) {
                    const fireDt = new Date(fireTarget);
                    const fireMs = fireDt.getTime();
                    const elapsedSec = (nowMs - fireMs) / 1000;

                    // Due right now: user is actively on page when the scheduled time hits (0 to 30 seconds window)
                    if (elapsedSec >= 0 && elapsedSec <= 30) {
                        isDueNow = true;
                    }
                }
            } else if (task.time_str || meta.time_str) {
                const parts = String(task.time_str || meta.time_str).split(':').map(Number);
                const now = new Date();
                const currentWeekday = (now.getDay() + 6) % 7; // JS Sun=0 -> Mon=0..Sun=6
                let dayMatches = true;
                if (rec === 'weekly') {
                    dayMatches = (currentWeekday === 5 || currentWeekday === 6);
                } else if (rec === 'custom' && task.days_of_week) {
                    const allowedDays = String(task.days_of_week).split(',').map(function (d) { return parseInt(d.trim(), 10); });
                    dayMatches = allowedDays.includes(currentWeekday);
                }

                if (dayMatches) {
                    const todayFireDt = new Date(now.getFullYear(), now.getMonth(), now.getDate(), parts[0] || 0, parts[1] || 0, 0);
                    const elapsedSec = (nowMs - todayFireDt.getTime()) / 1000;

                    // Due right now: user is actively on page when the scheduled time hits (0 to 30 seconds window)
                    if (elapsedSec >= 0 && elapsedSec <= 30) {
                        isDueNow = true;
                    }
                }
            }

            if (isDueNow) {
                globalFiredAlarmIds.add(uniqueKey);
                saveStoredAlarmSet('firedAlarmIds', globalFiredAlarmIds);

                const title = task.title || meta.title || 'Reminder';
                const note = task.note || meta.note || '';
                const isAlarm = Boolean(task.is_alarm !== undefined ? task.is_alarm : (meta.alarm_enabled !== false && meta.alarm_enabled !== 'false' && meta.alarm_enabled !== 0));
                const sound = task.sound || (isAlarm ? '/static/audio/alarm.mp3' : (task.source === 'course' ? '/static/audio/alarms and reminders.mp3' : '/static/audio/PWA.mp3'));

                startABCDAlarm(title, note, uniqueKey, isAlarm, sound);
            }
        });
    }

    let isUserUnauthenticated = false;
    function checkGlobalDueAlarms() {
        if (isCheckingGlobalAlarms || isUserUnauthenticated) return;
        if (document.hidden) return;
        const path = (window.location.pathname || '').toLowerCase();
        if (path === '/login/' || path.startsWith('/auth/')) return;
        isCheckingGlobalAlarms = true;

        fetch('/api/reminders/active/')
            .then(function (r) {
                if (!r || !r.ok || r.redirected) {
                    if (r && (r.redirected || r.status === 401 || r.status === 403)) {
                        isUserUnauthenticated = true;
                        window.__abcdCachedReminders = [];
                        globalFiredAlarmIds.clear();
                        locallyStoppedAlarmIds.clear();
                        saveStoredAlarmSet('firedAlarmIds', globalFiredAlarmIds);
                        saveStoredAlarmSet('locallyStoppedAlarmIds', locallyStoppedAlarmIds);
                        if (navigator.serviceWorker && navigator.serviceWorker.controller) {
                            navigator.serviceWorker.controller.postMessage({ type: 'CLEAR_NATIVE_TASKS' });
                        }
                        sendNativeTwaMessage('abcdalarm://clear');
                    }
                    return null;
                }
                return r.json();
            })
            .then(function (data) {
                isCheckingGlobalAlarms = false;
                if (!data || !data.reminders || !Array.isArray(data.reminders)) return;

                window.__abcdCachedReminders = data.reminders;
                tickGlobalDueAlarmsInMemory();
                syncRemindersToNativeTwa(data.reminders);
            })
            .catch(function () {
                isCheckingGlobalAlarms = false;
            });
    }

    // High precision: Check memory every 1 second, fetch server every 60 seconds (or immediately on focus/visibility)
    setInterval(tickGlobalDueAlarmsInMemory, 1000);
    setInterval(checkGlobalDueAlarms, 60000);
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
            stopABCDAlarm({ persistStop: true });
        }
    });

    // Check URL parameters for instant tap-to-ring when opened via push notification
    function checkUrlAlarmTrigger() {
        try {
            const urlParams = new URLSearchParams(window.location.search);
            const isGuidyPage = window.location.pathname.includes('/guidy');
            if (urlParams.get('ring_alarm') === '1' && urlParams.get('task_id') && !isGuidyPage) {
                const alarmTitle = urlParams.get('alarm_title') || 'Scheduled Reminder';
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
                    // When native TWA alarm is already playing (service), show the modal
                    // but skip starting duplicate web audio. User taps STOP → abcdalarm://cancel.
                    var nativeHandling = isNativeAlarmTwaActive();
                    startABCDAlarm(alarmTitle, 'Your scheduled reminder is ringing now!', alarmTaskId, isAlarm, undefined, nativeHandling);
                }, 200);
            }
        } catch (e) {}
    }

    // Service Worker message listener for instant audio playback in open/minimized tabs
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.addEventListener('message', function (event) {
            if (!event.data) return;

            if (event.data.type === 'ABCD_ALARM_PUSH') {
                // STRICT CHECK: Never fire alarm for Guidy chat!
                if (event.data.isGuidy || (event.data.url && event.data.url.includes('/guidy'))) return;
                const titleStr = String(event.data.title || '');
                if (titleStr.includes('Guidy') || titleStr.includes('ABCD Asst')) return;

                startABCDAlarm(
                    event.data.title,
                    event.data.body,
                    event.data.taskId,
                    event.data.isAlarm,
                    event.data.sound
                );
            } else if (event.data.type === 'ABCD_GUIDY_MESSAGE') {
                // Subtle Guidy chat chime if user is on any other page
                const isGuidyPage = window.location.pathname.includes('/guidy');
                if (!isGuidyPage && window.playABCDSound) {
                    playABCDSound('receive', 0.85);
                }
            } else if (event.data.type === 'ABCD_NOTIFICATION_PUSH') {
                // General PWA Notification chime (Fee, Seat, Announcement, etc.)
                if (window.playABCDSound) {
                    playABCDSound('pwa', 0.85);
                }
            } else if (event.data.type === 'ABCD_ACCOUNT_DELETED') {
                cancelAllNativeAlarms();
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

    function cancelAllNativeAlarms() {
        try {
            window.__abcdCachedReminders = [];
            if (typeof globalFiredAlarmIds !== 'undefined' && globalFiredAlarmIds.clear) {
                globalFiredAlarmIds.clear();
                saveStoredAlarmSet('firedAlarmIds', globalFiredAlarmIds);
            }
            if (typeof locallyStoppedAlarmIds !== 'undefined' && locallyStoppedAlarmIds.clear) {
                locallyStoppedAlarmIds.clear();
                saveStoredAlarmSet('locallyStoppedAlarmIds', locallyStoppedAlarmIds);
            }
            const token = getTwaBridgeToken();
            postMessageToNative({ cmd: 'cancel_all', bridge_token: token });
            sendNativeTwaMessage('abcdalarm://cancel_all');
        } catch (e) {
            console.warn('[ABCD Sound] Error cancelling all native alarms:', e);
        }
    }

    // Auto-intercept logout clicks across all pages to clear native alarms before session ends
    if (typeof document !== 'undefined') {
        document.addEventListener('click', function (e) {
            try {
                const target = e.target && e.target.closest ? e.target.closest('a[href*="/logout/"], a[href$="/logout"], .nav-logout-btn, .sidebar-logout-btn, #confirmLogoutBtn, [data-action="logout"]') : null;
                if (target) {
                    cancelAllNativeAlarms();
                }
            } catch (err) {}
        }, true);
    }

    // Clean-up hook if page arrived via logout redirect (?logout_clean=1)
    if (typeof window !== 'undefined' && window.location && window.location.search && window.location.search.includes('logout_clean=1')) {
        cancelAllNativeAlarms();
        try {
            const url = new URL(window.location.href);
            url.searchParams.delete('logout_clean');
            window.history.replaceState({}, document.title, url.pathname + (url.search ? url.search : '') + url.hash);
        } catch (e) {}
    }

    // Expose global methods on window
    window.playABCDSound = playABCDSound;
    window.playDoneSound = function () { playABCDSound('done'); };
    window.playErrorSound = function () { playABCDSound('error'); };
    window.playButtonSound = function () { playABCDSound('button', 0.85); };
    window.startABCDAlarm = startABCDAlarm;
    window.stopABCDAlarm = stopABCDAlarm;
    window.isABCDAlarmPlaying = isAlarmOrLoudAlertPlaying;
    window.setABCDSoundEnabled = setSoundEnabled;
    window.isABCDSoundEnabled = isSoundEnabled;
    window.unlockABCDAudio = unlockAudio;
    window.checkGlobalDueAlarms = checkGlobalDueAlarms;
    window.syncABCDReminders = checkGlobalDueAlarms;
    window.isNativeAlarmTwaActive = isNativeAlarmTwaActive;
    window.getTwaBridgeToken = getTwaBridgeToken;
    window.cancelAllNativeAlarms = cancelAllNativeAlarms;

    // Alarm Setup Checklist, Native Bridge & Diagnostics (Phase 3 & 4)
    window.showAlarmSetupChecklist = showAlarmSetupChecklist;
    window.checkAlarmSetupStatus = checkAlarmSetupStatus;
    window.openNativeSettings = openNativeSettings;
    window.requestNativeNotifications = requestNativeNotifications;
    window.confirmAlarmSetupChecklist = confirmAlarmSetupChecklist;
    window.closeAlarmSetupChecklist = closeAlarmSetupChecklist;
    window.saveWithoutDeviceRingChecklist = saveWithoutDeviceRingChecklist;
    window.showNativeDebugPanel = showNativeDebugPanel;
    window.setAutostartConfirmed = setAutostartConfirmed;
    window.setFloatingConfirmed = setFloatingConfirmed;
    window.requestNativeStatus = requestNativeStatus;
    window.evaluateStatus = evaluateStatus;

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
