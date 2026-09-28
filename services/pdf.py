"""A small PDF writer for Odin's plain-text reports — no dependency.

A saved report is lines of text: "# " headings, "- " list items, paragraphs
(services/reports.py). This lays them out on A4 with the PDF standard
Helvetica fonts: wrapped by measured width, bold headings, bulleted items,
new pages as needed, a title and a footer line on every page.

Ceiling: the standard fonts cover Western European text (Windows-1252).
Anything outside it (Arabic, CJK, emoji) prints as "?" — fine for delivery
reports written in English; an embedded TrueType font is the upgrade path.
"""

# Helvetica advance widths (1/1000 em) for the printable ASCII range 32..126;
# anything else is measured as a typical lowercase letter.
_W = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556,
      556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
      667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556,
      556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]
PAGE_W, PAGE_H, MARGIN = 595, 842, 56


def _width(text, size, bold=False):
    w = sum(_W[ord(c) - 32] if 32 <= ord(c) <= 126 else 556 for c in text)
    return w * size / 1000 * (1.06 if bold else 1)


def _wrap(text, size, width, bold=False):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and _width(trial, size, bold) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + [line] if line else lines or [""]


def _esc(text):
    raw = text.encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def report_pdf(title, lines, footer=""):
    """PDF bytes for a titled report of text lines ("# " heading, "- " item)."""
    pages, ops, y = [], [], PAGE_H - MARGIN

    def text(x, size, bold, s):
        ops.append(b"BT /F%d %d Tf %d %d Td (" % (2 if bold else 1, size, x, int(y)) + _esc(s) + b") Tj ET")

    def new_page():
        nonlocal ops, y
        if ops:
            pages.append(ops)
        ops, y = [], PAGE_H - MARGIN

    def room(h):
        nonlocal y
        if y - h < MARGIN + 20:
            new_page()

    for chunk in _wrap(title, 18, PAGE_W - 2 * MARGIN, bold=True):
        room(24)
        text(MARGIN, 18, True, chunk)
        y -= 24
    y -= 6
    for raw in lines:
        raw = raw.rstrip()
        if not raw:
            y -= 6
            continue
        if raw.startswith("# "):
            y -= 8
            for chunk in _wrap(raw[2:], 12.5, PAGE_W - 2 * MARGIN, bold=True):
                room(17)
                text(MARGIN, 12, True, chunk)
                y -= 17
            continue
        item = raw.startswith("- ")
        indent = 14 if item else 0
        for i, chunk in enumerate(_wrap(raw[2:] if item else raw, 10, PAGE_W - 2 * MARGIN - indent)):
            room(14)
            if item and i == 0:
                text(MARGIN + 2, 10, False, "\u2022")   # bullet (0x95 in Windows-1252)
            text(MARGIN + indent, 10, False, chunk)
            y -= 14
    new_page()

    # objects: 1 catalog, 2 pages, 3 Helvetica, 4 Helvetica-Bold, then (page, content) pairs
    objects = [None, None,
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
    kids = []
    for n, page_ops in enumerate(pages, 1):
        foot = f"{footer}  ·  page {n} of {len(pages)}".strip(" ·") if footer else f"page {n} of {len(pages)}"
        page_ops = page_ops + [b"BT /F1 8 Tf %d %d Td (" % (MARGIN, MARGIN - 24) + _esc(foot) + b") Tj ET"]
        stream = b"\n".join(page_ops)
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        content_id = len(objects)
        objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>"
                       % (PAGE_W, PAGE_H, content_id))
        kids.append(len(objects))
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % k for k in kids) + b"] /Count %d >>" % len(kids)

    out, offsets = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)
