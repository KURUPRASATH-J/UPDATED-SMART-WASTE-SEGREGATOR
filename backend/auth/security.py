"""
Admin-login security helpers.

Three concerns, all deliberately kept out of the route handlers:

1. Math challenges (``/api/auth/admin-challenge``). The expected answer is kept
   **server-side only** -- never in the Flask session, because the session
   cookie is signed but not encrypted, so anything stored there is readable by
   the client. Challenges are single-use and expire after
   ``CHALLENGE_TTL_SECONDS``.

2. Rate limiting + temporary lockout for the admin login path, keyed by IP and
   by account name.

3. Password strength rules for the forced first-login admin password change.

SECURITY NOTE (be honest about this): a math challenge only raises the cost of
unattended scripted guessing. It is not authentication. The real protections
here are the per-IP/per-account lockout, a strong password, and server-side role
checks on every admin request.
"""
import re
import secrets
import threading
import time

# ============ Tunables ============
CHALLENGE_TTL_SECONDS = 120      # 2 minutes, per spec
MAX_CHALLENGES = 512             # store cap; a cheap flood guard
ISSUE_LIMIT = (30, 60)           # (max issues, window seconds) per IP
ADMIN_ATTEMPT_LIMIT = (5, 60)    # (max attempts, window seconds) per IP
ADMIN_LOCK_THRESHOLD = 5         # consecutive failures before locking
ADMIN_LOCK_SECONDS = 600         # 10 minutes
MIN_PASSWORD_LENGTH = 10

# Seeded dev password that must never be reused, plus other obvious guesses.
WEAK_PASSWORDS = frozenset({
    'admin123', 'admin1234', 'admin12345', 'password', 'password1', 'password123',
    '1234567890', '12345678901', 'qwerty12345', 'letmein123', 'administrator',
    'admin@123', 'adminadmin', 'changeme123', 'welcome123', 'iloveyou123',
})


# ============ Challenge store (server-side, single-use, expiring) ============
_LOCK = threading.Lock()
_CHALLENGES = {}        # challenge_id -> {'answer': int, 'expires': float}
_ISSUE_HITS = {}       # ip -> [timestamps]


def _prune(now):
    for cid in [c for c, e in _CHALLENGES.items() if e['expires'] < now]:
        _CHALLENGES.pop(cid, None)
    for ip in [k for k, v in _ISSUE_HITS.items()
               if not v or v[-1] < now - ISSUE_LIMIT[1] * 2]:
        _ISSUE_HITS.pop(ip, None)


def _make_question():
    """Return ``(display_text, answer)``.

    Numbers stay small, results are never negative, and division always divides
    exactly because the quotient is chosen first and the dividend derived from it.
    """
    op = secrets.choice(['+', '-', '\u00d7', '\u00f7'])

    if op == '+':
        a = secrets.randbelow(19) + 2      # 2..20
        b = secrets.randbelow(19) + 2
        return f'What is {a} + {b}?', a + b

    if op == '-':
        a = secrets.randbelow(29) + 5      # 5..33
        b = secrets.randbelow(a)           # 0..a-1  => result >= 1, never negative
        if b == 0:
            b = 1
            a = 2
        return f'What is {a} \u2212 {b}?', a - b

    if op == '\u00d7':
        a = secrets.randbelow(9) + 2       # 2..10
        b = secrets.randbelow(9) + 2
        return f'What is {a} \u00d7 {b}?', a * b

    # division: pick quotient and divisor, then multiply to get the dividend
    quotient = secrets.randbelow(9) + 2    # 2..10
    divisor = secrets.randbelow(8) + 2     # 2..9
    dividend = quotient * divisor
    return f'What is {dividend} \u00f7 {divisor}?', quotient


def issue_challenge(ip='unknown'):
    """Mint a challenge. Returns ``(challenge_id, question)``.

    Raises ``RuntimeError`` when this IP has asked for too many challenges in
    the ISSUE_LIMIT window (protects the store from being flooded).
    """
    now = time.time()
    with _LOCK:
        _prune(now)
        hits = _ISSUE_HITS.setdefault(ip, [])
        while hits and hits[0] < now - ISSUE_LIMIT[1]:
            hits.pop(0)
        if len(hits) >= ISSUE_LIMIT[0]:
            raise RuntimeError('Too many challenge requests')
        hits.append(now)
        if len(_CHALLENGES) >= MAX_CHALLENGES:
            raise RuntimeError('Challenge store full')

        question, answer = _make_question()
        cid = secrets.token_urlsafe(18)
        _CHALLENGES[cid] = {'answer': answer, 'expires': now + CHALLENGE_TTL_SECONDS}
    return cid, question


def consume_challenge(challenge_id, raw_answer):
    """Validate and *always* consume the challenge.

    Returns ``(ok, reason)`` where reason is one of ``missing``,
    ``unknown``, ``expired`` or ``wrong``. Consumption happens before any
    comparison so a challenge can never be replayed, right or wrong.
    """
    if not challenge_id or raw_answer is None or str(raw_answer).strip() == '':
        return False, 'missing'

    with _LOCK:
        entry = _CHALLENGES.pop(str(challenge_id), None)   # single-use

    if entry is None:
        return False, 'unknown'
    if entry['expires'] < time.time():
        return False, 'expired'

    given = str(raw_answer).strip()
    if not re.fullmatch(r'\d{1,6}', given):       # reject "12abc", "1.5", "-3", "+12"
        return False, 'wrong'
    if int(given) != entry['answer']:
        return False, 'wrong'
    return True, 'ok'


def peek_challenge_answer(challenge_id):
    """Test/debug helper -- returns the expected answer or None."""
    with _LOCK:
        entry = _CHALLENGES.get(str(challenge_id))
        return entry['answer'] if entry else None


def reset_challenge_store():
    """Test helper -- drops all outstanding challenges."""
    with _LOCK:
        _CHALLENGES.clear()
        _ISSUE_HITS.clear()


# ============ Rate limiting + lockout (admin login path) ============
_LOCK2 = threading.Lock()
_ATTEMPTS = {}    # ip -> [timestamps]
_FAILS = {}       # key (ip or username) -> {'n': int, 'until': float}


def _window_ok(bucket, now, limit, window):
    """Record a hit in a sliding window. Returns (allowed, retry_after)."""
    while bucket and bucket[0] < now - window:
        bucket.pop(0)
    if len(bucket) >= limit:
        return False, max(1, int(window - (now - bucket[0])))
    bucket.append(now)
    return True, 0


def admin_guard(ip, username=''):
    """Check the admin login path BEFORE any credential work.

    Returns ``(blocked, message, retry_after_seconds)``. Applies both a sliding
    -window rate limit per IP and a temporary lock after consecutive failures on
    either the IP or the account name.
    """
    now = time.time()
    with _LOCK2:
        for key in (ip, username):
            if not key:
                continue
            rec = _FAILS.get(key)
            if rec and rec['until'] > now:
                mins = int((rec['until'] - now) / 60) + 1
                return True, (
                    'Too many failed admin sign-in attempts. '
                    'Try again in %d minute(s).' % mins
                ), int(rec['until'] - now) + 1

        limit, window = ADMIN_ATTEMPT_LIMIT
        allowed, retry = _window_ok(_ATTEMPTS.setdefault(ip, []), now, limit, window)
        if not allowed:
            return True, f'Too many admin sign-in attempts. Try again in {retry} second(s).', retry

    return False, '', 0


def admin_record_failure(ip, username=''):
    """Count a failed admin attempt; lock the IP and account at the threshold."""
    now = time.time()
    with _LOCK2:
        for key in (ip, username):
            if not key:
                continue
            rec = _FAILS.get(key) or {'n': 0, 'until': 0}
            if rec['until'] > now:          # already locked -> keep the longer lock
                rec['n'] += 1
            else:
                rec['n'] += 1
                rec['until'] = now + ADMIN_LOCK_SECONDS if rec['n'] >= ADMIN_LOCK_THRESHOLD else 0
            _FAILS[key] = rec


def admin_clear_failures(ip, username=''):
    with _LOCK2:
        _ATTEMPTS.pop(ip, None)
        for key in (ip, username):
            if key:
                _FAILS.pop(key, None)


def admin_lock_state(ip, username=''):
    """Introspection for tests / diagnostics."""
    now = time.time()
    with _LOCK2:
        out = {}
        for label, key in (('ip', ip), ('account', username)):
            rec = _FAILS.get(key) if key else None
            out[label] = {
                'failures': rec['n'] if rec else 0,
                'lockedFor': max(0, int(rec['until'] - now)) if rec and rec['until'] > now else 0,
            }
        out['windowHits'] = len([t for t in _ATTEMPTS.get(ip, []) if t >= now - ADMIN_ATTEMPT_LIMIT[1]])
        return out


def reset_rate_state():
    """Test helper."""
    with _LOCK2:
        _ATTEMPTS.clear()
        _FAILS.clear()


# ============ Password policy ============
def validate_password(new_password, username='', email=''):
    """Return ``(ok, message)`` for a proposed new password.

    Rules: at least ``MIN_PASSWORD_LENGTH`` characters, at least one letter and
    one digit, not a well-known weak password, and not derived from the account
    name/email.
    """
    pwd = new_password or ''
    if len(pwd) < MIN_PASSWORD_LENGTH:
        return False, f'Password must be at least {MIN_PASSWORD_LENGTH} characters long.'
    if not re.search(r'[A-Za-z]', pwd):
        return False, 'Password must contain at least one letter.'
    if not re.search(r'\d', pwd):
        return False, 'Password must contain at least one number.'
    if pwd.strip().lower() in WEAK_PASSWORDS:
        return False, 'That password is too common. Choose something unique.'
    if len(set(pwd)) <= 2:
        return False, 'Password is too repetitive.'
    low = pwd.lower()
    for token in (username or '', (email or '').split('@')[0]):
        token = (token or '').strip().lower()
        if len(token) >= 4 and token in low:
            return False, 'Password must not contain your username.'
    return True, ''