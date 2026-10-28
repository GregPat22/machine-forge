import { useState } from "react";
import type { MachineDesign, Station } from "../types";

const KIND_LABEL: Record<Station["kind"], string> = {
  process: "Process",
  transport: "Transport",
  inspection: "Inspection",
  control: "Control",
  frame: "Frame",
  safety: "Safety",
  utility: "Utility",
};

function Kpi({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="card px-4 py-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-0.5 text-lg font-semibold">{value}</div>
    </div>
  );
}

function StationCard({ station }: { station: Station }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card">
      <button className="flex w-full items-start gap-3 px-4 py-3 text-left" onClick={() => setOpen(!open)}>
        <span className="mt-0.5 w-7 shrink-0 text-center font-mono text-xs text-slate-400">
          {station.sequence > 0 ? station.sequence : "—"}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{station.name}</span>
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              {KIND_LABEL[station.kind]}
            </span>
            {station.cycle_time_s !== null && (
              <span className="text-[11px] text-slate-500">{station.cycle_time_s} s/cycle</span>
            )}
          </div>
          <div className="mt-0.5 text-sm text-slate-500">{station.function}</div>
        </div>
        <span className="text-xs text-slate-400">
          {station.components.length} parts {open ? "▴" : "▾"}
        </span>
      </button>
      {open && (
        <div className="overflow-x-auto border-t border-slate-200 dark:border-slate-800">
          <table className="w-full">
            <thead>
              <tr>
                <th className="th">Component</th>
                <th className="th">Qty</th>
                <th className="th">Manufacturer / P/N</th>
                <th className="th">Specs</th>
                <th className="th">Spares</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {station.components.map((c) => (
                <tr key={c.id}>
                  <td className="td">
                    <div>{c.name}</div>
                    <div className="text-[11px] text-slate-400">
                      {c.category}
                      {c.make_or_buy === "make" && " · custom (make)"}
                    </div>
                  </td>
                  <td className="td">{c.quantity}</td>
                  <td className="td">
                    <div>{c.manufacturer ?? "—"}</div>
                    {c.part_number && <div className="font-mono text-xs text-slate-500">{c.part_number}</div>}
                  </td>
                  <td className="td text-xs text-slate-600 dark:text-slate-300">
                    {c.specs.map((s) => `${s.name}: ${s.value}`).join(" · ") || "—"}
                  </td>
                  <td className="td text-xs">
                    {c.wear_part && <span className="mr-1 rounded bg-orange-100 px-1 text-orange-800">wear</span>}
                    <span className="mr-1 rounded bg-slate-100 px-1 dark:bg-slate-800">{c.criticality}</span>
                    {c.recommended_spares > 0 ? `${c.recommended_spares} pcs` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function DesignView({ design, onAsk }: { design: MachineDesign; onAsk: (question: string) => void }) {
  const flow = design.stations.filter((s) => s.sequence > 0).sort((a, b) => a.sequence - b.sequence);
  const infrastructure = design.stations.filter((s) => s.sequence <= 0);
  const components = design.stations.flatMap((s) => s.components);
  const wear = components.filter((c) => c.wear_part).length;

  return (
    <div className="space-y-6">
      <div>
        <div className="text-xs font-medium tracking-wide text-amber-600 uppercase">{design.machine_type}</div>
        <h1 className="text-2xl font-semibold tracking-tight">{design.name}</h1>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{design.summary}</p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Kpi label="Throughput" value={design.target_rate_text ?? "?"} />
        <Kpi label="Stations" value={design.stations.length} />
        <Kpi label="Component lines" value={components.length} />
        <Kpi label="Wear parts" value={wear} />
      </div>

      {flow.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-500">Product flow</h2>
          <div className="flex flex-wrap items-center gap-1 text-xs">
            {flow.map((s, i) => (
              <span key={s.id} className="flex items-center gap-1">
                <span className="rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900">
                  {s.name}
                </span>
                {i < flow.length - 1 && <span className="text-slate-400">→</span>}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-2">
        <h2 className="text-sm font-semibold text-slate-500">Process stations</h2>
        {flow.map((s) => (
          <StationCard key={s.id} station={s} />
        ))}
      </div>

      {infrastructure.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-slate-500">Infrastructure</h2>
          {infrastructure.map((s) => (
            <StationCard key={s.id} station={s} />
          ))}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        <div className="card p-4">
          <h3 className="text-sm font-semibold">Open questions</h3>
          <p className="mb-2 text-[11px] text-slate-400">Click one to answer it in the chat.</p>
          <ul className="space-y-1 text-sm">
            {design.open_questions.length === 0 && <li className="text-slate-400">None</li>}
            {design.open_questions.map((q) => (
              <li key={q}>
                <button className="text-left hover:text-amber-600" onClick={() => onAsk(`${q} → `)}>
                  • {q}
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className="card p-4">
          <h3 className="mb-2 text-sm font-semibold">Assumptions</h3>
          <ul className="space-y-1 text-sm text-slate-600 dark:text-slate-300">
            {design.assumptions.map((a) => (
              <li key={a}>• {a}</li>
            ))}
          </ul>
        </div>
        <div className="card p-4">
          <h3 className="mb-2 text-sm font-semibold">Utilities</h3>
          <ul className="space-y-1 text-sm text-slate-600 dark:text-slate-300">
            {design.utilities.map((u) => (
              <li key={u}>• {u}</li>
            ))}
            {design.footprint && <li>• Footprint: {design.footprint}</li>}
          </ul>
        </div>
      </div>
    </div>
  );
}
