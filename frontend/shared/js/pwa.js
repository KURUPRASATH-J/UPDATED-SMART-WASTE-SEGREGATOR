/**
 * @fileoverview PWA utilities module.
 * Handles service-worker registration with update detection, the
 * `beforeinstallprompt` event for a custom install UI, online/offline
 * monitoring, and new-version notifications.
 * @module pwa
 */

import { showToast, storage } from './utils.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Path to the service worker file (site root, so it works from every page). */
const SW_PATH = '/service-worker.js';

/** localStorage key used to track deferred install prompt state. */
const INSTALL_DISMISSED_KEY = 'sws_installDismissed';

/** Minimum seconds between "update available" toasts to avoid spamming. */
const UPDATE_TOAST_COOLDOWN_MS = 60_000;

// ---------------------------------------------------------------------------
// Internal state
// ---------------------------------------------------------------------------

/** Holds the deferred `BeforeInstallPromptEvent` if one fires. */
let _deferredPrompt = null;

/** Timestamp of the last "update available" notification. */
let _lastUpdateToast = 0;

/** The active ServiceWorkerRegistration (if any). */
let _registration = null;

// ---------------------------------------------------------------------------
// Service Worker registration
// ---------------------------------------------------------------------------

/**
 * Registers the service worker and sets up update / state-change handling.
 *
 * - On first install the user is notified the app is available offline.
 * - When a new SW version is detected (`updatefound`) the user is
 *   prompted to refresh via {@link showUpdateNotification}.
 *
 * @returns {Promise<ServiceWorkerRegistration|null>}
 *   The registration object, or `null` if SW is unsupported.
 */
export async function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) {
    console.warn('⚠️  Service Workers are not supported in this browser.');
    return null;
  }

  try {
    _registration = await navigator.serviceWorker.register(SW_PATH, {
      scope: '/',
    });

    console.log('✅ Service Worker registered — scope:', _registration.scope);

    // ----- Handle updates -----
    _registration.addEventListener('updatefound', () => {
      const newWorker = _registration.installing;
      if (!newWorker) return;

      newWorker.addEventListener('statechange', () => {
        // A new SW has installed and the old one is still active
        if (
          newWorker.state === 'installed' &&
          navigator.serviceWorker.controller
        ) {
          showUpdateNotification();
        }

        // First-time install completed (no previous controller)
        if (
          newWorker.state === 'activated' &&
          !navigator.serviceWorker.controller
        ) {
          showToast('📦 App is now available offline!', 'success', 4000);
        }
      });
    });

    // ----- Detect controller change (e.g. skipWaiting was called) -----
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      // The new service worker has taken over — reload to use it
      console.log('🔄 New service worker active — reloading…');
      window.location.reload();
    });

    return _registration;
  } catch (error) {
    console.error('❌ Service Worker registration failed:', error);
    return null;
  }
}

// ---------------------------------------------------------------------------
// Install prompt
// ---------------------------------------------------------------------------

/**
 * Captures the `beforeinstallprompt` event and (optionally) shows a custom
 * install banner/button.
 *
 * Call this early (before DOMContentLoaded ideally) so the event is not lost.
 *
 * The function:
 *  1. Prevents the browser's default mini-infobar.
 *  2. Stores the event for later use.
 *  3. If the user hasn't previously dismissed the prompt, shows a toast
 *     with an install action.
 *  4. Looks for a DOM element with id `installBtn` and wires it up.
 *
 * @returns {void}
 */
export function handleInstallPrompt() {
  window.addEventListener('beforeinstallprompt', (e) => {
    // Prevent default mini-infobar
    e.preventDefault();
    _deferredPrompt = e;

    console.log('📲 Install prompt captured');

    // Wire up a dedicated install button if present in the DOM
    const installBtn = document.getElementById('installBtn');
    if (installBtn) {
      installBtn.style.display = 'inline-flex';
      installBtn.addEventListener('click', () => _triggerInstall(), { once: true });
    }

    // Show toast if user hasn't dismissed before
    if (!storage.get(INSTALL_DISMISSED_KEY, false)) {
      _showInstallToast();
    }
  });

  // Track successful install
  window.addEventListener('appinstalled', () => {
    _deferredPrompt = null;
    showToast('🎉 App installed successfully!', 'success');
    console.log('✅ App was installed');

    // Hide install button
    const installBtn = document.getElementById('installBtn');
    if (installBtn) installBtn.style.display = 'none';
  });
}

/**
 * Triggers the native install prompt using the stored
 * `BeforeInstallPromptEvent`.
 * @private
 * @returns {Promise<void>}
 */
async function _triggerInstall() {
  if (!_deferredPrompt) return;

  try {
    _deferredPrompt.prompt();
    const { outcome } = await _deferredPrompt.userChoice;

    if (outcome === 'accepted') {
      console.log('👍 User accepted the install prompt');
    } else {
      console.log('👎 User dismissed the install prompt');
      storage.set(INSTALL_DISMISSED_KEY, true);
    }
  } catch (err) {
    console.error('❌ Install prompt error:', err);
  } finally {
    _deferredPrompt = null;
  }
}

/**
 * Creates an interactive toast that offers the user an "Install" button.
 * Uses the shared toast.js library (via utils showToast) with action buttons.
 * @private
 */
function _showInstallToast() {
  showToast('📲 Install Smart Waste Segregator for a better experience!', 'info', 15_000, {
    extraClass: 'pwa-install-toast',
    actions: [
      { label: 'Install', cls: 'toast-btn-primary', onClick: () => _triggerInstall(), dismiss: true },
      {
        label: 'Later',
        cls: 'toast-btn-ghost',
        onClick: () => { storage.set(INSTALL_DISMISSED_KEY, true); },
        dismiss: true,
      },
    ],
  });
}

// ---------------------------------------------------------------------------
// Update notification
// ---------------------------------------------------------------------------

/**
 * Shows a "new version available" toast with a reload button.
 * Rate-limited to avoid spamming the user.
 *
 * @returns {void}
 */
export function showUpdateNotification() {
  const now = Date.now();
  if (now - _lastUpdateToast < UPDATE_TOAST_COOLDOWN_MS) return;
  _lastUpdateToast = now;

  showToast('🆕 A new version is available!', 'info', 30_000, {
    extraClass: 'pwa-update-toast',
    actions: [
      {
        label: 'Refresh',
        cls: 'toast-btn-primary',
        onClick: () => {
          // Tell the waiting SW to activate immediately
          if (_registration && _registration.waiting) {
            _registration.waiting.postMessage({ type: 'SKIP_WAITING' });
          }
          // controllerchange listener (in registerServiceWorker) will reload
        },
        dismiss: true,
      },
      { label: 'Later', cls: 'toast-btn-ghost', onClick: () => {}, dismiss: true },
    ],
  });
}

// ---------------------------------------------------------------------------
// Online / Offline monitoring
// ---------------------------------------------------------------------------

/**
 * Monitors `navigator.onLine` and the `online`/`offline` window events.
 * Fires `pwaOnlineStatusChange` custom events that other modules can listen
 * to.
 *
 * @returns {{ isOnline: boolean }} The current connectivity state.
 */
export function checkOnlineStatus() {
  const status = { isOnline: navigator.onLine };

  const dispatchStatus = (online) => {
    status.isOnline = online;
    window.dispatchEvent(
      new CustomEvent('pwaOnlineStatusChange', { detail: { isOnline: online } })
    );
  };

  window.addEventListener('online',  () => dispatchStatus(true));
  window.addEventListener('offline', () => dispatchStatus(false));

  return status;
}

// ---------------------------------------------------------------------------
// Auto-initialise on DOMContentLoaded
// ---------------------------------------------------------------------------

/**
 * Bootstraps all PWA utilities:
 *  1. Registers the service worker
 *  2. Captures install prompts
 *  3. Sets up online/offline monitoring
 * @private
 */
function _autoInit() {
  registerServiceWorker();
  handleInstallPrompt();
  checkOnlineStatus();
  console.log('✅ PWA utilities initialised');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _autoInit);
} else {
  _autoInit();
}
