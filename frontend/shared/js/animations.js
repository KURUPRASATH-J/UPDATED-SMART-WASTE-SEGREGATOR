/**
 * animations.js - JavaScript Animation Helpers
 * Smart Waste Segregator
 * 
 * Provides animation utilities: counters, scroll reveals, 
 * ripple effects, confetti, progress bars, typewriter
 */

/**
 * Animate a number counting from one value to another
 * @param {HTMLElement} element - The element to update
 * @param {number} from - Start value
 * @param {number} to - End value
 * @param {number} duration - Animation duration in ms
 * @param {string} suffix - Optional suffix (e.g., '%', 'kg')
 */
export function animateCounter(element, from, to, duration = 1500, suffix = '') {
  if (!element) return;
  const startTime = performance.now();
  const diff = to - from;

  function update(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    // Ease out cubic
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = Math.round(from + diff * eased);
    element.textContent = current.toLocaleString() + suffix;
    if (progress < 1) {
      requestAnimationFrame(update);
    }
  }
  requestAnimationFrame(update);
}

/**
 * Initialize scroll reveal using IntersectionObserver.
 * Elements with class "reveal" get "visible" added when in viewport.
 */
export function initScrollReveal() {
  const revealElements = document.querySelectorAll('.reveal');
  if (!revealElements.length) return;

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.15, rootMargin: '0px 0px -50px 0px' });

  revealElements.forEach(el => observer.observe(el));
}

/**
 * Add a Material-Design-style ripple effect on click
 * @param {HTMLElement} element - Target element
 */
export function addRippleEffect(element) {
  if (!element) return;
  element.style.position = element.style.position || 'relative';
  element.style.overflow = 'hidden';

  element.addEventListener('click', function (e) {
    const rect = this.getBoundingClientRect();
    const ripple = document.createElement('span');
    const size = Math.max(rect.width, rect.height);
    ripple.style.cssText = `
      position:absolute;width:${size}px;height:${size}px;
      border-radius:50%;background:rgba(255,255,255,0.45);
      left:${e.clientX - rect.left - size / 2}px;
      top:${e.clientY - rect.top - size / 2}px;
      transform:scale(0);animation:rippleAnim 0.6s linear;
      pointer-events:none;
    `;
    this.appendChild(ripple);
    ripple.addEventListener('animationend', () => ripple.remove());
  });
}

/**
 * Show a canvas-based confetti burst
 * @param {object} options
 * @param {number} options.particleCount - Number of particles (default 80)
 * @param {number} options.duration - Duration in ms (default 2500)
 * @param {string[]} options.colors - Array of hex colors
 */
export function showConfetti({ particleCount = 80, duration = 2500, colors } = {}) {
  const defaultColors = ['#00d4ff', '#00ff99', '#ff6b35', '#9932ff', '#ffaa00', '#ff4444'];
  const palette = colors || defaultColors;

  const canvas = document.createElement('canvas');
  canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:10010;';
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  document.body.appendChild(canvas);
  const ctx = canvas.getContext('2d');

  const particles = Array.from({ length: particleCount }, () => ({
    x: canvas.width / 2 + (Math.random() - 0.5) * 200,
    y: canvas.height / 2,
    vx: (Math.random() - 0.5) * 15,
    vy: Math.random() * -18 - 4,
    color: palette[Math.floor(Math.random() * palette.length)],
    size: Math.random() * 8 + 3,
    rotation: Math.random() * 360,
    rotSpeed: (Math.random() - 0.5) * 10,
    gravity: 0.3 + Math.random() * 0.2,
    opacity: 1,
  }));

  const start = performance.now();
  function frame(now) {
    const elapsed = now - start;
    if (elapsed > duration) { canvas.remove(); return; }
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    particles.forEach(p => {
      p.x += p.vx;
      p.vy += p.gravity;
      p.y += p.vy;
      p.rotation += p.rotSpeed;
      p.opacity = Math.max(0, 1 - elapsed / duration);

      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate((p.rotation * Math.PI) / 180);
      ctx.globalAlpha = p.opacity;
      ctx.fillStyle = p.color;
      ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
      ctx.restore();
    });
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

/**
 * Animate a progress bar element's width
 * @param {HTMLElement} element - Progress bar inner element
 * @param {number} targetPercent - Target width percentage (0-100)
 * @param {number} duration - Duration in ms
 */
export function animateProgress(element, targetPercent, duration = 1200) {
  if (!element) return;
  const start = performance.now();
  const initial = parseFloat(element.style.width) || 0;
  const diff = targetPercent - initial;

  function tick(now) {
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    element.style.width = (initial + diff * eased) + '%';
    if (progress < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

/**
 * Typewriter text effect
 * @param {HTMLElement} element - Target element
 * @param {string} text - Text to type
 * @param {number} speed - Delay between characters in ms
 * @returns {Promise} Resolves when typing completes
 */
export function typeWriter(element, text, speed = 50) {
  return new Promise(resolve => {
    if (!element) { resolve(); return; }
    element.textContent = '';
    let i = 0;
    function type() {
      if (i < text.length) {
        element.textContent += text.charAt(i);
        i++;
        setTimeout(type, speed);
      } else {
        resolve();
      }
    }
    type();
  });
}

// =============================================
// Inject keyframe used by ripple effect
// =============================================
(function injectStyles() {
  if (document.getElementById('anim-helper-styles')) return;
  const style = document.createElement('style');
  style.id = 'anim-helper-styles';
  style.textContent = `
    @keyframes rippleAnim {
      to { transform: scale(4); opacity: 0; }
    }
    .reveal {
      opacity: 0;
      transform: translateY(30px);
      transition: opacity 0.6s ease, transform 0.6s ease;
    }
    .reveal.visible {
      opacity: 1;
      transform: translateY(0);
    }
  `;
  document.head.appendChild(style);
})();

// =============================================
// Auto-initialize on DOMContentLoaded
// =============================================
document.addEventListener('DOMContentLoaded', () => {
  initScrollReveal();
  // Add ripple to all buttons with .btn class
  document.querySelectorAll('.btn, .btn-primary, .btn-secondary, .glass-btn').forEach(addRippleEffect);
});
