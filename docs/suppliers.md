# Suppliers and sourcing

Goal: for every part in the spare-parts catalog, compare **what you pay today** (your own price
list) with **what external vendors offer**, and suggest the best option.

## 1. Your price list (current suppliers)

Upload a `.xlsx` or `.csv` on the **Suppliers** page (`POST /api/price-list`). Column headers are
matched loosely, in English or Italian:

| Field | Accepted headers (examples) | Required |
|---|---|---|
| supplier | Supplier, Vendor, Fornitore | yes |
| part number | Part number, MPN, Codice, Codice articolo | part number **or** description |
| description | Description, Descrizione | part number **or** description |
| manufacturer | Manufacturer, Brand, Produttore, Marca | no |
| unit price | Price, Unit price, Prezzo, Prezzo unitario | no |
| currency | Currency, Valuta (default: base currency) | no |
| lead time (days) | Lead time, Tempo di consegna | no |
| MOQ | MOQ, Lotto minimo | no |

Italian number formats (`1.234,56`) and `;`-separated CSVs from Excel work. Each import replaces
the list unless you tick **Append**.

## 2. External connectors

| Connector | Status | Covers | Credentials |
|---|---|---|---|
| Mouser Search API | implemented, tested on sample payloads, **not yet run against the live API** | electrical / electronic: sensors, PSUs, I/O, connectors, some motion | `MOUSER_API_KEY` (free; 30 calls/min, 1000/day) |
| Nexar (Octopart) | implemented, tested on sample payloads, **not yet run against the live API** | offers from many distributors (Digi-Key, RS, Farnell, TME, …) | `NEXAR_CLIENT_ID`, `NEXAR_CLIENT_SECRET` (free tier has a monthly part limit) |

**First thing to do when you have keys:** run a comparison on a demo machine and check the
offers. The parsers follow the documented response shapes, but field details can differ.

Mouser connection errors show a safe message (and the HTTP status when available), without the
authenticated request URL or its API key.

### Coverage gap: pneumatics and mechanics

Electronics distributors cover sensors, PLCs and power supplies well, but they only partly cover
Festo, SMC, Bosch Rexroth, SKF bearings, igus or Misumi components. Those vendors don't publish
open price APIs. Realistic options:
- your own price list (already supported) — usually the best source for these parts;
- distributors that carry them and have APIs (RS and Farnell list some Festo/SMC/SKF);
- an **RFQ workflow**: generate request-for-quotation emails/Excel per supplier from the catalog
  and import the answers (candidate feature);
- commercial agreements (Misumi, Festo) for API or EDI access.

Candidate connectors: Digi-Key API v4 (direct), RS Components, Farnell/element14 Product Search
API, TME API.

## 3. How the comparison works

`services/sourcing.py`, per catalog line (custom "make" parts are skipped and marked for your
machine shops):

1. **Internal offers.** An exact match on the normalized part number (`6ES7 515-2AM02` =
   `6ES75152AM02`). If none, a *similar* match where the description shares ≥ 50% of its words with
   the part name and specs, and the manufacturer agrees.
2. **External offers.** Each connector is queried by part number when the design has one,
   otherwise by keywords (manufacturer + name + main specs). Keyword results are marked
   *similar*.
3. **Currency.** Prices are converted to the base currency (`MF_BASE_CURRENCY`, default EUR) with
   the static rates in `MF_FX_RATES`. Update them, or replace them with a live FX source.
4. **Score** (0–1) = weighted sum of:
   - price: cheapest / this price;
   - lead time: an offer in stock for the needed quantity (machine qty + recommended spares) counts
     as 3 days, otherwise the stated lead time;
   - availability: in stock for the full quantity 1.0, partial 0.5, unknown 0.5, none 0.
   - Weights: `MF_WEIGHT_PRICE` 0.5, `MF_WEIGHT_LEAD_TIME` 0.3, `MF_WEIGHT_AVAILABILITY` 0.2.
     Similar matches are multiplied by 0.8.
5. **Current** = your best-scoring internal offer. **Best** = the best-scoring offer overall.
   **Savings** = (current − best unit price) × quantity in the machine.

6. **Your ratings** (Suppliers page): quality and delivery reliability, 1–5 stars each, weighted
   by `MF_WEIGHT_RATING` (0.15). Unrated suppliers count as 3 stars. Preferred suppliers win ties.

Not yet considered: quantity price breaks beyond the first one, shipping and customs, payment
terms, framework agreements.

## 4. Requests for quotation (RFQ)

**Spare parts & suppliers → Request quotes (Excel)** builds one workbook for the revision:
- one sheet per current supplier (from your price list), with the parts you buy from them;
- an **Open market** sheet for parts without a supplier, to send to any vendor;
- quantities = machine quantity + recommended spares; prices are never included;
- yellow columns for the supplier to fill in: unit price, lead time, MOQ, notes.

Import the answered workbook on the Suppliers page (tick **Append** to keep your list). Every
sheet is read; on RFQ sheets (recognised by the *Quantity requested* column) only rows with a price
are imported.
