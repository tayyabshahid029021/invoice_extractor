"""Single entry point used by the UI, the evaluator and the tests."""
from __future__ import annotations

import os

from .llm import extract_with_llm
from .parser import parse_text
from .text_extraction import extract_text

ENGINES = {
    "rules": "Offline: OCR + rule-based parser (no API key)",
    "llm": "LLM: Gemini vision (needs GEMINI_API_KEY)",
}


def process(data: bytes, filename: str, engine: str = "rules", dayfirst: bool | None = None) -> dict:
    """Return {"result": {...}, "raw_text": str, "text_method": str, "engine": str}."""
    if dayfirst is None:
        dayfirst = os.getenv("DATE_DAYFIRST", "true").lower() != "false"
    if engine == "llm":
        return {"result": extract_with_llm(data, filename), "raw_text": "", "text_method": "gemini_vision", "engine": engine}
    text, method = extract_text(data, filename)
    return {"result": parse_text(text, dayfirst), "raw_text": text, "text_method": method, "engine": "rules"}
