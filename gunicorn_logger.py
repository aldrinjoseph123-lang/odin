"""Access log without secrets (system map #18).

Guest, sign-up, sign-in and password-reset links carry their credential in
the path, so gunicorn's access log would keep a reusable copy of each one.
The Dockerfile runs gunicorn with --logger-class gunicorn_logger.RedactingLogger,
which writes those paths as /guest/[redacted] and the like. Cloudflare's own
request logs are outside Odin's reach.
"""
import re

SECRET_PATH = re.compile(r"/(guest|join|auth/link|auth/reset|api/join)/[^/?\s\"]+")


def redact(text):
    return SECRET_PATH.sub(lambda m: f"/{m.group(1)}/[redacted]", text or "")


try:
    from gunicorn.glogging import Logger
except ImportError:   # the development server and the tests run without gunicorn
    Logger = None

if Logger is not None:
    class RedactingLogger(Logger):
        def atoms(self, resp, req, environ, request_time):
            atoms = super().atoms(resp, req, environ, request_time)
            for key in ("r", "U", "f"):   # request line, path, referer
                if isinstance(atoms.get(key), str):
                    atoms[key] = redact(atoms[key])
            return atoms


if __name__ == "__main__":
    assert redact("GET /guest/Ab_9-x/stage HTTP/1.1") == "GET /guest/[redacted]/stage HTTP/1.1"
    assert redact("/auth/link/tok123?next=/projects/1") == "/auth/link/[redacted]?next=/projects/1"
    assert redact("/join/xyz") == "/join/[redacted]" and redact("/projects/1") == "/projects/1"
    print("ok")
