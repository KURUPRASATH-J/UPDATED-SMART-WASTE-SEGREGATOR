# Smart Waste Segregator

# UPDATED-SMART-WASTE-SEGREGATOR

**Version 3.0 (work-in-progress) · IoT + Web monitoring dashboard for a dual-chamber (Wet / Dry) smart waste bin**

> This README is a full engineering handover. It documents what the project *is*,
> the architecture that was built, every module and its **current completion state**,
> and the known issues/technical debt. It is intended to let any developer (or AI
> agent) pick up the project without re-discovering it from scratch.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Current Development State (TL;DR)](#2-current-development-state-tldr)
3. [System Architecture & Data Flow](#3-system-architecture--data-flow)
4. [Tech Stack](#4-tech-stack)
5. [Repository Structure](#5-repository-structure)
6. [Backend – Flask + SQLite (ACTIVE)](#6-backend--flask--sqlite-active)
   - [app.py (API + WebSocket)](#apppy-api--websocket)
   - [models.py (Data Layer)](#modelspy-data-layer)
7. [Frontend](#7-frontend)
   - [Auth pages (login / register)](#auth-pages-login--register)
   - [Dashboard](#dashboard)
   - [Feature pages (`pages/`)](#feature-pages-pages)
   - [React Native / CSS system](#css-system)
   - [PWA support](#pwa-support)
   - [JS modules (legacy Firebase generation)](#js-modules-legacy-firebase-generation)
8. [Hardware – ESP32 Firmware](#8-hardware--esp32-firmware)
9. [Database Schema](#9-database-schema)
10. [REST API Reference](#10-rest-api-reference)
11. [WebSocket (Socket.IO) Events](#11-websocket-socketio-events)
12. [Gamification System](#12-gamification-system)
13. [How to Run Locally](#13-how-to-run-locally)
14. [Completion Matrix](#14-completion-matrix)
15. [Known Issues & Technical Debt](#15-known-issues--technical-debt)
16. [Security Notes](#16-security-notes)
17. [Roadmap / Suggested Next Steps](#17-roadmap--suggested-next-steps)

---

## 1. Project Overview

The **Smart Waste Segregator** is an end-to-end IoT system that:

- Uses an **ESP32 microcontroller** with **3× HC-SR04 ultrasonic sensors** and a
  **servo-controlled lid** to build a smart two-compartment waste bin.
- Segregates waste into a **Wet bin** (organic/wet waste) and a **Dry bin**
  (recyclables/dry waste).
- Measures fill level (`%), distance (cm), weight (kg) and gas/air-quality for
  each chamber, detects **human presence** near the bin and **auto-opens the lid**.
- Streams that sensor data to a **Flask + SQLite backend** over HTTP
  (`POST /api/sensor-data`, `/api/presence`, `/api/lid`).
- Serves a **glassmorphic dark-themed PWA dashboard** with real-time WebSocket
  (Socket.IO) updates, 3D/bin visualizations, trend charts, predictions,
  gamification (eco points, streaks, badges, leaderboard), analytics, reports,
  maps, multi-user accounts and admin features.

The current repo is a **hybrid of two generations**:

| Generation | Backend | Frontend architecture | Status |
|---|---|---|---|
| **Gen 1 (legacy)** | Firebase Realtime Database | ES-module JS (`js/*.js`) shared across pages | **Written but almost entirely unwired.** Only `leaderboard.html` uses it (and it is currently broken). |
| **Gen 2 (active)** | Flask + SQLite + Socket.IO | Self-contained HTML pages (inline CSS + JS) | **The working system.** Auth, dashboard and several feature pages are wired to this backend. |

A fair amount of Gen 1 JS/CSS survives in the repo (dead code for now) and was the
basis for the design language that Gen 2 re-implemented inline per page.

---

## 2. Current Development State (TL;DR)

| Area | Status |
|---|---|
| ESP32 firmware (sensor reading, presence, servo lid, HTTP POST) | ✅ Working (gen-2 sketch) |
| Flask backend REST API | ✅ Working |
| SQLite schema + seed data (badges, challenges, bins, device state) | ✅ Working |
| WebSocket real-time broadcast | ✅ Working |
| User registration / login / logout / session | ✅ Working (session-cookie auth) |
| Main Dashboard (`dashboard.html`) | ✅ Working (Flask REST + Socket.IO + live UI) |
| Wet Bin page | ✅ Working (REST + Socket.IO) |
| Dry Bin page | ✅ Working (REST + Socket.IO) |
| Analytics page | ✅ Working (Flask REST, hand-rolled canvas charts) |
| Settings page | 🟡 Mostly working (server round-trips; theme toggles localStorage-only) |
| Reports page | 🟡 Partially working (real data + PDF/CSV/print; has a field-mismatch bug + duplicated DOM) |
| Notifications page | 🟡 Partially working (reads activity; actions not persisted; duplicated DOM) |
| Profile page | 🟡 Partially working (reads/saves settings; duplicated DOM; one broken link) |
| Leaderboard page | 🔴 Broken (ES-module imports invalid `auth` symbol; Firebase-gen page) |
| Map page (Leaflet) | 🔴 Static mock-up with duplicate container; data hardcoded |
| Locations / Maintenance / Impact / Users pages | 🔴 Static mock-ups; several truncated or have stub functions |
| Guide / Help / 404 pages | ✅ Complete as static/interactive info pages |
| PWA (manifest, service worker, offline cache, install) | 🟡 Cached list is stale (caches dead CSS); install flow present in `js/pwa.js` but un-wired |
| Database state (checked on handover) | Empty of user data: `users=0, readings=0, activity=0` (schema + seed only) |

**Bottom line:** the backend + core dashboard pipeline is **complete and usable**,
and is the "north star" implementation. Several satellite pages are UI mock-ups,
and a batch of legacy JS/CSS is dead weight that can be deleted or revived.

---

## 3. System Architecture & Data Flow

```
                    ┌─────────────────────────────┐
                    │         ESP32 / Bin         │
                    │  3× HC-SR04 (ultrasonic)    │
                    │  Servo lid (SG90)           │
                    └──────────────┬──────────────┘
                                   │  HTTP POST (JSON)
                    ┌──────────────▼──────────────┐
                    │      Flask Backend          │
                    │  app.py (routes + SocketIO) │
                    │  models.py (SQLite CRUD)    │
                    │  waste.db (WAL mode)        │
                    └──────┬───────────────┬──────┘
                           │               │
              emit('bin_update')        REST /api/*
                           │               │
                    ┌──────▼───────────────▼──────┐
                    │      Web Frontend (PWA)      │
                    │  index/register/dashboard.html│
                    │  pages/*.html + Socket.IO    │
                    └──────────────────────────────┘
```

1. ESP32 measures wet & dry levels via distance-to-fill conversion, presence via a
   PIR-style check (ultrasonic threshold), and opens/closes the lid servo.
2. Every 5 s it `POST`s `{wetLevel, wetDistance, dryLevel, dryDistance}` to
   `POST /api/sensor-data`; presence/lid events `POST` to `/api/presence` and
   `/api/lid`.
3. `models.update_bin()` writes the new level + a `readings` row, recomputes
   **fill rate (`%/hr`)** and **time-to-full**, stores a **prediction**, runs
   **anomaly detection** (sudden spike/drop >30), detects **collections**
   (old>30 → new<10), and triggers **eco-point awards**.
4. `app.py` then broadcasts the new state via Socket.IO `bin_update`, plus
   `presence_update` and `lid_update`. Optionally sends a **Telegram alert** when a
   bin ≥ 85 %.
5. Every connected browser updates 3D bin visuals, stat cards, predictions, charts
   and the live activity feed in real time.

---

## 4. Tech Stack

**Backend**
- Python 3.12, Flask 3.1.1, Flask-SocketIO 5.5.1 (eventlet async), Flask-CORS 5.0.1
- SQLite 3 (`waste.db`, WAL journal mode) via raw `sqlite3`
- Werkzeug for password hashing (`generate_password_hash` / `check_password_hash`)
- `requirements.txt` also lists `flask-login` (installed but **not used**)

**Frontend**
- Vanilla HTML5/CSS3/JavaScript (no frameworks)
- Socket.IO client 4.7.2 CDN (dashboard) / 4.7.5 CDN (wet/dry pages)
- Canvas 2D API hand-rolled charts (charts.js + inline chart code; no Chart.js)
- Leaflet 1.9.4 (map page), jsPDF 2.5.1 + html2canvas 1.4.1 (reports page)
- PWA: `manifest.json` + `service-worker.js` (offline cache, stale-while-revalidate)
- Google Fonts: Inter (dashboard), Poppins (auth + most pages)

**Hardware**
- ESP32, Arduino framework
- HC-SR04 ultrasonic sensors ×3 (presence, wet, dry)
- SG90 (or similar) servo for the lid
- `ESP32Servo`, `WiFi.h`, `HTTPClient.h`

---

## 5. Repository Structure

```
smart-waste-segregator/
├── frontend/                  # All web assets (HTML/CSS/JS/images/PWA)
│   ├── index.html             # Login page (Flask /api/auth/login)
│   ├── register.html          # Registration page (Flask /api/auth/register)
│   ├── dashboard.html         # Main live dashboard (Flask REST + Socket.IO)
│   ├── manifest.json          # PWA manifest (start /frontend/dashboard.html)
│   ├── service-worker.js      # PWA SW: cache v4, stale-while-revalidate, push
│   │
│   ├── pages/                 # All secondary feature pages (self-contained HTML)
│   │   ├── 404.html           # Error page (static, complete — minor font bug)
│   │   ├── analytics.html     # ✅ Wired to Flask (readings + hourly averages)
│   │   ├── wet-bin.html       # ✅ Wired: /api/bins/wetBin + Socket.IO
│   │   ├── dry-bin.html       # ✅ Wired: /api/bins/dryBin + Socket.IO
│   │   ├── reports.html       # 🟡 Partially wired (PDF/CSV/print; bugs noted)
│   │   ├── notifications.html # 🟡 Reads /api/activity; actions not persisted
│   │   ├── profile.html       # 🟡 Reads /api/auth/me + /api/settings
│   │   ├── settings.html      # 🟡 Mostly wired; theme/advanced localStorage-only
│   │   ├── leaderboard.html   # ✅ Wired: /api/gamification/leaderboard
│   │   ├── map.html           # 🟡 Leaflet static mock-up
│   │   ├── locations.html     # 🟡 Truncated static mock-up (modal JS missing)
│   │   ├── maintenance.html   # 🔴 Static mock-up (stub buttons, hardcoded data)
│   │   ├── impact.html        # 🔴 Truncated mock-up (metrics never populated)
│   │   ├── users.html         # 🔴 Static admin mock-up (no save handler)
│   │   ├── guide.html         # ✅ Static interactive (search + quiz)
│   │   └── help.html          # ✅ Static info page (FAQ, some stubs)
│   │
│   ├── assets/images/         # logo.png, logo-dark.png, bin-wet.svg
│   │
│   └── shared/
│       ├── css/               # themes.css, animations.css (linked by pages)
│       └── js/                # Shared scripts (main, utils, theme-switcher, …)
│
├── backend/                   # ACTIVE backend (Python 3.12)
│   ├── app.py                 # Flask app, all API routes, Socket.IO, Telegram
│   ├── config.py              # Env-based configuration
│   ├── extensions.py          # DB access, auth decorators, Socket.IO, Telegram
│   ├── models.py              # SQLite schema, CRUD, gamification, admin
│   ├── requirements.txt       # Python deps (pinned)
│   ├── waste.db               # SQLite database (initialized, currently seed-only)
│   ├── auth/ bins/ gamification/ analytics/ admin/
│   │                         # Blueprint packages (routes.py each)
│   └── tests/
│       └── test_badges.py     # Badge-engine tests (temp DB)
│
└── hardware/
    └── sketch_oct24a/
        └── sketch_oct24a.ino  # ESP32 firmware (gen-2, targets Flask)
```

---

## 6. Backend – Flask + SQLite (ACTIVE)

### `app.py` (API + WebSocket)

Entry point: `python backend/app.py` → serves everything on `http://0.0.0.0:5000`.

**App setup**
- `SECRET_KEY` from env or default `smart-waste-dev-key-2026`.
- `CORS(app, supports_credentials=True)`, `SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')`.
- `FRONTEND_DIR` points at `frontend/` so Flask serves all static files:

| Route | What it serves |
|---|---|
| `/`, `/index.html` | `frontend/index.html` |
| `/dashboard.html`, `/register.html` | `frontend/dashboard.html`, `frontend/register.html` |
| `/frontend/<file>` | anything under `frontend/` (canonical) |
| `/pages/<file>` | anything under `frontend/pages/` (legacy alias) |
| `/css/<file>`, `/js/<file>`, `/assets/<file>` | `frontend/shared/css`, `frontend/shared/js`, `frontend/assets` |
| `/manifest.json`, `/service-worker.js` | PWA files under `frontend/` |

**Auth guards**
- `@login_required` / `@admin_required` decorators exist.
- ⚠️ `admin_required` is defined but **never applied** — all `/api/admin/*` endpoints currently require **no auth**.

**Endpoint map** — see [§10 REST API Reference](#10-rest-api-reference).

**Sensor ingestion**
- `POST /api/sensor-data` clamps levels to 0–100, calls `models.update_bin(...)`
  for `wetBin`/`dryBin`, broadcasts `bin_update` over Socket.IO, and fires a
  Telegram alert (non-blocking background thread) whenever any bin ≥ 85 %.

**WebSocket** — on client connect the server pushes the current snapshot
(`bin_update`, `presence_update`, `lid_update`). See [§11](#11-websocket-socketio-events).

**Telegram bot** (`send_telegram`, `POST /api/telegram/test`)
- Reads `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` from env or the request body.
- Uses `urllib` in a daemon thread; silently no-ops if unconfigured.

Debug mode is on (`debug=True`) and the server binds `0.0.0.0` (LAN-visible) —
intended for local development with the ESP32 on the same network.

### `models.py` (Data Layer)

Everything talks to SQLite through small functions (no ORM). `init_db()` runs
**automatically on import** and:

- Creates **14 tables** (see [§9](#9-database-schema)).
- Inserts the two bins (`wetBin`, `dryBin`) and device-state rows
  (`presence_detected=false`, `presence_distance=0`, `lid_status=closed`).
- Seeds **12 badges** and **4 challenges**.

Key logic:

| Function | Purpose |
|---|---|
| `create_user` / `authenticate_user` / `get_user_by_id` / `get_all_users` | Accounts (Werkzeug password hashes; unique username+email) |
| `update_last_login` | Streak computation (increments / resets) + streak badge unlocking |
| `update_bin` | Level save, readings append, **fill-rate (¼%/hr)**, **time-to-full (min)**, prediction row, **anomaly detection**, **collection detection**, eco-score award (+10 per collection, attributed to most-recent user), ≥80 % alert logging, badge checks |
| `get_bins` / `get_bin` / `reset_bins` | Current state / reset all to 0 % |
| `get_readings` / `get_hourly_averages` | History + hourly aggregation (SQL `strftime`) |
| `get_stats` | Dashboard stats incl. CO₂ (0.5 kg per collection), water (25 L/collection), trees (0.05/collection), peak hour |
| `get_predictions` / `get_anomalies` | Prediction table + anomaly feed |
| `get_user_gamification` / `get_leaderboard` / `award_eco_points` | Gamification reads/writes |
| `save_settings` / `get_settings` | Per-user key/value settings |
| `get_admin_stats` / `backup_database` / `get_backups` | DB size, counts, timestamped DB backup files under `backend/backups/` |

---

## 7. Frontend

### Auth pages (login / register)

- **`index.html`** — glassmorphic login. `fetch('/api/auth/login', { credentials:'include' })`,
  stores the returned user in `localStorage['user']`, redirects to `dashboard.html`.
- **`register.html`** — sign-up form (full name, username, email, password ≥6,
  confirm). `POST /api/auth/register`, client-side password-match check.

Both are self-contained (inline styles + particles animation). No CSRF/rate limiting.

### Dashboard

**`dashboard.html`** — the flagship page. Self-contained (inline `:root` tokens,
inline CSS, inline JS, Socket.IO 4.7.2 CDN). Contents:

- **Sidebar** (11 nav links), **top bar** with live **streak 🔥** and **eco-score 🌿**
  badges, hamburger for mobile.
- **4 stat cards**: Total Readings, Avg Wet (24h), Avg Dry (24h), CO₂ saved (kg) —
  with count-up animation.
- **3D/CSS bin visualization**: two animated bins with wave fill animation, percentage,
  distance, fill-rate/hr, time-to-full, air-quality; status pill rows
  (`normal` <50 %, `warning` 50–79 %, `critical` ≥80 % with pulse animation).
- **Prediction cards** (full-in time + fill rate) derived from `time_to_full_min`.
- **Fill-level trend chart** (hand-rolled Canvas 2D, wet/dry gradient area lines) +
  **live activity feed**.
- **Gamification row** (badge cards, locked vs earned).
- **Live ticker** at the bottom, **toast** system, **confetti** on bin reset.
- **Socket.IO listener wiring**: `bin_update`, `presence_update`, `lid_update`,
  `confetti`; plus offline/online toasts.

Polling fallback: `loadStats()`, `loadActivity()`, `loadGamification()`,
`loadTrendChart()` every 30 s even on top of WebSocket pushes.

### Feature pages (`pages/`)

Each page is standalone (inline CSS or `themes.css`/`animations.css`). Summary of
every page + its state is in [§2](#2-current-development-state-tldr) and
[§14 Completion Matrix](#14-completion-matrix).

Worth calling out again:

- **`wet-bin.html` / `dry-bin.html`** are the cleanest "single-bin live monitor"
  pages: 4 stat cards, animated liquid fill, history table, and both REST load and
  Socket.IO live updates with offline fallbacks.
- **`analytics.html`** loads `/api/readings` + `/api/readings/hourly`, draws a line
  + bar chart in raw Canvas, has 6h/24h/72h/7d filters and a readings table.
- **`settings.html`** is the most complete "real" settings UI: General /
  Notifications / Appearance / Alerts / System / Advanced tabs; persists most
  values via `POST /api/settings`; theme + advanced toggles are localStorage-only;
  displays hardcoded `localhost:5000` info; `resetBins()` calls `/api/bins/reset`.
- **`leaderboard.html`** imports `{ auth } from '../js/auth.js'` which does **not**
  export `auth` — the module script throws and the page stays on "Loading…".
  `getLeaderboard` itself (in `js/gamification.js`) works.

### CSS system

Two live files, four dead files (see [§5](#5-repository-structure) table):

- `themes.css` — 6 themes (`dark` default, light, ocean, nature, sunset, galaxy)
  defined as `body.theme-*` overrides of tokens `--bg-primary, --bg-card,
  --border-color, --text-primary, --text-secondary, --accent-primary,
  --accent-secondary, --shadow, --glow`; plus the floating theme-picker widget.
- `animations.css` — `.fade-in, .slide-up, .scale-in, .bounce, .pulse,
  .skeleton, .spinner, .ripple, .typewriter, .hover-lift…` utilities.
- `style.css` (37 KB master), `responsive.css`, `glassmorphism.css`, `print.css`
  are **not referenced by any HTML file** — artifacts of the older shared-stylesheet era.

The modern pages re-implement their own `:root` tokens and keyframes inline
(e.g. `dashboard.html` uses `--bg, --surface, --border, --accent, --accent2,
--glass, --radius`), with different names from `themes.css`.

### PWA support

- `manifest.json` — name, standalone display, theme `#00d4ff`, background
  `#091020`, icons from `frontend/assets/images/logo.png` (⚠️ the PNG files are
  currently **0 bytes** — empty placeholders), shortcuts to Dashboard / Analytics / Guide.
- `service-worker.js` — cache `waste-segregator-v4`; precaches root HTML + some
  pages + shared CSS/JS + the logo, all under `/frontend/...`. Strategy:
  stale-while-revalidate, offline navigation fallback to `/frontend/dashboard.html`,
  `push` + `notificationclick` handlers.
- `frontend/shared/js/pwa.js` — a complete, well-documented install-prompt +
  update-notification module, but **no page currently imports it**, so it's dormant.

### JS modules (legacy Firebase generation)

The `js/` directory is a *second*, mostly-unused implementation that talks to
**Firebase Realtime Database** (`smart-waste-segregator-8d1de`). It includes
demo-mode fallbacks (`?demo=true`), localStorage caching, module-level charts and
gamification logic. Only `leaderboard.html` imports these modules, and that import
is currently broken (see above). The ESP32 firmware that wrote to Firebase has been
superseded by the gen-2 sketch that writes to Flask instead.

These modules are candidates for **deletion**, **porting**, or being re-wired once
the app moves to a bundled (vite/webpack) frontend.

---

## 8. Hardware – ESP32 Firmware

File: `hardware/sketch_oct24a/sketch_oct24a.ino` — "Smart Waste Bin System v2.0 (Flask)".

**Pin map**

| Pin | Function |
|---|---|
| 13 / 12 | Presence HC-SR04 (TRIG / ECHO) |
| 5 / 18 | Wet bin HC-SR04 |
| 19 / 21 | Dry bin HC-SR04 |
| 14 | Servo (lid) |

**Behaviour**
- Connects to WiFi hotspot (`Galaxy M34 5G 47D7` / `11111111` — **hardcoded, edit
  before sharing/field use**), posts to `http://192.168.43.100:5000` (laptop IP on
  hotspot — **hardcoded**).
- `loop()`: presence check every 500 ms; opens lid if someone within 20 cm for ≥2
  consecutive readings; keeps lid open up to 5 s (re-arms while person present);
  uploads bin levels every 5 s.
- `getDistance()`: HC-SR04 echo timing → cm (out-of-range returns −1).
- `calculateFillLevel()`: `(BIN_HEIGHT − distance) / BIN_HEIGHT × 100`, clamped 0–100;
  `BIN_HEIGHT` defaults to 50 cm.
- HTTP endpoints: `POST /api/sensor-data`, `POST /api/presence`, `POST /api/lid`
  with JSON bodies; logs serial output for debugging.

**Battery / signal (not yet sent):** the sketch does **not** upload battery level
or WiFi signal strength (no `WiFi.getRSSI()` / battery-ADC fields). The dashboard's
Device Health card intentionally hides these readings rather than faking them;
if you add them, the backend already tolerates extra JSON keys and
`models.get_device_health()` will surface `battery`/`signal` the moment the
firmware sends them (e.g. `WiFi.getRSSI()` on the sensor-data POST).

**To use**: set your own SSID/password and the laptop's LAN IP in the `#define`s,
flash via Arduino IDE, and run the Flask server on the same network.

---

## 9. Database Schema

`backend/waste.db` (SQLite, WAL mode, foreign keys ON). 14 tables:

| Table | Purpose | Notable columns |
|---|---|---|
| `users` | Accounts & gamification | `username, email, password_hash, full_name, role, eco_score, streak_days, streak_last_date, total_waste_kg, created_at, last_login, avatar_color` |
| `bins` | Current bin state | `id (wetBin/dryBin), level, distance, status, fill_rate, time_to_full_min, weight_kg, gas_level, location_name, updated_at` |
| `readings` | Historical samples | `bin_type, level, distance, weight_kg, gas_level, timestamp` |
| `activity` | Event log (feed uses it) | `event_type, message, data, timestamp` (types: `user, login, presence, lid, alert, anomaly, collection, level_update, reset`) |
| `device_state` | Key-value device flags | `presence_detected, presence_distance, lid_status` |
| `settings` | Per-user key/value | PK `(user_id, key)` |
| `collections` | Bin-emptying events | `bin_type, level_before, collected_at` |
| `badges` | Badge definitions | `id, name, description, icon, category, requirement` (12 seeded) |
| `user_badges` | Earned badges | PK `(user_id, badge_id)` |
| `challenges` | Challenge definitions | `title, description, metric, target_value, active…` (4 seeded) |
| `user_challenges` | Challenge progress | PK `(user_id, challenge_id)` |
| `predictions` | Fill prediction per bin | `fill_rate_per_hour, time_to_full_hours, predicted_full_at, confidence` |
| `anomalies` | Detected spikes/drops | `bin_type, anomaly_type, message, level_before, level_after` |

On handover the DB is freshly initialized: **0 users, 0 readings, 0 activity,
0 collections, 0 predictions, 0 anomalies**; bins, device state, 12 badges and 4
challenges seeded.

---

## 10. REST API Reference

Base URL: `http://localhost:5000`. All JSON. Session cookie auth for user routes.

### Auth
| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/api/auth/register` | `{username, email, password, fullName}` | 201 / 409 (exists) / 400. Always creates `role='user'`; a `role` field in the payload is ignored |
| POST | `/api/auth/login` | `{username, password, portal: "user"\|"admin", challenge_id?, challenge_answer?}` | see below |
| GET | `/api/auth/admin-challenge` | – | `{challenge_id, question}`; the answer stays server-side, expires in 2 min, single-use |
| POST | `/api/auth/change-password` | `{current_password, new_password, confirm_password?}` | 200 / 401 (wrong current) / 400 (policy) |
| POST | `/api/auth/logout` | – | clears session |
| GET | `/api/auth/me` | – | current user or 401 |

**Portal enforcement.** The login form has a User tab and an Admin tab; the tab
is sent as `portal` and the **server** checks it against the account role:

| `portal` | Requires | Mismatch |
|---|---|---|
| `user` (also the default when `portal` is missing/unknown) | `role != 'admin'` | `403 "These credentials can't be used on this portal"` |
| `admin` | `role == 'admin'` | `403`, same generic message |

A mismatch creates **no session** and is written to the activity log with the
username and IP. The message is deliberately identical in both directions so it
cannot be used to discover whether an account exists or is an admin.

**Admin login extras.** The admin portal additionally requires a math challenge
(`challenge_id` + `challenge_answer`) which is verified *before* the password is
checked — a missing, wrong or expired answer returns `400 Challenge failed`. The
challenge is consumed on every attempt, so it cannot be replayed. The admin path
is rate limited to 5 attempts/minute per IP and locks for 10 minutes after 5
consecutive failures. `admin_required` re-checks the role on every `/api/admin/*`
request, so bypassing the login UI gets you nowhere.

> ⚠️ **The math challenge is not strong security.** It raises the cost of
> unattended scripted guessing; it does not authenticate anyone. Real protection
> comes from the rate limit/lockout, a strong password, and the server-side role
> checks.

### 🔐 Default admin password — change this before sharing

The admin account is seeded from the `ADMIN_USERNAME` / `ADMIN_PASSWORD`
environment variables (see `backend/.env.example`). If `ADMIN_PASSWORD` is not
set, the app seeds the **weak development default `admin123`** and prints a
`[WARNING]` at startup.

The seeded account is created with `must_change_password = 1`, so the first
admin sign-in is forced through a password change before `/admin.html` or any
`/api/admin/*` route will respond. A password can also be changed at any time from
**Settings → Security**.

**Do not share or deploy this app with `admin123` still in place.** Set
`ADMIN_PASSWORD` (and `SECRET_KEY`) in `backend/.env` first.

### Sensor / device (ESP32)
| Method | Path | Body |
|---|---|---|
| POST | `/api/sensor-data` | `{wetLevel, wetDistance, dryLevel, dryDistance, wetWeight?, dryWeight?, wetGas?, dryGas?}` |
| POST | `/api/presence` | `{detected, distance}` |
| POST | `/api/lid` | `{status: open\|closed}` |

### Dashboard / data
| Method | Path | Notes |
|---|---|---|
| GET | `/api/bins` | `{bins, device, predictions}` |
| GET | `/api/bins/<bin_type>` | single bin or 404 |
| POST | `/api/bins/reset` | resets bins to 0; emits `confetti` |
| GET | `/api/stats` | total/today readings, avgWet/Dry 24h, co2Saved, ecoScore, peakHour, waterSaved, treesSaved, anomalyCount |
| GET | `/api/activity?limit=` | event log (default 50) |
| GET | `/api/readings?bin=&hours=&limit=` | raw samples |
| GET | `/api/readings/hourly?bin=&hours=` | hourly averages |
| GET | `/api/predictions` | prediction table |
| GET | `/api/anomalies?limit=` | anomaly feed |

### Gamification
| Method | Path | Notes |
|---|---|---|
| GET | `/api/gamification` | ecoScore, streakDays, badges, allBadges, challenges (demo data when logged out) |
| GET | `/api/gamification/leaderboard?limit=` | top users by eco_score |
| POST | `/api/gamification/award` | `{points}` — requires login |

### Settings & users
| Method | Path | Notes |
|---|---|---|
| GET / POST | `/api/settings` | per-user KV settings (login required) |

### Admin (⚠️ currently no auth on these)
| Method | Path | Notes |
|---|---|---|
| GET | `/api/admin/stats` | db size, user/readings/activity/anomaly counts |
| GET | `/api/admin/users` | all users sorted by eco_score |
| POST | `/api/admin/backup` | copies `waste.db` → `backend/backups/waste_backup_<ts>.db` |
| GET | `/api/admin/backups` | list backup files |
| GET | `/api/admin/backup/download/<file>` | download a backup |
| GET | `/api/admin/export?format=json` | full export (stats + 30-day readings + 1000 activity rows) |
| POST | `/api/telegram/test` | `{token?, chatId?}` sends test Telegram message |

---

## 11. WebSocket (Socket.IO) Events

Server → client:

| Event | Payload | Purpose |
|---|---|---|
| `bin_update` | `{wetBin, dryBin, predictions, timestamp}` | level/distance/status/fill-rate/TTF refresh |
| `presence_update` | `{detected, distance, timestamp}` | person near bin |
| `lid_update` | `{status, timestamp}` | lid open/close |
| `confetti` | `{}` | triggers fireworks after bin reset |

On client connect, the server immediately emits `bin_update`, `presence_update`
and `lid_update` with current snapshots, so pages hydrate instantly.

Client connects via `io()` (or `io({transports:['polling','websocket']})`).
`async_mode='eventlet'` serves both the HTTP app and WebSocket on the same port.

---

## 12. Gamification System

Implemented **server-side** (models.py) and mirrored in the legacy JS:

- **Eco score** — +10 points awarded on each detected collection
  (`update_bin`); `total_waste_kg` also incremented. Leaderboard = `eco_score DESC`.
- **Streak** — tracked on login (`streak_days`); resets if a day is skipped;
  unlocks `first_week / two_weeks / month_streak` badges.
- **Badges (12 seeded)** — first_login, first_week, two_weeks, month_streak,
  eco_starter(100), eco_warrior(500), eco_legend(1000), zero_overflow,
  collector_10, collector_50, night_owl, data_nerd.
- **Challenges (4 seeded)** — reduce dry waste, zero overflow week, eco score 100,
  daily check-in. Progress tracking exists (`user_challenges`) but **no evaluator
  loop is wired** (nothing updates `progress` yet).
- The legacy `js/gamification.js` has an independent points/levels/achievements
  model (5 levels, 6 achievements) targeting Firebase — not connected to the
  server-side eco-score system (a unification task).

---

## 13. How to Run Locally

**Prerequisites:** Python 3.12, pip; optionally an ESP32.

```bash
# 1. Backend
cd backend
pip install -r requirements.txt
python app.py
# → http://localhost:5000  (Flask + Socket.IO, debug=True)
```

```bash
# 2. Frontend (optional — Flask already serves it)
# Just open http://localhost:5000 in a browser.
```

- **Register** an account, then **log in**.
- The DB is re-initialized automatically on first import (seed data). No data will
  appear until a device posts to `/api/sensor-data`; until then the dashboard shows
  zeros/`--`.

**Simulating a device (no ESP32):**
```bash
# from a second terminal, e.g. PowerShell
$b = @{wetLevel=45; wetDistance=20; dryLevel=62; dryDistance=12} | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:5000/api/sensor-data -Method Post -ContentType "application/json" -Body $b
```

**Telegram alerts (optional):**
```powershell
$env:TELEGRAM_BOT_TOKEN  = "your-bot-token"
$env:TELEGRAM_CHAT_ID    = "your-chat-id"
```

---

## 14. Completion Matrix

Legend: ✅ working · 🟡 partially working / intentional placeholder · 🔴 broken/not implemented · 💀 dead code (kept)

_Matrix was re-verified by a full QA pass on 2026-09-25 (all pages rendered, all inline JS passed `node --check`, route map dumped, Socket.IO listeners audited)._

| Module | Current State | Notes |
|---|---|---|
| Backend REST API | ✅ | all endpoints in [§10](#10-rest-api-reference) respond (50 routes verified) |
| Auth (register/login/logout/me) | ✅ | session-cookie based; no email verification, no CSRF |
| SQLite schema + seed | ✅ | auto-init; WAL; FKs |
| Socket.IO real-time | ✅ | `bin_update/presence_update/lid_update/confetti/notification_new/badge_unlocked` |
| Sensor ingestion + fill-rate + TTF + anomalies + collections | ✅ | in `models.update_bin`; eco points attributed to acting user |
| Telegram alerting | 🟡 | works when env configured; no UI to set chat/token |
| Admin endpoints | ✅ | now **protected** with `admin_required` |
| Dashboard | ✅ | full live view; WebSocket + 30s polling; badge unlock toast now wired |
| Wet / Dry bin pages | ✅ | live + history + socket updates |
| Analytics | ✅ | REST + canvas charts; loads on filters/resize (no auto-refresh) |
| Settings | 🟡 | theme/advanced localStorage-only; server URL now derived from `window.location.origin` |
| Reports | ✅ | real data + PDF/CSV/print/email; `bin_type` bug fixed |
| Notifications | ✅ | persisted read/clear/delete + realtime push |
| Profile | ✅ | loads/saves settings; Cancel link fixed |
| Leaderboard | ✅ | wired to `/api/gamification/leaderboard` + `/api/auth/me` (`auth` import gone) |
| Map | 🟡 | intentional "coming soon" state (full original kept in `backend/_wip/`) |
| Locations | 🟡 | intentional "coming soon" state (original in `backend/_wip/`) |
| Maintenance | 🟡 | intentional "coming soon" state (original in `backend/_wip/`) |
| Impact | 🟡 | intentional "coming soon" state (original in `backend/_wip/`) |
| Users (admin) | 🟡 | "coming soon" UI; full admin REST API exists behind auth |
| Guide | ✅ | static interactive (search/quiz) |
| Help | ✅ | static FAQ |
| 404 | ✅ | static; favicon + `@import` fixed |
| PWA manifest / SW | ✅ | v6 precaches only existing assets; real logo icons in use |
| Themes / animations CSS | ✅ | `themes.css` + `animations.css` linked across templates |
| Badge engine (points/streak/challenges) | ✅ | new in this restructure; Ship-of-Theseus-proofed |
| Dashboard summary endpoint | ✅ | new single `/api/dashboard/summary` feed |
| Notification persistence | ✅ | new; `activity.read` column + migration + socket push |
| Nav unification | ✅ | single `_sidebar.html` incl. per-route role/active/highlight |
| `shared/js/*` legacy modules | 💀 | `main/charts/export/geolocation/theme-switcher/utils.js` unreferenced (candidates for pruning) |
| ESP32 firmware | ✅ | gen-2 Flask sketch; hardcoded credentials |
| Assets (`logo*.png`, `bin-wet.svg`) | ✅ | real files (~0.3–0.4 MB logos) |

---

## 15. Known Issues & Technical Debt

_Re-verified 2026-09-25. ✅ = fixed · 🟡 = partially fixed · 🔴 = still open._

**Functionality / correctness**
1. ✅ **Leaderboard page was broken** — invalid `import { auth }` removed; page now
   fetches `/api/gamification/leaderboard` + `/api/auth/me`; JS passes syntax check.
2. ✅ **Admin API had no auth** — every admin route now requires `admin_required`.
3. ✅ **Reports count bug** — page reads `r.bin_type` (was `r.bin`) for per-bin counts.
4. ✅ **Eco-point attribution** — `models.update_bin` receives `user_id` from the
   authenticated session; collection rows store `user_id`; points go to the actor.
5. ✅ **Challenge progress** — `gamification/badges.py` writes `progress` via
   `update_challenge_progress` + `evaluate_user`.
6. ✅ **Notifications UI** — read/clear/delete persisted (`activity.read` column +
   migration) and pushed over Socket.IO (`notification_new`).
7. ✅ **Duplicate DOM on 5 pages** — map/notifications/profile/reports/users rebuilt
   as single-container templates; guide.html's "duplicates" are JS string templates
   (not live DOM).
8. ✅ **Truncated markup** — impact/locations/users cleaned via coming-soon rewrite.
9. ✅ **Undefined functions** — no page references `openAddModal`/`closeAddModal`.
10. ✅ **Broken relative links** — map "View Details" removed (coming-soon); profile
    Cancel now uses absolute `/frontend/dashboard.html`.
11. 🟡 **No real-time on satellite pages** — dashboard + wet/dry-bin + notifications
    are live; analytics/leaderboard/settings still poll only (analytics has no
    auto-refresh, only resize + manual filter clicks).

**Dead code / legacy**
12. ✅ `css/style.css`, `css/responsive.css`, `css/glassmorphism.css`, `css/print.css`
    are gone from the repo; the service worker no longer precaches them.
13. ✅ The legacy `js/` Firebase module set is gone; nothing imports it anymore.
    ⚠️ Remaining: `frontend/shared/js/{main,charts,export,geolocation,theme-switcher,utils}.js`
    are unreferenced — prune in the next cleanup.
14. ✅ Assets (logo.png, logo-dark.png, bin-wet.svg) are real (0.3–0.4 MB / 978 B).
15. ✅ `404.html` `@import` moved inside `<style>`; favicon now points to a real image.

**Configuration / security**
16. 🔴 ESP32 sketch hardcodes WiFi SSID/password and server IP (intentional for a
    single-device project; use env/config if distributing).
17. ✅ `firebase-config.js` (real-looking API key) removed from the repo.
18. 🟡 `SECRET_KEY` now fails fast in production if unset; dev fallback key remains
    for local runs. Flask CORS default allow-list ✅, but Socket.IO still allows `*`.
19. ✅ Backend debug/host are env-gated (`DEBUG`, default `127.0.0.1`).
20. ✅ `settings.html` server URL / API endpoint now derive from `window.location.origin`.

**New findings from the QA pass**
- `badge_unlocked` was emitted but had no listener → dashboard now toasts it live
  (previously badges appeared only after the 30s poll).
- Boot emits `EventletDeprecationWarning`; switch to `"threading"` async_mode if you
  don't need eventlet (e.g. Windows dev boxes).
- `backend/_wip/` holds the full pre-restructure implementations of the 5 converted
  pages — keep as archive or delete once "coming soon" becomes "implement".

---

## 16. Security Notes

- Passwords are hashed with Werkzeug (PBKDF2) — good.
- Sessions use Flask's default signed cookie (client-side); no server session store.
- Admin routes are unprotected — **gate them** before any real deployment.
- The `/api/sensor-data` endpoint is unauthenticated by design (IoT device can't
  hold sessions) — consider an API token for the device in production.
- CORS `*` + `supports_credentials=True` is permissive; restrict to the frontend origin.
- Remove the exposed Firebase API key or restrict its scope, since it is public in the repo.
- Provide a proper `SECRET_KEY` via env in production.
- Never deploy with `debug=True`.

---

## 17. Roadmap / Suggested Next Steps

Priority order (highest → lowest) to make the app uniformly "complete":

1. **Fix the leaderboard** import (`auth` → `firebase-config.js`) or wire it to the
   Flask `/api/gamification/leaderboard` instead (recommended — kills the last
   Firebase dependency on a page).
2. **Deduplicate broken pages** — rebuild `map`, `notifications`, `profile`,
   `reports`, `users` from the first (correct) block and delete the duplicate.
3. **Finish `reports.html`** — use `bin_type`, pull real stats into the table.
4. **Finish `impact.html`** — add a `fetch('/api/stats')` loader for the metric IDs
   (treesSaved, co2Reduced, waterSaved, energySaved, progress bars).
5. **Wire locations/maintenance/users/map to real endpoints**, or explicitly mark
   them as planned.
6. **Reconnect notifications to Socket.IO** (`bin_update`) + a real unread store
   (e.g. extend `activity` with a `read` flag).
7. **Wire `pwa.js`** into pages, fix the SW cache list (drop dead CSS, add real
   pages), and commit real logo assets.
8. **Clean up legacy** — remove or archive the Firebase JS modules and orphaned CSS,
   or bundle the useful parts (charts.js, theme-switcher.js) via a build step.
9. **Add server-side evaluation** for challenges and anomaly-based badge logic
   (`zero_overflow`, `night_owl`, `data_nerd`, `collector_10/50` are currently not
   computed anywhere).
10. **Protect admin endpoints**, add CSRF protection for authenticated state-changing
    routes, and manage Telegram creds via settings (the backend already exposes a
    test endpoint).

---

## 18. Production Deployment

All config is environment-driven via `backend/.env` (see `backend/.env.example`).
Real environment variables always override the file. No secrets are hardcoded.

```bash
# 1. Configure the environment
cd backend
cp .env.example .env
# → edit .env: SECRET_KEY (REQUIRED), DEBUG=false, CORS_ORIGIN, tokens...
```

**0.1. Run with Gunicorn (production, not `app.py`)**

Socket.IO keeps state in-process, so use **one** eventlet worker:

```bash
cd backend
gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:5000 --timeout 120 app:app
```

**0.2. Run with Docker**

```bash
docker compose up -d --build
# → http://localhost:5000
```

- Port `5000` is exposed.
- SQLite (`waste.db`) is stored in a named Docker volume (`waste_data`), mounted at
  `/data`, so all data survives container restarts/rebuilds. Override via `DB_URL`.
- The container runs gunicorn (eventlet, 1 worker) automatically.

**Environment variables**

| Variable            | Required | Default                  | Purpose                              |
| ------------------- | -------- | ------------------------ | ------------------------------------ |
| `SECRET_KEY`        | yes      | *(empty)*                | Flask session signing key            |
| `DB_URL`            | no       | `backend/waste.db` / `/data/waste.db` | SQLite database path     |
| `CORS_ORIGIN`       | no       | `http://localhost:5000`  | Allowed origins (comma-separated)    |
| `DEBUG`             | no       | `false`                  | Flask/Socket.IO debug mode           |
| `HOST` / `PORT`     | no       | `0.0.0.0` / `5000`       | Bind address (local `app.py` run)    |
| `DEVICE_TOKEN`      | no       | *(empty)*                | Reserved for IoT device auth         |
| `TELEGRAM_BOT_TOKEN`| no       | *(empty)*                | Telegram alerts bot token            |
| `TELEGRAM_CHAT_ID`  | no       | *(empty)*                | Telegram receiver chat id            |

**CI** — `.github/workflows/ci.yml` installs `requirements.txt` and runs
`pytest -q` from `backend/` on every push/PR.

---

*Last updated: hand-over snapshot (repo not yet a git repository). Database is in
seed state — no user/sensor records present. All structural decisions documented
above reflect the code as found.*