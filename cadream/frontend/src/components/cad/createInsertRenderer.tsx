import { Group, Line, Text } from "react-konva";
import type { ReactNode } from "react";
import type { Affine2D, RenderDoc, RenderEntity } from "../../types/cad";
import {
  adaptiveArcSegments,
  adaptiveCircleSegments,
  arcPoints,
  type Bounds2D,
  boundsIntersect,
  composeTransforms,
  entityBounds,
  identityTransform,
  insertTransform,
  transformBounds,
  transformPoint,
} from "../../utils/cadGeometry";

type CreateInsertRendererArgs = {
  doc: RenderDoc | null;
  hiddenLayers: Record<string, boolean>;
  scale: number;
  safeScale: number;
  isHeavyScene: boolean;
  viewportWorld: Bounds2D;
  blockBoundsByName: Record<string, Bounds2D>;
  arcPixelsPerSegment: number;
  arcMaxSegments: number;
};

type InsertEntity = Extract<RenderEntity, { type: "INSERT" }>;

type RenderInsertBlock = (
  ins: InsertEntity,
  keyPrefix: string,
  parentXform?: Affine2D,
  depth?: number,
  chain?: string[]
) => ReactNode;

export function createInsertRenderer({
  doc,
  hiddenLayers,
  scale,
  safeScale,
  isHeavyScene,
  viewportWorld,
  blockBoundsByName,
  arcPixelsPerSegment,
  arcMaxSegments,
}: CreateInsertRendererArgs): RenderInsertBlock {
  function isEntityVisible(ent: RenderEntity, xform: Affine2D = identityTransform()) {
    const bounds = entityBounds(ent);
    if (!bounds) return true;
    const worldBounds = transformBounds(bounds, xform);
    if (!boundsIntersect(worldBounds, viewportWorld)) return false;

    if (isHeavyScene) {
      const wPx = Math.abs(worldBounds.maxX - worldBounds.minX) * safeScale;
      const hPx = Math.abs(worldBounds.maxY - worldBounds.minY) * safeScale;
      if (Math.max(wPx, hPx) < 0.7) return false;
    }

    return true;
  }

  function isInsertVisible(ins: InsertEntity, parentXform: Affine2D = identityTransform()) {
    const xform = composeTransforms(parentXform, insertTransform(ins));
    const blockBounds = blockBoundsByName[ins.name];
    if (!blockBounds) return isEntityVisible(ins, xform);
    const worldBounds = transformBounds(blockBounds, xform);
    return boundsIntersect(worldBounds, viewportWorld);
  }

  const renderInsertBlock: RenderInsertBlock = (
    ins,
    keyPrefix,
    parentXform = identityTransform(),
    depth = 0,
    chain: string[] = []
  ) => {
    if (depth > 10) return null;
    if (chain.includes(ins.name)) return null;
    if (!isInsertVisible(ins, parentXform)) return null;

    const xform = composeTransforms(parentXform, insertTransform(ins));
    const block = doc?.blocks?.[ins.name];
    if (!block || block.length === 0) {
      const p = transformPoint(0, 0, xform);
      const x = p[0];
      const y = -p[1];
      const size = 12 / scale;
      const fontSize = 12 / scale;

      return (
        <Group key={keyPrefix} listening={false}>
          <Line points={[x - size, y, x + size, y]} stroke="red" strokeWidth={2 / scale} />
          <Line points={[x, y - size, x, y + size]} stroke="red" strokeWidth={2 / scale} />
          <Text x={x + size + 2} y={y - size - 2} text={ins.name} fontSize={fontSize} />
        </Group>
      );
    }

    const avgScale = (Math.hypot(xform.a, xform.c) + Math.hypot(xform.b, xform.d)) / 2 || 1;

    return (
      <Group key={keyPrefix} listening={false}>
        {block.map((bEnt, bIdx) => {
          if (hiddenLayers[bEnt.layer]) return null;
          if (!isEntityVisible(bEnt, xform)) return null;

          if (bEnt.type === "LINE") {
            const p1 = transformPoint(bEnt.p1[0], bEnt.p1[1], xform);
            const p2 = transformPoint(bEnt.p2[0], bEnt.p2[1], xform);
            return (
              <Line
                key={`${keyPrefix}-b-${bIdx}`}
                points={[p1[0], -p1[1], p2[0], -p2[1]]}
                stroke="black"
                strokeWidth={1 / scale}
                listening={false}
                perfectDrawEnabled={false}
              />
            );
          }

          if (bEnt.type === "LWPOLYLINE") {
            const transformed = bEnt.points.map((p) => transformPoint(p[0], p[1], xform));
            const pts = transformed.flatMap((p) => [p[0], -p[1]]);
            if (bEnt.closed && transformed.length > 0) {
              pts.push(transformed[0][0], -transformed[0][1]);
            }
            return (
              <Line
                key={`${keyPrefix}-b-${bIdx}`}
                points={pts}
                stroke="black"
                strokeWidth={1 / scale}
                closed={bEnt.closed}
                listening={false}
                perfectDrawEnabled={false}
              />
            );
          }

          if (bEnt.type === "CIRCLE") {
            const segs = adaptiveCircleSegments(bEnt.r * avgScale, arcPixelsPerSegment, arcMaxSegments);
            const circlePts = arcPoints(bEnt.center[0], bEnt.center[1], bEnt.r, 0, 360, segs)
              .map((p) => transformPoint(p[0], p[1], xform))
              .flatMap((point) => [point[0], -point[1]]);
            if (circlePts.length < 4) return null;
            return (
              <Line
                key={`${keyPrefix}-b-${bIdx}`}
                points={circlePts}
                stroke="black"
                strokeWidth={1 / scale}
                closed
                listening={false}
                perfectDrawEnabled={false}
              />
            );
          }

          if (bEnt.type === "ARC") {
            const segs = adaptiveArcSegments(
              bEnt.r * avgScale,
              bEnt.start_angle,
              bEnt.end_angle,
              scale,
              arcPixelsPerSegment,
              arcMaxSegments
            );
            const arcPts = arcPoints(
              bEnt.center[0],
              bEnt.center[1],
              bEnt.r,
              bEnt.start_angle,
              bEnt.end_angle,
              segs
            )
              .map((p) => transformPoint(p[0], p[1], xform))
              .flatMap((point) => [point[0], -point[1]]);

            return (
              <Line
                key={`${keyPrefix}-b-${bIdx}`}
                points={arcPts}
                stroke="black"
                strokeWidth={1 / scale}
                listening={false}
                perfectDrawEnabled={false}
              />
            );
          }

          if (bEnt.type === "TEXT" || bEnt.type === "MTEXT") {
            const p = transformPoint(bEnt.pos[0], bEnt.pos[1], xform);
            return (
              <Text
                key={`${keyPrefix}-b-${bIdx}`}
                x={p[0]}
                y={-p[1]}
                text={bEnt.text}
                fontSize={Math.max(8 / scale, bEnt.height * avgScale)}
                listening={false}
              />
            );
          }

          if (bEnt.type === "INSERT") {
            return renderInsertBlock(
              bEnt,
              `${keyPrefix}-b-${bIdx}`,
              xform,
              depth + 1,
              [...chain, ins.name]
            );
          }

          return null;
        })}
      </Group>
    );
  };

  return renderInsertBlock;
}
