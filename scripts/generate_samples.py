"""Generate 30 self-made sample invoices and receipts plus exact ground truth.

Run:  python scripts/generate_samples.py
Output: samples/*.pdf|png|jpg and samples/ground_truth.json

Mix: 13 text PDFs (3 layouts), 2 scanned (image-only) PDFs and 15 receipt
photos/scans with different noise levels (rotation, blur, JPEG artefacts, shadow,
low contrast). Values are random but seeded, so results are reproducible.
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "samples"
SEED = 42

CURRENCIES = {
    "USD": {"sym": "$", "tax": (0.07, 0.0825)},
    "GBP": {"sym": "£", "tax": (0.20,)},
    "EUR": {"sym": "€", "tax": (0.19, 0.21)},
    "PKR": {"sym": "Rs. ", "tax": (0.17, 0.18)},
}

BUSINESSES = [
    ("Acme Office Supplies Ltd", "42 Market Street, Springfield", "office"),
    ("Northwind Traders Co", "18 Harbour Road, Portsmouth", "grocery"),
    ("Bluebird Cafe", "7 Elm Avenue, Austin", "cafe"),
    ("Lahore Digital Solutions", "Gulberg III, Lahore", "services"),
    ("Greenleaf Grocers", "221 Oak Lane, Denver", "grocery"),
    ("Pixel Forge Studio", "9 Canal View, Berlin", "services"),
    ("Metro Hardware & Tools", "560 Industrial Way, Leeds", "hardware"),
    ("The Daily Grind", "31 Station Road, Manchester", "cafe"),
    ("Silverline Electronics", "88 Tech Park, Karachi", "electronics"),
    ("Sunrise Bakery", "5 Rose Street, Edinburgh", "cafe"),
    ("Orbit Cloud Hosting GmbH", "Friedrichstrasse 12, Berlin", "services"),
    ("Falcon Stationers", "Mall Road, Lahore", "office"),
    ("Harvest Fresh Market", "14 Farm Lane, Dublin", "grocery"),
    ("Quantum Repair Works", "73 Bridge Street, Sydney", "hardware"),
    ("Cedar & Pine Furniture", "12 Timber Court, Toronto", "office"),
]

CATALOG = {
    "office": [("A4 Paper Ream", 4.5, 9), ("Ballpoint Pens Box", 3.2, 8), ("Stapler Heavy Duty", 12, 25),
               ("Desk Organizer", 9, 22), ("Printer Ink Cartridge", 18, 45), ("Sticky Notes Pack", 2, 6)],
    "grocery": [("Whole Milk 1L", 0.9, 2.2), ("Free Range Eggs 12", 2.5, 5), ("Basmati Rice 5kg", 8, 16),
                ("Olive Oil 500ml", 5, 11), ("Bananas 1kg", 1, 2.5), ("Cheddar Cheese 400g", 3, 7), ("Orange Juice 1L", 1.5, 3.5)],
    "cafe": [("Cappuccino", 2.8, 4.5), ("Blueberry Muffin", 2.2, 3.8), ("Club Sandwich", 5.5, 9), ("Iced Latte", 3, 5),
             ("Chicken Wrap", 5, 8.5), ("Cheesecake Slice", 3.5, 6), ("Mineral Water", 1, 2)],
    "hardware": [("Claw Hammer 16oz", 9, 20), ("Cordless Drill Bit Set", 14, 35), ("LED Bulb 4 Pack", 6, 14),
                 ("Extension Cord 5m", 8, 18), ("Wood Screws Box", 3, 8), ("Safety Gloves", 4, 10)],
    "electronics": [("USB-C Cable 2m", 4, 12), ("Wireless Mouse", 10, 30), ("HDMI Adapter", 7, 18),
                    ("Laptop Stand", 15, 40), ("Power Bank 10000mAh", 18, 45), ("Bluetooth Speaker", 20, 60)],
    "services": [("Website Maintenance (monthly)", 150, 400), ("SEO Audit Report", 200, 600), ("Cloud Hosting Plan", 40, 180),
                 ("Logo Design Package", 120, 350), ("Consulting Hour", 50, 120), ("Domain Renewal", 10, 25)],
}


def q(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money(x: Decimal) -> str:
    return f"{x:,.2f}"


def fmt_date(d: date, style: str) -> str:
    if style == "iso":
        return d.isoformat()
    if style == "long":
        return d.strftime("%d %B %Y").lstrip("0")
    if style == "us":
        return d.strftime("%B %d, %Y").replace(" 0", " ")
    if style == "slash":
        return d.strftime("%d/%m/%Y")
    return d.strftime("%d-%b-%Y")


def build_doc(rng: random.Random, biz, currency: str, n_items: int, with_subtotal=True) -> dict:
    name, addr, kind = biz
    cur = CURRENCIES[currency]
    d = date(2026, rng.randint(1, 9), rng.randint(13, 28))  # day>12 keeps slash dates unambiguous
    items = []
    for desc, lo, hi in rng.sample(CATALOG[kind], k=min(n_items, len(CATALOG[kind]))):
        scale = 280 if currency == "PKR" else 1
        unit = q(rng.uniform(lo, hi) * scale)
        qty = rng.choice([1, 1, 2, 3, 4, 5]) if kind != "services" else rng.choice([1, 1, 2, 3])
        items.append({"description": desc, "quantity": float(qty), "unit_price": float(unit), "amount": float(q(unit * qty))})
    subtotal = sum(q(i["amount"]) for i in items)
    rate = Decimal(str(rng.choice(cur["tax"])))
    tax = q(subtotal * rate)
    return {
        "vendor": name, "address": addr, "kind": kind,
        "invoice_number": rng.choice([f"INV-2026-{rng.randint(1, 999):04d}", f"{rng.randint(10000, 99999)}",
                                      f"R-{rng.randint(10000, 99999)}", f"2026/{rng.randint(100, 999)}"]),
        "date": d, "due": d + timedelta(days=30), "currency": currency, "sym": cur["sym"],
        "line_items": items, "subtotal": float(subtotal) if with_subtotal else None,
        "tax": float(tax), "total": float(subtotal + tax), "rate": float(rate * 100),
        "_subtotal_d": subtotal, "_tax_d": tax, "_total_d": subtotal + tax,
    }


def truth(doc: dict) -> dict:
    return {
        "vendor": doc["vendor"], "invoice_number": doc["invoice_number"], "date": doc["date"].isoformat(),
        "currency": doc["currency"], "line_items": doc["line_items"],
        "subtotal": doc["subtotal"], "tax": doc["tax"], "total": doc["total"],
    }


# --------------------------------------------------------------------- PDF layouts
def pdf_layout_a(doc, path, dstyle):
    c = canvas.Canvas(str(path), pagesize=A4)
    s = doc["sym"]
    c.setFont("Helvetica-Bold", 18); c.drawString(40, 800, doc["vendor"])
    c.setFont("Helvetica", 9); c.drawString(40, 786, doc["address"])
    c.setFont("Helvetica-Bold", 24); c.drawRightString(555, 770, "INVOICE")
    c.setFont("Helvetica", 10)
    c.drawRightString(555, 748, f"Invoice No: {doc['invoice_number']}")
    c.drawRightString(555, 734, f"Date: {fmt_date(doc['date'], dstyle)}")
    c.drawRightString(555, 720, f"Due Date: {fmt_date(doc['due'], dstyle)}")
    c.setFont("Helvetica-Bold", 10); c.drawString(40, 700, "Bill To:")
    c.setFont("Helvetica", 10); c.drawString(40, 686, "Orion Retail Pvt Ltd"); c.drawString(40, 673, "77 Commerce Avenue")
    y = 630
    c.setFillGray(0.9); c.rect(40, y - 5, 515, 20, fill=1, stroke=0); c.setFillGray(0)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(46, y, "Description"); c.drawRightString(350, y, "Qty"); c.drawRightString(450, y, "Unit Price"); c.drawRightString(550, y, "Amount")
    c.setFont("Helvetica", 10)
    for it in doc["line_items"]:
        y -= 22
        c.drawString(46, y, it["description"]); c.drawRightString(350, y, f"{int(it['quantity'])}")
        c.drawRightString(450, y, f"{s}{money(q(it['unit_price']))}"); c.drawRightString(550, y, f"{s}{money(q(it['amount']))}")
        c.setStrokeGray(0.8); c.line(40, y - 6, 555, y - 6)
    y -= 34
    for label, val, bold in (("Subtotal", doc["_subtotal_d"], False), (f"Tax ({doc['rate']:g}%)", doc["_tax_d"], False), ("Total", doc["_total_d"], True)):
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11)
        c.drawString(400, y, label); c.drawRightString(550, y, f"{s}{money(val)}"); y -= 18
    c.setFont("Helvetica", 8); c.drawString(40, 60, "Thank you for your business. Payment terms: Net 30. Account 5521 8830 1147.")
    c.save()


def pdf_layout_b(doc, path, dstyle):
    c = canvas.Canvas(str(path), pagesize=A4)
    s = doc["sym"]
    c.setFont("Helvetica", 12); c.drawString(50, 800, "Tax Invoice")
    c.setFont("Helvetica-Bold", 16); c.drawString(50, 778, doc["vendor"])
    c.setFont("Helvetica", 10); c.drawString(50, 764, doc["address"])
    c.drawString(50, 740, f"Invoice #: {doc['invoice_number']}")
    c.drawString(50, 726, f"Issued: {fmt_date(doc['date'], dstyle)}")
    c.drawString(50, 712, f"Payment due: {fmt_date(doc['due'], dstyle)}")
    y = 676
    c.setFont("Helvetica-Bold", 10); c.drawString(50, y, "Item"); c.drawString(300, y, "Qty x Price"); c.drawRightString(545, y, "Total")
    c.setFont("Helvetica", 10)
    for it in doc["line_items"]:
        y -= 18
        c.drawString(50, y, it["description"]); c.drawString(300, y, f"{int(it['quantity'])} x {money(q(it['unit_price']))}")
        c.drawRightString(545, y, money(q(it["amount"])))
    y -= 30
    c.drawString(350, y, f"VAT {doc['rate']:g}%"); c.drawRightString(545, y, money(doc["_tax_d"])); y -= 18
    c.setFont("Helvetica-Bold", 12); c.drawString(350, y, "Total"); c.drawRightString(545, y, f"{s}{money(doc['_total_d'])}")
    c.save()


def pdf_layout_c(doc, path, dstyle):
    c = canvas.Canvas(str(path), pagesize=A4)
    s = doc["sym"]
    c.setFont("Helvetica-Bold", 20); c.drawCentredString(297, 800, doc["vendor"])
    c.setFont("Helvetica", 9); c.drawCentredString(297, 786, doc["address"])
    c.setFont("Helvetica", 10)
    c.drawString(50, 750, f"Invoice Number: {doc['invoice_number']}"); c.drawString(330, 750, f"Invoice Date: {fmt_date(doc['date'], dstyle)}")
    c.setFont("Helvetica-Bold", 14); c.drawString(50, 715, f"Amount Due: {s}{money(doc['_total_d'])}")
    y = 670
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Item"); c.drawRightString(340, y, "Qty"); c.drawRightString(430, y, "Rate"); c.drawRightString(540, y, "Amount")
    c.line(50, y - 4, 540, y - 4)
    c.setFont("Helvetica", 10)
    for it in doc["line_items"]:
        y -= 20
        c.drawString(50, y, it["description"]); c.drawRightString(340, y, f"{int(it['quantity'])}")
        c.drawRightString(430, y, money(q(it["unit_price"]))); c.drawRightString(540, y, money(q(it["amount"])))
    y -= 32
    for label, val in (("Subtotal", doc["_subtotal_d"]), (f"Sales Tax {doc['rate']:g}%", doc["_tax_d"]), ("Total Due", doc["_total_d"])):
        c.drawString(360, y, label); c.drawRightString(540, y, f"{s}{money(val)}" if label == "Total Due" else money(val)); y -= 17
    c.save()


def rasterize_pdf(pdf_path: Path, rng: random.Random):
    """Turn a text PDF into an image-only (scanned) PDF with slight skew and noise."""
    import pypdfium2 as pdfium

    img = pdfium.PdfDocument(str(pdf_path))[0].render(scale=2).to_pil().convert("RGB")
    img = img.rotate(rng.uniform(-1.2, 1.2), expand=True, fillcolor=(255, 255, 255), resample=Image.BICUBIC)
    img = img.filter(ImageFilter.GaussianBlur(0.7))
    px = img.load()
    for _ in range(img.width * img.height // 120):
        x, y = rng.randrange(img.width), rng.randrange(img.height)
        v = rng.randint(150, 235)
        px[x, y] = (v, v, v)
    img.save(pdf_path, "PDF", resolution=150)


# --------------------------------------------------------------------- receipts
def load_font(size: int):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "C:/Windows/Fonts/consola.ttf",
              "C:/Windows/Fonts/cour.ttf", "/System/Library/Fonts/Menlo.ttc", "/Library/Fonts/Courier New.ttf"]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def receipt_lines(doc, style: int, dstyle: str, width_chars=38):
    s = doc["sym"]
    two = lambda l, r: l[: width_chars - len(r) - 1].ljust(width_chars - len(r)) + r
    L = [("c", doc["vendor"].upper()), ("c", doc["address"]), ("c", "Tel: 555-0142"), ("l", ""),
         ("l", f"Receipt #: {doc['invoice_number']}"), ("l", f"Date: {fmt_date(doc['date'], dstyle)}  14:22"), ("l", "-" * width_chars)]
    for it in doc["line_items"]:
        qty, unit, amt = int(it["quantity"]), money(q(it["unit_price"])), money(q(it["amount"]))
        if style == 1:
            L.append(("l", two(it["description"], amt)) if qty == 1 else ("l", it["description"]))
            if qty != 1:
                L.append(("l", two(f"  {qty} x {unit}", amt)))
        elif style == 2:
            L.append(("l", two(f"{qty} x {it['description']}", amt)))
        else:
            L.append(("l", two(it["description"], amt)))
    L.append(("l", "-" * width_chars))
    L.append(("l", two("SUBTOTAL", money(doc["_subtotal_d"]))))
    L.append(("l", two(f"TAX {doc['rate']:g}%", money(doc["_tax_d"]))))
    L.append(("b", two("TOTAL", f"{s}{money(doc['_total_d'])}")))
    L.append(("l", two("CASH", money(q(float(doc["_total_d"]) + 20 - float(doc["_total_d"]) % 10)))))
    L.append(("l", "")); L.append(("c", "THANK YOU, COME AGAIN!"))
    return L


def render_receipt(doc, path: Path, style: int, dstyle: str, noise: str, rng: random.Random):
    font, bold = load_font(20), load_font(22)
    lines = receipt_lines(doc, style, dstyle)
    w, lh = 540, 30
    img = Image.new("RGB", (w, lh * (len(lines) + 2)), (252, 252, 250))
    d = ImageDraw.Draw(img)
    y = lh // 2
    for kind, text in lines:
        f = bold if kind == "b" else font
        tw = d.textlength(text, font=f)
        x = (w - tw) / 2 if kind == "c" else 18
        d.text((x, y), text, fill=(25, 25, 25), font=f)
        y += lh
    if noise == "rotate":
        img = img.rotate(rng.uniform(-2.5, 2.5), expand=True, fillcolor=(235, 235, 235), resample=Image.BICUBIC)
    elif noise == "blur":
        img = img.filter(ImageFilter.GaussianBlur(1.1))
    elif noise == "shadow":
        px = img.load()
        for yy in range(img.height):
            for xx in range(img.width):
                r, g, b = px[xx, yy]
                k = 1 - 0.28 * (xx / img.width)
                px[xx, yy] = (int(r * k), int(g * k), int(b * k))
    elif noise == "lowcontrast":
        img = Image.eval(img, lambda v: int(150 + v * 0.42))
    elif noise == "speckle":
        px = img.load()
        for _ in range(img.width * img.height // 60):
            xx, yy = rng.randrange(img.width), rng.randrange(img.height)
            v = rng.randint(90, 220)
            px[xx, yy] = (v, v, v)
    if path.suffix == ".jpg":
        img.save(path, quality=45 if noise == "jpeg" else 85)
    else:
        img.save(path)


# --------------------------------------------------------------------- main
def main(seed: int = SEED, out: Path = OUT):
    global OUT
    OUT = out
    rng = random.Random(seed)
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*"):
        if f.suffix in {".pdf", ".png", ".jpg", ".json"}:
            f.unlink()
    gt: dict[str, dict] = {}
    cur_cycle = ["USD", "GBP", "EUR", "PKR", "USD"]
    dstyles = ["iso", "long", "us", "slash", "mon"]

    plan = [("A", 5), ("B", 4), ("C", 4)]
    n = 0
    for layout, count in plan:
        for k in range(count):
            n += 1
            biz = BUSINESSES[(n * 2) % len(BUSINESSES)]
            cur = cur_cycle[n % len(cur_cycle)]
            doc = build_doc(rng, biz, cur, rng.randint(2, 5), with_subtotal=(layout != "B"))
            name = f"invoice_{n:02d}_layout{layout}.pdf"
            {"A": pdf_layout_a, "B": pdf_layout_b, "C": pdf_layout_c}[layout](doc, OUT / name, dstyles[n % 5])
            gt[name] = {**truth(doc), "meta": {"type": "pdf_text", "layout": layout}}
    for layout in ("A", "C"):
        n += 1
        doc = build_doc(rng, BUSINESSES[(n * 3) % len(BUSINESSES)], cur_cycle[n % 5], rng.randint(3, 5))
        name = f"invoice_{n:02d}_scanned_layout{layout}.pdf"
        {"A": pdf_layout_a, "C": pdf_layout_c}[layout](doc, OUT / name, dstyles[n % 5])
        rasterize_pdf(OUT / name, rng)
        gt[name] = {**truth(doc), "meta": {"type": "pdf_scanned", "layout": layout}}

    noises = ["clean", "rotate", "blur", "jpeg", "shadow", "lowcontrast", "speckle"]
    cafes = [b for b in BUSINESSES if b[2] in ("cafe", "grocery", "hardware", "electronics")]
    for k in range(15):
        biz = cafes[k % len(cafes)]
        cur = cur_cycle[k % len(cur_cycle)]
        noise = noises[k % len(noises)]
        style = 1 + k % 3
        doc = build_doc(rng, biz, cur, rng.randint(2, 5))
        if style == 3:
            for it in doc["line_items"]:  # style 3 prints only the amount, so keep qty = 1
                it["quantity"], it["amount"] = 1.0, it["unit_price"]
            doc["_subtotal_d"] = sum(q(i["amount"]) for i in doc["line_items"])
            doc["_tax_d"] = q(doc["_subtotal_d"] * Decimal(str(doc["rate"])) / 100)
            doc["_total_d"] = doc["_subtotal_d"] + doc["_tax_d"]
            doc["subtotal"], doc["tax"], doc["total"] = float(doc["_subtotal_d"]), float(doc["_tax_d"]), float(doc["_total_d"])
        ext = ".jpg" if noise in ("jpeg", "blur", "shadow") else ".png"
        name = f"receipt_{k + 1:02d}_{noise}{ext}"
        render_receipt(doc, OUT / name, style, dstyles[k % 5], noise, rng)
        gt[name] = {**truth(doc), "meta": {"type": "image", "style": style, "noise": noise}}

    (OUT / "ground_truth.json").write_text(json.dumps(gt, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(gt)} samples to {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Generate sample invoices/receipts with ground truth")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", type=Path, default=OUT, help="output folder (default: samples/)")
    a = ap.parse_args()
    main(a.seed, a.out)
