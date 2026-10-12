"""JSON and CSV export."""
from __future__ import annotations

import csv
import io
import json

CSV_COLUMNS = [
    "source_file", "vendor", "invoice_number", "date", "currency",
    "item_description", "item_quantity", "item_unit_price", "item_amount",
    "subtotal", "tax", "total",
]


def to_json(result: dict) -> str:
    return json.dumps(result, indent=2, ensure_ascii=False)


def rows_for(result: dict, source_file: str = "") -> list[dict]:
    base = {
        "source_file": source_file,
        "vendor": result.get("vendor"),
        "invoice_number": result.get("invoice_number"),
        "date": result.get("date"),
        "currency": result.get("currency"),
        "subtotal": result.get("subtotal"),
        "tax": result.get("tax"),
        "total": result.get("total"),
    }
    items = result.get("line_items") or []
    if not items:
        return [{**base, "item_description": "", "item_quantity": "", "item_unit_price": "", "item_amount": ""}]
    return [
        {
            **base,
            "item_description": it.get("description"),
            "item_quantity": it.get("quantity"),
            "item_unit_price": it.get("unit_price"),
            "item_amount": it.get("amount"),
        }
        for it in items
    ]


def to_csv(results: list[tuple[str, dict]]) -> str:
    """results: list of (source_file, result). One CSV row per line item."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    w.writeheader()
    for name, res in results:
        for row in rows_for(res, name):
            w.writerow(row)
    return buf.getvalue()
