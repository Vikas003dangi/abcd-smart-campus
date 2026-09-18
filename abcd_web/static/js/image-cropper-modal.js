/**
 * ============================================================================
 * ABCD SMART CAMPUS - CENTRALIZED MODULAR IMAGE CROPPER COMPONENT
 * ============================================================================
 * Features:
 * - Dynamic scrim/masking tracking real-time bounding box (NO static deformed overlays)
 * - High-contrast 2px border & rule-of-thirds grid lines
 * - Optional inner circular guideline for circular avatars (shape: 'circle')
 * - Full context-aware aspect ratio control: 1:1, 16:9, 4:3, or Freeform (NaN)
 * - Complete toolbar: Zoom In/Out, Rotate L/R, Flip Horizontal, Reset
 * - Form input payload synchronization via DataTransfer
 * - Full Light Theme & Dark Theme (body.dark-theme) support
 */

(function () {
    'use strict';

    let cropperInstance = null;
    let activeOptions = null;
    let currentFlipH = false;
    let isInitialized = false;

    // DOM Elements Cache
    let overlayEl = null;
    let modalEl = null;
    let titleEl = null;
    let badgeEl = null;
    let targetImgEl = null;
    let closeBtnEl = null;
    let doneBtnEl = null;
    let cancelBtnEl = null;

    /**
     * Build and inject the singleton modal DOM into document.body if not already present
     */
    function ensureModalDOM() {
        if (document.getElementById('abcdCropperModal')) {
            overlayEl = document.getElementById('abcdCropperOverlay');
            modalEl = document.getElementById('abcdCropperModal');
            titleEl = document.getElementById('abcdCropperTitle');
            badgeEl = document.getElementById('abcdCropperBadge');
            targetImgEl = document.getElementById('abcdCropperTargetImg');
            closeBtnEl = document.getElementById('abcdCropperCloseBtn');
            doneBtnEl = document.getElementById('abcdCropperDoneBtn');
            cancelBtnEl = document.getElementById('abcdCropperCancelBtn');
            return;
        }

        const overlay = document.createElement('div');
        overlay.id = 'abcdCropperOverlay';
        overlay.className = 'abcd-crop-overlay';

        const modal = document.createElement('div');
        modal.id = 'abcdCropperModal';
        modal.className = 'abcd-crop-modal';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');

        modal.innerHTML = `
            <div class="abcd-crop-header">
                <div class="abcd-crop-title-group">
                    <h3 id="abcdCropperTitle"><i class='bx bx-crop'></i> <span>Adjust Image</span></h3>
                    <span id="abcdCropperBadge" class="abcd-crop-ratio-badge">1:1</span>
                </div>
                <button type="button" class="abcd-crop-close-btn" id="abcdCropperCloseBtn" aria-label="Close">&times;</button>
            </div>
            <div class="abcd-crop-viewport">
                <img id="abcdCropperTargetImg" src="" alt="To Crop" crossorigin="anonymous">
            </div>
            <div class="abcd-crop-toolbar">
                <button type="button" class="abcd-crop-tool-btn" data-action="zoom-in" title="Zoom In"><i class='bx bx-zoom-in'></i> Zoom In</button>
                <button type="button" class="abcd-crop-tool-btn" data-action="zoom-out" title="Zoom Out"><i class='bx bx-zoom-out'></i> Zoom Out</button>
                <button type="button" class="abcd-crop-tool-btn" data-action="rotate-left" title="Rotate Left (-90°)"><i class='bx bx-undo'></i> Rotate Left</button>
                <button type="button" class="abcd-crop-tool-btn" data-action="rotate-right" title="Rotate Right (+90°)"><i class='bx bx-redo'></i> Rotate Right</button>
                <button type="button" class="abcd-crop-tool-btn" data-action="flip-h" title="Flip Horizontal"><i class='bx bx-reflect-vertical'></i> Flip</button>
                <button type="button" class="abcd-crop-tool-btn danger" data-action="reset" title="Reset Selection"><i class='bx bx-refresh'></i> Reset</button>
            </div>
            <div class="abcd-crop-footer">
                <button type="button" class="abcd-crop-pill-btn btn-done" id="abcdCropperDoneBtn">
                    <i class='bx bx-check'></i> Done
                </button>
                <button type="button" class="abcd-crop-pill-btn btn-cancel" id="abcdCropperCancelBtn">
                    Cancel
                </button>
            </div>
        `;

        document.body.appendChild(overlay);
        document.body.appendChild(modal);

        overlayEl = overlay;
        modalEl = modal;
        titleEl = modal.querySelector('#abcdCropperTitle span');
        badgeEl = modal.querySelector('#abcdCropperBadge');
        targetImgEl = modal.querySelector('#abcdCropperTargetImg');
        closeBtnEl = modal.querySelector('#abcdCropperCloseBtn');
        doneBtnEl = modal.querySelector('#abcdCropperDoneBtn');
        cancelBtnEl = modal.querySelector('#abcdCropperCancelBtn');

        closeBtnEl.addEventListener('click', () => ABCDImageCropper.close());
        cancelBtnEl.addEventListener('click', () => ABCDImageCropper.close());
        overlayEl.addEventListener('click', () => ABCDImageCropper.close());

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && modalEl && modalEl.classList.contains('is-active')) {
                ABCDImageCropper.close();
            }
        });

        modal.querySelectorAll('.abcd-crop-tool-btn').forEach(btn => {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                const action = this.getAttribute('data-action');
                if (!cropperInstance) return;

                switch (action) {
                    case 'zoom-in':
                        cropperInstance.zoom(0.1);
                        break;
                    case 'zoom-out':
                        cropperInstance.zoom(-0.1);
                        break;
                    case 'rotate-left':
                        cropperInstance.rotate(-90);
                        break;
                    case 'rotate-right':
                        cropperInstance.rotate(90);
                        break;
                    case 'flip-h':
                        currentFlipH = !currentFlipH;
                        cropperInstance.scaleX(currentFlipH ? -1 : 1);
                        break;
                    case 'reset':
                        cropperInstance.reset();
                        currentFlipH = false;
                        break;
                }
            });
        });

        doneBtnEl.addEventListener('click', handleDone);
        isInitialized = true;
    }

    /**
     * Handle the Done / Save action
     */
    function handleDone(e) {
        if (e) e.preventDefault();
        if (!cropperInstance || !activeOptions) {
            ABCDImageCropper.close();
            return;
        }

        const opts = activeOptions;
        const mimeType = opts.mimeType || 'image/jpeg';
        const quality = typeof opts.quality === 'number' ? opts.quality : 0.9;

        const originalText = doneBtnEl.innerHTML;
        doneBtnEl.disabled = true;
        doneBtnEl.innerHTML = "<i class='bx bx-loader-alt bx-spin'></i> Processing...";

        try {
            const canvasOptions = {
                fillColor: '#ffffff',
                imageSmoothingEnabled: true,
                imageSmoothingQuality: 'high'
            };

            if (opts.aspectRatio && !isNaN(opts.aspectRatio)) {
                canvasOptions.width = opts.outputWidth || 600;
                canvasOptions.height = opts.outputHeight || 600;
            } else {
                if (opts.outputWidth) canvasOptions.maxWidth = opts.outputWidth;
                if (opts.outputHeight) canvasOptions.maxHeight = opts.outputHeight;
            }

            const canvas = cropperInstance.getCroppedCanvas(canvasOptions);

            if (!canvas) {
                throw new Error("Unable to extract cropped canvas");
            }

            canvas.toBlob((blob) => {
                doneBtnEl.disabled = false;
                doneBtnEl.innerHTML = originalText;

                if (!blob) {
                    ABCDImageCropper.close();
                    return;
                }

                const filename = opts.fileName || 'profile_photo.jpg';
                const file = new File([blob], filename, { type: mimeType, lastModified: Date.now() });
                const dataUrl = canvas.toDataURL(mimeType, quality);

                const result = {
                    blob: blob,
                    file: file,
                    dataUrl: dataUrl,
                    canvas: canvas,
                    width: width,
                    height: height
                };

                if (typeof opts.onDone === 'function') {
                    opts.onDone(result);
                }

                ABCDImageCropper.close();
            }, mimeType, quality);

        } catch (err) {
            console.error("Cropper processing error:", err);
            doneBtnEl.disabled = false;
            doneBtnEl.innerHTML = originalText;
            ABCDImageCropper.close();
        }
    }

    /**
     * Public API
     */
    const ABCDImageCropper = {
        /**
         * Open the cropper modal for a given image source or File
         */
        open: function (options) {
            ensureModalDOM();

            activeOptions = Object.assign({
                title: 'Adjust Image',
                aspectRatio: 1, // 1 (1:1), 16/9, 4/3, or NaN / null for freeform
                shape: 'circle', // 'circle' or 'rect'
                outputWidth: 600,
                outputHeight: 600,
                mimeType: 'image/jpeg',
                quality: 0.9,
                fileName: 'image.jpg',
                onDone: null,
                onCancel: null
            }, options);

            // Configure Title and Aspect Ratio Badge
            if (titleEl) {
                titleEl.textContent = activeOptions.title;
            }
            if (badgeEl) {
                let badgeText = '1:1';
                if (!activeOptions.aspectRatio || isNaN(activeOptions.aspectRatio)) {
                    badgeText = 'Free';
                } else if (Math.abs(activeOptions.aspectRatio - (16 / 9)) < 0.01) {
                    badgeText = '16:9';
                } else if (Math.abs(activeOptions.aspectRatio - (4 / 3)) < 0.01) {
                    badgeText = '4:3';
                } else if (Math.abs(activeOptions.aspectRatio - 1) < 0.01) {
                    badgeText = '1:1';
                } else {
                    badgeText = 'Custom';
                }
                badgeEl.textContent = badgeText;
            }

            // Cleanup previous instance
            if (cropperInstance) {
                cropperInstance.destroy();
                cropperInstance = null;
            }
            currentFlipH = false;

            // Resolve Image Source (File, Blob, or URL)
            const resolveSource = (callback) => {
                const imgSource = activeOptions.image || activeOptions.file;
                if (!imgSource) {
                    console.error("ABCDImageCropper: No image source provided.");
                    return;
                }

                if (imgSource instanceof File || imgSource instanceof Blob) {
                    activeOptions.fileName = imgSource.name || activeOptions.fileName;
                    const reader = new FileReader();
                    reader.onload = (e) => callback(e.target.result);
                    reader.readAsDataURL(imgSource);
                } else if (typeof imgSource === 'string') {
                    callback(imgSource);
                } else if (imgSource.src) {
                    callback(imgSource.src);
                }
            };

            resolveSource((src) => {
                targetImgEl.src = src;

                // Show Modal
                overlayEl.classList.add('is-active');
                modalEl.classList.add('is-active');

                // Check Cropper.js availability
                if (typeof Cropper === 'undefined') {
                    console.error("Cropper.js is not loaded! Make sure cropper.min.js is included.");
                    return;
                }

                let hasInitialized = false;
                const launchCropper = () => {
                    if (hasInitialized) return;
                    hasInitialized = true;

                    setTimeout(() => {
                        if (!modalEl || !modalEl.classList.contains('is-active')) return;

                        const isCircle = activeOptions.shape === 'circle' && (activeOptions.aspectRatio === 1 || !activeOptions.aspectRatio);
                        const ratio = (!activeOptions.aspectRatio || isNaN(activeOptions.aspectRatio)) ? NaN : activeOptions.aspectRatio;

                        cropperInstance = new Cropper(targetImgEl, {
                            aspectRatio: ratio,
                            viewMode: 1, // Keep inside canvas
                            dragMode: 'move',
                            autoCropArea: 0.85,
                            responsive: true,
                            restore: false,
                            guides: true,
                            center: true,
                            highlight: false,
                            cropBoxMovable: true,
                            cropBoxResizable: true,
                            toggleDragModeOnDblclick: false,
                            checkCrossOrigin: false,
                            ready: function () {
                                const viewBox = modalEl.querySelector('.cropper-view-box');
                                if (viewBox) {
                                    if (isCircle) {
                                        viewBox.classList.add('is-circle');
                                    } else {
                                        viewBox.classList.remove('is-circle');
                                    }
                                }
                            }
                        });
                    }, 80);
                };

                targetImgEl.onload = launchCropper;
                if (targetImgEl.complete) {
                    launchCropper();
                }
            });
        },

        /**
         * Close the cropper modal and cleanup
         */
        close: function () {
            if (cropperInstance) {
                cropperInstance.destroy();
                cropperInstance = null;
            }
            currentFlipH = false;

            if (targetImgEl) targetImgEl.src = '';
            if (modalEl) modalEl.classList.remove('is-active');
            if (overlayEl) overlayEl.classList.remove('is-active');

            if (activeOptions && typeof activeOptions.onCancel === 'function') {
                activeOptions.onCancel();
            }
            activeOptions = null;
        },

        /**
         * Declaratively attach cropper functionality to a file input and preview container
         */
        attach: function (config) {
            const input = typeof config.input === 'string' ? document.querySelector(config.input) : config.input;
            if (!input) return;

            const preview = typeof config.preview === 'string' ? document.querySelector(config.preview) : config.preview;
            const placeholder = typeof config.placeholder === 'string' ? document.querySelector(config.placeholder) : config.placeholder;
            const statusText = typeof config.statusText === 'string' ? document.querySelector(config.statusText) : config.statusText;
            const initialSrc = preview ? (preview.getAttribute('data-initial-src') || preview.src) : '';

            const maxSizeMB = config.maxSizeMB || 2;
            const allowedTypes = config.allowedTypes || ['image/jpeg', 'image/png', 'image/webp'];

            // File selection listener
            input.addEventListener('change', function () {
                const file = this.files && this.files[0];
                if (!file) return;

                // 1. Format validation
                const fileName = (file.name || '').toLowerCase();
                const validExt = /\.(jpe?g|png|webp)$/i.test(fileName);
                const validType = allowedTypes.includes(file.type) || validExt;

                if (!validType) {
                    const msg = 'Please choose a valid image format (JPG, PNG, or WEBP).';
                    if (window.CustomPopup && CustomPopup.alert) {
                        CustomPopup.alert(msg, 'Invalid Photo Format');
                    } else if (window.showStyledPopup) {
                        window.showStyledPopup({ title: 'Invalid Photo Format', message: msg, type: 'warning' });
                    } else {
                        alert(msg);
                    }
                    input.value = '';
                    return;
                }

                // 2. Size validation
                if (file.size > maxSizeMB * 1024 * 1024) {
                    const currentMB = (file.size / (1024 * 1024)).toFixed(2);
                    const msg = `Selected image is ${currentMB} MB, exceeding the ${maxSizeMB}MB limit. Please compress it before uploading.`;
                    if (window.CustomPopup && CustomPopup.alert) {
                        CustomPopup.alert(msg, 'Photo Too Large');
                    } else if (window.showStyledPopup) {
                        window.showStyledPopup({ title: 'Photo Too Large', message: msg, type: 'warning' });
                    } else {
                        alert(msg);
                    }
                    input.value = '';
                    return;
                }

                // 3. Launch Cropper
                ABCDImageCropper.open({
                    image: file,
                    title: config.title || 'Adjust Profile Photo',
                    aspectRatio: typeof config.aspectRatio === 'number' ? config.aspectRatio : 1,
                    shape: config.shape || (config.aspectRatio === 1 ? 'circle' : 'rect'),
                    outputWidth: config.outputWidth || 600,
                    outputHeight: config.outputHeight || 600,
                    mimeType: config.mimeType || 'image/jpeg',
                    quality: config.quality || 0.9,
                    fileName: file.name,
                    onDone: function (result) {
                        // Synchronize File input using DataTransfer
                        try {
                            const dt = new DataTransfer();
                            dt.items.add(result.file);
                            input.files = dt.files;
                        } catch (e) {
                            console.warn("DataTransfer assignment not supported:", e);
                        }

                        // Update Preview
                        if (preview) {
                            preview.src = result.dataUrl;
                            preview.style.display = 'block';
                        }
                        if (placeholder) {
                            placeholder.style.display = 'none';
                        }
                        if (statusText) {
                            statusText.innerHTML = `<span style="color: #4f46e5; font-weight: 600;">✓ Photo adjusted & ready</span>`;
                        }

                        if (typeof config.onDone === 'function') {
                            config.onDone(result);
                        }
                    },
                    onCancel: function () {
                        // If no file was saved and input was just selected, reset if no initial src
                        if (!input.files || input.files.length === 0) {
                            if (preview && initialSrc) {
                                preview.src = initialSrc;
                                preview.style.display = 'block';
                                if (placeholder) placeholder.style.display = 'none';
                            }
                        }
                        if (typeof config.onCancel === 'function') {
                            config.onCancel();
                        }
                    }
                });
            });

            // Allow clicking preview to re-adjust photo
            if (preview && config.allowPreviewClick !== false) {
                const clickableParent = preview.closest('[data-crop-trigger]') || preview.parentElement;
                if (clickableParent) {
                    clickableParent.style.cursor = 'pointer';
                    clickableParent.addEventListener('click', function (e) {
                        // Don't trigger if click was directly on an <input type="file"> or <label>
                        if (e.target.tagName === 'INPUT' || e.target.closest('label[for="' + input.id + '"]')) {
                            return;
                        }
                        if (preview.src && preview.style.display !== 'none' && !preview.src.endsWith('/')) {
                            ABCDImageCropper.open({
                                image: preview.src,
                                title: config.title || 'Adjust Profile Photo',
                                aspectRatio: typeof config.aspectRatio === 'number' ? config.aspectRatio : 1,
                                shape: config.shape || (config.aspectRatio === 1 ? 'circle' : 'rect'),
                                outputWidth: config.outputWidth || 600,
                                outputHeight: config.outputHeight || 600,
                                onDone: function (result) {
                                    try {
                                        const dt = new DataTransfer();
                                        dt.items.add(result.file);
                                        input.files = dt.files;
                                    } catch (e) { }

                                    preview.src = result.dataUrl;
                                    preview.style.display = 'block';
                                    if (placeholder) placeholder.style.display = 'none';

                                    if (typeof config.onDone === 'function') {
                                        config.onDone(result);
                                    }
                                }
                            });
                        } else {
                            input.click();
                        }
                    });
                }
            }
        }
    };

    window.ABCDImageCropper = ABCDImageCropper;
})();
