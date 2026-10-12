"""Rule-based field extraction from plain text (vendor, date, items, totals)."""
from __future__ import annotations

import re

from .schema import empty_result, normalize

MONEY = r"(?<![\d.,])(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?!\d|\.\d|\s*%)"
MONEY_RE = re.compile(MONEY)

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"

DATE_PATTERNS = [
    ("iso", re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b")),
    ("dmy_txt", re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[\s\-]+{MON}\.?,?[\s\-]+(\d{{4}})(?=\D|\d\d:\d\d|$)", re.I)),
    ("mdy_txt", re.compile(rf"\b{MON}\.?\s*(\d{{1,2}})(?:st|nd|rd|th)?,?\s*(\d{{4}})(?=\D|\d\d:\d\d|$)", re.I)),
    ("num", re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b")),
]

KW_SUBTOTAL = re.compile(r"sub\s*-?\s*total|net\s+amount", re.I)
KW_TAX = re.compile(r"(?<![a-z])(tax|vat|gst)(?![a-z])|sales\s*tax", re.I)
KW_TOTAL_STRONG = re.compile(r"grand\s+total|total\s+due|amount\s+due|balance\s+due|total\s+payable|amount\s+payable", re.I)
KW_TOTAL = re.compile(r"\btotal\b", re.I)
KW_HEADER = re.compile(r"description|item|qty|quantity|price|rate|amount|particulars", re.I)
KW_END = re.compile(r"sub\s*-?\s*total|\btotal\b|(?<![a-z])(tax|vat|gst)(?![a-z])|sales\s*tax|amount\s+due|balance\s+due", re.I)

SKIP_VENDOR = re.compile(
    r"^(tax\s+)?(invoice|receipt|sales\s+receipt|cash\s+receipt|statement|bill|credit\s+note)[\s:#.\-]*$", re.I)
VENDOR_NOISE = re.compile(r"@|www\.|http|\btel\b|\bphone\b|\bfax\b|\bbill\s*to\b|\bdate\b|\binvoice\s*(no|#|number)", re.I)

CURRENCY_CODES = ["USD", "EUR", "GBP", "PKR", "INR", "AED", "CAD", "AUD", "SAR"]


def _fix_line(ln: str) -> str:
    """Undo common OCR damage before any field is parsed."""
    ln = ln.replace("\u00d7", "x")
    ln = re.sub(r"(\d),\s+(\d{3}\b)", r"\1,\2", ln)            # "3, 946.20" -> "3,946.20"
    ln = re.sub(r"(\d)[.'`]\s*[xX]\s", r"\1 x ", ln)                # "4.x Muffin" -> "4 x Muffin"
    if not re.search(r"(?i)date|time", ln):
        ln = re.sub(r"(?<=\d):(\d{2})\.?\s*$", r".\1", ln)         # "5:77." -> "5.77"
    return ln


def _lines(text: str) -> list[str]:
    return [_fix_line(re.sub(r"[ \t]+", " ", ln).strip()) for ln in text.splitlines() if ln.strip()]


def to_float(s: str) -> float:
    return round(float(s.replace(",", "")), 2)


# ----------------------------------------------------------------- date
def _to_iso(kind: str, g: tuple, dayfirst: bool) -> str | None:
    try:
        if kind == "iso":
            y, m, d = int(g[0]), int(g[1]), int(g[2])
        elif kind == "dmy_txt":
            d, m, y = int(g[0]), MONTHS[g[1][:3].lower()], int(g[2])
        elif kind == "mdy_txt":
            m, d, y = MONTHS[g[0][:3].lower()], int(g[1]), int(g[2])
        else:
            a, b, y = int(g[0]), int(g[1]), int(g[2])
            if y < 100:
                y += 2000
            if a > 12:
                d, m = a, b
            elif b > 12:
                m, d = a, b
            else:
                d, m = (a, b) if dayfirst else (b, a)
        if 1 <= m <= 12 and 1 <= d <= 31 and 1990 <= y <= 2100:
            return f"{y:04d}-{m:02d}-{d:02d}"
    except (KeyError, ValueError):
        pass
    return None


def find_date(lines: list[str], dayfirst: bool = True) -> str | None:
    cands = []  # (priority, line index, iso)
    for idx, ln in enumerate(lines):
        low = ln.lower()
        due_pos = low.find("due")
        segments = [(ln, 2 if due_pos == 0 else 1)]
        if due_pos > 0:
            segments = [(ln[:due_pos], 1), (ln[due_pos:], 2)]
        for seg, base in segments:
            prio = base
            if base == 1 and "date" in seg.lower():
                prio = 0
            for kind, rx in DATE_PATTERNS:
                m = rx.search(seg)
                if m:
                    iso = _to_iso(kind, m.groups(), dayfirst)
                    if iso:
                        cands.append((prio, idx, iso))
                    break
    if not cands:
        return None
    return sorted(cands)[0][2]


# ----------------------------------------------------------------- vendor / ids / currency
def find_vendor(lines: list[str]) -> str | None:
    for ln in lines[:15]:
        m = re.match(r"(?i)^(from|vendor|seller|sold\s+by|merchant)\s*:\s*(.+)$", ln)
        if m:
            return m.group(2).strip()
    for ln in lines[:8]:
        if SKIP_VENDOR.match(ln) or VENDOR_NOISE.search(ln):
            continue
        letters = sum(c.isalpha() for c in ln)
        if letters < 3 or letters / max(len(ln), 1) < 0.55:
            continue
        return ln.strip(" -*#|")
    return None


def find_invoice_number(lines: list[str]) -> str | None:
    rx = re.compile(
        r"(?:invoice|inv|receipt|bill|order|ref)\s*(?:no\.?|number|num|#)?\s*[:#.\-]?\s*([A-Z0-9][A-Z0-9\-/]{2,})",
        re.I,
    )
    for ln in lines:
        for m in rx.finditer(ln):
            cand = m.group(1)
            if any(c.isdigit() for c in cand):
                return cand.strip("-/")
    return None


def find_currency(text: str) -> str | None:
    for code in CURRENCY_CODES:
        if re.search(rf"\b{code}\b", text):
            return code
    if "£" in text:
        return "GBP"
    # OCR often reads the pound sign as a lowercase f right before the total amount.
    if re.search(r"(?im)total[^\n]*?(?<![a-z0-9])f\s?\d", text):
        return "GBP"
    if "€" in text:
        return "EUR"
    if re.search(r"\bRs\b|\bPKR", text):
        return "PKR"
    if "$" in text:
        return "USD"
    return None


# ----------------------------------------------------------------- totals
def _last_amount(line: str) -> float | None:
    found = MONEY_RE.findall(line)
    return to_float(found[-1]) if found else None


def find_totals(lines: list[str]) -> dict:
    subtotal = tax = None
    total_cands = []  # (priority, idx, amount)
    for idx, ln in enumerate(lines):
        amt = _last_amount(ln)
        if amt is None:
            continue
        low = ln.lower()
        if KW_SUBTOTAL.search(low):
            subtotal = amt
        elif KW_TAX.search(low) and not re.search(r"incl|inc\.", low) and not KW_TOTAL_STRONG.search(low):
            tax = amt
        elif KW_TOTAL_STRONG.search(low):
            total_cands.append((0, idx, amt))
        elif KW_TOTAL.search(low):
            total_cands.append((1, idx, amt))
    total = None
    if total_cands:
        best = min(p for p, _, _ in total_cands)
        total = [a for p, i, a in total_cands if p == best][-1]
    return {"subtotal": subtotal, "tax": tax, "total": total}


# ----------------------------------------------------------------- line items
CUR = r"(?:[$£€]|Rs\.?)?\s?"
P_FULL = re.compile(rf"^(?P<desc>.+?)\s+(?P<qty>\d+(?:\.\d+)?)\s+{CUR}(?P<unit>{MONEY})\s+{CUR}(?P<amt>{MONEY})$")
P_XUNIT = re.compile(rf"^(?P<desc>.+?)\s+(?P<qty>\d+(?:\.\d+)?)\s*[xX@]\s*{CUR}(?P<unit>{MONEY})\s+{CUR}(?P<amt>{MONEY})$")
P_QTYFIRST = re.compile(rf"^(?P<qty>\d+(?:\.\d+)?)\s*[xX]\s+(?P<desc>.+?)\s+{CUR}(?P<amt>{MONEY})$")
P_QTYUNIT = re.compile(rf"^(?P<qty>\d+(?:\.\d+)?)\s*[xX@]\s*{CUR}(?P<unit>{MONEY})\s+{CUR}(?P<amt>{MONEY})$")
P_SIMPLE = re.compile(rf"^(?P<desc>.+?)\s+{CUR}(?P<amt>{MONEY})$")


def _clean_line(ln: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\bRs\.?\s*", "", ln.replace("£", "").replace("€", "").replace("$", ""))).strip()


def fix_ocr_description(desc: str) -> str:
    """Repair the most common OCR confusions inside item names (0 for O, l for 1)."""
    desc = re.sub(r"\b0(?=[A-Za-z]{2,}\b)", "O", desc)
    desc = re.sub(r"(?<![A-Za-z0-9])l(?=\d|kg\b|ml\b|g\b)", "1", desc)
    return desc


def find_line_items(lines: list[str]) -> list[dict]:
    start = 1
    for i, ln in enumerate(lines[:25]):
        if len(KW_HEADER.findall(ln)) >= 2 and not MONEY_RE.search(ln):
            start = i + 1
            break
    end = len(lines)
    for i in range(start, len(lines)):
        if KW_END.search(lines[i]) and MONEY_RE.search(lines[i]):
            end = i
            break
    items = []
    pending = None  # last text-only line, used when the quantity/price sits on the next line
    for raw in lines[start:end]:
        ln = _clean_line(raw)
        has_money = bool(MONEY_RE.search(ln))
        if not has_money:
            if re.search(r"(?i)\b(date|due|bill\s*to|invoice|tel|phone)\b", ln):
                pending = None
            elif any(c.isalpha() for c in ln):
                pending = ln
            continue
        item = None
        m = P_QTYUNIT.match(ln)
        if m and pending:
            qty, unit, amt = float(m["qty"]), to_float(m["unit"]), to_float(m["amt"])
            item = {"description": pending, "quantity": qty, "unit_price": unit, "amount": amt}
        else:
            for rx in (P_FULL, P_XUNIT, P_QTYFIRST, P_SIMPLE):
                m = rx.match(ln)
                if not m:
                    continue
                g = m.groupdict()
                desc = g["desc"].strip(" .-:")
                if not any(c.isalpha() for c in desc):
                    continue
                amt = to_float(g["amt"])
                qty = float(g["qty"]) if g.get("qty") else 1.0
                unit = to_float(g["unit"]) if g.get("unit") else (round(amt / qty, 2) if qty else amt)
                item = {"description": desc, "quantity": qty, "unit_price": unit, "amount": amt}
                break
        pending = None
        if item:
            item["description"] = fix_ocr_description(item["description"])
            items.append(item)
    return items


# ----------------------------------------------------------------- entry point
def parse_text(text: str, dayfirst: bool = True) -> dict:
    lines = _lines(text)
    if not lines:
        return empty_result()
    totals = find_totals(lines)
    items = find_line_items(lines)
    if totals["total"] is None:
        amounts = [a for ln in lines for a in map(to_float, MONEY_RE.findall(ln))]
        if totals["subtotal"] is not None:
            totals["total"] = round(totals["subtotal"] + (totals["tax"] or 0), 2)
        elif amounts:
            totals["total"] = max(amounts)
    return normalize(
        {
            "vendor": find_vendor(lines),
            "invoice_number": find_invoice_number(lines),
            "date": find_date(lines, dayfirst),
            "currency": find_currency(text),
            "line_items": items,
            **totals,
        }
    )
