# Odin — UAT & Smoke Test Results

**Date:** 8 September 2026 · **Build:** post-audit remediation, 151 unit tests green
**Executor:** Claude (automated + real-browser) · **Sign-off:** ________________ (name / date)

## Environment

| | |
|---|---|
| Server | gunicorn 23.0, 2 workers × 4 threads — the production process |
| Env flags | `SECRET_KEY` (random 32 bytes), `PMS_TRUST_PROXY=1`, `ODIN_DATA_DIR` isolated. `PMS_HTTPS` omitted: no TLS terminator on this machine |
| Not in scope here | nginx, Cloudflare Tunnel/Access, Docker entrypoint, Microsoft 365 (email, Teams, OneDrive) — marked N/A, to be run on the real host |
| Browsers | Chrome (automation pane, desktop + 375 px mobile emulation). Safari not exercised |
| Data | Phase 1: copy of production `odin.db` (14 projects, 5 users). Phases 2–3: fresh install, data created through the UI/API as the script directs. Production database untouched |

## Policy decisions applied (confirmed 8 Sep 2026)

Accepted as-is: Viewers may download documents · customer link shows the client's PO number · Members may close projects (Contributor role exists for those who should not) · guest links do not expire (rotation + delete revoke them).

## Phase 1 — Migration smoke test on a copy of production data

14/14 pass.

| ID | Step | Result | Evidence |
|---|---|---|---|
| S1 | real admin (still on changeme) is forced to the account page | **P** | HTTP 302 |
| S2 | password rotated, board reachable | **P** |  |
| S3 | existing stage names preserved through migration | **P** | PO Received > Invoiced > Kickoff > Implementation > Delivered/UAT > Payment Pending > Closed |
| S4 | 22 admin pages render | **P** | all 200 |
| S5 | all 14 projects: detail/edit/report/duplicate render | **P** | all 200 |
| S6 | all 28 guest links (vendor+customer) render without internal nav | **P** | all 200 |
| S7 | write to a migrated project | **P** |  |
| S8 | task on a migrated project | **P** |  |
| S9 | upload on a migrated project | **P** |  |
| S10 | download | **P** |  |
| S11 | audit trail grew with login/download/upload rows | **P** | 23 rows |
| S12 | existing users intact with roles | **P** | [{'username': 'admin', 'role': 'Admin', 'active': 1}, {'username': 'priya', 'role': 'Member', 'active': 1}, {'username': |
| S13 | no server errors in gunicorn error log | **P** | [] |
| S14 | integrity + FK after smoke | **P** |  |

## Phase 2 — UAT script `docs/UAT_SCRIPT.md`, sections A–G

48 pass · 0 fail · 2 N/A of 50 HTTP-executed steps.

| ID | Step | Result | Evidence |
|---|---|---|---|
| A1 | Log in as admin/seed → forced to account page | **P** | HTTP 302 → /account |
| A2 | Password containing 'odin' rejected | **P** |  |
| A3 | Passphrase accepted; re-login lands on empty board with CTA | **P** |  |
| A4 | Create Member, Contributor, Viewer | **P** | {'admin': 'Admin', 'pm1': 'Member', 'sales1': 'Contributor', 'vw1': 'Viewer'} |
| A5 | changeme1234 rejected for new user | **P** |  |
| A6 | Contacts appear in New Project dropdowns | **P** |  |
| A7 | Rename stage → board columns + filters | **P** |  |
| A8 | Add stage → inserted before Closed | **P** | ['PO Received', 'Scoping', 'Kickoff', 'Deployment', 'Tuning & UAT', 'Hypercare', 'Handover', 'Closed'] |
| A9 | Kickoff SLA=5 persists | **P** |  |
| A10 | Untick manage_settings for Admin → kept, view rights kept | **P** |  |
| A11 | Audit log lists config steps with caller IP | **P** |  |
| A12 | Deactivate own account refused | **P** |  |
| B1 | New project without PO refused | **P** |  |
| B2 | Create with PO/vendor/product/AM → first stage; PO filed as Client PO | **P** |  |
| B3 | Two tasks, one assigned | **P** |  |
| B4 | Assignee sees task in My Work + nav badge | **P** |  |
| B5 | Stage advances with note; history + audit | **P** |  |
| B6 | 9d in Kickoff vs 5d SLA → project badge + board banner | **P** |  |
| B7 | docx accepted, html refused | **P** |  |
| B8 | Download = attachment; audit row | **P** |  |
| B9 | Duplicate prefills '(copy)' | **P** |  |
| B10 | Search + sort persist across pagination | **P** |  |
| B11 | CSV = filtered rows, no financial columns | **P** | Project Name,Client,PO Number,PO Date,Stage,Owner,Delivery Mode,Outsou |
| B12 | Single + all-projects reports render | **P** |  |
| B13 | Member delete → 403 | **P** | 403 |
| B14 | Cycle Time renders with stage timings | **P** |  |
| C1 | Contributor creates a project from PO | **P** |  |
| C2 | Contributor cannot close (Members may — accepted policy) | **P** | HTTP 403 |
| C3 | Customer + vendor links with Copy buttons on project page | **P** |  |
| D1 | Viewer reads all, no edit controls | **P** |  |
| D2 | Viewer POSTs → 403 | **P** | [403, 403, 403] |
| D3 | Viewer may download (accepted policy) | **P** |  |
| D4 | Viewer blocked from Settings/Users/Audit | **P** | [403, 403, 403] |
| E1 | Customer link: no login, no internal nav | **P** |  |
| E2 | Internal note hidden | **P** |  |
| E3 | Note attributed 'Ann Lee · Acme Bank' | **P** |  |
| E4 | Customer has no stage control | **P** |  |
| E5 | Customer sees own PO (accepted policy) | **P** |  |
| F1 | Vendor advances one stage; audited as guest:vendor (owner email N/A — no M365) | **P** |  |
| F2 | Vendor cannot close or rewind | **P** | Scoping |
| F3 | 20 notes in 10 s → throttled | **P** | 13 × 429 |
| F4 | Rotate → both old links 404 | **P** |  |
| F5 | Soft delete → 404; undo → link back | **P** |  |
| G1 | Compose refuses start without SECRET_KEY | **N/A** | N/A — no Docker here; entrypoint covered by unit test |
| G2 | preflight.py reports ready | **P** | Ready to serve. |
| G3 | Attacker IP locked; other IP logs in | **P** |  |
| G3b | …attacking IP itself is locked | **P** |  |
| G4 | Backup → restore drill | **N/A** | Executed separately (see Phase 3) |
| G5 | 26 MB upload → 413 with readable page (via curl) | **P** | curl 413 |
| G6 | /healthz → 200 ok | **P** |  |

### Browser-executed steps

| ID | Step | Result | Evidence |
|---|---|---|---|
| A1 (visual) | Seed admin: forced-change screen, then board after new password | **P** | Browser |
| B3/B9 (visual) | Task due-date preset +1w fills correct date; inline task edit reveals row | **P** | setDueDate → 2026-09-15; edit row hidden→shown |
| B6 (visual) | SLA badge text on project page | **P** | "9 days in Kickoff — 4 over the 5-day target" |
| Board drag-drop | Drag card to Deployment column moves stage | **P** | Kickoff → Deployment; Recent Activity shows the change |
| C3 (visual) | Copy guest link button | **P** | Clipboard API unavailable in the automation context → designed fallback "Press Ctrl+C" with link selected |
| E/F (visual) | Vendor page: 'Advance to Kickoff' + name field, no PO; customer page: PO, no stage control | **P** | Chrome |
| M9 (visual) | Branded 404: heading, hint, nav, 'Back to the board' | **P** | Chrome |
| L2 (visual) | 375 px: nav collapses to 64 px bar, 9 links behind menu button, no horizontal overflow | **P** | Chrome mobile emulation |

## Phase 3 — Backup → restore drill (G4)

**PASS.** `backup.py` wrote `odin-backup-20260907-210018.zip` locally (OneDrive not configured). Restored into an empty data directory; `init_db()` booted it; all 8 table counts matched the source (32 projects, 33 documents, 78 audit rows), 33/33 upload files present, `integrity_check` ok, `/healthz` ok, audit append-only trigger intact after restore.

## Not executed — for your team on the real host

| Step | Reason | Who |
|---|---|---|
| G1 compose refuses to start without `SECRET_KEY` | No Docker on this machine (entrypoint logic unit-tested) | Ops |
| F1 owner email/Teams on vendor update; Settings → test email / test Teams / OneDrive backup | Microsoft 365 not connected | Admin, after Azure app is registered |
| Cloudflare Access sign-in (MFA), `/guest/*` bypass, edge rate limits | Cloudflare not in the local stack | Ops, per DEPLOY.md |
| Safari / iOS | Not automatable here | Any tester, 10 minutes with the script |

## Sign-off

Tested against the script above with the policy decisions recorded. Outstanding items are environment-dependent, not defects.

Product owner: ____________________  Date: __________
