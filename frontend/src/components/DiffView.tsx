import { useEffect, useState } from "react";
import { api } from "../api";
import type { DesignDiff, FieldChange } from "../types";

const BADGE = {
  added: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  removed: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  modified: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
};

function Fields({ fields }: { fields: FieldChange[] }) {
  if (fields.length === 0) return null;
  return (
    <ul className="mt-0.5 space-y-0.5 text-xs text-slate-600 dark:text-slate-300">
      {fields.map((f) => (
        <li key={f.field}>
          <span className="text-slate-400">{f.field.replace(/_/g, " ")}:</span>{" "}
          <span className="text-red-600 line-through decoration-red-400/60">{f.before ?? "—"}</span>{" → "}
          <span className="text-emerald-700 dark:text-emerald-400">{f.after ?? "—"}</span>
        </li>
      ))}
    </ul>
  );
}

export default function DiffView({ projectId, from, to }: { projectId: string; from: number; to: number }) {
  const [diff, setDiff] = useState<DesignDiff | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let obsolete = false;
    setDiff(null);
    setError(null);
    api.diff(projectId, from, to)
      .then((next) => { if (!obsolete) setDiff(next); })
      .catch((e: Error) => { if (!obsolete) setError(e.message); });
    // Responses can arrive after the engineer selects a different pair of revisions.
    return () => { obsolete = true; };
  }, [projectId, from, to]);

  if (error) return <p className="text-xs text-red-600">{error}</p>;
  if (!diff) return <p className="text-xs text-slate-500">Comparing…</p>;
  const empty = !diff.machine.length && !diff.lists.length && !diff.stations.length && !diff.components.length;
  if (empty) return <p className="text-xs text-slate-500">No changes between r{from} and r{to}.</p>;

  const c = diff.counts;
  const summary = [
    c.stations_added && `+${c.stations_added} station${c.stations_added > 1 ? "s" : ""}`,
    c.stations_removed && `−${c.stations_removed} station${c.stations_removed > 1 ? "s" : ""}`,
    c.components_added && `+${c.components_added} component${c.components_added > 1 ? "s" : ""}`,
    c.components_removed && `−${c.components_removed} component${c.components_removed > 1 ? "s" : ""}`,
    c.components_modified && `${c.components_modified} component${c.components_modified > 1 ? "s" : ""} changed`,
  ].filter(Boolean);

  return (
    <div className="space-y-3 text-sm">
      <div className="text-xs text-slate-500">
        r{diff.from_revision} → r{diff.to_revision}
        {summary.length > 0 && ` · ${summary.join(" · ")}`}
      </div>
      {(diff.machine.length > 0 || diff.lists.length > 0) && (
        <div>
          <h4 className="mb-1 text-xs font-semibold text-slate-500 uppercase">Machine</h4>
          <Fields fields={diff.machine} />
          {diff.lists.map((l) => (
            <div key={l.field} className="mt-1 text-xs">
              <span className="text-slate-400">{l.field.replace(/_/g, " ")}:</span>
              {l.added.map((x) => (
                <div key={`+${x}`} className="text-emerald-700 dark:text-emerald-400">+ {x}</div>
              ))}
              {l.removed.map((x) => (
                <div key={`-${x}`} className="text-red-600">− {x}</div>
              ))}
            </div>
          ))}
        </div>
      )}
      {diff.stations.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-semibold text-slate-500 uppercase">Stations</h4>
          <ul className="space-y-1.5">
            {diff.stations.map((s) => (
              <li key={s.station_id}>
                <span className={`mr-2 rounded px-1.5 py-0.5 text-[11px] ${BADGE[s.change]}`}>{s.change}</span>
                {s.name}
                <Fields fields={s.fields} />
              </li>
            ))}
          </ul>
        </div>
      )}
      {diff.components.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-semibold text-slate-500 uppercase">Components</h4>
          <ul className="space-y-1.5">
            {diff.components.map((comp) => (
              <li key={comp.component_id}>
                <span className={`mr-2 rounded px-1.5 py-0.5 text-[11px] ${BADGE[comp.change]}`}>{comp.change}</span>
                {comp.name} <span className="text-xs text-slate-400">· {comp.station}</span>
                <Fields fields={comp.fields} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
