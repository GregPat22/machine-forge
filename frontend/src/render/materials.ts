// Shared materials and procedural textures for the realistic machine render.
import * as THREE from "three";

function canvasTexture(width: number, height: number, draw: (ctx: CanvasRenderingContext2D) => void): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  draw(canvas.getContext("2d")!);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

/** Fine horizontal streaks: reads as brushed stainless steel under studio light. */
function brushedTexture(): THREE.CanvasTexture {
  const texture = canvasTexture(512, 512, (ctx) => {
    ctx.fillStyle = "#d8dadd";
    ctx.fillRect(0, 0, 512, 512);
    // Deterministic pseudo-random streaks, so every render looks the same.
    let seed = 7;
    const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    for (let i = 0; i < 2600; i++) {
      const y = rand() * 512;
      const shade = 200 + Math.floor(rand() * 45);
      ctx.strokeStyle = `rgba(${shade},${shade + 2},${shade + 5},${0.25 + rand() * 0.35})`;
      ctx.lineWidth = 0.5 + rand() * 1.2;
      const x = rand() * 512;
      ctx.beginPath();
      ctx.moveTo(x - 80 - rand() * 300, y);
      ctx.lineTo(x + 80 + rand() * 300, y + (rand() - 0.5) * 1.5);
      ctx.stroke();
    }
  });
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.anisotropy = 8;
  return texture;
}

/** A plausible operator screen: header, station tiles, state. Generic, no branding. */
export function hmiScreenTexture(title: string, stations: string[], throughput: string | null): THREE.CanvasTexture {
  return canvasTexture(640, 400, (ctx) => {
    ctx.fillStyle = "#0f172a";
    ctx.fillRect(0, 0, 640, 400);
    ctx.fillStyle = "#1e293b";
    ctx.fillRect(0, 0, 640, 46);
    ctx.fillStyle = "#f59e0b";
    ctx.fillRect(0, 44, 640, 3);
    ctx.font = "bold 20px Arial";
    ctx.fillStyle = "#f8fafc";
    ctx.fillText(title.length > 34 ? `${title.slice(0, 33)}…` : title, 16, 30);
    ctx.fillStyle = "#22c55e";
    ctx.beginPath();
    ctx.arc(560, 23, 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.font = "bold 15px Arial";
    ctx.fillText("EXECUTE", 572, 28);

    const shown = stations.slice(0, 8);
    const cols = 4;
    shown.forEach((name, i) => {
      const x = 16 + (i % cols) * 154;
      const y = 66 + Math.floor(i / cols) * 104;
      ctx.fillStyle = "#1e293b";
      ctx.fillRect(x, y, 142, 90);
      ctx.fillStyle = "#22c55e";
      ctx.fillRect(x, y, 142, 4);
      ctx.fillStyle = "#cbd5e1";
      ctx.font = "13px Arial";
      const words = name.split(" ");
      let line = "";
      let ly = y + 28;
      for (const w of words) {
        if (ctx.measureText(`${line} ${w}`).width > 128 && line) {
          ctx.fillText(line, x + 8, ly);
          line = w;
          ly += 17;
        } else line = line ? `${line} ${w}` : w;
      }
      ctx.fillText(line, x + 8, ly);
      ctx.fillStyle = "#64748b";
      ctx.font = "11px Arial";
      ctx.fillText(`S${String(i + 1).padStart(2, "0")} · OK`, x + 8, y + 80);
    });
    ctx.fillStyle = "#1e293b";
    ctx.fillRect(16, 290, 608, 92);
    ctx.fillStyle = "#94a3b8";
    ctx.font = "13px Arial";
    ctx.fillText("Speed", 32, 318);
    ctx.fillStyle = "#f8fafc";
    ctx.font = "bold 28px Arial";
    ctx.fillText(throughput ?? "—", 32, 356);
    ctx.fillStyle = "#334155";
    ctx.fillRect(330, 330, 270, 14);
    ctx.fillStyle = "#f59e0b";
    ctx.fillRect(330, 330, 200, 14);
  });
}

export interface Materials {
  steel: THREE.MeshPhysicalMaterial;
  steelDark: THREE.MeshPhysicalMaterial;
  plate: THREE.MeshStandardMaterial;
  chrome: THREE.MeshStandardMaterial;
  aluminum: THREE.MeshStandardMaterial;
  darkMetal: THREE.MeshStandardMaterial;
  blackPlastic: THREE.MeshStandardMaterial;
  greyPlastic: THREE.MeshStandardMaterial;
  rubber: THREE.MeshStandardMaterial;
  slat: THREE.MeshStandardMaterial;
  glass: THREE.MeshPhysicalMaterial;
  hoseBlue: THREE.MeshStandardMaterial;
  cable: THREE.MeshStandardMaterial;
  cableOrange: THREE.MeshStandardMaterial;
  sensorYellow: THREE.MeshStandardMaterial;
  red: THREE.MeshStandardMaterial;
  anodized: THREE.MeshStandardMaterial;
  motorPaint: THREE.MeshStandardMaterial;
  whitePlastic: THREE.MeshStandardMaterial;
  film: THREE.MeshPhysicalMaterial;
  foil: THREE.MeshStandardMaterial;
  cardboard: THREE.MeshStandardMaterial;
  belt: THREE.MeshStandardMaterial;
  ledGreen: THREE.MeshStandardMaterial;
  ledAmber: THREE.MeshStandardMaterial;
  ledRed: THREE.MeshStandardMaterial;
  ringLight: THREE.MeshStandardMaterial;
  lens: THREE.MeshPhysicalMaterial;
  accent: THREE.MeshStandardMaterial;
  highlight: THREE.LineBasicMaterial;
  textures: THREE.Texture[];
}

export function createMaterials(accent: string): Materials {
  const brushed = brushedTexture();
  const brushedDark = brushed.clone();
  brushedDark.needsUpdate = true;
  const std = (color: number, roughness: number, metalness = 0, extra: THREE.MeshStandardMaterialParameters = {}) =>
    new THREE.MeshStandardMaterial({ color, roughness, metalness, ...extra });
  return {
    steel: new THREE.MeshPhysicalMaterial({
      color: 0xeef0f2, map: brushed, metalness: 0.95, roughness: 0.28, anisotropy: 0.7, clearcoat: 0.15,
      envMapIntensity: 1.25,
    }),
    steelDark: new THREE.MeshPhysicalMaterial({
      color: 0xa9aeb4, map: brushedDark, metalness: 0.9, roughness: 0.38, anisotropy: 0.5, envMapIntensity: 1.1,
    }),
    plate: std(0x8d939a, 0.5, 0.75, { map: brushedDark, envMapIntensity: 0.8 }),
    chrome: std(0xf2f4f6, 0.08, 1),
    aluminum: std(0xc3c7cc, 0.38, 0.85),
    darkMetal: std(0x2b2e33, 0.42, 0.55),
    blackPlastic: std(0x18191b, 0.55),
    greyPlastic: std(0x4b5058, 0.6),
    rubber: std(0x111111, 0.9),
    slat: std(0x2a2c30, 0.55, 0.3),
    glass: new THREE.MeshPhysicalMaterial({
      color: 0xe8f0f7, roughness: 0.04, metalness: 0, transparent: true, opacity: 0.08, clearcoat: 0.3,
      depthWrite: false, side: THREE.DoubleSide,
    }),
    hoseBlue: std(0x1f5fd1, 0.45),
    cable: std(0x2f3237, 0.65),
    cableOrange: std(0xe56b1f, 0.55),
    sensorYellow: std(0xf2c230, 0.45),
    red: std(0xd11f1f, 0.35),
    anodized: std(0x2f3a46, 0.35, 0.5),
    motorPaint: std(0x55657a, 0.45, 0.35),
    whitePlastic: std(0xf3f4f5, 0.5),
    film: new THREE.MeshPhysicalMaterial({ color: 0xf4f6f8, roughness: 0.25, metalness: 0, clearcoat: 0.6 }),
    foil: std(0xd9dde2, 0.22, 1),
    cardboard: std(0xb58a5a, 0.85),
    belt: std(0x22262b, 0.8),
    ledGreen: std(0x16a34a, 0.3, 0, { emissive: 0x22c55e, emissiveIntensity: 1.6, transparent: true, opacity: 0.92 }),
    ledAmber: std(0xb45309, 0.3, 0, { emissive: 0xf59e0b, emissiveIntensity: 0.25, transparent: true, opacity: 0.85 }),
    ledRed: std(0x991b1b, 0.3, 0, { emissive: 0xef4444, emissiveIntensity: 0.2, transparent: true, opacity: 0.85 }),
    ringLight: std(0xffffff, 0.2, 0, { emissive: 0xffffff, emissiveIntensity: 1.2 }),
    lens: new THREE.MeshPhysicalMaterial({ color: 0x0b1220, roughness: 0.05, metalness: 0.2, clearcoat: 1 }),
    accent: std(new THREE.Color(accent).getHex(), 0.35, 0.2),
    highlight: new THREE.LineBasicMaterial({ color: 0xf59e0b }),
    textures: [brushed, brushedDark],
  };
}

export function disposeMaterials(m: Materials): void {
  for (const value of Object.values(m)) {
    if (value instanceof THREE.Material) value.dispose();
  }
  m.textures.forEach((t) => t.dispose());
}
