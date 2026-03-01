import { useEffect, useMemo, useRef, useState } from "react";
import type Konva from "konva";
import CadCanvas from "./components/CadCanvas";
import ControlPanel from "./components/ControlPanel";
import SldBuilder from "./components/sld/SldBuilder";
import { SIDEBAR_WIDTH } from "./constants/ui";
import { useBessEditing } from "./hooks/useBessEditing";
import { useCableRouting } from "./hooks/useCableRouting";
import { useSldEditor } from "./hooks/useSldEditor";
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
import { attachSitePlanToCadIr, buildCadIrFromRenderDoc } from "./utils/cadIrBuilder";
import {
  createProjectSessionV2,
  loadProjectFromAnySession,
  pickSuggestedBessBlockName,
} from "./utils/projectSession";

type InterfaceTab = "interactive-site-plan" | "single-line-diagram-builder";

type CadIrValidationState = {
  level: "error" | "warning" | "success";
  title: string;
  messages: string[];
} | null;

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
  const [cadIr, setCadIr] = useState<ReturnType<typeof buildCadIrFromRenderDoc> | null>(null);
  const [poi, setPoi] = useState<PointOfInterconnection | null>(null);
  const [cadIrValidationState, setCadIrValidationState] = useState<CadIrValidationState>(null);

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

  const sldEditor = useSldEditor();

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

  function buildCurrentCadIr() {
    const baseCadIr = doc
      ? buildCadIrFromRenderDoc({
          doc,
          sourceFileName: sourceDxfName,
        })
      : cadIr;

    if (!baseCadIr) return null;

    return attachSitePlanToCadIr(baseCadIr, {
      bessPlacements,
      poi,
      cablePaths,
    });
  }

  async function validateCadIrOrAlert(cadIrToValidate: NonNullable<ReturnType<typeof buildCurrentCadIr>>) {
    let res: Response;
    try {
      res = await fetch("/api/cad-ir/validate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ cad_ir: cadIrToValidate }),
      });
    } catch {
      setCadIrValidationState({
        level: "error",
        title: "CAD IR Validation Service Unavailable",
        messages: ["Could not validate CAD IR. Please ensure backend is running and try again."],
      });
      return false;
    }

    if (!res.ok) {
      setCadIrValidationState({
        level: "error",
        title: "CAD IR Validation Service Unavailable",
        messages: ["Could not validate CAD IR. Please ensure backend is running and try again."],
      });
      return false;
    }

    const result = (await res.json()) as {
      valid: boolean;
      errors?: string[];
      warnings?: string[];
    };

    if (!result.valid) {
      setCadIrValidationState({
        level: "error",
        title: "CAD IR Validation Failed",
        messages: (result.errors ?? []).slice(0, 6),
      });
      return false;
    }

    if ((result.warnings?.length ?? 0) > 0) {
      setCadIrValidationState({
        level: "warning",
        title: "CAD IR Validation Warnings",
        messages: (result.warnings ?? []).slice(0, 6),
      });
      return true;
    }

    setCadIrValidationState({
      level: "success",
      title: "CAD IR Validation Passed",
      messages: ["No errors found."],
    });

    return true;
  }

  async function onSaveProject() {
    const currentCadIr = buildCurrentCadIr();
    if (currentCadIr) {
      const valid = await validateCadIrOrAlert(currentCadIr);
      if (!valid) return;
    }

    const session = createProjectSessionV2({
      sourceDxfName,
      cadIr: currentCadIr,
      bessPlacements,
      poi,
      cablePaths,
      toolMode,
      bessSizeFactor,
      hiddenLayers,
      scale,
      pos,
      sldSession: sldEditor.session,
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

  async function onExportDxf() {
    if (!doc?.source_token) {
      setCadIrValidationState({
        level: "error",
        title: "Export Unavailable",
        messages: ["Please upload the source DXF in this session before exporting."],
      });
      return;
    }

    const exportCadIr = buildCurrentCadIr();

    if (!exportCadIr) {
      setCadIrValidationState({
        level: "error",
        title: "Export Unavailable",
        messages: ["No CAD data available to export. Upload a DXF first."],
      });
      return;
    }

    const valid = await validateCadIrOrAlert(exportCadIr);
    if (!valid) return;

    const defaultBase = sourceDxfName ? sourceDxfName.replace(/\.[^.]+$/, "") : "cadream-export";
    const requestedName = window.prompt("Enter DXF file name", defaultBase);
    if (requestedName === null) return;
    const normalizedFileBase = requestedName.trim().replace(/\.[^.]+$/, "") || defaultBase;

    let res: Response;
    try {
      res = await fetch("/api/dxf/export", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          source_token: doc.source_token,
          site_placements: sitePlacementPayload,
          cad_ir: exportCadIr,
          source_file_name: normalizedFileBase,
        }),
      });
    } catch {
      setCadIrValidationState({
        level: "error",
        title: "Export Service Unavailable",
        messages: ["Could not reach backend export service. Please ensure backend is running and try again."],
      });
      return;
    }

    if (!res.ok) {
      let detail = "DXF export failed.";
      try {
        const err = (await res.json()) as { detail?: string };
        if (typeof err.detail === "string" && err.detail.trim()) {
          detail = err.detail;
        }
      } catch {
        // keep default message
      }

      setCadIrValidationState({
        level: "error",
        title: "DXF Export Failed",
        messages: [detail],
      });
      return;
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    const fileBase = normalizedFileBase;
    anchor.href = url;
    anchor.download = `${fileBase}.dxf`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  async function onLoadProject(file: File) {
    try {
      const raw = await file.text();
      const parsed = JSON.parse(raw) as unknown;

      const loaded = loadProjectFromAnySession(parsed, {
        scale,
        pos,
      });

      if (!loaded) {
        setCadIrValidationState({
          level: "error",
          title: "Load Failed",
          messages: ["Unsupported project file format."],
        });
        return;
      }

      setSourceDxfName(loaded.sitePlan.sourceDxfName);
      setCadIr(loaded.sitePlan.cadIr);
      loadBessPlacements(loaded.sitePlan.bessPlacements);
      loadCablePaths(loaded.sitePlan.cablePaths);
      setPoi(loaded.sitePlan.poi);
      setToolMode(loaded.sitePlan.toolMode);
      setBessSizeFactor(loaded.sitePlan.bessSizeFactor);
      setHiddenLayers(loaded.sitePlan.hiddenLayers);
      setScale(loaded.sitePlan.scale);
      setPos(loaded.sitePlan.pos);
      setSelectedBessId(null);
      setSelectedCableId(null);
      sldEditor.loadSession(loaded.sldSession);
      setCadIrValidationState(null);
    } catch {
      setCadIrValidationState({
        level: "error",
        title: "Load Failed",
        messages: ["Failed to load project JSON."],
      });
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
    setCadIr(
      buildCadIrFromRenderDoc({
        doc: data,
        sourceFileName: file.name,
      })
    );

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

  function onStageDragMove(e: Konva.KonvaEventObject<Event>) {
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
              onExportDxf={onExportDxf}
              canExportDxf={cadIr !== null}
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

            {cadIrValidationState && (
              <div
                style={{
                  position: "absolute",
                  right: 10,
                  top: 52,
                  maxWidth: 420,
                  background:
                    cadIrValidationState.level === "error"
                      ? "#fef2f2"
                      : cadIrValidationState.level === "warning"
                      ? "#fffbeb"
                      : "#ecfdf5",
                  border:
                    cadIrValidationState.level === "error"
                      ? "1px solid #fecaca"
                      : cadIrValidationState.level === "warning"
                      ? "1px solid #fde68a"
                      : "1px solid #a7f3d0",
                  color:
                    cadIrValidationState.level === "error"
                      ? "#7f1d1d"
                      : cadIrValidationState.level === "warning"
                      ? "#78350f"
                      : "#14532d",
                  padding: 10,
                  borderRadius: 8,
                  fontSize: 12,
                  zIndex: 20,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                  <strong>{cadIrValidationState.title}</strong>
                  <button
                    style={{
                      border: "1px solid #cbd5e1",
                      background: "#fff",
                      borderRadius: 4,
                      fontSize: 11,
                      padding: "2px 6px",
                      cursor: "pointer",
                    }}
                    onClick={() => setCadIrValidationState(null)}
                  >
                    Dismiss
                  </button>
                </div>
                <ul style={{ margin: "8px 0 0", paddingLeft: 16 }}>
                  {cadIrValidationState.messages.map((message, index) => (
                    <li key={`${cadIrValidationState.title}-${index}`}>{message}</li>
                  ))}
                </ul>
              </div>
            )}

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
              onStageDragMove={onStageDragMove}
              onStageDragEnd={onStageDragEnd}
              onSetSelectedBessId={setSelectedBessId}
              onSetSelectedCableId={setSelectedCableId}
              onUpdateSelectedCableStart={updateSelectedCableStart}
              onSetBessPlacements={setBessPlacements}
            />
          </div>
        ) : (
          <SldBuilder
            session={sldEditor.session}
            palette={sldEditor.palette}
            selectedNodeId={sldEditor.selectedNodeId}
            selectedEdgeId={sldEditor.selectedEdgeId}
            wireDraft={sldEditor.wireDraft}
            reconnectDraft={sldEditor.reconnectDraft}
            onSetToolMode={sldEditor.setToolMode}
            onUndo={sldEditor.undo}
            onRedo={sldEditor.redo}
            canUndo={sldEditor.canUndo}
            canRedo={sldEditor.canRedo}
            onAddNode={sldEditor.addNode}
            onMoveNode={sldEditor.moveNode}
            onSelectNode={sldEditor.selectNode}
            onSelectEdge={sldEditor.selectEdge}
            onDeleteSelection={sldEditor.deleteSelection}
            onBeginOrCompleteConnection={sldEditor.beginOrCompleteConnection}
            onAddWireDraftCorner={sldEditor.addWireDraftCorner}
            onUpdateWireDraftCursor={sldEditor.updateWireDraftCursor}
            onCancelDrafts={sldEditor.cancelDrafts}
            onClearAll={sldEditor.clearAll}
          />
        )}
      </div>
    </div>
  );
}
