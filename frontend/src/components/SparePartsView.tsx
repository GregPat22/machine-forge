import { Fragment, useEffect, useState } from "react";
import { api, money } from "../api";
import type { SourcingLine, SourcingReport, SparePart } from "../types";

const CRIT_STYLE = {
  A: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  B: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  C: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
};

function OffersTable({ line, currency }: { line: SourcingLine; currency: string }) {
  if (line.offers.length === 0) return <p className="px-3 py-2 text-xs text-slate-500">{line.note}</p>;
  return (
    <table className="w-full bg-slate-50 dark:bg-slate-950">
      <thead>
        <tr>
          <th className="th">Supplier</th>
          <th className="th">Source</th>
          <th className="th">Part</th>
          <th className="th">Unit price</th>
          <th className="th">Stock</th>
          <th className="th">Lead time</th>
          <th className="th">Score</th>
        </tr>
      </thead>
      <tbody>
        {line.offers.map((o, i) => (
          <tr key={i} className={i === 0 && line.best ? "font-medium" : ""}>
            <td className="td">
              {o.url ? (
                <a href={o.url} target="_blank" rel="noreferrer" className="underline hover:text-amber-600">
                  {o.supplier}
                </a>
              ) : (
                o.supplier
              )}
              {o.is_current && <span className="ml-1 rounded bg-sky-100 px-1 text-[11px] text-sky-800">your list</span>}
              {o.preferred && <span className="ml-1 rounded bg-emerald-100 px-1 text-[11px] text-emerald-800">preferred</span>}
              {o.rating !== null && <span className="ml-1 text-[11px] text-amber-600">{"★".repeat(Math.round(o.rating))}</span>}
            </td>
            <td className="td text-xs">{o.source}</td>
            <td className="td text-xs">
              <span className="font-mono">{o.part_number ?? "—"}</span>
              {o.match === "similar" && <span className="ml-1 text-orange-600">(similar)</span>}
              <div className="text-slate-500">{o.description}</div>
            </td>
            <td className="td">
              {money(o.unit_price_base, currency)}
              {o.currency && o.currency !== currency && (
                <div className="text-[11px] text-slate-500">{money(o.unit_price, o.currency)}</div>
              )}
            </td>
            <td className="td">{o.stock ?? "—"}</td>
            <td className="td">{o.lead_time_days !== null ? `${o.lead_time_days} d` : "—"}</td>
            <td className="td">{o.score?.toFixed(2) ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function SparePartsView({ projectId, revision }: { projectId: string; revision: number }) {
  const [parts, setParts] = useState<SparePart[]>([]);
  const [report, setReport] = useState<SourcingReport | null>(null);
  const [busy, setBusy] = useState<"internal" | "external" | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [onlySpares, setOnlySpares] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setReport(null);
    api.spareParts(projectId, revision).then(setParts).catch((e: Error) => setError(e.message));
  }, [projectId, revision]);

  async function compare(external: boolean) {
    setBusy(external ? "external" : "internal");
    setError(null);
    try {
      setReport(await api.sourcing(projectId, revision, external));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const lines = new Map(report?.lines.map((l) => [l.part.key, l]));
  const currency = report?.base_currency ?? "EUR";
  const visible = onlySpares ? parts.filter((p) => p.wear_part || p.recommended_spares > 0) : parts;
  const savings = report?.lines.reduce((sum, l) => sum + (l.savings_base ?? 0), 0) ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <button className="btn-secondary" disabled={busy !== null} onClick={() => compare(false)}>
          {busy === "internal" ? "Comparing…" : "Compare with my price list"}
        </button>
        <button className="btn-primary" disabled={busy !== null} onClick={() => compare(true)}>
          {busy === "external" ? "Querying suppliers…" : "Compare with external suppliers"}
        </button>
        <a className="btn-secondary" href={api.sparePartsCsvUrl(projectId, revision)}>
          Download CSV
        </a>
        <a
          className="btn-secondary"
          href={api.rfqUrl(projectId, revision)}
          title="Excel with one sheet per supplier. Send it, then import the answers on the Suppliers page."
        >
          Request quotes (Excel)
        </a>
        <label className="ml-auto flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          <input type="checkbox" checked={onlySpares} onChange={(e) => setOnlySpares(e.target.checked)} />
          Only parts to stock as spares
        </label>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}

      {report && (
        <div className="grid gap-3 md:grid-cols-3">
          <div className="card px-4 py-3">
            <div className="text-xs text-slate-500">Machine cost with current suppliers*</div>
            <div className="text-lg font-semibold">{money(report.total_current_base, currency)}</div>
          </div>
          <div className="card px-4 py-3">
            <div className="text-xs text-slate-500">With the best offers*</div>
            <div className="text-lg font-semibold">{money(report.total_best_base, currency)}</div>
          </div>
          <div className="card px-4 py-3">
            <div className="text-xs text-slate-500">Potential savings on parts with both prices</div>
            <div className="text-lg font-semibold text-emerald-600">{money(savings, currency)}</div>
          </div>
          <p className="text-[11px] text-slate-500 md:col-span-3">
            * Only parts that have a price. Connectors used: {report.connectors_used.join(", ") || "none"}.
            {report.connector_errors.map((e) => (
              <span key={e} className="ml-2 text-red-600">
                {e}
              </span>
            ))}
          </p>
        </div>
      )}

      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-slate-200 dark:border-slate-800">
            <tr>
              <th className="th">#</th>
              <th className="th">Part</th>
              <th className="th">Manufacturer / P/N</th>
              <th className="th">Qty</th>
              <th className="th">Spares</th>
              <th className="th">Crit.</th>
              {report && <th className="th">Current supplier</th>}
              {report && <th className="th">Best offer</th>}
              {report && <th className="th">Savings</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {visible.map((p) => {
              const line = lines.get(p.key);
              return (
                <Fragment key={p.key}>
                  <tr
                    className={line ? "cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50" : ""}
                    onClick={() => line && setOpen(open === p.key ? null : p.key)}
                  >
                    <td className="td font-mono text-xs text-slate-400">{p.item}</td>
                    <td className="td">
                      <div>{p.name}</div>
                      <div className="text-[11px] text-slate-400">
                        {p.category}
                        {p.make_or_buy === "make" && " · custom (make)"} · {p.used_in.join(", ")}
                      </div>
                    </td>
                    <td className="td">
                      <div>{p.manufacturer ?? "—"}</div>
                      {p.part_number && <div className="font-mono text-xs text-slate-500">{p.part_number}</div>}
                    </td>
                    <td className="td">{p.quantity_in_machine}</td>
                    <td className="td">
                      {p.recommended_spares || "—"}
                      {p.wear_part && <span className="ml-1 rounded bg-orange-100 px-1 text-[11px] text-orange-800">wear</span>}
                    </td>
                    <td className="td">
                      <span className={`rounded px-1.5 text-xs ${CRIT_STYLE[p.criticality]}`}>{p.criticality}</span>
                    </td>
                    {report && (
                      <td className="td">
                        {line?.current ? (
                          <>
                            <div>{line.current.supplier}</div>
                            <div className="text-xs text-slate-500">{money(line.current.unit_price_base, currency)}</div>
                          </>
                        ) : (
                          <span className="text-xs text-slate-400">—</span>
                        )}
                      </td>
                    )}
                    {report && (
                      <td className="td">
                        {line?.best ? (
                          <>
                            <div>{line.best.supplier}</div>
                            <div className="text-xs text-slate-500">{money(line.best.unit_price_base, currency)}</div>
                          </>
                        ) : (
                          <span className="text-xs text-slate-400">{line?.note ?? "—"}</span>
                        )}
                      </td>
                    )}
                    {report && (
                      <td className="td">
                        {line?.savings_base ? (
                          <span className={line.savings_base > 0 ? "text-emerald-600" : "text-red-600"}>
                            {money(line.savings_base, currency)}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                    )}
                  </tr>
                  {line && open === p.key && (
                    <tr>
                      <td colSpan={9} className="p-0">
                        <OffersTable line={line} currency={currency} />
                        {line.note && line.offers.length > 0 && (
                          <p className="px-3 py-1 text-xs text-orange-600">{line.note}</p>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
