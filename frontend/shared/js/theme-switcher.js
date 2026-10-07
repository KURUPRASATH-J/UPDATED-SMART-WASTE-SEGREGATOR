import { storage } from './utils.js';

// Shared theme mechanism. Loaded by every themed page (type="module").
// - Applies the localStorage cache immediately on load (fast paint) ...
// - ... then reconciles with the per-user settings from GET /api/settings
//   (source of truth), and persists changes via POST /api/settings.
// Pages that ship their own theme UI (Settings) don't load this module.

// Available themes
const themes = {
  dark: {
    name: 'Dark',
    icon: '🌙',
    class: 'theme-dark'
  },
  light: {
    name: 'Light',
    icon: '☀️',
    class: 'theme-light'
  },
  ocean: {
    name: 'Ocean',
    icon: '🌊',
    class: 'theme-ocean'
  },
  nature: {
    name: 'Nature',
    icon: '🌿',
    class: 'theme-nature'
  },
  sunset: {
    name: 'Sunset',
    icon: '🌅',
    class: 'theme-sunset'
  },
  galaxy: {
    name: 'Galaxy',
    icon: '🌌',
    class: 'theme-galaxy'
  }
};

// Current theme (localStorage is a fast-paint CACHE only; the server settings
// endpoint is the source of truth so the choice follows the user's account).
let currentTheme = storage.get('theme', 'dark');

// Initialize theme
export function initTheme() {
  applyTheme(currentTheme);       // instant paint from cache
  createThemePicker();
  syncServerTheme();              // reconcile with the account's saved theme
}

// Pull the saved theme from the server and apply it if it differs (this is
// what makes a theme picked in Settings appear across devices/pages).
function syncServerTheme() {
  fetch('/api/settings', { method: 'GET', credentials: 'include' })
    .then(function (r) { if (!r.ok) return null; return r.json(); })
    .then(function (data) {
      if (data && data.theme && themes[data.theme] && data.theme !== currentTheme) {
        applyTheme(data.theme);
      }
    })
    .catch(function () { /* offline/not logged in -> keep cached theme */ });
}

// Apply theme
export function applyTheme(themeName) {
  // Remove all theme classes
  Object.values(themes).forEach(theme => {
    document.body.classList.remove(theme.class);
  });
  
  // Add new theme class
  const theme = themes[themeName];
  if (theme) {
    document.body.classList.add(theme.class);
    currentTheme = themeName;
    storage.set('theme', themeName);
    
    // Update mode toggle button if exists
    const modeBtn = document.getElementById('modeBtn');
    if (modeBtn) {
      modeBtn.textContent = theme.icon + ' ' + theme.name;
    }

    // Keep the sidebar theme select in sync (relocated picker UI)
    const themeSelect = document.getElementById('themeSelect');
    if (themeSelect) {
      themeSelect.value = themeName;
    }
    
    // Emit theme change event
    window.dispatchEvent(new CustomEvent('themechange', { 
      detail: { theme: themeName } 
    }));
  }
}

// Get current theme
export function getCurrentTheme() {
  return currentTheme;
}

// Toggle between dark and light
export function toggleTheme() {
  const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
  applyTheme(newTheme);
}

// Theme selector. The sidebar partial (_sidebar.html) ships the theme card
// markup statically (right card of the "equal two-card layout"), so nothing
// is injected here — we only make sure the select reflects the current theme.
// Pages without the sidebar (Settings ships its own Appearance tab UI) have
// no #themeSelect, which is fine.
function createThemePicker() {
  const themeSelect = document.getElementById('themeSelect');
  if (themeSelect) {
    themeSelect.value = currentTheme;
  }
}

// Set theme (exposed to window for picker event handlers).
window.setTheme = function(themeName) {
  applyTheme(themeName);

  // Persist the choice server-side so it follows the user account.
  fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ theme: themeName })
  }).catch(function() { /* offline -> local cache still applies */ });
};

// Auto theme based on time
export function enableAutoTheme() {
  const hour = new Date().getHours();
  
  if (hour >= 6 && hour < 12) {
    applyTheme('light'); // Morning
  } else if (hour >= 12 && hour < 17) {
    applyTheme('ocean'); // Afternoon
  } else if (hour >= 17 && hour < 20) {
    applyTheme('sunset'); // Evening
  } else {
    applyTheme('dark'); // Night
  }
  
  storage.set('autoTheme', true);
}

// Disable auto theme
export function disableAutoTheme() {
  storage.set('autoTheme', false);
}

// Check if auto theme is enabled
export function isAutoThemeEnabled() {
  return storage.get('autoTheme', false);
}

// Initialize on page load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initTheme);
} else {
  initTheme();
}
