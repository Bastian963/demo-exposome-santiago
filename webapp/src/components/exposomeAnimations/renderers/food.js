import { Container, Graphics } from "pixi.js";
import { clamp01 } from "../transitions.js";

// Diegetic food monitors. Two variants share this renderer:
//
// - default ("food_stall"): a produce market stall that stocks up as the
//   healthy-food-access index rises. Low index = empty crates (food
//   desert); high index = full, fresh crates under a lit awning. Honest
//   by construction: it depicts access to healthy retail, not diet quality.
// - "food_pantry": a household pantry for the food-insecurity layer.
//   Here the value is the % of households in moderate-severe food
//   insecurity, so the scene inverts internally (provision = 1 - t):
//   higher insecurity = emptier shelves and dimmer light. The cabinet
//   geometry is fixed and independent of the value (no hover flicker).
export function createFoodRenderer() {
  let root = null;
  let staticLayer = null;
  let dynamicLayer = null;
  let lastBounds = null;

  function init({ parent, theme, bounds }) {
    root = new Container();
    staticLayer = new Container();
    dynamicLayer = new Container();
    root.addChild(staticLayer);
    root.addChild(dynamicLayer);
    parent.addChild(root);
    resize(bounds, theme);
  }

  function update({ bounds, theme, visualState, now }) {
    if (!root) return;
    if (!sameBounds(bounds, lastBounds)) resize(bounds, theme);
    destroyChildren(dynamicLayer);
    const t = clamp01(visualState.intensity ?? 0);
    if (resolveVariant(theme) === "food_pantry") {
      drawPantryMonitor(dynamicLayer, bounds, theme, t, now);
    } else {
      drawFoodStallMonitor(dynamicLayer, bounds, theme, t, now);
    }
  }

  function resize(bounds, theme) {
    lastBounds = { ...bounds };
    destroyChildren(staticLayer);
    drawFrame(staticLayer, bounds, theme);
    drawGrid(staticLayer, bounds, theme);
  }

  function destroy() {
    destroyChildren(staticLayer);
    destroyChildren(dynamicLayer);
    if (root?.parent) root.parent.removeChild(root);
    try { root?.destroy({ children: true }); } catch (_) {}
    root = null;
    staticLayer = null;
    dynamicLayer = null;
    lastBounds = null;
  }

  return { init, update, resize, destroy };
}

const AMBER = 0xf4b41b;
const GREEN = 0x78d6aa;
const CYAN = 0x73eff7;

function drawFoodStallMonitor(container, bounds, theme, t, now) {
  const box = getBox(bounds);
  const scene = {
    x: box.x + 16,
    y: box.y + 16,
    w: box.w - 32,
    h: box.h - 28,
  };
  const pulse = 0.5 + 0.5 * Math.sin(now * 0.0045);
  drawStallBase(container, scene, theme, t);
  drawAwning(container, scene, theme, t, pulse);
  drawProduceCrates(container, scene, theme, t, pulse);
  drawFreshnessMeter(container, scene, theme, t, pulse);
}

function drawStallBase(container, scene, theme, t) {
  const g = new Graphics();
  g.rect(scene.x, scene.y, scene.w, scene.h).fill({ color: 0x0c1422, alpha: 0.5 });
  // counter surface where crates sit
  const counterY = scene.y + scene.h * 0.62;
  g.rect(scene.x + scene.w * 0.06, counterY, scene.w * 0.88, Math.max(4, scene.h * 0.045))
    .fill({ color: theme.lineSoft, alpha: 0.42 + t * 0.2 });
  // counter front panel
  g.rect(scene.x + scene.w * 0.06, counterY + scene.h * 0.045, scene.w * 0.88, scene.h * 0.18)
    .fill({ color: 0x101425, alpha: 0.55 });
  // top-lit edge on the counter
  g.rect(scene.x + scene.w * 0.06, counterY, scene.w * 0.88, 1)
    .fill({ color: theme.particle || GREEN, alpha: 0.25 + t * 0.4 });
  container.addChild(g);
}

function drawAwning(container, scene, theme, t, pulse) {
  const g = new Graphics();
  const ax = scene.x + scene.w * 0.06;
  const aw = scene.w * 0.88;
  const ay = scene.y + scene.h * 0.06;
  const ah = Math.max(8, scene.h * 0.12);
  const lit = 0.22 + t * 0.4 + pulse * 0.06;
  // support posts
  g.rect(ax + 1, ay, 2, scene.h * 0.56).fill({ color: theme.line, alpha: 0.3 });
  g.rect(ax + aw - 3, ay, 2, scene.h * 0.56).fill({ color: theme.line, alpha: 0.3 });
  // striped canopy
  const stripes = 8;
  const sw = aw / stripes;
  for (let i = 0; i < stripes; i += 1) {
    const color = i % 2 === 0 ? (theme.particle || GREEN) : CYAN;
    g.rect(ax + i * sw, ay, sw, ah).fill({ color, alpha: 0.14 + (i % 2 === 0 ? lit : lit * 0.7) });
  }
  // scalloped lower edge
  for (let i = 0; i < stripes; i += 1) {
    const cxs = ax + i * sw + sw / 2;
    g.moveTo(ax + i * sw, ay + ah)
      .lineTo(cxs, ay + ah + Math.min(6, sw * 0.5))
      .lineTo(ax + (i + 1) * sw, ay + ah)
      .stroke({ width: 1, color: theme.white, alpha: 0.16 + t * 0.2 });
  }
  container.addChild(g);
}

function drawProduceCrates(container, scene, theme, t, pulse) {
  const g = new Graphics();
  const n = 4;
  const gap = scene.w * 0.03;
  const marginX = scene.w * 0.1;
  const rowW = scene.w - marginX * 2;
  const crateW = (rowW - gap * (n - 1)) / n;
  const crateH = Math.max(14, scene.h * 0.2);
  const baseY = scene.y + scene.h * 0.62 - crateH + 1; // sit on the counter
  const accent = theme.particle || GREEN;

  for (let i = 0; i < n; i += 1) {
    const x = scene.x + marginX + i * (crateW + gap);
    const threshold = i / n; // left crates fill first
    const active = clamp01((t - threshold) / 0.28);

    // crate box
    g.roundRect(x, baseY, crateW, crateH, 2).fill({ color: 0x101425, alpha: 0.72 });
    g.roundRect(x, baseY, crateW, crateH, 2)
      .stroke({ width: 1, color: active > 0.15 ? accent : theme.line, alpha: 0.3 + active * 0.5 });
    // slat lines on the crate front
    for (let s = 1; s < 3; s += 1) {
      const yy = baseY + (crateH * s) / 3;
      g.moveTo(x + 1, yy).lineTo(x + crateW - 1, yy)
        .stroke({ width: 1, color: theme.lineSoft, alpha: 0.4 });
    }

    // produce mound: stacked dots whose count/brightness grow with `active`
    if (active > 0.05) {
      const cols = 3;
      const rows = 2;
      const filled = Math.round(active * cols * rows);
      const palette = [GREEN, AMBER, CYAN];
      let drawn = 0;
      const pr = Math.max(2, crateW * 0.12);
      for (let ry = 0; ry < rows; ry += 1) {
        for (let cx0 = 0; cx0 < cols; cx0 += 1) {
          if (drawn >= filled) break;
          const px = x + crateW * (0.24 + cx0 * 0.26);
          const py = baseY - 1 - ry * pr * 1.7;
          const color = palette[(cx0 + ry) % palette.length];
          g.circle(px, py, pr).fill({ color, alpha: 0.5 + active * 0.4 });
          g.circle(px - pr * 0.3, py - pr * 0.3, pr * 0.35)
            .fill({ color: theme.white, alpha: 0.3 + active * 0.4 });
          drawn += 1;
        }
      }
      // glow over a well-stocked crate
      g.circle(x + crateW / 2, baseY - crateH * 0.1, crateW * 0.5)
        .fill({ color: accent, alpha: 0.04 + active * (0.1 + pulse * 0.05) });
    } else {
      // empty crate marker (food desert): faint cross
      g.moveTo(x + crateW * 0.35, baseY + crateH * 0.5)
        .lineTo(x + crateW * 0.65, baseY + crateH * 0.5)
        .stroke({ width: 1, color: theme.line, alpha: 0.22 });
    }
  }
  container.addChild(g);
}

function drawFreshnessMeter(container, scene, theme, t, pulse) {
  const g = new Graphics();
  const x = scene.x + scene.w * 0.1;
  const y = scene.y + scene.h * 0.93;
  const w = scene.w * 0.8;
  const h = Math.max(5, scene.h * 0.035);
  const accent = theme.particle || GREEN;
  g.roundRect(x, y, w, h, h / 2).stroke({ width: 1, color: theme.line, alpha: 0.42 });
  g.roundRect(x + 1, y + 1, Math.max(2, w * t - 2), h - 2, (h - 2) / 2)
    .fill({ color: accent, alpha: 0.42 + t * 0.34 + pulse * 0.06 });
  container.addChild(g);
}

// --- food_pantry variant (food insecurity: provision = 1 - t) ---

function resolveVariant(theme) {
  if (theme?.variant) return theme.variant;
  return "food_stall";
}

function drawPantryMonitor(container, bounds, theme, t, now) {
  const box = getBox(bounds);
  const scene = {
    x: box.x + 16,
    y: box.y + 16,
    w: box.w - 32,
    h: box.h - 28,
  };
  const pulse = 0.5 + 0.5 * Math.sin(now * 0.0045);
  const provision = clamp01(1 - t);
  drawPantryCabinet(container, scene, theme, provision);
  drawPantryLamp(container, scene, theme, provision, pulse);
  drawPantryJars(container, scene, theme, provision, pulse);
  drawProvisionMeter(container, scene, theme, provision, pulse);
}

// Cabinet frame + shelves. Geometry never depends on the value; only
// fill alphas breathe slightly with the ambient provision level.
function drawPantryCabinet(container, scene, theme, provision) {
  const g = new Graphics();
  g.rect(scene.x, scene.y, scene.w, scene.h).fill({ color: 0x0c1422, alpha: 0.5 });
  const cab = pantryCabinetBox(scene);
  // cabinet back panel
  g.roundRect(cab.x, cab.y, cab.w, cab.h, 3).fill({ color: 0x101425, alpha: 0.72 });
  g.roundRect(cab.x, cab.y, cab.w, cab.h, 3)
    .stroke({ width: 2, color: theme.line, alpha: 0.45 });
  // side walls (inner shading)
  g.rect(cab.x + 2, cab.y + 2, 2, cab.h - 4).fill({ color: theme.lineSoft, alpha: 0.35 });
  g.rect(cab.x + cab.w - 4, cab.y + 2, 2, cab.h - 4).fill({ color: theme.lineSoft, alpha: 0.35 });
  // shelves
  for (let s = 0; s < 3; s += 1) {
    const yy = pantryShelfY(cab, s);
    g.rect(cab.x + 3, yy, cab.w - 6, 2)
      .fill({ color: theme.lineSoft, alpha: 0.5 + provision * 0.15 });
  }
  // floor line under the cabinet
  g.rect(scene.x + scene.w * 0.05, cab.y + cab.h + 3, scene.w * 0.9, 1)
    .fill({ color: theme.lineSoft, alpha: 0.4 });
  container.addChild(g);
}

// Small kitchen lamp above the cabinet; its glow fades as provision drops.
function drawPantryLamp(container, scene, theme, provision, pulse) {
  const g = new Graphics();
  const cab = pantryCabinetBox(scene);
  const lx = cab.x + cab.w / 2;
  const ly = scene.y + scene.h * 0.045;
  // cord + shade (fixed)
  g.rect(lx - 0.5, scene.y, 1, ly - scene.y).fill({ color: theme.line, alpha: 0.35 });
  g.moveTo(lx - 5, ly + 4).lineTo(lx, ly).lineTo(lx + 5, ly + 4).lineTo(lx - 5, ly + 4)
    .fill({ color: theme.lineSoft, alpha: 0.8 });
  // bulb + glow (dims with insecurity)
  const lit = 0.15 + provision * 0.5 + pulse * 0.05;
  g.circle(lx, ly + 5, 1.6).fill({ color: theme.white, alpha: 0.25 + provision * 0.55 });
  g.circle(lx, ly + 6, 10 + provision * 8).fill({ color: AMBER, alpha: lit * 0.14 });
  container.addChild(g);
}

// Jars/provisions on the shelves. Slots empty from the top shelf down as
// insecurity rises; empty slots get the faint cross marker (same language
// as the empty crates in the stall variant).
function drawPantryJars(container, scene, theme, provision, pulse) {
  const g = new Graphics();
  const cab = pantryCabinetBox(scene);
  const cols = 6;
  const rows = 3;
  const totalSlots = cols * rows;
  const filled = Math.round(provision * totalSlots);
  const palette = [GREEN, AMBER, CYAN];
  const slotW = (cab.w - 14) / cols;
  const jarW = Math.max(4, slotW * 0.62);
  const jarH = Math.max(7, pantryShelfGap(cab) * 0.52);

  let index = 0; // fill order: bottom shelf first, left to right
  for (let s = rows - 1; s >= 0; s -= 1) {
    const shelfY = pantryShelfY(cab, s);
    for (let c = 0; c < cols; c += 1) {
      const cx = cab.x + 7 + c * slotW + (slotW - jarW) / 2;
      const jy = shelfY - jarH - 1;
      const isFilled = index < filled;
      const fade = clamp01((filled - index) / 2); // the last jars look sparse
      if (isFilled) {
        const color = palette[(c + s) % palette.length];
        g.roundRect(cx, jy, jarW, jarH, 1.5)
          .fill({ color, alpha: 0.32 + fade * 0.38 + pulse * 0.04 });
        // lid
        g.rect(cx + jarW * 0.18, jy - 2, jarW * 0.64, 2)
          .fill({ color: theme.lineSoft, alpha: 0.6 + fade * 0.3 });
        // highlight
        g.rect(cx + 1, jy + 1.5, 1.5, jarH * 0.55)
          .fill({ color: theme.white, alpha: 0.18 + fade * 0.25 });
      } else {
        // empty slot marker: faint cross on the shelf back
        const mx = cx + jarW / 2;
        const my = jy + jarH * 0.55;
        g.moveTo(mx - jarW * 0.28, my).lineTo(mx + jarW * 0.28, my)
          .stroke({ width: 1, color: theme.line, alpha: 0.2 });
      }
      index += 1;
    }
  }
  container.addChild(g);
}

// Provision meter: mirrors the stall's freshness meter but tracks the
// inverted value, so "full bar" always reads as a well-stocked pantry.
function drawProvisionMeter(container, scene, theme, provision, pulse) {
  const g = new Graphics();
  const x = scene.x + scene.w * 0.1;
  const y = scene.y + scene.h * 0.93;
  const w = scene.w * 0.8;
  const h = Math.max(5, scene.h * 0.035);
  g.roundRect(x, y, w, h, h / 2).stroke({ width: 1, color: theme.line, alpha: 0.42 });
  g.roundRect(x + 1, y + 1, Math.max(2, w * provision - 2), h - 2, (h - 2) / 2)
    .fill({ color: AMBER, alpha: 0.42 + provision * 0.34 + pulse * 0.06 });
  container.addChild(g);
}

function pantryCabinetBox(scene) {
  return {
    x: scene.x + scene.w * 0.12,
    y: scene.y + scene.h * 0.14,
    w: scene.w * 0.76,
    h: scene.h * 0.7,
  };
}

function pantryShelfY(cab, shelfIndex) {
  // 3 shelves evenly spaced inside the cabinet (shelf 0 is the top one)
  return cab.y + cab.h * (0.3 + shelfIndex * 0.3);
}

function pantryShelfGap(cab) {
  return cab.h * 0.3;
}

// --- shared LCD chrome (mirrors social renderer) ---

function drawFrame(container, bounds, theme) {
  const g = new Graphics();
  const box = getBox(bounds);
  g.roundRect(box.x, box.y, box.w, box.h, 8).fill({ color: theme.lcd, alpha: 0.88 });
  g.roundRect(box.x, box.y, box.w, box.h, 8).stroke({ width: 2, color: theme.line, alpha: 0.75 });
  g.roundRect(box.x + 8, box.y + 8, box.w - 16, box.h - 16, 5)
    .stroke({ width: 1, color: theme.lineSoft, alpha: 0.72 });
  container.addChild(g);
}

function drawGrid(container, bounds, theme) {
  const g = new Graphics();
  const box = getBox(bounds);
  const left = box.x + 20;
  const right = box.x + box.w - 20;
  const top = box.y + 20;
  const bottom = box.y + box.h - 24;
  for (let i = 1; i < 5; i += 1) {
    const y = top + (bottom - top) * (i / 5);
    g.moveTo(left, y).lineTo(right, y).stroke({ width: 1, color: theme.grid, alpha: 0.45 });
  }
  container.addChild(g);
}

function getBox(bounds) {
  return {
    x: bounds.width * 0.08,
    y: bounds.height * 0.13,
    w: bounds.width * 0.84,
    h: bounds.height * 0.68,
  };
}

function sameBounds(a, b) {
  return b && a.width === b.width && a.height === b.height;
}

function destroyChildren(container) {
  if (!container) return;
  for (const child of container.removeChildren()) {
    try { child.destroy({ children: true }); } catch (_) {}
  }
}
