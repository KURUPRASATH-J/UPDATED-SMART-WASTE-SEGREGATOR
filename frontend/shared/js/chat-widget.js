/* Smart Waste Segregator — JUNO AI support chat widget.
   Floating bubble (bottom-right) on every page. JUNO AI answers via
   rule-based FAQ -> Gemini AI fallback -> escalation:
     POST /api/support/chat    {message, history}
     GET  /api/support/messages  (restores per-user history in the DB)
   Avatar images: /frontend/assets/images/juno.png (light theme) and
   juno-dark.png (every other theme), swapped via body.theme-light like the
   brand logo; "J" badge fallback on image errors. No external libraries. */
(function () {
  var EMAIL = (window.EMAILJS_CONFIG && window.EMAILJS_CONFIG.SUPPORT_EMAIL) || 'support@wastesegregator.com';
  var QUICK = [
    'How do I set up the system?',
    'What goes in wet vs dry bins?',
    'How do I earn points?'
  ];
  var CHAT_ENDPOINT = '/api/support/chat';
  var HISTORY_ENDPOINT = '/api/support/messages';

  if (document.getElementById('swChatWidget')) return;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function fmtTime() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  var JUNO_LIGHT_SRC = '/frontend/assets/images/juno.png';
  var JUNO_DARK_SRC = '/frontend/assets/images/juno-dark.png';

  function junoHTML() {
    return '<span class="swJuno">' +
      '<img class="swJunoImg swJunoLight" src="' + JUNO_LIGHT_SRC + '" alt="JUNO AI" width="58" height="58">' +
      '<img class="swJunoImg swJunoDark" src="' + JUNO_DARK_SRC + '" alt="JUNO AI" width="58" height="58">' +
      '<span class="swJunoFallback" aria-hidden="true">J</span>' +
      '</span>';
  }

  var css = [
    '#swChatWidget{font-family:"Poppins",sans-serif;position:relative;z-index:11000}',
    '#swChatBtn{position:fixed;right:22px;bottom:44px;width:58px;height:58px;border-radius:50%;border:none;cursor:pointer;padding:0;overflow:hidden;',
    'color:#0a0e1a;display:flex;align-items:center;justify-content:center;',
    'box-shadow:0 8px 24px rgba(0,212,255,0.45);transition:transform .2s ease,box-shadow .2s ease}',
    '#swChatBtn:hover{transform:scale(1.07);box-shadow:0 10px 30px rgba(0,212,255,0.6)}',
    '#swChatBtn .swUnread{position:absolute;top:-2px;right:-2px;z-index:2;min-width:20px;height:20px;border-radius:10px;background:#ff4757;color:#fff;',
    'font-size:.7rem;font-weight:700;display:flex;align-items:center;justify-content:center;padding:0 5px;display:none}',
    '#swChatPanel{position:fixed;right:22px;bottom:112px;width:min(370px,calc(100vw - 24px));height:540px;max-height:calc(100vh - 160px);',
    'background:rgba(12,16,30,0.98);border:1px solid rgba(255,255,255,0.12);border-radius:18px;overflow:hidden;',
    'display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,212,255,0.28);z-index:11002;',
    'opacity:0;visibility:hidden;transform:translateY(16px) scale(.98);transition:opacity .25s ease,transform .25s ease,visibility .25s}',
    '#swChatPanel.open{opacity:1;visibility:visible;transform:translateY(0) scale(1)}',
    '#swChatHead{display:flex;align-items:center;gap:12px;padding:16px 18px;background:linear-gradient(135deg,rgba(0,212,255,0.22),rgba(0,255,136,0.08));border-bottom:1px solid rgba(255,255,255,0.08)}',
    '#swChatHead .swBot{width:40px;height:40px;border-radius:50%;overflow:hidden;flex-shrink:0;',
    'box-shadow:0 0 0 2px rgba(255,255,255,0.08)}',
    '#swChatHead h3{margin:0;font-size:.98rem;font-weight:600;color:#fff}',
    '#swChatHead .swStatus{font-size:.72rem;color:rgba(255,255,255,0.6);display:flex;align-items:center;gap:6px;margin-top:2px}',
    '#swChatHead .swStatus .swDot{width:7px;height:7px;border-radius:50%;background:#00ff88;box-shadow:0 0 8px #00ff88}',
    '#swChatClose{margin-left:auto;background:none;border:none;color:rgba(255,255,255,0.6);font-size:1.4rem;cursor:pointer;line-height:1;padding:4px}',
    '#swChatClose:hover{color:#ff6b6b}',
    '#swChatMsgs{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px}',
    '.swMsg{max-width:82%;padding:10px 13px;border-radius:14px;font-size:.86rem;line-height:1.5;white-space:pre-wrap;word-wrap:break-word;animation:swIn .22s ease}',
    '.swMsg.user{align-self:flex-end;background:linear-gradient(135deg,#00d4ff,#00a3cc);color:#04121a;border-bottom-right-radius:4px}',
    '.swMsg.bot{align-self:flex-start;background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.08);color:#fff;border-bottom-left-radius:4px}',
    '.swMsg .swSrc{display:block;margin-top:6px;font-size:.66rem;letter-spacing:.3px;text-transform:uppercase;opacity:.55}',
    '.swJuno{position:relative;display:inline-block;width:100%;height:100%;border-radius:50%;overflow:hidden;background:#0a0e1a;flex-shrink:0}',
    '.swJuno img.swJunoImg{position:absolute;top:0;left:0;width:100%;height:100%;object-fit:cover;display:block}',
    '.swJuno img.swJunoLight{display:none}',
    '.swJuno img.swJunoDark{display:block}',
    'body.theme-light .swJuno img.swJunoDark{display:none}',
    'body.theme-light .swJuno img.swJunoLight{display:block}',
    '.swJuno img.err{display:none}',
    '.swJuno .swJunoFallback{display:none;position:absolute;top:0;left:0;right:0;bottom:0;align-items:center;justify-content:center;',
    'border-radius:50%;background:linear-gradient(135deg,#00d4ff,#00ff88);color:#0a0e1a;font-size:1.05rem;font-weight:700}',
    '.swJuno.swF .swJunoFallback{display:flex}',
    '.swRow{display:flex;align-items:flex-end;gap:8px;align-self:flex-start;max-width:100%}',
    '.swMv{display:block;width:32px;height:32px}',
    '.swRow .swBubWrap{display:flex;flex-direction:column;align-items:flex-start;max-width:76%;min-width:0}',
    '.swRow .swMsg.bot{max-width:100%}',
    '.swAuthor{font-size:.66rem;color:rgba(255,255,255,0.55);margin-bottom:3px;letter-spacing:.4px;text-transform:uppercase}',
    '.swTypingLabel{text-transform:none;color:rgba(0,212,255,0.85)}',
    '.swTypeDots{display:inline-flex}',
    '.swTypeDots span{animation:swBlink 1.2s infinite}',
    '.swTypeDots span:nth-child(2){animation-delay:.2s}.swTypeDots span:nth-child(3){animation-delay:.4s}',
    '.swChips{display:flex;flex-wrap:wrap;gap:8px;padding:4px 16px 8px}',
    '.swChip{cursor:pointer;border:1px solid rgba(0,212,255,0.35);background:rgba(0,212,255,0.08);color:#00d4ff;border-radius:999px;padding:6px 12px;',
    'font-size:.75rem;transition:all .2s ease}',
    '.swChip:hover{background:rgba(0,212,255,0.2);transform:translateY(-1px)}',
    '#swChatInputRow{display:flex;gap:8px;padding:12px 14px;border-top:1px solid rgba(255,255,255,0.08)}',
    '#swChatInput{flex:1;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);border-radius:12px;color:#fff;',
    'padding:11px 14px;font-size:.85rem;outline:none;font-family:inherit}',
    '#swChatInput::placeholder{color:rgba(255,255,255,0.4)}',
    '#swChatInput:focus{border-color:rgba(0,212,255,0.55)}',
    '#swChatSend{background:linear-gradient(135deg,#00d4ff,#00ff88);border:none;border-radius:12px;color:#0a0e1a;cursor:pointer;',
    'font-size:1.05rem;padding:0 16px;transition:opacity .2s}',
    '#swChatSend:disabled{opacity:.4;cursor:default}',
    '#swChatEscalate{text-align:center;font-size:.72rem;color:rgba(255,255,255,0.55);padding:8px 14px 13px;border-top:1px solid rgba(255,255,255,0.05)}',
    '#swChatEscalate a{color:#00d4ff;text-decoration:none}',
    '#swChatEscalate a:hover{text-decoration:underline}',
    '.swTyping{align-self:flex-start;display:flex;gap:5px;padding:12px 15px;background:rgba(255,255,255,0.07);border-radius:14px;border-bottom-left-radius:4px}',
    '.swTyping span{width:7px;height:7px;border-radius:50%;background:rgba(255,255,255,0.5);animation:swBlink 1.2s infinite}',
    '.swTyping span:nth-child(2){animation-delay:.2s}.swTyping span:nth-child(3){animation-delay:.4s}',
    '@keyframes swIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}',
    '@keyframes swBlink{0%,80%,100%{opacity:.2}40%{opacity:1}}',
    '#swChatMsgs::-webkit-scrollbar{width:6px}#swChatMsgs::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.18);border-radius:3px}',
    '@media(max-width:520px){#swChatPanel{right:10px;bottom:112px;width:calc(100vw - 20px);height:calc(100vh - 150px)}#swChatBtn{right:14px;bottom:44px}}'
  ].join('');

  var styleEl = document.createElement('style');
  styleEl.textContent = css;
  document.head.appendChild(styleEl);

  var host = document.createElement('div');
  host.id = 'swChatWidget';
  host.innerHTML =
    '<button id="swChatBtn" aria-label="Chat with JUNO AI" title="Chat with JUNO AI">' + junoHTML() +
    '<span class="swUnread" id="swUnread">1</span></button>' +
    '<div id="swChatPanel" role="dialog" aria-label="Chat with JUNO AI">' +
    '  <div id="swChatHead">' +
    '    <div class="swBot">' + junoHTML() + '</div>' +
    '    <div><h3>JUNO AI</h3>' +
    '    <div class="swStatus"><span class="swDot"></span>Smart Waste Segregator Assistant</div></div>' +
    '    <button id="swChatClose" aria-label="Close chat">&times;</button>' +
    '  </div>' +
    '  <div id="swChatMsgs"></div>' +
    '  <div class="swChips" id="swChips"></div>' +
    '  <div id="swChatInputRow">' +
    '    <input id="swChatInput" type="text" placeholder="Type your question..." autocomplete="off">' +
    '    <button id="swChatSend" aria-label="Send">➤</button>' +
    '  </div>' +
    '  <div id="swChatEscalate">Still need help? <a href="mailto:' + EMAIL + '">✉️ ' + EMAIL + '</a></div>' +
    '</div>';
  document.body.appendChild(host);

  var btn = document.getElementById('swChatBtn');
  var panel = document.getElementById('swChatPanel');
  var msgs = document.getElementById('swChatMsgs');
  var input = document.getElementById('swChatInput');
  var sendBtn = document.getElementById('swChatSend');
  var unread = document.getElementById('swUnread');
  var chipsRow = document.getElementById('swChips');
  var historyLoaded = false;
  var historyStack = [];
  var suggestionsShown = false;

  QUICK.forEach(function (q) {
    var chip = document.createElement('button');
    chip.className = 'swChip';
    chip.type = 'button';
    chip.textContent = q;
    chip.addEventListener('click', function () { open(); send(q); });
    chipsRow.appendChild(chip);
  });

  function appendMsg(role, text, source, reason) {
    var b = document.createElement('div');
    b.className = 'swMsg ' + role;
    b.innerHTML = esc(text);
    if (source && role === 'bot') {
      var tag = document.createElement('span');
      tag.className = 'swSrc';
      tag.textContent = source === 'faq' ? 'Instant FAQ'
        : source === 'gemini' ? 'AI · Gemini'
        : reason === 'ai_disabled' ? 'Escalation · AI disabled'
        : reason === 'ai_unreachable' ? 'Escalation · AI unreachable'
        : 'Escalation';
      b.appendChild(tag);
    }
    if (role === 'bot') {
      var row = document.createElement('div');
      row.className = 'swRow';
      var mv = document.createElement('span');
      mv.className = 'swMv';
      mv.innerHTML = junoHTML();
      var col = document.createElement('div');
      col.className = 'swBubWrap';
      var author = document.createElement('div');
      author.className = 'swAuthor';
      author.textContent = 'JUNO AI';
      col.appendChild(author);
      col.appendChild(b);
      row.appendChild(mv);
      row.appendChild(col);
      msgs.appendChild(row);
    } else {
      msgs.appendChild(b);
    }
    msgs.scrollTop = msgs.scrollHeight;
    return b;
  }

  function showTyping(on) {
    var t = document.getElementById('swTypingRow');
    if (on && !t) {
      t = document.createElement('div');
      t.className = 'swRow';
      t.id = 'swTypingRow';
      t.innerHTML =
        '<span class="swMv">' + junoHTML() + '</span>' +
        '<div class="swBubWrap">' +
        '  <div class="swAuthor">JUNO AI <span class="swTypingLabel">is typing<span class="swTypeDots"><span>.</span><span>.</span><span>.</span></span></span></div>' +
        '  <div class="swTyping"><span></span><span></span><span></span></div>' +
        '</div>';
      msgs.appendChild(t);
      msgs.scrollTop = msgs.scrollHeight;
    } else if (!on && t) {
      t.remove();
    }
  }

  function showSuggestions() {
    suggestionsShown = true;
    chipsRow.style.display = 'flex';
  }

  function hideSuggestions() {
    suggestionsShown = false;
    chipsRow.style.display = 'none';
  }

  function open() {
    panel.classList.add('open');
    unread.style.display = 'none';
    input.focus();
    showSuggestions();
    if (!historyLoaded) {
      historyLoaded = true;
      fetch(HISTORY_ENDPOINT, { credentials: 'include' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d || !d.authenticated || !d.messages) return;
          d.messages.forEach(function (m) {
            if (m.role === 'user' || m.role === 'bot') {
              appendMsg(m.role, m.content);
              historyStack.push({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content });
            }
          });
          if (historyStack.length === 0) greet();
        })
        .catch(function () { greet(); });
    }
  }

  function greet() {
    if (msgs.childElementCount === 0) {
      appendMsg('bot', 'Hello! I am JUNO AI, your Smart Waste Segregator support assistant. I can help with setup, wet vs dry waste, sensors, reports, badges and more. Ask away!');
    }
  }

  function close() {
    panel.classList.remove('open');
  }

  function send(text) {
    text = (text || '').trim();
    if (!text || sendBtn.disabled) return;
    sendBtn.disabled = true;
    hideSuggestions();
    appendMsg('user', text);
    historyStack.push({ role: 'user', content: text });
    showTyping(true);
    var payload = {
      message: text,
      history: historyStack.slice(-8)
    };
    fetch(CHAT_ENDPOINT, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (r) { return r.json(); }).then(function (d) {
      var reply = (d && typeof d.reply === 'string' && d.reply.trim())
        ? d.reply
        : 'Sorry, I hit an error answering that — please try again.';
var source = (d && d.source) || '';
      var reason = (d && d.reason) || '';
      appendMsg('bot', reply, source, reason);
      historyStack.push({ role: 'assistant', content: reply });
    }).catch(function () {
      appendMsg('bot', 'Could not reach the support service. Please check your connection and try again, or email ' + EMAIL + '.', 'fallback');
    }).then(function () {
      showTyping(false);
      sendBtn.disabled = false;
      input.value = '';
    });
  }

  function onKey(e) {
    if (e.key === 'Enter') send(input.value);
    if (e.key === 'Escape') close();
  }

  btn.addEventListener('click', function () { open(); });
  document.getElementById('swChatClose').addEventListener('click', close);
  sendBtn.addEventListener('click', function () { send(input.value); });
  input.addEventListener('keydown', onKey);

  // JUNO avatar fallback: if the image visible for the current theme fails to
  // load, show the circular "J" badge. Driven by capture-phase load/error on
  // every .swJunoImg, re-evaluated on theme changes.
  function resolveJunoWrap(wrap) {
    if (!wrap) return;
    var light = wrap.querySelector('.swJunoLight');
    var dark = wrap.querySelector('.swJunoDark');
    var isLight = document.body.classList.contains('theme-light');
    var activeBad = isLight
      ? (!light || light.classList.contains('err'))
      : (!dark || dark.classList.contains('err'));
    wrap.classList.toggle('swF', !!activeBad);
  }
  function resolveJunos() {
    var wraps = document.querySelectorAll('.swJuno');
    for (var i = 0; i < wraps.length; i++) resolveJunoWrap(wraps[i]);
  }
  document.addEventListener('error', function (e) {
    var t = e.target;
    if (t && t.nodeName === 'IMG' && t.classList.contains('swJunoImg')) {
      t.classList.add('err');
      resolveJunoWrap(t.closest('.swJuno'));
    }
  }, true);
  document.addEventListener('load', function (e) {
    var t = e.target;
    if (t && t.nodeName === 'IMG' && t.classList.contains('swJunoImg')) {
      t.classList.remove('err');
      resolveJunoWrap(t.closest('.swJuno'));
    }
  }, true);
  window.addEventListener('themechange', resolveJunos);

  // Preload the launcher image so the button paints instantly, and settle the
  // fallback state once the DOM/theme is ready.
  (new Image()).src = JUNO_LIGHT_SRC;
  (new Image()).src = JUNO_DARK_SRC;
  resolveJunos();

  setTimeout(function () { greet(); }, 400);
})();