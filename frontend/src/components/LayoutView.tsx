import { lazy, Suspense, useEffect, useState } from "react";
import { api } from "../api";
import type { Layout, MachineDesign } from "../types";

const Layout3D = lazy(() => import("./Layout3D"));

interface Props {
  projectId: string;
  revision: number;
  design: MachineDesign;
}

export default function LayoutView({ projectId, revision, design }: Props) {
  const [layout, setLayout] = useState<Layout | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLayout(null);
    api.layout(projectId, revision).then(setLayout).catch((e: Error) => setError(e.message));
  }, [projectId, revision]);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  const loading = <p className="text-sm text-slate-500">Loading 3D layout…</p>;
  if (!layout) return loading;
  if (layout.boxes.length === 0) return <p className="text-sm text-slate-500">The design has no stations yet.</p>;
  return (
    <Suspense fallback={loading}>
      <Layout3D layout={layout} design={design} />
    </Suspense>
  );
}
