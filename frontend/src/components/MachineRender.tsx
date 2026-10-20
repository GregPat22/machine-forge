// Realistic render of the machine: procedural models, brushed-steel materials, studio lighting,
// soft shadows and a glossy floor. Loaded lazily together with three.js.
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { Reflector } from "three/examples/jsm/objects/Reflector.js";
import { CSS2DRenderer } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import { buildMachine, type MachineScene } from "../render/machine";
import { createMaterials, disposeMaterials, type Materials } from "../render/materials";
import type { Layout, MachineDesign } from "../types";

const BACKGROUND = 0xf2f3f5;
const DEFAULT_ACCENT = "#f59e0b";
const FLOOR_FADE = 0.9; // opacity of the layer over the mirror: higher = subtler reflection

function stored(key: string, fallback: string): string {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function store(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // private mode / blocked storage: the setting just isn't remembered
  }
}

interface Props {
  layout: Layout;
  design: MachineDesign;
}

export default function MachineRender({ layout, design }: Props) {
  const mount = useRef<HTMLDivElement>(null);
  const machineRef = useRef<MachineScene | null>(null);
  const materialsRef = useRef<Materials | null>(null);
  const reflectorRef = useRef<THREE.Object3D | null>(null);
  const fadeRef = useRef<THREE.MeshStandardMaterial | null>(null);
  const highlightRef = useRef<THREE.LineSegments | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const actions = useRef({ reset: () => undefined as void, snapshot: () => undefined as void });
  const animateRef = useRef(true);

  const [selected, setSelected] = useState<string | null>(null);
  const [guards, setGuards] = useState(true);
  const [labels, setLabels] = useState(false);
  const [reflections, setReflections] = useState(true);
  const [animate, setAnimate] = useState(true);
  const [accent, setAccent] = useState(() => stored("mf.accent", DEFAULT_ACCENT));

  useEffect(() => {
    const el = mount.current;
    if (!el) return;
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(el.clientWidth, el.clientHeight);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    el.appendChild(renderer.domElement);

    const labelRenderer = new CSS2DRenderer();
    labelRenderer.setSize(el.clientWidth, el.clientHeight);
    Object.assign(labelRenderer.domElement.style, { position: "absolute", top: "0", left: "0", pointerEvents: "none" });
    el.appendChild(labelRenderer.domElement);

    const scene = new THREE.Scene();
    sceneRef.current = scene;
    scene.background = new THREE.Color(BACKGROUND);
    const pmrem = new THREE.PMREMGenerator(renderer);
    const environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = environment;
    scene.environmentIntensity = 0.9;

    const materials = createMaterials(stored("mf.accent", DEFAULT_ACCENT));
    materialsRef.current = materials;
    const machine = buildMachine(layout, design, materials);
    machineRef.current = machine;
    scene.add(machine.group);

    // Framing.
    const bounds = new THREE.Box3().setFromObject(machine.group);
    const center = bounds.isEmpty() ? new THREE.Vector3(0, 1, 0) : bounds.getCenter(new THREE.Vector3());
    const sphere = bounds.isEmpty() ? new THREE.Sphere(center, 3) : bounds.getBoundingSphere(new THREE.Sphere());
    const span = Math.max(sphere.radius * 2, 3);
    scene.fog = new THREE.Fog(BACKGROUND, span * 1.6, span * 4.5);

    // Glossy studio floor: a mirror, a translucent fade layer on top, and a shadow catcher.
    const floorSize = span * 12;
    const reflector = new Reflector(new THREE.PlaneGeometry(floorSize, floorSize), {
      color: 0x6f747b,
      textureWidth: el.clientWidth * Math.min(window.devicePixelRatio, 2),
      textureHeight: el.clientHeight * Math.min(window.devicePixelRatio, 2),
    });
    reflector.rotation.x = -Math.PI / 2;
    reflector.position.set(center.x, -0.002, center.z);
    scene.add(reflector);
    reflectorRef.current = reflector;
    const fadeMaterial = new THREE.MeshStandardMaterial({ color: BACKGROUND, roughness: 1, transparent: true, opacity: FLOOR_FADE });
    fadeRef.current = fadeMaterial;
    const fade = new THREE.Mesh(new THREE.PlaneGeometry(floorSize, floorSize), fadeMaterial);
    fade.rotation.x = -Math.PI / 2;
    fade.position.set(center.x, -0.001, center.z);
    scene.add(fade);
    const shadowCatcher = new THREE.Mesh(new THREE.PlaneGeometry(floorSize, floorSize), new THREE.ShadowMaterial({ opacity: 0.22 }));
    shadowCatcher.rotation.x = -Math.PI / 2;
    shadowCatcher.position.set(center.x, 0, center.z);
    shadowCatcher.receiveShadow = true;
    scene.add(shadowCatcher);

    // Lights: soft sky, a shadow-casting key light from the front-left, a fill from the right.
    scene.add(new THREE.HemisphereLight(0xffffff, 0xd4d8de, 0.55));
    const key = new THREE.DirectionalLight(0xffffff, 2.1);
    key.position.set(center.x - span * 0.55, span * 1.1, center.z + span * 0.9);
    key.target.position.copy(center);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    const sc = key.shadow.camera;
    sc.left = sc.bottom = -span * 0.75;
    sc.right = sc.top = span * 0.75;
    sc.near = 0.1;
    sc.far = span * 4;
    key.shadow.bias = -0.0004;
    key.shadow.normalBias = 0.02;
    scene.add(key, key.target);
    const fill = new THREE.DirectionalLight(0xffffff, 0.6);
    fill.position.set(center.x + span, span * 0.6, center.z - span * 0.3);
    scene.add(fill);

    const camera = new THREE.PerspectiveCamera(35, el.clientWidth / el.clientHeight, 0.05, span * 20);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.maxPolarAngle = Math.PI / 2 - 0.03;
    controls.minDistance = 0.5;
    controls.maxDistance = span * 6;
    const viewDir = new THREE.Vector3(-0.42, 0.2, 1).normalize();
    /** Point the camera at a box so that its corners fill `fill` of the view. */
    const frame = (box: THREE.Box3, fill = 0.9) => {
      if (box.isEmpty()) return;
      const target = box.getCenter(new THREE.Vector3());
      const corners = [0, 1, 2, 3, 4, 5, 6, 7].map((i) => new THREE.Vector3(
        i & 1 ? box.max.x : box.min.x, i & 2 ? box.max.y : box.min.y, i & 4 ? box.max.z : box.min.z));
      // Start from the bounding sphere, then tighten using the projected corners.
      const vFov = THREE.MathUtils.degToRad(camera.fov);
      const hFov = 2 * Math.atan(Math.tan(vFov / 2) * camera.aspect);
      let distance = box.getBoundingSphere(new THREE.Sphere()).radius / Math.sin(Math.min(vFov, hFov) / 2);
      for (let i = 0; i < 6; i++) {
        camera.position.copy(target).addScaledVector(viewDir, distance);
        camera.lookAt(target);
        camera.updateMatrixWorld();
        const extent = Math.max(...corners.map((c) => {
          const p = c.clone().project(camera);
          return Math.max(Math.abs(p.x), Math.abs(p.y));
        }));
        distance *= extent / fill;
      }
      controls.target.copy(target);
      camera.position.copy(target).addScaledVector(viewDir, distance);
      controls.update();
    };
    actions.current.reset = () => frame(bounds);
    const focusStation = (id: string) => {
      const box = machine.stationBounds.get(id);
      if (!box) return false;
      frame(box, 0.8);
      setSelected(id);
      return true;
    };
    // A link can open the view on one station: ?tab=layout&focus=<station id>
    const initialFocus = new URLSearchParams(window.location.search).get("focus");
    if (!initialFocus || !focusStation(initialFocus)) actions.current.reset();
    actions.current.snapshot = () => {
      renderer.render(scene, camera);
      const link = document.createElement("a");
      link.download = `${design.name.replace(/[^\w-]+/g, "_")}.png`;
      link.href = renderer.domElement.toDataURL("image/png");
      link.click();
    };

    // Click (without dragging) selects a station.
    const raycaster = new THREE.Raycaster();
    let down = { x: 0, y: 0 };
    const onDown = (e: PointerEvent) => (down = { x: e.clientX, y: e.clientY });
    const onUp = (e: PointerEvent) => {
      if (Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) return;
      setSelected(pick(e) ?? null);
    };
    const pick = (e: MouseEvent): string | undefined => {
      const rect = renderer.domElement.getBoundingClientRect();
      const pointer = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(machine.pickables.filter((p) => p.visible), false)[0];
      return hit?.object.userData.stationId as string | undefined;
    };
    // Double-click zooms to a station; double-click on empty space shows the whole machine.
    const onDouble = (e: MouseEvent) => {
      const id = pick(e);
      if (!id || !focusStation(id)) actions.current.reset();
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);
    renderer.domElement.addEventListener("dblclick", onDouble);

    const resize = new ResizeObserver(() => {
      const { clientWidth: w, clientHeight: h } = el;
      if (!w || !h) return;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      labelRenderer.setSize(w, h);
    });
    resize.observe(el);

    const clock = new THREE.Clock();
    renderer.setAnimationLoop(() => {
      const dt = Math.min(clock.getDelta(), 0.1);
      if (animateRef.current) machine.update(dt);
      controls.update();
      renderer.render(scene, camera);
      labelRenderer.render(scene, camera);
    });

    return () => {
      renderer.setAnimationLoop(null);
      resize.disconnect();
      controls.dispose();
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      renderer.domElement.removeEventListener("dblclick", onDouble);
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh || obj instanceof THREE.LineSegments || obj instanceof THREE.Line) {
          obj.geometry.dispose();
        }
      });
      reflector.dispose();
      fadeMaterial.dispose();
      (shadowCatcher.material as THREE.Material).dispose();
      machine.textures.forEach((t) => t.dispose());
      disposeMaterials(materials);
      environment.dispose();
      pmrem.dispose();
      renderer.dispose();
      el.removeChild(renderer.domElement);
      el.removeChild(labelRenderer.domElement);
      machineRef.current = null;
      materialsRef.current = null;
      highlightRef.current = null;
      sceneRef.current = null;
    };
    // The scene is rebuilt only when the layout (or the design it reads) changes.
  }, [layout, design]);

  useEffect(() => {
    machineRef.current?.guards.forEach((g) => (g.visible = guards));
  }, [guards, layout, design]);

  useEffect(() => {
    machineRef.current?.labels.forEach((l) => (l.visible = labels));
  }, [labels, layout, design]);

  useEffect(() => {
    if (reflectorRef.current) reflectorRef.current.visible = reflections;
    if (fadeRef.current) fadeRef.current.opacity = reflections ? FLOOR_FADE : 1;
  }, [reflections, layout, design]);

  useEffect(() => {
    animateRef.current = animate;
  }, [animate]);

  useEffect(() => {
    materialsRef.current?.accent.color.set(accent);
    store("mf.accent", accent);
  }, [accent, layout, design]);

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    if (highlightRef.current) {
      scene.remove(highlightRef.current);
      highlightRef.current.geometry.dispose();
      highlightRef.current = null;
    }
    const box = selected ? machineRef.current?.stationBounds.get(selected) : undefined;
    if (box && materialsRef.current) {
      const size = box.getSize(new THREE.Vector3());
      const lines = new THREE.LineSegments(
        new THREE.EdgesGeometry(new THREE.BoxGeometry(size.x + 0.04, size.y + 0.04, size.z + 0.04)),
        materialsRef.current.highlight,
      );
      lines.position.copy(box.getCenter(new THREE.Vector3()));
      scene.add(lines);
      highlightRef.current = lines;
    }
  }, [selected, layout, design]);

  const station = design.stations.find((s) => s.id === selected) ?? null;
  const toggle = (label: string, value: boolean, set: (v: boolean) => void) => (
    <label className="flex items-center gap-1.5 rounded bg-white/90 px-2 py-1 text-xs text-slate-700 shadow-sm">
      <input type="checkbox" checked={value} onChange={(e) => set(e.target.checked)} />
      {label}
    </label>
  );

  return (
    <div className="card relative h-[640px] overflow-hidden">
      <div ref={mount} className="absolute inset-0" />
      <div className="absolute top-3 right-3 left-3 flex flex-wrap justify-end gap-1.5">
          {toggle("Guards", guards, setGuards)}
          {toggle("Labels", labels, setLabels)}
          {toggle("Reflections", reflections, setReflections)}
          {toggle("Animate", animate, setAnimate)}
          <label className="flex items-center gap-1.5 rounded bg-white/90 px-2 py-1 text-xs text-slate-700 shadow-sm" title="Accent stripe colour">
            Accent
            <input type="color" value={accent} onChange={(e) => setAccent(e.target.value)} className="h-4 w-6 cursor-pointer border-0 bg-transparent p-0" />
          </label>
          <button className="rounded bg-white/90 px-2 py-1 text-xs text-slate-700 shadow-sm hover:bg-white" onClick={() => actions.current.reset()}>
            Reset view
          </button>
          <button className="rounded bg-white/90 px-2 py-1 text-xs text-slate-700 shadow-sm hover:bg-white" onClick={() => actions.current.snapshot()}>
            Save image
          </button>
      </div>

      {station && (
        <aside className="absolute top-14 left-3 max-h-[calc(100%-6rem)] w-72 overflow-y-auto rounded-lg bg-white/95 p-3 text-sm text-slate-800 shadow-lg">
          <div className="flex items-start gap-2">
            <div className="min-w-0 flex-1">
              <div className="text-[11px] text-slate-500 uppercase">{station.kind}</div>
              <h3 className="font-semibold">{station.name}</h3>
            </div>
            <button className="text-slate-400 hover:text-slate-700" onClick={() => setSelected(null)} aria-label="Close">
              ✕
            </button>
          </div>
          <p className="mt-1 text-xs text-slate-600">{station.function}</p>
          <ul className="mt-2 space-y-0.5 text-xs">
            {station.components.map((c) => (
              <li key={c.id}>
                {c.quantity} × {c.name}
                {c.manufacturer && <span className="text-slate-400"> · {c.manufacturer}</span>}
              </li>
            ))}
          </ul>
        </aside>
      )}

      <div className="pointer-events-none absolute bottom-3 left-3 rounded bg-white/80 px-2 py-1 text-[11px] text-slate-600">
        Procedural render from the design, not engineering geometry · drag to orbit · scroll to zoom · click a station,
        double-click to zoom to it
      </div>
    </div>
  );
}
