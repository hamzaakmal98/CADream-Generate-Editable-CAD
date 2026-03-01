import type Konva from "konva";
import type { Dispatch, RefObject, SetStateAction } from "react";
import CadCanvas from "../CadCanvas";
import ControlPanel from "../ControlPanel";
import type {
  BessPlacement,
  CablePath,
  PointOfInterconnection,
  RenderDoc,
  RenderEntity,
  SitePlacementExport,
  SldSessionState,
  ToolMode,
} from "../../types/cad";
import type { CadIrDrawing } from "../../types/cadIr";
import PlanSetStatusPanel from "./PlanSetStatusPanel";

type CadIrValidationState = {
  level: "error" | "warning" | "success";
  title: string;
  messages: string[];
} | null;

type InteractiveSitePlanWorkspaceProps = {
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
  bessSizeFactor: number;
  cadIr: CadIrDrawing | null;
  sitePlacementPayload: SitePlacementExport;
  sldSession: SldSessionState;
  cadIrValidationState: CadIrValidationState;
  canExportDxf: boolean;
  onDismissValidation: () => void;
  onUpload: (file: File) => void;
  onFitToDrawing: () => void;
  onToggleLayer: (layerName: string) => void;
  onSetToolMode: (mode: ToolMode) => void;
  onDeleteSelectedBess: () => void;
  onClearBess: () => void;
  onFinishCable: () => void;
  onCancelCableDraft: () => void;
  onDeleteSelectedCable: () => void;
  onClearCables: () => void;
  onClearPoi: () => void;
  onSetBessSizeFactor: (value: number) => void;
  onSaveProject: () => void;
  onLoadProject: (file: File) => void;
  onExportDxf: () => void;
  onWheel: (e: Konva.KonvaEventObject<WheelEvent>) => void;
  onStageMouseDown: (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => void;
  onStageDragMove: (e: Konva.KonvaEventObject<Event>) => void;
  onStageDragEnd: (e: Konva.KonvaEventObject<Event>) => void;
  onSetSelectedBessId: (id: number | null) => void;
  onSetSelectedCableId: (id: number | null) => void;
  onUpdateSelectedCableStart: (point: number[]) => void;
  onSetBessPlacements: Dispatch<SetStateAction<BessPlacement[]>>;
};

export default function InteractiveSitePlanWorkspace({
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
  bessSizeFactor,
  cadIr,
  sitePlacementPayload,
  sldSession,
  cadIrValidationState,
  canExportDxf,
  onDismissValidation,
  onUpload,
  onFitToDrawing,
  onToggleLayer,
  onSetToolMode,
  onDeleteSelectedBess,
  onClearBess,
  onFinishCable,
  onCancelCableDraft,
  onDeleteSelectedCable,
  onClearCables,
  onClearPoi,
  onSetBessSizeFactor,
  onSaveProject,
  onLoadProject,
  onExportDxf,
  onWheel,
  onStageMouseDown,
  onStageDragMove,
  onStageDragEnd,
  onSetSelectedBessId,
  onSetSelectedCableId,
  onUpdateSelectedCableStart,
  onSetBessPlacements,
}: InteractiveSitePlanWorkspaceProps) {
  return (
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
        onFitToDrawing={onFitToDrawing}
        onToggleLayer={onToggleLayer}
        onSetToolMode={onSetToolMode}
        onDeleteSelectedBess={onDeleteSelectedBess}
        onClearBess={onClearBess}
        onFinishCable={onFinishCable}
        onCancelCableDraft={onCancelCableDraft}
        onDeleteSelectedCable={onDeleteSelectedCable}
        onClearCables={onClearCables}
        onClearPoi={onClearPoi}
        onSetBessSizeFactor={onSetBessSizeFactor}
        onSaveProject={onSaveProject}
        onLoadProject={onLoadProject}
        onExportDxf={onExportDxf}
        canExportDxf={canExportDxf}
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
              onClick={onDismissValidation}
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

      <PlanSetStatusPanel cadIr={cadIr} sitePlacementPayload={sitePlacementPayload} sldSession={sldSession} />

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
        onSetSelectedBessId={onSetSelectedBessId}
        onSetSelectedCableId={onSetSelectedCableId}
        onUpdateSelectedCableStart={onUpdateSelectedCableStart}
        onSetBessPlacements={onSetBessPlacements}
      />
    </div>
  );
}
