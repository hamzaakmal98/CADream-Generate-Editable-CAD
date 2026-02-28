import { useMemo, useRef, useState, useEffect } from "react";
import { Stage, Layer, Line, Circle, Text, Group } from "react-konva";

type RenderLayer = { name: string; color?: number; linetype?: string };
type RenderEntity =
  | { type: "LINE"; layer: string; p1: number[]; p2: number[] }
  | { type: "LWPOLYLINE"; layer: string; points: number[][]; closed: boolean }
  | { type: "CIRCLE"; layer: string; center: number[]; r: number }
  | {
      type: "ARC";
      layer: string;
      center: number[];
      r: number;
      start_angle: number;
      end_angle: number;
    }
  | {
      type: "TEXT" | "MTEXT";
      layer: string;
      text: string;
      pos: number[];
      height: number;
    }
  | {
      type: "INSERT";
      layer: string;
      name: string;
      pos: number[];
      rotation: number;
      xscale: number;
      yscale: number;
    };

type RenderDoc = {
  layers: RenderLayer[];
  entities: RenderEntity[];
  bounds: null | { min: number[]; max: number[] };
  blocks?: Record<string, RenderEntity[]>;
};

type Affine2D = {
  a: number;
  b: number;
  c: number;
  d: number;
  tx: number;
  ty: number;
};

export default function App() {
  const stageRef = useRef<any>(null);
  const [doc, setDoc] = useState<RenderDoc | null>(null);
  const [hiddenLayers, setHiddenLayers] = useState<Record<string, boolean>>({});
  const [scale, setScale] = useState(1);
  const [pos, setPos] = useState({ x: 20, y: 20 });

  const [stageSize, setStageSize] = useState({
    w: window.innerWidth - 260,
    h: window.innerHeight,
  });

  useEffect(() => {
    const onResize = () =>
      setStageSize({ w: window.innerWidth - 260, h: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const visibleEntities = useMemo(() => {
    if (!doc) return [];
    return doc.entities.filter((e) => !hiddenLayers[e.layer]);
  }, [doc, hiddenLayers]);

 async function onUpload(file: File) {
  const fd = new FormData();
  fd.append("file", file);

  const res = await fetch("/api/dxf/parse", {
    method: "POST",
    body: fd,
  });

  const data = (await res.json()) as RenderDoc;

  console.log("bounds", data.bounds, "entities", data.entities.length);

  const ib2 = boundsFromInserts(data.entities);
  console.log("insertBounds", ib2);

  setDoc(data);

  const inserts = data.entities.filter((e) => e.type === "INSERT") as Extract<
  RenderEntity,
  { type: "INSERT" }
  >[];

  console.log(
    "first 5 inserts",
    inserts.slice(0, 5).map((i) => ({ name: i.name, layer: i.layer, pos: i.pos }))
  );
  (window as any).__doc = data;

  if (ib2) fitToBounds(ib2);
  else if (data.bounds) fitToBounds(data.bounds);
}

  function toggleLayer(name: string) {
    setHiddenLayers((prev) => ({ ...prev, [name]: !prev[name] }));
  }

  function onWheel(e: any) {
    e.evt.preventDefault();
    const stage = stageRef.current;
    const oldScale = scale;

    const pointer = stage.getPointerPosition();
    if (!pointer) return;

    const mousePointTo = {
      x: (pointer.x - pos.x) / oldScale,
      y: (pointer.y - pos.y) / oldScale,
    };

    const direction = e.evt.deltaY > 0 ? 1 : -1;
    const factor = 1.08;
    const newScale = direction > 0 ? oldScale / factor : oldScale * factor;

    setScale(newScale);
    setPos({
      x: pointer.x - mousePointTo.x * newScale,
      y: pointer.y - mousePointTo.y * newScale,
    });
  }

  function identityTransform(): Affine2D {
    return { a: 1, b: 0, c: 0, d: 1, tx: 0, ty: 0 };
  }

  function insertTransform(ins: Extract<RenderEntity, { type: "INSERT" }>): Affine2D {
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

  function composeTransforms(parent: Affine2D, local: Affine2D): Affine2D {
    return {
      a: parent.a * local.a + parent.b * local.c,
      b: parent.a * local.b + parent.b * local.d,
      c: parent.c * local.a + parent.d * local.c,
      d: parent.c * local.b + parent.d * local.d,
      tx: parent.a * local.tx + parent.b * local.ty + parent.tx,
      ty: parent.c * local.tx + parent.d * local.ty + parent.ty,
    };
  }

  function transformPoint(x: number, y: number, xform: Affine2D) {
    return [xform.a * x + xform.b * y + xform.tx, xform.c * x + xform.d * y + xform.ty];
  }

  function arcPoints(
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
  
  function fitToBounds(bounds: { min: number[]; max: number[] }) {
    const [minX, minY] = bounds.min;
    const [maxX, maxY] = bounds.max;

    const viewportW = stageSize.w;
    const viewportH = stageSize.h;

    const dx = maxX - minX;
    const dy = maxY - minY;

    if (dx <= 0 || dy <= 0) return;

    const scaleX = viewportW / dx;
    const scaleY = viewportH / dy;
    const newScale = Math.min(scaleX, scaleY) * 0.9;

    setScale(newScale);

    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;

    setPos({
      x: viewportW / 2 - centerX * newScale + 260,
      y: viewportH / 2 - -centerY * newScale,
    });
  }

  function boundsFromInserts(entities: RenderEntity[]) {
    const inserts = entities.filter((e) => e.type === "INSERT") as Extract<
      RenderEntity,
      { type: "INSERT" }
    >[];
    if (!inserts.length) return null;

    let minX = Infinity,
      minY = Infinity,
      maxX = -Infinity,
      maxY = -Infinity;

    for (const ins of inserts) {
      const x = ins.pos[0];
      const y = ins.pos[1];
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    }

    const padX = (maxX - minX) * 0.1 || 1000;
    const padY = (maxY - minY) * 0.1 || 1000;

    return { min: [minX - padX, minY - padY], max: [maxX + padX, maxY + padY] };
  }

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "system-ui" }}>
      <div
        style={{
          width: 260,
          borderRight: "1px solid #ddd",
          padding: 12,
          overflow: "auto",
        }}
      >
        <h3 style={{ marginTop: 0 }}>CADream</h3>

        <input
          type="file"
          accept=".dxf"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onUpload(f);
          }}
        />

        <button
          style={{ marginTop: 8, padding: "6px 10px" }}
          disabled={!doc?.bounds}
          onClick={() => doc?.bounds && fitToBounds(doc.bounds)}
        >
          Fit to drawing
        </button>

        <button
          style={{ marginTop: 8, padding: "6px 10px" }}
          disabled={!doc}
          onClick={() => {
            if (!doc) return;
            const newHidden: Record<string, boolean> = {};
            for (const l of doc.layers) newHidden[l.name] = true;
            newHidden["Obstruction"] = false;
            newHidden["0"] = false;
            setHiddenLayers(newHidden);
          }}
        >
          Solo: Obstruction
        </button>

        <hr />

        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
          Layers
        </div>
        {!doc && (
          <div style={{ fontSize: 12, color: "#666" }}>
            Upload a DXF to begin.
          </div>
        )}

        {doc?.layers?.slice(0, 400).map((l) => (
          <label
            key={l.name}
            style={{ display: "block", fontSize: 12, cursor: "pointer" }}
          >
            <input
              type="checkbox"
              checked={!hiddenLayers[l.name]}
              onChange={() => toggleLayer(l.name)}
              style={{ marginRight: 6 }}
            />
            {l.name}
          </label>
        ))}
      </div>

      <div
        style={{
          position: "absolute",
          right: 10,
          top: 10,
          background: "white",
          padding: 6,
          border: "1px solid #ddd",
          fontSize: 12,
        }}
      >
        {doc ? `Entities: ${doc.entities.length}` : "No DXF loaded"}
      </div>

      <div style={{ flex: 1 }}>
        <Stage
          ref={stageRef}
          width={stageSize.w}
          height={stageSize.h}
          draggable
          x={pos.x}
          y={pos.y}
          scaleX={scale}
          scaleY={scale}
          onWheel={onWheel}
          onDragEnd={(e) => setPos({ x: e.target.x(), y: e.target.y() })}
        >
          <Layer>

            <Line points={[0, 0, 200000, 0]} stroke="red" strokeWidth={5} />
            <Line points={[0, 0, 0, 200000]} stroke="red" strokeWidth={5} />
            <Text x={0} y={0} text="ORIGIN" fontSize={40} fill="red" />

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
                  <Line
                    key={idx}
                    points={pts}
                    stroke="black"
                    strokeWidth={1}
                    closed={ent.closed}
                  />
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

            })}
          </Layer>
        </Stage>
      </div>
    </div>
  );
}
