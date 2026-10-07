/**
 * @fileoverview Main application initialisation module.
 * Runs on every page (except login / register) to set up the shared sidebar,
 * theme toggle, particles and online/offline detection.
 * @module main
 */

import { showToast, storage, isMobile } from './utils.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Sidebar navigation items — single source of truth for every page. */
const NAV_ITEMS = [
  { icon: '📊', label: 'Dashboard',   href: 'dashboard.html'   },
  { icon: '💧', label: 'Wet Bin',     href: 'wet-bin.html'     },
  { icon: '♻️', label: 'Dry Bin',     href: 'dry-bin.html'     },
  { icon: '📈', label: 'Analytics',   href: 'analytics.html'   },
  { icon: '📄', label: 'Reports',     href: 'reports.html'     },
  { icon: '🌍', label: 'Impact',      href: 'impact.html'      },
  { icon: '🏆', label: 'Leaderboard', href: 'leaderboard.html' },
  { icon: '🗺️', label: 'Locations',   href: 'locations.html'   },
  { icon: '🔧', label: 'Maintenance', href: 'maintenance.html' },
  { icon: '📖', label: 'Guide',       href: 'guide.html'       },
  { icon: '⚙️', label: 'Settings',    href: 'settings.html'    },
];

/** Number of floating background particles to generate. */
const PARTICLE_COUNT = 20;

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

/**
 * Builds the sidebar HTML string.
 * @param {string} activePage - The filename of the current page (e.g. "dashboard.html").
 * @returns {string} Full sidebar inner HTML.
 */
function _buildSidebarHTML(activePage) {
  const links = NAV_ITEMS.map(({ icon, label, href }) => {
    const isActive = activePage === href ? ' class="active"' : '';
    return `<li><a href="${href}"${isActive}>${icon} ${label}</a></li>`;
  }).join('\n      ');

  return `
    <div class="sidebar-header">
      <h2>🗑️ Smart Waste Segregator</h2>
      <button class="close-btn" id="closeSidebar">✕</button>
    </div>
    <ul class="nav-links">
      ${links}
    </ul>
  `;
}

/**
 * Injects the shared sidebar into the page.
 * If an element with id="sidebar" already exists its innerHTML is replaced;
 * otherwise a new `<nav>` is created and prepended to <body>.
 */
function _injectSidebar() {
  const currentPage = window.location.pathname.split('/').pop() || 'dashboard.html';
  let sidebar = document.getElementById('sidebar');

  if (!sidebar) {
    sidebar = document.createElement('nav');
    sidebar.className = 'sidebar';
    sidebar.id = 'sidebar';
    document.body.prepend(sidebar);
  }

  sidebar.innerHTML = _buildSidebarHTML(currentPage);

  // Wire up close button inside sidebar
  const closeBtn = document.getElementById('closeSidebar');
  if (closeBtn) {
    closeBtn.addEventListener('click', () => {
      sidebar.classList.remove('active');
    });
  }
}

/**
 * Highlights the currently-active sidebar link based on the page URL.
 */
function _highlightActivePage() {
  const currentPage = window.location.pathname.split('/').pop() || 'dashboard.html';
  const links = document.querySelectorAll('#sidebar .nav-links a');
  links.forEach(link => {
    const href = link.getAttribute('href');
    if (href === currentPage) {
      link.classList.add('active');
    } else {
      link.classList.remove('active');
    }
  });
}

// ---------------------------------------------------------------------------
// Hamburger toggle
// ---------------------------------------------------------------------------

/**
 * Wires the hamburger button (id="hamburger") to open/close the sidebar.
 */
function _setupHamburger() {
  const hamburger = document.getElementById('hamburger');
  const sidebar   = document.getElementById('sidebar');
  if (!hamburger || !sidebar) return;

  hamburger.addEventListener('click', () => {
    sidebar.classList.toggle('active');
  });
}

// ---------------------------------------------------------------------------
// Theme toggle
// ---------------------------------------------------------------------------

/**
 * Wires the mode-toggle button (id="modeBtn") for dark ↔ light switching.
 * Persists the choice to localStorage under the key "theme".
 */
function _setupThemeToggle() {
  const modeBtn = document.getElementById('modeBtn');
  if (!modeBtn) return;

  // Apply persisted theme
  const savedTheme = storage.get('theme', 'dark');
  document.body.classList.remove('theme-dark', 'theme-light');
  document.body.classList.add(`theme-${savedTheme}`);
  modeBtn.textContent = savedTheme === 'light' ? '🌙 Dark Mode' : '☀️ Light Mode';

  modeBtn.addEventListener('click', () => {
    const isLight = document.body.classList.contains('theme-light');
    const newTheme = isLight ? 'dark' : 'light';

    document.body.classList.remove('theme-dark', 'theme-light');
    document.body.classList.add(`theme-${newTheme}`);
    modeBtn.textContent = newTheme === 'light' ? '🌙 Dark Mode' : '☀️ Light Mode';
    storage.set('theme', newTheme);

    // Let other modules react
    window.dispatchEvent(new CustomEvent('themechange', { detail: { theme: newTheme } }));
  });
}

// ---------------------------------------------------------------------------
// Particles
// ---------------------------------------------------------------------------

/**
 * Creates decorative floating background particles and appends them to <body>.
 * @param {number} [count=PARTICLE_COUNT] - Number of particles to spawn.
 */
export function createParticles(count = PARTICLE_COUNT) {
  // Avoid duplicate particles on hot-reload
  document.querySelectorAll('.particle[data-auto]').forEach(p => p.remove());

  for (let i = 0; i < count; i++) {
    const particle = document.createElement('div');
    particle.className = 'particle';
    particle.setAttribute('data-auto', 'true');
    particle.style.left            = `${Math.random() * 100}vw`;
    particle.style.top             = `${Math.random() * 100}vh`;
    particle.style.width           = `${3 + Math.random() * 5}px`;
    particle.style.height          = particle.style.width;
    particle.style.animationDelay  = `${Math.random() * 8}s`;
    particle.style.animationDuration = `${6 + Math.random() * 8}s`;
    particle.style.opacity         = `${0.3 + Math.random() * 0.5}`;
    document.body.appendChild(particle);
  }
}

// ---------------------------------------------------------------------------
// Online / Offline detection
// ---------------------------------------------------------------------------

/**
 * Sets up listeners that show toast notifications when the browser goes
 * online or offline.
 */
function _setupConnectivityListeners() {
  window.addEventListener('online', () => {
    showToast('🌐 You are back online', 'success');
    document.body.classList.remove('is-offline');
    document.body.classList.add('is-online');
  });

  window.addEventListener('offline', () => {
    showToast('📡 You are offline — cached data will be used', 'error', 5000);
    document.body.classList.remove('is-online');
    document.body.classList.add('is-offline');
  });

  // Set initial class
  if (navigator.onLine) {
    document.body.classList.add('is-online');
  } else {
    document.body.classList.add('is-offline');
  }
}

// ---------------------------------------------------------------------------
// Auto-close sidebar on mobile
// ---------------------------------------------------------------------------

/**
 * Closes the sidebar when the user clicks/taps outside of it on mobile viewports.
 */
function _setupAutoCloseSidebar() {
  document.addEventListener('click', (e) => {
    const sidebar   = document.getElementById('sidebar');
    const hamburger = document.getElementById('hamburger');
    if (!sidebar || !hamburger) return;

    const isOpen = sidebar.classList.contains('active');
    if (!isOpen) return;

    // If the click is outside both sidebar and hamburger
    if (!sidebar.contains(e.target) && !hamburger.contains(e.target)) {
      sidebar.classList.remove('active');
    }
  });
}

// ---------------------------------------------------------------------------
// Page transition
// ---------------------------------------------------------------------------

/**
 * Adds the `page-transition` class to <body> so CSS entry animations trigger.
 */
function _setupPageTransition() {
  document.body.classList.add('page-transition');
}

// ---------------------------------------------------------------------------
// Public: initApp
// ---------------------------------------------------------------------------

/**
 * Master initialisation function — call once on DOMContentLoaded for every
 * authenticated page.
 *
 * Performs:
 *  1. Sidebar injection & active-page highlighting
 *  2. Hamburger and theme-toggle wiring
 *  3. Background particle creation
 *  4. Online/offline toast notifications
 *  5. Page transition class
 *  6. Auto-close sidebar on outside click (mobile)
 *
 * @returns {void}
 */
export function initApp() {
  try {
    _setupPageTransition();
    _injectSidebar();
    _highlightActivePage();
    _setupHamburger();
    _setupThemeToggle();
    createParticles();
    _setupConnectivityListeners();
    _setupAutoCloseSidebar();

    console.log('✅ App initialised (live mode)');
  } catch (error) {
    console.error('❌ App initialisation failed:', error);
  }
}

// ---------------------------------------------------------------------------
// Auto-run on DOMContentLoaded (skip login & register pages)
// ---------------------------------------------------------------------------

const _page = window.location.pathname.split('/').pop() || '';
const _skipPages = ['index.html', 'register.html', ''];

if (!_skipPages.includes(_page)) {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
  } else {
    initApp();
  }
}
