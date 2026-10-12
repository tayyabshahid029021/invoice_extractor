"""Invoice & Receipt Extractor (aiTransform). Run with:  streamlit run app.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "scripts"))

import os  # noqa: E402

from extractor import ENGINES, process  # noqa: E402
from extractor.export import to_csv, to_json  # noqa: E402
from extractor.text_extraction import render_preview  # noqa: E402

SAMPLES = ROOT / "samples"
REPORTS = ROOT / "reports"

st.set_page_config(page_title="Invoice & Receipt Extractor", page_icon="🧾", layout="wide")


@st.cache_data(show_spinner=False)
def run_cached(data: bytes, name: str, engine: str, dayfirst: bool) -> dict:
    return process(data, name, engine=engine, dayfirst=dayfirst)


def checks(res: dict) -> list[str]:
    """Cheap consistency checks that catch most extraction mistakes."""
    notes = []
    items = res.get("line_items") or []
    if items and res.get("subtotal") is not None:
        s = round(sum(i["amount"] or 0 for i in items), 2)
        if abs(s - res["subtotal"]) > 0.02:
            notes.append(f"Line items add up to {s:,.2f} but subtotal is {res['subtotal']:,.2f}.")
    if res.get("subtotal") is not None and res.get("tax") is not None and res.get("total") is not None:
        if abs(res["subtotal"] + res["tax"] - res["total"]) > 0.02:
            notes.append("Subtotal + tax does not equal total.")
    if res.get("total") is None:
        notes.append("Total was not found.")
    if not items:
        notes.append("No line items were detected.")
    return notes


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Settings")
    has_key = bool(os.getenv("GEMINI_API_KEY", "").strip())
    options = list(ENGINES) if has_key else ["rules"]
    engine = st.radio("Extraction engine", options, format_func=lambda k: ENGINES[k])
    if not has_key:
        st.caption("LLM engine is hidden because GEMINI_API_KEY is not set in .env.")
    dayfirst = st.checkbox("Ambiguous dates are DD/MM/YYYY", value=os.getenv("DATE_DAYFIRST", "true").lower() != "false")
    st.divider()
    st.caption("Supported: PDF (text or scanned), PNG, JPG, WEBP. Amounts are expected with two decimals.")

st.title("🧾 Invoice & Receipt Extractor")
st.caption("Upload an invoice or receipt and get vendor, date, line items and totals as JSON or CSV.")

tab_extract, tab_acc = st.tabs(["Extract", "Accuracy report"])

# ------------------------------------------------------------------ extract tab
with tab_extract:
    uploads = st.file_uploader("Upload invoices or receipts", type=["pdf", "png", "jpg", "jpeg", "webp"], accept_multiple_files=True)
    sample_names = sorted(p.name for p in SAMPLES.glob("*") if p.suffix in {".pdf", ".png", ".jpg"}) if SAMPLES.exists() else []
    picked = st.multiselect("...or try bundled samples", sample_names)

    files: list[tuple[str, bytes]] = [(u.name, u.getvalue()) for u in uploads]
    files += [(n, (SAMPLES / n).read_bytes()) for n in picked]

    if not files:
        st.info("Upload a file or pick a sample to begin.")
    results: list[tuple[str, dict]] = []
    for name, data in files:
        with st.expander(name, expanded=len(files) == 1):
            try:
                with st.spinner("Extracting..."):
                    out = run_cached(data, name, engine, dayfirst)
            except Exception as e:
                st.error(f"Could not process this file: {e}")
                continue
            res = out["result"]
            results.append((name, res))
            left, right = st.columns([1, 1.3])
            with left:
                img = render_preview(data, name)
                if img is not None:
                    st.image(img, width="stretch")
                st.caption(f"Text source: {out['text_method']}")
            with right:
                c1, c2, c3 = st.columns(3)
                c1.metric("Vendor", res["vendor"] or "n/a")
                c2.metric("Date", res["date"] or "n/a")
                c3.metric("Total", f"{res['total']:,.2f} {res['currency'] or ''}" if res["total"] is not None else "n/a")
                st.write(f"Invoice / receipt no: **{res['invoice_number'] or 'n/a'}**")
                if res["line_items"]:
                    st.dataframe(pd.DataFrame(res["line_items"]), hide_index=True, width="stretch")
                m1, m2 = st.columns(2)
                m1.write(f"Subtotal: **{res['subtotal'] if res['subtotal'] is not None else 'n/a'}**")
                m2.write(f"Tax: **{res['tax'] if res['tax'] is not None else 'n/a'}**")
                for note in checks(res):
                    st.warning(note)
                stem = Path(name).stem
                d1, d2 = st.columns(2)
                d1.download_button("Download JSON", to_json(res), f"{stem}.json", "application/json", key=f"j_{name}")
                d2.download_button("Download CSV", to_csv([(name, res)]), f"{stem}.csv", "text/csv", key=f"c_{name}")
                with st.expander("Raw JSON"):
                    st.json(res)
                if out["raw_text"]:
                    with st.expander("Extracted text"):
                        st.code(out["raw_text"], language=None)
    if len(results) > 1:
        st.divider()
        st.download_button("Download all as one CSV", to_csv(results), "extracted_all.csv", "text/csv")
        st.download_button("Download all as one JSON", json.dumps({n: r for n, r in results}, indent=2), "extracted_all.json", "application/json")

# ------------------------------------------------------------------ accuracy tab
def show_report(path: Path, title: str):
    if not path.exists():
        st.info(f"{title}: no report yet. Run `python scripts/evaluate.py`.")
        return
    rep = json.loads(path.read_text(encoding="utf-8"))
    st.subheader(title)
    a, b, c = st.columns(3)
    a.metric("Documents", rep["documents"])
    b.metric("Overall field accuracy", f"{rep['overall_field_accuracy']:.1%}")
    c.metric("Line item recall / precision", f"{rep['line_item_recall']:.0%} / {rep['line_item_precision']:.0%}")
    df = pd.DataFrame(
        [{"field": k, "accuracy": v, "level": "document"} for k, v in rep["doc_field_accuracy"].items()]
        + [{"field": f"item.{k}", "accuracy": v, "level": "line item"} for k, v in rep["line_item_field_accuracy"].items()]
    )
    st.bar_chart(df.set_index("field")["accuracy"])
    st.dataframe(df.assign(accuracy=df["accuracy"].map("{:.1%}".format)), hide_index=True, width="stretch")
    st.write("By document type:", {k: f"{v:.1%}" for k, v in rep["by_document_type"].items()})
    with st.expander("Per-document results"):
        cols = ["file", "type", "doc_fields_correct", "items_found", "items_exact"]
        st.dataframe(pd.DataFrame(rep["per_document"])[cols], hide_index=True, width="stretch")


with tab_acc:
    st.write("Per-field accuracy against known ground truth. The main set was used while building the parser, "
             "so it is optimistic. The held-out set was generated with a different seed and never used for tuning.")
    if st.button("Re-run evaluation on bundled samples"):
        import evaluate as ev

        with st.spinner("Running 30 documents through the pipeline..."):
            ev.write_reports(ev.evaluate(engine, SAMPLES))
        st.success("Report updated.")
    show_report(REPORTS / "accuracy_report.json", "Bundled samples")
    st.divider()
    show_report(REPORTS / "heldout_accuracy_report.json", "Held-out samples (unseen seed)")
