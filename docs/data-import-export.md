# CSV Import / Export Formats

Endpoints (all require permissions; `data.export` for exports):

| Endpoint | Direction | Notes |
|---|---|---|
| `GET /api/export/products` | export | UTF-8 CSV download |
| `GET /api/export/customers` | export | |
| `GET /api/export/suppliers` | export | |
| `POST /api/import/products` (multipart `file`) | import | validated, all-or-nothing per file |
| `POST /api/import/customers` (multipart `file`) | import | |
| `GET /api/reports/export.csv?report=…&from=…&to=…` | export | any report as CSV |

UI: Settings → Data (choose file, see created/updated/error counts before commit).

## Products CSV

Required columns: **name**, **retail_price**. Optional: sku, barcode, category,
brand, unit, cost_price, wholesale_price, min_stock.

```csv
name,sku,barcode,cost_price,retail_price,category,brand,unit,min_stock,stock_qty
Surf Excel 1kg,SX-1K,8961234567890,350,400,Detergent,Surf Excel,Piece,10,20
Sugar 1kg,,,80,110,Grocery,,Kg,5,40
Cooking Oil 1L,,,260,300,Grocery,Sufi,Litre,6,
```

Rules & validation:
- `retail_price` must be a number ≥ 0; empty optional numeric cells are skipped.
- Matching: an existing product with the same **SKU** or same **name** is
  *updated* (price changes go through price-history + audit, never silent);
  otherwise a new product is created.
- Duplicate SKUs inside one file are rejected line-by-line.
- Categories/brands/units are auto-created if missing.
- `stock_qty` (if given) becomes an audited opening-stock movement.
- The response lists every rejected line with a reason; nothing partial commits.

## Customers CSV

Required column: **name**. Optional: phone, phone2, address, credit_limit,
opening_balance, notes.

```csv
name,phone,address,credit_limit,opening_balance
Ahmed Khan,03001234567,Johar Town,20000,0
Ali Truck Stand,03219876543,Saddar,,1500
```

Rules: duplicate names are reported and skipped; `opening_balance > 0` means
the customer already owes that amount (recorded as an audited ledger opening
entry, not a silent balance edit).

## Suppliers

Export only (`GET /api/export/suppliers`): name, company, phone, address,
contact_person, payment_terms, opening_payable, outstanding, status. Supplier
import follows the same pattern on request — use the UI form meanwhile.

## Reports CSV

Any report from the Reports page has an **Export CSV** button; it calls
`/api/reports/export.csv` with the same filters currently applied on screen
(date range, group-by, search). Files open directly in Excel (UTF-8 BOM).
