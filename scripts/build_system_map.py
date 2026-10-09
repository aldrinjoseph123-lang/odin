"""Regenerate the facts in docs/system-map.html from the repository itself.

The Odin System Map has two kinds of content: what a person wrote (flows,
permissions, loopholes) and what the repository can say for itself. This
script produces the second kind: every folder and tracked file with a one-line
description taken from the file's own docstring or header comment, line
counts, every test by suite, the CI jobs, the Docker build stages, the compose
services, the latest releases and a few counts (routes, tables, policies).

It reads the last commit (HEAD), not the working copy, so unfinished edits
never make the map look stale, and it leaves out the page's own size, so
regenerating is a fixed point. Output is deterministic (no clock, no commit
hash): `--check` tells whether the page matches HEAD, and the Stop hook
(scripts/system_map_stale.sh) runs it.

    python3 scripts/build_system_map.py           # rewrite the page
    python3 scripts/build_system_map.py --check   # exit 1 when out of date

Standard library only: it runs from the hook without the app's virtualenv.
"""
import ast
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "docs", "system-map.html")
START, END = "<!-- REPO-DATA:START -->", "<!-- REPO-DATA:END -->"
BINARY = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".pdf", ".zip")

# How the repository is organised: one line per folder that matters. The
# file lines come from the files themselves; these say what a folder is for.
FOLDERS = {
    "": "The Flask application: one module per concern at the top level, HTTP endpoints in routes/, logic in services/.",
    "routes": "HTTP endpoints grouped by area. Each checks sign-in, permission and project role, then calls services/ and writes the audit trail.",
    "services": "Business logic with no HTTP: plans, reports, sign-off, notifications, alerts, activity, templates, two-step sign-in. Called by routes/ and the scheduler.",
    "templates": "Jinja pages. Only the guest pages, the fallback sign-in form and the error page are still served; the rest are fallbacks when no React build exists.",
    "static": "The legacy stylesheet for the remaining Jinja pages (frozen: defects only).",
    "frontend": "The React app (Vite + TypeScript + shadcn/ui). Built into frontend/dist by Docker and CI; Flask serves the bundle.",
    "frontend/src": "React source: the entry point, the router and the design tokens (index.css).",
    "frontend/src/pages": "One file per screen, plus its page test (*.test.tsx) where it has one.",
    "frontend/src/components": "Shared pieces: the app shell, panels, editors, widgets; ui/ holds the shadcn primitives.",
    "frontend/src/components/ui": "shadcn/ui primitives (buttons, inputs, popovers…) styled through the tokens.",
    "frontend/src/lib": "Pure helpers (formatting, plans, dashboard packing, theme) with unit tests, and api.ts, the one client for the JSON API.",
    "frontend/e2e": "The Playwright UI suite: smoke, journeys, accessibility, keyboard, screenshots, plus the Lighthouse budget.",
    "frontend/e2e/visual.spec.ts-snapshots": "Golden screenshots for the visual tests (Linux, refreshed through the CI workflow).",
    "frontend/public": "Files served as they are: icons and the web manifest.",
    "scripts": "Operational scripts: UAT seed data, password reset from the shell, and the system map's generator and freshness check.",
    "deploy": "nginx configurations for the two deployment shapes (TLS on the box, or behind a Cloudflare tunnel).",
    "docs": "Go-live runbook, brand guide, UAT scripts and results, and this system map.",
    "docs/brand": "Logo, mark and wordmark files.",
    ".github/workflows": "CI: Python tests, the front-end build, the UI suite and the Docker image, on every push.",
    ".claude": "Claude Code project settings: the Stop hook that keeps this map current, and the dev-server launchers.",
    ".impeccable": "Design-review notes, mock-ups and screenshots from the design passes.",
}
# Files whose first lines do not describe them.
FILES = {
    "requirements.txt": "Python dependencies, pinned.",
    "Dockerfile": "Two-stage image: Node builds the React bundle, then a slim Python image runs gunicorn as an unprivileged user.",
    "docker-compose.yml": "The base stack: app, scheduler and nginx sharing the odin-data volume.",
    "docker-compose.host-tunnel.yml": "Production overlay: nginx on 127.0.0.1:8080 for the cloudflared service on the host.",
    "docker-compose.cloudflare.yml": "Alternative overlay: cloudflared as a container.",
    "frontend/package.json": "Front-end dependencies and the dev, build, test and e2e scripts.",
    "frontend/package-lock.json": "Exact front-end dependency versions.",
    "frontend/index.html": "The HTML shell; sets the theme and accent before first paint.",
    "frontend/vite.config.ts": "Vite build and the dev proxy to Flask.",
    "frontend/playwright.config.ts": "Playwright: one seeded database, one worker, desktop and phone projects.",
    "frontend/components.json": "shadcn/ui settings.",
    "frontend/tsconfig.json": "TypeScript project references.",
    "frontend/tsconfig.app.json": "TypeScript settings for the app.",
    "frontend/tsconfig.node.json": "TypeScript settings for build tooling.",
    "frontend/.oxlintrc.json": "Lint rules.",
    ".gitignore": "Keeps data, builds and secrets out of git.",
    ".claude/settings.json": "Claude Code hooks: the Stop hook that keeps the system map current.",
    ".claude/launch.json": "Dev-server launchers for the preview browser.",
    "docs/system-map.html": "This page: the Odin System Map, published as an artifact.",
    "schema.sql": "The database schema: every table, created on first start; later columns are added by migrations in db.py.",
    "test_app.py": "The Python test suite: routes, permissions, audit coverage, sign-in, reports, sign-off, scheduler jobs.",
    "test_fix_security.py": "Tests for the 9 Oct security and input-validation round: data exposure, sign-in links, typed inputs, JSON errors.",
    "test_fix_logic.py": "Tests for the 9 Oct logic round: working-day clocks, counts that agree, sign-off rules, purge and undo.",
    ".env.example": "The settings a deployment needs in .env (SECRET_KEY first).",
    ".dockerignore": "Keeps secrets, data and dev state out of the Docker image.",
    "frontend/src/main.tsx": "Entry point: mounts the React app with its router.",
    "frontend/src/lib/utils.ts": "The class-name helper shadcn components share.",
    "frontend/src/pages/Alerts.tsx": "Screen: Alerts — overdue, due soon, over SLA and stale rollouts.",
    "frontend/src/pages/Analytics.tsx": "Screen: Cycle time — how long stages take, throughput and lead time.",
    "frontend/src/pages/Audit.tsx": "Screen: Audit log — filter and export the trail.",
    "frontend/src/pages/Contacts.tsx": "Screen: Contacts and partners (Settings).",
    "frontend/src/pages/Users.tsx": "Screen: Users — accounts, roles, approvals, sign-up links.",
    "deploy/certs/.gitkeep": "Keeps the folder for TLS certificates (never committed).",
    "frontend/.gitignore": "Keeps builds and test output out of git.",
}


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout


HEAD = {}   # path -> text (None for binary), as committed at HEAD


def load_head():
    paths = [p for p in git("ls-tree", "-r", "--name-only", "HEAD").splitlines() if p]
    proc = subprocess.run(["git", "cat-file", "--batch"], cwd=ROOT, input="".join(f"HEAD:{p}\n" for p in paths).encode(), capture_output=True)
    out, i = proc.stdout, 0
    for path in paths:
        header_end = out.index(b"\n", i)
        size = int(out[i:header_end].split()[2])
        blob = out[header_end + 1: header_end + 1 + size]
        i = header_end + 1 + size + 1
        try:
            HEAD[path] = None if path.lower().endswith(BINARY) else blob.decode("utf-8")
        except UnicodeDecodeError:
            HEAD[path] = None


def tracked(prefix=""):
    return sorted(p for p in HEAD if p.startswith(prefix))


def first_sentence(text, limit=220):
    text = " ".join(text.split())
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    out = m.group(1) if m else text
    return out if len(out) <= limit else out[: limit - 1].rstrip() + "…"


def describe(path, text):
    if path in FILES:
        return FILES[path]
    ext = os.path.splitext(path)[1]
    name = os.path.basename(path)
    if path.startswith("frontend/src/components/ui/"):
        return f"shadcn/ui primitive: {os.path.splitext(name)[0]}."
    if re.search(r"\.test\.tsx?$", name):
        return f"Tests for {name.split('.test.')[0]}."
    if name == "__init__.py":
        return "Package marker."
    if ext == ".svg":
        return "Vector artwork."
    if ext == ".py":
        try:
            doc = ast.get_docstring(ast.parse(text))
        except SyntaxError:
            doc = None
        return first_sentence(doc) if doc else ""
    if ext in (".ts", ".tsx", ".mjs", ".js", ".css"):
        lines = []
        for line in text.splitlines()[:80]:
            s = line.strip()
            if s.startswith("//") and not s.startswith("// @ts") and "eslint" not in s:
                lines.append(s[2:].strip())
            elif s.startswith("/*") and not lines:
                lines.append(s.strip("/* "))
            elif lines:
                break
        return first_sentence(" ".join(lines)) if lines else ""
    if ext == ".md":
        for line in text.splitlines():
            if line.startswith("#"):
                return line.lstrip("# ").strip()
        return ""
    if ext == ".html" and path.startswith("templates/"):
        m = re.search(r"{%\s*block title\s*%}(.*?){%", text)
        return f"Jinja page: {m.group(1).strip()}" if m else "Jinja partial or layout"
    if ext in (".sh", ".yml", ".yaml", ".conf", ".sql"):
        lines = []
        for line in text.splitlines()[:30]:
            s = line.strip()
            if s.startswith("#!"):
                continue
            if s.startswith("#") or s.startswith("--"):
                lines.append(s.lstrip("#-").strip())
            elif lines or s:
                break
        return first_sentence(" ".join(lines)) if lines else ""
    return ""


def tree():
    files = tracked()
    folders = {}
    lang = {}
    for path in files:
        folder = os.path.dirname(path)
        name = os.path.basename(path)
        ext = os.path.splitext(name)[1].lower() or name
        entry = {"name": name}
        if ext in BINARY:
            entry["kind"] = ext.lstrip(".").upper()
        else:
            text = HEAD[path]
            if path == "docs/system-map.html":
                entry["desc"] = FILES[path]
            elif text is None:
                entry["kind"] = "binary"
            else:
                n = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
                entry["lines"] = n
                d = describe(path, text)
                if d:
                    entry["desc"] = d
                key = {".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".html": "HTML", ".md": "Markdown",
                       ".css": "CSS", ".sql": "SQL"}.get(ext)
                if key:
                    lang[key] = lang.get(key, 0) + n
        folders.setdefault(folder, []).append(entry)
    # every ancestor exists, even with no direct files
    for folder in list(folders):
        while folder:
            folder = os.path.dirname(folder)
            folders.setdefault(folder, [])
    out = [{"path": f, "note": FOLDERS.get(f, ""), "files": sorted(folders[f], key=lambda e: e["name"].lower())}
           for f in sorted(folders)]
    return out, len(files), lang


def python_tests():
    classes = []
    for node in [n for f in ("test_app.py", "test_fix_security.py", "test_fix_logic.py") for n in ast.parse(HEAD.get(f, "")).body]:
        if isinstance(node, ast.ClassDef):
            tests = [f.name[5:].replace("_", " ") for f in node.body if isinstance(f, ast.FunctionDef) and f.name.startswith("test_")]
            if tests:
                classes.append({"name": node.name, "tests": tests})
    return classes


STR = r"""(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)'|`((?:[^`\\]|\\.)*)`)"""


def js_names(text, words):
    out = []
    for m in re.finditer(r"^\s*(" + "|".join(words) + r")(?:\.\w+)?\(\s*" + STR, text, re.M):
        name = next(g for g in m.groups()[1:] if g is not None)
        out.append({"kind": m.group(1), "name": re.sub(r"\$\{[^}]*\}", "…", name)})
    return out


def front_tests():
    unit, ui, e2e = [], [], []
    for path in tracked("frontend/"):
        if re.search(r"\.test\.tsx?$", path):
            items = js_names(HEAD[path], ["describe", "it", "test"])
            (ui if path.endswith(".tsx") else unit).append({"file": path, "items": items})
        elif path.startswith("frontend/e2e/") and path.endswith(".spec.ts"):
            items = js_names(HEAD[path], ["test"])
            for it in items:
                it["tags"] = sorted(set(re.findall(r"@(\w+)", it["name"])))
                it["name"] = re.sub(r"@\w+\s*", "", it["name"]).strip()
            e2e.append({"file": path, "items": items})
    return unit, ui, e2e


def self_checks():
    out = []
    for path in tracked("services/"):
        if path.endswith(".py") and '__name__ == "__main__"' in HEAD[path]:
            out.append(path)
    return sorted(out)


def ci_jobs():
    text = HEAD.get(".github/workflows/ci.yml", "")
    jobs = []
    for m in re.finditer(r"^  ([\w-]+):\n    name: \"?(.+?)\"?$", text, re.M):
        body = text[m.end():]
        nxt = re.search(r"^  [\w-]+:\n    name:", body, re.M)
        body = body[: nxt.start()] if nxt else body
        steps = re.findall(r"^\s+- name: (.+)$", body, re.M)
        jobs.append({"id": m.group(1), "name": m.group(2), "steps": steps})
    triggers = re.findall(r"^  (push|pull_request|workflow_dispatch|schedule):", text, re.M)
    return {"triggers": triggers, "jobs": jobs}


def docker():
    text = HEAD.get("Dockerfile", "")
    stages = [{"from": m.group(1), "as": m.group(2) or ""} for m in re.finditer(r"^FROM\s+(\S+)(?:\s+AS\s+(\S+))?", text, re.M)]
    cmd = re.search(r"^CMD\s+(\[.*?\])", text, re.M | re.S)
    compose = {}
    for name in ("docker-compose.yml", "docker-compose.host-tunnel.yml", "docker-compose.cloudflare.yml"):
        body = HEAD.get(name)
        if body is None:
            continue
        block = body.split("\nservices:\n", 1)[1] if "\nservices:\n" in body else ""
        block = re.split(r"^\S", block, maxsplit=1, flags=re.M)[0]
        compose[name] = re.findall(r"^  ([\w-]+):", block, re.M)
    return {"stages": stages, "cmd": " ".join(json.loads(re.sub(r"\\\n", "", cmd.group(1)))) if cmd else "", "compose": compose}


def releases():
    out = []
    for line in git("for-each-ref", "--sort=-creatordate", "--count=8", "--format=%(refname:short)\t%(creatordate:short)\t%(contents:subject)", "refs/tags").splitlines():
        tag, day, subject = (line.split("\t") + ["", ""])[:3]
        out.append({"tag": tag, "date": day, "subject": subject})
    return out


# Which part of Odin a changed file belongs to, first match wins.
AREAS = [
    ("Tests", r"^(test_\w+\.py|frontend/e2e/|.*\.test\.tsx?$)"),
    ("Screens", r"^frontend/"),
    ("Deployment", r"^(Dockerfile|docker-compose|deploy/|\.github/|docker-entrypoint\.sh|requirements\.txt|preflight\.py|\.dockerignore|\.gitignore|\.env\.example|VERSION$)"),
    ("Docs", r"(\.md$|^docs/)"),
    ("Tooling", r"^(scripts/|\.claude/|\.impeccable/)"),
    ("Server", r"."),
]
MAP_ONLY = {"docs/system-map.html"}


def area_of(path):
    return next(name for name, rx in AREAS if re.search(rx, path))


def changelog():
    """Every change by release: the tags in order, then what is after the last
    tag, named by VERSION. A commit that only regenerates this page is left
    out, so regenerating never changes the log it writes."""
    version = (HEAD.get("VERSION") or "").strip()
    tags = [t for t in git("tag", "--sort=creatordate").splitlines() if t]
    reachable = set(git("tag", "--merged", "HEAD").splitlines())
    tags = [t for t in tags if t in reachable]
    ranges, prev = [], None
    for t in tags:
        ranges.append((t, f"{prev}..{t}" if prev else t))
        prev = t
    ranges.append((None, f"{prev}..HEAD" if prev else "HEAD"))
    out = []
    for tag, rng in ranges:
        log = git("log", "--no-merges", "--format=%x1e%h%x1f%cs%x1f%s%x1f%b%x1f", "--name-only", rng)
        commits = []
        for chunk in log.split("\x1e")[1:]:
            short, day, subject, body, files = (chunk.split("\x1f") + [""] * 5)[:5]
            files = [f for f in files.split("\n") if f.strip()]
            if not files or set(files) <= MAP_ONLY:
                continue
            body = "\n".join(l for l in body.strip().splitlines() if not l.startswith("Co-Authored-By")).strip()
            tally = {}
            for f in files:
                a = area_of(f)
                tally[a] = tally.get(a, 0) + 1
            order = [a for a, _ in AREAS]
            main = max(tally, key=lambda a: (tally[a], -order.index(a)))
            commits.append({"id": short, "date": day, "subject": subject, "body": body[:1500], "files": len(files),
                            "area": main, "areas": sorted(tally, key=order.index)})
        if tag is None and not commits:
            continue
        if tag:
            info = git("for-each-ref", "--format=%(creatordate:short)\t%(contents:subject)", f"refs/tags/{tag}").strip().split("\t")
            entry = {"version": tag, "date": info[0], "title": re.sub(r"^Odin [\d.]+: ?", "", info[1] if len(info) > 1 else "")}
        else:
            named = version and f"v{version}" not in tags
            entry = {"version": f"v{version}" if named else "Next release", "date": commits[0]["date"], "title": "", "untagged": True}
        entry["current"] = entry["version"] == f"v{version}"
        entry["commits"] = commits
        out.append(entry)
    return {"version": version, "releases": list(reversed(out))}


def counts():
    def grep(pattern, *paths):
        n = 0
        for p in paths:
            for path in tracked(p):
                n += len(re.findall(pattern, HEAD[path] or "", re.M))
        return n
    return {
        "routes": grep(r"^@app\.route\(", "routes", "core.py", "app.py"),
        "tables": grep(r"CREATE TABLE", "schema.sql"),
        "policies": grep(r"^\s+\"\w+\": dict\(area=", "policies.py"),
        "pages": len([p for p in tracked("frontend/src/pages/") if p.endswith(".tsx") and ".test." not in p]),
    }


def build():
    if not HEAD:
        load_head()
    folders, nfiles, lang = tree()
    unit, ui, e2e = front_tests()
    py = python_tests()
    return {
        "files": nfiles, "lines": lang, "counts": counts(), "folders": folders,
        "tests": {"python": py, "unit": unit, "ui": ui, "e2e": e2e, "self_checks": self_checks(),
                  "totals": {"python": sum(len(c["tests"]) for c in py),
                             "unit": sum(sum(1 for i in f["items"] if i["kind"] != "describe") for f in unit),
                             "ui": sum(sum(1 for i in f["items"] if i["kind"] != "describe") for f in ui),
                             "e2e": sum(len(f["items"]) for f in e2e)}},
        "ci": ci_jobs(), "docker": docker(), "releases": releases(), "changelog": changelog(),
    }


def render(page, data):
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True).replace("</", "<\\/")
    block = f'{START}\n<script type="application/json" id="repo-data">{blob}</script>\n{END}'
    head, rest = page.split(START, 1)
    return head + block + rest.split(END, 1)[1]


def main():
    page = open(PAGE, encoding="utf-8").read()
    new = render(page, build())
    if "--check" in sys.argv:
        sys.exit(0 if new == page else 1)
    if new != page:
        with open(PAGE, "w", encoding="utf-8") as fh:
            fh.write(new)
        print("docs/system-map.html: repository facts updated")
    else:
        print("docs/system-map.html: already current")


if __name__ == "__main__":
    main()
