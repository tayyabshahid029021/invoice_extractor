# Accuracy report (rules engine, 30 documents)

Overall field accuracy: **99.5%**

## Document-level fields

| Field | Accuracy |
|---|---|
| vendor | 100.0% |
| invoice_number | 100.0% |
| date | 100.0% |
| currency | 90.0% |
| subtotal | 100.0% |
| tax | 100.0% |
| total | 100.0% |

## Line items

| Metric | Value |
|---|---|
| description accuracy | 100.0% |
| quantity accuracy | 100.0% |
| unit_price accuracy | 100.0% |
| amount accuracy | 100.0% |
| item recall | 100.0% |
| item precision | 100.0% |
| documents with fully correct item list | 100.0% |

## By document type

| Type | Doc-field accuracy |
|---|---|
| pdf_text | 100.0% |
| pdf_scanned | 100.0% |
| image | 97.1% |

## Failures

- `receipt_03_blur.jpg` items 3/3 | currency: got None, expected 'EUR'
- `receipt_08_clean.png` items 5/5 | currency: got None, expected 'EUR'
- `receipt_13_lowcontrast.png` items 2/2 | currency: got None, expected 'EUR'
