import { useEffect, useState } from "react";
import { api, money } from "../api";
import SupplierRatings from "../components/SupplierRatings";
import type { ConnectorStatus, PriceListEntry } from "../types";

export default function Suppliers() {
  const [entries, setEntries] = useState<PriceListEntry[]>([]);
  const [connectors, setConnectors] = useState<ConnectorStatus[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [append, setAppend] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [imports, setImports] = useState(0);

  useEffect(() => {
    api.priceList().then(setEntries).catch((e: Error) => setError(e.message));
    api.connectors().then(setConnectors).catch(() => undefined);
  }, []);

  async function upload() {
    if (!file) return;
    setError(null);
    setMessage(null);
    try {
      const result = await api.uploadPriceList(file, append);
      setMessage(`Imported ${result.imported} rows (${result.total} in your list).`);
      setEntries(await api.priceList());
      setImports((n) => n + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const q = filter.toLowerCase();
  const shown = q
    ? entries.filter((e) =>
        [e.supplier, e.manufacturer, e.part_number, e.description].some((v) => v?.toLowerCase().includes(q)),
      )
    : entries;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card p-5">
          <h2 className="font-semibold">Your current suppliers</h2>
          <p className="mt-1 text-sm text-slate-500">
            Import a price list or purchase history (.xlsx or .csv). Needed columns: supplier, and part number or
            description. Optional: manufacturer, unit price, currency, lead time (days), MOQ. English or Italian
            headers both work (e.g. “Fornitore”, “Codice”, “Prezzo”). Every sheet of an Excel file is read, so answered
            RFQ workbooks can be imported as they are (only quoted rows).
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <input type="file" accept=".csv,.xlsx,.xlsm" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={append} onChange={(e) => setAppend(e.target.checked)} />
              Append (otherwise replace)
            </label>
            <button className="btn-primary" disabled={!file} onClick={upload}>
              Import
            </button>
          </div>
          {message && <p className="mt-2 text-sm text-emerald-600">{message}</p>}
          {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        </section>

        <section className="card p-5">
          <h2 className="font-semibold">External supplier connectors</h2>
          <p className="mt-1 text-sm text-slate-500">
            Used by “Compare with external suppliers”. Configure keys in <code>backend/.env</code>.
          </p>
          <ul className="mt-3 space-y-2">
            {connectors.map((c) => (
              <li key={c.name} className="flex items-start gap-3 text-sm">
                <span
                  className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${c.configured ? "bg-emerald-500" : "bg-slate-300"}`}
                />
                <div>
                  <div className="font-medium">
                    {c.label} {c.configured ? "" : <span className="font-normal text-slate-400">· not configured</span>}
                  </div>
                  <div className="text-xs text-slate-500">{c.covers}</div>
                  {!c.configured && <div className="text-xs text-slate-400">{c.setup}</div>}
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <SupplierRatings refreshKey={imports} />

      <section className="card overflow-x-auto">
        <div className="flex items-center gap-3 border-b border-slate-200 p-3 dark:border-slate-800">
          <h2 className="font-semibold">Price list ({entries.length})</h2>
          <input
            className="input ml-auto max-w-xs"
            placeholder="Filter…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
        <table className="w-full">
          <thead>
            <tr>
              <th className="th">Supplier</th>
              <th className="th">Manufacturer</th>
              <th className="th">Part number</th>
              <th className="th">Description</th>
              <th className="th">Unit price</th>
              <th className="th">Lead time</th>
              <th className="th">MOQ</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {shown.slice(0, 500).map((e) => (
              <tr key={e.id}>
                <td className="td">{e.supplier}</td>
                <td className="td">{e.manufacturer ?? "—"}</td>
                <td className="td font-mono text-xs">{e.part_number ?? "—"}</td>
                <td className="td text-xs">{e.description ?? "—"}</td>
                <td className="td">{money(e.unit_price, e.currency)}</td>
                <td className="td">{e.lead_time_days !== null ? `${e.lead_time_days} d` : "—"}</td>
                <td className="td">{e.moq ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {shown.length > 500 && <p className="p-3 text-xs text-slate-500">Showing the first 500 rows.</p>}
      </section>
    </div>
  );
}
