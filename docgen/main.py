"""main.py — stateless document-generation microservice (FastAPI).

The Next.js backend calls this service to do the heavy lifting it can't do in
Node: parse messy text (rule-based or Gemini), pick distinct style variants,
draft wording (Gemini), and render each quotation onto the user's .docx
letterhead, then convert to PDF.

It is intentionally stateless and storage-agnostic: letterhead bytes come in,
rendered docx/pdf bytes go out (base64). The Next backend owns Supabase
auth/db/storage. Protected by a shared secret (DOCGEN_SECRET).

Run:  python -m uvicorn main:app --port 8500    (from the docgen/ directory)
"""
from __future__ import annotations

import base64
import os
import random
import re
import tempfile
import traceback
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

import gemini
import parser
import renderer
import templates_engine

app = FastAPI(title="Quotation docgen service")


# ------------------------------------------------------------------ auth
def _check_secret(secret: str | None) -> None:
    expected = (os.getenv("DOCGEN_SECRET") or "").strip()
    if expected and secret != expected:
        raise HTTPException(401, "Bad or missing X-Docgen-Secret.")


# ------------------------------------------------------------------ helpers
def company_from_filename(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"(?i)[_\s\-]*letter[_\s\-]*head", " ", stem)
    stem = stem.replace("_", " ").replace("-", " ")
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem.upper() or "COMPANY"


# ------------------------------------------------------------------ models
class Item(BaseModel):
    description: str = ""
    hsn: str = ""
    qty: str = ""
    unit: str = ""
    rate: str = ""
    amount: str = ""


class QData(BaseModel):
    buyer: str = ""
    subject: str = ""
    ref: str = ""
    date: str = ""
    gst_percent: str = "18"
    signatory: str = ""
    items: list[Item] = []
    terms: list[str] = []


class LetterheadIn(BaseModel):
    company: str = ""
    filename: str = ""
    content_b64: str          # the .docx letterhead bytes, base64


class ParseRequest(BaseModel):
    text: str
    ai_mode: bool = False


class ConvertRequest(BaseModel):
    filename: str = ""
    content_b64: str          # the PDF bytes, base64


class GenerateRequest(BaseModel):
    data: QData
    letterheads: list[LetterheadIn]
    count: int = 3
    ai_mode: bool = False
    make_pdf: bool = True
    seed: int | None = None


# ------------------------------------------------------------------ routes
@app.get("/health")
def health():
    return {
        "ok": True,
        "ai_available": gemini.is_enabled(),
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash") if gemini.is_enabled() else None,
        "pdf_engine": renderer.pdf_engine(),
    }


@app.post("/parse")
def parse_text(req: ParseRequest, x_docgen_secret: str | None = Header(None)):
    _check_secret(x_docgen_secret)
    if not req.text.strip():
        raise HTTPException(400, "No text to parse.")
    if req.ai_mode and gemini.is_enabled():
        try:
            result = gemini.ai_parse(req.text)
            result["_engine"] = "ai"
            return result
        except gemini.GeminiError:
            traceback.print_exc()
            result = parser.parse(req.text)
            result["_engine"] = "rule-based (AI failed)"
            return result
    result = parser.parse(req.text)
    result["_engine"] = "rule-based"
    return result


@app.post("/convert")
def convert_letterhead(req: ConvertRequest, x_docgen_secret: str | None = Header(None)):
    """Turn a PDF letterhead into a .docx we can render onto: the page becomes a
    full-page background image in the header (behind text, every page), so the
    quotation renders on top of the letterhead instead of spilling to a blank
    page. Returns the .docx bytes as base64."""
    _check_secret(x_docgen_secret)
    from pdf_letterhead import pdf_to_letterhead_docx

    with tempfile.TemporaryDirectory(prefix="convert_") as tmp:
        pdf_path = Path(tmp) / "in.pdf"
        docx_path = Path(tmp) / "out.docx"
        try:
            pdf_path.write_bytes(base64.b64decode(req.content_b64))
        except Exception:
            raise HTTPException(400, "Invalid base64 PDF content.")
        try:
            pdf_to_letterhead_docx(pdf_path, docx_path)
        except Exception as e:
            raise HTTPException(
                400,
                f"Could not convert PDF letterhead ({type(e).__name__}: {e}). "
                "Try a .docx instead.",
            )
        return {"docx_b64": base64.b64encode(docx_path.read_bytes()).decode("ascii")}


@app.post("/generate")
def generate(req: GenerateRequest, x_docgen_secret: str | None = Header(None)):
    _check_secret(x_docgen_secret)
    if not req.letterheads:
        raise HTTPException(400, "No letterheads supplied.")

    n = max(1, min(int(req.count or 1), 20))
    rng = random.Random(req.seed)

    # choose which letterhead backs each of the n variations
    pool = list(range(len(req.letterheads)))
    if len(pool) >= n:
        chosen = rng.sample(pool, n)
    else:
        chosen = pool[:] + [rng.choice(pool) for _ in range(n - len(pool))]
        rng.shuffle(chosen)

    data = {
        "buyer": req.data.buyer, "subject": req.data.subject, "ref": req.data.ref,
        "date": req.data.date, "gst_percent": req.data.gst_percent,
        "signatory": req.data.signatory,
        "items": [it.model_dump() for it in req.data.items],
        "terms": req.data.terms,
    }
    variants = templates_engine.make_variants(n, seed=req.seed)
    use_ai = bool(req.ai_mode and gemini.is_enabled())
    item_sum = templates_engine.item_summary(data["items"])

    results, errors = [], []
    with tempfile.TemporaryDirectory(prefix="docgen_") as tmp:
        tmpdir = Path(tmp)
        for i, (lh_idx, variant) in enumerate(zip(chosen, variants), start=1):
            lh = req.letterheads[lh_idx]
            company = (lh.company or "").strip() or company_from_filename(lh.filename or "letterhead")

            ai_copy = None
            if use_ai:
                try:
                    ai_copy = gemini.ai_draft(data, company, variant["tone"], item_sum)
                except gemini.GeminiError:
                    traceback.print_exc()

            try:
                lh_path = tmpdir / f"lh_{i}.docx"
                lh_path.write_bytes(base64.b64decode(lh.content_b64))
                spec = templates_engine.build_spec(data, variant, company, copy=ai_copy)
                out_docx = tmpdir / f"out_{i}.docx"
                docx_path, pdf_path = renderer.render(lh_path, spec, out_docx, make_pdf=req.make_pdf)
                results.append({
                    "n": i,
                    "company": company,
                    "letterhead": lh.filename or company,
                    "summary": templates_engine.describe(variant) + (" · AI-written" if ai_copy else ""),
                    "docx_b64": base64.b64encode(docx_path.read_bytes()).decode("ascii"),
                    "pdf_b64": base64.b64encode(pdf_path.read_bytes()).decode("ascii") if pdf_path else None,
                })
            except Exception as e:
                errors.append({"n": i, "company": company,
                               "letterhead": lh.filename or company,
                               "error": f"{type(e).__name__}: {e}"})
                traceback.print_exc()

    return {"results": results, "errors": errors, "ai_used": use_ai}
