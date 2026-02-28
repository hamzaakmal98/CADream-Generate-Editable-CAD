import { useEffect, useMemo, useRef, useState } from "react";
import type Konva from "konva";
import CadCanvas from "./components/CadCanvas";
import ControlPanel from "./components/ControlPanel";
import { SIDEBAR_WIDTH } from "./constants/ui";
import type {
  BessPlacement,
  RenderDoc,
  SitePlacementExport,
  ToolMode,
} from "./types/cad";
import { boundsFromInsertEntities, computeBessMarkerSize } from "./utils/cadGeometry";

export default function App() {
  const stageRef = useRef<Konva.Stage | null>(null);
  const nextBessIdRef = useRef(1);
  const [doc, setDoc] = useState<RenderDoc | null>(null);
  const [hiddenLayers, setHiddenLayers] = useState<Record<string, boolean>>({});
  const [scale, setScale] = useState(1);
  const [pos, setPos] = useState({ x: 20, y: 20 });
  const [toolMode, setToolMode] = useState<ToolMode>("pan");
  const [bessPlacements, setBessPlacements] = useState<BessPlacement[]>([]);
  const [selectedBessId, setSelectedBessId] = useState<number | null>(null);
  const [bessSizeFactor, setBessSizeFactor] = useState(1);
  const [sourceDxfName, setSourceDxfName] = useState<string | null>(null);

  const [stageSize, setStageSize] = useState({
    w: window.innerWidth - SIDEBAR_WIDTH,
    h: window.innerHeight,
  });

  useEffect(() => {
    const onResize = () =>
      setStageSize({ w: window.innerWidth - SIDEBAR_WIDTH, h: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const visibleEntities = useMemo(() => {
    if (!doc) return [];
    return doc.entities.filter((e) => !hiddenLayers[e.layer]);
  }, [doc, hiddenLayers]);

  const bessMarkerSize = useMemo(
    () => computeBessMarkerSize(doc?.bounds ?? null, bessSizeFactor),
    [doc, bessSizeFactor]
  );

  const sitePlacementPayload = useMemo<SitePlacementExport>(
    () => ({
      schema_version: "v1",
      source_dxf_filename: sourceDxfName,
      coordinate_space: "cad_world",
      entities: {
        bess: bessPlacements.map((item) => ({
          id: item.id,
          label: item.label,
          cad_position: {
            x: item.x,
            y: item.y,
          },
        })),
      },
    }),
    [bessPlacements, sourceDxfName]
  );

  useEffect(() => {
    localStorage.setItem("cadream.sitePlacementPayload", JSON.stringify(sitePlacementPayload));
  }, [sitePlacementPayload]);

  async function onUpload(file: File) {
    setSourceDxfName(file.name);
    const fd = new FormData();
    fd.append("file", file);

    const res = await fetch("/api/dxf/parse", {
      method: "POST",
      body: fd,
    });

    const data = (await res.json()) as RenderDoc;
    const insertBounds = boundsFromInsertEntities(data.entities);

    setDoc(data);
    (window as Window & { __doc?: RenderDoc }).__doc = data;

    if (insertBounds) fitToBounds(insertBounds);
    else if (data.bounds) fitToBounds(data.bounds);
  }

  function toggleLayer(name: string) {
    setHiddenLayers((prev) => ({ ...prev, [name]: !prev[name] }));
  }

  function onWheel(e: Konva.KonvaEventObject<WheelEvent>) {
    e.evt.preventDefault();
    const stage = stageRef.current;
    if (!stage) return;
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

  function pointerToWorld() {
    const stage = stageRef.current;
    if (!stage) return null;
    const pointer = stage.getPointerPosition();
    if (!pointer) return null;
    return {
      x: (pointer.x - pos.x) / scale,
      y: -((pointer.y - pos.y) / scale),
    };
  }

  function onStageMouseDown(e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) {
    if (toolMode === "place-bess") {
      const clickedBess = e.target?.findAncestor?.(".bess-marker", true);
      if (clickedBess) return;

      const world = pointerToWorld();
      if (!world) return;

      const id = nextBessIdRef.current;
      nextBessIdRef.current += 1;

      const newPlacement: BessPlacement = {
        id,
        label: `BESS-${id}`,
        x: world.x,
        y: world.y,
      };

      setBessPlacements((prev) => [...prev, newPlacement]);
      setSelectedBessId(id);
      return;
    }

    const clickedOnEmpty = e.target === e.target.getStage();
    if (!clickedOnEmpty) return;

    setSelectedBessId(null);
  }

  function deleteSelectedBess() {
    if (selectedBessId === null) return;
    setBessPlacements((prev) => prev.filter((b) => b.id !== selectedBessId));
    setSelectedBessId(null);
  }

  function onStageDragEnd(e: Konva.KonvaEventObject<Event>) {
    setPos({ x: e.target.x(), y: e.target.y() });
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
      x: viewportW / 2 - centerX * newScale + SIDEBAR_WIDTH,
      y: viewportH / 2 - -centerY * newScale,
    });
  }

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "system-ui" }}>
      <ControlPanel
        doc={doc}
        hiddenLayers={hiddenLayers}
        toolMode={toolMode}
        selectedBessId={selectedBessId}
        bessPlacements={bessPlacements}
        bessSizeFactor={bessSizeFactor}
        onUpload={onUpload}
        onFitToDrawing={() => doc?.bounds && fitToBounds(doc.bounds)}
        onToggleLayer={toggleLayer}
        onSetToolMode={setToolMode}
        onDeleteSelectedBess={deleteSelectedBess}
        onClearBess={() => {
          setBessPlacements([]);
          setSelectedBessId(null);
        }}
        onSetBessSizeFactor={setBessSizeFactor}
      />

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
        {doc
          ? `Entities: ${doc.entities.length} | BESS: ${bessPlacements.length}`
          : "No DXF loaded"}
      </div>

      <CadCanvas
        stageRef={stageRef}
        stageSize={stageSize}
        pos={pos}
        scale={scale}
        toolMode={toolMode}
        visibleEntities={visibleEntities}
        hiddenLayers={hiddenLayers}
        doc={doc}
        bessPlacements={bessPlacements}
        selectedBessId={selectedBessId}
        bessMarkerSize={bessMarkerSize}
        onWheel={onWheel}
        onStageMouseDown={onStageMouseDown}
        onStageDragEnd={onStageDragEnd}
        onSetSelectedBessId={setSelectedBessId}
        onSetBessPlacements={setBessPlacements}
      />
    </div>
  );
}
