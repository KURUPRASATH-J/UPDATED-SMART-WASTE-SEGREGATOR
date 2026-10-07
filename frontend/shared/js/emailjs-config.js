/* Shared EmailJS configuration — the ONLY place these values live.
   Consumed by:
     - backend/templates/pages/help.html   (Email Support form)
     - frontend/shared/js/chat-widget.js   (support email address)
   The template ID is intentionally empty until the project owner supplies it. */
window.EMAILJS_CONFIG = {
  SERVICE_ID: 'service_6zrwvc9',                  // confirmed by project owner
  PUBLIC_KEY: 'ZeT4Rtk2GV0bS4zAd',
  // 🔴 PASTE THE REAL TEMPLATE ID HERE (EmailJS dashboard → Email Templates)
  //    e.g. 'template_abc123def456' — until this is non-empty, the help page
  //    Email Support form shows the "not configured yet" warning.
  TEMPLATE_ID: 'template_o6p2xqu',
  SUPPORT_EMAIL: 'support@wastesegregator.com'
};