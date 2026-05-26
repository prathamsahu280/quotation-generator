"""pdf_letterhead.py — turn a PDF letterhead into a .docx we can render onto.

A PDF letterhead (often a scanned/designed full-page image) can't be appended to
like a normal Word letterhead: `pdf2docx` dumps the whole page into the document
*body*, so any quotation we add spills onto a blank second page.

Instead we rasterise the first PDF page and place it as a **full-page background
image in the document header** (behind text, repeating on every page), leaving
the body empty. The quotation then renders on top of the letterhead. We also
auto-detect the header/footer ink bands so the body margins keep text inside the
blank middle area.

build_spec/renderer are unchanged: they just append body blocks, which now flow
over the background.
"""
from __future__ import annotations

import tempfile
from copy import deepcopy
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Emu

DPI = 150
PT_TO_EMU = 12700          # 1 pt = 1/72 in; 1 in = 914400 EMU
IN_TO_EMU = 914400


def _detect_margins(gray: np.ndarray) -> tuple[float, float, float, float]:
    """Return (top, bottom, left, right) margins in inches that clear the
    letterhead's printed header/footer/side bands, from a grayscale page."""
    H, W = gray.shape
    ink = gray < 200                       # dark-ish pixels = printed content
    row_ink = ink.sum(axis=1)
    row_thr = max(3, int(W * 0.005))
    rows = np.where(row_ink > row_thr)[0]

    def clamp(v, lo, hi):
        return max(lo, min(hi, v))

    # header: last content row in the top 45% of the page
    top_rows = rows[rows < 0.45 * H] if rows.size else np.array([])
    top_in = (top_rows.max() / DPI + 0.18) if top_rows.size else 0.8
    top = clamp(top_in, 0.6, 3.0)

    # footer: first content row in the bottom 40%
    bot_rows = rows[rows > 0.60 * H] if rows.size else np.array([])
    bot_in = ((H - bot_rows.min()) / DPI + 0.18) if bot_rows.size else 0.8
    bottom = clamp(bot_in, 0.5, 2.5)

    # sides: content columns within the middle band only
    mid = ink[int(0.25 * H): int(0.75 * H), :]
    col_thr = max(3, int(mid.shape[0] * 0.01))
    cols = np.where(mid.sum(axis=0) > col_thr)[0]
    left = clamp((cols.min() / DPI + 0.1) if cols.size else 0.9, 0.5, 1.3)
    right = clamp(((W - cols.max()) / DPI + 0.1) if cols.size else 0.9, 0.5, 1.3)
    return top, bottom, left, right


def _make_background_anchor(inline_drawing) -> None:
    """Convert the <wp:inline> image (just added to the header) into a page-
    anchored, behind-text <wp:anchor> so it becomes a full-page background."""
    inline = inline_drawing.find(qn("wp:inline"))
    extent = inline.find(qn("wp:extent"))
    graphic = inline.find(qn("a:graphic"))
    cx, cy = extent.get("cx"), extent.get("cy")

    anchor = parse_xml(
        f'<wp:anchor {nsdecls("wp", "a", "r", "pic")} behindDoc="1" distT="0" '
        'distB="0" distL="0" distR="0" simplePos="0" locked="0" layoutInCell="1" '
        'allowOverlap="1" relativeHeight="0">'
        '<wp:simplePos x="0" y="0"/>'
        '<wp:positionH relativeFrom="page"><wp:posOffset>0</wp:posOffset></wp:positionH>'
        '<wp:positionV relativeFrom="page"><wp:posOffset>0</wp:posOffset></wp:positionV>'
        f'<wp:extent cx="{cx}" cy="{cy}"/>'
        '<wp:wrapNone/>'
        '<wp:docPr id="100" name="Letterhead background"/>'
        "</wp:anchor>"
    )
    anchor.append(deepcopy(graphic))
    inline.getparent().replace(inline, anchor)


def pdf_to_letterhead_docx(pdf_path: Path, out_docx: Path) -> Path:
    """Render PDF page 1 as a full-page background in a new .docx's header."""
    pdf_path, out_docx = Path(pdf_path), Path(out_docx)
    doc_pdf = fitz.open(str(pdf_path))
    try:
        page = doc_pdf[0]
        w_emu = int(round(page.rect.width * PT_TO_EMU))
        h_emu = int(round(page.rect.height * PT_TO_EMU))
        pix = page.get_pixmap(dpi=DPI)
    finally:
        doc_pdf.close()

    with tempfile.TemporaryDirectory(prefix="lh_") as tmp:
        png = Path(tmp) / "page.png"
        pix.save(str(png))

        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        gray = arr[:, :, :3].mean(axis=2) if pix.n >= 3 else arr[:, :, 0].astype(float)
        top, bottom, left, right = _detect_margins(gray)

        doc = Document()
        sec = doc.sections[0]
        sec.page_width = Emu(w_emu)
        sec.page_height = Emu(h_emu)
        sec.top_margin = Emu(int(top * IN_TO_EMU))
        sec.bottom_margin = Emu(int(bottom * IN_TO_EMU))
        sec.left_margin = Emu(int(left * IN_TO_EMU))
        sec.right_margin = Emu(int(right * IN_TO_EMU))
        sec.header_distance = Emu(0)
        sec.footer_distance = Emu(0)

        # full-page image in the header, then make it a behind-text page anchor
        hp = sec.header.paragraphs[0]
        run = hp.add_run()
        run.add_picture(str(png), width=Emu(w_emu), height=Emu(h_emu))
        drawing = run._element.find(qn("w:drawing"))
        _make_background_anchor(drawing)

        doc.save(str(out_docx))
    return out_docx
