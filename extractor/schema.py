"""Output schema and normalisation helpers shared by every engine."""
from __future__ import annotations

from typing import Any

DOC_FIELDS = ["vendor", "invoice_number", "date", "currency", "subtotal", "tax", "total"]
ITEM_FIELDS = ["description", "quantity", "unit_price", "amount"]


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    s = str(v).replace(",", "").replace("$", "").replace("£", "").replace("€", "").strip()
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def empty_result() -> dict:
    return {
        "vendor": None,
        "invoice_number": None,
        "date": None,
        "currency": None,
        "line_items": [],
        "subtotal": None,
        "tax": None,
        "total": None,
    }


def normalize(data: dict) -> dict:
    """Coerce any engine output into the canonical schema."""
    out = empty_result()
    out["vendor"] = _str(data.get("vendor"))
    out["invoice_number"] = _str(data.get("invoice_number"))
    out["date"] = _str(data.get("date"))
    cur = _str(data.get("currency"))
    out["currency"] = cur.upper() if cur else None
    for k in ("subtotal", "tax", "total"):
        out[k] = _num(data.get(k))
    items = []
    for it in data.get("line_items") or []:
        if not isinstance(it, dict):
            continue
        items.append(
            {
                "description": _str(it.get("description")) or "",
                "quantity": _num(it.get("quantity")) if it.get("quantity") is not None else 1.0,
                "unit_price": _num(it.get("unit_price")),
                "amount": _num(it.get("amount")),
            }
        )
    out["line_items"] = items
    return out
