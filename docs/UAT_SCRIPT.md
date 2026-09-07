# Odin — User Acceptance Test Script

Re-runnable sign-off script. One row per scenario; tester initials + date in the last column.
Run against a **clean instance** (`python reset_data.py` or a fresh `ODIN_DATA_DIR`), never production.
Setup: admin password rotated, users `pm1` (Member), `sales1` (Member), `vw1` (Viewer) created.

Result key: **P** pass · **F** fail · **B** blocked · **N/A**

## A. Admin — first run

| # | Step | Expected | Result | Who/Date |
|---|------|----------|--------|----------|
| A1 | Log in as `admin` / seed password | Board loads, empty-state CTA "Create your first project" | | |
| A2 | Account → change password to one containing "odin" | Rejected: "too common" | | |
| A3 | Change password to a 12+ char passphrase, log out, log in | Succeeds | | |
| A4 | Users → create Member, Member, Viewer | All three appear, roles correct | | |
| A5 | Users → try password `changeme1234` for a new user | Rejected | | |
| A6 | Settings → Contacts → add Vendor, Product, Outsourcer (with email), Internal AM | All appear in dropdowns on New Project | | |
| A7 | Settings → Stages → rename two stages | Renamed everywhere (board columns, guest bar); closed projects stay closed | | |
| A8 | Settings → Stages → add a stage | Inserted **before** the terminal stage; flash explains | | |
| A9 | Settings → Stage SLAs → set Kickoff = 5 days | Persists after reload | | |
| A10 | Settings → RBAC → untick `manage_settings` for Admin | Admin keeps it (guard); flash explains | | |
| A11 | Audit Logs | Every step above listed with your username and IP (your real IP, not a proxy address) | | |
| A12 | Users → deactivate your own account | Refused | | |

## B. Project Manager (Member) — daily flow

| # | Step | Expected | Result | Who/Date |
|---|------|----------|--------|----------|
| B1 | New Project without a PO file | Refused, project not created | | |
| B2 | New Project with PO, vendor, product, AM, target end date | Created in first stage; PO stored under "Client PO" | | |
| B3 | Add two tasks, one assigned to `sales1` with due date | Shown on project; assignee notified (if email configured) | | |
| B4 | Log in as `sales1` → My Work | Assigned task listed; nav badge shows count | | |
| B5 | Move stage with a note | Stage bar advances; note in history; audit row | | |
| B6 | (DB or wait) project sits in Kickoff > 5 days | SLA badge on project; board banner "over their stage SLA" | | |
| B7 | Upload a `.docx` deliverable; upload a `.html` | docx listed; html refused | | |
| B8 | Download the deliverable | Browser downloads (not renders); audit row for download | | |
| B9 | Duplicate project | Form prefilled with "(copy)" | | |
| B10 | All Projects → search client name, sort by column, page 2 | Filters persist across pagination | | |
| B11 | Export CSV | All filtered rows, no financial columns | | |
| B12 | Project report / All-projects report | Print-ready pages render | | |
| B13 | Delete project | 403 — Members cannot delete | | |
| B14 | Cycle Time page | Renders; stage timings match history | | |

## C. Sales / Account Manager (Member)

| # | Step | Expected | Result | Who/Date |
|---|------|----------|--------|----------|
| C1 | Create project from PO | Succeeds | | |
| C2 | Move a delivery project to Closed | **Policy decision** — today Members can. Confirm this is intended, or a restricted role is needed | | |
| C3 | Copy guest link from project page | Copies; toast confirms | | |

## D. Viewer

| # | Step | Expected | Result | Who/Date |
|---|------|----------|--------|----------|
| D1 | Board, All Projects, project detail, Cycle Time | All readable, no edit controls | | |
| D2 | POST a note / stage / task via form or curl | 403 | | |
| D3 | Download a document | Allowed (policy: viewers may download) | | |
| D4 | Settings, Users, Audit Logs | 403 | | |

## E. Customer via guest link

| # | Step | Expected | Result | Who/Date |
|---|------|----------|--------|----------|
| E1 | Open link in a private window | Page loads, no login, no internal nav | | |
| E2 | Internal note (not guest-visible) | Not shown | | |
| E3 | Add a note | Appears in history with a **customer** attribution (today: attributed to vendor name — see report H2) | | |
| E4 | Stage control | Customer should **not** be able to change stage (today: can — see report H1) | | |
| E5 | Client PO number shown | Policy decision — acceptable for customer, not for vendor | | |

## F. Vendor / Outsourcer via guest link

| # | Step | Expected | Result | Who/Date |
|---|------|----------|--------|----------|
| F1 | Move stage forward with a note | Advances; owner notified; audit row | | |
| F2 | Move stage to Closed or back to first stage | Should be refused (today: allowed — see report H1) | | |
| F3 | Post 20 notes in 10 seconds | Should be throttled (today: all accepted — see report H4) | | |
| F4 | Admin rotates the token | Old link 404s immediately | | |
| F5 | Admin soft-deletes the project | Link 404s; undo restores it | | |

## G. Operations

| # | Step | Expected | Result | Who/Date |
|---|------|----------|--------|----------|
| G1 | `docker compose up -d --build` without SECRET_KEY | Container refuses to start with a clear message | | |
| G2 | `python preflight.py` | "Ready to serve" | | |
| G3 | Wrong password 5× from one IP, then correct password from **another** IP | Second IP not locked out (requires correct real-IP config — report C2) | | |
| G4 | Backup → restore into empty volume → boot | Row counts match; documents open (drill procedure in DEPLOY.md) | | |
| G5 | Upload 26 MB file | 413 with a readable page | | |
| G6 | `/healthz` | 200 (after implementing — report M8) | | |

Sign-off: ____________________  Date: __________
