"""Stage a realistic UAT dataset on a fresh data directory, through the app's
own routes where a rule or side effect matters (so every audit row and
notification is the real one), and straight into the tables for the bulk
history a dashboard needs (tasks over the past month, notes, snapshots).

    ODIN_DATA_DIR=/tmp/odin-uat python scripts/seed_uat.py

Then run the app against the same ODIN_DATA_DIR and sign in as
admin / Glacier-Harbour-4471. Never point this at production.
"""
import io
import os
import random
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("ODIN_DATA_DIR", os.path.join(os.path.dirname(HERE), "uat-data"))
os.makedirs(os.environ["ODIN_DATA_DIR"], exist_ok=True)

from app import app                      # noqa: E402
from db import DB_PATH, init_db          # noqa: E402

ADMIN_PASSWORD = "Glacier-Harbour-4471"
STAFF_PASSWORD = "Correct-Horse-Battery-9"
random.seed(7)   # the same portfolio every time

if os.path.exists(DB_PATH):
    sys.exit(f"{DB_PATH} already exists — seed a fresh ODIN_DATA_DIR")
init_db()
app.config["SERVE_SPA"] = False   # the Jinja forms carry the CSRF field the seed needs

STAFF = [("pm1", "Priya Menon", "Member"), ("pm2", "Tom Keller", "Member"), ("sales1", "Sara Lind", "Contributor"),
         ("eng1", "Omar Haddad", "Contributor"), ("eng2", "Lena Fischer", "Contributor"), ("vw1", "Viewer One", "Viewer")]
CLIENTS = ["Globex", "Initech", "Acme Bank", "Umbrella Health", "Stark Logistics", "Wayne Retail", "Hooli", "Vandelay Industries"]
KINDS = ["EDR rollout", "SIEM onboarding", "Firewall refresh", "MDR onboarding", "Email security", "Vulnerability mgmt"]
TASKS = ["Collect asset inventory", "Confirm change window", "Deploy agents to pilot group", "Review detection coverage", "Tune noisy rules",
         "Onboard firewall logs", "Customer sign-off on scope", "Schedule cutover", "Validate backups", "Hand over runbook",
         "Set up SSO for console", "Train the SOC on the new source"]
NOTES = ["Kick-off held, scope agreed with the customer.", "Waiting on the change window from the customer's IT.", "Pilot group live, no issues in 48 h.",
         "Firewall vendor confirmed the log format.", "Two endpoints failed enrolment — hardware too old, excluded from scope.",
         "Customer asked to add the branch office; PO amendment requested.", "Runbook draft shared for review.", "Cutover done over the weekend."]

with app.test_client() as c:
    def csrf(path="/login"):
        return re.search(r'name="_csrf" value="([^"]+)"', c.get(path).data.decode()).group(1)

    def post(path, **data):
        data.setdefault("_csrf", token)
        r = c.post(path, data=data)
        assert r.status_code in (200, 302), (path, r.status_code)
        return r

    c.post("/login", data={"username": "admin", "password": "changeme", "_csrf": csrf()})
    c.post("/account", data={"current_password": "changeme", "new_password": ADMIN_PASSWORD, "_csrf": csrf("/account")})
    token = csrf("/board")

    for u, name, r in STAFF:
        post("/users", username=u, name=name, password=STAFF_PASSWORD, role=r)
    con = sqlite3.connect(DB_PATH)   # UAT staff keep the documented test password (production asks for a new one)
    con.execute("UPDATE users SET must_change_password = 0 WHERE username != 'admin'")
    con.commit()
    con.close()
    for v in ["CrowdStrike", "Palo Alto", "Microsoft", "Fortinet"]:
        post("/settings/contacts/vendors/add", name=v)
    # each product under its vendor (ids follow the list above)
    for p, vendor_id in [("Falcon Complete", "1"), ("Sentinel", "3"), ("Defender XDR", "3"), ("FortiGate", "4")]:
        post("/settings/contacts/products/add", name=p, vendor_id=vendor_id)
    post("/settings/contacts/outsourcers/add", name="VendorCo", email="ops@vendorco.example")
    post("/settings/contacts/partners/add", name="Redington")
    post("/settings/contacts/partners/1/managers/add", name="Meera", email="meera@redington.example")
    post("/settings/templates/add", name="EDR rollout")
    post("/settings/templates/add", name="SIEM onboarding")

    con = sqlite3.connect(DB_PATH)
    edr = con.execute("SELECT id FROM stage_templates WHERE name='EDR rollout'").fetchone()[0]
    siem = con.execute("SELECT id FROM stage_templates WHERE name='SIEM onboarding'").fetchone()[0]
    kick = con.execute("SELECT id FROM stage_template_stages WHERE template_id=? AND name='Kickoff'", (edr,)).fetchone()[0]
    con.close()
    post(f"/settings/templates/{edr}/stages/{kick}/rename", name="Sensor pilot")
    post(f"/settings/templates/{edr}/stages/add", name="Fleet rollout")
    post(f"/settings/templates/{siem}/stages/add", name="Log source onboarding")
    post(f"/settings/templates/{siem}/stages/add", name="Use-case tuning")

    def proj(name, client, **fields):
        data = {"po_document": (io.BytesIO(b"%PDF-1.4 fake PO"), "po.pdf"), "name": name, "client": client, "_csrf": token}
        data.update(fields)
        assert c.post("/projects/new", data=data).status_code == 302, name

    today = date.today()
    proj("EDR Rollout - Globex", "Globex", stage_template_id=edr, vendor_name="CrowdStrike", product_name="Falcon Complete",
         target_end_date=(today + timedelta(days=62)).isoformat(), po_number="PO-GLX-0091", customer_approval="1", team_user_ids="2")
    proj("SIEM Onboarding - Acme", "Acme Bank", stage_template_id=siem, delivery_mode="Outsourced", outsourcer_name="VendorCo",
         outsourcer_email="ops@vendorco.example", target_end_date=(today + timedelta(days=16)).isoformat(), po_number="PO-ACME-4471")
    proj("Firewall refresh - Initech", "Initech", target_end_date=(today + timedelta(days=82)).isoformat(), via="Partner", partner_name="Redington",
         partner_account_manager_name="Meera", partner_account_manager_email="meera@redington.example", vendor_name="Palo Alto")
    # a portfolio: 20 more rollouts of every kind, some late, some far out, a few closed
    for i in range(20):
        kind, client = KINDS[i % len(KINDS)], CLIENTS[(i * 3) % len(CLIENTS)]
        offset = random.choice([-40, -12, -3, 5, 14, 30, 45, 60, 90, 120])
        proj(f"{kind} - {client}", client, stage_template_id=edr if i % 2 else siem,
             target_end_date=(today + timedelta(days=offset)).isoformat(), po_number=f"PO-{client[:3].upper()}-{1000 + i}",
             vendor_name=random.choice(["CrowdStrike", "Palo Alto", "Microsoft", "Fortinet"]),
             **({"customer_approval": "1"} if i % 5 == 0 else {}))   # a checkbox: present means on

    # the first three, as before: real moves through the routes
    post("/projects/1/stage", stage="Scoping", note="Scope agreed")
    post("/projects/1/stage", stage="Sensor pilot", note="Pilot group of 50 endpoints")
    post("/projects/1/tasks", title="Collect asset inventory", assignee_id="4", due_date=(today - timedelta(days=4)).isoformat())
    post("/projects/1/tasks", title="Deploy sensors to pilot group", due_date=(today + timedelta(days=3)).isoformat(), stage="Sensor pilot")
    for s in ["Scoping", "Kickoff", "Deployment", "Log source onboarding"]:
        post("/projects/2/stage", stage=s, note=f"Now in {s}")
    post("/projects/2/tasks", title="Onboard firewall logs", assignee_id="2", stage="Log source onboarding")
    post("/projects/1/participants/invite", email="jane@vendorco.example", name="Jane Okafor", role="Contractor")
    post("/projects/1/participants/invite", email="ann@globex.example", name="Ann Reyes", role="Customer")

    # move the portfolio along: each rollout to a plausible stage, through the route (approvals, notes, audit)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    plan = {}
    for p in con.execute("SELECT id, name FROM projects WHERE id > 3 ORDER BY id"):
        stages = [r["name"] for r in con.execute("SELECT name FROM project_stages WHERE project_id = ? ORDER BY position", (p["id"],))]
        depth = random.choice([0, 1, 1, 2, 2, 3, 4, 5, len(stages) - 1])
        if p["id"] in (8, 14, 19):   # three reach the end of the work: the sign-off stories below
            depth = stages.index("Sign-off")
        plan[p["id"]] = stages[1:depth + 1]
    con.close()
    for pid, path in plan.items():
        for s in path:
            post(f"/projects/{pid}/stage", stage=s, note=f"Now in {s}")   # the last stage waits for the sign-off: those stop in Sign-off

    # the agreed scope of the first rollout: three delivered, one still open (the journey test marks it)
    hdr = {"X-CSRF-Token": token}
    for title, status in [("Falcon sensor on 1,200 endpoints", "delivered"), ("Prevention policies tuned to the baseline", "delivered"),
                          ("SOC runbook and handover session", "delivered"), ("Alerts forwarded to the customer's SIEM", "agreed")]:
        r = c.post("/api/projects/1/scope", json={"title": title}, headers=hdr)
        assert r.status_code == 200, r.data
        if status != "agreed":
            c.put(f"/api/projects/1/scope/{r.get_json()['id']}", json={"status": status}, headers=hdr)
    # rollouts that reached Sign-off: a customer contact each, the scope marked, and a sign-off in every state
    con = sqlite3.connect(DB_PATH)
    waiting = [r[0] for r in con.execute("SELECT id FROM projects WHERE stage = 'Sign-off' ORDER BY id")]
    con.close()
    con = sqlite3.connect(DB_PATH)
    for pid in waiting[:3]:   # they began two months ago (the history pass below keeps these dates)
        con.execute("UPDATE projects SET start_date = date('now', '-62 days'), created_at = datetime('now', '-62 days') WHERE id = ?", (pid,))
    con.commit()
    con.close()
    for n, pid in enumerate(waiting[:3]):
        post(f"/projects/{pid}/participants/invite", email=f"signer{pid}@customer.example", name=["Mia Chen", "Raj Patel", "Eva Novak"][n], role="Customer")
        for title in ["Agents deployed to every in-scope endpoint", "Detection policies tuned", "Runbook and handover"]:
            item = c.post(f"/api/projects/{pid}/scope", json={"title": title}, headers=hdr).get_json()["id"]
            c.put(f"/api/projects/{pid}/scope/{item}", json={"status": "delivered"}, headers=hdr)
        d = c.get(f"/api/projects/{pid}/signoff").get_json()
        body = {"summary": d["draft"]["summary"], "delivered": [], "outstanding": d["draft"]["outstanding"][:2], "terms": d["draft"]["terms"],
                "signer_id": d["candidates"]["signers"][0]["id"], "counter_id": d["candidates"]["default_counter_id"]}
        assert c.post(f"/api/projects/{pid}/signoff", json=body, headers=hdr).status_code == 200
        if n in (0, 2):   # the customer signed; for the first, we countersigned too and the project closed
            with app.test_request_context():
                from services import signoff as so
                strokes = [[[80 + k * 40, 180 + (30 if k % 2 else -30)] for k in range(12)]]
                so.sign(so.latest(pid), {"name": body and d["candidates"]["signers"][0]["name"], "title": "IT Director", "accept": True,
                                         "signature": {"kind": "drawn", "strokes": strokes}}, "203.0.113.7", "Seed")
                if n == 0:
                    so.countersign(so.latest(pid), {"name": "Admin", "title": "Delivery lead", "accept": True, "signature": {"kind": "typed", "text": "Admin"}}, "198.51.100.2", "Seed")
            if n == 0:
                con = sqlite3.connect(DB_PATH)
                last = con.execute("SELECT name FROM project_stages WHERE project_id = ? ORDER BY position DESC LIMIT 1", (pid,)).fetchone()[0]
                con.close()
                post(f"/projects/{pid}/stage", stage=last, note="Signed off by the customer")

# ---- history straight into the tables: a month of work, spread out ----
con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row
now = datetime.utcnow()
staff_ids = [r["id"] for r in con.execute("SELECT id FROM users WHERE username IN ('admin','pm1','pm2','sales1','eng1','eng2')")]
projects = con.execute("SELECT id, stage, owner_id FROM projects ORDER BY id").fetchall()
for p in projects:
    stages = [r["name"] for r in con.execute("SELECT name FROM project_stages WHERE project_id = ? ORDER BY position", (p["id"],))]
    at = stages.index(p["stage"]) if p["stage"] in stages else 0
    # the team: two or three staff besides the owner
    for uid in random.sample([u for u in staff_ids if u != p["owner_id"]], random.choice([1, 2, 3])):
        con.execute("INSERT OR IGNORE INTO project_participants (project_id, user_id, role, added_by, added_at) VALUES (?, ?, ?, 1, ?)",
                    (p["id"], uid, random.choice(["Sales", "Coordinator", "Coordinator"]), (now - timedelta(days=random.randint(5, 40))).isoformat()))
    # tasks: done ones in past stages, open ones in the current stage, due dates around today
    for k in range(random.randint(3, 6)):
        stage = stages[random.randint(0, at)] if stages else ""
        done = stage != p["stage"] or random.random() < 0.3
        created = now - timedelta(days=random.randint(6, 35))
        due = (created + timedelta(days=random.randint(3, 20))).date()
        con.execute(
            "INSERT INTO tasks (project_id, title, done, assignee_id, due_date, created_at, created_by, stage, done_at) VALUES (?, ?, ?, ?, ?, ?, 'admin', ?, ?)",
            (p["id"], random.choice(TASKS), int(done), random.choice(staff_ids + [None]), due.isoformat(), created.isoformat(), stage,
             min(created + timedelta(days=random.randint(1, 20), hours=random.randint(8, 18)), now - timedelta(hours=random.randint(1, 30))).isoformat() if done else None))
    # notes over the past three weeks
    for k in range(random.randint(0, 3)):
        when = now - timedelta(days=random.randint(0, 21), hours=random.randint(0, 9))
        con.execute("INSERT INTO status_notes (project_id, author, note, stage, created_at, author_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (p["id"], random.choice(["Priya Menon", "Tom Keller", "Omar Haddad", "Admin"]), random.choice(NOTES), p["stage"], when.isoformat(), None))
# spread "last touched" and time-in-stage so SLAs and idleness show
con.execute("UPDATE projects SET updated_at = datetime('now', ?) WHERE id IN (7, 12)", ("-41 days",))
con.execute("UPDATE projects SET stage_entered_at = datetime('now', '-9 days') WHERE id = 1")
con.execute("UPDATE projects SET stage_entered_at = datetime('now', '-16 days') WHERE id IN (9, 15)")
con.execute("UPDATE project_stages SET sla_days = 5 WHERE project_id = 1 AND name = 'Sensor pilot'")
con.execute("UPDATE project_stages SET sla_days = 7 WHERE project_id IN (9, 15) AND name = (SELECT stage FROM projects WHERE id = project_stages.project_id)")
# two weeks of snapshots, drifting toward today's numbers (synthetic history so deltas and sparklines have something to show)
for d in range(14, 0, -1):
    day = (date.today() - timedelta(days=d)).isoformat()
    con.execute("INSERT OR REPLACE INTO portfolio_snapshots (day, active, overdue, over_sla, due_soon, awaiting, idle) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (day, 18 + (14 - d) // 3, max(1, 6 - (14 - d) // 4), random.choice([1, 2, 3]), random.choice([1, 2]), random.choice([1, 2, 3]), random.choice([1, 2])))
con.commit()
con.close()

# ---- history in time: each rollout began weeks ago and moved through its stages since ----
con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row
RISKS = [("risk", "Customer change window may slip", "high", "medium"), ("risk", "Legacy endpoints below agent minimum", "medium", "high"),
         ("issue", "Proxy blocks the agent's cloud endpoint", "high", None), ("issue", "Log volume above the sizing estimate", "medium", None),
         ("blocker", "Waiting on firewall change approval", "high", None), ("decision", "Pilot on 50 endpoints before fleet", "medium", None),
         ("decision", "Weekend cutover agreed", "low", None)]
for p in con.execute("SELECT id, stage, target_end_date FROM projects ORDER BY id").fetchall():
    stages = con.execute("SELECT id, name, position, sla_days FROM project_stages WHERE project_id = ? ORDER BY position", (p["id"],)).fetchall()
    names = [r["name"] for r in stages]
    at = names.index(p["stage"]) if p["stage"] in names else 0
    began = now - timedelta(days=random.randint(25, 70))
    if con.execute("SELECT 1 FROM signoffs WHERE project_id = ?", (p["id"],)).fetchone():   # its sign-off already names the start
        began = datetime.fromisoformat(con.execute("SELECT created_at FROM projects WHERE id = ?", (p["id"],)).fetchone()[0])
    moves = con.execute("SELECT id FROM status_notes WHERE project_id = ? AND prev_stage IS NOT NULL ORDER BY id", (p["id"],)).fetchall()
    # the moves spread from the start to a few days ago, in order; the current stage entered at the last one
    span = (now - timedelta(days=random.randint(2, 12)) - began).total_seconds()
    stamps = sorted(began + timedelta(seconds=span * (k + 1) / (len(moves) + 1)) for k in range(len(moves)))
    for m, when in zip(moves, stamps):
        con.execute("UPDATE status_notes SET created_at = ? WHERE id = ?", (when.isoformat(), m["id"]))
    entered = stamps[-1] if stamps else began
    con.execute("UPDATE projects SET created_at = ?, start_date = ?, stage_entered_at = ? WHERE id = ?",
                (began.isoformat(), began.date().isoformat(), entered.isoformat(), p["id"]))
    # the plan as first agreed (the baseline): back to back from the start, SLA or 5-12 days a stage, a finish line at the end
    day, first = began.date(), []
    for i, r in enumerate(stages):
        length = 0 if i == len(stages) - 1 else (r["sla_days"] or random.randint(5, 12))
        first.append((r["id"], day, day + timedelta(days=length)))
        day += timedelta(days=length)
    for sid, s0, e0 in first:
        con.execute("UPDATE project_stages SET plan_start = ?, plan_end = ?, base_start = ?, base_end = ? WHERE id = ?",
                    (s0.isoformat(), e0.isoformat(), s0.isoformat(), e0.isoformat(), sid))
    con.execute("UPDATE projects SET baseline_at = ?, target_end_date = COALESCE(target_end_date, ?) WHERE id = ?",
                ((began + timedelta(days=1)).isoformat(), first[-1][2].isoformat(), p["id"]))
    # some rollouts re-planned since: the stages from the current one on moved later, with a reason in the log
    if random.random() < 0.55 and at < len(stages) - 1:
        slip = random.choice([3, 5, 7, 10, 14])
        why = random.choice(["Vendor delivery late", "Customer change freeze", "Scope added: branch office", "Waiting on firewall approval"])
        for sid, s0, e0 in first[at:]:
            name = next(r["name"] for r in stages if r["id"] == sid)
            con.execute("UPDATE project_stages SET plan_start = ?, plan_end = ? WHERE id = ?", ((s0 + timedelta(days=slip)).isoformat(), (e0 + timedelta(days=slip)).isoformat(), sid))
            con.execute("INSERT INTO plan_changes (project_id, stage, field, old, new, reason, author, created_at) VALUES (?, ?, 'end', ?, ?, ?, 'Priya Menon', ?)",
                        (p["id"], name, e0.isoformat(), (e0 + timedelta(days=slip)).isoformat(), why, (now - timedelta(days=random.randint(1, 10))).isoformat()))
    # a few RAID items each
    for kind, title, impact, likelihood in random.sample(RISKS, random.randint(1, 4)):
        status = {"decision": "decided"}.get(kind, random.choice(["open", "open", "mitigating" if kind == "risk" else "open", "closed"]))
        made = now - timedelta(days=random.randint(1, 20))
        con.execute("INSERT INTO raid_items (project_id, kind, title, impact, likelihood, status, owner_id, due_date, stage, resolution, customer_visible, created_by, created_at, updated_at, closed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Priya Menon', ?, ?, ?)",
                    (p["id"], kind, title, impact, likelihood, status, random.choice(staff_ids), (now + timedelta(days=random.randint(-5, 20))).date().isoformat(),
                     p["stage"], "Agreed in the weekly call" if status in ("closed", "decided") else None, int(kind in ("decision", "blocker")),
                     made.isoformat(), made.isoformat(), made.isoformat() if status in ("closed", "decided") else None))
con.commit()
con.close()

# a month of active minutes for the staff, and when each was last seen (People, Account)
con = sqlite3.connect(DB_PATH)
for (uid,) in con.execute("SELECT id FROM users WHERE kind = 'internal'").fetchall():
    for d in range(30):
        day = date.today() - timedelta(days=d)
        if day.weekday() < 5 and random.random() < 0.85:
            con.execute("INSERT OR REPLACE INTO user_activity (user_id, day, minutes) VALUES (?, ?, ?)", (uid, day.isoformat(), random.randint(15, 190)))
    con.execute("UPDATE users SET last_seen_at = ? WHERE id = ?", ((now - timedelta(minutes=random.randint(3, 60 * 30))).isoformat(), uid))
con.commit()
con.close()

# the daily check, so the alerts table holds what the portfolio deserves
with app.test_request_context():
    from db import get_db
    from services.alerts import build_alerts, sync_alerts_to_db
    rows = get_db().execute("SELECT p.* FROM projects p WHERE p.deleted_at IS NULL").fetchall()
    sync_alerts_to_db(build_alerts(rows))
    # the check ran nightly all along: age each alert a little
    for a in get_db().execute("SELECT id FROM alerts").fetchall():
        get_db().execute("UPDATE alerts SET created_at = ? WHERE id = ?", ((now - timedelta(days=random.randint(0, 9), hours=random.randint(1, 20))).isoformat(), a["id"]))
    get_db().commit()

con = sqlite3.connect(DB_PATH)
for row in con.execute("SELECT id, name, stage FROM projects ORDER BY id LIMIT 3"):
    print(f"   {row[1]} | {row[2]}")
n = con.execute("SELECT COUNT(*) FROM projects").fetchone()[0]; t = con.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
con.close()
print(f"Seeded {os.environ['ODIN_DATA_DIR']}: {n} projects, {t} tasks. Sign in as admin / {ADMIN_PASSWORD}; staff password {STAFF_PASSWORD}.")
print("Sign-in links for the two invited externals: open the project's Team panel and Invite them again to mint fresh ones.")
