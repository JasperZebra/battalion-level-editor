import os

import numpy as np
from PyQt6 import QtCore, QtGui

from lib.bw.bwfont import read_btf, read_wdf

# BW2's per-level/per-menu "wdf" font family (SP_*.btf, MP*.btf, fe_units_*.btf,
# frontend2.btf, credits.btf, fe_concept.btf, 0.*_Prologue_*.btf) packs glyphs
# left-to-right/top-to-bottom in strict ascending character-code order with no
# gaps, starting at '!' (0x21) - confirmed by decoding fe_units_ai.btf's atlas
# and reading the visible glyph sequence directly off the image (see
# decomp/font_format_analysis.md). This does NOT hold for the older .fnc
# "master" fonts shared with BW1 (Chisel_CN/_L/_O, Debugging, Techno_HB,
# ModelView/*) - those pack in some other, uncracked order, so there is
# currently no known-correct way to build a real bitmap font for BW1's CO
# dialogue text; BW1 keeps the QFont approximation.
START_CHAR = 0x21


def _detect_glyph_boxes(pil_image, ink_threshold=16, col_gap=2):
    """Row-major (x0, y0, x1, y1) ink bounding boxes, one per glyph cell.
    Pure numpy: row bands via zero-tolerance run detection, then column
    bands within each row band - no connected-component library needed,
    and tolerant of glyphs with disconnected ink (dotted i/j, colon,
    the two ticks of a "). Column bands separated by a gap of col_gap
    pixels or less are merged into one glyph - small enough to bridge a
    character's own internal gaps, well under the ~10+px gap the atlas
    leaves between distinct characters (verified against SP_1.1.btf,
    where the "" quote mark's two ticks are 1px apart but the next real
    character starts 16px later)."""
    arr = np.array(pil_image.convert("L"))
    mask = arr > ink_threshold

    def runs(boolarr, gap=0):
        out = []
        start = None
        pending_gap = 0
        for i, v in enumerate(boolarr):
            if v:
                if start is None:
                    start = i
                pending_gap = 0
            elif start is not None:
                pending_gap += 1
                if pending_gap > gap:
                    out.append((start, i - pending_gap + 1))
                    start = None
        if start is not None:
            out.append((start, len(boolarr)))
        return out

    boxes = []
    for y0, y1 in runs(mask.any(axis=1)):
        sub = mask[y0:y1, :]
        for x0, x1 in runs(sub.any(axis=0), gap=col_gap):
            ys = np.where(sub[:, x0:x1].any(axis=1))[0]
            boxes.append((x0, y0 + int(ys.min()), x1, y0 + int(ys.max()) + 1))
    return boxes


def _pil_to_qpixmap(image):
    image = image.convert("RGBA")
    data = image.tobytes("raw", "RGBA")
    qimg = QtGui.QImage(data, image.width, image.height,
                         QtGui.QImage.Format.Format_RGBA8888)
    return QtGui.QPixmap.fromImage(qimg.copy())


class BWBitmapFont:
    """Renders text using glyphs cropped directly from a real BW2 game font
    atlas, instead of a stand-in system font."""
    SPACE_WIDTH_FALLBACK = 6

    def __init__(self, atlas_pixmap, glyph_boxes, widths, gap=1):
        self.atlas = atlas_pixmap
        self.glyphs = glyph_boxes  # char -> QRect (source crop, atlas space)
        self.widths = widths       # char -> advance width (pixels, atlas space)
        self.gap = gap
        self.space_width = widths.get(" ", self.SPACE_WIDTH_FALLBACK)
        self.glyph_height = max((r.height() for r in glyph_boxes.values()), default=10)

    @classmethod
    def load(cls, btf_path, wdf_path=None, start_char=START_CHAR):
        tex = read_btf(btf_path)
        boxes = _detect_glyph_boxes(tex.image)
        pixmap = _pil_to_qpixmap(tex.image)
        wdf_widths = None
        if wdf_path and os.path.exists(wdf_path):
            wdf_widths = read_wdf(wdf_path)

        glyphs = {}
        widths = {}
        for i, (x0, y0, x1, y1) in enumerate(boxes):
            code = start_char + i
            ch = chr(code)
            glyphs[ch] = QtCore.QRect(x0, y0, x1 - x0, y1 - y0)
            if wdf_widths is not None and code in wdf_widths:
                widths[ch] = wdf_widths[code]
            else:
                widths[ch] = (x1 - x0) + 2
        if wdf_widths is not None and 0x20 in wdf_widths:
            widths[" "] = wdf_widths[0x20]
        return cls(pixmap, glyphs, widths)

    def char_width(self, ch):
        if ch == " " or ch not in self.glyphs:
            return self.space_width
        return self.widths.get(ch, self.glyphs[ch].width()) + self.gap

    def text_width(self, text):
        return sum(self.char_width(c) for c in text)

    def wrap_lines(self, text, max_width):
        """Greedy word-wrap using this font's own measured widths."""
        lines = []
        for paragraph in text.split("\n"):
            words = paragraph.split(" ")
            cur = ""
            for word in words:
                cand = word if not cur else cur + " " + word
                if cur and self.text_width(cand) > max_width:
                    lines.append(cur)
                    cur = word
                else:
                    cur = cand
            lines.append(cur)
        return lines

    def draw_text(self, painter, rect, text, color, scale=1.0, line_spacing=1.25):
        """Word-wrapped, vertically-centered, left-aligned text blitted from
        the real font atlas - the bitmap-font equivalent of
        painter.drawText(rect, AlignLeft|AlignVCenter|TextWordWrap, text)."""
        max_w = max(rect.width() / scale, 1)
        lines = self.wrap_lines(text, max_w)
        line_h = self.glyph_height * line_spacing
        total_h = line_h * len(lines) * scale
        y = rect.top() + (rect.height() - total_h) / 2.0
        for line in lines:
            x = rect.left()
            for ch in line:
                box = self.glyphs.get(ch)
                if box is None:
                    x += self.char_width(ch) * scale
                    continue
                dw, dh = max(int(box.width() * scale), 1), max(int(box.height() * scale), 1)
                glyph = self.atlas.copy(box).scaled(
                    dw, dh, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation)
                if color != QtGui.QColor(255, 255, 255):
                    gp = QtGui.QPainter(glyph)
                    gp.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
                    gp.fillRect(glyph.rect(), color)
                    gp.end()
                painter.drawPixmap(int(x), int(y), glyph)
                x += self.char_width(ch) * scale
            y += line_h * scale
