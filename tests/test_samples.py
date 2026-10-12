"""Regression test: the whole pipeline (OCR included) over every bundled sample."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import evaluate as ev  # noqa: E402


def test_test_set_size():
    gt = json.loads((ROOT / "samples" / "ground_truth.json").read_text(encoding="utf-8"))
    assert len(gt) >= 25


def test_accuracy_floor():
    rep = ev.evaluate("rules", ROOT / "samples")
    assert rep["overall_field_accuracy"] >= 0.90
    assert rep["doc_field_accuracy"]["total"] >= 0.90
    assert rep["doc_field_accuracy"]["vendor"] >= 0.90
