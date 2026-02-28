import { Circle, FastLayer, Group, Layer, Line, Stage, Text } from "react-konva";
import type Konva from "konva";
import { useMemo } from "react";
import type { Dispatch, RefObject, SetStateAction } from "react";
import type {
  Affine2D,
  BessPlacement,
  CablePath,
  PointOfInterconnection,
  RenderDoc,
  RenderEntity,
  ToolMode,
} from "../types/cad";
import {
  adaptiveArcSegments,
  adaptiveCircleSegments,
  arcPoints,
  type Bounds2D,
  boundsIntersect,
  composeTransforms,
  entityBounds,
  getViewportWorldBounds,
  identityTransform,
  insertTransform,
  transformBounds,
  transformPoint,
} from "../utils/cadGeometry";

type CadCanvasProps = {
  stageRef: RefObject<Konva.Stage | null>;
  stageSize: { w: number; h: number };
  pos: { x: number; y: number };
  scale: number;
  toolMode: ToolMode;
  visibleEntities: RenderEntity[];
  hiddenLayers: Record<string, boolean>;
  doc: RenderDoc | null;
  bessPlacements: BessPlacement[];
  cablePaths: CablePath[];
  draftCablePoints: number[][];
  poi: PointOfInterconnection | null;
  selectedCableId: number | null;
  selectedBessId: number | null;
  bessMarkerSize: number;
  poiMarkerSize: number;
  onWheel: (e: Konva.KonvaEventObject<WheelEvent>) => void;
  onStageMouseDown: (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => void;
  onStageDragEnd: (e: Konva.KonvaEventObject<Event>) => void;
  onSetSelectedBessId: (id: number | null) => void;
  onSetSelectedCableId: (id: number | null) => void;
  onUpdateSelectedCableStart: (point: number[]) => void;
  onSetBessPlacements: Dispatch<SetStateAction<BessPlacement[]>>;
};

export default function CadCanvas({
  stageRef,
  stageSize,
  pos,
  scale,
  toolMode,
  visibleEntities,
  hiddenLayers,
  doc,
  bessPlacements,
  cablePaths,
  draftCablePoints,
  poi,
  selectedCableId,
  selectedBessId,
  bessMarkerSize,
  poiMarkerSize,
  onWheel,
  onStageMouseDown,
  onStageDragEnd,
  onSetSelectedBessId,
  onSetSelectedCableId,
  onUpdateSelectedCableStart,
  onSetBessPlacements,
}: CadCanvasProps) {
  const selectedCable = cablePaths.find((c) => c.id === selectedCableId) ?? null;
  const viewportWorld = useMemo(
    () => getViewportWorldBounds(stageSize, pos, scale),
    [stageSize, pos, scale]
  );
  const isHeavyScene = useMemo(
    () => visibleEntities.length > 15000 || (doc?.entities.length ?? 0) > 20000,
    [visibleEntities.length, doc?.entities.length]
  );
  const arcPixelsPerSegment = isHeavyScene ? 20 : 10;
  const arcMaxSegments = isHeavyScene ? 128 : 512;
  const blockBoundsByName = useMemo(() => {
    const blocks = doc?.blocks;
    if (!blocks) return {} as Record<string, Bounds2D>;

    const next: Record<string, Bounds2D> = {};

    for (const [name, entities] of Object.entries(blocks)) {
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;

      for (const ent of entities) {
        const b = entityBounds(ent);
        if (!b) continue;
        minX = Math.min(minX, b.minX);
        minY = Math.min(minY, b.minY);
        maxX = Math.max(maxX, b.maxX);
        maxY = Math.max(maxY, b.maxY);
      }

      if (isFinite(minX) && isFinite(minY) && isFinite(maxX) && isFinite(maxY)) {
        next[name] = { minX, minY, maxX, maxY };
      }
    }

    return next;
  }, [doc?.blocks]);

  function isEntityVisible(ent: RenderEntity, xform: Affine2D = identityTransform()) {
    const bounds = entityBounds(ent);
    if (!bounds) return true;
    const worldBounds = transformBounds(bounds, xform);
    if (!boundsIntersect(worldBounds, viewportWorld)) return false;

    if (isHeavyScene) {
      const wPx = Math.abs(worldBounds.maxX - worldBounds.minX) * Math.max(Math.abs(scale), 0.0001);
      const hPx = Math.abs(worldBounds.maxY - worldBounds.minY) * Math.max(Math.abs(scale), 0.0001);
      if (Math.max(wPx, hPx) < 0.7) return false;
    }

    return true;
  }

  function isInsertVisible(ins: Extract<RenderEntity, { type: "INSERT" }>, parentXform: Affine2D = identityTransform()) {
    const xform = composeTransforms(parentXform, insertTransform(ins));
    const blockBounds = blockBoundsByName[ins.name];
    if (!blockBounds) return isEntityVisible(ins, xform);
    const worldBounds = transformBounds(blockBounds, xform);
    return boundsIntersect(worldBounds, viewportWorld);
  }

  function renderInsertBlock(
    ins: Extract<RenderEntity, { type: "INSERT" }>,
    keyPrefix: string,
    parentXform: Affine2D = identityTransform(),
    depth = 0,
    chain: string[] = []
  ) {
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

    const avgScale =
      (Math.hypot(xform.a, xform.c) + Math.hypot(xform.b, xform.d)) / 2 || 1;

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
            const segs = adaptiveCircleSegments(
              bEnt.r * avgScale,
              scale,
              arcPixelsPerSegment,
              arcMaxSegments
            );
            const circlePts = arcPoints(bEnt.center[0], bEnt.center[1], bEnt.r, 0, 360, segs)
              .map((p) => transformPoint(p[0], p[1], xform))
              .flatMap((p) => [p[0], -p[1]]);

            return (
              <Line
                key={`${keyPrefix}-b-${bIdx}`}
                points={circlePts}
                stroke="red"
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
              .flatMap((p) => [p[0], -p[1]]);

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
  }

  return (
    <div style={{ flex: 1 }}>
      <Stage
        ref={stageRef}
        width={stageSize.w}
        height={stageSize.h}
        draggable={toolMode === "pan"}
        x={pos.x}
        y={pos.y}
        scaleX={scale}
        scaleY={scale}
        onWheel={onWheel}
        onMouseDown={onStageMouseDown}
        onDragEnd={onStageDragEnd}
      >
        <FastLayer listening={false}>
          {visibleEntities.map((ent, idx) => {
            if (ent.type === "INSERT" && !isInsertVisible(ent)) return null;
            if (ent.type !== "INSERT" && !isEntityVisible(ent)) return null;

            if (ent.type === "LINE") {
              return (
                <Line
                  key={idx}
                  points={[ent.p1[0], -ent.p1[1], ent.p2[0], -ent.p2[1]]}
                  stroke="black"
                  strokeWidth={1}
                  listening={false}
                  perfectDrawEnabled={false}
                />
              );
            }
            if (ent.type === "LWPOLYLINE") {
              const pts = ent.points.flatMap((p) => [p[0], -p[1]]);
              if (ent.closed) pts.push(ent.points[0][0], -ent.points[0][1]);
              return (
                <Line
                  key={idx}
                  points={pts}
                  stroke="black"
                  strokeWidth={1}
                  closed={ent.closed}
                  listening={false}
                  perfectDrawEnabled={false}
                />
              );
            }
            if (ent.type === "CIRCLE") {
              const segs = adaptiveCircleSegments(
                ent.r,
                scale,
                arcPixelsPerSegment,
                arcMaxSegments
              );
              const circlePts = arcPoints(ent.center[0], ent.center[1], ent.r, 0, 360, segs).flatMap(
                (p) => [p[0], -p[1]]
              );
              return (
                <Line
                  key={idx}
                  points={circlePts}
                  stroke="red"
                  strokeWidth={1}
                  closed
                  listening={false}
                  perfectDrawEnabled={false}
                />
              );
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
              const arcPts = arcPoints(
                ent.center[0],
                ent.center[1],
                ent.r,
                ent.start_angle,
                ent.end_angle,
                segs
              ).flatMap((p) => [p[0], -p[1]]);
              return (
                <Line
                  key={idx}
                  points={arcPts}
                  stroke="black"
                  strokeWidth={1}
                  listening={false}
                  perfectDrawEnabled={false}
                />
              );
            }
            if (ent.type === "TEXT" || ent.type === "MTEXT") {
              return (
                <Text
                  key={idx}
                  x={ent.pos[0]}
                  y={-ent.pos[1]}
                  text={ent.text}
                  fontSize={Math.max(8, ent.height)}
                  listening={false}
                />
              );
            }
            if (ent.type === "INSERT") {
              return renderInsertBlock(ent, `ins-${idx}`);
            }
            return null;
          })}
        </FastLayer>

        <Layer>
          {cablePaths.map((cable) => {
            const pts = cable.points.flatMap((p) => [p[0], -p[1]]);
            const selected = cable.id === selectedCableId;

            return (
              <Line
                key={`cable-${cable.id}`}
                name="cable-path"
                points={pts}
                stroke={selected ? "#0057ff" : "#f97316"}
                strokeWidth={Math.max(2, 3 / scale)}
                hitStrokeWidth={20 / scale}
                lineCap="round"
                lineJoin="round"
                onClick={() => onSetSelectedCableId(cable.id)}
                onTap={() => onSetSelectedCableId(cable.id)}
              />
            );
          })}

          {draftCablePoints.length > 0 && (
            <Line
              points={draftCablePoints.flatMap((p) => [p[0], -p[1]])}
              stroke="#fb923c"
              strokeWidth={Math.max(2, 3 / scale)}
              dash={[30 / scale, 20 / scale]}
              lineCap="round"
              lineJoin="round"
            />
          )}

          {selectedCable && selectedCable.points.length > 0 && (
            <Circle
              x={selectedCable.points[0][0]}
              y={-selectedCable.points[0][1]}
              radius={Math.max(8, 10 / scale)}
              fill="#2563eb"
              stroke="white"
              strokeWidth={Math.max(2, 2 / scale)}
              draggable
              onDragEnd={(e: Konva.KonvaEventObject<Event>) => {
                onUpdateSelectedCableStart([e.target.x(), -e.target.y()]);
              }}
            />
          )}

          {poi && (
            <Group name="poi-marker" x={poi.x} y={-poi.y}>
              <Circle
                radius={poiMarkerSize}
                stroke="#7c3aed"
                strokeWidth={Math.max(4, poiMarkerSize * 0.12)}
                fill="rgba(124, 58, 237, 0.18)"
              />
              <Line
                points={[-poiMarkerSize, 0, poiMarkerSize, 0]}
                stroke="#7c3aed"
                strokeWidth={Math.max(4, poiMarkerSize * 0.12)}
              />
              <Line
                points={[0, -poiMarkerSize, 0, poiMarkerSize]}
                stroke="#7c3aed"
                strokeWidth={Math.max(4, poiMarkerSize * 0.12)}
              />
              <Text
                x={poiMarkerSize + 3}
                y={-poiMarkerSize - 4}
                text="POI"
                fill="#7c3aed"
                fontSize={Math.max(24, poiMarkerSize * 0.6)}
              />
            </Group>
          )}

          {bessPlacements.map((bess) => {
            const selected = bess.id === selectedBessId;
            const x = bess.x;
            const y = -bess.y;
            const size = bessMarkerSize;
            const markerStroke = Math.max(4, size * 0.12);
            const markerFont = Math.max(24, size * 0.6);

            return (
              <Group
                key={`bess-${bess.id}`}
                name="bess-marker"
                bessId={bess.id}
                x={x}
                y={y}
                draggable
                onClick={() => onSetSelectedBessId(bess.id)}
                onTap={() => onSetSelectedBessId(bess.id)}
                onDragEnd={(e: Konva.KonvaEventObject<Event>) => {
                  const nx = e.target.x();
                  const ny = -e.target.y();
                  onSetBessPlacements((prev) =>
                    prev.map((item) => (item.id === bess.id ? { ...item, x: nx, y: ny } : item))
                  );
                }}
              >
                <Circle
                  x={0}
                  y={0}
                  radius={size}
                  stroke={selected ? "#0057ff" : "#0b8f00"}
                  strokeWidth={markerStroke}
                  fill={selected ? "rgba(0, 87, 255, 0.18)" : "rgba(11, 143, 0, 0.18)"}
                />
                <Line
                  points={[-size, 0, size, 0]}
                  stroke={selected ? "#0057ff" : "#0b8f00"}
                  strokeWidth={markerStroke}
                />
                <Line
                  points={[0, -size, 0, size]}
                  stroke={selected ? "#0057ff" : "#0b8f00"}
                  strokeWidth={markerStroke}
                />
                <Text
                  x={size + 3}
                  y={-size - 4}
                  text={bess.label}
                  fontSize={markerFont}
                  fill={selected ? "#0057ff" : "#0b8f00"}
                />
              </Group>
            );
          })}
        </Layer>
      </Stage>
    </div>
  );
}
