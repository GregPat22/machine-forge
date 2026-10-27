# Parking lot

Found, not fixed. Each entry is out of scope for the change that found it. Pick one up only when
a spec names it.

## Behaviour decided from display names (rule 1)

Found 2026-10-23 by scanning for `.lower()`, regex, `startswith` and `in name` checks.

### Phase 1 item: `backend/app/services/io_points.py`

`_text()` (line 34) joins `component.name` and the spec names and values into one lowercase
string, and `signals()` (lines 43-77) decides the I/O of each component by keyword in that
string ("thermocouple", "ejector", "axis", "gun", "door", "camera", "terminal", ...). Renaming a
component changes the generated I/O list and the PLC skeleton.
Replace with the model v2 fields `role`, `signals` and `motion`, filled by the AI and validated
by code. This is PLAN section 2, item 4.

### Other

- `backend/app/services/documents.py:144`: regex over the free-text `design.throughput` to
  check the required rate against the slowest cycle. Replace with a numeric
  `throughput_per_min` and unit field.
- `backend/app/services/sourcing.py:30-41`: `_similar` matches a spare part to a price-list
  entry by word overlap of names and descriptions. Fuzzy suggestion only. Replace with
  `part_number`, `manufacturer` and structured spec keys.
- `backend/app/services/sourcing.py:154`, `backend/app/storage.py:268,276,286`: supplier
  ratings are joined by `supplier.lower()`. Renaming a supplier loses its rating. Replace with
  a `supplier_id`. Supplier code is frozen, so this needs a spec that reopens it.
- `frontend/src/components/PlcView.tsx:16,23,68`: the selected file is found by `f.name`.
  Replace with an `id`.
- `frontend/src/components/SupplierRatings.tsx:33`: a supplier is found by `x.name === s.name`.
  Replace with a `supplier_id`.

### Not a problem

Search lowercasing (`Suppliers.tsx`), file extension checks, price and header parsing in
`price_list.py`, `spare_parts.py` and `suppliers/base.py`, env parsing in `config.py`, sheet
titles in `rfq.py`, and `plc.py:352` (filters on generated station codes, not labels).

## Rule checks that are not enforced

- Rule 1 (no behaviour from display names) has no automated test. `tests/test_repo_rules.py`
  only checks rule 4 (no import of the deleted render). Phase 1 item: write the grep test for
  rule 1 together with the `io_points.py` fix, so it can start with no allowlist.
- Rule 7: `tests/test_migration.py` builds the v0.3 database in code. Add a committed old-database fixture and test for rule 7.
