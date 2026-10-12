"""Run the extractor over every sample and write a per-field accuracy report.

Run:  python scripts/evaluate.py [--engine rules|llm]
Output: reports/accuracy_report.json, reports/accuracy_report.md, reports/per_document.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
from extractor import process  # noqa: E402

SAMPLES = ROOT / "samples"
REPORTS = ROOT / "reports"
DOC_FIELDS = ["vendor", "invoice_number", "date", "currency", "subtotal", "tax", "total"]
ITEM_FIELDS = ["description", "quantity", "unit_price", "amount"]


def norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def field_ok(name: str, pred, gold) -> bool:
    if gold is None:
        return pred is None
    if pred is None:
        return False
    if name in ("subtotal", "tax", "total"):
        return abs(float(pred) - float(gold)) < 0.011
    if name == "vendor":
        return SequenceMatcher(None, norm(pred), norm(gold)).ratio() >= 0.9
    return norm(pred) == norm(gold)


def match_items(pred: list[dict], gold: list[dict]) -> list[tuple[dict, dict | None]]:
    """Greedy match each gold item to the most similar unused predicted item."""
    used: set[int] = set()
    out = []
    for g in gold:
        best, best_i = 0.0, None
        for i, p in enumerate(pred):
            if i in used:
                continue
            r = SequenceMatcher(None, norm(p["description"]), norm(g["description"])).ratio()
            if r > best:
                best, best_i = r, i
        if best_i is not None and best >= 0.8:
            used.add(best_i)
            out.append((g, pred[best_i]))
        else:
            out.append((g, None))
    return out


def score_items(pred: list[dict], gold: list[dict]) -> dict:
    pairs = match_items(pred, gold)
    c = {f: 0 for f in ITEM_FIELDS}
    for g, p in pairs:
        if p is None:
            continue
        c["description"] += 1
        for f in ("quantity", "unit_price", "amount"):
            if p.get(f) is not None and abs(float(p[f]) - float(g[f])) < 0.011:
                c[f] += 1
    matched = sum(1 for _, p in pairs if p is not None)
    precision = matched / len(pred) if pred else (1.0 if not gold else 0.0)
    return {"counts": c, "n_gold": len(gold), "n_pred": len(pred), "matched": matched, "precision": precision,
            "exact_list": len(pred) == len(gold) and all(
                p is not None and abs(p["amount"] - g["amount"]) < 0.011 and abs(p["quantity"] - g["quantity"]) < 0.011
                for g, p in pairs)}


def evaluate(engine: str = "rules", samples: Path = SAMPLES) -> dict:
    gt = json.loads((samples / "ground_truth.json").read_text(encoding="utf-8"))
    per_doc, field_hits = [], {f: 0 for f in DOC_FIELDS}
    item_hits = {f: 0 for f in ITEM_FIELDS}
    n_gold_items = n_pred_items = n_matched = n_exact = 0
    by_type: dict[str, dict] = {}
    for name, gold in gt.items():
        data = (samples / name).read_bytes()
        try:
            res = process(data, name, engine=engine)["result"]
            err = ""
        except Exception as e:  # keep going, count as all wrong
            res = {k: None for k in DOC_FIELDS} | {"line_items": []}
            err = str(e)
        row = {"file": name, "type": gold["meta"]["type"], "error": err}
        ok_count = 0
        for f in DOC_FIELDS:
            ok = field_ok(f, res.get(f), gold.get(f))
            field_hits[f] += ok
            ok_count += ok
            row[f] = int(ok)
            if not ok:
                row[f"{f}_pred"], row[f"{f}_gold"] = res.get(f), gold.get(f)
        s = score_items(res.get("line_items", []), gold["line_items"])
        for f in ITEM_FIELDS:
            item_hits[f] += s["counts"][f]
        n_gold_items += s["n_gold"]; n_pred_items += s["n_pred"]; n_matched += s["matched"]; n_exact += s["exact_list"]
        row["items_exact"] = int(s["exact_list"]); row["items_found"] = f"{s['matched']}/{s['n_gold']}"
        row["doc_fields_correct"] = f"{ok_count}/{len(DOC_FIELDS)}"
        per_doc.append(row)
        t = by_type.setdefault(gold["meta"]["type"], {"docs": 0, "fields_ok": 0, "fields_total": 0})
        t["docs"] += 1; t["fields_ok"] += ok_count; t["fields_total"] += len(DOC_FIELDS)
    n = len(gt)
    acc = {f: field_hits[f] / n for f in DOC_FIELDS}
    item_acc = {f: item_hits[f] / n_gold_items for f in ITEM_FIELDS}
    overall = (sum(field_hits.values()) + sum(item_hits.values())) / (n * len(DOC_FIELDS) + n_gold_items * len(ITEM_FIELDS))
    return {
        "engine": engine, "documents": n, "doc_field_accuracy": acc, "line_item_field_accuracy": item_acc,
        "line_item_recall": n_matched / n_gold_items, "line_item_precision": n_matched / n_pred_items if n_pred_items else 0.0,
        "docs_with_all_items_exact": n_exact / n, "overall_field_accuracy": overall,
        "by_document_type": {k: v["fields_ok"] / v["fields_total"] for k, v in by_type.items()},
        "per_document": per_doc,
    }


def write_reports(rep: dict, reports: Path = REPORTS) -> None:
    REPORTS_DIR = reports
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "accuracy_report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    cols = ["file", "type", "doc_fields_correct", "items_found", "items_exact"] + DOC_FIELDS
    with open(REPORTS_DIR / "per_document.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rep["per_document"])
    md = [f"# Accuracy report ({rep['engine']} engine, {rep['documents']} documents)\n",
          f"Overall field accuracy: **{rep['overall_field_accuracy']:.1%}**\n", "## Document-level fields\n",
          "| Field | Accuracy |", "|---|---|"]
    md += [f"| {k} | {v:.1%} |" for k, v in rep["doc_field_accuracy"].items()]
    md += ["", "## Line items\n", "| Metric | Value |", "|---|---|"]
    md += [f"| {k} accuracy | {v:.1%} |" for k, v in rep["line_item_field_accuracy"].items()]
    md += [f"| item recall | {rep['line_item_recall']:.1%} |", f"| item precision | {rep['line_item_precision']:.1%} |",
           f"| documents with fully correct item list | {rep['docs_with_all_items_exact']:.1%} |", "",
           "## By document type\n", "| Type | Doc-field accuracy |", "|---|---|"]
    md += [f"| {k} | {v:.1%} |" for k, v in rep["by_document_type"].items()]
    md += ["", "## Failures\n"]
    for r in rep["per_document"]:
        bad = [f for f in DOC_FIELDS if not r[f]]
        if bad or not r["items_exact"]:
            detail = "; ".join(f"{f}: got {r.get(f + '_pred')!r}, expected {r.get(f + '_gold')!r}" for f in bad)
            md.append(f"- `{r['file']}` items {r['items_found']}" + (f" | {detail}" if detail else ""))
    (REPORTS_DIR / "accuracy_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="rules", choices=["rules", "llm"])
    ap.add_argument("--samples", type=Path, default=SAMPLES, help="folder with files + ground_truth.json")
    ap.add_argument("--reports", type=Path, default=REPORTS, help="where to write the report")
    a = ap.parse_args()
    rep = evaluate(a.engine, a.samples)
    write_reports(rep, a.reports)
    print(f"Overall field accuracy: {rep['overall_field_accuracy']:.1%}")
    for k, v in rep["doc_field_accuracy"].items():
        print(f"  {k:15s} {v:.1%}")
    for k, v in rep["line_item_field_accuracy"].items():
        print(f"  item.{k:10s} {v:.1%}")
    print("Reports written to", a.reports)
