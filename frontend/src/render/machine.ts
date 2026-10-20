// Assembles a realistic-looking machine from the computed layout and the design.
// World frame: X along the flow, Y up, Z towards the operator side (layout y), metres.
import * as THREE from "three";
import { CSS2DObject } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import type { Component, Layout, LayoutBox, MachineDesign, Station } from "../types";
import { hmiScreenTexture, type Materials } from "./materials";
import { CELL, WALL_CATEGORIES, box, buildFiller, buildPart, cyl, mesh, tube } from "./parts";

export const BASE_H = 0.85; // base cabinet height = height of the product transfer
const UPPER_H = 0.4;
const MIN_PLATE_H = 0.78; // the realistic view never draws a mechanism plate lower than this
const WALL_T = 0.03;
const FEET_H = 0.05;
const MAX_ITEMS = 12;
const PRODUCT_SPACING = 0.2;
const PRODUCT_SPEED = 0.16; // m/s

const PRIORITY: Record<string, number> = {
  cutting: 0, heating: 0, sealing: 0, linear_motion: 1, vision: 1, dosing: 1, pump: 1, conveyor: 2,
  custom_part: 2, servo_motor: 2, motor: 2, transmission: 3, gearbox: 3, pneumatic_actuator: 3,
  pneumatic_valve: 3, air_treatment: 4, cooling: 4, vacuum: 4, printing_marking: 4, sensor: 5, other: 6,
};

export interface MachineScene {
  group: THREE.Group;
  pickables: THREE.Mesh[];
  stationBounds: Map<string, THREE.Box3>;
  guards: THREE.Object3D[];
  labels: CSS2DObject[];
  textures: THREE.Texture[];
  update(dt: number): void;
}

const v3 = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);

function label(text: string, y: number): CSS2DObject {
  const el = document.createElement("div");
  el.className = "rounded bg-slate-900/85 px-1.5 py-0.5 text-[11px] whitespace-nowrap text-white";
  el.textContent = text;
  const obj = new CSS2DObject(el);
  obj.position.set(0, y, 0);
  obj.visible = false;
  return obj;
}

function handle(g: THREE.Group, x: number, y: number, z: number, length: number, m: Materials): void {
  g.add(box(0.016, length, 0.016, m.blackPlastic, x, y, z + 0.02));
  for (const dy of [-length / 2 + 0.01, length / 2 - 0.01]) g.add(box(0.012, 0.012, 0.02, m.blackPlastic, x, y + dy, z + 0.01));
}

function feet(g: THREE.Group, L: number, W: number, m: Materials): void {
  for (const x of [-L / 2 + 0.07, L / 2 - 0.07]) {
    for (const z of [-W / 2 + 0.07, W / 2 - 0.07]) {
      g.add(cyl(0.02, 0.02, FEET_H - 0.01, m.chrome, "y", x, (FEET_H - 0.01) / 2 + 0.01, z));
      g.add(cyl(0.035, 0.035, 0.012, m.blackPlastic, "y", x, 0.006, z));
    }
  }
}

function louvres(g: THREE.Group, L: number, z: number, y0: number, count: number, m: Materials, stripe = true): void {
  for (let i = 0; i < count; i++) g.add(box(L - 0.07, 0.011, 0.014, m.slat, 0, y0 + 0.03 + i * 0.03, z + 0.007));
  if (stripe) g.add(box(L - 0.02, 0.014, 0.012, m.accent, 0, y0, z + 0.006));
}

function doors(g: THREE.Group, L: number, front: number, y0: number, y1: number, m: Materials): void {
  const mid = (y0 + y1) / 2;
  const len = Math.min(0.16, (y1 - y0) * 0.5);
  if (L > 0.75) {
    g.add(box(0.003, y1 - y0, 0.002, m.slat, 0, mid, front + 0.001));
    handle(g, -0.05, mid, front, len, m);
    handle(g, 0.05, mid, front, len, m);
  } else {
    handle(g, L / 2 - 0.08, mid, front, len, m);
  }
}

function stationText(s: Station): string {
  return `${s.name} ${s.function}`.toLowerCase();
}

// --- process / inspection station ("balcony" module) -------------------------------------------------

interface Module {
  group: THREE.Group;
  guard: THREE.Group;
  productZ: number; // local z of the product path
  H: number;
  L: number;
  W: number;
  upperFront: number;
}

function processModule(b: LayoutBox, station: Station, m: Materials, sideGuards: { left: boolean; right: boolean }): Module {
  const L = b.length / 1000;
  const W = b.width / 1000;
  const H = Math.max(b.height / 1000, BASE_H + UPPER_H + MIN_PLATE_H);
  const g = new THREE.Group();

  // Base cabinet with louvres, accent stripe and doors.
  g.add(box(L, BASE_H - FEET_H, W, m.steel, 0, FEET_H + (BASE_H - FEET_H) / 2, 0));
  feet(g, L, W, m);
  louvres(g, L, W / 2, FEET_H + 0.045, 6, m);
  doors(g, L, W / 2, FEET_H + 0.27, BASE_H - 0.04, m);
  g.add(box(L + 0.004, 0.012, W + 0.004, m.chrome, 0, BASE_H - 0.006, 0));

  // Mechanism plate and upper cabinet.
  const wallZ = -W / 2 + W * 0.32;
  const plateFront = wallZ + WALL_T / 2;
  const procTop = H - UPPER_H;
  g.add(box(L, procTop - BASE_H, WALL_T, m.plate, 0, (BASE_H + procTop) / 2, wallZ));
  const upperD = W * 0.55;
  const upperFront = -W / 2 + upperD;
  g.add(box(L, UPPER_H, upperD, m.steel, 0, procTop + UPPER_H / 2, -W / 2 + upperD / 2));
  doors(g, L, upperFront, procTop + 0.04, H - 0.04, m);
  g.add(box(L - 0.06, 0.05, 0.045, m.greyPlastic, 0, BASE_H + 0.04, plateFront + 0.0225));

  // Mechanism area, reduced by reels on the left.
  let x0 = -L / 2 + 0.06;
  const x1 = L / 2 - 0.06;
  const y0 = BASE_H + 0.1;
  const y1 = procTop - 0.05;
  const text = stationText(station);
  const reelMaterials: THREE.Material[] = [];
  if (/film|unwind|reel|web/.test(text)) reelMaterials.push(m.film);
  if (/foil|lidding|alu/.test(text)) reelMaterials.push(m.foil);
  if (/label/.test(text) && reelMaterials.length === 0) reelMaterials.push(m.whitePlastic);
  for (const mat of reelMaterials.slice(0, 2)) {
    const r = Math.min(0.22, (y1 - y0) / 2 - 0.02, L * 0.17);
    if (r < 0.08 || x1 - x0 < 2 * r + 0.25) break;
    const x = x0 + r + 0.02;
    const y = y0 + r + 0.04;
    const z = plateFront + 0.1;
    g.add(cyl(0.02, 0.02, 0.22, m.chrome, "z", x, y, plateFront + 0.11));
    g.add(cyl(r, r, 0.13, mat, "z", x, y, z, 48));
    g.add(cyl(0.045, 0.045, 0.134, m.cardboard, "z", x, y, z));
    g.add(cyl(r * 0.55, r * 0.55, 0.012, m.steelDark, "z", x, y, plateFront + 0.025));
    g.add(cyl(0.022, 0.022, 0.12, m.chrome, "z", x + r + 0.05, y0 + 0.02, z));
    g.add(box(x1 - (x + r + 0.05), 0.002, 0.11, mat, (x1 + x + r + 0.05) / 2, y0 + 0.002, z));
    x0 += 2 * r + 0.1;
  }

  const items = station.components
    .filter((c) => WALL_CATEGORIES.has(c.category))
    .sort((a, b) => (PRIORITY[a.category] ?? 6) - (PRIORITY[b.category] ?? 6))
    .slice(0, MAX_ITEMS - 1);
  // Driven stations get a main drive wheel, like the cam/drum mechanisms of real machines.
  if (station.kind === "process" && station.components.some((c) => ["servo_motor", "motor"].includes(c.category))) {
    items.splice(Math.min(1, items.length), 0, { id: "drive", name: "Drive wheel", category: "custom_part", quantity: 1, specs: [] } as unknown as Component);
  }
  if (items.length === 0) {
    items.push({ id: "placeholder", name: "Mechanism", category: "custom_part", quantity: 1, specs: [] } as unknown as Component);
  }
  const areaW = x1 - x0;
  const areaH = y1 - y0;
  // A grid of ~24 x 22 cm cells; grow it if the station has more components than cells.
  let cols = Math.max(1, Math.floor(areaW / 0.24));
  let rows = Math.max(1, Math.floor(areaH / 0.22));
  while (cols * rows < items.length) {
    if (areaW / (cols + 1) >= areaH / (rows + 1)) cols++;
    else rows++;
  }
  const cellW = areaW / cols;
  const cellH = areaH / rows;
  const k = Math.min(2.2, Math.max(0.4, (Math.min(cellW, cellH) * 0.95) / CELL));
  const ductTop = BASE_H + 0.065;
  // Guide rails across the plate, behind the mechanisms.
  for (const y of [y0 + areaH * 0.12, y1 - areaH * 0.08]) {
    g.add(cyl(0.008, 0.008, areaW, m.chrome, "x", (x0 + x1) / 2, y, plateFront + 0.025));
    for (const x of [x0 + 0.01, x1 - 0.01]) g.add(box(0.025, 0.03, 0.035, m.steelDark, x, y, plateFront + 0.0175));
  }
  // Fill the cells left over with generic hardware, so plates look as busy as real ones.
  const seed = station.id.length + station.sequence * 3;
  for (let i = items.length; i < cols * rows; i++) {
    const cx = x0 + ((i % cols) + 0.5) * cellW;
    const cy = y1 - (Math.floor(i / cols) + 0.5) * cellH;
    const filler = buildFiller(m, seed + i);
    filler.scale.setScalar(Math.min(1.3, (Math.min(cellW, cellH) * 0.9) / CELL));
    filler.position.set(cx, cy, plateFront);
    g.add(filler);
  }
  items.forEach((c, i) => {
    const cx = x0 + ((i % cols) + 0.5) * cellW;
    const cy = y1 - (Math.floor(i / cols) + 0.5) * cellH;
    const part = buildPart(c, m, i);
    part.group.scale.setScalar(k);
    part.group.position.set(cx, cy, plateFront);
    g.add(part.group);
    const start = cy - CELL * k * 0.35;
    if (start > ductTop + 0.04) {
      g.add(tube([v3(cx + 0.03, start, plateFront + 0.012), v3(cx + 0.04, (start + ductTop) / 2, plateFront + 0.02),
        v3(cx + 0.045, ductTop, plateFront + 0.03)], 0.004, part.pneumatic ? m.hoseBlue : m.cable));
    }
  });

  // Guard: aluminium profiles with glass doors, front and outer sides.
  const guard = new THREE.Group();
  const front = W / 2 - 0.015;
  const gy0 = BASE_H;
  const gy1 = procTop;
  const midY = (gy0 + gy1) / 2;
  const p = 0.03;
  const panes = L > 1.1 ? 2 : 1;
  for (let i = 0; i <= panes; i++) {
    const x = -L / 2 + p / 2 + (i * (L - p)) / panes;
    guard.add(box(p, gy1 - gy0, p, m.aluminum, x, midY, front));
  }
  guard.add(box(L, p, p, m.aluminum, 0, gy1 - p / 2, front));
  guard.add(box(L, p, p, m.aluminum, 0, gy0 + p / 2, front));
  for (let i = 0; i < panes; i++) {
    const w = (L - p) / panes - p;
    const cx = -L / 2 + p + w / 2 + (i * (L - p)) / panes;
    const pane = box(w, gy1 - gy0 - 2 * p, 0.006, m.glass, cx, midY, front);
    pane.castShadow = false;
    guard.add(pane);
    const hx = cx + (i % 2 === 0 ? w / 2 - 0.06 : -w / 2 + 0.06);
    guard.add(box(0.012, 0.2, 0.012, m.chrome, hx, midY, front + 0.035));
    for (const dy of [-0.09, 0.09]) guard.add(box(0.012, 0.012, 0.03, m.chrome, hx, midY + dy, front + 0.018));
    guard.add(box(0.025, 0.06, 0.02, m.sensorYellow, hx, gy1 - p - 0.04, front - 0.02));
  }
  for (const [side, x] of [["left", -L / 2], ["right", L / 2]] as const) {
    if (!sideGuards[side]) continue;
    const depth = front - plateFront;
    const pane = box(0.006, gy1 - gy0 - 2 * p, depth, m.glass, x, midY, plateFront + depth / 2);
    pane.castShadow = false;
    guard.add(pane);
    guard.add(box(p, p, depth, m.aluminum, x, gy1 - p / 2, plateFront + depth / 2));
  }
  g.add(guard);

  return { group: g, guard, productZ: (plateFront + W / 2) / 2, H, L, W, upperFront };
}

// --- conveyor (transport station) -------------------------------------------------------------------

function conveyorModule(b: LayoutBox, station: Station, m: Materials): { group: THREE.Group; H: number } {
  const L = b.length / 1000;
  const Wc = Math.min(b.width / 1000, 0.32);
  const g = new THREE.Group();
  const legH = BASE_H - 0.09 - FEET_H;
  for (const x of [-L / 2 + 0.08, L / 2 - 0.08]) {
    for (const z of [-Wc / 2 + 0.03, Wc / 2 - 0.03]) {
      g.add(box(0.04, legH, 0.04, m.steel, x, FEET_H + legH / 2, z));
      g.add(cyl(0.03, 0.03, FEET_H, m.blackPlastic, "y", x, FEET_H / 2, z));
    }
  }
  for (const z of [-Wc / 2 + 0.03, Wc / 2 - 0.03]) g.add(box(L - 0.16, 0.035, 0.035, m.steel, 0, 0.28, z));
  for (const z of [-(Wc / 2 + 0.0125), Wc / 2 + 0.0125]) g.add(box(L, 0.07, 0.025, m.steel, 0, BASE_H - 0.045, z));
  g.add(box(L - 0.05, 0.012, Wc, m.belt, 0, BASE_H - 0.006, 0));
  for (const x of [-(L / 2 - 0.025), L / 2 - 0.025]) g.add(cyl(0.03, 0.03, Wc, m.chrome, "z", x, BASE_H - 0.03, 0));
  for (const z of [-(Wc / 2 - 0.03), Wc / 2 - 0.03]) {
    g.add(cyl(0.006, 0.006, L - 0.06, m.chrome, "x", 0, BASE_H + 0.05, z));
    for (let x = -L / 2 + 0.1; x < L / 2 - 0.05; x += 0.4) {
      g.add(cyl(0.005, 0.005, 0.07, m.chrome, "y", x, BASE_H + 0.02, Math.sign(z) * (Wc / 2 + 0.02)));
      g.add(cyl(0.005, 0.005, 0.05, m.chrome, "z", x, BASE_H + 0.05, Math.sign(z) * (Wc / 2 - 0.005)));
    }
  }
  const motorComponent = station.components.find((c) => c.category === "motor");
  const motor = buildPart(motorComponent ?? ({ id: "m", name: "Gearmotor", category: "motor", quantity: 1 } as Component), m, 0);
  motor.group.scale.setScalar(0.9);
  motor.group.position.set(L / 2 - 0.12, BASE_H - 0.13, Wc / 2 + 0.03);
  g.add(motor.group);
  const extras = station.components.filter((c) => WALL_CATEGORIES.has(c.category) && !["motor", "conveyor"].includes(c.category)).slice(0, 3);
  extras.forEach((c, i) => {
    const part = buildPart(c, m, i + 1);
    part.group.scale.setScalar(0.75);
    part.group.position.set(-L / 2 + ((i + 1) * L) / (extras.length + 1), BASE_H + 0.1, -Wc / 2 - 0.05);
    g.add(box(0.03, 0.1, 0.03, m.steel, part.group.position.x, BASE_H + 0.02, -Wc / 2 - 0.06));
    g.add(part.group);
  });
  if (/reject/.test(stationText(station))) {
    const bx = L / 4;
    const bz = Wc / 2 + 0.22;
    g.add(box(0.3, 0.012, 0.25, m.steel, bx, 0.35, bz));
    for (const [w, d, x, z] of [[0.3, 0.012, bx, bz - 0.125], [0.3, 0.012, bx, bz + 0.125], [0.012, 0.25, bx - 0.15, bz], [0.012, 0.25, bx + 0.15, bz]] as const) {
      g.add(box(w, 0.25, d, m.steel, x, 0.47, z));
    }
    for (const x of [bx - 0.13, bx + 0.13]) g.add(box(0.025, 0.35, 0.025, m.steel, x, 0.175, bz));
  }
  return { group: g, H: BASE_H + 0.1 };
}

function transferConveyor(a: THREE.Vector3, b: THREE.Vector3, m: Materials): THREE.Group {
  const g = new THREE.Group();
  const length = a.distanceTo(b);
  const mid = a.clone().add(b).multiplyScalar(0.5);
  g.position.set(mid.x, 0, mid.z);
  g.rotation.y = -Math.atan2(b.z - a.z, b.x - a.x);
  g.add(box(length, 0.012, 0.14, m.belt, 0, BASE_H - 0.006, 0));
  for (const z of [-0.08, 0.08]) g.add(box(length, 0.06, 0.02, m.steel, 0, BASE_H - 0.04, z));
  g.add(box(0.06, BASE_H - 0.07, 0.06, m.steel, 0, (BASE_H - 0.07) / 2, 0));
  return g;
}

// --- cabinets ---------------------------------------------------------------------------------------

function cabinet(b: LayoutBox, station: Station, m: Materials): THREE.Group {
  const L = b.length / 1000;
  const W = b.width / 1000;
  const H = b.height / 1000;
  const g = new THREE.Group();
  if (station.kind === "utility") {
    g.add(box(L, H - 0.1, W, m.steelDark, 0, 0.1 + (H - 0.1) / 2, 0));
    g.add(box(L, 0.1, W - 0.02, m.slat, 0, 0.05, 0));
    const air = station.components.find((c) => c.category === "air_treatment");
    const part = buildPart(air ?? ({ id: "frl", name: "FRL", category: "air_treatment", quantity: 1 } as Component), m, 0);
    part.group.scale.setScalar(Math.min(1.5, L / CELL / 1.2));
    part.group.position.set(0, H * 0.62, W / 2);
    g.add(part.group);
    const valves = station.components.find((c) => c.category === "pneumatic_valve");
    if (valves) {
      const vt = buildPart(valves, m, 1);
      vt.group.scale.setScalar(Math.min(1.3, L / CELL / 1.3));
      vt.group.position.set(0, H * 0.3, W / 2);
      g.add(vt.group);
    }
    return g;
  }
  g.add(box(L, H - 0.1, W, m.steel, 0, 0.1 + (H - 0.1) / 2, 0));
  g.add(box(L, 0.1, W - 0.02, m.slat, 0, 0.05, 0));
  louvres(g, L, W / 2, 0.16, 4, m, false);
  louvres(g, L, W / 2, H - 0.2, 4, m, false);
  doors(g, L, W / 2, 0.35, H - 0.25, m);
  g.add(box(0.09, 0.09, 0.005, m.sensorYellow, L / 2 - 0.13, H * 0.72, W / 2 + 0.003));
  g.add(box(0.07, 0.016, 0.025, m.red, L / 2 - 0.13, H * 0.72, W / 2 + 0.018));
  if (station.components.some((c) => c.category === "cooling")) {
    g.add(box(0.06, H * 0.45, W * 0.7, m.greyPlastic, L / 2 + 0.03, H * 0.6, 0));
  }
  return g;
}

// --- HMI and stack light ------------------------------------------------------------------------------

function hmi(mod: Module, design: MachineDesign, m: Materials, textures: THREE.Texture[]): THREE.Group {
  const g = new THREE.Group();
  const { L, W, H, upperFront } = mod;
  const anchorY = H - UPPER_H * 0.45;
  const panel = v3(-L / 2 - 0.42, 1.42, W / 2 + 0.16);
  g.add(box(0.06, 0.09, 0.08, m.steel, -L / 2 - 0.03, anchorY, upperFront - 0.12));
  g.add(tube([
    v3(-L / 2 - 0.03, anchorY, upperFront - 0.12), v3(-L / 2 - 0.2, anchorY + 0.02, upperFront - 0.02),
    v3(-L / 2 - 0.38, anchorY - 0.05, W / 2 - 0.05), v3(panel.x, panel.y + 0.32, panel.z - 0.06),
    v3(panel.x, panel.y + 0.2, panel.z - 0.05),
  ], 0.024, m.chrome));
  g.add(cyl(0.035, 0.035, 0.06, m.steelDark, "y", panel.x, panel.y + 0.2, panel.z - 0.05));

  const head = new THREE.Group();
  head.position.copy(panel);
  head.rotation.set(-0.12, 0.35, 0);
  head.add(box(0.5, 0.37, 0.085, m.steel, 0, 0, 0));
  head.add(box(0.42, 0.28, 0.008, m.blackPlastic, 0, 0.03, 0.044));
  const screenTexture = hmiScreenTexture(design.name, design.stations.filter((s) => s.sequence > 0).map((s) => s.name), design.throughput);
  textures.push(screenTexture);
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(0.39, 0.245), new THREE.MeshBasicMaterial({ map: screenTexture, toneMapped: false }));
  screen.position.set(0, 0.03, 0.049);
  head.add(screen);
  head.add(cyl(0.032, 0.032, 0.008, m.sensorYellow, "z", 0.19, -0.14, 0.046));
  head.add(cyl(0.022, 0.022, 0.022, m.red, "z", 0.19, -0.14, 0.06));
  head.add(mesh(new THREE.SphereGeometry(0.022, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2), m.red, 0.19, -0.14, 0.07).rotateX(Math.PI / 2));
  for (const [x, mat] of [[-0.17, m.ledGreen], [-0.12, m.blackPlastic], [-0.07, m.whitePlastic]] as const) {
    head.add(cyl(0.013, 0.013, 0.015, mat, "z", x, -0.15, 0.05));
  }
  head.add(cyl(0.012, 0.012, 0.01, m.chrome, "z", 0.0, -0.15, 0.048));
  for (const x of [-0.27, 0.27]) head.add(box(0.016, 0.26, 0.03, m.chrome, x, 0, 0.0));
  g.add(head);
  return g;
}

function stackLight(x: number, y: number, z: number, m: Materials): THREE.Group {
  const g = new THREE.Group();
  g.position.set(x, y, z);
  g.add(cyl(0.032, 0.032, 0.03, m.darkMetal, "y", 0, 0.015, 0));
  g.add(cyl(0.011, 0.011, 0.18, m.aluminum, "y", 0, 0.12, 0));
  [m.ledGreen, m.ledAmber, m.ledRed].forEach((mat, i) => g.add(cyl(0.032, 0.032, 0.05, mat, "y", 0, 0.235 + i * 0.052, 0)));
  g.add(cyl(0.03, 0.033, 0.015, m.blackPlastic, "y", 0, 0.375, 0));
  return g;
}

// --- products ---------------------------------------------------------------------------------------

function productParts(design: MachineDesign, m: Materials): { geometry: THREE.BufferGeometry; material: THREE.Material; y: number }[] {
  const text = `${design.machine_type} ${design.product}`.toLowerCase();
  if (/blister/.test(text)) {
    return [{ geometry: new THREE.BoxGeometry(0.1, 0.008, 0.05), material: m.foil, y: 0.004 }];
  }
  if (/carton|box|case|astucc/.test(text)) {
    return [
      { geometry: new THREE.BoxGeometry(0.05, 0.11, 0.07), material: m.whitePlastic, y: 0.055 },
      { geometry: new THREE.BoxGeometry(0.051, 0.025, 0.071), material: m.accent, y: 0.085 },
    ];
  }
  if (/bottle|vial|fill|cap|liquid/.test(text)) {
    return [
      { geometry: new THREE.CylinderGeometry(0.018, 0.018, 0.06, 20), material: m.film, y: 0.03 },
      { geometry: new THREE.CylinderGeometry(0.0185, 0.0185, 0.016, 20), material: m.accent, y: 0.068 },
    ];
  }
  if (/tube/.test(text)) {
    const g = new THREE.CylinderGeometry(0.018, 0.018, 0.12, 20).rotateZ(Math.PI / 2);
    return [{ geometry: g, material: m.whitePlastic, y: 0.018 }];
  }
  return [{ geometry: new THREE.BoxGeometry(0.06, 0.04, 0.05), material: m.steelDark, y: 0.02 }];
}

// --- assembly ----------------------------------------------------------------------------------------

export function buildMachine(layout: Layout, design: MachineDesign, m: Materials): MachineScene {
  const root = new THREE.Group();
  const pickables: THREE.Mesh[] = [];
  const stationBounds = new Map<string, THREE.Box3>();
  const guards: THREE.Object3D[] = [];
  const labels: CSS2DObject[] = [];
  const textures: THREE.Texture[] = [];
  const stations = new Map(design.stations.map((s) => [s.id, s]));

  const flow = layout.boxes
    .filter((b) => b.sequence !== null && b.station_id && stations.has(b.station_id))
    .sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
  const ushape = layout.style === "u_shape";
  const facingOf = (b: LayoutBox) => (ushape && b.y < 0 ? -1 : 1);

  const register = (group: THREE.Group, stationId: string, name: string, height: number) => {
    group.traverse((o) => {
      if (o instanceof THREE.Mesh) {
        o.userData.stationId = stationId;
        pickables.push(o);
      }
    });
    const tag = label(name, height + 0.15);
    group.add(tag);
    labels.push(tag);
    root.add(group);
    group.updateMatrixWorld(true);
    stationBounds.set(stationId, new THREE.Box3().setFromObject(group));
  };

  // Product path through the flow stations: entry and exit point per station.
  const path: THREE.Vector3[] = [];
  const transfers: [THREE.Vector3, THREE.Vector3][] = [];
  let firstModule: Module | null = null;
  let lastModule: { group: THREE.Group; L: number; H: number } | null = null;

  flow.forEach((b, i) => {
    const station = stations.get(b.station_id!)!;
    const facing = facingOf(b);
    const L = b.length / 1000;
    const next = flow[i + 1];
    const prev = flow[i - 1];
    const dir = next ? Math.sign(next.x - b.x) || 1 : prev ? Math.sign(b.x - prev.x) || 1 : 1;
    let productZ = 0;
    let group: THREE.Group;
    let height: number;
    if (station.kind === "transport") {
      const conv = conveyorModule(b, station, m);
      group = conv.group;
      height = conv.H;
    } else {
      const sameRow = (o?: LayoutBox) => !!o && Math.abs(o.y - b.y) < 1;
      const neighbours = [flow[i - 1], flow[i + 1]].filter(sameRow);
      const leftOpen = !neighbours.some((o) => o!.x < b.x);
      const rightOpen = !neighbours.some((o) => o!.x > b.x);
      const mod = processModule(b, station, m, facing === 1 ? { left: leftOpen, right: rightOpen } : { left: rightOpen, right: leftOpen });
      group = mod.group;
      height = mod.H;
      productZ = mod.productZ;
      guards.push(mod.guard);
      if (!firstModule && facing === 1) firstModule = mod;
      lastModule = { group, L: mod.L, H: mod.H };
    }
    group.position.set(b.x / 1000, 0, b.y / 1000);
    group.rotation.y = facing === 1 ? 0 : Math.PI;
    const z = b.y / 1000 + facing * productZ;
    const entry = v3(b.x / 1000 - (dir * L) / 2, BASE_H, z);
    const exit = v3(b.x / 1000 + (dir * L) / 2, BASE_H, z);
    const last = path[path.length - 1];
    if (last && Math.abs(last.z - entry.z) > 0.6) transfers.push([last.clone(), entry.clone()]);
    path.push(entry, exit);
    register(group, station.id, `${b.sequence}. ${station.name}`, height);
  });

  for (const [a, b] of transfers) root.add(transferConveyor(a, b, m));

  if (firstModule) {
    const mod = firstModule as Module;
    const arm = hmi(mod, design, m, textures);
    mod.group.add(arm);
  }
  if (lastModule) {
    const lm = lastModule as { group: THREE.Group; L: number; H: number };
    lm.group.add(stackLight(lm.L / 2 - 0.12, lm.H, -0.1, m));
  }

  // Cabinets and utility panels.
  for (const b of layout.boxes) {
    if (b.sequence !== null || !b.station_id || b.kind === "guard" || b.kind === "base") continue;
    const station = stations.get(b.station_id);
    if (!station) continue;
    const group = cabinet(b, station, m);
    group.position.set(b.x / 1000, 0, b.y / 1000);
    register(group, station.id, station.name, b.height / 1000);
  }

  // Moving products.
  const lengths = [0];
  for (let i = 1; i < path.length; i++) lengths.push(lengths[i - 1] + path[i].distanceTo(path[i - 1]));
  const total = lengths[lengths.length - 1] ?? 0;
  const count = total > 0 ? Math.floor(total / PRODUCT_SPACING) : 0;
  const parts = count ? productParts(design, m) : [];
  const instanced = parts.map((p) => {
    const im = new THREE.InstancedMesh(p.geometry, p.material, count);
    im.castShadow = true;
    root.add(im);
    return { im, y: p.y };
  });
  const matrix = new THREE.Matrix4();
  const quaternion = new THREE.Quaternion();
  const up = new THREE.Vector3(0, 1, 0);
  const one = new THREE.Vector3(1, 1, 1);
  const position = new THREE.Vector3();
  let offset = 0;

  const update = (dt: number) => {
    if (!count) return;
    offset = (offset + dt * PRODUCT_SPEED) % total;
    let seg = 0;
    for (let i = 0; i < count; i++) {
      const s = (i * PRODUCT_SPACING + offset) % total;
      seg = 0;
      while (seg < lengths.length - 2 && lengths[seg + 1] < s) seg++;
      const a = path[seg];
      const b = path[seg + 1];
      const t = (s - lengths[seg]) / Math.max(1e-6, lengths[seg + 1] - lengths[seg]);
      quaternion.setFromAxisAngle(up, -Math.atan2(b.z - a.z, b.x - a.x));
      for (const { im, y } of instanced) {
        position.lerpVectors(a, b, t);
        position.y += y + 0.002;
        matrix.compose(position, quaternion, one);
        im.setMatrixAt(i, matrix);
      }
    }
    for (const { im } of instanced) im.instanceMatrix.needsUpdate = true;
  };
  update(0);

  return { group: root, pickables, stationBounds, guards, labels, textures, update };
}
