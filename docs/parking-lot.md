# Parking lot

Found, not fixed. Each entry is out of scope for the change that found it. Pick one up only when
a spec names it.

## Behaviour decided from display names (rule 1)

Found 2026-10-23 by scanning for `.lower()`, regex, `startswith` and `in name` checks.

`io_points.py` (I/O by keyword in component names) and the regex over the required rate in
`documents.py` were fixed in Phase 1 step 3. `tests/test_repo_rules.py` now catches direct
comparisons and regex tests on names, not indirect ones (see `docs/engineering-rules.md`, rule 1).

### Other

- `backend/app/services/documents.py`, `cycle_check`: the required rate is free text
  (`target_rate_text`), so it is shown but no longer compared with the slowest cycle. The check
  comes back with a numeric rate field (Phase 3, throughput).
- `backend/app/llm/mock.py`, cartoner: the hot-melt unit and the hot-melt guns are both
  category `dosing`, so since Phase 1 step 3 both get a "dispense" output and the unit is a
  dispense step in the PLC skeleton instead of running continuously. Before, only the word "gun"
  in the name told them apart. Agreed fix (Greg, 2026-10-27): category `pump` for the unit, as a
  separate small change after step 3.
- PLC view: a design migrated from v1 has no `signals`, so it has no I/O points and the PLC
  stations say "no actuated components detected" without saying why (ADR 0015). Only the I/O list
  in the documents names the components without signals. `plc.py` is frozen.
- `backend/app/services/io_points.py`: a `safety` component gets two-channel safety inputs only
  when its role is `sensor`. With no role, a door switch's inputs are plain DI, and the PLC sizing
  counts them as standard inputs. Nothing requires a role on safety parts.
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

- Rule 7: `tests/test_migration.py` builds the v0.3 database in code. Add a committed old-database fixture and test for rule 7.

## Docs to update

- `README.md`, roadmap lines for Phases 4 and 5: still the summary from before ADRs 0016 and 0017.
  Phase 4 should mention the shape kit, materials and lighting; Phase 5 the parametric module
  shapes and whole-machine STEP import. Greg asked (2026-10-27) to be reminded; it goes with the
  communication work, not before.
