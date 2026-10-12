"""Optional LLM engine (Google Gemini, free tier works). Reads the file directly."""
from __future__ import annotations

import base64
import json
import mimetypes
import os

import requests

from .schema import normalize

PROMPT = """You extract data from invoices and receipts. Return ONLY JSON with this shape:
{"vendor": string, "invoice_number": string|null, "date": "YYYY-MM-DD"|null,
 "currency": "ISO 4217 code like USD"|null,
 "line_items": [{"description": string, "quantity": number, "unit_price": number, "amount": number}],
 "subtotal": number|null, "tax": number|null, "total": number}
Use null when a field is not present. Do not invent values. Numbers must be plain numbers without symbols."""


def extract_with_llm(data: bytes, filename: str) -> dict:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it to your .env file or use the offline engine.")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}},
            {"text": PROMPT},
        ]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = requests.post(url, params={"key": key}, json=body, timeout=90)
    if r.status_code != 200:
        raise RuntimeError(f"Gemini API error {r.status_code}: {r.text[:300]}")
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    text = text.strip().removeprefix("```json").removesuffix("```").strip()
    return normalize(json.loads(text))
