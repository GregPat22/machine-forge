import type { LayoutBox } from "../types";

// Screen projection only. Every corner, including base elevation, uses layout API dimensions.
type Point = [number, number];
const project = (x: number, y: number, z: number): Point => [0.88 * x - 0.6 * y, 0.22 * x + 0.35 * y - 0.82 * z];
const points = (items: Point[]) => items.map((p) => p.join(",")).join(" ");

export function projectEnvelopes(boxes: LayoutBox[]) {
  const all: Point[] = [];
  const envelopes = boxes.map((box) => {
    const x0 = box.x - box.length / 2,
      x1 = box.x + box.length / 2;
    const y0 = box.y - box.width / 2,
      y1 = box.y + box.width / 2;
    const z0 = box.z - box.height / 2,
      z1 = box.z + box.height / 2;
    const p = [
      [x0, y0, z0],
      [x1, y0, z0],
      [x1, y1, z0],
      [x0, y1, z0],
      [x0, y0, z1],
      [x1, y0, z1],
      [x1, y1, z1],
      [x0, y1, z1],
    ].map(([x, y, z]) => project(x, y, z));
    all.push(...p);
    return {
      box,
      side: points([p[1], p[2], p[6], p[5]]),
      front: points([p[2], p[3], p[7], p[6]]),
      top: points([p[4], p[5], p[6], p[7]]),
      label: project(box.x, box.y, z1),
    };
  });
  if (!all.length) return { envelopes, viewBox: "0 0 1 1", fontSize: 1 };
  const xs = all.map((p) => p[0]),
    ys = all.map((p) => p[1]);
  const left = Math.min(...xs),
    top = Math.min(...ys),
    width = Math.max(...xs) - left,
    height = Math.max(...ys) - top;
  const margin = Math.max(width, height) * 0.04;
  return {
    envelopes,
    viewBox: `${left - margin} ${top - margin} ${width + 2 * margin} ${height + 2 * margin}`,
    fontSize: Math.max(width, height) / 38,
  };
}
