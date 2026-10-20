// Concept 3D layout rendered with three.js. Loaded lazily (three.js is large).
// Backend coordinates are mm: x along the flow, y across (+y = operator side), z up.
// three.js is y-up, so (x, y, z) mm -> (x, z, y) m; the operator side faces the camera.
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { CSS2DObject, CSS2DRenderer } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import type { Layout, MachineDesign } from "../types";

const COLORS: Record<string, number> = {
  process: 0xf59e0b,
  transport: 0x94a3b8,
  inspection: 0x38bdf8,
  control: 0x64748b,
  utility: 0x14b8a6,
  base: 0x334155,
  guard: 0x93c5fd,
};
const LEGEND: [string, string][] = [
  ["process", "Process"],
  ["transport", "Transport"],
  ["inspection", "Inspection"],
  ["control", "Control"],
  ["utility", "Utility"],
  ["guard", "Guarding"],
];
const SELECTED_EMISSIVE = 0x7c2d12;

const toThree = (x: number, y: number, z: number) => new THREE.Vector3(x / 1000, z / 1000, y / 1000);

interface Props {
  layout: Layout;
  design: MachineDesign;
}

export default function Layout3D({ layout, design }: Props) {
  const mount = useRef<HTMLDivElement>(null);
  const guard = useRef<THREE.Object3D | null>(null);
  const meshes = useRef(new Map<string, THREE.Mesh>());
  const resetView = useRef<() => void>(() => undefined);
  const [showGuards, setShowGuards] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    const el = mount.current;
    if (!el) return;
    const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(dark ? 0x0f172a : 0xf1f5f9);

    const camera = new THREE.PerspectiveCamera(45, el.clientWidth / el.clientHeight, 0.1, 500);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(el.clientWidth, el.clientHeight);
    el.appendChild(renderer.domElement);

    const labels = new CSS2DRenderer();
    labels.setSize(el.clientWidth, el.clientHeight);
    Object.assign(labels.domElement.style, { position: "absolute", top: "0", left: "0", pointerEvents: "none" });
    el.appendChild(labels.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    scene.add(new THREE.HemisphereLight(0xffffff, 0x475569, 1.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(-6, 12, 9);
    scene.add(sun);

    // Boxes.
    meshes.current.clear();
    const pickable: THREE.Mesh[] = [];
    for (const box of layout.boxes) {
      const geometry = new THREE.BoxGeometry(box.length / 1000, box.height / 1000, box.width / 1000);
      const isGuard = box.kind === "guard";
      const material = new THREE.MeshStandardMaterial({
        color: COLORS[box.kind] ?? 0xa3a3a3,
        roughness: 0.65,
        metalness: 0.1,
        transparent: isGuard,
        opacity: isGuard ? 0.1 : 1,
        depthWrite: !isGuard,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.copy(toThree(box.x, box.y, box.z));
      mesh.userData = { stationId: box.station_id };
      const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(geometry),
        new THREE.LineBasicMaterial({ color: isGuard ? 0x60a5fa : 0x0f172a, transparent: true, opacity: isGuard ? 0.8 : 0.35 }),
      );
      mesh.add(edges);
      scene.add(mesh);

      if (isGuard) {
        guard.current = mesh;
        continue;
      }
      if (box.kind !== "base") {
        pickable.push(mesh);
        if (box.station_id) meshes.current.set(box.station_id, mesh);
        const tag = document.createElement("div");
        tag.className = "rounded bg-slate-900/85 px-1.5 py-0.5 text-[11px] whitespace-nowrap text-white";
        tag.textContent = box.sequence ? `${box.sequence}. ${box.label}` : box.label;
        const label = new CSS2DObject(tag);
        label.position.set(0, box.height / 2000 + 0.2, 0);
        mesh.add(label);
      }
    }

    // Product flow line with an arrow head.
    if (layout.flow.length >= 2) {
      const points = layout.flow.map(([x, y, z]) => toThree(x, y, z));
      scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), new THREE.LineBasicMaterial({ color: 0xea580c })));
      const [a, b] = points.slice(-2);
      const arrow = new THREE.Mesh(new THREE.ConeGeometry(0.08, 0.25, 16), new THREE.MeshBasicMaterial({ color: 0xea580c }));
      arrow.position.copy(b);
      arrow.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize());
      scene.add(arrow);
    }

    // Floor grid (1 m cells) and camera framing.
    const bounds = new THREE.Box3();
    for (const box of layout.boxes) {
      bounds.expandByPoint(toThree(box.x - box.length / 2, box.y - box.width / 2, 0));
      bounds.expandByPoint(toThree(box.x + box.length / 2, box.y + box.width / 2, box.height));
    }
    const center = bounds.isEmpty() ? new THREE.Vector3() : bounds.getCenter(new THREE.Vector3());
    const span = bounds.isEmpty() ? 6 : Math.max(bounds.max.x - bounds.min.x, bounds.max.z - bounds.min.z, 3);
    const gridSize = Math.ceil(span) + 4;
    const grid = new THREE.GridHelper(gridSize, gridSize, dark ? 0x334155 : 0xcbd5e1, dark ? 0x1e293b : 0xe2e8f0);
    grid.position.set(center.x, 0, center.z);
    scene.add(grid);

    // Frame the whole machine: fit its bounding sphere in the narrower of the two fields of view.
    const radius = bounds.isEmpty() ? 4 : bounds.getBoundingSphere(new THREE.Sphere()).radius;
    const viewDir = new THREE.Vector3(-0.45, 0.6, 1).normalize();
    resetView.current = () => {
      const vFov = THREE.MathUtils.degToRad(camera.fov);
      const hFov = 2 * Math.atan(Math.tan(vFov / 2) * camera.aspect);
      const distance = (radius / Math.sin(Math.min(vFov, hFov) / 2)) * 1.05;
      camera.position.copy(center).addScaledVector(viewDir, distance);
      controls.target.copy(center);
      controls.update();
    };
    resetView.current();

    // Click (without dragging) selects a station.
    const raycaster = new THREE.Raycaster();
    let down = { x: 0, y: 0 };
    const onDown = (e: PointerEvent) => (down = { x: e.clientX, y: e.clientY });
    const onUp = (e: PointerEvent) => {
      if (Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) return;
      const rect = renderer.domElement.getBoundingClientRect();
      const pointer = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(pickable, false)[0];
      setSelected((hit?.object.userData.stationId as string | undefined) ?? null);
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);

    const resize = new ResizeObserver(() => {
      const { clientWidth: w, clientHeight: h } = el;
      if (!w || !h) return;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      labels.setSize(w, h);
    });
    resize.observe(el);

    renderer.setAnimationLoop(() => {
      controls.update();
      renderer.render(scene, camera);
      labels.render(scene, camera);
    });

    return () => {
      renderer.setAnimationLoop(null);
      resize.disconnect();
      controls.dispose();
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh || obj instanceof THREE.Line || obj instanceof THREE.LineSegments) {
          obj.geometry.dispose();
          (Array.isArray(obj.material) ? obj.material : [obj.material]).forEach((m) => m.dispose());
        }
      });
      renderer.dispose();
      el.removeChild(renderer.domElement);
      el.removeChild(labels.domElement);
      guard.current = null;
    };
  }, [layout]);

  useEffect(() => {
    if (guard.current) guard.current.visible = showGuards;
  }, [showGuards, layout]);

  useEffect(() => {
    for (const [id, mesh] of meshes.current) {
      (mesh.material as THREE.MeshStandardMaterial).emissive.setHex(id === selected ? SELECTED_EMISSIVE : 0x000000);
    }
  }, [selected, layout]);

  const station = design.stations.find((s) => s.id === selected) ?? null;

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_280px]">
      <div className="card relative h-[560px] overflow-hidden">
        <div ref={mount} className="absolute inset-0" />
        <div className="pointer-events-none absolute top-3 left-3 rounded bg-white/85 px-2 py-1 text-xs text-slate-700 dark:bg-slate-900/85 dark:text-slate-200">
          Concept layout · ≈ {(layout.footprint_length_mm / 1000).toFixed(1)} m × {(layout.footprint_width_mm / 1000).toFixed(1)} m ·{" "}
          {layout.style === "u_shape" ? "U-shape" : "Inline"}
        </div>
        <div className="absolute top-3 right-3 flex gap-2">
          <label className="flex items-center gap-1.5 rounded bg-white/85 px-2 py-1 text-xs dark:bg-slate-900/85">
            <input type="checkbox" checked={showGuards} onChange={(e) => setShowGuards(e.target.checked)} />
            Guards
          </label>
          <button className="rounded bg-white/85 px-2 py-1 text-xs hover:bg-white dark:bg-slate-900/85" onClick={() => resetView.current()}>
            Reset view
          </button>
        </div>
        <div className="pointer-events-none absolute bottom-3 left-3 text-[11px] text-slate-500">
          Drag to orbit · scroll to zoom · right-drag to pan · click a station
        </div>
      </div>

      <aside className="card p-4 text-sm">
        {station ? (
          <>
            <div className="text-xs text-slate-500 uppercase">{station.kind}</div>
            <h3 className="font-semibold">{station.name}</h3>
            <p className="mt-1 text-slate-600 dark:text-slate-300">{station.function}</p>
            <dl className="mt-3 grid grid-cols-2 gap-1 text-xs">
              <dt className="text-slate-500">Envelope</dt>
              <dd>
                {station.length_mm && station.width_mm && station.height_mm
                  ? `${station.length_mm} × ${station.width_mm} × ${station.height_mm} mm`
                  : "default size"}
              </dd>
              <dt className="text-slate-500">Cycle time</dt>
              <dd>{station.cycle_time_s ? `${station.cycle_time_s} s` : "—"}</dd>
            </dl>
            <h4 className="mt-3 mb-1 text-xs font-semibold text-slate-500 uppercase">Components</h4>
            <ul className="space-y-0.5">
              {station.components.map((c) => (
                <li key={c.id}>
                  {c.quantity} × {c.name}
                  {c.manufacturer && <span className="text-slate-400"> · {c.manufacturer}</span>}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <>
            <h3 className="mb-2 font-semibold">Legend</h3>
            <ul className="space-y-1">
              {LEGEND.map(([kind, label]) => (
                <li key={kind} className="flex items-center gap-2">
                  <span className="h-3 w-3 rounded-sm" style={{ background: `#${COLORS[kind].toString(16).padStart(6, "0")}` }} />
                  {label}
                </li>
              ))}
              <li className="flex items-center gap-2">
                <span className="h-0.5 w-3 bg-orange-600" /> Product flow
              </li>
            </ul>
            <p className="mt-4 text-xs text-slate-500">
              Click a station to see its components. Sizes come from the station envelopes in the design; ask in the
              chat to change them or to make the line U-shaped. This is a concept view, not engineering geometry.
            </p>
          </>
        )}
      </aside>
    </div>
  );
}
