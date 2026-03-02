import { useEffect, useMemo, useRef, useState } from "react";
import type Konva from "konva";
import SldBuilder from "./components/sld/SldBuilder";
import InteractiveSitePlanWorkspace from "./components/siteplan/InteractiveSitePlanWorkspace";
import { SIDEBAR_WIDTH } from "./constants/ui";
import { useBessEditing } from "./hooks/useBessEditing";
import { useCableRouting } from "./hooks/useCableRouting";
import { useProjectActions } from "./hooks/useProjectActions";
import { useSldEditor } from "./hooks/useSldEditor";
import type {
  PointOfInterconnection,
  RenderDoc,
  SitePlacementExport,
  ToolMode,
} from "./types/cad";
import type { CadIrDrawing } from "./types/cadIr";
import type { RightPanelMetadata } from "./types/planset";
import {
  boundsFromInsertEntities,
  computeBessMarkerSize,
  estimateStructureBounds,
} from "./utils/cadGeometry";
import { pickSuggestedBessBlockName } from "./utils/projectSession";

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

function createDefaultRightPanelMetadata(): RightPanelMetadata {
  const today = new Date().toISOString().slice(0, 10);
  return {
    ac_system_size: "380kW",
    inverter_model: "Dynapower CPS1250",
    dc_system_size: "760kWh",
    bess_model: "Gotion Edge 760",
    customer_website: "",
    customer_phone: "",
    customer_contact: "",
    ahj: "",
    designer_company: "CADream",
    designer_address: "",
    designer_website: "",
    designer_phone: "",
    designer_contact: "",
    page_notes: "",
    sheet_metadata: {
      scale: "As Noted",
      sheet_title: "",
      drawn_by: "DG",
      checked_by: "DG",
      approved_by: "A",
      issue_date: today,
      sheet_number: "01",
      revision: "A",
    },
    title_block: {
      project_name: "",
      client_name: "",
      site_address: "",
      drawn_by: "DG",
      checked_by: "DG",
      approved_by: "A",
    },
    engineer_signature_image: {
      uri: "",
      mime_type: "",
      base64: "",
    },
  };
}

function triggerFileDownload(blob: Blob, filename: string): void {
  const forceDownloadBlob =
    blob.type === "application/octet-stream" ? blob : new Blob([blob], { type: "application/octet-stream" });
  const url = URL.createObjectURL(forceDownloadBlob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.target = "_self";
  anchor.rel = "noopener noreferrer";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

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
  const [cadIr, setCadIr] = useState<CadIrDrawing | null>(null);
  const [poi, setPoi] = useState<PointOfInterconnection | null>(null);
  const [rightPanelMetadata, setRightPanelMetadata] = useState<RightPanelMetadata>(createDefaultRightPanelMetadata);
  const [isExportingPlansetPdf, setIsExportingPlansetPdf] = useState(false);
  const [plansetPdfProgress, setPlansetPdfProgress] = useState<number | null>(null);

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

  const {
    cadIrValidationState,
    setCadIrValidationState,
    onSaveProject,
    onExportDxf,
    onLoadProject,
    onUpload,
  } = useProjectActions({
    doc,
    setDoc,
    sourceDxfName,
    setSourceDxfName,
    cadIr,
    setCadIr,
    bessPlacements,
    poi,
    cablePaths,
    toolMode,
    bessSizeFactor,
    hiddenLayers,
    scale,
    pos,
    sitePlacementPayload,
    sldSession: sldEditor.session,
    sldLoadSession: sldEditor.loadSession,
    loadBessPlacements,
    loadCablePaths,
    setPoi,
    setToolMode,
    setBessSizeFactor,
    setHiddenLayers,
    setScale,
    setPos,
    setSelectedBessId,
    setSelectedCableId,
    getBestFitBounds,
    fitToBounds,
  });

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

  async function onExportPages2425FromSldBuilder() {
    const res = await fetch("/api/planset/pages-24-25/export", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        total_pages: 49,
        cad_ir: cadIr,
        site_placements: sitePlacementPayload,
        sld_session: sldEditor.session,
      }),
    });

    if (!res.ok) {
      let detail = "Failed to export pages 24/25 DXF zip.";
      try {
        const err = (await res.json()) as { detail?: string };
        if (typeof err.detail === "string" && err.detail.trim()) {
          detail = err.detail;
        }
      } catch {
        // keep default detail
      }
      throw new Error(detail);
    }

    const blob = await res.blob();
    triggerFileDownload(blob, "planset-pages-24-25.zip");
  }

  async function onExportPagesPdfFromInterfaceA() {
    setIsExportingPlansetPdf(true);
    setPlansetPdfProgress(2);

    let syntheticProgress = 2;
    const preparationTimer = window.setInterval(() => {
      syntheticProgress = Math.min(85, syntheticProgress + Math.max(0.4, (85 - syntheticProgress) * 0.035));
      setPlansetPdfProgress(Math.round(syntheticProgress));
    }, 500);

    try {
      const res = await fetch("/api/planset/pages/pdf-export", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          total_pages: 49,
          cad_ir: cadIr,
          site_placements: sitePlacementPayload,
          sld_session: sldEditor.session,
          right_panel_metadata: rightPanelMetadata,
        }),
      });

      window.clearInterval(preparationTimer);

      if (!res.ok) {
        let detail = "Failed to generate pages PDF.";
        try {
          const err = (await res.json()) as { detail?: string };
          if (typeof err.detail === "string" && err.detail.trim()) {
            detail = err.detail;
          }
        } catch {
          // keep default detail
        }
        throw new Error(detail);
      }

      const contentLengthHeader = res.headers.get("Content-Length");
      const contentLength = contentLengthHeader ? Number(contentLengthHeader) : 0;
      const reader = res.body?.getReader();

      let blob: Blob;

      setPlansetPdfProgress((prev) => (prev !== null ? Math.max(prev, 88) : 88));

      if (reader) {
        const chunks: Uint8Array[] = [];
        let receivedLength = 0;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (!value) continue;

          chunks.push(value);
          receivedLength += value.length;

          if (contentLength > 0) {
            const progress = Math.min(100, 88 + Math.round((receivedLength / contentLength) * 12));
            setPlansetPdfProgress(progress);
          } else {
            setPlansetPdfProgress((prev) => {
              const current = prev ?? 92;
              return Math.min(99, current + 1);
            });
          }
        }

        const bytes = new Uint8Array(receivedLength);
        let position = 0;
        for (const chunk of chunks) {
          bytes.set(chunk, position);
          position += chunk.length;
        }
        blob = new Blob([bytes], { type: "application/pdf" });
      } else {
        blob = await res.blob();
        setPlansetPdfProgress(100);
      }

      triggerFileDownload(blob, "planset-pages.pdf");
      setPlansetPdfProgress(100);
    } finally {
      window.clearInterval(preparationTimer);
      setTimeout(() => {
        setIsExportingPlansetPdf(false);
        setPlansetPdfProgress(null);
      }, 400);
    }
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
          <InteractiveSitePlanWorkspace
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
            bessSizeFactor={bessSizeFactor}
            cadIr={cadIr}
            sitePlacementPayload={sitePlacementPayload}
            sldSession={sldEditor.session}
            cadIrValidationState={cadIrValidationState}
            canExportDxf={cadIr !== null}
            onDismissValidation={() => setCadIrValidationState(null)}
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
            onExportPagesPdf={onExportPagesPdfFromInterfaceA}
            isExportingPlansetPdf={isExportingPlansetPdf}
            plansetPdfProgress={plansetPdfProgress}
            rightPanelMetadata={rightPanelMetadata}
            onRightPanelMetadataChange={setRightPanelMetadata}
            onWheel={onWheel}
            onStageMouseDown={onStageMouseDown}
            onStageDragMove={onStageDragMove}
            onStageDragEnd={onStageDragEnd}
            onSetSelectedBessId={setSelectedBessId}
            onSetSelectedCableId={setSelectedCableId}
            onUpdateSelectedCableStart={updateSelectedCableStart}
            onSetBessPlacements={setBessPlacements}
          />
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
            onLoadSession={sldEditor.loadSession}
            onExportPages2425={onExportPages2425FromSldBuilder}
          />
        )}
      </div>
    </div>
  );
}
