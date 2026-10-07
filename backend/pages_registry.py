"""
Single source of truth for application navigation.

Every sidebar entry lives here. Adding a page in the future = adding one dict
(and a template under ``templates/pages/``); the ``_sidebar.html`` partial
renders the whole navigation from this list.

Fields:
    name           Display label (used verbatim in the nav link).
    path           URL path relative to the root, e.g. ``pages/analytics.html``.
                   The rendered href is ``/<path>`` and the current page is
                   highlighted by comparing ``request.path`` against it.
    icon           Corridor marker for the nav dot (a hex color). Kept as a
                   color to reproduce the original ``.nav-dot`` styling exactly.
    group          Sidebar group header. ``Overview`` is rendered without a
                   group header (the Dashboard is the first, ungrouped item).
    required_role  Role needed to see the entry (``None`` = visible to all);
                   matches the ``users.role`` column. ``"admin"`` is the only
                   privileged role currently used.
"""

NAV = [
    # ---------------- Overview ----------------
    {"name": "Dashboard", "path": "dashboard.html", "icon": "#00d4ff",
     "group": "Overview", "required_role": None},

    # ---------------- Monitoring ----------------
    {"name": "Wet Bin", "path": "pages/wet-bin.html", "icon": "#3498db",
     "group": "Monitoring", "required_role": None},
    {"name": "Dry Bin", "path": "pages/dry-bin.html", "icon": "#2ecc71",
     "group": "Monitoring", "required_role": None},
    {"name": "Analytics", "path": "pages/analytics.html", "icon": "#9b59b6",
     "group": "Monitoring", "required_role": None},
    {"name": "Map", "path": "pages/map.html", "icon": "#e74c3c",
     "group": "Monitoring", "required_role": None},
    {"name": "Reports", "path": "pages/reports.html", "icon": "#e67e22",
     "group": "Monitoring", "required_role": None},

    # ---------------- Engagement ----------------
    {"name": "Leaderboard", "path": "pages/leaderboard.html", "icon": "#f1c40f",
     "group": "Engagement", "required_role": None},
    {"name": "Impact", "path": "pages/impact.html", "icon": "#1abc9c",
     "group": "Engagement", "required_role": None},

    # ---------------- Account ----------------
    {"name": "Profile", "path": "pages/profile.html", "icon": "#8e44ad",
     "group": "Account", "required_role": None},
    {"name": "Settings", "path": "pages/settings.html", "icon": "#bdc3c7",
     "group": "Account", "required_role": None},
    {"name": "Notifications", "path": "pages/notifications.html", "icon": "#f39c12",
     "group": "Account", "required_role": None},

    # ---------------- Admin ----------------
    {"name": "Admin Portal", "path": "admin.html", "icon": "#f1c40f",
     "group": "Admin", "required_role": "admin"},
    {"name": "Users", "path": "pages/users.html", "icon": "#c0392b",
     "group": "Admin", "required_role": "admin"},
    {"name": "Maintenance", "path": "pages/maintenance.html", "icon": "#95a5a6",
     "group": "Admin", "required_role": "admin"},
    {"name": "Locations", "path": "pages/locations.html", "icon": "#00d4ff",
     "group": "Admin", "required_role": None},

    # ---------------- Support ----------------
    {"name": "Guide", "path": "pages/guide.html", "icon": "#16a085",
     "group": "Support", "required_role": None},
    {"name": "Help", "path": "pages/help.html", "icon": "#34495e",
     "group": "Support", "required_role": None},
]


def pages_for_role(role):
    """Return the navigation list filtered by ``role`` (``None`` = no auth)."""
    return [p for p in NAV if not p["required_role"] or p["required_role"] == role]