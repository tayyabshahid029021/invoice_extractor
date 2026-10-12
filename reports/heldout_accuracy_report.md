# Held-out accuracy report (seed 2026, never used for tuning)


Overall field accuracy: **96.4%**

## Document-level fields

| Field | Accuracy |
|---|---|
| vendor | 100.0% |
| invoice_number | 100.0% |
| date | 96.7% |
| currency | 86.7% |
| subtotal | 100.0% |
| tax | 96.7% |
| total | 96.7% |

## Line items

| Metric | Value |
|---|---|
| description accuracy | 97.2% |
| quantity accuracy | 95.3% |
| unit_price accuracy | 95.3% |
| amount accuracy | 97.2% |
| item recall | 97.2% |
| item precision | 98.1% |
| documents with fully correct item list | 90.0% |

## By document type

| Type | Doc-field accuracy |
|---|---|
| pdf_text | 100.0% |
| pdf_scanned | 100.0% |
| image | 93.3% |

## Failures

- `invoice_14_scanned_layoutA.pdf` items 4/4
- `receipt_03_blur.jpg` items 3/3 | currency: got None, expected 'EUR'
- `receipt_07_speckle.png` items 2/5 | date: got None, expected '2026-03-21'; currency: got None, expected 'GBP'
- `receipt_08_clean.png` items 5/5 | currency: got None, expected 'EUR'
- `receipt_09_rotate.png` items 4/4 | tax: got None, expected 1568.77; total: got 9228.08, expected 10796.85
- `receipt_13_lowcontrast.png` items 3/3 | currency: got None, expected 'EUR'
- `receipt_14_speckle.png` items 4/4
