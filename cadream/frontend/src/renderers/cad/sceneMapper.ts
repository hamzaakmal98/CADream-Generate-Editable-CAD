import type { Affine2D, RenderDoc, RenderEntity } from "../../types/cad";
import {
  adaptiveArcSegments,
  adaptiveCircleSegments,
  arcPoints,
  composeTransforms,
  identityTransform,
  insertTransform,
  transformPoint,
} from "../../utils/cadGeometry";
import type { CadPrimitive, CadScene } from "./types";

const COLOR_BLACK = 0x1f2937;
const COLOR_RED = 0xdc2626;

function mapEntity(
  ent: RenderEntity,
  out: CadPrimitive[],
  doc: RenderDoc | null,
  hiddenLayers: Record<string, boolean>,
  scale: number,
  arcPixelsPerSegment: number,
  arcMaxSegments: number,
  xform: Affine2D = identityTransform(),
  depth = 0,
  chain: string[] = []
) {
  if (depth > 10) return;
  if (hiddenLayers[ent.layer]) return;

  if (ent.type === "LINE") {
    const p1 = transformPoint(ent.p1[0], ent.p1[1], xform);
    const p2 = transformPoint(ent.p2[0], ent.p2[1], xform);
    out.push({
      type: "line",
      points: [p1[0], p1[1], p2[0], p2[1]],
      stroke: COLOR_BLACK,
      strokeWidth: 1,
    });
    return;
  }

  if (ent.type === "LWPOLYLINE") {
    const points = ent.points.map((point) => transformPoint(point[0], point[1], xform));
    out.push({
      type: "polyline",
      points,
      closed: ent.closed,
      stroke: COLOR_BLACK,
      strokeWidth: 1,
    });
    return;
  }

  if (ent.type === "CIRCLE") {
    const segs = adaptiveCircleSegments(ent.r, scale, arcPixelsPerSegment, arcMaxSegments);
    const points = arcPoints(ent.center[0], ent.center[1], ent.r, 0, 360, segs).map((point) =>
      transformPoint(point[0], point[1], xform)
    );
    out.push({
      type: "polyline",
      points,
      closed: true,
      stroke: COLOR_RED,
      strokeWidth: 1,
    });
    return;
  }

  if (ent.type === "ARC") {
    const segs = adaptiveArcSegments(
      ent.r,
      ent.start_angle,
      ent.end_angle,
      scale,
      arcPixelsPerSegment,
      arcMaxSegments
    );
    const points = arcPoints(
      ent.center[0],
      ent.center[1],
      ent.r,
      ent.start_angle,
      ent.end_angle,
      segs
    ).map((point) => transformPoint(point[0], point[1], xform));

    out.push({
      type: "polyline",
      points,
      closed: false,
      stroke: COLOR_BLACK,
      strokeWidth: 1,
    });
    return;
  }

  if (ent.type === "TEXT" || ent.type === "MTEXT") {
    const p = transformPoint(ent.pos[0], ent.pos[1], xform);
    out.push({
      type: "text",
      text: ent.text,
      x: p[0],
      y: p[1],
      fontSize: Math.max(8, ent.height),
      fill: COLOR_BLACK,
    });
    return;
  }

  if (ent.type === "INSERT") {
    if (chain.includes(ent.name)) return;
    const block = doc?.blocks?.[ent.name];
    if (!block || block.length === 0) return;
    const nextTransform = composeTransforms(xform, insertTransform(ent));

    for (const blockEntity of block) {
      mapEntity(
        blockEntity,
        out,
        doc,
        hiddenLayers,
        scale,
        arcPixelsPerSegment,
        arcMaxSegments,
        nextTransform,
        depth + 1,
        [...chain, ent.name]
      );
    }
  }
}

export function buildCadScene(input: {
  entities: RenderEntity[];
  doc: RenderDoc | null;
  hiddenLayers: Record<string, boolean>;
  scale: number;
  arcPixelsPerSegment: number;
  arcMaxSegments: number;
}): CadScene {
  const primitives: CadPrimitive[] = [];

  for (const ent of input.entities) {
    mapEntity(
      ent,
      primitives,
      input.doc,
      input.hiddenLayers,
      input.scale,
      input.arcPixelsPerSegment,
      input.arcMaxSegments
    );
  }

  return { primitives };
}
