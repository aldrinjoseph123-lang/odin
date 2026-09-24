# Odin — User Acceptance Test Script (v2)

Re-runnable sign-off script. One row per scenario; tester initials + date in the last column.
Run against a **clean instance** (`python reset_data.py` or a fresh `ODIN_DATA_DIR`), never production.
Setup: admin password rotated; users `pm1` (Member), `sales1` (Contributor), `vw1` (Viewer) created;
Settings → Contacts: one vendor, one product, one outsourcer with email, one partner with an account manager.
Microsoft 365 connected if you want the email rows to pass; otherwise mark them N/A.

Result key: **P** pass · **F** fail · **B** blocked · **N/A**

## A. Admin — first run and settings

| # | Step | Expected | Result | Who/Date |
|---|------|----------|--------|----------|
| A1 | Sign in as `admin` / seed password | Forced to the Account page; every other page bounces back until the password is changed | | |
| A2 | Set a password containing "odin" | Rejected: too common | | |
| A3 | Set a 12+ character passphrase, sign out, sign in | Lands on the Flow screen, empty state "Create one from a client PO" | | |
| A4 | Users → add `pm1` Member, `sales1` Contributor, `vw1` Viewer | Rows appear; role select disabled on your own row; "External" is never offered to staff | | |
| A5 | Users → password `changeme1234` for a new user | Rejected | | |
| A6 | Users → deactivate your own account | Refused | | |
| A7 | Settings → Stage templates → rename a stage, add a stage, set SLA days, add a second template | Stage inserted before the last; SLAs persist on reload; the new template starts as a copy of the first | | |
| A8 | Settings → Document categories → add one, delete "Client PO" | Add works; Client PO refused while documents use it | | |
| A9 | Settings → Alert types → set Project due soon to 10 days, tick Email | Persists on reload | | |
| A10 | Settings → Role permissions → untick `manage_users` for Admin | Cell is locked; Admin keeps it after save | | |
| A11 | Settings → Contacts → add vendor, product, outsourcer with email, partner + account manager; delete then Undo the partner | All appear in the New project pick-lists; Undo restores the partner with its manager | | |
| A12 | Audit log → filter by action `create_user`, then by date | Every step above listed with your username and real IP; CSV export matches the filter | | |

## B. Project manager — daily flow

| # | Step | Expected | Result | Who/Date |
|---|------|----------|--------|----------|
| B1 | New project without a PO file | Refused with a message; nothing created | | |
| B2 | New project with PO, template, `pm1` in Team, "Ask the customer contact to approve" ticked | Created in the template's first stage; you are Project manager, `pm1` Coordinator; PO under Client PO | | |
| B3 | Flow → select the rollout | Row shows its own stepper and stage name; detail shows the flowchart with every stage from the template | | |
| B4 | Flow → "+ Task" under the current stage, assign to `pm1`; tick it; add one under a later stage | Tasks sit under their stage; Next up updates; the count "n open before moving on" is right | | |
| B5 | Flow → Advance with a note | Stage moves; note in Recent; "Awaiting approval" chip on the row and detail | | |
| B6 | Project page → This project's stages → rename the current stage, add one, delete a future one | Only this project changes; the template in Settings is untouched; the current stage cannot be deleted | | |
| B7 | Project page → Team → add `sales1` as Sales; remove them; try to remove yourself | Add and remove work; the Project manager cannot be removed | | |
| B8 | Project page → Documents → upload a `.docx`, then a `.html` | docx listed; html refused with a message | | |
| B9 | Download the deliverable | Downloads as an attachment; audit row | | |
| B10 | Project page → Sharing → rotate guest links | Both links change; old customer link 404s | | |
| B11 | Projects → search client name, filter Overdue, sort by Client, page 2 (with 26+ projects) | Filters live in the URL and survive paging; Export CSV honours them | | |
| B12 | Report → edit the draft summary, Save as version 1; change data, Regenerate draft, save version 2; open v1 from the picker | Both versions readable; print hides the app chrome | | |
| B13 | Delete project from Sharing, then Undo from the message | Project gone from Flow, back after Undo | | |
| B14 | Cycle time → switch template | Aging and stage timings match the history; projects on custom lists counted as "not compared" | | |

## C. Coordinator, Sales, Viewer — what roles allow

| # | Step | Expected | Result | Who/Date |
|---|------|----------|--------|----------|
| C1 | Sign in as `pm1` (Coordinator on B2's project) → Flow | Can add and tick tasks, upload a document, add a note; **no** Advance button; stage change via API is 403 | | |
| C2 | `pm1` on a project they are **not** on | Read and comment only; no task or document controls | | |
| C3 | Sign in as `sales1` (Contributor) → New project | Can create (becomes its Project manager); on others' projects: notes only | | |
| C4 | Sign in as `vw1` (Viewer) → every page | All readable, no edit controls; Settings, Users, Audit log are 403; downloads allowed | | |
| C5 | Admin off every project | Can still do everything (Admin bypasses project roles) | | |

## D. External partner and customer (email sign-in link)

| # | Step | Expected | Result | Who/Date |
|---|------|----------|--------|----------|
| D1 | Project page → Team → Invite `ann@customer.example` as Customer, `raj@vendor.example` as Contractor | Both listed as External; with mail connected each gets a link, otherwise the link is shown to you to pass on | | |
| D2 | Open Ann's link in a private window | Signed in with "Partner access"; nav shows only Flow and Projects; only this project visible; other project ids 404 | | |
| D3 | Open the same link again | Refused: invalid or expired; request page offered | | |
| D4 | Sign-in page → "Partner or customer?" → request a link for an unknown address and for Ann's | Same neutral message both times; a fourth request for one address inside 15 minutes is throttled | | |
| D5 | Try `ann@customer.example` on the staff login form with any password | "Bad username or password"; audit says sign-in links only | | |
| D6 | Ann → project page → Report | Sees saved versions only, never the draft or an editor; can add a note; no edit controls anywhere | | |
| D7 | Admin advances the stage (approval on) → Ann → Flow → "Your approval" card → Approve with a comment | Chip turns Approved on row and detail; note "Approved <stage>: …" is customer-visible; owner notified; audit row | | |
| D8 | Raj (Contractor) tries to approve | 403 | | |
| D9 | Admin tags a task to Raj → Raj ticks it; Raj tries another task | Own task ticks; other task 403 | | |
| D10 | Users → Ann's row | External badge, no Reset password, role locked to External; Deactivate ends her session and her next link is refused | | |
| D11 | Admin → Account → Users → Reset password on Ann via API | Refused: nothing to reset | | |

## E. Notifications (Microsoft 365 connected)

| # | Step | Expected | Result | Who/Date |
|---|------|----------|--------|----------|
| E1 | Settings → Integrations → tick Email notifications; Send test email | Email arrives at your account address | | |
| E2 | Advance a stage on a project with `pm1`, Ann and Raj on it | Every participant with an address is emailed except you; externals get the partner sign-in pointer; owner mail and Teams as configured | | |
| E3 | Assign a task to `pm1` | `pm1` emailed; assigning to yourself sends nothing | | |
| E4 | Alerts page after a project passes its target date | Project overdue row; chip on Flow; email if the alert type has Email ticked | | |

## F. Legacy guest links (until retired)

| # | Step | Expected | Result | Who/Date |
|---|------|----------|--------|----------|
| F1 | Customer link in a private window | Loads without login; internal notes hidden; can add a named note; cannot change stage | | |
| F2 | Vendor link (Outsourced project) | Can advance one step with a name and note; never to Closed or backwards | | |
| F3 | Post 20 notes in 10 seconds through the link | Throttled | | |

## G. Operations

| # | Step | Expected | Result | Who/Date |
|---|------|----------|--------|----------|
| G1 | `docker compose up -d --build` without SECRET_KEY | Container refuses to start with a clear message | | |
| G2 | `python preflight.py` | "Ready to serve" | | |
| G3 | Wrong password 5× from one IP, then correct password from **another** IP | Second IP not locked out | | |
| G4 | Backup → restore into an empty volume → boot | Row counts match; documents open; report versions and approvals present | | |
| G5 | Upload a 26 MB file | 413 with a readable page | | |
| G6 | `/healthz` | 200 | | |
| G7 | Cloudflare Access in front | `/auth/link*` reachable without Access; everything else behind it | | |

Sign-off: ____________________  Date: __________
