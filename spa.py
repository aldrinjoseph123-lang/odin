"""Serves the Vite-built React app (frontend/dist) for routes that have been
ported, and nothing else — un-ported pages keep rendering their Jinja
templates. That is the whole strangler mechanism: add a page's endpoint name
to SPA_PAGES once its React version has passed tests and UAT.

Serving is off when there is no build (fresh checkout, unit-test run) and can
be forced off with app.config["SERVE_SPA"] = False.
"""
import os

from flask import current_app, send_from_directory

DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")

# Endpoint names whose GET is answered by the React app.
SPA_PAGES = {"login", "board", "dashboard", "people", "person", "projects_list", "project_detail", "users", "audit_logs_view", "settings", "settings_section", "settings_rbac", "settings_contacts", "project_new", "project_edit", "account", "my_work", "analytics", "alerts_log_view", "report_all", "report_single", "project_signoff", "join_page", "auth_link_request", "auth_reset_request", "auth_reset_form", "auth_link_consume", "login_password"}


def spa_available():
    if current_app.config.get("SERVE_SPA") is False:
        return False
    return os.path.exists(os.path.join(current_app.config.get("SPA_DIST", DIST_DIR), "index.html"))


def spa_serves(endpoint):
    return endpoint in SPA_PAGES and spa_available()


def spa_index():
    response = send_from_directory(current_app.config.get("SPA_DIST", DIST_DIR), "index.html")
    # The shell is tiny and must never be cached: it names hashed asset files
    # that change on every build.
    response.headers["Cache-Control"] = "no-store"
    return response


def spa_asset(filename):
    # Hashed filenames → safe to cache hard.
    response = send_from_directory(os.path.join(current_app.config.get("SPA_DIST", DIST_DIR), "assets"), filename)
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response
