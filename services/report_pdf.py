"""The rollout report as a PDF, drawn from the same data as the page
(services/report_data.py): brand band, health, the numbers, the words, the
plan-versus-actual timeline drawn as vectors, and the tables. Dependency-free
(services/pdf.Canvas): Helvetica, Windows-1252 text."""
from datetime import date, timedelta

from services.pdf import MARGIN, Canvas

INK, MUTED, HAIR, FAINT = (16, 17, 20), (91, 98, 112), (228, 230, 235), (243, 244, 246)
ACCENT, ACCENT_SOFT, WHITE = (61, 90, 254), (197, 206, 255), (255, 255, 255)
RAG = {"green": ((230, 246, 236), (23, 122, 66), "On track"), "amber": ((255, 244, 224), (138, 83, 0), "At risk"),
       "red": ((253, 236, 235), (180, 35, 28), "Off track"), "done": ((243, 244, 246), (91, 98, 112), "Complete")}
WARN_LINE, BAD_LINE, BRAND_RED = (227, 155, 29), (224, 70, 61), (225, 29, 46)
MARK = {"green": (31, 157, 85), "amber": WARN_LINE, "red": BAD_LINE, "done": (150, 154, 162)}   # fills wear the -line colours
LEFT, RIGHT = MARGIN - 16, Canvas.W - (MARGIN - 16)
WIDTH = RIGHT - LEFT


def _d(iso):
    return date.fromisoformat(iso[:10]) if iso else None


def _fmt(iso):
    d = _d(iso)
    return f"{d.day} {d.strftime('%b %Y')}" if d else "-"


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
            when = f"as of {_fmt(self.data['today'])}"
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


def _gantt(doc, stages, today, target, customer=False):
    """Plan (outline), actual (solid), forecast (pale), baseline (thin grey), today and target lines."""
    c = doc.c
    dates = [_d(x) for s in stages for x in (s.get("plan_start"), s.get("plan_end"), s.get("base_start"), s.get("base_end"),
                                              s.get("actual_start"), s.get("actual_end"), s.get("forecast_start"), s.get("forecast_end")) if x]
    dates += [d for d in (_d(today), _d(target)) if d]
    if not dates:
        return
    t0, t1 = min(dates) - timedelta(days=3), max(dates) + timedelta(days=3)
    label_w, row_h = 118, 17
    track_x, track_w = LEFT + label_w, WIDTH - label_w
    x = lambda d: track_x + track_w * ((d - t0).days / max(1, (t1 - t0).days))   # noqa: E731
    doc.room(22 + row_h * min(len(stages), 6))
    # month ticks
    m = date(t0.year, t0.month, 1)
    while m <= t1:
        if m >= t0:
            c.line(x(m), doc.y + 10, x(m), doc.y + 12 + row_h * len(stages), FAINT, 0.6)
            c.text(x(m) + 2, doc.y, m.strftime("%b %y"), 7, False, MUTED)
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    top = doc.y + 12
    for i, s in enumerate(stages):
        y = top + i * row_h
        if y + row_h > c.H - 44:
            doc._new_page(); top = doc.y - i * row_h; y = doc.y
        c.text(LEFT, y + 4, c.fit(s["name"], 8.5, label_w - 8, s["status"] == "current"), 8.5, s["status"] == "current", INK if s["status"] != "next" else MUTED)
        mid = y + row_h / 2
        if s.get("base_start") and s.get("base_end"):
            c.rect(x(_d(s["base_start"])), mid + 5, max(1.5, x(_d(s["base_end"])) - x(_d(s["base_start"]))), 1.6, fill=(208, 211, 218))
        if s.get("plan_start") and s.get("plan_end"):
            c.rect(x(_d(s["plan_start"])), mid - 4.5, max(2, x(_d(s["plan_end"])) - x(_d(s["plan_start"]))), 9, stroke=doc.accent, width=0.9)
        if s.get("actual_start") and (s.get("actual_end") or s["status"] == "current"):
            a0, a1 = _d(s["actual_start"]), _d(s["actual_end"]) or _d(today)
            late = s["status"] == "current" and s.get("plan_end") and s.get("forecast_end") and s["forecast_end"] > s["plan_end"]
            c.rect(x(a0), mid - 2.5, max(2, x(a1) - x(a0)), 5, fill=WARN_LINE if late else (doc.accent if s["status"] == "current" else (86, 88, 94)))
        if s.get("forecast_start") and s.get("forecast_end") and (s["status"] == "next" or (s["status"] == "current" and s["forecast_end"] > today)):
            f0 = _d(today) if s["status"] == "current" else _d(s["forecast_start"])
            c.rect(x(f0), mid - 2.5, max(2, x(_d(s["forecast_end"])) - x(f0)), 5, fill=doc.accent_soft)
    bottom = top + len(stages) * row_h
    c.line(x(_d(today)), top - 2, x(_d(today)), bottom, doc.accent, 1.1)
    c.text(x(_d(today)) - 9, bottom + 2, "today", 7, True, doc.accent)
    if target:
        c.line(x(_d(target)), top - 2, x(_d(target)), bottom, BAD_LINE, 0.9, dash=(3, 2))
        c.text(x(_d(target)) - 10, bottom + 2, "target", 7, False, BAD_LINE)
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
              "stage": p["stage"], "target": _fmt(f.get("target")), "forecast": _fmt(f.get("forecast")), "date": _fmt(data["today"])}

    c.text(LEFT, doc.y, c.fit(p["name"], 18, WIDTH, True), 18, True)
    doc.y += 24
    meta = " · ".join(x for x in (p["client"], f"PM {p['owner_name']}", f"stage {p['stage_number']} of {p['stage_count']}: {p['stage']}",
                                         p.get("po_number") and (p["po_number"] if p["po_number"].upper().startswith("PO") else f"PO {p['po_number']}")) if x)
    c.text(LEFT, doc.y, c.fit(meta, 9, WIDTH), 9, False, MUTED)
    doc.y += 18

    soft, strong, word = RAG[h["rag"]]
    pw = c.width(word, 9.5, True) + 22
    c.rect(LEFT, doc.y, pw, 17, fill=soft)
    c.rect(LEFT + 7, doc.y + 6.5, 4, 4, fill=strong)
    c.text(LEFT + 15, doc.y + 3.5, word, 9.5, True, strong)
    reasons = " ".join(h["reasons"]) if h["reasons"] and not customer else f"Status as of {_fmt(data['today'])}."
    for i, line in enumerate(c.wrap(reasons, 8.5, WIDTH - pw - 10)[:2]):
        c.text(LEFT + pw + 10, doc.y + 1 + i * 11, line, 8.5, False, MUTED)
    doc.y += 30
    doc.company_line()
    doc.block("intro", values)

    def numbers():
        # the numbers
        vs_t = f.get("vs_target_days")
        boxes = [("Forecast finish", _fmt(f.get("forecast")), "" if vs_t is None else f"{vs_t} d after target" if vs_t > 0 else f"{-vs_t} d before target", vs_t is not None and vs_t > 0),
                 ("Target", _fmt(f.get("target")), "" if f.get("days_to_target") is None else (f"{-f['days_to_target']} d ago" if f["days_to_target"] < 0 else f"{f['days_to_target']} d to go"), False),
                 ("Complete", f"{data['pct_complete']}%", f"{data['elapsed_days']} d since start", False)]
        if not customer:
            vb = f.get("vs_baseline_days")
            boxes.insert(2, ("Against baseline", "-" if vb is None else "on plan" if vb == 0 else f"{abs(vb)} d {'late' if vb > 0 else 'early'}",
                             f"baseline of {_fmt(data['baseline_at'])}" if data.get("baseline_at") else "no baseline", bool(vb and vb > 0)))
        _boxes(doc, boxes)

    def summary():
        doc.heading("Summary")
        doc.para(words.get("summary") or "-")
        if words.get("next_steps"):
            doc.heading("Next steps")
            doc.bullets([x for x in words["next_steps"].splitlines() if x.strip()])
        if customer and (words.get("asks") or data["needs"].get("approval") or data["needs"].get("tasks")):
            doc.heading("What we need from you")
            asks = [x for x in (words.get("asks") or "").splitlines() if x.strip()]
            if data["needs"].get("approval"):
                asks.append(f"Approve the {data['needs']['approval']['stage']} stage (asked {_fmt(data['needs']['approval']['requested_at'])}).")
            asks += [t["title"] + (" - due " + _fmt(t["due_date"]) if t.get("due_date") else "") for t in data["needs"].get("tasks", [])]
            doc.bullets(asks)

    def timeline():
        doc.heading("Timeline", "plan against actual, and the forecast for what is left")
        _gantt(doc, data["stages"], data["today"], f.get("target"), customer)
        cols = ["Stage", "Planned", "Actual", "Forecast end"] + ([] if customer else ["Slip"])
        widths = [0.24, 0.24, 0.24, 0.16] + ([] if customer else [0.12])
        rows, tones = [], []
        for s in data["stages"]:
            planned = f"{_fmt(s['plan_start'])} - {_fmt(s['plan_end'])}" if s.get("plan_start") else "-"
            actual = f"{_fmt(s['actual_start'])} - {_fmt(s['actual_end']) if s.get('actual_end') else 'now'}" if s.get("actual_start") else ("skipped" if s["status"] == "skipped" else "-")
            slip = s.get("slip_days")
            row = [s["name"] + (" (now)" if s["status"] == "current" else ""), planned, actual, _fmt(s.get("forecast_end"))]
            if not customer:
                row.append("-" if slip is None else "on plan" if slip == 0 else f"{abs(slip)} d {'late' if slip > 0 else 'early'}")
            rows.append(row)
            tones.append({4: (180, 35, 28)} if not customer and slip and slip > 0 else {})
        doc.table(cols, rows, widths, tones)

    def raid():
        raid = data.get("raid", [])
        if raid:
            doc.heading("Risks, issues, decisions and blockers" if not customer else "Decisions and open points", f"{sum(1 for r in raid if r['open'])} open")
            doc.table(["Kind", "Item", "Owner", "Impact", "Status", "Due"],
                      [[r["kind"].title(), r["title"] + (f" - {r['resolution']}" if r.get("resolution") else ""), r.get("owner_name") or "-",
                        r["impact"] if r["kind"] != "decision" else "", r["status"], _fmt(r.get("due_date")) if r.get("due_date") else "-"] for r in raid],
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
                doc.table(["Task", "Stage", "Who", "Due"], [[t["title"], t.get("stage") or "-", t.get("who") or "-", (_fmt(t["due_date"]) + (" - late" if t["late"] else "")) if t.get("due_date") else "-"] for t in w["open"]],
                          [0.46, 0.2, 0.16, 0.18], [{3: (180, 35, 28)} if t["late"] else {} for t in w["open"]])

    def history():
        hist = data["history"]
        doc.heading("Stage history", "time in each stage against its SLA")
        doc.table(["Stage", "Entered", "Left", "Days", "SLA"],
                  [[x["stage"], _fmt(x["entered"]), _fmt(x["left"]) if x.get("left") else "still here", "-" if x["days"] is None else str(x["days"]), f"{x['sla']} d" if x.get("sla") else "-"] for x in hist["dwell"]],
                  [0.32, 0.2, 0.2, 0.14, 0.14], [{3: (138, 83, 0)} if x.get("over") else {} for x in hist["dwell"]])
        if hist.get("approvals"):
            doc.heading("Customer approvals")
            doc.table(["Stage", "Status", "Asked", "Decided", "Comment"],
                      [[a["stage"], a["status"], _fmt(a["requested_at"]), _fmt(a["decided_at"]) if a.get("decided_at") else "-", a.get("comment") or ""] for a in hist["approvals"]],
                      [0.22, 0.14, 0.16, 0.16, 0.32])

    def plan_changes():
        hist = data["history"]
        if not customer and data.get("plan_changes"):
            doc.heading("What moved in the plan")
            doc.table(["When", "Stage", "Change", "Why", "By"],
                      [[_fmt(x["created_at"]), x.get("stage") or "-", "re-baselined" if x["field"] == "baseline" else f"{x['field']} {_fmt(x['old'])} -> {_fmt(x['new'])}", x.get("reason") or "", x["author"]] for x in data["plan_changes"]],
                      [0.14, 0.18, 0.3, 0.24, 0.14])

    def notes():
        hist = data["history"]
        if hist.get("notes"):
            doc.heading("Notes")
            for n in hist["notes"][:10]:
                doc.room(26)
                c.text(LEFT, doc.y, f"{n['author']} · {n['stage']} · {_fmt(n['created_at'])}", 7.5, False, MUTED)
                doc.y += 11
                doc.para(n["note"], 9)
                doc.y += 2

    def team():
        if data.get("team"):
            doc.heading("Team")
            doc.para(" · ".join(f"{m['name']} ({m['role']})" for m in data["team"]), 9)

    sections = {"numbers": numbers, "summary": summary, "timeline": timeline, "raid": raid, "work": work,
                "history": history, "plan_changes": plan_changes, "notes": notes, "team": team}
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
    dates = [_d(x) for r in rows for x in (r["start"], r["forecast"], r["baseline"], r["target_end_date"]) if x] + [_d(today)]
    t0, t1 = min(dates) - timedelta(days=5), max(dates) + timedelta(days=5)
    label_w, row_h = 150, 16
    track_x, track_w = LEFT + label_w, WIDTH - label_w
    x = lambda d: track_x + track_w * ((d - t0).days / max(1, (t1 - t0).days))   # noqa: E731

    def ticks():
        m = date(t0.year, t0.month, 1)
        while m <= t1:
            if m >= t0 and x(m) < RIGHT - 20:
                c.text(x(m) + 2, doc.y, m.strftime("%b %y"), 7, False, MUTED)
            m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
        doc.y += 12
    doc.room(40)
    ticks()
    top = doc.y
    for r in rows:
        if doc.y + row_h > c.H - 44:
            tx = x(_d(today))
            c.line(tx, top, tx, doc.y, doc.accent, 0.9)
            doc._new_page(); ticks(); top = doc.y
        y, mid = doc.y, doc.y + row_h / 2
        soft, strong = RAG[r["rag"]][0], MARK[r["rag"]]
        c.rect(LEFT, mid - 2.5, 5, 5, fill=strong)
        c.text(LEFT + 9, y + 3.5, c.fit(f"{r['name']}", 8, label_w - 14), 8, False, INK)
        c.line(track_x, y + row_h, RIGHT, y + row_h, FAINT, 0.5)
        s, f = _d(r["start"]), _d(r["forecast"]) or _d(today)
        now = min(max(_d(today), s), f)
        c.rect(x(s), mid - 3, max(2, x(now) - x(s)), 6, fill=strong)
        if f > now:
            c.rect(x(now), mid - 3, max(2, x(f) - x(now)), 6, fill=soft, stroke=strong, width=0.4)
        if r["baseline"]:
            bx = x(_d(r["baseline"]))
            c.rect(bx - 0.6, mid - 5.5, 1.2, 11, fill=(120, 124, 134))
        if r["target_end_date"]:
            tx = x(_d(r["target_end_date"]))
            c.line(tx, mid - 6, tx, mid + 6, BAD_LINE, 0.9, dash=(1.5, 1.5))
        doc.y += row_h
    tx = x(_d(today))
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
    values = {"company": data["company"], "date": _fmt(data["today"]), "project": "", "client": "", "pm": "", "po": "", "stage": "", "target": "", "forecast": ""}
    c.text(LEFT, doc.y, c.fit(tpl["title"], 18, WIDTH, True), 18, True)
    doc.y += 24
    c.text(LEFT, doc.y, f"{s['count']} active rollouts, as of {_fmt(data['today'])}", 9, False, MUTED)
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
                     ("Finishing in 30 days", str(s["finishing_30d"]), "by forecast", False)])

    def roadmap():
        if rows:
            doc.heading("Roadmap", "start to forecast finish, worst health first")
            _roadmap(doc, rows, data["today"])

    def slippage():
        league = sorted([r for r in rows if r.get("vs_baseline_days")], key=lambda r: -r["vs_baseline_days"])[:12]
        if league:
            doc.heading("Slippage", "against each rollout's baseline")
            doc.table(["Rollout", "Stage", "Against baseline", "Forecast", "Against target", "Confidence"],
                      [[r["name"], r["stage"], f"{abs(r['vs_baseline_days'])} d {'late' if r['vs_baseline_days'] > 0 else 'early'}", _fmt(r["forecast"]),
                        "-" if r["vs_target_days"] is None else f"{abs(r['vs_target_days'])} d {'after' if r['vs_target_days'] > 0 else 'before'}", r["confidence"]] for r in league],
                      [0.3, 0.16, 0.14, 0.13, 0.14, 0.13],
                      [{2: (180, 35, 28)} if r["vs_baseline_days"] > 0 else {} for r in league])

    def risks():
        if data["risks"]:
            doc.heading("Blockers and high-impact risks", f"{len(data['risks'])} open")
            doc.table(["Rollout", "Kind", "Item", "Owner", "Due"],
                      [[r["project"], r["kind"].title(), r["title"], r.get("owner_name") or "-", _fmt(r.get("due_date")) if r.get("due_date") else "-"] for r in data["risks"]],
                      [0.22, 0.1, 0.4, 0.14, 0.14], [{1: (180, 35, 28)} if r["kind"] == "blocker" else {} for r in data["risks"]])

    def table():
        doc.heading("Every rollout")
        doc.table(["Rollout", "Client", "Health", "Stage", "Done", "Forecast", "Target", "PM"],
                  [[r["name"], r["client"] or "-", RAG[r["rag"]][2], f"{r['stage_number']}/{r['stage_count']} {r['stage']}", f"{r['pct_complete']}%",
                    _fmt(r["forecast"]), _fmt(r["target_end_date"]) if r["target_end_date"] else "-", r["owner_name"]] for r in rows],
                  [0.2, 0.13, 0.09, 0.18, 0.06, 0.11, 0.11, 0.12],
                  [{2: RAG[r["rag"]][1]} for r in rows])

    sections = {"health": health, "roadmap": roadmap, "slippage": slippage, "risks": risks, "table": table}
    for key in order(tpl):
        sections[key]()
    doc.block("closing", values)
    return c.render(doc.footer(f"Odin · {data['company']} · portfolio report"))
