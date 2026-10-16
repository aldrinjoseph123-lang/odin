"""The rollout report as a PDF, drawn from the same data as the page
(services/report_data.py): brand band, health, the numbers, the words, the
plan-versus-actual timeline drawn as vectors, and the tables. Dependency-free
(services/pdf.Canvas): Helvetica, Windows-1252 text."""
from datetime import date, timedelta

from services.fmt import fmt_date, iso_date
from services.pdf import MARGIN, Canvas

INK, MUTED, HAIR, FAINT = (16, 17, 20), (91, 98, 112), (228, 230, 235), (243, 244, 246)
ACCENT, ACCENT_SOFT, WHITE = (61, 90, 254), (197, 206, 255), (255, 255, 255)
RAG = {"green": ((230, 246, 236), (23, 122, 66), "On track"), "amber": ((255, 244, 224), (138, 83, 0), "At risk"),
       "red": ((253, 236, 235), (180, 35, 28), "Off track"), "done": ((243, 244, 246), (91, 98, 112), "Complete")}
WARN_LINE, BAD_LINE, BRAND_RED = (227, 155, 29), (224, 70, 61), (225, 29, 46)
MARK = {"green": (31, 157, 85), "amber": WARN_LINE, "red": BAD_LINE, "done": (150, 154, 162)}   # fills wear the -line colours
LEFT, RIGHT = MARGIN - 16, Canvas.W - (MARGIN - 16)
WIDTH = RIGHT - LEFT


class _Doc:
    def __init__(self, data, label=None, running=None, tpl=None):
        from services.doc_templates import ACCENTS, logo_image
        self.c = Canvas()
        self.data = data
        self.tpl = tpl or {}
        self.accent = ACCENTS.get(self.tpl.get("accent") or "blue", ACCENT)
        self.accent_soft = tuple(int(v + (255 - v) * 0.7) for v in self.accent)
        self.logo = logo_image(self.tpl.get("logo")) if self.tpl.get("logo") else None
        self.co_logo = logo_image(self.tpl.get("co_logo")) if self.tpl.get("co_logo") else None
        self.label = label or "Rollout report · " + ("customer copy" if data["audience"] == "customer" else "internal")
        self.running = running or data["project"]["name"]
        self.y = 0
        self._new_page(first=True)

    def footer(self, text):
        """The page footer: the template's own line first, when it has one."""
        custom = (self.tpl.get("footer") or "").strip()
        return f"{custom} · {text}" if custom else text

    def _new_page(self, first=False):
        c = self.c
        c.page()
        if first:
            c.rect(0, 0, c.W, 58, fill=INK)
            if self.logo:     # the template's logo stands in for the wordmark
                c.image(self.logo, LEFT, 12, 170, 34)
            else:
                c.rect(LEFT, 20, 4, 18, fill=BRAND_RED)
                c.text(LEFT + 10, 19, "ODIN", 17, True, WHITE)
                c.text(LEFT + 10 + c.width("ODIN", 17, True) + 8, 25, f"by {self.data['company']}", 8.5, False, (184, 184, 180))
            right = RIGHT
            if self.co_logo:  # the customer's logo beside ours, on the right of the band
                c.rect(RIGHT - 118, 10, 118, 38, fill=WHITE)
                c.image(self.co_logo, RIGHT - 114, 12, 110, 34)
                right = RIGHT - 128
            c.text(right - c.width(self.label, 8.5), 19, self.label, 8.5, False, (184, 184, 180))
            when = f"as of {fmt_date(self.data['today'])}"
            c.text(right - c.width(when, 8.5), 32, when, 8.5, False, WHITE)
            self.y = 76
        else:
            c.text(LEFT, 26, self.running, 9, True, MUTED)
            c.line(LEFT, 40, RIGHT, 40, HAIR)
            self.y = 52

    def room(self, h):
        if self.y + h > self.c.H - 44:
            self._new_page()

    def heading(self, text, sub=None):
        self.room(34)
        self.y += 10
        self.c.text(LEFT, self.y, text, 11.5, True)
        if sub:
            self.c.text(LEFT + self.c.width(text, 11.5, True) + 8, self.y + 2.5, sub, 8.5, False, MUTED)
        self.y += 19

    def block(self, key, values):
        """A template text block (opening, closing...), placeholders filled; nothing when empty."""
        from services.doc_templates import fill
        text = fill((self.tpl.get("texts") or {}).get(key, ""), values).strip()
        if text:
            self.y += 4
            self.para(text, 9.5, INK)
            self.y += 6

    def company_line(self):
        line = (self.tpl.get("company_line") or "").strip()
        if line:
            self.c.text(LEFT, self.y, self.c.fit(line, 8, WIDTH), 8, False, MUTED)
            self.y += 13

    def para(self, text, size=9.5, color=INK, indent=0):
        for line in self.c.wrap(text, size, WIDTH - indent):
            self.room(size + 4)
            self.c.text(LEFT + indent, self.y, line, size, False, color)
            self.y += size + 4

    def bullets(self, lines, size=9.5):
        for line in lines:
            first = True
            for chunk in self.c.wrap(line, size, WIDTH - 12):
                self.room(size + 4)
                if first:
                    self.c.text(LEFT + 2, self.y, "•", size, False, MUTED)
                self.c.text(LEFT + 12, self.y, chunk, size, False)
                self.y += size + 4
                first = False

    def table(self, columns, rows, widths, tones=None):
        """columns: header labels; widths: fractions of the width; tones: per-row {col: colour}."""
        xs, x = [], LEFT
        for w in widths:
            xs.append(x)
            x += w * WIDTH
        def head():
            self.room(18)
            for i, col in enumerate(columns):
                self.c.text(xs[i] + 3, self.y, col, 7.5, False, MUTED)
            self.y += 12
            self.c.line(LEFT, self.y, RIGHT, self.y, HAIR)
            self.y += 4
        head()
        for r, row in enumerate(rows):
            if self.y + 15 > self.c.H - 44:
                self._new_page()
                head()
            for i, cell in enumerate(row):
                colour = (tones[r].get(i) if tones and tones[r] else None) or INK
                self.c.text(xs[i] + 3, self.y, self.c.fit(cell, 8.5, widths[i] * WIDTH - 6), 8.5, False, colour)
            self.y += 12.5
            self.c.line(LEFT, self.y, RIGHT, self.y, FAINT)
            self.y += 2.5
        self.y += 4


def _opening_month(t0, t1):
    """t0 when the month the chart opens in would go unnamed (the first month tick sits
    over 12% in, as on screen: review P2-50), else None."""
    first = date(t0.year, t0.month, 1)
    if first < t0:
        first = date(t0.year + (t0.month == 12), t0.month % 12 + 1, 1)
    return t0 if (first - t0).days / max(1, (t1 - t0).days) > 0.12 else None


def _gantt(doc, stages, today, target, customer=False):
    """Plan (outline), actual (solid), forecast (pale), baseline (thin grey), today and target lines."""
    c = doc.c
    dates = [d for s in stages for d in map(iso_date, (s.get("plan_start"), s.get("plan_end"), s.get("base_start"), s.get("base_end"),
                                                 s.get("actual_start"), s.get("actual_end"), s.get("forecast_start"), s.get("forecast_end"))) if d]
    dates += [d for d in (iso_date(today), iso_date(target)) if d]
    if not dates:
        return
    t0, t1 = min(dates) - timedelta(days=3), max(dates) + timedelta(days=3)
    label_w, row_h = 118, 17
    track_x, track_w = LEFT + label_w, WIDTH - label_w
    x = lambda d: track_x + track_w * ((d - t0).days / max(1, (t1 - t0).days)) if d else track_x   # noqa: E731   (an unreadable date sits at the left edge)
    doc.room(22 + row_h * min(len(stages), 6))
    # month ticks, the opening month named at the left edge
    if _opening_month(t0, t1):
        c.text(x(t0) + 2, doc.y, t0.strftime("%b '%y"), 7, False, MUTED)
    m = date(t0.year, t0.month, 1)
    while m <= t1:
        if m >= t0:
            c.line(x(m), doc.y + 10, x(m), doc.y + 12 + row_h * len(stages), FAINT, 0.6)
            c.text(x(m) + 2, doc.y, m.strftime("%b '%y"), 7, False, MUTED)
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    top = doc.y + 12
    for i, s in enumerate(stages):
        y = top + i * row_h
        if y + row_h > c.H - 44:
            doc._new_page(); top = doc.y - i * row_h; y = doc.y
        c.text(LEFT, y + 4, c.fit(s["name"], 8.5, label_w - 8, s["status"] == "current"), 8.5, s["status"] == "current", INK if s["status"] != "next" else MUTED)
        mid = y + row_h / 2
        if s.get("base_start") and s.get("base_end"):
            c.rect(x(iso_date(s["base_start"])), mid + 5, max(1.5, x(iso_date(s["base_end"])) - x(iso_date(s["base_start"]))), 1.6, fill=(208, 211, 218))
        if s.get("plan_start") and s.get("plan_end"):
            c.rect(x(iso_date(s["plan_start"])), mid - 4.5, max(2, x(iso_date(s["plan_end"])) - x(iso_date(s["plan_start"]))), 9, stroke=doc.accent, width=0.9)
        if s.get("actual_start") and (s.get("actual_end") or s["status"] == "current"):
            a0, a1 = iso_date(s["actual_start"]), iso_date(s["actual_end"]) or iso_date(today)
            late = s["status"] == "current" and s.get("plan_end") and s.get("forecast_end") and s["forecast_end"] > s["plan_end"]
            c.rect(x(a0), mid - 2.5, max(2, x(a1) - x(a0)), 5, fill=WARN_LINE if late else (doc.accent if s["status"] == "current" else (86, 88, 94)))
        if s.get("forecast_start") and s.get("forecast_end") and (s["status"] == "next" or (s["status"] == "current" and s["forecast_end"] > today)):
            f0 = iso_date(today) if s["status"] == "current" else iso_date(s["forecast_start"])
            c.rect(x(f0), mid - 2.5, max(2, x(iso_date(s["forecast_end"])) - x(f0)), 5, fill=doc.accent_soft)
    bottom = top + len(stages) * row_h
    c.line(x(iso_date(today)), top - 2, x(iso_date(today)), bottom, doc.accent, 1.1)
    c.text(x(iso_date(today)) - 9, bottom + 2, "today", 7, True, doc.accent)
    if target:
        c.line(x(iso_date(target)), top - 2, x(iso_date(target)), bottom, BAD_LINE, 0.9, dash=(3, 2))
        c.text(x(iso_date(target)) - 10, bottom + 2, "target", 7, False, BAD_LINE)
    doc.y = bottom + 14
    # legend
    lx = LEFT
    for kind, label in (("plan", "Plan"), ("actual", "Actual"), ("forecast", "Forecast"), ("base", "Baseline"), ("late", "Running late")):
        if kind == "base" and customer:
            continue
        if kind == "plan":
            c.rect(lx, doc.y + 1, 14, 6, stroke=doc.accent, width=0.9)
        elif kind == "base":
            c.rect(lx, doc.y + 3, 14, 1.6, fill=(208, 211, 218))
        else:
            c.rect(lx, doc.y + 1.5, 14, 5, fill={"actual": (86, 88, 94), "forecast": doc.accent_soft, "late": WARN_LINE}[kind])
        c.text(lx + 18, doc.y, label, 7.5, False, MUTED)
        lx += 18 + c.width(label, 7.5) + 14
    doc.y += 16


def render(data, words, tpl=None):
    """PDF bytes for one report (data from report_data, words the PM's), laid
    out by a document template (services/doc_templates; the built-in default
    when none): its brand, its sections in its order, its text blocks."""
    from services.doc_templates import default_config, order
    tpl = tpl or data.get("template") or default_config("rollout")
    doc = _Doc(data, label=f"{tpl['title']} · " + ("customer copy" if data["audience"] == "customer" else "internal"), tpl=tpl)
    c, p, f, h = doc.c, data["project"], data["finish"], data["health"]
    customer = data["audience"] == "customer"
    values = {"project": p["name"], "client": p["client"], "company": data["company"], "pm": p["owner_name"], "po": p.get("po_number") or "",
              "stage": p["stage"], "target": fmt_date(f.get("target")), "forecast": fmt_date(f.get("forecast")), "date": fmt_date(data["today"])}
    from services.fields import shown   # {field:Name}: the fields this copy carries (the customer's copy: theirs only)
    values |= {f"field:{x['name']}": shown(x["kind"], x["value"]) for x in data.get("fields", [])}

    c.text(LEFT, doc.y, c.fit(p["name"], 18, WIDTH, True), 18, True)
    doc.y += 24
    meta = " · ".join(x for x in (p["client"], f"PM {p['owner_name']}", f"stage {p['stage_number']} of {p['stage_count']}: {p['stage']}",
                                         p.get("po_number") and (p["po_number"] if p["po_number"].upper().startswith("PO") else f"PO {p['po_number']}")) if x)
    c.text(LEFT, doc.y, c.fit(meta, 9, WIDTH), 9, False, MUTED)
    doc.y += 18
    if data.get("fields"):   # the custom fields this copy carries, one line
        c.text(LEFT, doc.y - 4, c.fit(" · ".join(f"{x['name']}: {shown(x['kind'], x['value'])}" for x in data["fields"]), 9, WIDTH), 9, False, MUTED)
        doc.y += 14

    soft, strong, word = RAG[h["rag"]]
    pw = c.width(word, 9.5, True) + 22
    c.rect(LEFT, doc.y, pw, 17, fill=soft)
    c.rect(LEFT + 7, doc.y + 6.5, 4, 4, fill=strong)
    c.text(LEFT + 15, doc.y + 3.5, word, 9.5, True, strong)
    reasons = " ".join(h["reasons"]) if h["reasons"] and not customer else f"Status as of {fmt_date(data['today'])}."
    for i, line in enumerate(c.wrap(reasons, 8.5, WIDTH - pw - 10)[:2]):
        c.text(LEFT + pw + 10, doc.y + 1 + i * 11, line, 8.5, False, MUTED)
    doc.y += 30
    doc.company_line()
    doc.block("intro", values)

    def numbers():
        # the numbers
        vs_t = f.get("vs_target_days")
        boxes = [("Forecast finish", fmt_date(f.get("forecast")), "" if vs_t is None else f"{vs_t} d after target" if vs_t > 0 else f"{-vs_t} d before target", vs_t is not None and vs_t > 0),
                 ("Target", fmt_date(f.get("target")), "" if f.get("days_to_target") is None else (f"{-f['days_to_target']} d ago" if f["days_to_target"] < 0 else f"{f['days_to_target']} d to go"), False),
                 ("Complete", f"{data['pct_complete']}%", f"{data['elapsed_days']} d since start", False)]
        if not customer:
            vb = f.get("vs_baseline_days")
            boxes.insert(2, ("Against baseline", "-" if vb is None else "on plan" if vb == 0 else f"{abs(vb)} d {'late' if vb > 0 else 'early'}",
                             f"baseline of {fmt_date(data['baseline_at'])}" if data.get("baseline_at") else "no baseline", bool(vb and vb > 0)))
        _boxes(doc, boxes)

    def summary():
        doc.heading("Summary")
        doc.para(words.get("summary") or "-")
        if words.get("next_steps"):
            doc.heading("Next steps")
            doc.bullets([x for x in words["next_steps"].splitlines() if x.strip()])
        if words.get("asks") or data["needs"].get("approval") or data["needs"].get("tasks"):   # the internal copy says it too (P23)
            doc.heading("What we need from you" if customer else "What we need from the customer")
            asks = [x for x in (words.get("asks") or "").splitlines() if x.strip()]
            if data["needs"].get("approval"):
                asks.append(f"Approve the {data['needs']['approval']['stage']} stage (asked {fmt_date(data['needs']['approval']['requested_at'])}).")
            asks += [t["title"] + (" - due " + fmt_date(t["due_date"]) if t.get("due_date") else "") for t in data["needs"].get("tasks", [])]
            doc.bullets(asks)

    def timeline():
        doc.heading("Timeline", "plan against actual, and the forecast for what is left")
        _gantt(doc, data["stages"], data["today"], f.get("target"), customer)
        cols = ["Stage", "Planned", "Actual", "Forecast end"] + ([] if customer else ["Slip"])
        widths = [0.24, 0.24, 0.24, 0.16] + ([] if customer else [0.12])
        rows, tones = [], []
        for s in data["stages"]:
            planned = f"{fmt_date(s['plan_start'])} - {fmt_date(s['plan_end'])}" if s.get("plan_start") else "-"
            actual = f"{fmt_date(s['actual_start'])} - {fmt_date(s['actual_end']) if s.get('actual_end') else 'now'}" if s.get("actual_start") else ("skipped" if s["status"] == "skipped" else "-")
            slip = s.get("slip_days")
            row = [s["name"] + (" (now)" if s["status"] == "current" else ""), planned, actual, fmt_date(s.get("forecast_end"))]
            if not customer:
                row.append("-" if slip is None else "on plan" if slip == 0 else f"{abs(slip)} d {'late' if slip > 0 else 'early'}")
            rows.append(row)
            tones.append({4: (180, 35, 28)} if not customer and slip and slip > 0 else {})
        doc.table(cols, rows, widths, tones)
        held = next((m["gate"] for m in data.get("milestones", []) if m.get("gate")), None)   # what holds the next move (internal only)
        if held and not customer:
            doc.para(f"Before the next stage: {held}", 9, (138, 83, 0))
        ms = data.get("project_milestones") or []   # the rollout's own milestones (the customer's copy: those marked for them)
        if ms:
            doc.heading("Milestones", f"{sum(1 for m in ms if m['done'])} of {len(ms)} reached")
            doc.table(["Milestone", "Stage", "Date", "State"],
                      [[m["name"], m.get("stage") or "-", fmt_date(m["date"]), f"reached {fmt_date(m['done_at'][:10])}" if m["done"] else "missed" if m["missed"] else "ahead"] for m in ms],
                      [0.44, 0.2, 0.16, 0.2], [{3: (180, 35, 28)} if m["missed"] and not m["done"] else {} for m in ms])

    def raid():
        raid = data.get("raid", [])
        if raid:
            doc.heading("Risks, issues, decisions and blockers" if not customer else "Decisions and open points", f"{sum(1 for r in raid if r['open'])} open")
            doc.table(["Kind", "Item", "Owner", "Impact", "Status", "Due"],
                      [[r["kind"].title(), r["title"] + (f" - {r['resolution']}" if r.get("resolution") else ""), r.get("owner_name") or "-",
                        r["impact"] if r["kind"] != "decision" else "", r["status"], fmt_date(r.get("due_date")) if r.get("due_date") else "-"] for r in raid],
                      [0.1, 0.44, 0.14, 0.09, 0.11, 0.12],
                      [{0: (180, 35, 28)} if r["kind"] == "blocker" and r["open"] else {} for r in raid])

    def work():
        w = data["work"]
        doc.heading("Work", f"{w['done']} of {w['total']} tasks done" + (f", {w['late']} late" if w["late"] else ""))
        doc.table(["Stage", "Tasks", "Done", "Late"], [[b["stage"], str(b["total"]), str(b["done"]), str(b["late"])] for b in w["by_stage"] if b["total"]],
                  [0.46, 0.18, 0.18, 0.18], [{3: (180, 35, 28)} if b["late"] else {} for b in w["by_stage"] if b["total"]])
        if not customer and data.get("people"):
            doc.table(["Person", "Role", "Open", "Done", "Late"], [[x["name"], x.get("role") or "-", str(x["open"]), str(x["done"]), str(x["late"])] for x in data["people"]],
                      [0.34, 0.22, 0.14, 0.14, 0.16], [{4: (180, 35, 28)} if x["late"] else {} for x in data["people"]])
            if w.get("open"):
                doc.heading("Open tasks")
                doc.table(["Task", "Stage", "Who", "Due"], [[t["title"], t.get("stage") or "-", t.get("who") or "-", (fmt_date(t["due_date"]) + (" - late" if t["late"] else "")) if t.get("due_date") else "-"] for t in w["open"]],
                          [0.46, 0.2, 0.16, 0.18], [{3: (180, 35, 28)} if t["late"] else {} for t in w["open"]])

    def history():
        hist = data["history"]
        doc.heading("Stage history", "time in each stage against its SLA")
        doc.table(["Stage", "Entered", "Left", "Days", "SLA"],
                  [[x["stage"], fmt_date(x["entered"]), fmt_date(x["left"]) if x.get("left") else "still here", "-" if x["days"] is None else str(x["days"]), f"{x['sla']} d" if x.get("sla") else "-"] for x in hist["dwell"]],
                  [0.32, 0.2, 0.2, 0.14, 0.14], [{3: (138, 83, 0)} if x.get("over") else {} for x in hist["dwell"]])
        if hist.get("approvals"):
            doc.heading("Customer approvals")
            doc.table(["Stage", "Status", "Asked", "Decided", "Comment"],
                      [[a["stage"], a["status"], fmt_date(a["requested_at"]), fmt_date(a["decided_at"]) if a.get("decided_at") else "-", a.get("comment") or ""] for a in hist["approvals"]],
                      [0.22, 0.14, 0.16, 0.16, 0.32])

    def plan_changes():
        hist = data["history"]
        if not customer and data.get("plan_changes"):
            doc.heading("What moved in the plan")
            doc.table(["When", "Stage", "Change", "Why", "By"],
                      [[fmt_date(x["created_at"]), x.get("stage") or "-", "re-baselined" if x["field"] == "baseline" else f"{x['field']} {fmt_date(x['old'])} -> {fmt_date(x['new'])}", x.get("reason") or "", x["author"]] for x in data["plan_changes"]],
                      [0.14, 0.18, 0.3, 0.24, 0.14])

    def notes():
        hist = data["history"]
        if hist.get("notes"):
            doc.heading("Notes")
            for n in hist["notes"][:10]:
                doc.room(26)
                c.text(LEFT, doc.y, f"{n['author']} · {n['stage']} · {fmt_date(n['created_at'])}", 7.5, False, MUTED)
                doc.y += 11
                doc.para(n["note"], 9)
                doc.y += 2

    def asks():
        # what the outside parties were asked and answered, and their ratings at sign-off: internal only (the customer cut drops both)
        if customer or not (data.get("asks") or data.get("csat")):
            return
        rated = data.get("csat") or []
        doc.heading("Asked of the customer and partners", f"rated {rated[-1]['rating']} of 5 at sign-off" if rated else None)
        if data.get("asks"):
            doc.table(["Ask", "Who", "State", "What came back"],
                      [[a["title"], f"{a['assignee'] or '-'} ({a['assignee_role'] or '-'})", "done" if a["done"] else f"open · due {fmt_date(a['due_date'])}" if a.get("due_date") else "open",
                        (a["file"]["filename"] if a.get("file") else "; ".join(f"{x['label']}: {x['value']}" for x in a.get("answers", []))) or "-"] for a in data["asks"]],
                      [0.32, 0.22, 0.16, 0.3])
        for r in rated:
            if r.get("comment"):
                doc.para(f"\"{r['comment']}\" - {r['by_name']}, version {r['signoff_version']} ({r['rating']} of 5)", 9)

    def team():
        if data.get("team"):
            doc.heading("Team")
            doc.para(" · ".join(f"{m['name']} ({m['role']})" for m in data["team"]), 9)

    sections = {"numbers": numbers, "summary": summary, "timeline": timeline, "raid": raid, "work": work,
                "history": history, "plan_changes": plan_changes, "notes": notes, "asks": asks, "team": team}
    for key in order(tpl):
        sections[key]()
    doc.block("closing", values)
    return c.render(doc.footer(f"Odin · {data['company']} · {p['name']} · {'customer copy' if customer else 'internal'}"))


def _boxes(doc, boxes):
    """A row of number boxes: (label, value, sub, bad)."""
    c = doc.c
    bw = (WIDTH - 8 * (len(boxes) - 1)) / len(boxes)
    for i, (label, value, sub, bad) in enumerate(boxes):
        bx = LEFT + i * (bw + 8)
        c.rect(bx, doc.y, bw, 52, fill=FAINT)
        c.text(bx + 9, doc.y + 8, label, 7.5, False, MUTED)
        c.text(bx + 9, doc.y + 20, c.fit(value, 14, bw - 18, True), 14, True, (180, 35, 28) if bad else INK)
        c.text(bx + 9, doc.y + 38, c.fit(sub, 7.5, bw - 18), 7.5, False, MUTED)
    doc.y += 64


def _roadmap(doc, rows, today):
    """One bar per rollout from its start to its forecast finish: done so far
    solid, the rest pale, the baseline finish as a tick, the target as a dashed tick."""
    c = doc.c
    dates = [d for r in rows for d in map(iso_date, (r["start"], r["forecast"], r["baseline"], r["target_end_date"])) if d] + [iso_date(today)]
    t0, t1 = min(dates) - timedelta(days=5), max(dates) + timedelta(days=5)
    label_w, row_h = 150, 16
    track_x, track_w = LEFT + label_w, WIDTH - label_w
    x = lambda d: track_x + track_w * ((d - t0).days / max(1, (t1 - t0).days)) if d else track_x   # noqa: E731

    def ticks():
        if _opening_month(t0, t1):
            c.text(x(t0) + 2, doc.y, t0.strftime("%b '%y"), 7, False, MUTED)
        m = date(t0.year, t0.month, 1)
        while m <= t1:
            if m >= t0 and x(m) < RIGHT - 20:
                c.text(x(m) + 2, doc.y, m.strftime("%b '%y"), 7, False, MUTED)
            m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
        doc.y += 12
    doc.room(40)
    ticks()
    top = doc.y
    for r in rows:
        if doc.y + row_h > c.H - 44:
            tx = x(iso_date(today))
            c.line(tx, top, tx, doc.y, doc.accent, 0.9)
            doc._new_page(); ticks(); top = doc.y
        y, mid = doc.y, doc.y + row_h / 2
        soft, strong = RAG[r["rag"]][0], MARK[r["rag"]]
        c.rect(LEFT, mid - 2.5, 5, 5, fill=strong)
        c.text(LEFT + 9, y + 3.5, c.fit(f"{r['name']}", 8, label_w - 14), 8, False, INK)
        c.line(track_x, y + row_h, RIGHT, y + row_h, FAINT, 0.5)
        s, f = iso_date(r["start"]), iso_date(r["forecast"]) or iso_date(today)
        now = min(max(iso_date(today), s), f)
        c.rect(x(s), mid - 3, max(2, x(now) - x(s)), 6, fill=strong)
        if f > now:
            c.rect(x(now), mid - 3, max(2, x(f) - x(now)), 6, fill=soft, stroke=strong, width=0.4)
        if r["baseline"]:
            bx = x(iso_date(r["baseline"]))
            c.rect(bx - 0.6, mid - 5.5, 1.2, 11, fill=(120, 124, 134))
        if r["target_end_date"]:
            tx = x(iso_date(r["target_end_date"]))
            c.line(tx, mid - 6, tx, mid + 6, BAD_LINE, 0.9, dash=(1.5, 1.5))
        doc.y += row_h
    tx = x(iso_date(today))
    c.line(tx, top, tx, doc.y, doc.accent, 0.9)
    c.text(tx - 9, doc.y + 2, "today", 7, True, doc.accent)
    doc.y += 14
    lx = LEFT
    for label, draw in (("Done so far", lambda: c.rect(lx, doc.y + 1.5, 14, 5, fill=(86, 88, 94))),
                        ("Forecast", lambda: c.rect(lx, doc.y + 1.5, 14, 5, fill=FAINT, stroke=(86, 88, 94), width=0.4)),
                        ("Baseline finish", lambda: c.rect(lx + 6, doc.y - 1, 1.2, 10, fill=(120, 124, 134))),
                        ("Target", lambda: c.line(lx + 7, doc.y - 1, lx + 7, doc.y + 9, BAD_LINE, 0.9, dash=(1.5, 1.5)))):
        draw()
        c.text(lx + 18, doc.y, label, 7.5, False, MUTED)
        lx += 18 + c.width(label, 7.5) + 14
    doc.y += 16


def render_portfolio(data, tpl=None):
    """PDF bytes for the portfolio report (data from services.portfolio.build), laid out by a document template."""
    from services.doc_templates import default_config, order
    tpl = tpl or default_config("portfolio")
    doc = _Doc(data, label=f"{tpl['title']} · internal", running=tpl["title"], tpl=tpl)
    c, s, rows = doc.c, data["summary"], data["rows"]
    values = {"company": data["company"], "date": fmt_date(data["today"]), "project": "", "client": "", "pm": "", "po": "", "stage": "", "target": "", "forecast": ""}
    c.text(LEFT, doc.y, c.fit(tpl["title"], 18, WIDTH, True), 18, True)
    doc.y += 24
    c.text(LEFT, doc.y, f"{s['count']} active rollouts, as of {fmt_date(data['today'])}", 9, False, MUTED)
    doc.y += 18
    doc.company_line()
    doc.block("intro", values)

    def health():
        h = s["health"]   # health mix: one bar split by health
        x0 = LEFT
        for rag in ("red", "amber", "green", "done"):
            n = h.get(rag, 0)
            if n:
                w = WIDTH * n / max(1, s["count"])
                c.rect(x0, doc.y, max(1, w - 2), 8, fill=MARK[rag])
                x0 += w
        doc.y += 13
        lx = LEFT
        for rag in ("red", "amber", "green", "done"):
            if h.get(rag):
                label = f"{RAG[rag][2]} {h[rag]}"
                c.rect(lx, doc.y + 2, 5, 5, fill=MARK[rag])
                c.text(lx + 9, doc.y, label, 8, False, INK)
                lx += 9 + c.width(label, 8) + 14
        doc.y += 20
        _boxes(doc, [("Late against target", str(s["late_vs_target"]), f"of {s['count']} rollouts", s["late_vs_target"] > 0),
                     ("Behind baseline", str(s["behind_baseline"]), "no baseline data" if s["avg_slip"] is None else f"average {s['avg_slip']:+} d", False),
                     ("Open blockers", str(s["blockers"]), "across the portfolio", s["blockers"] > 0),
                     ("Finishing in 30 days", str(s["finishing_30d"]), "by forecast", False)]
                    + ([("Customer rating", f"{s['csat']} of 5", f"{s['csat_count']} rated at sign-off", False)] if s.get("csat") is not None else []))

    def roadmap():
        if rows:
            doc.heading("Roadmap", "start to forecast finish, worst health first")
            _roadmap(doc, rows, data["today"])

    def slippage():
        league = sorted([r for r in rows if r.get("vs_baseline_days")], key=lambda r: -r["vs_baseline_days"])[:12]
        if league:
            doc.heading("Slippage", "against each rollout's baseline")
            doc.table(["Rollout", "Stage", "Against baseline", "Forecast", "Against target", "Confidence"],
                      [[r["name"], r["stage"], f"{abs(r['vs_baseline_days'])} d {'late' if r['vs_baseline_days'] > 0 else 'early'}", fmt_date(r["forecast"]),
                        "-" if r["vs_target_days"] is None else f"{abs(r['vs_target_days'])} d {'after' if r['vs_target_days'] > 0 else 'before'}", r["confidence"]] for r in league],
                      [0.3, 0.16, 0.14, 0.13, 0.14, 0.13],
                      [{2: (180, 35, 28)} if r["vs_baseline_days"] > 0 else {} for r in league])

    def risks():
        if data["risks"]:
            doc.heading("Blockers and high-impact risks", f"{len(data['risks'])} open")
            doc.table(["Rollout", "Kind", "Item", "Owner", "Due"],
                      [[r["project"], r["kind"].title(), r["title"], r.get("owner_name") or "-", fmt_date(r.get("due_date")) if r.get("due_date") else "-"] for r in data["risks"]],
                      [0.22, 0.1, 0.4, 0.14, 0.14], [{1: (180, 35, 28)} if r["kind"] == "blocker" else {} for r in data["risks"]])

    def table():
        doc.heading("Every rollout")
        def mark(m):   # the rollout's next milestone (services/milestones.summary_of), and how many it missed
            m = m or {}
            nxt = f"{m['next']['name']} {fmt_date(m['next']['date'])}" if m.get("next") else "-"
            return nxt + (f" ({m['missed']} missed)" if m.get("missed") else "")
        doc.table(["Rollout", "Client", "Health", "Stage", "Done", "Forecast", "Target", "Next milestone", "PM"],
                  [[r["name"], r["client"] or "-", RAG[r["rag"]][2], f"{r['stage_number']}/{r['stage_count']} {r['stage']}", f"{r['pct_complete']}%",
                    fmt_date(r["forecast"]), fmt_date(r["target_end_date"]) if r["target_end_date"] else "-", mark(r.get("milestones")), r["owner_name"]] for r in rows],
                  [0.16, 0.1, 0.08, 0.14, 0.05, 0.1, 0.1, 0.18, 0.09],
                  [{2: RAG[r["rag"]][1], **({7: (180, 35, 28)} if (r.get("milestones") or {}).get("missed") else {})} for r in rows])

    sections = {"health": health, "roadmap": roadmap, "slippage": slippage, "risks": risks, "table": table}
    for key in order(tpl):
        sections[key]()
    doc.block("closing", values)
    return c.render(doc.footer(f"Odin · {data['company']} · portfolio report"))
