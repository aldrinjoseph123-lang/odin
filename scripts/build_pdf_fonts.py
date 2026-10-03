"""Build the fonts the PDF writer embeds for text Helvetica cannot print
(services/pdf.py): Noto Sans (Latin, Greek, Cyrillic) and Noto Sans Arabic,
regular and bold, cut to the scripts Odin needs and without layout tables
(the writer shapes Arabic itself from Unicode's presentation forms), plus a
metrics file with each character's glyph id and advance.

    pip install fonttools          # a build-time tool only
    python3 scripts/build_pdf_fonts.py <folder with the four Noto .ttf files>

Sources: https://notofonts.github.io (NotoSans-*.ttf from latin-greek-cyrillic,
NotoSansArabic-*.ttf from arabic), SIL Open Font License 1.1 (fonts/OFL.txt).
Chinese, Japanese and Korean are left out on purpose: those fonts run to
megabytes, and such names still print as "?".
"""
import json
import os
import sys

from fontTools import subset
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "services", "fonts")
LATIN = [(0x20, 0x24F), (0x300, 0x36F), (0x370, 0x3FF), (0x400, 0x52F), (0x1E00, 0x1EFF), (0x2000, 0x206F), (0x20A0, 0x20CF), (0x2100, 0x215F)]
ARABIC = [(0x20, 0x40), (0x600, 0x6FF), (0x750, 0x77F), (0x8A0, 0x8FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)]
FONTS = [("NotoSans-Regular.ttf", LATIN), ("NotoSans-Bold.ttf", LATIN), ("NotoSansArabic-Regular.ttf", ARABIC), ("NotoSansArabic-Bold.ttf", ARABIC)]


def build(src):
    os.makedirs(OUT, exist_ok=True)
    metrics = {}
    for name, ranges in FONTS:
        font = TTFont(os.path.join(src, name))
        opts = subset.Options()
        opts.layout_features = []                 # no GSUB/GPOS: shaping happens in services/pdf.py
        opts.drop_tables += ["GSUB", "GPOS", "GDEF", "DSIG"]
        opts.name_IDs, opts.notdef_outline, opts.glyph_names = ["*"], True, False
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=[c for a, b in ranges for c in range(a, b + 1)])
        sub.subset(font)
        font.save(os.path.join(OUT, name))
        font = TTFont(os.path.join(OUT, name))
        order, hmtx, head, os2 = font.getGlyphOrder(), font["hmtx"], font["head"], font["OS/2"]
        gid = {g: i for i, g in enumerate(order)}
        metrics[name] = {
            "chars": {str(cp): [gid[g], hmtx[g][0]] for cp, g in font.getBestCmap().items()},
            "bbox": [head.xMin, head.yMin, head.xMax, head.yMax], "ascent": os2.sTypoAscender,
            "descent": os2.sTypoDescender, "cap": getattr(os2, "sCapHeight", 714) or 714,
            "name": font["name"].getDebugName(6),
        }
    with open(os.path.join(OUT, "metrics.json"), "w") as fh:
        json.dump(metrics, fh, separators=(",", ":"))
    for name, _ in FONTS:
        print(f"{name}: {os.path.getsize(os.path.join(OUT, name)) // 1024} KB")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else ".")
