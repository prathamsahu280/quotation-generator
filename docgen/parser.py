"""parser.py — best-effort extraction of quotation fields from free-form text.

No LLM. This is a heuristic parser tuned for how Indian quotations are usually
typed/pasted. It recognises buyer blocks, a wide range of line-item formats
(``@``, ``x``, ``Rate:``, ``Rs 62.50/kg``, rate-only, and Excel/tab columns),
HSN codes, GSTIN, GST %, and payment/delivery/validity/warranty terms, and
applies smart defaults (today's date, GST 18, subject from the first item).

Everything it returns is shown in an editable form, so wrong guesses are cheap.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path


# ---- text extraction from uploaded files -------------------------------------

def extract_text(file_path: Path) -> str:
    """Pull plain text out of a .pdf or .txt/.md file."""
    file_path = Path(file_path)
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(file_path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    return file_path.read_text(encoding="utf-8", errors="replace")


# ---- number / money helpers --------------------------------------------------

_NUM = r"\d[\d,]*(?:\.\d+)?"
UNIT_WORDS = (
    r"(?:kgs?|kg|grams?|gms?|tons?|tonnes?|mt|nos?\.?|pcs?\.?|pieces?|units?|sets?|"
    r"mtrs?|meters?|metres?|sqft|sq\.?ft|sqm|cft|ft|feet|ltrs?|litres?|liters?|"
    r"boxes?|bags?|rolls?|sheets?|pairs?|dozen|drums?|cartons?|nm|qty)"
)
_CUR = r"(?:rs\.?|inr|₹|/-)"


def _to_float(s):
    if s is None:
        return None
    s = re.sub(r"[^\d.]", "", str(s).replace(",", ""))
    try:
        return float(s)
    except ValueError:
        return None


def _trim_num(x):
    if x is None or x == "":
        return ""
    try:
        f = float(x)
        return str(int(f)) if f.is_integer() else f"{f:g}"
    except (TypeError, ValueError):
        return str(x)


# ---- line-item detection -----------------------------------------------------

# "<desc> <qty><unit>? @|x|rate|: <rate> [= <amount>]"
ITEM_RE = re.compile(
    r"^(?P<desc>.+?)[\s,:\-–—]+"
    r"(?:qty\.?[:\s]*)?"
    r"(?P<qty>" + _NUM + r")\s*(?P<unit>" + UNIT_WORDS + r")?\s*"
    r"(?:@|x|×|at|rate[:\s]*|price[:\s]*|=|:|for|of)\s*"
    r"" + _CUR + r"?\s*"
    r"(?P<rate>" + _NUM + r")\s*(?:/\s*\w+)?"
    r"(?:[\s,]*=?\s*" + _CUR + r"?\s*(?P<amount>" + _NUM + r"))?\s*$",
    re.IGNORECASE,
)

# "<qty> <unit> <desc> @|x <rate> [= <amount>]"  (quantity leads the line)
LEAD_QTY_RE = re.compile(
    r"^(?P<qty>" + _NUM + r")\s*(?P<unit>" + UNIT_WORDS + r")\s+(?P<desc>.+?)\s*"
    r"(?:@|x|×|at|rate[:\s]*|=|:)\s*" + _CUR + r"?\s*(?P<rate>" + _NUM + r")\s*(?:/\s*\w+)?"
    r"(?:[\s,]*=?\s*" + _CUR + r"?\s*(?P<amount>" + _NUM + r"))?\s*$",
    re.IGNORECASE,
)

# rate only, no quantity: "<desc> @ Rs 62.50", "<desc> - 1500/-", "<desc> - Rs 4500"
RATE_ONLY_RE = re.compile(
    r"^(?P<desc>.+?)[\s,:\-–—]+"
    r"(?:(?:@|rate[:\s]*|price[:\s]*|cost[:\s]*|=|:)\s*" + _CUR + r"?|" + _CUR + r")\s*"
    r"(?P<rate>" + _NUM + r")\s*(?:/\s*\w+|/-)?\s*$",
    re.IGNORECASE,
)

# a token that is purely a money/qty value (for Excel/tab-column parsing)
NUMERIC_TOKEN_RE = re.compile(
    r"^" + _CUR + r"?\s*(?P<num>" + _NUM + r")\s*(?P<unit>" + UNIT_WORDS + r")?(?:/\s*\w+|/-)?$",
    re.IGNORECASE,
)
HSN_RE = re.compile(r"\bHSN(?:/SAC)?\s*(?:code)?\s*[:#]?\s*(\d{4,8})\b", re.IGNORECASE)
_SKIP_ITEM = re.compile(r"\b(gst|igst|cgst|sgst|total|sub-?total|grand|phone|mob|gstin|"
                        r"email|terms?|validity|payment|delivery|warranty|note)\b", re.IGNORECASE)


def _clean_desc(s: str) -> str:
    s = re.sub(r"\bHSN(?:/SAC)?\s*(?:code)?\s*[:#]?\s*\d{4,8}\b", "", s, flags=re.IGNORECASE)
    return s.strip(" .,-–—:|\t")


def _split_item_candidates(text: str) -> list[str]:
    chunks = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # a line may pack several items separated by ';'
        for part in re.split(r";\s+", line):
            part = re.sub(r"^(\d+[\.\)]|[-•*])\s*", "", part.strip())  # strip "1." / "-" / "•"
            part = re.sub(r"^(?:items?|particulars?|products?|goods|description|qty)\s*[:\-]\s*",
                          "", part, flags=re.IGNORECASE)
            if part:
                chunks.append(part)
    return chunks


def _columnar_item(chunk: str):
    """Parse a tab- or wide-space-separated row (e.g. pasted from Excel)."""
    if "\t" not in chunk and not re.search(r"\S {2,}\S", chunk):
        return None
    tokens = [t.strip() for t in re.split(r"\t+| {2,}", chunk) if t.strip()]
    if len(tokens) < 2:
        return None
    desc_parts, nums, unit = [], [], ""
    for t in tokens:
        m = NUMERIC_TOKEN_RE.match(t)
        if m:
            nums.append(_to_float(m.group("num")))
            unit = unit or (m.group("unit") or "")
        else:
            desc_parts.append(t)
    if not desc_parts or not nums:
        return None
    qty = rate = amount = None
    if len(nums) >= 3:
        qty, rate, amount = nums[0], nums[1], nums[2]
    elif len(nums) == 2:
        qty, rate = nums[0], nums[1]
    else:
        rate, qty = nums[0], 1.0
    return desc_parts, qty, unit, rate, amount


def parse_item_line(chunk: str):
    if _SKIP_ITEM.search(chunk) and not re.search(r"@|×|\bx\b|rate|/kg|/-", chunk, re.IGNORECASE):
        return None
    hsn_m = HSN_RE.search(chunk)
    hsn = hsn_m.group(1) if hsn_m else ""

    col = _columnar_item(chunk)
    if col:
        desc_parts, qty, unit, rate, amount = col
        desc = _clean_desc(" ".join(desc_parts))
    elif LEAD_QTY_RE.search(chunk):
        m = LEAD_QTY_RE.search(chunk)
        qty, unit, rate = _to_float(m.group("qty")), (m.group("unit") or ""), _to_float(m.group("rate"))
        amount = _to_float(m.group("amount")) if m.group("amount") else None
        desc = _clean_desc(m.group("desc"))
    elif ITEM_RE.search(chunk):
        m = ITEM_RE.search(chunk)
        qty, unit, rate = _to_float(m.group("qty")), (m.group("unit") or ""), _to_float(m.group("rate"))
        amount = _to_float(m.group("amount")) if m.group("amount") else None
        desc = _clean_desc(m.group("desc"))
    else:
        m = RATE_ONLY_RE.search(chunk)
        if not m:
            return None
        qty, unit, rate, amount = 1.0, "", _to_float(m.group("rate")), None
        desc = _clean_desc(m.group("desc"))

    if not desc or rate is None:
        return None
    if amount is None and qty is not None:
        amount = round(qty * rate, 2)
    return {
        "description": desc, "hsn": hsn, "qty": _trim_num(qty), "unit": unit.strip(),
        "rate": _trim_num(rate), "amount": _trim_num(amount),
    }


def parse_items(text: str) -> list[dict]:
    items = []
    for chunk in _split_item_candidates(text):
        it = parse_item_line(chunk)
        if it:
            items.append(it)
    return items


# ---- field detection ---------------------------------------------------------

def _first_match(patterns, text, flags=re.IGNORECASE):
    for p in patterns:
        m = re.search(p, text, flags)
        if m:
            return m.group(1).strip(" .,:-\n")
    return ""


def _normalise_terms(text: str) -> list[str]:
    terms: list[str] = []
    done: set[str] = set()           # categories already captured (avoids dupes)

    def add(t, cat=None):
        t = t.strip(" .;-•*\t")
        if t and t.lower() not in {x.lower() for x in terms}:
            terms.append(t)
        if cat:
            done.add(cat)

    # structured normalisations first (clean, consistent phrasing)
    m = re.search(r"(\d{1,3})\s*%\s*(?:advance|adv)[^.\n]*?(?:balance|bal)[^.\n]*", text, re.IGNORECASE)
    if m:
        add("Payment: " + m.group(0).strip(), "payment")
    elif re.search(r"\b(advance|against\s+delivery|on\s+delivery|credit)\b", text, re.IGNORECASE):
        pm = _first_match([r"(payment[^.\n]*)"], text)
        if pm:
            add(pm if pm.lower().startswith("payment") else "Payment: " + pm, "payment")

    m = re.search(r"deliver\w*[:\s]*([^.\n]*?\b\d+\s*(?:-\s*\d+)?\s*(?:days?|weeks?)\b[^.\n]*)", text, re.IGNORECASE)
    if m:
        add("Delivery: " + m.group(1).strip(), "delivery")

    m = re.search(r"valid\w*[^.\n]*?(\d+\s*(?:days?|weeks?|months?))", text, re.IGNORECASE)
    if m:
        add(f"Quotation valid for {m.group(1)} from date of issue", "valid")

    m = re.search(r"warrant\w*[^.\n]*?(\d+\s*(?:months?|years?|yrs?))", text, re.IGNORECASE)
    if m:
        add(f"Warranty: {m.group(1)}", "warrant")

    if re.search(r"gst[^.\n]{0,8}extra|extra[^.\n]{0,6}gst|exclusive\s+of\s+gst|plus\s+gst|\+\s*gst",
                 text, re.IGNORECASE):
        add("Prices are exclusive of GST", "gst")
    elif re.search(r"inclusive\s+of\s+gst|incl\.?\s+gst", text, re.IGNORECASE):
        add("Prices are inclusive of GST", "gst")

    if re.search(r"freight\s+extra|transport\s+extra|ex-?works|fob|f\.o\.r", text, re.IGNORECASE):
        add(_first_match([r"(freight[^.\n]*|transport[^.\n]*|ex-?works[^.\n]*)"], text)
            or "Freight extra at actuals", "freight")

    # then any leftover sentence that smells like a condition (skip categories
    # already normalised above, so we don't list the same term twice)
    cat_words = {"payment": ("payment", "advance", "balance"), "delivery": ("delivery", "deliver"),
                 "valid": ("valid", "validity"), "warrant": ("warrant", "guarantee"),
                 "gst": ("gst", "tax"), "freight": ("freight", "transport", "ex-works")}
    term_keys = ("payment", "delivery", "validity", "valid", "warranty", "guarantee",
                 "freight", "packing", "transport", "tax", "advance", "lead time",
                 "installation", "jurisdiction", "subject to", "terms", "condition")
    for s in re.split(r"(?<=[.;])\s+(?=[A-Z0-9])|\n+", text):
        s = s.strip(" .-•*\t")
        if not s or len(s) > 200:
            continue
        low = s.lower()
        if re.match(r"(buyer|client|customer|to|ref|reference|date|item)s?\b\s*[:\-]", low) \
                or re.match(r"(subject|sub|re)\s*[:\-]", low):
            continue
        if any(any(w in low for w in cat_words[c]) for c in done):
            continue   # this category is already covered by a clean normalised term
        if any(k in low for k in term_keys) and not parse_item_line(s):
            add(s)
    return terms[:12]


_BUYER_CUE = re.compile(r"^\s*(?:buyer|client|customer|bill\s*to|ship\s*to|to|kind\s*attn\.?|attn\.?)"
                        r"\s*[:\-]\s*(.*)$", re.IGNORECASE)
_STOP_LINE = re.compile(r"^\s*(?:subject|sub|re|ref|reference|date|gst|items?|terms?|payment|"
                        r"delivery|validity|warranty|note|quote|quotation)\b", re.IGNORECASE)


def _extract_buyer(text: str) -> str:
    lines = text.split("\n")
    for i, line in enumerate(lines):
        m = _BUYER_CUE.match(line)
        if not m:
            continue
        collected = [m.group(1).strip()] if m.group(1).strip() else []
        for nxt in lines[i + 1:]:
            s = nxt.strip()
            if not s or "\t" in nxt or _STOP_LINE.match(s) or re.match(r"^\d+[\.\)]", s):
                break
            if parse_item_line(s):
                break
            collected.append(s)
            if len(collected) >= 4:
                break
        buyer = "\n".join(c for c in collected if c)
        if buyer:
            return buyer
    m = re.search(r"\b(M/s\.?\s+[^\n]+)", text)
    return m.group(1).strip() if m else ""


def parse(text: str) -> dict:
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    buyer = _extract_buyer(text)
    items = parse_items(text)

    subject = _first_match([
        r"(?:subject|sub|re|regarding)\s*[:\-]\s*(.+)",
        r"(?:quotation|quote|offer)\s+for\s+(.+)",
    ], text)
    if not subject and items:
        first = items[0]["description"]
        more = f" & {len(items) - 1} more item{'s' if len(items) > 2 else ''}" if len(items) > 1 else ""
        subject = f"Quotation for {first}{more}"

    ref = _first_match([
        r"(?:ref|reference|enquiry|enq|quotation\s*no|quote\s*no|qt\s*no|po\s*no)\.?\s*[:#\-]\s*([A-Za-z0-9/\-]+)",
    ], text)

    date_str = _first_match([
        r"(?:date|dated|dt)\s*[:\-]?\s*(\d{1,2}[\-/.][A-Za-z0-9]{2,9}[\-/.]\d{2,4})",
        r"\b(\d{1,2}[\-/.]\d{1,2}[\-/.]\d{2,4})\b",
    ], text)
    if not date_str:
        d = date.today()
        date_str = f"{d.day:02d}-{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.month-1]}-{d.year}"

    gst_m = (re.search(r"\b(?:i|c|s)?gst\b[^\d%]*(" + _NUM + r")\s*%", text, re.IGNORECASE)
             or re.search(r"(" + _NUM + r")\s*%\s*(?:i|c|s)?gst", text, re.IGNORECASE)
             or re.search(r"\btax\b[^\d%]*(" + _NUM + r")\s*%", text, re.IGNORECASE))
    gst_percent = _trim_num(_to_float(gst_m.group(1))) if gst_m else "18"

    gstin = _first_match([r"\bGSTIN\s*[:#]?\s*([0-9A-Z]{15})"], text)

    signatory = _first_match([
        r"(?:regards|thanking you|yours faithfully|yours truly)\s*[,\n]+\s*(.+)",
        r"(?:for|from)\s+([A-Z][A-Za-z&.,\- ]+(?:LLP|LTD|LIMITED|PVT|TRADERS|ENTERPRISES|INDUSTRIES|CO\.?))",
    ], text)

    return {
        "buyer": buyer,
        "subject": subject,
        "ref": ref,
        "date": date_str,
        "gst_percent": gst_percent,
        "gstin": gstin,
        "items": items,
        "terms": _normalise_terms(text),
        "signatory": signatory,
        "raw": text.strip(),
    }
