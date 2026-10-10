"""The weekly portfolio report (Settings → Reports).

One email: what needs attention first (overdue, over their stage SLA, due
soon), stages moved in the last 7 days, what falls due in the next 7, and
how many rollouts sit in each stage, with a link into Odin. Optionally the
portfolio report and each active project's latest saved report ride along
as PDFs, and a short
summary goes to Teams (the connected channel and/or a Workflows webhook).

Staff only: recipients are active internal users in the chosen roles plus
the extra addresses an admin typed. Needs a request context (links).
"""
import json
from collections import Counter
from datetime import datetime, timedelta

from markupsafe import escape

import graph
from core import external_url
from db import PROJECT_OPEN_SQL, get_db, get_setting
from policies import local_today, policy
from security import file_stem
from services.alerts import build_alerts
from services.dashboard import tasks_due_by
from services import portfolio
from services.pdf import report_pdf
from services.report_pdf import render, render_portfolio


def build():
    """(subject, html, summary_lines, attachments) for this week."""
    db = get_db()
    today = local_today()
    projects = db.execute(f"SELECT p.*, u.name AS owner_name FROM projects p LEFT JOIN users u ON u.id = p.owner_id "
                          f"WHERE p.deleted_at IS NULL AND {PROJECT_OPEN_SQL} ORDER BY p.name").fetchall()
    folio = portfolio.build(projects)
    mix = folio["summary"]["health"]
    alerts = build_alerts(projects)
    week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
    moves = db.execute(
        "SELECT p.name, n.prev_stage, n.stage, n.author FROM status_notes n JOIN projects p ON p.id = n.project_id "
        "WHERE n.prev_stage IS NOT NULL AND n.created_at >= ? AND p.deleted_at IS NULL ORDER BY n.created_at", (week_ago,)).fetchall()
    soon = (today + timedelta(days=7)).isoformat()
    due_tasks = tasks_due_by(db, soon)
    per_stage = Counter(p["stage"] for p in projects)

    late = "<b style='color:#B4231C'>late</b>"

    def due_row(t):
        who = f" · {escape(t['who'])}" if t["who"] else ""
        return f"<li>{escape(t['due_date'])} · {escape(t['title'])} — {escape(t['project'])}{who}{' ' + late if t['due_date'] < today.isoformat() else ''}</li>"

    def row(p, note):
        return f"<li><b>{escape(p['name'])}</b> · {escape(p['client'] or '')} · {escape(p['stage'])} — {note}</li>"
    attention = ([row(p, "past its target date") for p in alerts["project_overdue"]]
                 + [row(p, "over its stage SLA") for p in alerts["stage_sla_breach"] if p not in alerts["project_overdue"]]
                 + [row(p, f"due {p['target_end_date']}") for p in alerts["project_due_soon"] if p not in alerts["stage_sla_breach"]])   # once each (sim L-8)
    sections = [
        ("Needs attention", attention, "Nothing is overdue, over SLA or due soon."),
        ("Stages moved this week", [f"<li><b>{escape(m['name'])}</b>: {escape(m['prev_stage'])} → {escape(m['stage'])} <span style='color:#6B7280'>({escape(m['author'])})</span></li>" for m in moves], "No stage moved this week."),
        ("Due in the next 7 days", [due_row(t) for t in due_tasks], "Nothing falls due."),
        ("Rollouts per stage", [f"<li>{escape(stage)}: {n}</li>" for stage, n in per_stage.most_common()], "No active rollouts."),
    ]
    health = f"{mix.get('green', 0)} on track · {mix.get('amber', 0)} at risk · {mix.get('red', 0)} off track"
    # the AI's opening (services/ai portfolio_narrative), only when it may run now and is from the last day and a half
    from services.ai import latest_portfolio
    ai = latest_portfolio("portfolio_narrative")
    opening = ""
    if ai:
        words, rec = ai
        opening = f"<p>{escape(words['opening'])}</p>"
        if words["needs_decision"]:
            opening += "<p style='margin:8px 0 4px'><b>Needs a decision</b></p><ul style='margin:0;padding-left:18px'>" + "".join(f"<li>{escape(x)}</li>" for x in words["needs_decision"]) + "</ul>"
        opening += f"<p style='color:#6B7280;font-size:12px;margin:6px 0 14px'>Written by AI ({escape(rec['model'])}) from the figures below.</p>"
    html = opening + (f"<p><b>{len(projects)}</b> active rollouts · <b>{len(alerts['project_overdue'])}</b> overdue · "
            f"<b>{len(alerts['stage_sla_breach'])}</b> over SLA · <b>{len(alerts['project_due_soon'])}</b> due soon</p>"
            f"<p>Health: {health}</p>")
    for title, items, empty in sections:
        html += f"<h3 style='margin:18px 0 6px;font-size:14px'>{title}</h3>" + (f"<ul style='margin:0;padding-left:18px'>{''.join(items)}</ul>" if items else f"<p style='color:#6B7280;margin:0'>{empty}</p>")
    html += f"<p style='margin-top:18px'><a href=\"{external_url('board')}\">Open the flow in Odin</a></p>"
    summary = [f"{len(projects)} active · {len(alerts['project_overdue'])} overdue · {len(alerts['stage_sla_breach'])} over SLA · {len(alerts['project_due_soon'])} due soon",
               f"{len(moves)} stage move{'s' if len(moves) != 1 else ''} this week, {len(due_tasks)} task{'s' if len(due_tasks) != 1 else ''} due in the next 7 days", health]

    attachments = []
    if policy("report_attach"):
        company = policy("company_name")
        from services.doc_templates import resolve
        attachments.append((f"portfolio-report-{today.isoformat()}.pdf", render_portfolio(folio, resolve("portfolio")), "application/pdf"))
        for p in projects:
            latest = db.execute("SELECT * FROM project_reports WHERE project_id = ? ORDER BY version DESC LIMIT 1", (p["id"],)).fetchone()
            if not latest:
                continue
            safe = file_stem(p["name"])
            if latest["kind"] == "snapshot":
                pdf = render(json.loads(latest["data"]), {"summary": latest["summary"], "next_steps": latest["next_steps"], "asks": latest["asks"]})
            else:   # an old plain-text version
                pdf = report_pdf(f"{p['name']} · report v{latest['version']}", (latest["body"] or "").splitlines(), f"Odin · {company} · saved {latest['created_at'][:10]}")
            attachments.append((f"{safe}-report-v{latest['version']}.pdf", pdf, "application/pdf"))
    return f"Odin weekly report · {today.strftime('%d %b %Y')}", html, summary, attachments


def recipients():
    db = get_db()
    roles = policy("report_roles")
    staff = [r["email"].lower() for r in db.execute(
        f"SELECT email FROM users WHERE active = 1 AND kind = 'internal' AND email IS NOT NULL AND email != '' "
        f"AND role IN ({','.join('?' * len(roles)) or 'NULL'})", roles)] if roles else []
    return sorted(set(staff) | set(policy("report_emails")))


def send(to=None, teams=True):
    """Send the report to `to` (default: the configured recipients) and,
    when asked and allowed, a summary to Teams. Returns (sent, failed, message)."""
    subject, html, summary, attachments = build()
    targets = to if to is not None else recipients()
    # The PDFs are internal (baseline, slip, notes, risks): they go to Odin staff
    # accounts only. Any other address gets the summary without them.
    staff = {r[0].lower() for r in get_db().execute("SELECT email FROM users WHERE kind = 'internal' AND active = 1 AND email IS NOT NULL")}
    outside_html = html + ("<p style=\"color:#666\">The PDF reports go to Odin accounts only; sign in to Odin to read them.</p>" if attachments else "")
    sent, failed = 0, []
    for address in targets:
        inside = address.lower() in staff
        ok, error = graph.send_mail(address, subject, html if inside else outside_html, attachments=attachments if inside else [])
        sent += ok
        if not ok:
            failed.append(f"{address}: {error}")
    posted = []
    if teams and policy("report_teams"):
        if get_setting("notify_teams_enabled") == "1":
            ok, _ = graph.send_teams_message(f"<b>{escape(subject)}</b><br>" + "<br>".join(escape(s) for s in summary))
            posted.append("Teams channel" if ok else "Teams channel failed")
        if policy("teams_webhook_url"):
            ok, _ = graph.post_teams_webhook(policy("teams_webhook_url"), subject, summary, external_url("board"))
            posted.append("Teams webhook" if ok else "Teams webhook failed")
    message = f"Sent to {sent} of {len(targets)}" + (f" with {len(attachments)} PDF{'s' if len(attachments) != 1 else ''}" if attachments else "") \
        + (f"; {', '.join(posted)}" if posted else "") + (f"; failed: {'; '.join(failed)[:300]}" if failed else "")
    return sent, failed, message
