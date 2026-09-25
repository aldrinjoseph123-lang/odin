# UAT dry run — 25 Sep 2026

Executed by the build agent against `scripts/seed_uat.py` data on a local
instance, through the built React bundle in a browser and the JSON API.
Not a customer sign-off: no Microsoft 365 connection, so mail rows are N/A.
Every failure below was fixed the same day (commit noted).

| Row | Result | Note |
|---|---|---|
| A1 | P | Fresh admin forced to Account; `pm1` created from Users signs straight in (no forced change on staff created by an admin with a chosen password) |
| A4–A6 | P | Users page; own row locked; self-deactivate refused |
| A7 | P | Templates: rename, add before last, SLAs persist, new template copies the first |
| A8 | P | "Cannot delete 'Client PO' — 15 document(s) use it" |
| A9 | P | Threshold 10 days persisted |
| A10 | P | Admin keeps `manage_users` after an emptied matrix |
| A11 | P | Partner delete + Undo restores the manager |
| A12 | P | Audit filters and CSV |
| B1–B2 | P | PO required; PM + coordinator seats |
| B3–B5 | P | Row stepper, flowchart, tasks per stage, advance with approval chip |
| B6–B10 | P | Stage editor, team add/remove, docx accepted / html refused, download, rotate |
| B11 | P | URL-held filters; paging not reachable with 15 projects |
| B12 | P | Versions, regenerate, picker |
| B13 | P | Delete → 404 → Undo → 200 |
| B14 | P | Per template; custom lists counted |
| C1 | P | Coordinator: tasks yes, no Advance, stage move 403 |
| C2 | P | Off the project: note only |
| C4 | P | Viewer refused admin pages |
| C5 | P | Admin bypasses project roles |
| D1 | P | Invites create External accounts; link shown when mail is off |
| D2 | P | Partner access: Flow + Projects only; other projects 404 on the API (the bundle shell itself answers 200, no data) |
| D3 | **F → fixed** | Reused link refused, but the legacy request page showed the full staff nav to the still-signed-in external. Now: a signed-in user is sent home; the legacy nav hides My work / Cycle time / Alerts for externals |
| D6 | P | Saved versions only, no editor |
| D7 | P | Approve with comment → chip, note, audit, participant mails |
| D8–D11 | P (tests) | Contractor 403; own-task tick; no password reset |
| — | **F → fixed** | Row and detail disagreed on days in stage when the SLA clock and the note history differ; the current stage now follows `stage_entered_at` |
| — | **F → fixed** | Approval + SLA chips clipped in the row; stage column widened, chips wrap |
| E1–E4 | N/A | No Microsoft 365 connection |
| F1–F3 | P (tests) | Guest routes covered by the suite; switch off verified |
| G1–G2, G6 | P | CI boots the image and answers /healthz; preflight run locally |
| G3–G5, G7 | not run | Needs the deployed stack |

Open for the owner: connect Microsoft 365 and run E1–E4 and D1 with real
mail; run G3–G5 and G7 on the deployed stack; decide when to switch the
guest links off.
