import type { Affine2D, RenderEntity } from "../types/cad";

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
