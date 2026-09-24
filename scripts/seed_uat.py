"""Stage a realistic UAT dataset on a fresh data directory, through the app's
own routes (so every rule, audit row and side effect is the real one).

    ODIN_DATA_DIR=/tmp/odin-uat python scripts/seed_uat.py

Then run the app against the same ODIN_DATA_DIR and sign in as
admin / Glacier-Harbour-4471. Never point this at production.
"""
import io
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("ODIN_DATA_DIR", os.path.join(os.path.dirname(HERE), "uat-data"))
os.makedirs(os.environ["ODIN_DATA_DIR"], exist_ok=True)

from app import app                      # noqa: E402
from db import DB_PATH, init_db          # noqa: E402

ADMIN_PASSWORD = "Glacier-Harbour-4471"
STAFF_PASSWORD = "Correct-Horse-Battery-9"

if os.path.exists(DB_PATH):
    sys.exit(f"{DB_PATH} already exists — seed a fresh ODIN_DATA_DIR")
init_db()
app.config["SERVE_SPA"] = False   # the Jinja forms carry the CSRF field the seed needs

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

    for u, r in [("pm1", "Member"), ("sales1", "Contributor"), ("vw1", "Viewer")]:
        post("/users", username=u, name=u.upper(), password=STAFF_PASSWORD, role=r)
    post("/settings/contacts/vendors/add", name="CrowdStrike")
    post("/settings/contacts/products/add", name="Falcon Complete")
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

    proj("EDR Rollout - Globex", "Globex", stage_template_id=edr, vendor_name="CrowdStrike", product_name="Falcon Complete",
         target_end_date="2026-11-30", po_number="PO-GLX-0091", customer_approval="1", team_user_ids="2")
    proj("SIEM Onboarding - Acme", "Acme Bank", stage_template_id=siem, delivery_mode="Outsourced", outsourcer_name="VendorCo",
         outsourcer_email="ops@vendorco.example", target_end_date="2026-10-15", po_number="PO-ACME-4471")
    proj("Firewall refresh - Initech", "Initech", target_end_date="2026-12-20", via="Partner", partner_name="Redington",
         partner_account_manager_name="Meera", partner_account_manager_email="meera@redington.example")
    for i in range(12):
        proj(f"Bulk {i:02d}", "Globex" if i % 2 else "Initech", target_end_date="2026-01-15" if i % 4 == 3 else "2027-03-01")

    post("/projects/1/stage", stage="Scoping", note="Scope agreed")
    post("/projects/1/stage", stage="Sensor pilot", note="Pilot group of 50 endpoints")
    post("/projects/1/tasks", title="Collect asset inventory", assignee_id="3", due_date="2026-09-25")
    post("/projects/1/tasks", title="Deploy sensors to pilot group", due_date="2026-10-02", stage="Sensor pilot")
    for s in ["Scoping", "Kickoff", "Deployment", "Log source onboarding"]:
        post("/projects/2/stage", stage=s, note=f"Now in {s}")
    post("/projects/2/tasks", title="Onboard firewall logs", assignee_id="2", stage="Log source onboarding")
    post("/projects/1/participants/invite", email="jane@vendorco.example", name="Jane Okafor", role="Contractor")
    post("/projects/1/participants/invite", email="ann@globex.example", name="Ann Reyes", role="Customer")

con = sqlite3.connect(DB_PATH)
con.execute("UPDATE projects SET stage_entered_at = datetime('now', '-9 days') WHERE id = 1")
con.execute("UPDATE project_stages SET sla_days = 5 WHERE project_id = 1 AND name = 'Sensor pilot'")
con.commit()
for row in con.execute("SELECT id, name, stage FROM projects ORDER BY id LIMIT 3"):
    print(f"   {row[1]} | {row[2]}")
con.close()
print(f"Seeded {os.environ['ODIN_DATA_DIR']}. Sign in as admin / {ADMIN_PASSWORD}; staff password {STAFF_PASSWORD}.")
print("Sign-in links for the two invited externals: open the project's Team panel and Invite them again to mint fresh ones.")
