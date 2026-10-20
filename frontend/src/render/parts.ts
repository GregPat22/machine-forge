// Procedural models of machine components, built from primitives.
// Local frame: X right, Y up, Z out of the mounting plate (plate surface at z = 0).
// Every builder fits a cell of about CELL x CELL metres; callers scale the result.
import * as THREE from "three";
import type { Component } from "../types";
import type { Materials } from "./materials";

export const CELL = 0.24;

type Axis = "x" | "y" | "z";

export function mesh(geometry: THREE.BufferGeometry, material: THREE.Material, x = 0, y = 0, z = 0): THREE.Mesh {
  const m = new THREE.Mesh(geometry, material);
  m.position.set(x, y, z);
  m.castShadow = true;
  m.receiveShadow = true;
  return m;
}

export function box(w: number, h: number, d: number, mat: THREE.Material, x = 0, y = 0, z = 0): THREE.Mesh {
  return mesh(new THREE.BoxGeometry(w, h, d), mat, x, y, z);
}

export function cyl(
  rTop: number, rBottom: number, length: number, mat: THREE.Material, axis: Axis = "y",
  x = 0, y = 0, z = 0, segments = 24,
): THREE.Mesh {
  const m = mesh(new THREE.CylinderGeometry(rTop, rBottom, length, segments), mat, x, y, z);
  if (axis === "x") m.rotation.z = Math.PI / 2;
  if (axis === "z") m.rotation.x = Math.PI / 2;
  return m;
}

export function tube(points: THREE.Vector3[], radius: number, mat: THREE.Material): THREE.Mesh {
  const curve = new THREE.CatmullRomCurve3(points);
  const m = mesh(new THREE.TubeGeometry(curve, Math.max(8, points.length * 8), radius, 8, false), mat);
  m.castShadow = false;
  return m;
}

const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);

// --- builders: one unit of each component kind ------------------------------------------------------

function servo(m: Materials): THREE.Group {
  const g = new THREE.Group();
  g.add(box(0.11, 0.11, 0.014, m.steelDark, 0, 0, 0.007));
  g.add(box(0.092, 0.092, 0.15, m.darkMetal, 0, 0, 0.09));
  for (const dz of [0.04, 0.07, 0.1, 0.13]) g.add(box(0.096, 0.096, 0.004, m.blackPlastic, 0, 0, dz));
  g.add(cyl(0.038, 0.038, 0.022, m.blackPlastic, "z", 0, 0, 0.176));
  g.add(box(0.03, 0.024, 0.036, m.blackPlastic, 0, 0.058, 0.12));
  g.add(tube([v(0, 0.07, 0.12), v(0, 0.1, 0.08), v(0.02, 0.11, 0.02), v(0.03, 0.1, 0.003)], 0.006, m.cableOrange));
  return g;
}

function gearmotor(m: Materials): THREE.Group {
  const g = new THREE.Group();
  g.add(cyl(0.048, 0.048, 0.13, m.motorPaint, "x", -0.035, 0, 0.075));
  for (let i = 0; i < 6; i++) g.add(cyl(0.051, 0.051, 0.004, m.motorPaint, "x", -0.085 + i * 0.018, 0, 0.075));
  g.add(cyl(0.046, 0.05, 0.03, m.greyPlastic, "x", -0.115, 0, 0.075));
  g.add(box(0.08, 0.11, 0.1, m.motorPaint, 0.07, 0, 0.06));
  g.add(box(0.05, 0.03, 0.05, m.motorPaint, -0.03, 0.06, 0.075));
  g.add(cyl(0.012, 0.012, 0.02, m.chrome, "z", 0.07, 0, 0.005));
  return g;
}

function pneumaticCylinder(m: Materials): THREE.Group {
  const g = new THREE.Group();
  g.add(box(0.02, 0.06, 0.07, m.steelDark, -0.105, 0, 0.035));
  g.add(box(0.13, 0.044, 0.044, m.aluminum, -0.025, 0, 0.065));
  g.add(box(0.016, 0.048, 0.048, m.darkMetal, -0.092, 0, 0.065));
  g.add(box(0.016, 0.048, 0.048, m.darkMetal, 0.042, 0, 0.065));
  g.add(cyl(0.008, 0.008, 0.07, m.chrome, "x", 0.085, 0, 0.065));
  g.add(box(0.022, 0.022, 0.022, m.steelDark, 0.125, 0, 0.065));
  for (const x of [-0.065, 0.015]) {
    g.add(box(0.02, 0.006, 0.008, m.blackPlastic, x, 0.025, 0.065));
    g.add(box(0.003, 0.004, 0.004, m.ledGreen, x + 0.01, 0.028, 0.065));
  }
  for (const x of [-0.088, 0.038]) {
    g.add(cyl(0.005, 0.005, 0.014, m.chrome, "y", x, 0.029, 0.075));
    g.add(tube([v(x, 0.035, 0.075), v(x, 0.075, 0.07), v(x + 0.01, 0.1, 0.03), v(x + 0.01, 0.105, 0.004)], 0.0035, m.hoseBlue));
  }
  return g;
}

function gripper(m: Materials): THREE.Group {
  const g = new THREE.Group();
  g.add(box(0.04, 0.12, 0.04, m.aluminum, 0, 0.04, 0.03));
  g.add(box(0.07, 0.05, 0.05, m.aluminum, 0, -0.03, 0.06));
  g.add(box(0.012, 0.06, 0.022, m.steelDark, -0.022, -0.085, 0.06));
  g.add(box(0.012, 0.06, 0.022, m.steelDark, 0.022, -0.085, 0.06));
  g.add(tube([v(0.03, -0.01, 0.07), v(0.06, 0.03, 0.06), v(0.06, 0.1, 0.02), v(0.06, 0.11, 0.004)], 0.0035, m.hoseBlue));
  return g;
}

function valveTerminal(m: Materials): THREE.Group {
  const g = new THREE.Group();
  g.add(box(0.22, 0.07, 0.03, m.aluminum, 0, 0, 0.015));
  for (let i = 0; i < 8; i++) {
    const x = -0.09 + i * 0.022;
    g.add(box(0.019, 0.06, 0.05, m.greyPlastic, x, 0, 0.055));
    g.add(box(0.017, 0.018, 0.016, m.blackPlastic, x, 0.022, 0.087));
    g.add(box(0.004, 0.004, 0.003, i % 3 === 0 ? m.ledAmber : m.ledGreen, x, 0.035, 0.087));
    for (const dx of [-0.004, 0.004]) {
      g.add(cyl(0.003, 0.003, 0.012, m.chrome, "y", x + dx, -0.036, 0.06));
      g.add(tube([v(x + dx, -0.04, 0.06), v(x + dx, -0.08, 0.055), v(x + dx * 2, -0.11, 0.03), v(x + dx * 2, -0.12, 0.004)], 0.0025, m.hoseBlue));
    }
  }
  g.add(box(0.04, 0.07, 0.065, m.blackPlastic, 0.13, 0, 0.0325));
  for (let i = 0; i < 3; i++) g.add(box(0.005, 0.005, 0.003, i ? m.ledGreen : m.ledAmber, 0.12 + i * 0.01, 0.02, 0.066));
  return g;
}

function sensor(m: Materials, c: Component, variant: number): THREE.Group {
  const g = new THREE.Group();
  const text = `${c.name} ${c.specs.map((s) => s.value).join(" ")}`.toLowerCase();
  if (/thermocouple|pt100|type j|type k/.test(text)) {
    g.add(cyl(0.013, 0.013, 0.025, m.aluminum, "z", 0, 0.03, 0.02));
    g.add(cyl(0.003, 0.003, 0.09, m.chrome, "y", 0, -0.025, 0.02));
    g.add(tube([v(0, 0.04, 0.02), v(0.02, 0.07, 0.015), v(0.03, 0.09, 0.003)], 0.003, m.chrome));
    return g;
  }
  if (/load cell|weigh/.test(text)) {
    g.add(box(0.1, 0.028, 0.035, m.aluminum, 0, 0, 0.03));
    g.add(box(0.03, 0.01, 0.03, m.steelDark, 0.03, 0.019, 0.03));
    return g;
  }
  g.add(box(0.03, 0.006, 0.045, m.steelDark, 0, 0.022, 0.0225));
  g.add(box(0.022, 0.036, 0.03, variant % 2 ? m.sensorYellow : m.greyPlastic, 0, 0, 0.035));
  g.add(cyl(0.008, 0.008, 0.004, m.lens, "y", 0, -0.019, 0.035));
  g.add(box(0.004, 0.004, 0.003, m.ledGreen, 0.006, 0.012, 0.051));
  g.add(tube([v(0, 0.018, 0.035), v(0.01, 0.045, 0.03), v(0.02, 0.07, 0.01), v(0.02, 0.08, 0.003)], 0.0025, m.cable));
  return g;
}

function vision(m: Materials): THREE.Group {
  const g = new THREE.Group();
  g.add(box(0.03, 0.03, 0.012, m.steelDark, 0, 0.09, 0.006));
  g.add(box(0.012, 0.012, 0.12, m.aluminum, 0, 0.09, 0.066));
  g.add(box(0.055, 0.055, 0.075, m.whitePlastic, 0, 0.05, 0.12));
  g.add(cyl(0.018, 0.018, 0.035, m.blackPlastic, "y", 0, 0.008, 0.12));
  g.add(cyl(0.012, 0.012, 0.004, m.lens, "y", 0, -0.011, 0.12));
  const ring = mesh(new THREE.TorusGeometry(0.04, 0.009, 12, 32), m.ringLight, 0, -0.045, 0.12);
  ring.rotation.x = Math.PI / 2;
  g.add(ring);
  g.add(box(0.004, 0.06, 0.004, m.aluminum, 0.04, -0.02, 0.12));
  g.add(tube([v(0, 0.08, 0.12), v(0.02, 0.11, 0.1), v(0.03, 0.12, 0.03), v(0.03, 0.12, 0.004)], 0.004, m.cable));
  return g;
}

function heatedTool(m: Materials, sealing: boolean): THREE.Group {
  const g = new THREE.Group();
  g.add(box(0.19, 0.055, 0.13, m.anodized, 0, -0.02, 0.075));
  g.add(box(0.19, 0.008, 0.131, m.red, 0, 0.011, 0.075));
  for (const x of [-0.06, 0, 0.06]) g.add(cyl(0.006, 0.006, 0.03, m.chrome, "x", x + 0.11, -0.02, 0.075));
  if (sealing) {
    g.add(box(0.03, 0.08, 0.03, m.aluminum, 0, 0.055, 0.075));
    g.add(cyl(0.008, 0.008, 0.06, m.chrome, "y", 0, 0.03, 0.075));
  }
  for (const x of [-0.085, 0.085]) g.add(cyl(0.007, 0.007, 0.14, m.chrome, "y", x, 0.03, 0.02));
  g.add(tube([v(0.1, -0.02, 0.075), v(0.12, 0.03, 0.06), v(0.11, 0.09, 0.02), v(0.1, 0.1, 0.004)], 0.004, m.cable));
  return g;
}

function dieSet(m: Materials): THREE.Group {
  const g = new THREE.Group();
  g.add(box(0.18, 0.022, 0.12, m.steelDark, 0, -0.075, 0.07));
  g.add(box(0.18, 0.022, 0.12, m.steelDark, 0, 0.06, 0.07));
  for (const x of [-0.075, 0.075]) for (const z of [0.025, 0.115]) g.add(cyl(0.006, 0.006, 0.14, m.chrome, "y", x, -0.008, z));
  g.add(box(0.06, 0.05, 0.06, m.steel, 0, 0.02, 0.07));
  g.add(box(0.03, 0.03, 0.03, m.chrome, 0, -0.02, 0.07));
  return g;
}

function linearAxis(m: Materials): THREE.Group {
  const g = new THREE.Group();
  g.add(box(0.23, 0.045, 0.05, m.aluminum, 0, 0, 0.025));
  for (const y of [-0.012, 0.012]) g.add(box(0.23, 0.004, 0.002, m.darkMetal, 0, y, 0.051));
  g.add(box(0.065, 0.055, 0.03, m.darkMetal, 0.02, 0, 0.065));
  g.add(box(0.045, 0.045, 0.07, m.darkMetal, -0.135, 0, 0.035));
  g.add(cyl(0.015, 0.015, 0.01, m.blackPlastic, "z", -0.135, 0, 0.075));
  g.add(tube([v(-0.135, 0.025, 0.05), v(-0.13, 0.07, 0.04), v(-0.12, 0.1, 0.004)], 0.004, m.cableOrange));
  return g;
}

function vacuum(m: Materials, c: Component): THREE.Group {
  const g = new THREE.Group();
  if (/ejector|generator|pump/i.test(c.name)) {
    g.add(box(0.05, 0.035, 0.035, m.aluminum, 0, 0, 0.03));
    g.add(cyl(0.01, 0.01, 0.04, m.blackPlastic, "x", 0.045, 0, 0.03));
    g.add(tube([v(-0.025, 0, 0.03), v(-0.05, 0.04, 0.025), v(-0.06, 0.1, 0.004)], 0.0035, m.hoseBlue));
    return g;
  }
  g.add(box(0.012, 0.09, 0.012, m.aluminum, 0, 0.04, 0.07));
  g.add(box(0.17, 0.012, 0.014, m.aluminum, 0, -0.005, 0.07));
  for (const x of [-0.07, -0.025, 0.025, 0.07]) {
    g.add(cyl(0.003, 0.003, 0.02, m.chrome, "y", x, -0.02, 0.07));
    g.add(cyl(0.006, 0.016, 0.018, m.rubber, "y", x, -0.038, 0.07));
  }
  return g;
}

function pump(m: Materials, c: Component): THREE.Group {
  const g = new THREE.Group();
  if (/peristaltic/i.test(`${c.name} ${c.specs.map((s) => s.value).join(" ")}`) || c.category === "pump") {
    g.add(box(0.13, 0.13, 0.03, m.greyPlastic, 0, 0, 0.015));
    g.add(cyl(0.055, 0.055, 0.04, m.greyPlastic, "z", 0, 0, 0.05));
    g.add(cyl(0.057, 0.057, 0.008, m.glass, "z", 0, 0, 0.074));
    for (let i = 0; i < 3; i++) {
      const a = (i / 3) * Math.PI * 2;
      g.add(cyl(0.01, 0.01, 0.02, m.chrome, "z", Math.cos(a) * 0.035, Math.sin(a) * 0.035, 0.065));
    }
    g.add(tube([v(-0.05, -0.04, 0.06), v(-0.07, -0.08, 0.06), v(-0.07, -0.12, 0.05)], 0.004, m.whitePlastic));
    g.add(tube([v(0.05, -0.04, 0.06), v(0.07, -0.08, 0.06), v(0.07, -0.12, 0.05)], 0.004, m.whitePlastic));
    return g;
  }
  return dosing(m, c);
}

function dosing(m: Materials, c: Component): THREE.Group {
  const g = new THREE.Group();
  const name = c.name.toLowerCase();
  if (name.includes("gun")) {
    g.add(box(0.035, 0.06, 0.045, m.darkMetal, 0, 0, 0.05));
    g.add(cyl(0.004, 0.012, 0.03, m.chrome, "y", 0, -0.045, 0.05));
    g.add(tube([v(0, 0.03, 0.05), v(0.03, 0.07, 0.04), v(0.05, 0.1, 0.004)], 0.007, m.blackPlastic));
    return g;
  }
  if (name.includes("brush")) {
    g.add(box(0.2, 0.05, 0.1, m.steel, 0, 0.03, 0.06));
    g.add(cyl(0.035, 0.035, 0.18, m.blackPlastic, "x", 0, -0.025, 0.06));
    return g;
  }
  if (name.includes("unit") || name.includes("tank") || name.includes("melter")) {
    g.add(box(0.17, 0.17, 0.13, m.greyPlastic, 0, 0, 0.065));
    g.add(box(0.06, 0.035, 0.004, m.lens, 0.035, 0.04, 0.131));
    g.add(box(0.17, 0.02, 0.13, m.darkMetal, 0, 0.095, 0.065));
    return g;
  }
  const hopper = mesh(new THREE.CylinderGeometry(0.1, 0.03, 0.13, 4, 1), m.steel, 0, 0.04, 0.11);
  hopper.rotation.y = Math.PI / 4;
  g.add(hopper);
  g.add(cyl(0.02, 0.02, 0.05, m.steel, "y", 0, -0.045, 0.11));
  g.add(box(0.03, 0.12, 0.012, m.steelDark, 0, 0.02, 0.006));
  return g;
}

function printer(m: Materials): THREE.Group {
  const g = new THREE.Group();
  g.add(box(0.06, 0.1, 0.1, m.blackPlastic, 0, 0.01, 0.06));
  g.add(box(0.04, 0.02, 0.04, m.darkMetal, 0, -0.05, 0.08));
  g.add(tube([v(0, 0.06, 0.06), v(0.03, 0.09, 0.05), v(0.05, 0.11, 0.004)], 0.005, m.cable));
  return g;
}

function starWheel(m: Materials): THREE.Group {
  const g = new THREE.Group();
  const shape = new THREE.Shape();
  const pockets = 8;
  const R = 0.1;
  const r = 0.022;
  for (let i = 0; i <= 64; i++) {
    const a = (i / 64) * Math.PI * 2;
    const nearest = Math.round((a / (Math.PI * 2)) * pockets) / pockets * Math.PI * 2;
    const inPocket = Math.abs(a - nearest) < 0.2;
    const rad = inPocket ? R - r * Math.cos(((a - nearest) / 0.2) * (Math.PI / 2)) : R;
    const p = [Math.cos(a) * rad, Math.sin(a) * rad] as const;
    if (i === 0) shape.moveTo(...p);
    else shape.lineTo(...p);
  }
  const wheel = mesh(new THREE.ExtrudeGeometry(shape, { depth: 0.018, bevelEnabled: false }), m.whitePlastic, 0, 0, 0.06);
  g.add(wheel);
  g.add(cyl(0.015, 0.015, 0.07, m.chrome, "z", 0, 0, 0.035));
  g.add(cyl(0.03, 0.03, 0.02, m.steelDark, "z", 0, 0, 0.085));
  return g;
}

function timingScrew(m: Materials): THREE.Group {
  const g = new THREE.Group();
  g.add(cyl(0.035, 0.035, 0.22, m.whitePlastic, "x", 0, 0, 0.06));
  for (let i = 0; i < 9; i++) g.add(cyl(0.037, 0.037, 0.006, m.greyPlastic, "x", -0.1 + i * 0.025, 0, 0.06));
  for (const x of [-0.12, 0.12]) g.add(box(0.012, 0.06, 0.06, m.steelDark, x, 0, 0.03));
  return g;
}

function driveWheel(m: Materials): THREE.Group {
  const g = new THREE.Group();
  g.add(cyl(0.105, 0.105, 0.022, m.anodized, "z", 0, 0, 0.05, 48));
  g.add(cyl(0.11, 0.11, 0.006, m.steelDark, "z", 0, 0, 0.062, 48));
  for (let i = 0; i < 6; i++) {
    const a = (i / 6) * Math.PI * 2;
    g.add(cyl(0.018, 0.018, 0.024, m.darkMetal, "z", Math.cos(a) * 0.065, Math.sin(a) * 0.065, 0.05));
  }
  g.add(cyl(0.03, 0.03, 0.04, m.chrome, "z", 0, 0, 0.055));
  g.add(cyl(0.012, 0.012, 0.05, m.steelDark, "z", 0, 0, 0.08));
  g.add(cyl(0.025, 0.025, 0.02, m.steelDark, "z", 0.11, -0.09, 0.05));
  g.add(box(0.035, 0.035, 0.03, m.darkMetal, 0.11, -0.09, 0.025));
  return g;
}

function machinedPart(m: Materials): THREE.Group {
  const g = new THREE.Group();
  g.add(box(0.16, 0.1, 0.07, m.steel, 0, 0, 0.035));
  for (const x of [-0.06, 0.06]) for (const y of [-0.035, 0.035]) g.add(cyl(0.006, 0.006, 0.006, m.darkMetal, "z", x, y, 0.072));
  g.add(cyl(0.022, 0.022, 0.004, m.darkMetal, "z", 0, 0, 0.071));
  return g;
}

function miniConveyor(m: Materials): THREE.Group {
  const g = new THREE.Group();
  g.add(box(0.22, 0.016, 0.09, m.belt, 0, 0, 0.08));
  for (const x of [-0.11, 0.11]) g.add(cyl(0.012, 0.012, 0.095, m.chrome, "z", x, -0.004, 0.08));
  for (const z of [0.03, 0.13]) g.add(box(0.23, 0.03, 0.006, m.steel, 0, 0.004, z));
  return g;
}

function transmission(m: Materials): THREE.Group {
  const g = new THREE.Group();
  for (const x of [-0.07, 0.07]) {
    g.add(cyl(0.036, 0.036, 0.022, m.steelDark, "z", x, 0, 0.035));
    g.add(cyl(0.008, 0.008, 0.03, m.chrome, "z", x, 0, 0.02));
  }
  g.add(box(0.14, 0.005, 0.02, m.rubber, 0, 0.0385, 0.035));
  g.add(box(0.14, 0.005, 0.02, m.rubber, 0, -0.0385, 0.035));
  for (const [x, rot] of [[0.07, -Math.PI / 2], [-0.07, Math.PI / 2]] as const) {
    const arc = mesh(new THREE.TorusGeometry(0.0385, 0.0028, 6, 20, Math.PI), m.rubber, x, 0, 0.035);
    arc.rotation.z = rot;
    arc.scale.z = 3.5;
    g.add(arc);
  }
  return g;
}

function gearbox(m: Materials): THREE.Group {
  const g = new THREE.Group();
  g.add(box(0.09, 0.09, 0.08, m.motorPaint, 0, 0, 0.04));
  g.add(cyl(0.012, 0.012, 0.03, m.chrome, "x", 0.06, 0, 0.04));
  return g;
}

function airTreatment(m: Materials): THREE.Group {
  const g = new THREE.Group();
  g.add(box(0.2, 0.02, 0.02, m.aluminum, 0, 0.05, 0.01));
  for (let i = 0; i < 3; i++) {
    const x = -0.065 + i * 0.065;
    g.add(box(0.045, 0.05, 0.045, m.greyPlastic, x, 0.03, 0.04));
    g.add(cyl(0.017, 0.014, 0.065, m.glass, "y", x, -0.027, 0.04));
    g.add(cyl(0.006, 0.006, 0.02, m.blackPlastic, "y", x, -0.07, 0.04));
    if (i === 1) {
      g.add(cyl(0.018, 0.018, 0.008, m.whitePlastic, "z", x, 0.03, 0.067));
      g.add(mesh(new THREE.TorusGeometry(0.018, 0.0025, 6, 20), m.blackPlastic, x, 0.03, 0.071));
    }
  }
  g.add(tube([v(0.1, 0.05, 0.03), v(0.12, 0.0, 0.03), v(0.12, -0.09, 0.02)], 0.004, m.hoseBlue));
  return g;
}

function cooling(m: Materials): THREE.Group {
  const g = new THREE.Group();
  g.add(box(0.14, 0.14, 0.06, m.greyPlastic, 0, 0, 0.03));
  for (let i = 0; i < 6; i++) g.add(box(0.12, 0.006, 0.004, m.blackPlastic, 0, -0.05 + i * 0.02, 0.062));
  return g;
}

// --- generic hardware that fills the rest of a mechanism plate ---------------------------------------

function bearingShaft(m: Materials): THREE.Group {
  const g = new THREE.Group();
  for (const x of [-0.08, 0.08]) {
    g.add(box(0.04, 0.05, 0.05, m.steelDark, x, -0.01, 0.025));
    g.add(cyl(0.02, 0.02, 0.052, m.darkMetal, "z", x, 0.0, 0.03));
  }
  g.add(cyl(0.009, 0.009, 0.22, m.chrome, "x", 0, 0.0, 0.055));
  g.add(cyl(0.03, 0.03, 0.016, m.steelDark, "x", 0.0, 0.0, 0.055));
  return g;
}

function camLever(m: Materials): THREE.Group {
  const g = new THREE.Group();
  g.add(cyl(0.05, 0.05, 0.018, m.anodized, "z", -0.05, 0.02, 0.03, 32));
  g.add(cyl(0.012, 0.012, 0.03, m.chrome, "z", -0.05, 0.02, 0.04));
  const lever = box(0.14, 0.022, 0.012, m.steelDark, 0.03, -0.02, 0.05);
  lever.rotation.z = -0.35;
  g.add(lever);
  g.add(cyl(0.012, 0.012, 0.016, m.blackPlastic, "z", -0.02, 0.005, 0.058));
  g.add(cyl(0.008, 0.008, 0.02, m.chrome, "z", 0.09, -0.045, 0.05));
  g.add(cyl(0.004, 0.004, 0.08, m.chrome, "y", 0.09, -0.09, 0.05));
  return g;
}

function sensorBracket(m: Materials, i: number): THREE.Group {
  const g = new THREE.Group();
  g.add(box(0.012, 0.09, 0.03, m.steelDark, -0.03, 0, 0.015));
  g.add(box(0.06, 0.012, 0.04, m.steelDark, 0, 0.04, 0.03));
  g.add(box(0.02, 0.032, 0.025, i % 2 ? m.sensorYellow : m.greyPlastic, 0.012, 0.018, 0.04));
  g.add(box(0.003, 0.003, 0.003, m.ledGreen, 0.016, 0.03, 0.053));
  g.add(tube([v(0.012, 0.036, 0.04), v(0.03, 0.07, 0.03), v(0.05, 0.1, 0.004)], 0.0025, m.cable));
  return g;
}

function fittingManifold(m: Materials): THREE.Group {
  const g = new THREE.Group();
  g.add(box(0.1, 0.03, 0.03, m.aluminum, 0, 0, 0.015));
  for (const x of [-0.03, 0, 0.03]) {
    g.add(cyl(0.005, 0.005, 0.016, m.chrome, "y", x, 0.022, 0.018));
    g.add(tube([v(x, 0.03, 0.018), v(x + 0.01, 0.07, 0.02), v(x + 0.03, 0.1, 0.005)], 0.003, m.hoseBlue));
  }
  return g;
}

function guidePlate(m: Materials): THREE.Group {
  const g = new THREE.Group();
  for (const x of [-0.07, 0.07]) g.add(cyl(0.006, 0.006, 0.07, m.chrome, "z", x, 0, 0.035));
  g.add(box(0.2, 0.05, 0.016, m.whitePlastic, 0, 0, 0.075));
  for (const x of [-0.07, 0.07]) g.add(cyl(0.007, 0.007, 0.004, m.darkMetal, "z", x, 0, 0.085));
  return g;
}

/** Generic hardware for an empty cell of the mechanism plate (not a component of the design). */
export function buildFiller(m: Materials, index: number): THREE.Group {
  const builders = [bearingShaft, camLever, (mm: Materials) => sensorBracket(mm, index), fittingManifold, guidePlate];
  return builders[index % builders.length](m);
}

/** Components that are drawn on the station's mechanism plate (others live in the cabinets). */
export const WALL_CATEGORIES = new Set([
  "servo_motor", "motor", "gearbox", "pneumatic_actuator", "pneumatic_valve", "sensor", "vision", "heating",
  "sealing", "cutting", "linear_motion", "vacuum", "pump", "dosing", "printing_marking", "custom_part",
  "conveyor", "transmission", "air_treatment", "cooling", "other",
]);

const PNEUMATIC = new Set(["pneumatic_actuator", "pneumatic_valve", "vacuum", "air_treatment"]);

function unit(c: Component, m: Materials, variant: number): THREE.Group {
  const name = c.name.toLowerCase();
  switch (c.category) {
    case "servo_motor": return servo(m);
    case "motor": return gearmotor(m);
    case "gearbox": return gearbox(m);
    case "pneumatic_actuator": return /grip|jaw|finger/.test(name) ? gripper(m) : pneumaticCylinder(m);
    case "pneumatic_valve": return valveTerminal(m);
    case "sensor": return sensor(m, c, variant);
    case "vision": return /light|lamp|illum/.test(name) ? sensor(m, c, variant) : vision(m);
    case "heating": return heatedTool(m, false);
    case "sealing": return heatedTool(m, true);
    case "cutting": return dieSet(m);
    case "linear_motion": return linearAxis(m);
    case "vacuum": return vacuum(m, c);
    case "pump": return pump(m, c);
    case "dosing": return dosing(m, c);
    case "printing_marking": return printer(m);
    case "conveyor": return miniConveyor(m);
    case "transmission": return transmission(m);
    case "air_treatment": return airTreatment(m);
    case "cooling": return cooling(m);
    case "custom_part":
      if (/drive wheel|cam/.test(name)) return driveWheel(m);
      if (/star|wheel/.test(name)) return starWheel(m);
      if (/screw|auger/.test(name)) return timingScrew(m);
      return machinedPart(m);
    default: return machinedPart(m);
  }
}

const SMALL = new Set(["sensor", "vacuum"]);

/** All visible units of a component, arranged side by side within one CELL x CELL cell. */
export function buildPart(c: Component, m: Materials, variant: number): { group: THREE.Group; pneumatic: boolean } {
  const group = new THREE.Group();
  const isCups = c.category === "vacuum" && !/ejector|generator|pump/i.test(c.name);
  const count = Math.min(c.quantity, SMALL.has(c.category) && !isCups ? 4 : c.category === "custom_part" ? 1 : 2);
  const scale = count > 1 ? Math.min(1, 1.25 / count) : 1;
  for (let i = 0; i < count; i++) {
    const u = unit(c, m, variant + i);
    u.scale.setScalar(scale);
    u.position.x = count > 1 ? (-0.5 + (i + 0.5) / count) * CELL * 0.95 : 0;
    // Vertical cylinders now and then, so a station doesn't look like a copy-paste row.
    if (c.category === "pneumatic_actuator" && (variant + i) % 2 === 1 && !/grip|jaw/i.test(c.name)) {
      u.rotation.z = Math.PI / 2;
    }
    group.add(u);
  }
  return { group, pneumatic: PNEUMATIC.has(c.category) };
}
