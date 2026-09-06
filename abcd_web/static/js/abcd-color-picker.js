/**
 * ABCD Universal Custom Color Picker
 * Supports fluid live dragging on both desktop (mouse) and mobile/tablet (touch).
 * Features:
 * - Real-time draggable circle cursor on Saturation/Value canvas
 * - Real-time draggable white thumb on the rainbow Hue slider
 * - Pointer capture & touch-action: none for seamless multi-touch and out-of-bounds drag
 * - Hex input syncing & color preview
 * - Dark & light theme compatibility
 */

(function() {
  function rgbToHex(rgbStr) {
    if (!rgbStr) return null;
    if (rgbStr.startsWith('#')) return rgbStr;
    const match = rgbStr.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    if (!match) return null;
    const toHex = (n) => parseInt(n, 10).toString(16).padStart(2, '0');
    return '#' + toHex(match[1]) + toHex(match[2]) + toHex(match[3]);
  }

  class CustomColorPicker {
    constructor(container, onColorChange, onDone) {
      this.container = container;
      this.onColorChange = onColorChange;
      this.onDone = onDone;

      this.canvas = container.querySelector('.cp-canvas-sv');
      this.ctx = this.canvas.getContext('2d');
      this.svContainer = container.querySelector('.cp-sv-container') || this.canvas.parentElement;
      this.svHandle = container.querySelector('.cp-sv-handle');

      // Create svHandle if not already in markup
      if (!this.svHandle) {
        this.svHandle = document.createElement('div');
        this.svHandle.className = 'cp-sv-handle';
        this.svHandle.style.cssText = 'position: absolute; top: 0; left: 0; width: 14px; height: 14px; border-radius: 50%; border: 2px solid #fff; box-shadow: 0 0 2px rgba(0,0,0,0.9), inset 0 0 2px rgba(0,0,0,0.5); transform: translate(-50%, -50%); pointer-events: none; box-sizing: border-box; z-index: 2;';
        if (this.svContainer) {
          if (getComputedStyle(this.svContainer).position === 'static') {
            this.svContainer.style.position = 'relative';
          }
          this.svContainer.appendChild(this.svHandle);
        }
      }

      this.hueContainer = container.querySelector('.cp-hue-container');
      this.hueHandle = container.querySelector('.cp-hue-handle');
      this.preview = container.querySelector('.cp-color-preview');
      this.hexInput = container.querySelector('.cp-color-hex');
      this.doneBtn = container.querySelector('.cp-done-btn');

      this.hue = 0; // 0 - 360
      this.s = 1;   // 0 - 1
      this.v = 1;   // 0 - 1

      this.isDraggingSV = false;
      this.isDraggingHue = false;

      this.initEvents();
      this.drawSV();
      this.updateHandlePositions();
    }

    initEvents() {
      const getSVCoords = (clientX, clientY) => {
        const target = this.svContainer || this.canvas;
        const rect = target.getBoundingClientRect();
        let x = (clientX - rect.left) / rect.width;
        let y = (clientY - rect.top) / rect.height;
        x = Math.max(0, Math.min(1, x));
        y = Math.max(0, Math.min(1, y));
        return { x, y };
      };

      const handleSVMove = (clientX, clientY) => {
        const { x, y } = getSVCoords(clientX, clientY);
        this.s = x;
        this.v = 1 - y;
        this.updateHandlePositions();
        this.updateColor();
      };

      const getHueCoord = (clientX) => {
        const rect = this.hueContainer.getBoundingClientRect();
        let x = (clientX - rect.left) / rect.width;
        x = Math.max(0, Math.min(1, x));
        return x;
      };

      const handleHueMove = (clientX) => {
        const x = getHueCoord(clientX);
        this.hue = x * 360;
        this.updateHandlePositions();
        this.drawSV();
        this.updateColor();
      };

      // ── Saturation / Value Canvas Pointer & Touch Handling ──
      const svTarget = this.svContainer || this.canvas;
      svTarget.style.touchAction = 'none';

      svTarget.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.isDraggingSV = true;
        try {
          svTarget.setPointerCapture(e.pointerId);
        } catch (err) {}
        handleSVMove(e.clientX, e.clientY);
      });

      svTarget.addEventListener('pointermove', (e) => {
        if (!this.isDraggingSV) return;
        e.preventDefault();
        handleSVMove(e.clientX, e.clientY);
      });

      const stopSV = (e) => {
        if (this.isDraggingSV) {
          this.isDraggingSV = false;
          try {
            if (e && e.pointerId && svTarget.hasPointerCapture(e.pointerId)) {
              svTarget.releasePointerCapture(e.pointerId);
            }
          } catch (err) {}
        }
      };
      svTarget.addEventListener('pointerup', stopSV);
      svTarget.addEventListener('pointercancel', stopSV);

      // Fallback touch events for older mobile environments
      svTarget.addEventListener('touchstart', (e) => {
        if (e.touches && e.touches.length > 0) {
          e.preventDefault();
          this.isDraggingSV = true;
          handleSVMove(e.touches[0].clientX, e.touches[0].clientY);
        }
      }, { passive: false });

      svTarget.addEventListener('touchmove', (e) => {
        if (this.isDraggingSV && e.touches && e.touches.length > 0) {
          e.preventDefault();
          handleSVMove(e.touches[0].clientX, e.touches[0].clientY);
        }
      }, { passive: false });

      svTarget.addEventListener('touchend', () => { this.isDraggingSV = false; }, { passive: false });

      // ── Hue Slider Pointer & Touch Handling ──
      this.hueContainer.style.touchAction = 'none';
      if (this.hueHandle) this.hueHandle.style.touchAction = 'none';

      this.hueContainer.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.isDraggingHue = true;
        try {
          this.hueContainer.setPointerCapture(e.pointerId);
        } catch (err) {}
        handleHueMove(e.clientX);
      });

      this.hueContainer.addEventListener('pointermove', (e) => {
        if (!this.isDraggingHue) return;
        e.preventDefault();
        handleHueMove(e.clientX);
      });

      const stopHue = (e) => {
        if (this.isDraggingHue) {
          this.isDraggingHue = false;
          try {
            if (e && e.pointerId && this.hueContainer.hasPointerCapture(e.pointerId)) {
              this.hueContainer.releasePointerCapture(e.pointerId);
            }
          } catch (err) {}
        }
      };
      this.hueContainer.addEventListener('pointerup', stopHue);
      this.hueContainer.addEventListener('pointercancel', stopHue);

      // Fallback touch events for hue slider
      this.hueContainer.addEventListener('touchstart', (e) => {
        if (e.touches && e.touches.length > 0) {
          e.preventDefault();
          this.isDraggingHue = true;
          handleHueMove(e.touches[0].clientX);
        }
      }, { passive: false });

      this.hueContainer.addEventListener('touchmove', (e) => {
        if (this.isDraggingHue && e.touches && e.touches.length > 0) {
          e.preventDefault();
          handleHueMove(e.touches[0].clientX);
        }
      }, { passive: false });

      this.hueContainer.addEventListener('touchend', () => { this.isDraggingHue = false; }, { passive: false });

      // Window safety listeners to catch releases outside the elements
      window.addEventListener('pointermove', (e) => {
        if (this.isDraggingSV) {
          e.preventDefault();
          handleSVMove(e.clientX, e.clientY);
        } else if (this.isDraggingHue) {
          e.preventDefault();
          handleHueMove(e.clientX);
        }
      });

      window.addEventListener('pointerup', (e) => {
        stopSV(e);
        stopHue(e);
      });

      window.addEventListener('pointercancel', (e) => {
        stopSV(e);
        stopHue(e);
      });

      // ── Hex Input ──
      if (this.hexInput) {
        const onHexUpdate = () => {
          let val = this.hexInput.value.trim();
          if (!val.startsWith('#')) val = '#' + val;
          if (/^#[0-9A-Fa-f]{6}$/i.test(val)) {
            this.setColorFromHex(val);
          }
        };
        this.hexInput.addEventListener('input', onHexUpdate);
        this.hexInput.addEventListener('change', onHexUpdate);
      }

      // ── Done Button ──
      if (this.doneBtn) {
        this.doneBtn.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          if (this.onDone) this.onDone(this.getHexColor());
        });
      }
    }

    drawSV() {
      const width = this.canvas.width;
      const height = this.canvas.height;

      // Base Hue
      this.ctx.fillStyle = `hsl(${this.hue}, 100%, 50%)`;
      this.ctx.fillRect(0, 0, width, height);

      // White horizontal gradient (Saturation)
      const whiteGrad = this.ctx.createLinearGradient(0, 0, width, 0);
      whiteGrad.addColorStop(0, '#ffffff');
      whiteGrad.addColorStop(1, 'rgba(255,255,255,0)');
      this.ctx.fillStyle = whiteGrad;
      this.ctx.fillRect(0, 0, width, height);

      // Black vertical gradient (Value / Brightness)
      const blackGrad = this.ctx.createLinearGradient(0, height, 0, 0);
      blackGrad.addColorStop(0, '#000000');
      blackGrad.addColorStop(1, 'rgba(0,0,0,0)');
      this.ctx.fillStyle = blackGrad;
      this.ctx.fillRect(0, 0, width, height);
    }

    updateHandlePositions() {
      if (this.svHandle) {
        this.svHandle.style.left = (this.s * 100) + '%';
        this.svHandle.style.top = ((1 - this.v) * 100) + '%';
      }
      if (this.hueHandle) {
        const huePercent = (this.hue / 360) * 100;
        this.hueHandle.style.left = huePercent + '%';
      }
    }

    updateColor() {
      const hex = this.getHexColor();
      if (this.preview) this.preview.style.background = hex;
      if (this.hexInput) this.hexInput.value = hex.toUpperCase();
      if (this.onColorChange) this.onColorChange(hex);
    }

    setColorFromHex(hex) {
      if (!hex || typeof hex !== 'string') return;
      hex = hex.trim();
      if (!hex.startsWith('#')) hex = '#' + hex;
      if (!/^#[0-9A-Fa-f]{6}$/.test(hex)) return;

      const r = parseInt(hex.slice(1, 3), 16) / 255;
      const g = parseInt(hex.slice(3, 5), 16) / 255;
      const b = parseInt(hex.slice(5, 7), 16) / 255;

      const max = Math.max(r, g, b), min = Math.min(r, g, b);
      let h, s, v = max;
      const d = max - min;
      s = max === 0 ? 0 : d / max;

      if (max === min) {
        h = 0;
      } else {
        switch (max) {
          case r: h = (g - b) / d + (g < b ? 6 : 0); break;
          case g: h = (b - r) / d + 2; break;
          case b: h = (r - g) / d + 4; break;
        }
        h /= 6;
      }

      this.hue = h * 360;
      this.s = s;
      this.v = v;

      this.updateHandlePositions();
      this.drawSV();
      if (this.preview) this.preview.style.background = hex;
      if (this.hexInput) this.hexInput.value = hex.toUpperCase();
    }

    getHexColor() {
      const h = this.hue / 360;
      const s = this.s;
      const v = this.v;
      let r, g, b;

      const i = Math.floor(h * 6);
      const f = h * 6 - i;
      const p = v * (1 - s);
      const q = v * (1 - f * s);
      const t = v * (1 - (1 - f) * s);

      switch (i % 6) {
        case 0: r = v; g = t; b = p; break;
        case 1: r = q; g = v; b = p; break;
        case 2: r = p; g = v; b = t; break;
        case 3: r = p; g = q; b = v; break;
        case 4: r = t; g = p; b = v; break;
        case 5: r = v; g = p; b = q; break;
      }

      const toHex = x => {
        const val = Math.round(x * 255).toString(16);
        return val.length === 1 ? '0' + val : val;
      };
      return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
    }
  }

  let customColorPickerInstance = null;

  function ensureColorPickerBoardDOM() {
    let board = document.getElementById('gCustomColorPickerBoard');
    if (!board) {
      board = document.createElement('div');
      board.id = 'gCustomColorPickerBoard';
      board.className = 'custom-color-picker-board';
      board.style.cssText = 'display: none; position: fixed; z-index: 100001; background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; padding: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.18); width: 228px; user-select: none; -webkit-user-select: none; box-sizing: border-box; touch-action: none;';
      board.innerHTML = `
        <div class="cp-sv-container" style="position: relative; width: 100%; height: 120px; border-radius: 8px; overflow: hidden; cursor: crosshair; touch-action: none; user-select: none; -webkit-user-select: none; line-height: 0; margin-bottom: 10px;">
          <canvas class="cp-canvas-sv" width="204" height="120" style="display: block; width: 100%; height: 100%; border-radius: 8px;"></canvas>
          <div class="cp-sv-handle" style="position: absolute; top: 0; left: 0; width: 14px; height: 14px; border-radius: 50%; border: 2px solid #fff; box-shadow: 0 0 2px rgba(0,0,0,0.9), inset 0 0 2px rgba(0,0,0,0.5); transform: translate(-50%, -50%); pointer-events: none; box-sizing: border-box; z-index: 2;"></div>
        </div>
        <div class="cp-hue-container" style="position: relative; height: 14px; border-radius: 7px; background: linear-gradient(to right, #ff0000 0%, #ffff00 17%, #00ff00 33%, #00ffff 50%, #0000ff 67%, #ff00ff 83%, #ff0000 100%); margin-bottom: 12px; cursor: pointer; touch-action: none; user-select: none; -webkit-user-select: none; box-sizing: border-box;">
          <div class="cp-hue-handle" style="position: absolute; top: -1px; left: 0; width: 16px; height: 16px; border-radius: 50%; background: #fff; border: 2.5px solid #7b61ff; cursor: grab; box-shadow: 0 1px 4px rgba(0,0,0,0.35); transform: translateX(-50%); box-sizing: border-box; touch-action: none;"></div>
        </div>
        <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; box-sizing: border-box;">
          <div class="cp-color-preview" style="width: 28px; height: 28px; border-radius: 50%; border: 1.5px solid rgba(0,0,0,0.15); box-shadow: inset 0 0 3px rgba(0,0,0,0.1); background: red; flex-shrink: 0; box-sizing: border-box;"></div>
          <input class="cp-color-hex" type="text" value="#FF0000" maxlength="7" style="width: 76px; border: 1px solid #cbd5e1; border-radius: 6px; padding: 4px; font-size: 0.8rem; text-align: center; text-transform: uppercase; font-family: monospace; font-weight: 600; box-sizing: border-box; background: #fff; color: #1e293b;">
          <button class="cp-done-btn" type="button" style="background: #7b61ff; color: #fff; border: none; padding: 6px 14px; border-radius: 8px; font-size: 0.82rem; font-weight: 600; cursor: pointer; transition: background 0.15s; box-sizing: border-box;">Done</button>
        </div>
      `;
      document.body.appendChild(board);
    } else {
      // Ensure svContainer & svHandle exist in existing board markup
      let svContainer = board.querySelector('.cp-sv-container');
      let canvas = board.querySelector('.cp-canvas-sv');
      if (!svContainer && canvas) {
        svContainer = document.createElement('div');
        svContainer.className = 'cp-sv-container';
        svContainer.style.cssText = 'position: relative; width: 100%; height: 120px; border-radius: 8px; overflow: hidden; cursor: crosshair; touch-action: none; user-select: none; -webkit-user-select: none; line-height: 0; margin-bottom: 10px;';
        canvas.parentNode.insertBefore(svContainer, canvas);
        svContainer.appendChild(canvas);
        canvas.style.display = 'block';
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        canvas.style.borderRadius = '8px';
      }
      if (svContainer && !svContainer.querySelector('.cp-sv-handle')) {
        const svHandle = document.createElement('div');
        svHandle.className = 'cp-sv-handle';
        svHandle.style.cssText = 'position: absolute; top: 0; left: 0; width: 14px; height: 14px; border-radius: 50%; border: 2px solid #fff; box-shadow: 0 0 2px rgba(0,0,0,0.9), inset 0 0 2px rgba(0,0,0,0.5); transform: translate(-50%, -50%); pointer-events: none; box-sizing: border-box; z-index: 2;';
        svContainer.appendChild(svHandle);
      }

      // Ensure proper Hue gradient orientation
      const hueContainer = board.querySelector('.cp-hue-container');
      if (hueContainer) {
        hueContainer.style.background = 'linear-gradient(to right, #ff0000 0%, #ffff00 17%, #00ff00 33%, #00ffff 50%, #0000ff 67%, #ff00ff 83%, #ff0000 100%)';
        hueContainer.style.touchAction = 'none';
        const hueHandle = hueContainer.querySelector('.cp-hue-handle');
        if (hueHandle) hueHandle.style.touchAction = 'none';
      }
    }
    return board;
  }

  function openCustomColorPickerBoard(e, buttonEl, onSelectCallback, initialColor) {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }

    const board = ensureColorPickerBoardDOM();
    if (!board) return;

    if (board.style.display === 'block' && board.dataset.targetId === buttonEl.id) {
      board.style.display = 'none';
      return;
    }

    board.dataset.targetId = buttonEl.id || ('picker_btn_' + Math.random().toString(36).substr(2, 6));
    if (board.parentNode !== document.body) {
      document.body.appendChild(board);
    }

    // Adapt to dark theme
    const isDark = document.body.classList.contains('dark-theme');
    board.style.background = isDark ? '#191033' : '#ffffff';
    board.style.borderColor = isDark ? '#36245c' : '#e2e8f0';
    board.style.color = isDark ? '#f8fafc' : '#1e293b';
    const hexInput = board.querySelector('.cp-color-hex');
    if (hexInput) {
      hexInput.style.background = isDark ? '#120a24' : '#ffffff';
      hexInput.style.borderColor = isDark ? '#3d2b6b' : '#cbd5e1';
      hexInput.style.color = isDark ? '#f8fafc' : '#000000';
    }

    const rect = buttonEl.getBoundingClientRect();
    const shell = document.querySelector('.todo-hub-container') || document.getElementById('gShell') || document.body;
    const shellRect = shell.getBoundingClientRect();

    const boardWidth = 228;
    const boardHeight = 230;
    const margin = 8;

    // 1. Vertical positioning
    let topVal;
    if (rect.top - shellRect.top >= boardHeight + margin) {
      topVal = rect.top - boardHeight - margin; // above
    } else if (shellRect.bottom - rect.bottom >= boardHeight + margin) {
      topVal = rect.bottom + margin;            // below
    } else {
      topVal = Math.max(shellRect.top + margin, shellRect.bottom - boardHeight - margin);
    }

    // 2. Horizontal positioning
    let leftVal = rect.left + rect.width / 2 - boardWidth / 2;
    leftVal = Math.max(shellRect.left + margin, Math.min(shellRect.right - boardWidth - margin, leftVal));

    // Viewport bounds clamp
    topVal = Math.max(margin, Math.min(window.innerHeight - boardHeight - margin, topVal));
    leftVal = Math.max(margin, Math.min(window.innerWidth - boardWidth - margin, leftVal));

    board.style.top = topVal + 'px';
    board.style.left = leftVal + 'px';
    board.style.display = 'block';

    if (!customColorPickerInstance) {
      customColorPickerInstance = new CustomColorPicker(
        board,
        (color) => {},
        (color) => {
          buttonEl.dataset.currentColor = color;
          if (typeof onSelectCallback === 'function') onSelectCallback(color);
          board.style.display = 'none';
        }
      );
    } else {
      customColorPickerInstance.onDone = (color) => {
        buttonEl.dataset.currentColor = color;
        if (typeof onSelectCallback === 'function') onSelectCallback(color);
        board.style.display = 'none';
      };
    }

    // Determine initial color
    let startColor = initialColor;
    if (!startColor) {
      if (buttonEl.dataset.currentColor) {
        startColor = buttonEl.dataset.currentColor;
      } else if (buttonEl.dataset.color) {
        startColor = buttonEl.dataset.color;
      } else if (buttonEl.style.backgroundColor && buttonEl.style.backgroundColor !== 'transparent') {
        startColor = rgbToHex(buttonEl.style.backgroundColor) || buttonEl.style.backgroundColor;
      }
    }
    if (!startColor || !/^#[0-9A-Fa-f]{6}$/.test(startColor)) {
      startColor = '#EF4444';
    }

    customColorPickerInstance.setColorFromHex(startColor);
  }

  // Outside click / tap listener to close board
  document.addEventListener('pointerdown', (e) => {
    const board = document.getElementById('gCustomColorPickerBoard');
    if (board && board.style.display === 'block') {
      if (!board.contains(e.target) && !e.target.closest('.custom-picker-btn')) {
        board.style.display = 'none';
      }
    }
  });

  // Export to window
  window.CustomColorPicker = CustomColorPicker;
  window.openCustomColorPickerBoard = openCustomColorPickerBoard;
  window.ensureColorPickerBoardDOM = ensureColorPickerBoardDOM;
})();
