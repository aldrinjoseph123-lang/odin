"""A small PDF writer for Odin's plain-text reports — no dependency.

A saved report is lines of text: "# " headings, "- " list items, paragraphs
(services/reports.py). This lays them out on A4 with the PDF standard
Helvetica fonts: wrapped by measured width, bold headings, bulleted items,
new pages as needed, a title and a footer line on every page.

Text Helvetica cannot print (beyond Windows-1252) is set in embedded Noto
Sans: Latin, Greek, Cyrillic and Arabic, the Arabic joined from Unicode's
presentation forms and laid right to left (services/fonts, built by
scripts/build_pdf_fonts.py). Ceiling: Chinese, Japanese, Korean and emoji
still print as "?" (those fonts run to megabytes).
"""
import json
import os
import unicodedata
import zlib

# Helvetica advance widths (1/1000 em) for the printable ASCII range 32..126;
# anything else is measured as a typical lowercase letter.
_W = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556,
      556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
      667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556,
      556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]
PAGE_W, PAGE_H, MARGIN = 595, 842, 56


def _width(text, size, bold=False):
    if not _plain(text):
        return sum(adv for _, glyphs in _segments(text, bold) for _, adv, _ in glyphs) * size / 1000
    w = sum(_W[ord(c) - 32] if 32 <= ord(c) <= 126 else 556 for c in text)
    return w * size / 1000 * (1.06 if bold else 1)


# ---- text beyond Windows-1252: the embedded Noto fonts ----------------------

_FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
_LATIN, _ARABIC = ("NotoSans-Regular.ttf", "NotoSans-Bold.ttf"), ("NotoSansArabic-Regular.ttf", "NotoSansArabic-Bold.ttf")
_FONT_ORDER = _LATIN + _ARABIC
_cache = {}


def _metrics():
    if "m" not in _cache:
        with open(os.path.join(_FONTS, "metrics.json")) as fh:
            raw = json.load(fh)
        _cache["m"] = {name: {**m, "chars": {int(k): v for k, v in m["chars"].items()}} for name, m in raw.items()}
    return _cache["m"]


def _plain(text):
    try:
        text.encode("cp1252")
        return True
    except UnicodeEncodeError:
        return False


def _is_arabic(c):
    o = ord(c)
    return 0x600 <= o <= 0x6FF or 0x750 <= o <= 0x77F or 0x8A0 <= o <= 0x8FF or 0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF


_ALEFS = ("\u0622", "\u0623", "\u0625", "\u0627")


def _forms():
    """{(letter or lam+alef, "isolated"|"final"|"initial"|"medial"): presentation form},
    read from Unicode's own decompositions — the joining table, no library."""
    if "forms" not in _cache:
        forms = {}
        for o in range(0xFB50, 0xFF00):
            parts = unicodedata.decomposition(chr(o)).split()
            if len(parts) >= 2 and parts[0] in ("<isolated>", "<final>", "<initial>", "<medial>"):
                base = "".join(chr(int(h, 16)) for h in parts[1:])
                if len(base) == 1 or (base[0] == "\u0644" and base[1:] in _ALEFS):   # letters, and the one required ligature
                    forms.setdefault((base, parts[0][1:-1]), chr(o))
        _cache["forms"] = forms
    return _cache["forms"]


def _shape(run):
    """An Arabic run in logical order → its presentation forms in visual
    (left-to-right drawing) order: each letter joined to its neighbours."""
    forms, out, i = _forms(), [], 0
    has = lambda c, f: (c, f) in forms   # noqa: E731
    forward = lambda c: has(c, "initial") or has(c, "medial")   # noqa: E731 — dual-joining: connects to the next letter
    marks = lambda j: unicodedata.category(run[j]) == "Mn"   # noqa: E731
    letters = [j for j in range(len(run)) if not marks(j)]
    for k, j in enumerate(letters):
        if i > j:
            continue
        c = run[j]
        prev = run[letters[k - 1]] if k and letters[k - 1] < j else None
        after = letters[k + 1] if k + 1 < len(letters) else None
        nxt = run[after] if after is not None else None
        back = prev is not None and forward(prev) and has(c, "final")
        if c == "\u0644" and nxt in _ALEFS and has(c + nxt, "isolated"):   # lam + alef: one ligature
            out.append(forms[(c + nxt, "final" if back else "isolated")])
            out.extend(run[m] for m in range(j + 1, after) if marks(m))
            i = after + 1
            continue
        ahead = nxt is not None and forward(c) and has(nxt, "final")
        form = "medial" if back and ahead else "final" if back else "initial" if ahead else "isolated"
        out.append(forms.get((c, form)) or forms.get((c, "isolated")) or c)
        out.extend(run[m] for m in range(j + 1, after if after is not None else len(run)) if marks(m))
        i = j + 1
    return "".join(reversed(out))


def _segments(text, bold):
    """[(font file, [(glyph id, advance, char)])] in drawing order: runs of
    Arabic shaped and reversed, the rest left to right; each character from
    the font that has it, "?" when none does."""
    m = _metrics()
    latin, arabic = _LATIN[bold], _ARABIC[bold]
    kinds = ["R" if _is_arabic(c) and unicodedata.category(c) != "Nd" else "L" for c in text]
    for i, c in enumerate(text):   # a space between two Arabic words stays in the Arabic run
        if c == " " and 0 < i < len(text) - 1 and kinds[i - 1] == "R" and "R" in kinds[i + 1:i + 2]:
            kinds[i] = "R"
    runs, start = [], 0
    for i in range(1, len(text) + 1):
        if i == len(text) or kinds[i] != kinds[start]:
            runs.append((kinds[start], text[start:i]))
            start = i
    out = []
    for kind, run in runs:
        for c in (_shape(run) if kind == "R" else run):
            for name in ((arabic, latin) if _is_arabic(c) else (latin, arabic)):
                g = m[name]["chars"].get(ord(c))
                if g:
                    break
            else:
                name, g = latin, m[latin]["chars"][ord("?")]
            if out and out[-1][0] == name:
                out[-1][1].append((g[0], g[1], c))
            else:
                out.append((name, [(g[0], g[1], c)]))
    return out


def _show(s, size, bold, used):
    """The text operators for `s` at the current position: Helvetica for
    Windows-1252, else the Noto glyphs (noted in `used` for embedding)."""
    if _plain(s):
        return b"/F%d %s Tf (" % (2 if bold else 1, b"%g" % size) + _esc(s) + b") Tj"
    ops = []
    for name, glyphs in _segments(s, bold):
        n = _FONT_ORDER.index(name)
        used.setdefault(name, {}).update({g: (adv, c) for g, adv, c in glyphs})
        ops.append(b"/U%d %s Tf <" % (n, b"%g" % size) + b"".join(b"%04x" % g for g, _, _ in glyphs) + b"> Tj")
    return b" ".join(ops)


def _embed(used, objects):
    """Append the objects for every Noto font `used` names; returns the font
    resource entries (b"/U0 n 0 R ...")."""
    entries = []
    for name, glyphs in sorted(used.items()):
        m = _metrics()[name]
        with open(os.path.join(_FONTS, name), "rb") as fh:
            raw = fh.read()
        packed = zlib.compress(raw)
        objects.append(b"<< /Length %d /Length1 %d /Filter /FlateDecode >>\nstream\n" % (len(packed), len(raw)) + packed + b"\nendstream")
        file_id = len(objects)
        base = m["name"].encode("ascii", "replace")
        objects.append(b"<< /Type /FontDescriptor /FontName /%s /Flags 32 /FontBBox [%d %d %d %d] /ItalicAngle 0 /Ascent %d /Descent %d /CapHeight %d /StemV 80 /FontFile2 %d 0 R >>"
                       % (base, *m["bbox"], m["ascent"], m["descent"], m["cap"], file_id))
        desc_id = len(objects)
        widths = b" ".join(b"%d [%d]" % (g, adv) for g, (adv, _) in sorted(glyphs.items()))
        objects.append(b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /%s /CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
                       b"/FontDescriptor %d 0 R /CIDToGIDMap /Identity /W [%s] >>" % (base, desc_id, widths))
        cid_id = len(objects)
        # copy and search read the presentation forms back as their letters
        pairs = b"\n".join(b"<%04x> <%s>" % (g, "".join("%04x" % ord(x) for x in unicodedata.normalize("NFKC", c)).encode())
                            for g, (_, c) in sorted(glyphs.items()))
        cmap = (b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def "
                b"/CMapName /Adobe-Identity-UCS def /CMapType 2 def 1 begincodespacerange <0000> <ffff> endcodespacerange\n%d beginbfchar\n" % len(glyphs)
                + pairs + b"\nendbfchar endcmap CMapName currentdict /CMap defineresource pop end end")
        objects.append(b"<< /Length %d >>\nstream\n" % len(cmap) + cmap + b"\nendstream")
        objects.append(b"<< /Type /Font /Subtype /Type0 /BaseFont /%s /Encoding /Identity-H /DescendantFonts [%d 0 R] /ToUnicode %d 0 R >>"
                       % (base, cid_id, len(objects)))
        entries.append(b"/U%d %d 0 R" % (_FONT_ORDER.index(name), len(objects)))
    return b" ".join(entries)


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
    pages, ops, y, used = [], [], PAGE_H - MARGIN, {}

    def text(x, size, bold, s):
        ops.append(b"BT %d %d Td " % (x, int(y)) + _show(s, size, bold, used) + b" ET")

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
        page_ops = page_ops + [b"BT %d %d Td " % (MARGIN, MARGIN - 24) + _show(foot, 8, False, used) + b" ET"]
        stream = b"\n".join(page_ops)
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        content_id = len(objects)
        objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R /Resources << /Font << /F1 3 0 R /F2 4 0 R FONTS >> >> >>"
                       % (PAGE_W, PAGE_H, content_id))
        kids.append(len(objects))
    fonts = _embed(used, objects)
    objects = [o.replace(b"FONTS >>", fonts + b" >>") if o and o.startswith(b"<< /Type /Page ") else o for o in objects]
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


class Image:
    """A raster for Canvas.image: PNG (8/16-bit; grey, RGB, palette, with or
    without alpha; not interlaced) or JPEG, decoded without any library. JPEG
    is embedded as it is; PNG pixels are unfiltered and re-deflated, alpha
    becomes a soft mask. Anything malformed is a ValueError with words to
    show, never a crash; the size is checked before any pixel is inflated."""

    MAX_SIDE = 3000

    def __init__(self, data):
        import struct
        import zlib
        try:
            self._decode(data)
        except ValueError:
            raise
        except (struct.error, zlib.error, KeyError, IndexError, TypeError, NameError, MemoryError, OverflowError):
            raise ValueError("That image could not be read; save it again as a PNG or JPEG") from None
        if not (0 < self.w <= self.MAX_SIDE and 0 < self.h <= self.MAX_SIDE):
            raise ValueError(f"An image up to {self.MAX_SIDE} × {self.MAX_SIDE} pixels, please")

    def _decode(self, data):
        import struct
        import zlib
        if data[:2] == b"\xff\xd8":
            self._jpeg(data)
            return
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("Use a PNG or JPEG image")
        pos, idat, plte, trns = 8, b"", None, None
        while pos < len(data):
            n, kind = struct.unpack(">I4s", data[pos:pos + 8])
            chunk = data[pos + 8:pos + 8 + n]
            if kind == b"IHDR":
                w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
            elif kind == b"PLTE":
                plte = chunk
            elif kind == b"tRNS":
                trns = chunk
            elif kind == b"IDAT":
                idat += chunk
            pos += 12 + n
        if interlace:
            raise ValueError("Save the PNG without interlacing")
        if depth not in (8, 16) and ctype != 3:
            raise ValueError("Use an 8-bit PNG")
        if not (0 < w <= self.MAX_SIDE and 0 < h <= self.MAX_SIDE):   # before inflating: a tiny file may claim a huge picture
            raise ValueError(f"An image up to {self.MAX_SIDE} × {self.MAX_SIDE} pixels, please")
        channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
        bpp = channels * (2 if depth == 16 else 1)
        stride = (w * channels * depth + 7) // 8
        need = h * (stride + 1)
        raw, rows, prev = zlib.decompressobj().decompress(idat, need), [], bytearray(stride)   # never more than the picture needs
        if len(raw) < need:
            raise ValueError("That PNG is cut short")
        if ctype == 3 and not plte:
            raise ValueError("That PNG has no palette")
        for y in range(h):
            f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b, c = prev[i], prev[i - bpp] if i >= bpp else 0
                if f == 1:
                    line[i] = (line[i] + a) & 255
                elif f == 2:
                    line[i] = (line[i] + b) & 255
                elif f == 3:
                    line[i] = (line[i] + (a + b) // 2) & 255
                elif f == 4:
                    pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                    line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
            rows.append(bytes(line))
            prev = line
        pix = b"".join(rows)
        if depth == 16:
            pix = pix[::2]   # the high byte of each sample
        if ctype == 3:       # palette → RGB (+ alpha from tRNS)
            if depth != 8:
                raise ValueError("Use an 8-bit PNG")
            rgb = bytearray()
            alpha = bytearray() if trns else None
            for i in pix:
                rgb += plte[i * 3:i * 3 + 3]
                if alpha is not None:
                    alpha.append(trns[i] if i < len(trns) else 255)
            color, a = bytes(rgb), (bytes(alpha) if alpha is not None else None)
            ncomp = 3
        elif ctype in (4, 6):
            n = 2 if ctype == 4 else 4
            color = b"".join(pix[i:i + n - 1] for i in range(0, len(pix), n))
            a = pix[n - 1::n]
            ncomp = n - 1
        else:
            color, a, ncomp = pix, None, channels
        self.w, self.h, self.filter = w, h, b"/FlateDecode"
        self.cs = b"/DeviceRGB" if ncomp == 3 else b"/DeviceGray"
        self.data = zlib.compress(color)
        self.alpha = zlib.compress(a) if a is not None and min(a) < 255 else None

    def _jpeg(self, data):
        i = 2
        while i < len(data):
            if data[i] != 0xFF:
                raise ValueError("That JPEG could not be read")
            marker, n = data[i + 1], int.from_bytes(data[i + 2:i + 4], "big")
            if marker in (0xC0, 0xC1, 0xC2):
                self.h, self.w = int.from_bytes(data[i + 5:i + 7], "big"), int.from_bytes(data[i + 7:i + 9], "big")
                comps = data[i + 9]
                self.cs = {1: b"/DeviceGray", 3: b"/DeviceRGB", 4: b"/DeviceCMYK"}[comps]
                self.data, self.alpha, self.filter = data, None, b"/DCTDecode"
                return
            i += 2 + n
        raise ValueError("That JPEG could not be read")


class Canvas:
    W, H = PAGE_W, PAGE_H

    def __init__(self):
        self.pages = []
        self.ops = None
        self.images = []   # Image objects; every page may draw any of them
        self.used = {}     # Noto glyphs drawn, by font file (text beyond Windows-1252)

    def image(self, img, x, y, w, h):
        """Draw `img` into the box, keeping its proportions, centred vertically, left-aligned."""
        if img not in self.images:
            self.images.append(img)
        k = min(w / img.w, h / img.h)
        dw, dh = img.w * k, img.h * k
        n = self.images.index(img) + 1
        self.ops.append(b"q %.2f 0 0 %.2f %.2f %.2f cm /Im%d Do Q" % (dw, dh, x, self.H - y - (h + dh) / 2, n))

    def page(self):
        self.ops = []
        self.pages.append(self.ops)

    def text(self, x, y, s, size=10, bold=False, color=(16, 17, 20)):
        """Text with its baseline `size` points below y (y is the line's top)."""
        s = str(s).translate(_TRANSLATE)
        self.ops.append(_rgb(color) + b" rg BT %.1f %.1f Td " % (x, self.H - y - size * 0.82) + _show(s, size, bold, self.used) + b" ET")

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
        xobjects = []
        for n, img in enumerate(self.images, 1):
            smask = b""
            if img.alpha is not None:
                objects.append(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n"
                               % (img.w, img.h, len(img.alpha)) + img.alpha + b"\nendstream")
                smask = b" /SMask %d 0 R" % len(objects)
            objects.append(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace %s /BitsPerComponent 8 /Filter %s%s /Length %d >>\nstream\n"
                           % (img.w, img.h, img.cs, img.filter, smask, len(img.data)) + img.data + b"\nendstream")
            xobjects.append(b"/Im%d %d 0 R" % (n, len(objects)))
        xres = b" /XObject << " + b" ".join(xobjects) + b" >>" if xobjects else b""
        kids = []
        for n, ops in enumerate(self.pages, 1):
            foot = f"{footer}  \u00b7  page {n} of {len(self.pages)}" if footer else f"page {n} of {len(self.pages)}"
            stream = b"\n".join(ops + [b"0.42 0.45 0.5 rg BT %d %d Td " % (MARGIN - 16, 22) + _show(foot, 7.5, False, self.used) + b" ET"])
            objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
            content_id = len(objects)
            objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R /Resources << /Font << /F1 3 0 R /F2 4 0 R FONTS >>%s >> >>"
                           % (PAGE_W, PAGE_H, content_id, xres))
            kids.append(len(objects))
        fonts = _embed(self.used, objects)
        objects = [o.replace(b"FONTS >>", fonts + b" >>") if o and o.startswith(b"<< /Type /Page ") else o for o in objects]
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
