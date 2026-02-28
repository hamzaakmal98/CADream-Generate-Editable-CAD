import { useRef } from "react";
import type { BessPlacement, CablePath, RenderDoc, ToolMode } from "../types/cad";
import { SIDEBAR_WIDTH } from "../constants/ui";

type ControlPanelProps = {
  doc: RenderDoc | null;
  hiddenLayers: Record<string, boolean>;
  toolMode: ToolMode;
  selectedBessId: number | null;
  bessPlacements: BessPlacement[];
  selectedCableId: number | null;
  cablePaths: CablePath[];
  draftCablePoints: number[][];
  hasPoi: boolean;
  bessSizeFactor: number;
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
};

export default function ControlPanel({
  doc,
  hiddenLayers,
  toolMode,
  selectedBessId,
  bessPlacements,
  selectedCableId,
  cablePaths,
  draftCablePoints,
  hasPoi,
  bessSizeFactor,
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
}: ControlPanelProps) {
  const loadProjectInputRef = useRef<HTMLInputElement | null>(null);

  return (
    <div
      style={{
        width: SIDEBAR_WIDTH,
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
          const file = e.target.files?.[0];
          if (file) onUpload(file);
        }}
      />

      <button
        style={{ marginTop: 8, padding: "6px 10px" }}
        disabled={!doc?.bounds}
        onClick={onFitToDrawing}
      >
        Fit to drawing
      </button>

      <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
        <button style={{ padding: "6px 10px" }} onClick={onSaveProject}>
          Save Project
        </button>
        <button
          style={{ padding: "6px 10px" }}
          onClick={() => loadProjectInputRef.current?.click()}
        >
          Load Project
        </button>
      </div>

      <input
        ref={loadProjectInputRef}
        type="file"
        accept=".json,application/json"
        style={{ display: "none" }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onLoadProject(file);
          e.currentTarget.value = "";
        }}
      />

      <hr />

      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Site Editing</div>

      <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
        <button
          style={{ padding: "6px 10px", background: toolMode === "pan" ? "#eee" : "white" }}
          onClick={() => onSetToolMode("pan")}
        >
          Pan
        </button>
        <button
          style={{
            padding: "6px 10px",
            background: toolMode === "place-bess" ? "#eee" : "white",
          }}
          disabled={!doc}
          onClick={() => onSetToolMode("place-bess")}
        >
          Place BESS
        </button>
        <button
          style={{
            padding: "6px 10px",
            background: toolMode === "draw-cable" ? "#eee" : "white",
          }}
          disabled={!doc}
          onClick={() => onSetToolMode("draw-cable")}
        >
          Draw Cable
        </button>
        <button
          style={{
            padding: "6px 10px",
            background: toolMode === "place-poi" ? "#eee" : "white",
          }}
          disabled={!doc}
          onClick={() => onSetToolMode("place-poi")}
        >
          Place POI
        </button>
      </div>

      <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
        <button
          style={{ padding: "6px 10px" }}
          disabled={selectedBessId === null}
          onClick={onDeleteSelectedBess}
        >
          Delete Selected
        </button>
        <button style={{ padding: "6px 10px" }} disabled={bessPlacements.length === 0} onClick={onClearBess}>
          Clear BESS
        </button>
      </div>

      <div style={{ fontSize: 12, color: "#666", marginBottom: 8 }}>
        {toolMode === "place-bess" && "Click on site plan to place BESS."}
        {toolMode === "place-poi" && "Click on site plan to place or move POI."}
        {toolMode === "draw-cable" && "Click to add cable vertices, then finish cable."}
        {toolMode === "pan" && "Pan mode: drag canvas to navigate."}
      </div>

      <div style={{ fontSize: 12, color: "#666" }}>Placed BESS: {bessPlacements.length}</div>
      <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>POI: {hasPoi ? "set" : "not set"}</div>

      <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
        <button style={{ padding: "6px 10px" }} disabled={!hasPoi} onClick={onClearPoi}>
          Clear POI
        </button>
      </div>

      <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
        Cable paths: {cablePaths.length}
      </div>

      <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
        <button
          style={{ padding: "6px 10px" }}
          disabled={draftCablePoints.length < 2 || !hasPoi}
          onClick={onFinishCable}
        >
          Finish Cable
        </button>
        <button
          style={{ padding: "6px 10px" }}
          disabled={draftCablePoints.length === 0}
          onClick={onCancelCableDraft}
        >
          Cancel Draft
        </button>
      </div>

      <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
        <button
          style={{ padding: "6px 10px" }}
          disabled={selectedCableId === null}
          onClick={onDeleteSelectedCable}
        >
          Delete Cable
        </button>
        <button
          style={{ padding: "6px 10px" }}
          disabled={cablePaths.length === 0}
          onClick={onClearCables}
        >
          Clear Cables
        </button>
      </div>

      <div style={{ marginTop: 8 }}>
        <div style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>
          BESS size: {bessSizeFactor.toFixed(1)}x
        </div>
        <input
          type="range"
          min={0.4}
          max={2.5}
          step={0.1}
          value={bessSizeFactor}
          onChange={(e) => onSetBessSizeFactor(Number(e.target.value))}
          style={{ width: "100%" }}
        />
      </div>

      <hr />

      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Layers</div>
      {!doc && <div style={{ fontSize: 12, color: "#666" }}>Upload a DXF to begin.</div>}

      {doc?.layers?.slice(0, 400).map((layer) => (
        <label key={layer.name} style={{ display: "block", fontSize: 12, cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={!hiddenLayers[layer.name]}
            onChange={() => onToggleLayer(layer.name)}
            style={{ marginRight: 6 }}
          />
          {layer.name}
        </label>
      ))}
    </div>
  );
}
