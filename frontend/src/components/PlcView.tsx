import { useEffect, useState } from "react";
import { api } from "../api";
import type { PlcProject } from "../types";

export default function PlcView({ projectId, revision }: { projectId: string; revision: number }) {
  const [project, setProject] = useState<PlcProject | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setProject(null);
    api
      .plc(projectId, revision)
      .then((p) => {
        setProject(p);
        setSelected((current) => (current && p.files.some((f) => f.name === current) ? current : p.files[4]?.name ?? p.files[0]?.name));
      })
      .catch((e: Error) => setError(e.message));
  }, [projectId, revision]);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!project) return <p className="text-sm text-slate-500">Generating the PLC skeleton…</p>;
  const file = project.files.find((f) => f.name === selected) ?? project.files[0];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold tracking-tight">PLC skeleton · IEC 61131-3 Structured Text</h1>
          <p className="text-sm text-slate-500">
            PackML state machine per station, step sequences for the actuators, one variable per estimated I/O point.
          </p>
        </div>
        <div className="flex gap-2">
          <a className="btn-primary" href={api.plcFileUrl(projectId, revision, "zip")}>
            Download .zip
          </a>
          <a className="btn-secondary" href={api.plcFileUrl(projectId, revision, "xml")}>
            PLCopen XML
          </a>
        </div>
      </div>

      <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
        {project.warnings.map((w) => (
          <div key={w}>{w}</div>
        ))}
        <div className="mt-1 text-xs opacity-80">
          The PLCopen XML follows the TC6 v2.01 schema (CODESYS-based IDEs, TwinCAT). Import into a real project has not
          been tested yet. Siemens TIA needs SCL and isn't generated.
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {Object.entries(project.io_counts).map(([kind, n]) => (
          <span key={kind} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs dark:bg-slate-800">
            {kind}: <strong>{n}</strong>
          </span>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[230px_1fr]">
        <ul className="card h-fit divide-y divide-slate-100 overflow-hidden text-sm dark:divide-slate-800">
          {project.files.map((f) => (
            <li key={f.name}>
              <button
                className={`w-full px-3 py-2 text-left font-mono text-xs ${
                  f.name === file?.name ? "bg-amber-100 dark:bg-amber-900/40" : "hover:bg-slate-50 dark:hover:bg-slate-800"
                }`}
                onClick={() => setSelected(f.name)}
              >
                {f.name}
              </button>
            </li>
          ))}
        </ul>
        {file && (
          <pre className="card max-h-[640px] overflow-auto p-4 font-mono text-xs leading-relaxed whitespace-pre text-slate-800 dark:text-slate-200">
            {file.content}
          </pre>
        )}
      </div>
    </div>
  );
}
