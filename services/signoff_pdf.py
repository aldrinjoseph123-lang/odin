"""The sign-off document as a PDF: what was agreed and delivered, what is
left, the terms, the acceptance statement, both signature blocks (drawn
signatures as vector strokes) and the signing record with the document's
fingerprint. Drawn with the report PDF's page builder (services/report_pdf)."""
from services.fmt import fmt_date
from services.report_pdf import BAD_LINE, FAINT, HAIR, INK, LEFT, MUTED, RAG, WIDTH, _Doc

STATUS = {
    "sent": ("amber", "Awaiting the customer's signature"), "signed": ("amber", "Signed by the customer, awaiting our countersignature"),
    "countersigned": ("green", "Signed by both parties"), "uploaded": ("green", "Signed on paper; the signed copy is on file"),
    "waived": ("done", "Closed without signatures (waived)"), "rejected": ("red", "Not accepted by the customer"), "withdrawn": ("done", "Withdrawn"),
}
SCOPE_WORD = {"delivered": "Delivered", "partial": "Partly delivered", "descoped": "Descoped", "agreed": "Agreed"}


def _when(iso):
    return f"{fmt_date(iso)}, {iso[11:16]} UTC" if iso and len(iso) > 15 else fmt_date(iso)


def _signature(c, sig, x, y, w, h):
    if not sig:
        return
    if sig["kind"] == "typed":
        c.text(x + 6, y + h / 2 - 9, c.fit(sig["text"], 20, w - 12), 20, False, INK)
        return
    k = min(w / 1000, h / 300)
    ox, oy = x + (w - 1000 * k) / 2, y + (h - 300 * k) / 2
    for stroke in sig["strokes"]:
        for (x1, y1), (x2, y2) in zip(stroke, stroke[1:]):
            c.line(ox + x1 * k, oy + y1 * k, ox + x2 * k, oy + y2 * k, INK, 1.1)


def render(v):
    """PDF bytes for one version (services.signoff.view)."""
    from services.doc_templates import default_config, section_on
    d, p = v["content"], v["content"]["project"]
    tpl = d.get("template") or default_config("signoff")   # frozen with the version (older versions: the built-in)
    doc = _Doc({"company": p["company"], "today": v["completed_at"] or v["created_at"]}, label=f"{tpl['title']} · version {v['version']}",
               running=f"{p['name']} · sign-off v{v['version']}", tpl=tpl)
    c = doc.c
    c.text(LEFT, doc.y, c.fit(tpl["title"], 18, WIDTH, True), 18, True)
    doc.y += 24
    c.text(LEFT, doc.y, c.fit(p["name"], 12, WIDTH, True), 12, True)
    doc.y += 18
    doc.company_line()
    if d.get("intro"):
        doc.para(d["intro"]); doc.y += 6
    facts = [("Customer", p["client"]), ("Delivered by", p["company"] + (f" with {p['partner_name']}" if p.get("partner_name") else "")),
             ("Purchase order", " · ".join(x for x in (p.get("po_number"), fmt_date(p.get("po_date")) if p.get("po_date") else None) if x) or "-"),
             ("Project manager", p["owner_name"]), ("Solution", " ".join(x for x in (p.get("vendor_name"), p.get("product_name")) if x) or "-"),
             ("Started", fmt_date(p.get("start_date"))), ("Target", fmt_date(p.get("target_end_date"))), ("Issued", fmt_date(p.get("finished")))]
    col = WIDTH / 2
    if section_on(tpl, "facts"):
        for i, (label, value) in enumerate(facts):
            x, y = LEFT + (i % 2) * col, doc.y + (i // 2) * 14
            c.text(x, y, label, 8, False, MUTED)
            c.text(x + 88, y, c.fit(value or "-", 9, col - 96), 9, False, INK)
        doc.y += 14 * ((len(facts) + 1) // 2) + 8

    rag, word = STATUS.get(v["status"], ("done", v["status"]))
    soft, strong = RAG[rag][0], RAG[rag][1]
    pw = c.width(word, 9, True) + 22
    c.rect(LEFT, doc.y, pw, 17, fill=soft)
    c.rect(LEFT + 7, doc.y + 6.5, 4, 4, fill=strong)
    c.text(LEFT + 15, doc.y + 3.8, word, 9, True, strong)
    doc.y += 28

    def summary():
        doc.heading("Summary")
        doc.para(d["summary"])

    def scope():
        if d["scope"]:
            doc.heading("Agreed scope and what was delivered", f"{sum(1 for x in d['scope'] if x['status'] == 'delivered')} of {len(d['scope'])} delivered in full")
            doc.table(["#", "Scope item", "Status", "Notes"],
                      [[str(i + 1), x["title"] + (f" - {x['detail']}" if x.get("detail") else ""), SCOPE_WORD.get(x["status"], x["status"]), x.get("note") or ""] for i, x in enumerate(d["scope"])],
                      [0.05, 0.47, 0.16, 0.32], [{2: (138, 83, 0)} if x["status"] == "partial" else {2: MUTED} if x["status"] == "descoped" else {} for x in d["scope"]])
        else:
            doc.heading("What was delivered")
            doc.bullets(d["delivered"] or ["-"])

    def outstanding():
        doc.heading("Outstanding items", "recorded here; they do not hold up acceptance")
        doc.bullets(d["outstanding"] or ["None."])

    def terms():
        if d["terms"]:
            doc.heading("Handover and support")
            doc.bullets(d["terms"])

    sections = {"summary": summary, "scope": scope, "outstanding": outstanding, "terms": terms}
    for key in [s["key"] for s in tpl["sections"] if s["on"] and s["key"] in sections]:
        sections[key]()
    if d.get("closing"):
        doc.y += 6
        doc.para(d["closing"])

    doc.heading("Acceptance")
    lines = c.wrap(d["statement"], 9.5, WIDTH - 20)
    doc.room(len(lines) * 13.5 + 16)
    c.rect(LEFT, doc.y - 4, WIDTH, len(lines) * 13.5 + 10, fill=FAINT)
    for line in lines:
        c.text(LEFT + 10, doc.y, line, 9.5, False, INK)
        doc.y += 13.5
    doc.y += 14

    # the two signature blocks, side by side
    doc.room(150)
    gap = 18
    bw = (WIDTH - gap) / 2
    blocks = [(f"For {p['client']}", v["signature"], v["signer_name"], v["signer_title"], v["signed_at"], (d.get("signer") or {}).get("name")),
              (f"For {p['company']}", v["counter_signature"], v["counter_name"], v["counter_title"], v["counter_signed_at"], (d.get("countersigner") or {}).get("name"))]
    top = doc.y
    for i, (label, sig, name, title, when, named) in enumerate(blocks):
        x = LEFT + i * (bw + gap)
        c.text(x, top, label, 9, True, INK)
        c.rect(x, top + 16, bw, 64, stroke=HAIR, width=0.8)
        if sig:
            _signature(c, sig, x, top + 16, bw, 64)
        elif v["status"] == "uploaded" and i == 0:
            c.text(x + 8, top + 42, "Signed on paper - copy on file", 8.5, False, MUTED)
        y = top + 88
        for k, val in (("Name", name or (named and f"{named} (to sign)") or ""), ("Title", title or ""), ("Date", fmt_date(when) if when else "")):
            c.text(x, y, k, 7.5, False, MUTED)
            c.text(x + 34, y, c.fit(val, 9, bw - 40), 9, False, INK)
            c.line(x + 32, y + 11, x + bw, y + 11, HAIR, 0.6)
            y += 16
    doc.y = top + 148

    # the signing record
    doc.heading("Signing record")
    rows = [["Version", f"{v['version']}, prepared by {v['created_by']} on {_when(v['created_at'])}"],
            ["Fingerprint", f"SHA-256 {v['content_hash']}"],
            ["Integrity", "The content matches its fingerprint." if v["intact"] else "WARNING: the content no longer matches its fingerprint."]]
    if v["signed_at"] and v["status"] != "uploaded":
        rows.append(["Customer", f"{v['signer_name']} <{v['signer_email']}> signed {_when(v['signed_at'])} in Odin, after a one-time sign-in link sent to that address"
                     + (f"; from {v['signed_ip']}" if v.get("signed_ip") else "")])
    if v.get("link_issued_by"):
        rows.append(["Sign-in link", f"The signatory's one-time sign-in link was issued by {v['link_issued_by']} on {_when(v['link_issued_at'])} and passed on by hand"])
    if v["counter_signed_at"]:
        rows.append(["Countersigned", f"{v['counter_name']} signed {_when(v['counter_signed_at'])} in Odin" + (f"; from {v['counter_ip']}" if v.get("counter_ip") else "")])
    if v["status"] == "uploaded":
        rows.append(["Paper copy", f"Signed by {v['signer_name']} on {fmt_date(v['signed_at'])}; the scanned copy is document #{v['document_id']} on the rollout"])
    if v["status"] == "rejected":
        rows.append(["Not accepted", f"{_when(v['rejected_at'])}: {v['reject_comment']}"])
    if v["status"] == "waived":
        rows.append(["Waived", f"by {v['waived_by']} on {_when(v['completed_at'])}: {v['waiver_reason']}"])
    tones = [{1: BAD_LINE} if r[0] in ("Integrity",) and not v["intact"] else {} for r in rows]
    for (label, text), tone in zip(rows, tones):
        chunks = c.wrap(text, 8.5, WIDTH - 90)
        doc.room(len(chunks) * 11.5 + 4)
        c.text(LEFT, doc.y, label, 8, False, MUTED)
        for chunk in chunks:
            c.text(LEFT + 90, doc.y, chunk, 8.5, False, tone.get(1, INK))
            doc.y += 11.5
        doc.y += 3
    return c.render(doc.footer(f"Odin · {p['company']} · {p['name']} · sign-off v{v['version']} · SHA-256 {v['content_hash'][:16]}…"))
