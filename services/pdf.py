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


# ---- a small drawing canvas: text, filled and stroked rectangles, lines ----
# Coordinates are points from the TOP-left of an A4 page (the PDF's own
# origin is bottom-left; the canvas flips). Colours are (r, g, b) in 0–255.
# Same two standard fonts and the same Windows-1252 ceiling as above.

_TRANSLATE = str.maketrans({"\u2192": "->", "\u2190": "<-", "\u2264": "<=", "\u2265": ">=", "\u2713": "v", "\u00d7": "x", "\u2212": "-"})


def _rgb(c):
    return b"%.3f %.3f %.3f" % tuple(v / 255 for v in c)


class Canvas:
    W, H = PAGE_W, PAGE_H

    def __init__(self):
        self.pages = []
        self.ops = None

    def page(self):
        self.ops = []
        self.pages.append(self.ops)

    def text(self, x, y, s, size=10, bold=False, color=(16, 17, 20)):
        """Text with its baseline `size` points below y (y is the line's top)."""
        s = str(s).translate(_TRANSLATE)
        self.ops.append(_rgb(color) + b" rg BT /F%d %.1f Tf %.1f %.1f Td (" % (2 if bold else 1, size, x, self.H - y - size * 0.82) + _esc(s) + b") Tj ET")

    def rect(self, x, y, w, h, fill=None, stroke=None, width=0.8):
        if w <= 0 or h <= 0:
            return
        box = b"%.1f %.1f %.1f %.1f re" % (x, self.H - y - h, w, h)
        if fill and stroke:
            self.ops.append(_rgb(fill) + b" rg " + _rgb(stroke) + b" RG %.2f w " % width + box + b" B")
        elif fill:
            self.ops.append(_rgb(fill) + b" rg " + box + b" f")
        elif stroke:
            self.ops.append(_rgb(stroke) + b" RG %.2f w " % width + box + b" S")

    def line(self, x1, y1, x2, y2, color=(208, 211, 218), width=0.8, dash=None):
        d = b"[%d %d] 0 d " % dash if dash else b"[] 0 d "
        self.ops.append(_rgb(color) + b" RG %.2f w " % width + d + b"%.1f %.1f m %.1f %.1f l S [] 0 d" % (x1, self.H - y1, x2, self.H - y2))

    @staticmethod
    def width(s, size, bold=False):
        return _width(str(s).translate(_TRANSLATE), size, bold)

    def fit(self, s, size, width, bold=False):
        """`s` cut with an ellipsis to fit `width` points."""
        s = str(s or "")
        if self.width(s, size, bold) <= width:
            return s
        while s and self.width(s + "\u2026", size, bold) > width:
            s = s[:-1]
        return s + "\u2026"

    def wrap(self, s, size, width, bold=False):
        out = []
        for para in str(s or "").split("\n"):
            out += _wrap(para.translate(_TRANSLATE), size, width, bold) if para.strip() else [""]
        return out

    def render(self, footer=""):
        objects = [None, None,
                   b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
                   b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
        kids = []
        for n, ops in enumerate(self.pages, 1):
            foot = f"{footer}  \u00b7  page {n} of {len(self.pages)}" if footer else f"page {n} of {len(self.pages)}"
            stream = b"\n".join(ops + [b"0.42 0.45 0.5 rg BT /F1 7.5 Tf %d %d Td (" % (MARGIN - 16, 22) + _esc(foot) + b") Tj ET"])
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
