"""Application entrypoint / route aggregator.

The Flask app object and request glue live in core.py; every handler lives in
the routes/ package. This module wires them together — importing each routes
submodule registers its handlers on the shared app — and re-exports the handful
of names that the test suite and the cron scripts import from `app`.
"""
from datetime import datetime, timedelta  # noqa: F401 — re-exported for tests

import graph  # noqa: F401 — re-exported for tests
from constants import CONTACT_LISTS, PERMISSIONS  # noqa: F401 — re-exported for tests
from core import app
from db import (  # noqa: F401 — re-exported for tests + backup.py
    DB_PATH,
    UPLOAD_DIR,
    init_db,
    migrate_db,
    set_setting,
)

# Importing each submodule registers its @app.route handlers on the shared app.
import routes.ai  # noqa: E402,F401
import routes.api  # noqa: E402,F401
import routes.auth  # noqa: E402,F401
import routes.board  # noqa: E402,F401
import routes.client  # noqa: E402,F401
import routes.guest  # noqa: E402,F401
import routes.mfa  # noqa: E402,F401
import routes.integrations  # noqa: E402,F401
import routes.projects  # noqa: E402,F401
import routes.settings  # noqa: E402,F401
import routes.signoff  # noqa: E402,F401
import routes.signup  # noqa: E402,F401
import routes.doc_templates  # noqa: E402,F401
import routes.sso  # noqa: E402,F401
import routes.tokens  # noqa: E402,F401
import routes.users  # noqa: E402,F401


if __name__ == "__main__":
    init_db()
    import os
    # Loopback only unless HOST says otherwise (P2-5), and the interactive debugger
    # (which answers anyone who can reach the port) only when ODIN_DEBUGGER=1.
    app.run(debug=True, use_debugger=os.environ.get("ODIN_DEBUGGER", "0") == "1",
            host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5050")))
