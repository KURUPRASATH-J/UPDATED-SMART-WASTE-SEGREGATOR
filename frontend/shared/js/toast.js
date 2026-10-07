/* ============================================================================
   shared/toast.js — single source of truth for toast notifications.

   Classic (non-module) script; load it via _sidebar.html so it is available
   on every page. Exposes:

     window.toastNotify(message, type, duration, options)   <- internal API,
          never shadowed by page-local functions; prefer calling this from
          modules/utilities.

     window.showToast(message, type, duration, options)     <- public alias.

   type:     'info' | 'success' | 'error' | 'warning'
             ('ok' -> success, 'err' -> error; booleans: true -> error)

   duration: ms before auto-dismiss (default 4500). Pass 0 to keep it open
             until dismissed (PWA prompts etc. pass a longer explicit value).

   options:  {
               extraClass: string,                       // extra class for scoping
               actions: [{ label, cls, onClick, dismiss }]  // dismiss:false keeps toast
             }

   Behaviour:
     - Container is fixed at the top-right, starting just below the topbar
       (see .toast-container in shared/themes.css).
     - At most MAX_VISIBLE on screen at once; the rest queue.
     - Slide-in from the right, fade-out on dismiss.
     - Auto-dismiss timer pauses while the toast is hovered.
     - ✕ close button, or click the message body, dismisses immediately.
     - Actions render as buttons on the right of the message.
   ========================================================================== */
(function () {
  'use strict';

  var CONTAINER_ID = 'toastContainer';
  var MAX_VISIBLE = 4;
  var DEFAULT_DURATION = 4500;
  var CLOSE_TEXT = '\u2715';
  var TYPE_MAP = {
    ok: 'success', success: 'success',
    err: 'error',  error:  'error',
    warn: 'warning', warning: 'warning',
    info: 'info'
  };

  var queue = [];
  var visible = 0;

  function reduceMotion() {
    try {
      return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) {
      return false;
    }
  }

  function ensureContainer() {
    var c = document.getElementById(CONTAINER_ID);
    if (!c) {
      c = document.createElement('div');
      c.className = 'toast-container';
      c.id = CONTAINER_ID;
      c.setAttribute('aria-live', 'polite');
      document.body.appendChild(c);
    }
    return c;
  }

  function stopTimer(el) {
    if (el.__timer) { clearTimeout(el.__timer); el.__timer = null; }
  }

  function startTimer(el, ms) {
    stopTimer(el);
    el.__deadline = Date.now() + ms;
    el.__timer = setTimeout(function () { dismissToast(el); }, ms);
  }

  function afterLeave(el, done) {
    var ran = false;
    function finish(ev) {
      if (ran || (ev && ev.type === 'animationend' && ev.animationName !== 'toastOut')) return;
      ran = true;
      el.removeEventListener('animationend', finish, false);
      if (el.parentNode) el.parentNode.removeChild(el);
      done();
    }
    if (reduceMotion()) { finish(); return; }
    el.addEventListener('animationend', finish, false);
    setTimeout(finish, 900);
  }

  function dismissToast(el) {
    if (el.__gone) return;
    el.__gone = true;
    stopTimer(el);
    el.classList.add('toast-leave');
    afterLeave(el, function () {
      visible = Math.max(0, visible - 1);
      next();
    });
  }

  function render(item) {
    var c = ensureContainer();
    var el = document.createElement('div');
    el.className = 'toast toast-' + item.type + (item.extraClass ? ' ' + item.extraClass : '');
    el.setAttribute('role', item.type === 'error' ? 'alert' : 'status');

    var msg = document.createElement('span');
    msg.className = 'toast-msg';
    msg.textContent = item.message;
    el.appendChild(msg);

    if (item.actions && item.actions.length) {
      var actionsWrap = document.createElement('div');
      actionsWrap.className = 'toast-actions';
      item.actions.forEach(function (a) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'toast-action ' + (a.cls || 'toast-btn-ghost');
        btn.textContent = a.label;
        btn.addEventListener('click', function () {
          var handler = a.onClick;
          if (handler) { try { handler(); } catch (err) { /* ignore */ } }
          if (a.dismiss !== false) dismissToast(el);
        });
        actionsWrap.appendChild(btn);
      });
      el.appendChild(actionsWrap);
    }

    var close = document.createElement('button');
    close.type = 'button';
    close.className = 'toast-close';
    close.setAttribute('aria-label', 'Dismiss notification');
    close.textContent = CLOSE_TEXT;
    close.addEventListener('click', function (e) {
      e.stopPropagation();
      dismissToast(el);
    });
    el.appendChild(close);

    el.addEventListener('click', function (e) {
      if (e.target.closest('.toast-action') || e.target.closest('.toast-close')) return;
      dismissToast(el);
    });

    if (item.duration > 0) {
      startTimer(el, item.duration);
      el.__remaining = item.duration;
      el.addEventListener('mouseenter', function () {
        if (el.__gone) return;
        el.__remaining = Math.max(0, el.__deadline - Date.now());
        stopTimer(el);
      });
      el.addEventListener('mouseleave', function () {
        if (el.__gone) return;
        startTimer(el, Math.max(250, el.__remaining));
      });
    }

    c.appendChild(el);
  }

  function next() {
    if (visible >= MAX_VISIBLE || !queue.length) return;
    var item = queue.shift();
    visible++;
    render(item);
  }

  function normalizeType(type) {
    if (type === true) return 'error';
    if (type === false || type === undefined || type === null) return 'info';
    return TYPE_MAP[String(type).toLowerCase()] || 'info';
  }

  function toastNotify(message, type, duration, options) {
    var opts = options || {};
    var dur = (typeof duration === 'number') ? duration : DEFAULT_DURATION;
    queue.push({
      message: String(message),
      type: normalizeType(type),
      duration: dur,
      extraClass: opts.extraClass || '',
      actions: opts.actions || null
    });
    next();
    return CONTAINER_ID;
  }

  // Public aliases. Pages must call the internal `toastNotify` from adapters so
  // a page-local `function showToast()` cannot create recursion or shadowing.
  window.toastNotify = toastNotify;
  window.showToast = toastNotify;
})();