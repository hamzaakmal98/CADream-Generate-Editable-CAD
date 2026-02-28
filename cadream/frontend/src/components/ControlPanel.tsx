import type { BessPlacement, RenderDoc, ToolMode } from "../types/cad";
import { SIDEBAR_WIDTH } from "../constants/ui";

type ControlPanelProps = {
  doc: RenderDoc | null;
  hiddenLayers: Record<string, boolean>;
  toolMode: ToolMode;
  selectedBessId: number | null;
  bessPlacements: BessPlacement[];
  bessSizeFactor: number;
  onUpload: (file: File) => void;
  onFitToDrawing: () => void;
  onToggleLayer: (layerName: string) => void;
  onSetToolMode: (mode: ToolMode) => void;
  onDeleteSelectedBess: () => void;
  onClearBess: () => void;
  onSetBessSizeFactor: (value: number) => void;
};

export default function ControlPanel({
  doc,
  hiddenLayers,
  toolMode,
  selectedBessId,
  bessPlacements,
  bessSizeFactor,
  onUpload,
  onFitToDrawing,
  onToggleLayer,
  onSetToolMode,
  onDeleteSelectedBess,
  onClearBess,
  onSetBessSizeFactor,
}: ControlPanelProps) {
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
        {toolMode === "place-bess"
          ? "Click on site plan to place BESS."
          : "Pan mode: drag canvas to navigate."}
      </div>

      <div style={{ fontSize: 12, color: "#666" }}>Placed BESS: {bessPlacements.length}</div>

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
