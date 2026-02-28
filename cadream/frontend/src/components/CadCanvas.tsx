import { Circle, Group, Layer, Line, Stage, Text } from "react-konva";
import type Konva from "konva";
import type { Dispatch, RefObject, SetStateAction } from "react";
import type {
  Affine2D,
  BessPlacement,
  RenderDoc,
  RenderEntity,
  ToolMode,
} from "../types/cad";
import {
  arcPoints,
  composeTransforms,
  identityTransform,
  insertTransform,
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
  selectedBessId: number | null;
  bessMarkerSize: number;
  onWheel: (e: Konva.KonvaEventObject<WheelEvent>) => void;
  onStageMouseDown: (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => void;
  onStageDragEnd: (e: Konva.KonvaEventObject<Event>) => void;
  onSetSelectedBessId: (id: number | null) => void;
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
  selectedBessId,
  bessMarkerSize,
  onWheel,
  onStageMouseDown,
  onStageDragEnd,
  onSetSelectedBessId,
  onSetBessPlacements,
}: CadCanvasProps) {
  function renderInsertBlock(
    ins: Extract<RenderEntity, { type: "INSERT" }>,
    keyPrefix: string,
    parentXform: Affine2D = identityTransform(),
    depth = 0,
    chain: string[] = []
  ) {
    if (depth > 10) return null;
    if (chain.includes(ins.name)) return null;

    const xform = composeTransforms(parentXform, insertTransform(ins));
    const block = doc?.blocks?.[ins.name];
    if (!block || block.length === 0) {
      const p = transformPoint(0, 0, xform);
      const x = p[0];
      const y = -p[1];
      const size = 12 / scale;
      const fontSize = 12 / scale;

      return (
        <Group key={keyPrefix}>
          <Line points={[x - size, y, x + size, y]} stroke="red" strokeWidth={2 / scale} />
          <Line points={[x, y - size, x, y + size]} stroke="red" strokeWidth={2 / scale} />
          <Text x={x + size + 2} y={y - size - 2} text={ins.name} fontSize={fontSize} />
        </Group>
      );
    }

    const avgScale =
      (Math.hypot(xform.a, xform.c) + Math.hypot(xform.b, xform.d)) / 2 || 1;

    return (
      <Group key={keyPrefix}>
        {block.map((bEnt, bIdx) => {
          if (hiddenLayers[bEnt.layer]) return null;

          if (bEnt.type === "LINE") {
            const p1 = transformPoint(bEnt.p1[0], bEnt.p1[1], xform);
            const p2 = transformPoint(bEnt.p2[0], bEnt.p2[1], xform);
            return (
              <Line
                key={`${keyPrefix}-b-${bIdx}`}
                points={[p1[0], -p1[1], p2[0], -p2[1]]}
                stroke="black"
                strokeWidth={1 / scale}
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
              />
            );
          }

          if (bEnt.type === "CIRCLE") {
            const circlePts = arcPoints(bEnt.center[0], bEnt.center[1], bEnt.r, 0, 360, 64)
              .map((p) => transformPoint(p[0], p[1], xform))
              .flatMap((p) => [p[0], -p[1]]);

            return (
              <Line
                key={`${keyPrefix}-b-${bIdx}`}
                points={circlePts}
                stroke="red"
                strokeWidth={1 / scale}
                closed
              />
            );
          }

          if (bEnt.type === "ARC") {
            const arcPts = arcPoints(
              bEnt.center[0],
              bEnt.center[1],
              bEnt.r,
              bEnt.start_angle,
              bEnt.end_angle,
              40
            )
              .map((p) => transformPoint(p[0], p[1], xform))
              .flatMap((p) => [p[0], -p[1]]);

            return (
              <Line
                key={`${keyPrefix}-b-${bIdx}`}
                points={arcPts}
                stroke="black"
                strokeWidth={1 / scale}
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
        <Layer>
          {visibleEntities.map((ent, idx) => {
            if (ent.type === "LINE") {
              return (
                <Line
                  key={idx}
                  points={[ent.p1[0], -ent.p1[1], ent.p2[0], -ent.p2[1]]}
                  stroke="black"
                  strokeWidth={1}
                />
              );
            }
            if (ent.type === "LWPOLYLINE") {
              const pts = ent.points.flatMap((p) => [p[0], -p[1]]);
              if (ent.closed) pts.push(ent.points[0][0], -ent.points[0][1]);
              return (
                <Line key={idx} points={pts} stroke="black" strokeWidth={1} closed={ent.closed} />
              );
            }
            if (ent.type === "CIRCLE") {
              return (
                <Circle
                  key={idx}
                  x={ent.center[0]}
                  y={-ent.center[1]}
                  radius={ent.r}
                  stroke="red"
                  strokeWidth={1}
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
                />
              );
            }
            if (ent.type === "INSERT") {
              return renderInsertBlock(ent, `ins-${idx}`);
            }
            return null;
          })}

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
