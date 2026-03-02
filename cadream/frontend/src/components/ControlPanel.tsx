import { useRef, useState } from "react";
import type { BessPlacement, CablePath, RenderDoc, ToolMode } from "../types/cad";
import type { RightPanelMetadata } from "../types/planset";
import { SIDEBAR_WIDTH } from "../constants/ui";

const BUTTON_STYLE = {
  minHeight: 34,
  minWidth: 0,
  padding: "6px 10px",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  textAlign: "center" as const,
  flex: "1 1 0",
  maxWidth: "100%",
  boxSizing: "border-box" as const,
  border: "1px solid #cbd5e1",
  borderRadius: 8,
  background: "#ffffff",
  color: "#0f172a",
};

const SECTION_TOGGLE_STYLE = {
  ...BUTTON_STYLE,
  width: "100%",
  justifyContent: "space-between",
  background: "#eff6ff",
  border: "1px solid #bfdbfe",
};

const PANEL_CARD_STYLE = {
  border: "1px solid #e2e8f0",
  borderRadius: 8,
  padding: 8,
  background: "linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)",
};

const TOOL_BUTTONS: Array<{ mode: ToolMode; label: string; requiresDoc: boolean }> = [
  { mode: "pan", label: "Pan", requiresDoc: false },
  { mode: "place-bess", label: "Place BESS", requiresDoc: true },
  { mode: "draw-cable", label: "Set Cable point", requiresDoc: true },
  { mode: "place-poi", label: "Mark POI", requiresDoc: true },
];

const TOOL_HINTS: Record<ToolMode, string> = {
  "place-bess": "Click on site plan to place BESS.",
  "place-poi": "Click on site plan to mark or move POI.",
  "draw-cable": "Click to add cable vertices, then finish cable.",
  pan: "Pan mode: drag canvas to navigate.",
};

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
  onExportDxf: () => void;
  onExportAutoPages: () => void;
  onExportPagesPdf: () => void;
  isExportingPlansetPdf: boolean;
  plansetPdfProgress: number | null;
  rightPanelMetadata: RightPanelMetadata;
  onRightPanelMetadataChange: (next: RightPanelMetadata) => void;
  canExportDxf: boolean;
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
  onExportDxf,
  onExportAutoPages,
  onExportPagesPdf,
  isExportingPlansetPdf,
  plansetPdfProgress,
  rightPanelMetadata,
  onRightPanelMetadataChange,
  canExportDxf,
}: ControlPanelProps) {
  const loadProjectInputRef = useRef<HTMLInputElement | null>(null);
  const [showMetadataForm, setShowMetadataForm] = useState(false);
  const [showProjectActions, setShowProjectActions] = useState(false);
  const [showSiteEditing, setShowSiteEditing] = useState(true);
  const [showLayers, setShowLayers] = useState(false);

  function setRootField<K extends keyof RightPanelMetadata>(key: K, value: RightPanelMetadata[K]) {
    onRightPanelMetadataChange({
      ...rightPanelMetadata,
      [key]: value,
    });
  }

  function setTitleBlockField(
    key: keyof RightPanelMetadata["title_block"],
    value: string
  ) {
    onRightPanelMetadataChange({
      ...rightPanelMetadata,
      title_block: {
        ...rightPanelMetadata.title_block,
        [key]: value,
      },
    });
  }

  function setSheetMetadataField(
    key: keyof RightPanelMetadata["sheet_metadata"],
    value: string
  ) {
    onRightPanelMetadataChange({
      ...rightPanelMetadata,
      sheet_metadata: {
        ...rightPanelMetadata.sheet_metadata,
        [key]: value,
      },
    });
  }

  async function onSignatureUpload(file: File) {
    const dataUri = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result ?? ""));
      reader.onerror = () => reject(new Error("Failed to read signature file"));
      reader.readAsDataURL(file);
    });

    const base64 = dataUri.includes(",") ? dataUri.split(",", 2)[1] : "";
    onRightPanelMetadataChange({
      ...rightPanelMetadata,
      engineer_signature_image: {
        uri: dataUri,
        mime_type: file.type || "application/octet-stream",
        base64,
      },
    });
  }

  return (
    <div
      style={{
        width: SIDEBAR_WIDTH,
        borderRight: "1px solid #e2e8f0",
        padding: 12,
        overflow: "auto",
        background: "#f8fafc",
      }}
    >
      <h3 style={{ marginTop: 0, marginBottom: 6 }}>CADream</h3>
      <div style={{ fontSize: 12, color: "#64748b", marginBottom: 10 }}>Interface A • Site Plan</div>

      <div style={{ ...PANEL_CARD_STYLE, marginBottom: 8 }}>
        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Source Drawing</div>

        <input
          type="file"
          accept=".dxf"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onUpload(file);
          }}
        />

        <button
          style={{ ...BUTTON_STYLE, marginTop: 8 }}
          disabled={!doc?.bounds}
          onClick={onFitToDrawing}
        >
          Fit to Drawing
        </button>
      </div>

      <div style={{ ...PANEL_CARD_STYLE, marginTop: 8, display: "grid", gap: 6 }}>
        <div style={{ fontSize: 12, fontWeight: 600 }}>PlanSet Export</div>
        <button
          style={{ ...BUTTON_STYLE, width: "100%" }}
          disabled={!doc}
          onClick={onExportAutoPages}
        >
          Generate Auto Pages (DXF)
        </button>
        <button
          style={{ ...BUTTON_STYLE, width: "100%" }}
          disabled={!doc || isExportingPlansetPdf}
          onClick={onExportPagesPdf}
        >
          {isExportingPlansetPdf ? "Generating PlanSet PDF..." : "Generate PlanSet PDF"}
        </button>
      </div>

      <button
        style={{ ...SECTION_TOGGLE_STYLE, marginTop: 8 }}
        onClick={() => setShowProjectActions((prev) => !prev)}
      >
        <span>Project Actions</span>
        <span>{showProjectActions ? "−" : "+"}</span>
      </button>

      {showProjectActions && (
        <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
          <button style={BUTTON_STYLE} onClick={onSaveProject}>
            Save CADream Project
          </button>
          <button
            style={BUTTON_STYLE}
            onClick={() => loadProjectInputRef.current?.click()}
          >
            Load CADream Project
          </button>
          <button
            style={BUTTON_STYLE}
            disabled={!canExportDxf}
            onClick={onExportDxf}
          >
            Export Editable DXF
          </button>
        </div>
      )}

      <div style={{ marginTop: 8 }}>
        <button
          style={{ ...BUTTON_STYLE, width: "100%", marginBottom: 6 }}
          onClick={() => setShowMetadataForm((prev) => !prev)}
        >
          {showMetadataForm ? "Hide PlanSet Metadata" : "Edit PlanSet Metadata"}
        </button>
        {(isExportingPlansetPdf || plansetPdfProgress !== null) && (
          <div style={{ marginTop: 6 }}>
            <div style={{ width: "100%", height: 8, border: "1px solid #cbd5e1", borderRadius: 4, overflow: "hidden", background: "#f8fafc" }}>
              <div
                style={{
                  height: "100%",
                  width: `${plansetPdfProgress ?? 40}%`,
                  background: "#2563eb",
                  transition: "width 150ms linear",
                }}
              />
            </div>
            <div style={{ fontSize: 11, color: "#334155", marginTop: 4 }}>
              {plansetPdfProgress === null ? "Downloading PlanSet PDF..." : `Downloading PlanSet PDF... ${plansetPdfProgress}%`}
            </div>
          </div>
        )}
      </div>

      {showMetadataForm && (
        <div style={{ marginTop: 8, border: "1px solid #dbe3ef", borderRadius: 8, padding: 8, background: "#f8fbff" }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Metadata Form</div>

          <div style={{ display: "grid", gap: 6 }}>
            <input placeholder="AC System Size" value={rightPanelMetadata.ac_system_size} onChange={(e) => setRootField("ac_system_size", e.target.value)} />
            <input placeholder="Inverter Model" value={rightPanelMetadata.inverter_model} onChange={(e) => setRootField("inverter_model", e.target.value)} />
            <input placeholder="DC System Size" value={rightPanelMetadata.dc_system_size} onChange={(e) => setRootField("dc_system_size", e.target.value)} />
            <input placeholder="BESS" value={rightPanelMetadata.bess_model} onChange={(e) => setRootField("bess_model", e.target.value)} />

            <input placeholder="Customer Name" value={rightPanelMetadata.title_block.client_name} onChange={(e) => setTitleBlockField("client_name", e.target.value)} />
            <input placeholder="Customer Address" value={rightPanelMetadata.title_block.site_address} onChange={(e) => setTitleBlockField("site_address", e.target.value)} />
            <input placeholder="Customer Website" value={rightPanelMetadata.customer_website} onChange={(e) => setRootField("customer_website", e.target.value)} />
            <input placeholder="Customer Phone" value={rightPanelMetadata.customer_phone} onChange={(e) => setRootField("customer_phone", e.target.value)} />
            <input placeholder="Customer Contact" value={rightPanelMetadata.customer_contact} onChange={(e) => setRootField("customer_contact", e.target.value)} />

            <input placeholder="AHJ" value={rightPanelMetadata.ahj} onChange={(e) => setRootField("ahj", e.target.value)} />
            <input placeholder="EQORE Project" value={rightPanelMetadata.title_block.project_name} onChange={(e) => setTitleBlockField("project_name", e.target.value)} />

            <input placeholder="Designer Company" value={rightPanelMetadata.designer_company} onChange={(e) => setRootField("designer_company", e.target.value)} />
            <input placeholder="Designer Address" value={rightPanelMetadata.designer_address} onChange={(e) => setRootField("designer_address", e.target.value)} />
            <input placeholder="Designer Website" value={rightPanelMetadata.designer_website} onChange={(e) => setRootField("designer_website", e.target.value)} />
            <input placeholder="Designer Phone" value={rightPanelMetadata.designer_phone} onChange={(e) => setRootField("designer_phone", e.target.value)} />
            <input placeholder="Designer Contact" value={rightPanelMetadata.designer_contact} onChange={(e) => setRootField("designer_contact", e.target.value)} />

            <input placeholder="Page Notes" value={rightPanelMetadata.page_notes} onChange={(e) => setRootField("page_notes", e.target.value)} />

            <input placeholder="Scale" value={rightPanelMetadata.sheet_metadata.scale} onChange={(e) => setSheetMetadataField("scale", e.target.value)} />
            <input placeholder="Sheet" value={rightPanelMetadata.sheet_metadata.sheet_title} onChange={(e) => setSheetMetadataField("sheet_title", e.target.value)} />
            <input placeholder="Drawn By" value={rightPanelMetadata.sheet_metadata.drawn_by} onChange={(e) => setSheetMetadataField("drawn_by", e.target.value)} />
            <input placeholder="Checked By" value={rightPanelMetadata.sheet_metadata.checked_by} onChange={(e) => setSheetMetadataField("checked_by", e.target.value)} />
            <input placeholder="Approved By" value={rightPanelMetadata.sheet_metadata.approved_by} onChange={(e) => setSheetMetadataField("approved_by", e.target.value)} />
            <input placeholder="Date" value={rightPanelMetadata.sheet_metadata.issue_date} onChange={(e) => setSheetMetadataField("issue_date", e.target.value)} />
            <input placeholder="Sheet No" value={rightPanelMetadata.sheet_metadata.sheet_number} onChange={(e) => setSheetMetadataField("sheet_number", e.target.value)} />
            <input placeholder="Revision" value={rightPanelMetadata.sheet_metadata.revision} onChange={(e) => setSheetMetadataField("revision", e.target.value)} />

            <label style={{ fontSize: 12 }}>
              Engineer Signature Image
              <input
                type="file"
                accept="image/png,image/jpeg,image/jpg"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (file) {
                    try {
                      await onSignatureUpload(file);
                    } catch {
                      // ignore upload error in UI for now
                    }
                  }
                }}
              />
            </label>
          </div>
        </div>
      )}

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

      <button
        style={SECTION_TOGGLE_STYLE}
        onClick={() => setShowSiteEditing((prev) => !prev)}
      >
        <span>Site Editing</span>
        <span>{showSiteEditing ? "−" : "+"}</span>
      </button>

      {showSiteEditing && (
        <>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, marginTop: 8 }}>Site Editing</div>

          <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
            {TOOL_BUTTONS.map((tool) => (
              <button
                key={tool.mode}
                style={{ ...BUTTON_STYLE, background: toolMode === tool.mode ? "#eee" : "white" }}
                disabled={tool.requiresDoc && !doc}
                onClick={() => onSetToolMode(tool.mode)}
              >
                {tool.label}
              </button>
            ))}
          </div>

          <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
            <button
              style={BUTTON_STYLE}
              disabled={selectedBessId === null}
              onClick={onDeleteSelectedBess}
            >
              Delete Selected
            </button>
            <button style={BUTTON_STYLE} disabled={bessPlacements.length === 0} onClick={onClearBess}>
              Clear BESS
            </button>
          </div>

          <div style={{ fontSize: 12, color: "#475569", marginBottom: 8 }}>{TOOL_HINTS[toolMode]}</div>

          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 4 }}>
            <span style={{ fontSize: 11, border: "1px solid #cbd5e1", borderRadius: 999, padding: "2px 7px", background: "#fff" }}>
              BESS: {bessPlacements.length}
            </span>
            <span style={{ fontSize: 11, border: "1px solid #cbd5e1", borderRadius: 999, padding: "2px 7px", background: "#fff" }}>
              POI: {hasPoi ? "Set" : "Not set"}
            </span>
            <span style={{ fontSize: 11, border: "1px solid #cbd5e1", borderRadius: 999, padding: "2px 7px", background: "#fff" }}>
              Cables: {cablePaths.length}
            </span>
          </div>

          <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
            <button style={BUTTON_STYLE} disabled={!hasPoi} onClick={onClearPoi}>
              Clear POI
            </button>
          </div>

          <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
            <button
              style={BUTTON_STYLE}
              disabled={draftCablePoints.length < 2 || !hasPoi}
              onClick={onFinishCable}
              title={!hasPoi ? "Set POI before finishing cable path." : "Finalize current cable draft."}
            >
              Finish Cable
            </button>
            <button
              style={BUTTON_STYLE}
              disabled={draftCablePoints.length === 0}
              onClick={onCancelCableDraft}
            >
              Cancel Draft
            </button>
          </div>

          <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
            <button
              style={BUTTON_STYLE}
              disabled={selectedCableId === null}
              onClick={onDeleteSelectedCable}
            >
              Delete Cable
            </button>
            <button
              style={BUTTON_STYLE}
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
        </>
      )}

      <hr />

      <button
        style={SECTION_TOGGLE_STYLE}
        onClick={() => setShowLayers((prev) => !prev)}
      >
        <span>Layers</span>
        <span>{showLayers ? "−" : "+"}</span>
      </button>

      {showLayers && (
        <>
          {!doc && <div style={{ fontSize: 12, color: "#666", marginTop: 8 }}>Upload a DXF to begin.</div>}

          {doc?.layers?.slice(0, 400).map((layer) => (
            <label key={layer.name} style={{ display: "block", fontSize: 12, cursor: "pointer", marginTop: 4 }}>
              <input
                type="checkbox"
                checked={!hiddenLayers[layer.name]}
                onChange={() => onToggleLayer(layer.name)}
                style={{ marginRight: 6 }}
              />
              {layer.name}
            </label>
          ))}
        </>
      )}
    </div>
  );
}
