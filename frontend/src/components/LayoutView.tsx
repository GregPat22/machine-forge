import { lazy, Suspense, useEffect, useState } from "react";
import { api } from "../api";
import type { Layout, MachineDesign } from "../types";

const Layout3D = lazy(() => import("./Layout3D"));
const MachineRender = lazy(() => import("./MachineRender"));

type Mode = "realistic" | "concept" | "top";
const MODES: [Mode, string][] = [
  ["realistic", "Realistic 3D"],
  ["concept", "Concept 3D"],
  ["top", "Top view 2D"],
];

function storedMode(): Mode {
  try {
    const value = localStorage.getItem("mf.layoutMode");
    return MODES.some(([m]) => m === value) ? (value as Mode) : "realistic";
  } catch {
    return "realistic";
  }
}

interface Props {
  projectId: string;
  revision: number;
  design: MachineDesign;
}

export default function LayoutView({ projectId, revision, design }: Props) {
  const [layout, setLayout] = useState<Layout | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>(storedMode);

  useEffect(() => {
    setLayout(null);
    api.layout(projectId, revision).then(setLayout).catch((e: Error) => setError(e.message));
  }, [projectId, revision]);

  function choose(next: Mode) {
    setMode(next);
    try {
      localStorage.setItem("mf.layoutMode", next);
    } catch {
      // not remembered
    }
  }

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  const loading = <p className="text-sm text-slate-500">Loading the layout…</p>;
  if (!layout) return loading;
  if (layout.boxes.length === 0) return <p className="text-sm text-slate-500">The design has no stations yet.</p>;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-md border border-slate-300 p-0.5 dark:border-slate-700">
          {MODES.map(([key, label]) => (
            <button
              key={key}
              onClick={() => choose(key)}
              className={`rounded px-3 py-1 text-sm ${mode === key ? "bg-amber-500 font-medium text-slate-950" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"}`}
            >
              {label}
            </button>
          ))}
        </div>
        <span className="text-xs text-slate-500">
          ≈ {(layout.footprint_length_mm / 1000).toFixed(1)} m × {(layout.footprint_width_mm / 1000).toFixed(1)} m ·{" "}
          {layout.style === "u_shape" ? "U-shape" : "inline"}
        </span>
        <div className="ml-auto flex gap-2">
          <a className="btn-secondary" href={api.layoutFileUrl(projectId, revision, "svg")} download>
            Top view (SVG)
          </a>
          <a className="btn-secondary" href={api.layoutFileUrl(projectId, revision, "dxf")}>
            DXF for CAD
          </a>
        </div>
      </div>

      {mode === "top" ? (
        <div className="card overflow-auto bg-white p-2">
          <img src={api.layoutFileUrl(projectId, revision, "svg")} alt="Top view of the layout" className="mx-auto max-h-[620px] w-full" />
        </div>
      ) : (
        <Suspense fallback={loading}>
          {mode === "realistic" ? <MachineRender layout={layout} design={design} /> : <Layout3D layout={layout} design={design} />}
        </Suspense>
      )}
    </div>
  );
}
