/**
 * static/js/abcd-sound.js - ABCD Audio Engine
 * Provides unique high-fidelity sound effects for PWA, ToDo alarms,
 * button clicks, form completions, errors, and Guidy messages.
 */

(function () {
    'use strict';

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
        'reminder': '/static/audio/alarm.mp3',
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
        isAudioUnlocked = true;

        try {
            const primer = audioPool['button'] || new Audio(SOUND_PATHS['button']);
            primer.volume = 0.01;
            const promise = primer.play();
            if (promise !== undefined) {
                promise.then(function () {
                    primer.pause();
                    primer.currentTime = 0;
                    primer.volume = 1.0;
                }).catch(function () {
                    isAudioUnlocked = false;
                });
            }
        } catch (e) {
            isAudioUnlocked = false;
        }

        ['click', 'touchstart', 'keydown'].forEach(function (evt) {
            document.removeEventListener(evt, unlockAudio, { capture: true });
        });
    }

    // Register interaction listeners to unlock
    ['click', 'touchstart', 'keydown'].forEach(function (evt) {
        document.addEventListener(evt, unlockAudio, { capture: true, once: true });
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
            // Create a dedicated audio object to allow overlapping sounds
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

    // Global click sound listener for interactive buttons
    document.addEventListener('click', function (e) {
        if (!isSoundEnabled()) return;

        const target = e.target;
        if (!target) return;

        // Skip elements explicitly marked with .no-sound
        if (target.closest('.no-sound, [data-no-sound="true"]')) return;

        // Trigger sound on buttons, action links, submit inputs
        const isClickable = target.closest('button, .btn, [role="button"], input[type="submit"], .action-btn, .nav-tab, .dropdown-item');
        if (isClickable) {
            const now = Date.now();
            // Debounce button clicks to avoid harsh machine-gun audio
            if (now - lastButtonSoundTime > 80) {
                lastButtonSoundTime = now;
                playABCDSound('button', 0.4);
            }
        }
    }, true);

    // Listen for custom global events
    window.addEventListener('abcd:sound', function (e) {
        if (e && e.detail && e.detail.sound) {
            playABCDSound(e.detail.sound, e.detail.volume || 1.0);
        }
    });

    // Expose global methods on window
    window.playABCDSound = playABCDSound;
    window.setABCDSoundEnabled = setSoundEnabled;
    window.isABCDSoundEnabled = isSoundEnabled;

    // Initialize preloading on DOM load or immediate
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAudioPool);
    } else {
        initAudioPool();
    }
})();
