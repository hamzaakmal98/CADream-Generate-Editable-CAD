import { useEffect, useMemo, useRef, useState } from "react";
import type Konva from "konva";
import CadCanvas from "./components/CadCanvas";
import ControlPanel from "./components/ControlPanel";
import { SIDEBAR_WIDTH } from "./constants/ui";
import { useBessEditing } from "./hooks/useBessEditing";
import { useCableRouting } from "./hooks/useCableRouting";
import type {
  PointOfInterconnection,
  RenderDoc,
  SitePlacementExport,
  ToolMode,
} from "./types/cad";
import {
  boundsFromInsertEntities,
  computeBessMarkerSize,
  estimateStructureBounds,
} from "./utils/cadGeometry";
import {
  createProjectSessionV2,
  loadSitePlanFromAnyProjectSession,
  pickSuggestedBessBlockName,
} from "./utils/projectSession";

type InterfaceTab = "interactive-site-plan" | "single-line-diagram-builder";

const TAB_BAR_HEIGHT = 44;
const TAB_BUTTON_STYLE = {
  padding: "8px 12px",
  borderRadius: 6,
  border: "1px solid #ddd",
  background: "#fff",
  cursor: "pointer",
  fontSize: 13,
  fontWeight: 600,
} as const;

export default function App() {
  const stageRef = useRef<Konva.Stage | null>(null);
  const [activeInterface, setActiveInterface] = useState<InterfaceTab>("interactive-site-plan");
  const [doc, setDoc] = useState<RenderDoc | null>(null);
  const [hiddenLayers, setHiddenLayers] = useState<Record<string, boolean>>({});
  const [scale, setScale] = useState(1);
  const [pos, setPos] = useState({ x: 20, y: 20 });
  const [toolMode, setToolMode] = useState<ToolMode>("pan");
  const [bessSizeFactor, setBessSizeFactor] = useState(1);
  const [sourceDxfName, setSourceDxfName] = useState<string | null>(null);
  const [poi, setPoi] = useState<PointOfInterconnection | null>(null);

  const [stageSize, setStageSize] = useState({
    w: window.innerWidth - SIDEBAR_WIDTH,
    h: window.innerHeight - TAB_BAR_HEIGHT,
  });

  useEffect(() => {
    const onResize = () =>
      setStageSize({ w: window.innerWidth - SIDEBAR_WIDTH, h: window.innerHeight - TAB_BAR_HEIGHT });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const visibleEntities = useMemo(() => {
    if (!doc) return [];
    return doc.entities.filter((e) => !hiddenLayers[e.layer]);
  }, [doc, hiddenLayers]);

  const suggestedBessBlockName = useMemo(() => pickSuggestedBessBlockName(doc), [doc]);

  const bessMarkerSize = useMemo(
    () => computeBessMarkerSize(doc?.bounds ?? null, bessSizeFactor),
    [doc, bessSizeFactor]
  );
  const poiMarkerSize = bessMarkerSize;

  const {
    bessPlacements,
    selectedBessId,
    addBessAt,
    setSelectedBessId,
    setBessPlacements,
    loadBessPlacements,
    deleteSelectedBess,
    clearBess,
  } = useBessEditing();

  const {
    cablePaths,
    draftCablePoints,
    selectedCableId,
    setSelectedCableId,
    loadCablePaths,
    addDraftPoint,
    finishCableDraft,
    cancelCableDraft,
    deleteSelectedCable,
    clearCables,
    updateSelectedCableStart,
    snapAllCableEndsToPoi,
    snapPointToNearestBess,
  } = useCableRouting({
    bessPlacements,
    poi,
    bessMarkerSize,
    scale,
  });

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
          cad_insert: {
            block_name: item.block_name,
            rotation: item.rotation,
            xscale: item.xscale,
            yscale: item.yscale,
          },
        })),
        poi,
        cable_paths: cablePaths,
      },
    }),
    [bessPlacements, cablePaths, poi, sourceDxfName]
  );

  useEffect(() => {
    if (poi) {
      snapAllCableEndsToPoi(poi);
    }
  }, [poi, snapAllCableEndsToPoi]);

  useEffect(() => {
    localStorage.setItem("cadream.sitePlacementPayload", JSON.stringify(sitePlacementPayload));
  }, [sitePlacementPayload]);

  function getBestFitBounds(data: RenderDoc) {
    return (
      estimateStructureBounds(data.entities) ||
      boundsFromInsertEntities(data.entities) ||
      data.bounds
    );
  }

  function onSaveProject() {
    const session = createProjectSessionV2({
      sourceDxfName,
      bessPlacements,
      poi,
      cablePaths,
      toolMode,
      bessSizeFactor,
      hiddenLayers,
      scale,
      pos,
    });

    const blob = new Blob([JSON.stringify(session, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    const fileBase = sourceDxfName ? sourceDxfName.replace(/\.[^.]+$/, "") : "cadream-project";
    anchor.href = url;
    anchor.download = `${fileBase}.project.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  async function onLoadProject(file: File) {
    try {
      const raw = await file.text();
      const parsed = JSON.parse(raw) as unknown;

      const loaded = loadSitePlanFromAnyProjectSession(parsed, {
        scale,
        pos,
      });

      if (!loaded) {
        window.alert("Unsupported project file format.");
        return;
      }

      setSourceDxfName(loaded.sourceDxfName);
      loadBessPlacements(loaded.bessPlacements);
      loadCablePaths(loaded.cablePaths);
      setPoi(loaded.poi);
      setToolMode(loaded.toolMode);
      setBessSizeFactor(loaded.bessSizeFactor);
      setHiddenLayers(loaded.hiddenLayers);
      setScale(loaded.scale);
      setPos(loaded.pos);
      setSelectedBessId(null);
      setSelectedCableId(null);
    } catch {
      window.alert("Failed to load project JSON.");
    }
  }

  async function onUpload(file: File) {
    setSourceDxfName(file.name);
    const fd = new FormData();
    fd.append("file", file);

    const res = await fetch("/api/dxf/parse", {
      method: "POST",
      body: fd,
    });

    const data = (await res.json()) as RenderDoc;
    const fitBounds = getBestFitBounds(data);

    setDoc(data);
    (window as Window & { __doc?: RenderDoc }).__doc = data;

    if (fitBounds) fitToBounds(fitBounds);
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

      addBessAt(world.x, world.y, {
        block_name: suggestedBessBlockName,
        rotation: 0,
        xscale: 1,
        yscale: 1,
      });
      setSelectedCableId(null);
      return;
    }

    if (toolMode === "place-poi") {
      const world = pointerToWorld();
      if (!world) return;
      setPoi({ x: world.x, y: world.y });
      setSelectedBessId(null);
      setSelectedCableId(null);
      return;
    }

    if (toolMode === "draw-cable") {
      const clickedBess = e.target?.findAncestor?.(".bess-marker", true);
      const clickedCable = e.target?.findAncestor?.(".cable-path", true);
      if (clickedCable) return;

      if (clickedBess) {
        const bessId = Number(clickedBess.getAttr("bessId"));
        const bess = bessPlacements.find((b) => b.id === bessId);
        if (!bess) return;

        addDraftPoint([bess.x, bess.y]);
        setSelectedBessId(bess.id);
        setSelectedCableId(null);
        return;
      }

      const clickedPoi = e.target?.findAncestor?.(".poi-marker", true);
      if (clickedPoi && poi) {
        addDraftPoint([poi.x, poi.y]);
        setSelectedBessId(null);
        setSelectedCableId(null);
        return;
      }

      const world = pointerToWorld();
      if (!world) return;

      const isFirstPoint = draftCablePoints.length === 0;
      const firstSnap = isFirstPoint ? snapPointToNearestBess([world.x, world.y]) : null;
      const pointToAdd = firstSnap?.point ?? [world.x, world.y];

      addDraftPoint(pointToAdd);
      setSelectedBessId(null);
      setSelectedCableId(null);
      return;
    }

    const clickedOnEmpty = e.target === e.target.getStage();
    if (!clickedOnEmpty) return;

    setSelectedBessId(null);
    setSelectedCableId(null);
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
      x: viewportW / 2 - centerX * newScale,
      y: viewportH / 2 - -centerY * newScale,
    });
  }

  return (
    <div style={{ height: "100vh", fontFamily: "system-ui", display: "flex", flexDirection: "column" }}>
      <div
        style={{
          height: TAB_BAR_HEIGHT,
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "0 10px",
          borderBottom: "1px solid #ddd",
          background: "#f8f8f8",
        }}
      >
        <button
          style={{
            ...TAB_BUTTON_STYLE,
            background: activeInterface === "interactive-site-plan" ? "#fff" : "#f0f0f0",
            borderColor: activeInterface === "interactive-site-plan" ? "#888" : "#ddd",
          }}
          onClick={() => setActiveInterface("interactive-site-plan")}
        >
          Interactive Site Plan
        </button>

        <button
          style={{
            ...TAB_BUTTON_STYLE,
            background: activeInterface === "single-line-diagram-builder" ? "#fff" : "#f0f0f0",
            borderColor: activeInterface === "single-line-diagram-builder" ? "#888" : "#ddd",
          }}
          onClick={() => setActiveInterface("single-line-diagram-builder")}
        >
          Single-Line Diagram Builder
        </button>
      </div>

      <div style={{ flex: 1, position: "relative" }}>
        {activeInterface === "interactive-site-plan" ? (
          <div style={{ display: "flex", height: "100%" }}>
            <ControlPanel
              doc={doc}
              hiddenLayers={hiddenLayers}
              toolMode={toolMode}
              selectedBessId={selectedBessId}
              bessPlacements={bessPlacements}
              selectedCableId={selectedCableId}
              cablePaths={cablePaths}
              draftCablePoints={draftCablePoints}
              hasPoi={poi !== null}
              bessSizeFactor={bessSizeFactor}
              onUpload={onUpload}
              onFitToDrawing={() => {
                if (!doc) return;
                const fitBounds = getBestFitBounds(doc);
                if (fitBounds) fitToBounds(fitBounds);
              }}
              onToggleLayer={toggleLayer}
              onSetToolMode={setToolMode}
              onDeleteSelectedBess={deleteSelectedBess}
              onClearBess={clearBess}
              onFinishCable={finishCableDraft}
              onCancelCableDraft={cancelCableDraft}
              onDeleteSelectedCable={deleteSelectedCable}
              onClearCables={clearCables}
              onClearPoi={() => setPoi(null)}
              onSetBessSizeFactor={setBessSizeFactor}
              onSaveProject={onSaveProject}
              onLoadProject={onLoadProject}
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
                ? `Entities: ${doc.entities.length} | BESS: ${bessPlacements.length} | POI: ${poi ? "set" : "none"} | Cables: ${cablePaths.length}`
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
              cablePaths={cablePaths}
              draftCablePoints={draftCablePoints}
              poi={poi}
              selectedCableId={selectedCableId}
              selectedBessId={selectedBessId}
              bessMarkerSize={bessMarkerSize}
              poiMarkerSize={poiMarkerSize}
              onWheel={onWheel}
              onStageMouseDown={onStageMouseDown}
              onStageDragEnd={onStageDragEnd}
              onSetSelectedBessId={setSelectedBessId}
              onSetSelectedCableId={setSelectedCableId}
              onUpdateSelectedCableStart={updateSelectedCableStart}
              onSetBessPlacements={setBessPlacements}
            />
          </div>
        ) : (
          <div
            style={{
              height: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "#fff",
              color: "#444",
              fontSize: 16,
              fontWeight: 500,
            }}
          >
            Single-Line Diagram Builder interface coming next.
          </div>
        )}
      </div>
    </div>
  );
}
