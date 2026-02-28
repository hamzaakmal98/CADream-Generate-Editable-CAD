import type { Affine2D, RenderEntity } from "../types/cad";

export type Bounds2D = {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
};

export function identityTransform(): Affine2D {
  return { a: 1, b: 0, c: 0, d: 1, tx: 0, ty: 0 };
}

export function insertTransform(ins: Extract<RenderEntity, { type: "INSERT" }>): Affine2D {
  const rad = (ins.rotation * Math.PI) / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);

  return {
    a: cos * ins.xscale,
    b: -sin * ins.yscale,
    c: sin * ins.xscale,
    d: cos * ins.yscale,
    tx: ins.pos[0],
    ty: ins.pos[1],
  };
}

export function composeTransforms(parent: Affine2D, local: Affine2D): Affine2D {
  return {
    a: parent.a * local.a + parent.b * local.c,
    b: parent.a * local.b + parent.b * local.d,
    c: parent.c * local.a + parent.d * local.c,
    d: parent.c * local.b + parent.d * local.d,
    tx: parent.a * local.tx + parent.b * local.ty + parent.tx,
    ty: parent.c * local.tx + parent.d * local.ty + parent.ty,
  };
}

export function transformPoint(x: number, y: number, xform: Affine2D) {
  return [xform.a * x + xform.b * y + xform.tx, xform.c * x + xform.d * y + xform.ty];
}

function normalizedArcSpanDeg(startDeg: number, endDeg: number) {
  const span = ((endDeg - startDeg) % 360 + 360) % 360;
  return span === 0 ? 360 : span;
}

export function adaptiveArcSegments(
  radiusWorld: number,
  startDeg: number,
  endDeg: number,
  zoomScale: number,
  maxPixelsPerSegment = 10,
  maxSegments = 512
) {
  const safeScale = Math.max(Math.abs(zoomScale), 0.0001);
  const spanDeg = normalizedArcSpanDeg(startDeg, endDeg);
  const spanRad = (spanDeg * Math.PI) / 180;
  const arcLengthPx = Math.abs(radiusWorld) * safeScale * spanRad;
  const estimated = Math.ceil(arcLengthPx / Math.max(2, maxPixelsPerSegment));
  const minSegments = spanDeg >= 359.999 ? 24 : 8;
  return Math.max(minSegments, Math.min(Math.max(minSegments, maxSegments), estimated));
}

export function adaptiveCircleSegments(
  radiusWorld: number,
  zoomScale: number,
  maxPixelsPerSegment = 10,
  maxSegments = 512
) {
  return adaptiveArcSegments(radiusWorld, 0, 360, zoomScale, maxPixelsPerSegment, maxSegments);
}

export function arcPoints(
  centerX: number,
  centerY: number,
  radius: number,
  startDeg: number,
  endDeg: number,
  segments = 48
) {
  let start = (startDeg * Math.PI) / 180;
  let end = (endDeg * Math.PI) / 180;
  if (end < start) end += Math.PI * 2;

  const step = (end - start) / Math.max(1, segments);
  const pts: number[][] = [];
  for (let i = 0; i <= segments; i++) {
    const a = start + step * i;
    pts.push([centerX + radius * Math.cos(a), centerY + radius * Math.sin(a)]);
  }
  return pts;
}

export function getViewportWorldBounds(
  stageSize: { w: number; h: number },
  pos: { x: number; y: number },
  scale: number,
  padScreenPx = 80
): Bounds2D {
  const safeScale = Math.max(Math.abs(scale), 0.0001);
  const padWorld = padScreenPx / safeScale;
  const left = (0 - pos.x) / safeScale;
  const right = (stageSize.w - pos.x) / safeScale;
  const top = (pos.y - 0) / safeScale;
  const bottom = (pos.y - stageSize.h) / safeScale;
  return {
    minX: Math.min(left, right) - padWorld,
    maxX: Math.max(left, right) + padWorld,
    minY: Math.min(bottom, top) - padWorld,
    maxY: Math.max(bottom, top) + padWorld,
  };
}

export function boundsIntersect(a: Bounds2D, b: Bounds2D) {
  return !(a.maxX < b.minX || a.minX > b.maxX || a.maxY < b.minY || a.minY > b.maxY);
}

export function pointInBounds(point: number[], bounds: Bounds2D) {
  return (
    point[0] >= bounds.minX &&
    point[0] <= bounds.maxX &&
    point[1] >= bounds.minY &&
    point[1] <= bounds.maxY
  );
}

export function transformBounds(bounds: Bounds2D, xform: Affine2D): Bounds2D {
  const p1 = transformPoint(bounds.minX, bounds.minY, xform);
  const p2 = transformPoint(bounds.minX, bounds.maxY, xform);
  const p3 = transformPoint(bounds.maxX, bounds.minY, xform);
  const p4 = transformPoint(bounds.maxX, bounds.maxY, xform);
  const xs = [p1[0], p2[0], p3[0], p4[0]];
  const ys = [p1[1], p2[1], p3[1], p4[1]];
  return {
    minX: Math.min(...xs),
    minY: Math.min(...ys),
    maxX: Math.max(...xs),
    maxY: Math.max(...ys),
  };
}

export function entityBounds(ent: RenderEntity): Bounds2D | null {
  const cached = entityBoundsCache.get(ent);
  if (cached !== undefined) return cached;

  let result: Bounds2D | null = null;

  if (ent.type === "LINE") {
    result = {
      minX: Math.min(ent.p1[0], ent.p2[0]),
      minY: Math.min(ent.p1[1], ent.p2[1]),
      maxX: Math.max(ent.p1[0], ent.p2[0]),
      maxY: Math.max(ent.p1[1], ent.p2[1]),
    };
    entityBoundsCache.set(ent, result);
    return result;
  }
  if (ent.type === "LWPOLYLINE") {
    if (ent.points.length === 0) {
      entityBoundsCache.set(ent, null);
      return null;
    }
    const xs = ent.points.map((p) => p[0]);
    const ys = ent.points.map((p) => p[1]);
    result = {
      minX: Math.min(...xs),
      minY: Math.min(...ys),
      maxX: Math.max(...xs),
      maxY: Math.max(...ys),
    };
    entityBoundsCache.set(ent, result);
    return result;
  }
  if (ent.type === "CIRCLE" || ent.type === "ARC") {
    result = {
      minX: ent.center[0] - ent.r,
      minY: ent.center[1] - ent.r,
      maxX: ent.center[0] + ent.r,
      maxY: ent.center[1] + ent.r,
    };
    entityBoundsCache.set(ent, result);
    return result;
  }
  if (ent.type === "TEXT" || ent.type === "MTEXT") {
    const width = Math.max(ent.height, ent.text.length * ent.height * 0.6);
    result = {
      minX: ent.pos[0],
      minY: ent.pos[1],
      maxX: ent.pos[0] + width,
      maxY: ent.pos[1] + ent.height,
    };
    entityBoundsCache.set(ent, result);
    return result;
  }
  if (ent.type === "INSERT") {
    result = {
      minX: ent.pos[0],
      minY: ent.pos[1],
      maxX: ent.pos[0],
      maxY: ent.pos[1],
    };
    entityBoundsCache.set(ent, result);
    return result;
  }

  entityBoundsCache.set(ent, null);
  return null;
}

const entityBoundsCache = new WeakMap<RenderEntity, Bounds2D | null>();

export function boundsFromInsertEntities(entities: RenderEntity[]) {
  const inserts = entities.filter((e) => e.type === "INSERT") as Extract<
    RenderEntity,
    { type: "INSERT" }
  >[];
  if (!inserts.length) return null;

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  for (const ins of inserts) {
    minX = Math.min(minX, ins.pos[0]);
    minY = Math.min(minY, ins.pos[1]);
    maxX = Math.max(maxX, ins.pos[0]);
    maxY = Math.max(maxY, ins.pos[1]);
  }

  const padX = (maxX - minX) * 0.1 || 1000;
  const padY = (maxY - minY) * 0.1 || 1000;

  return {
    min: [minX - padX, minY - padY],
    max: [maxX + padX, maxY + padY],
  };
}

export function computeBessMarkerSize(
  bounds: { min: number[]; max: number[] } | null,
  sizeFactor: number
) {
  if (!bounds) return 120 * sizeFactor;
  const dx = Math.abs(bounds.max[0] - bounds.min[0]);
  const dy = Math.abs(bounds.max[1] - bounds.min[1]);
  const span = Math.max(dx, dy);
  if (!isFinite(span) || span <= 0) return 120 * sizeFactor;
  const baseSize = Math.max(30, Math.min(500, span * 0.006));
  return baseSize * sizeFactor;
}

function quantile(sortedValues: number[], q: number) {
  if (sortedValues.length === 0) return 0;
  if (sortedValues.length === 1) return sortedValues[0];
  const clampedQ = Math.min(1, Math.max(0, q));
  const idx = (sortedValues.length - 1) * clampedQ;
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  if (lo === hi) return sortedValues[lo];
  const t = idx - lo;
  return sortedValues[lo] * (1 - t) + sortedValues[hi] * t;
}

function shortestInterval(sortedValues: number[], fraction: number) {
  if (sortedValues.length === 0) return { min: 0, max: 0 };
  const n = sortedValues.length;
  const windowSize = Math.max(2, Math.min(n, Math.floor(n * Math.min(1, Math.max(0.1, fraction)))));
  let bestStart = 0;
  let bestEnd = windowSize - 1;
  let bestWidth = sortedValues[bestEnd] - sortedValues[bestStart];

  for (let i = 1; i + windowSize - 1 < n; i++) {
    const j = i + windowSize - 1;
    const width = sortedValues[j] - sortedValues[i];
    if (width < bestWidth) {
      bestWidth = width;
      bestStart = i;
      bestEnd = j;
    }
  }

  return {
    min: sortedValues[bestStart],
    max: sortedValues[bestEnd],
  };
}

export function estimateStructureBounds(entities: RenderEntity[]) {
  const xs: number[] = [];
  const ys: number[] = [];
  const points: number[][] = [];
  const maxPoints = 120000;

  function pushPoint(x: number, y: number) {
    if (!isFinite(x) || !isFinite(y)) return;
    xs.push(x);
    ys.push(y);
    if (points.length < maxPoints) points.push([x, y]);
  }

  for (const ent of entities) {
    if (ent.type === "LINE") {
      pushPoint(ent.p1[0], ent.p1[1]);
      pushPoint(ent.p2[0], ent.p2[1]);
      continue;
    }

    if (ent.type === "LWPOLYLINE") {
      for (const point of ent.points) {
        pushPoint(point[0], point[1]);
      }
      continue;
    }

    if (ent.type === "CIRCLE" || ent.type === "ARC") {
      pushPoint(ent.center[0] - ent.r, ent.center[1]);
      pushPoint(ent.center[0] + ent.r, ent.center[1]);
      pushPoint(ent.center[0], ent.center[1] - ent.r);
      pushPoint(ent.center[0], ent.center[1] + ent.r);
      continue;
    }

    if (ent.type === "INSERT") {
      pushPoint(ent.pos[0], ent.pos[1]);
    }
  }

  if (xs.length < 4 || ys.length < 4) return null;

  xs.sort((a, b) => a - b);
  ys.sort((a, b) => a - b);

  const rawMinX = xs[0];
  const rawMaxX = xs[xs.length - 1];
  const rawMinY = ys[0];
  const rawMaxY = ys[ys.length - 1];

  const enoughSamples = xs.length >= 80 && ys.length >= 80;
  const trimLow = enoughSamples ? 0.02 : 0;
  const trimHigh = enoughSamples ? 0.98 : 1;

  let minX = quantile(xs, trimLow);
  let maxX = quantile(xs, trimHigh);
  let minY = quantile(ys, trimLow);
  let maxY = quantile(ys, trimHigh);

  const rawDx = rawMaxX - rawMinX;
  const rawDy = rawMaxY - rawMinY;
  const dx = maxX - minX;
  const dy = maxY - minY;

  if (!isFinite(dx) || !isFinite(dy) || dx <= 0 || dy <= 0) {
    minX = rawMinX;
    maxX = rawMaxX;
    minY = rawMinY;
    maxY = rawMaxY;
  }

  if ((rawDx > 0 && dx < rawDx * 0.05) || (rawDy > 0 && dy < rawDy * 0.05)) {
    minX = rawMinX;
    maxX = rawMaxX;
    minY = rawMinY;
    maxY = rawMaxY;
  }

  if (points.length >= 300) {
    const xCore = shortestInterval(xs, 0.85);
    const yCore = shortestInterval(ys, 0.85);
    const coreMinX = xCore.min;
    const coreMaxX = xCore.max;
    const coreMinY = yCore.min;
    const coreMaxY = yCore.max;

    const inCore = points.reduce(
      (count, point) =>
        count + (point[0] >= coreMinX && point[0] <= coreMaxX && point[1] >= coreMinY && point[1] <= coreMaxY ? 1 : 0),
      0
    );

    const coreCoverage = inCore / points.length;
    const coreDx = coreMaxX - coreMinX;
    const coreDy = coreMaxY - coreMinY;

    if (
      coreCoverage >= 0.55 &&
      coreDx > 0 &&
      coreDy > 0 &&
      coreDx < dx * 0.8 &&
      coreDy < dy * 0.8
    ) {
      minX = coreMinX;
      maxX = coreMaxX;
      minY = coreMinY;
      maxY = coreMaxY;
    }
  }

  const padX = (maxX - minX) * 0.08 || 100;
  const padY = (maxY - minY) * 0.08 || 100;

  return {
    min: [minX - padX, minY - padY],
    max: [maxX + padX, maxY + padY],
  };
}
