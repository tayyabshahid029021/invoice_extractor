from extractor.export import to_csv, to_json
from extractor.parser import find_date, parse_text

INVOICE = """Acme Supplies Ltd
INVOICE
Invoice No: INV-2026-0042
Date: 14 March 2026
Due Date: 13 April 2026
Description Qty Unit Price Amount
Widget A 2 10.00 20.00
USB Cable 2m 3 5.50 16.50
Subtotal 36.50
Tax (8%) 2.92
Total $39.42"""


def test_invoice_fields():
    r = parse_text(INVOICE)
    assert r["vendor"] == "Acme Supplies Ltd"
    assert r["invoice_number"] == "INV-2026-0042"
    assert r["date"] == "2026-03-14"
    assert r["currency"] == "USD"
    assert (r["subtotal"], r["tax"], r["total"]) == (36.5, 2.92, 39.42)
    assert [i["amount"] for i in r["line_items"]] == [20.0, 16.5]


def test_due_date_is_not_picked_as_invoice_date():
    assert find_date(["Due Date: 01/05/2026", "Invoice Date: 2026-04-01"]) == "2026-04-01"


def test_ambiguous_date_respects_dayfirst():
    assert find_date(["Date: 03/04/2026"], dayfirst=True) == "2026-04-03"
    assert find_date(["Date: 03/04/2026"], dayfirst=False) == "2026-03-04"


def test_receipt_two_line_item():
    r = parse_text("Corner Shop\nReceipt #: 1234\nDate: 2026-05-01\nWhole Milk 1L\n2 x 1.06 2.12\nSUBTOTAL 2.12\nTAX 7% 0.15\nTOTAL 2.27")
    assert r["line_items"] == [{"description": "Whole Milk 1L", "quantity": 2.0, "unit_price": 1.06, "amount": 2.12}]
    assert r["total"] == 2.27


def test_empty_text_returns_empty_schema():
    r = parse_text("")
    assert r["total"] is None and r["line_items"] == []


def test_exports():
    r = parse_text(INVOICE)
    assert '"vendor": "Acme Supplies Ltd"' in to_json(r)
    csv_text = to_csv([("a.pdf", r)])
    assert csv_text.splitlines()[0].startswith("source_file,vendor")
    assert len(csv_text.splitlines()) == 3  # header + 2 line items
