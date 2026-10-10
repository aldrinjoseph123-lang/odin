"""Serves the Vite-built React app (frontend/dist). Every signed-in page is
React; the Jinja pages were retired on 9 Oct 2026, leaving only the guest
project page, the sign-in form's error re-render and the error page.

Without a build (a fresh checkout) a page answers 503 with how to build one.
Tests point SPA_DIST at a stub shell.
"""
import os

from flask import current_app, send_from_directory

DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")


def spa_index():
    from security import csp_nonce
    path = os.path.join(current_app.config.get("SPA_DIST", DIST_DIR), "index.html")
    if not os.path.exists(path):
        return current_app.response_class("The front end is not built: run npm --prefix frontend run build", status=503, mimetype="text/plain")
    with open(path, encoding="utf-8") as fh:
        html = fh.read()
    # the theme snippet runs before first paint: it carries this response's CSP nonce
    response = current_app.response_class(html.replace("<script>", f'<script nonce="{csp_nonce()}">'), mimetype="text/html")
    # The shell is tiny and must never be cached: it names hashed asset files
    # that change on every build.
    response.headers["Cache-Control"] = "no-store"
    return response


def spa_asset(filename):
    # Hashed filenames → safe to cache hard.
    response = send_from_directory(os.path.join(current_app.config.get("SPA_DIST", DIST_DIR), "assets"), filename)
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response
