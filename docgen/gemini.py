"""gemini.py — AI mode via Google Gemini (REST, httpx). Self-contained.

Reads GEMINI_API_KEY / GEMINI_MODEL from the environment at call time. Raises
GeminiError on any failure so callers can fall back to the rule-based engine.
"""
from __future__ import annotations

import json
import os
from datetime import date

import httpx

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
TIMEOUT = httpx.Timeout(45.0)


class GeminiError(RuntimeError):
    pass


def _key() -> str:
    return (os.getenv("GEMINI_API_KEY") or "").strip()


def _model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()


def is_enabled() -> bool:
    return bool(_key())


def _call(prompt: str, response_schema: dict, system: str | None = None) -> dict:
    if not _key():
        raise GeminiError("Gemini API key not configured (set GEMINI_API_KEY).")

    url = f"{API_ROOT}/{_model()}:generateContent"
    payload: dict = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "responseMimeType": "application/json",
            "responseSchema": response_schema,
        },
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}

    try:
        resp = httpx.post(url, params={"key": _key()}, json=payload, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        raise GeminiError(f"network error calling Gemini: {e}") from e

    if resp.status_code != 200:
        raise GeminiError(f"Gemini HTTP {resp.status_code}: {resp.text[:300]}")

    try:
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError, TypeError) as e:
        raise GeminiError(f"unexpected Gemini response: {e}") from e


# ------------------------------------------------------------------ parsing
_PARSE_SCHEMA = {
    "type": "object",
    "properties": {
        "buyer": {"type": "string"},
        "subject": {"type": "string"},
        "ref": {"type": "string"},
        "date": {"type": "string"},
        "gst_percent": {"type": "string"},
        "gstin": {"type": "string"},
        "signatory": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "hsn": {"type": "string"},
                    "qty": {"type": "string"},
                    "unit": {"type": "string"},
                    "rate": {"type": "string"},
                    "amount": {"type": "string"},
                },
            },
        },
        "terms": {"type": "array", "items": {"type": "string"}},
    },
}

_PARSE_SYSTEM = (
    "You extract structured data from informal Indian B2B quotation/enquiry text. "
    "Return ONLY fields you can find; use empty strings/arrays when absent. "
    "For each line item give description, hsn (HSN/SAC code if present), qty, unit "
    "(kg, nos, mtr, etc.), rate (per-unit price as a plain number), and amount "
    "(qty*rate). Numbers must be plain digits without currency symbols or commas. "
    "Capture payment/delivery/validity/warranty/freight/tax as separate concise "
    "term strings. Do not invent values."
)


def ai_parse(text: str) -> dict:
    today = date.today().strftime("%d-%b-%Y")
    prompt = (
        f"Today's date is {today}. Extract the quotation details from the text below.\n"
        f"If no GST rate is stated, leave gst_percent empty (the app defaults it).\n\n"
        f"--- TEXT ---\n{text.strip()}\n--- END ---"
    )
    out = _call(prompt, _PARSE_SCHEMA, system=_PARSE_SYSTEM)

    items = []
    for it in (out.get("items") or []):
        if not isinstance(it, dict):
            continue
        items.append({
            "description": str(it.get("description", "")).strip(),
            "hsn": str(it.get("hsn", "")).strip(),
            "qty": str(it.get("qty", "")).strip(),
            "unit": str(it.get("unit", "")).strip(),
            "rate": str(it.get("rate", "")).strip(),
            "amount": str(it.get("amount", "")).strip(),
        })
    terms = [str(t).strip() for t in (out.get("terms") or []) if str(t).strip()]

    result = {
        "buyer": str(out.get("buyer", "")).strip(),
        "subject": str(out.get("subject", "")).strip(),
        "ref": str(out.get("ref", "")).strip(),
        "date": str(out.get("date", "")).strip(),
        "gst_percent": str(out.get("gst_percent", "")).strip() or "18",
        "gstin": str(out.get("gstin", "")).strip(),
        "signatory": str(out.get("signatory", "")).strip(),
        "items": items,
        "terms": terms,
        "raw": text.strip(),
    }
    if not result["date"]:
        result["date"] = today
    return result


# ------------------------------------------------------------------ drafting
_DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "greeting": {"type": "string"},
        "intro": {"type": "string"},
        "closing": {"type": "string"},
        "subject": {"type": "string"},
        "terms": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["intro", "closing"],
}

_DRAFT_SYSTEM = (
    "You are a sales executive at an Indian company writing the prose for a price "
    "quotation on company letterhead. Write professional, natural, India-appropriate "
    "business English. Do NOT include the price table, totals, the date, or the "
    "signature block — only the wording requested. Keep it concise and free of "
    "placeholders or markdown."
)


def ai_draft(data: dict, company: str, tone: str, item_summary: str) -> dict:
    buyer = (data.get("buyer") or "the customer").strip()
    subject = (data.get("subject") or "").strip()
    terms = [t for t in (data.get("terms") or []) if str(t).strip()]

    prompt = (
        f"Company sending the quotation: {company}\n"
        f"Addressed to (buyer): {buyer}\n"
        f"What is being quoted: {item_summary}\n"
        f"Existing subject (improve if weak, else keep): {subject or '(none)'}\n"
        f"Existing terms to re-phrase cleanly and professionally "
        f"(keep meaning, do not add new commercial commitments): {terms or '(none)'}\n\n"
        f"Write in a {tone} tone. Produce:\n"
        f"- greeting: a salutation line (e.g. 'Dear Sir,'), or empty for a terse style\n"
        f"- intro: ONE short paragraph introducing the offer below\n"
        f"- closing: 1-2 sentences inviting the order plus a sign-off phrase "
        f"(e.g. 'Thanking you,' / 'Warm regards,'), but NOT the company name or signatory\n"
        f"- subject: a crisp one-line subject for the quotation\n"
        f"- terms: the re-phrased terms as a list of short strings (omit if none)"
    )
    out = _call(prompt, _DRAFT_SCHEMA, system=_DRAFT_SYSTEM)
    return {
        "greeting": str(out.get("greeting", "")).strip(),
        "intro": str(out.get("intro", "")).strip(),
        "closing": str(out.get("closing", "")).strip(),
        "subject": str(out.get("subject", "")).strip(),
        "terms": [str(t).strip() for t in (out.get("terms") or []) if str(t).strip()],
    }
