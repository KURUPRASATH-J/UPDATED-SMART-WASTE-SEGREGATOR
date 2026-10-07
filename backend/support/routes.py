"""
Support chat endpoints for the Smart Waste Segregator help widget.

Answer pipeline (server-side, key never exposed to the browser):
  1. Rule-based FAQ match  (models.lookup_faq)  -> source 'faq'
  2. Google Gemini fallback                      -> source 'gemini'
  3. Escalation message                          -> source 'fallback'

Per-user history is persisted in the `chat_messages` table when the user is
logged in; anonymous users still get answers but nothing is stored.
"""
import json
import urllib.request
import urllib.error
from urllib.parse import urlencode

from flask import Blueprint, jsonify, request, session

import models
from config import Config

support_bp = Blueprint('support', __name__, url_prefix='/api/support')

SUPPORT_EMAIL = 'support@wastesegregator.com'
GEMINI_ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
GEMINI_FALLBACK_MODELS = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash']
GEMINI_TIMEOUT = 20

SYSTEM_PROMPT = """You are JUNO AI, the friendly support assistant for "Smart Waste Segregator",
a smart-bin IoT web app (Flask backend + vanilla-JS frontend) that monitors wet and dry
bins with ultrasonic/IR/moisture sensors, shows a live dashboard, maps, analytics, reports,
maintenance logs and gamification (points, streaks, badges).

Answer concisely and helpfully in the same language the user writes in. Use plain text
with short bullet lists. Useful quick facts:
- Setup: create account, connect ESP32 to WiFi, set Flask server IP in ESP32 code, place sensors.
- Wet waste: food scraps, peels, tea bags; Dry waste: paper, plastic, metal, glass.
- Sensors: ultrasonic ±2% accuracy, readings every ~5s.
- Alerts at 80%+ fill; reports exportable as PDF/CSV/Excel on the Reports page.
- Emailing the inbox: {email}
If the question is off-topic or you genuinely cannot answer, suggest contacting
{email}. Never invent API endpoints or security credentials."""

FALLBACK_REPLY_AI_UNAVAILABLE = (
    "I'm JUNO AI and I couldn't find a match in my quick answers; my AI "
    "assistant isn't reachable right now (it may be offline or rate-limited). "
    "Try rephrasing, watch the video tutorials on the Help page, or email "
    f"{SUPPORT_EMAIL} and we'll get back to you!")
FALLBACK_REPLY_AI_DISABLED = (
    "I'm JUNO AI and I couldn't find a match in my quick answers; the AI "
    "assistant is currently disabled on this server (no API key configured). "
    f"Email {SUPPORT_EMAIL} and we'll get back to you!")


def _sanitize_history(raw):
    """Clip + coerce the client-sent conversation history to a safe shape."""
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw[-8:]:
        if not isinstance(item, dict):
            continue
        role = item.get('role')
        content = str(item.get('content', ''))[:400]
        if role in ('user', 'assistant', 'model') and content.strip():
            out.append({'role': 'user' if role == 'user' else 'model', 'content': content})
    return out


def _call_gemini(message, history):
    """POST to the Gemini generateContent REST endpoint (stdlib only)."""
    if not Config.GEMINI_API_KEY:
        return None
    models_to_try = ([Config.GEMINI_MODEL] if Config.GEMINI_MODEL
                     else GEMINI_FALLBACK_MODELS)
    body = {
        'systemInstruction': {'parts': [{'text': SYSTEM_PROMPT.format(email=SUPPORT_EMAIL)}]},
        'contents': history + [{'role': 'user', 'parts': [{'text': message}]}],
        'generationConfig': {'temperature': 0.4, 'maxOutputTokens': 600},
    }
    payload = json.dumps(body).encode('utf-8')
    for model in models_to_try:
        url = GEMINI_ENDPOINT.format(model=model) + '?' + urlencode({'key': Config.GEMINI_API_KEY})
        req = urllib.request.Request(url, data=payload, method='POST',
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=GEMINI_TIMEOUT) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 404:  # model id not found -> try the next one
                continue
            return None  # 400/401/403/429 etc.: key or quota issue, stop probing
        except Exception:
            return None  # network timeout / DNS / connection refused
        try:
            parts = data['candidates'][0]['content']['parts']
            return ''.join(p.get('text', '') for p in parts).strip() or None
        except (KeyError, IndexError, TypeError):
            return None
    return None


@support_bp.route('/messages', methods=['GET'])
def get_messages():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'authenticated': False, 'messages': []})
    return jsonify({'authenticated': True, 'messages': models.get_chat_messages(user_id)})


@support_bp.route('/chat', methods=['POST'])
def chat():
    data = request.get_json(silent=True) or {}
    message = str(data.get('message', '')).strip()
    if not message:
        return jsonify({'error': 'Message is required'}), 400

    user_id = session.get('user_id')
    history = _sanitize_history(data.get('history'))
    if user_id:
        models.save_chat_message(user_id, 'user', message, source='user')

    # 1) Rule-based FAQ engine (offline, instant).
    faq = models.lookup_faq(message)
    if faq:
        reply, source = faq['answer'], 'faq'
        if user_id:
            models.save_chat_message(user_id, 'bot', reply, source=source)
        return jsonify({'reply': reply, 'source': source, 'matched': faq['question']})

    # 2) AI fallback via Gemini (server-side key).
    if Config.GEMINI_API_KEY:
        ai_reply = _call_gemini(message, history)
        if ai_reply:
            if user_id:
                models.save_chat_message(user_id, 'bot', ai_reply, source='gemini')
            return jsonify({'reply': ai_reply, 'source': 'gemini'})
        fallback = FALLBACK_REPLY_AI_UNAVAILABLE
        reason = 'ai_unreachable'
    else:
        fallback = FALLBACK_REPLY_AI_DISABLED
        reason = 'ai_disabled'

    # 3) Escalation fallback (clearly attributed, distinct from a plain
    #    no-FAQ-match: the AI was attempted/disabled, not skipped silently).
    if user_id:
        models.save_chat_message(user_id, 'bot', fallback, source='fallback')
    return jsonify({'reply': fallback, 'source': 'fallback', 'reason': reason})