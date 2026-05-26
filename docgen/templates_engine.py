"""templates_engine.py — turn structured quotation data into varied `blocks` specs.

No LLM. Each "variant" is a random-but-distinct combination of style axes
(font, tone, section order, table style, currency/date format, header colour,
closing, etc.). build_spec() renders the data into a list of blocks for renderer.py.

This is the rule-based replacement for the drafting that Claude did in the plugin.
"""
from __future__ import annotations

import random
import re
from datetime import date, datetime


# ---------------------------------------------------------------- style axes
FONTS = ["Arial", "Times New Roman", "Calibri", "Georgia", "Verdana", "Cambria", "Tahoma"]
BODY_SIZES = [10, 11, 12]
TONES = ["formal", "semiformal", "terse", "warm"]
SECTION_ORDERS = ["a", "b", "c"]
ITEM_STYLES = ["full_table", "simple_table", "numbered_list", "keyvalue"]
CURRENCY_FMTS = ["rs_dec", "rupee_sym", "inr_plain", "slash_only"]
DATE_FMTS = ["d-Mon-Y", "d/m/Y", "Mon d, Y", "d.m.Y"]
QNUM_STYLES = ["qt", "dash", "ref", "none"]
TC_STYLES = ["bullets", "prose", "table"]
HEADER_SHADES = ["D9E2F3", "EAD1DC", "F4CCCC", "E2EFDA", "FFF2CC", "FFFFFF"]
TOTAL_STYLES = ["in_table", "paragraph", "framed"]

TONE_INTROS = {
    "formal": "We are pleased to submit herewith our most competitive offer for your kind consideration as detailed below:",
    "semiformal": "Please find below our offer against your enquiry. We trust the same will meet your requirement.",
    "terse": "Our quotation, as per your enquiry, is given below.",
    "warm": "Thank you for your enquiry. We are delighted to share our best pricing with you, as set out below.",
}
TONE_GREETINGS = {"formal": "Dear Sir,", "semiformal": "Dear Sir/Madam,",
                  "terse": "", "warm": "Dear Sir,"}
TONE_CLOSINGS = {
    "formal": "We look forward to receiving your valued order.\n\nThanking you,",
    "semiformal": "Awaiting your confirmation.\n\nWith regards,",
    "terse": "Regards,",
    "warm": "We would be glad to serve you and look forward to a long association.\n\nWarm regards,",
}


# ---------------------------------------------------------------- formatters
def _indian_group(n: str) -> str:
    """Group an integer string the Indian way: 1,25,000."""
    if len(n) <= 3:
        return n
    head, tail = n[:-3], n[-3:]
    head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
    return head + "," + tail


def fmt_money(amount: float, mode: str) -> str:
    if amount is None:
        return ""
    whole = f"{abs(amount):.2f}"
    int_part, dec = whole.split(".")
    grouped = _indian_group(int_part)
    if mode == "rs_dec":
        return f"Rs. {grouped}.{dec}"
    if mode == "rupee_sym":
        return f"₹ {grouped}"
    if mode == "inr_plain":
        return f"INR {int_part}.{dec}"
    if mode == "slash_only":
        return f"{grouped}/-"
    return f"Rs. {grouped}.{dec}"


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _parse_date(s: str) -> date:
    s = (s or "").strip()
    for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d", "%b %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return date.today()


def fmt_date(d: date, mode: str) -> str:
    if mode == "d-Mon-Y":
        return f"{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year}"
    if mode == "d/m/Y":
        return f"{d.day:02d}/{d.month:02d}/{d.year}"
    if mode == "Mon d, Y":
        return f"{_MONTHS[d.month - 1]} {d.day}, {d.year}"
    if mode == "d.m.Y":
        return f"{d.day:02d}.{d.month:02d}.{d.year}"
    return d.isoformat()


def make_qnum(mode: str, seed_n: int, fy: str) -> str:
    if mode == "qt":
        return f"QT/{fy}/{seed_n:03d}"
    if mode == "dash":
        return f"Q-{1000 + seed_n}"
    if mode == "ref":
        return f"Ref: {datetime.today().strftime('%y%m%d')}/{seed_n}"
    return ""


# ---------------------------------------------------------------- variants
def make_variants(n: int, seed: int | None = None) -> list[dict]:
    """Pick n distinct style combinations. Tries hard to make each look different."""
    rng = random.Random(seed)
    fonts = rng.sample(FONTS, k=min(n, len(FONTS)))
    while len(fonts) < n:
        fonts.append(rng.choice(FONTS))
    tones = (TONES * (n // len(TONES) + 1))
    rng.shuffle(tones)
    orders = (SECTION_ORDERS * (n // len(SECTION_ORDERS) + 1))
    rng.shuffle(orders)
    item_styles = (ITEM_STYLES * (n // len(ITEM_STYLES) + 1))
    rng.shuffle(item_styles)
    shades = rng.sample(HEADER_SHADES, k=min(n, len(HEADER_SHADES)))
    while len(shades) < n:
        shades.append(rng.choice(HEADER_SHADES))

    variants = []
    for i in range(n):
        variants.append({
            "font": fonts[i],
            "size": rng.choice(BODY_SIZES),
            "tone": tones[i],
            "order": orders[i],
            "item_style": item_styles[i],
            "currency": rng.choice(CURRENCY_FMTS),
            "date_fmt": rng.choice(DATE_FMTS),
            "qnum_style": rng.choice(QNUM_STYLES),
            "tc_style": rng.choice(TC_STYLES),
            "shade": shades[i],
            "total_style": rng.choice(TOTAL_STYLES),
            "seed_n": rng.randint(1, 999),
        })
    return variants


def describe(v: dict) -> str:
    tone = {"formal": "formal corporate", "semiformal": "semi-formal", "terse": "terse commercial", "warm": "warm personal"}[v["tone"]]
    item = {"full_table": "full itemised table", "simple_table": "compact 3-col table",
            "numbered_list": "numbered price list", "keyvalue": "key-value layout"}[v["item_style"]]
    return f"{v['font']} {v['size']}pt · {tone} tone · {item} · {v['tc_style']} T&C"


# ---------------------------------------------------------------- spec builder
def _compute_totals(items: list[dict], gst_percent: float):
    rows = []
    subtotal = 0.0
    for it in items:
        qty = float(str(it.get("qty", "0") or 0).replace(",", "") or 0)
        rate = float(str(it.get("rate", "0") or 0).replace(",", "") or 0)
        amt = it.get("amount")
        amount = float(str(amt).replace(",", "")) if amt not in (None, "", "0") else round(qty * rate, 2)
        subtotal += amount
        rows.append({**it, "qty": qty, "rate": rate, "amount": amount})
    gst_amt = round(subtotal * gst_percent / 100.0, 2)
    grand = round(subtotal + gst_amt, 2)
    return rows, subtotal, gst_amt, grand


def build_spec(data: dict, variant: dict, company: str, copy: dict | None = None) -> dict:
    """Build the blocks spec for one variation.

    `copy`, when given, is AI-written wording (greeting/intro/closing/subject/
    terms) that overrides the canned tone strings — this is what makes AI mode
    read naturally while reusing the same reliable layout/table logic.
    """
    v = variant
    copy = copy or {}
    font, size = v["font"], v["size"]
    base = {"font": font, "size": size}
    cur = lambda x: fmt_money(x, v["currency"])

    gst_percent = float(str(data.get("gst_percent", "18") or 18).replace("%", "") or 18)
    rows, subtotal, gst_amt, grand = _compute_totals(data.get("items", []), gst_percent)

    d = _parse_date(data.get("date", ""))
    fy = f"{d.year}-{str(d.year + 1)[-2:]}" if d.month >= 4 else f"{d.year - 1}-{str(d.year)[-2:]}"
    qnum = make_qnum(v["qnum_style"], v["seed_n"], fy)
    date_str = fmt_date(d, v["date_fmt"])

    blocks: list[dict] = []

    def head_para():
        line = f"Date: {date_str}"
        if qnum:
            blocks.append({"type": "paragraph", "text": qnum, "style": {**base, "alignment": "right", "bold": True}})
        blocks.append({"type": "paragraph", "text": line, "style": {**base, "alignment": "right"}})

    def to_block():
        buyer = data.get("buyer", "").strip() or "M/s __________"
        blocks.append({"type": "paragraph", "text": "To,\n" + buyer, "style": base})
        blocks.append({"type": "spacer", "lines": 1})

    def subject_block():
        subj = (copy.get("subject") or data.get("subject", "")).strip()
        if subj:
            blocks.append({"type": "heading", "text": f"Subject: {subj}", "level": 2,
                           "style": {**base, "bold": True, "underline": True,
                                     "alignment": "center" if v["order"] != "b" else "left",
                                     "size": size + 1}})
            blocks.append({"type": "spacer", "lines": 1})

    def greeting_intro():
        g = copy.get("greeting", TONE_GREETINGS[v["tone"]])
        intro = copy.get("intro") or TONE_INTROS[v["tone"]]
        if g:
            blocks.append({"type": "paragraph", "text": g, "style": base})
        blocks.append({"type": "paragraph", "text": intro,
                       "style": {**base, "alignment": "justify"}})
        blocks.append({"type": "spacer", "lines": 1})

    def items_block():
        style = v["item_style"]
        shade = v["shade"]
        tstyle = {"font": font, "size": max(size - 1, 9), "header_bold": True,
                  "borders": True, "header_align": "center"}
        if shade != "FFFFFF":
            tstyle["header_shading"] = shade
        if style == "full_table":
            headers = ["SN", "Description", "HSN", "Qty", "Unit", "Rate", "Amount"]
            body = [[str(i + 1), r["description"], r.get("hsn", "") or "-",
                     _n(r["qty"]), r.get("unit", "") or "-", cur(r["rate"]), cur(r["amount"])]
                    for i, r in enumerate(rows)]
            tstyle["row_aligns"] = ["center", "left", "center", "right", "center", "right", "right"]
            blocks.append({"type": "table", "headers": headers, "rows": body,
                           "column_widths_in": [0.4, 2.5, 0.7, 0.7, 0.6, 1.0, 1.2], "style": tstyle})
        elif style == "simple_table":
            headers = ["Item", "Qty", "Amount"]
            body = [[r["description"] + (f" @ {cur(r['rate'])}" if r["rate"] else ""),
                     _n(r["qty"]) + (f" {r.get('unit','')}" if r.get("unit") else ""), cur(r["amount"])]
                    for r in rows]
            tstyle["row_aligns"] = ["left", "center", "right"]
            blocks.append({"type": "table", "headers": headers, "rows": body,
                           "column_widths_in": [4.0, 1.3, 1.5], "style": tstyle})
        elif style == "numbered_list":
            for i, r in enumerate(rows):
                txt = f"{r['description']} — {_n(r['qty'])} {r.get('unit','')} @ {cur(r['rate'])} = {cur(r['amount'])}"
                blocks.append({"type": "bullet", "text": txt, "style": base})
        else:  # keyvalue
            for r in rows:
                blocks.append({"type": "paragraph",
                               "text": f"{r['description']}",
                               "style": {**base, "bold": True}})
                blocks.append({"type": "paragraph",
                               "text": f"   Qty: {_n(r['qty'])} {r.get('unit','')}    Rate: {cur(r['rate'])}    Amount: {cur(r['amount'])}",
                               "style": base})
        blocks.append({"type": "spacer", "lines": 1})

    def totals_block():
        lines = [
            ("Sub-Total", cur(subtotal)),
            (f"GST @ {_n(gst_percent)}%", cur(gst_amt)),
            ("Grand Total", cur(grand)),
        ]
        if v["total_style"] == "in_table" or v["total_style"] == "framed":
            body = [[lbl, val] for lbl, val in lines]
            tstyle = {"font": font, "size": size, "borders": v["total_style"] == "framed",
                      "row_aligns": ["left", "right"], "header_bold": True}
            blocks.append({"type": "table", "headers": [], "rows": body,
                           "column_widths_in": [4.5, 2.0], "style": tstyle})
        else:
            txt = "\n".join(f"{lbl}: {val}" for lbl, val in lines)
            blocks.append({"type": "paragraph", "text": txt,
                           "style": {**base, "alignment": "right", "bold": True}})
        blocks.append({"type": "spacer", "lines": 1})

    def terms_block():
        source = copy.get("terms") or data.get("terms", [])
        terms = [t for t in source if t.strip()]
        if not terms:
            return
        blocks.append({"type": "heading", "text": "Terms & Conditions", "level": 3,
                       "style": {**base, "bold": True, "size": size}})
        if v["tc_style"] == "bullets":
            for t in terms:
                blocks.append({"type": "bullet", "text": t, "style": base})
        elif v["tc_style"] == "prose":
            blocks.append({"type": "paragraph", "text": "  ".join(f"{i+1}) {t}." for i, t in enumerate(terms)),
                           "style": {**base, "alignment": "justify"}})
        else:  # table
            body = [[str(i + 1), t] for i, t in enumerate(terms)]
            blocks.append({"type": "table", "headers": [], "rows": body,
                           "column_widths_in": [0.4, 6.0],
                           "style": {"font": font, "size": max(size - 1, 9), "borders": True,
                                     "row_aligns": ["center", "left"]}})
        blocks.append({"type": "spacer", "lines": 1})

    def closing_block():
        sig = (data.get("signatory") or "").strip()
        close = copy.get("closing") or TONE_CLOSINGS[v["tone"]]
        tail = f"For {company}"
        if sig and sig.upper() != company.upper():
            tail += f"\n\n\n{sig}"
        else:
            tail += "\n\n\nAuthorised Signatory"
        blocks.append({"type": "paragraph", "text": close, "style": base})
        blocks.append({"type": "spacer", "lines": 1})
        blocks.append({"type": "paragraph", "text": tail, "style": {**base, "bold": True}})

    # ----- assemble per section order
    blocks.append({"type": "spacer", "lines": 1})
    if v["order"] == "a":  # Subject → Greeting → Items → Terms → Closing
        head_para(); to_block(); subject_block(); greeting_intro()
        items_block(); totals_block(); terms_block(); closing_block()
    elif v["order"] == "b":  # Date+Ref → To → Items → Total → T&C → Sign
        head_para(); to_block(); greeting_intro(); subject_block()
        items_block(); totals_block(); terms_block(); closing_block()
    else:  # c: narrative intro → bullet/tabular items → sign-off
        to_block(); head_para(); subject_block(); greeting_intro()
        items_block(); totals_block(); terms_block(); closing_block()

    return {"blocks": blocks, "keep_docx": True}


def item_summary(items: list[dict], limit: int = 6) -> str:
    """A short human description of what's being quoted, for an AI draft prompt."""
    names = [str(it.get("description", "")).strip() for it in items if str(it.get("description", "")).strip()]
    if not names:
        return "the items listed in the quotation"
    shown = names[:limit]
    extra = len(names) - len(shown)
    summary = "; ".join(shown)
    if extra > 0:
        summary += f"; and {extra} more item{'s' if extra > 1 else ''}"
    return summary


def _n(x) -> str:
    try:
        f = float(x)
        return str(int(f)) if f.is_integer() else f"{f:g}"
    except (TypeError, ValueError):
        return str(x)
