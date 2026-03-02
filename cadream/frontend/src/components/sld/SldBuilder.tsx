import { useMemo, useRef, useState } from "react";
import type { ChangeEvent, DragEvent, MouseEvent } from "react";
import type { SldSessionState, SldToolMode } from "../../types/cad";
import type { SldPaletteItem, SldSymbolType } from "../../types/sld";
import { getSldSymbolDefinition } from "../../utils/sld/symbolRegistry";
import { orthogonalLeg } from "../../utils/sld/validation";
import SldSymbolGlyph from "./SldSymbolGlyph";

type SldBuilderProps = {
  session: {
    nodes: Array<{
      id: string;
      symbol_type: string;
      label: string;
      x: number;
      y: number;
      terminals: Array<{ id: string; x: number; y: number; role: "line" | "in" | "out" }>;
    }>;
    edges: Array<{
      id: string;
      from_node_id: string;
      from_terminal_id: string;
      to_node_id: string;
      to_terminal_id: string;
      points: number[][];
    }>;
    tool_settings: {
      tool_mode: SldToolMode;
    };
  };
  palette: SldPaletteItem[];
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  wireDraft: { fromNodeId: string; fromTerminalId: string; points: number[][]; cursor: number[] | null } | null;
  reconnectDraft: { edgeId: string; endpoint: "from" | "to" } | null;
  onSetToolMode: (mode: SldToolMode) => void;
  onUndo: () => void;
  onRedo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  onAddNode: (type: SldSymbolType, x: number, y: number) => void;
  onMoveNode: (nodeId: string, x: number, y: number) => void;
  onSelectNode: (nodeId: string | null) => void;
  onSelectEdge: (edgeId: string | null) => void;
  onDeleteSelection: () => void;
  onBeginOrCompleteConnection: (nodeId: string, terminalId: string) => void;
  onAddWireDraftCorner: (point: number[]) => void;
  onUpdateWireDraftCursor: (point: number[] | null) => void;
  onCancelDrafts: () => void;
  onClearAll: () => void;
  onLoadSession: (session: SldSessionState) => void;
};

const TOOL_BUTTON_STYLE = {
  minHeight: 34,
  minWidth: 150,
  padding: "6px 10px",
  border: "1px solid #cfd7e3",
  borderRadius: 6,
  background: "#fff",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  textAlign: "center" as const,
  fontSize: 13,
  color: "#0f172a",
} as const;
const TERMINAL_SNAP_RADIUS = 14;
const SLD_CANVAS_NODE_HEIGHT = 64;
const SLD_CANVAS_SAFE_MARGIN = 24;
const CIRCULAR_SYMBOL_TYPES = new Set(["utility-grid", "load"]);

export default function SldBuilder({
  session,
  palette,
  selectedNodeId,
  selectedEdgeId,
  wireDraft,
  reconnectDraft,
  onSetToolMode,
  onUndo,
  onRedo,
  canUndo,
  canRedo,
  onAddNode,
  onMoveNode,
  onSelectNode,
  onSelectEdge,
  onDeleteSelection,
  onBeginOrCompleteConnection,
  onAddWireDraftCorner,
  onUpdateWireDraftCursor,
  onCancelDrafts,
  onClearAll,
  onLoadSession,
}: SldBuilderProps) {
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const [paletteCollapsed, setPaletteCollapsed] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [dragState, setDragState] = useState<{
    nodeId: string;
    offsetX: number;
    offsetY: number;
  } | null>(null);

  function canvasPoint(clientX: number, clientY: number) {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return null;
    return { x: clientX - rect.left, y: clientY - rect.top };
  }

  function clampNodePosition(x: number, y: number, nodeWidth: number) {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return { x, y };

    const maxX = Math.max(SLD_CANVAS_SAFE_MARGIN, rect.width - nodeWidth - SLD_CANVAS_SAFE_MARGIN);
    const maxY = Math.max(SLD_CANVAS_SAFE_MARGIN, rect.height - SLD_CANVAS_NODE_HEIGHT - SLD_CANVAS_SAFE_MARGIN);

    return {
      x: Math.min(Math.max(x, SLD_CANVAS_SAFE_MARGIN), maxX),
      y: Math.min(Math.max(y, SLD_CANVAS_SAFE_MARGIN), maxY),
    };
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    const symbolType = e.dataTransfer.getData("application/x-sld-symbol");
    if (!symbolType) return;

    if (symbolType === "wire") {
      onSetToolMode("connect");
      return;
    }

    const point = canvasPoint(e.clientX, e.clientY);
    if (!point) return;

    const symbol = getSldSymbolDefinition(symbolType);
    const clamped = clampNodePosition(point.x, point.y, symbol?.width ?? 120);
    onAddNode(symbolType as SldSymbolType, clamped.x, clamped.y);
  }

  function handleCanvasMouseMove(e: MouseEvent<HTMLDivElement>) {
    moveDraggedNode(e);
    if (!wireDraft) return;
    const point = canvasPoint(e.clientX, e.clientY);
    if (!point) return;
    onUpdateWireDraftCursor([point.x, point.y]);
  }

  function startNodeDrag(e: MouseEvent<HTMLDivElement>, nodeId: string, nodeX: number, nodeY: number) {
    const point = canvasPoint(e.clientX, e.clientY);
    if (!point) return;
    setDragState({
      nodeId,
      offsetX: point.x - nodeX,
      offsetY: point.y - nodeY,
    });
  }

  function moveDraggedNode(e: MouseEvent<HTMLDivElement>) {
    if (!dragState) return;
    const point = canvasPoint(e.clientX, e.clientY);
    if (!point) return;

    const node = session.nodes.find((item) => item.id === dragState.nodeId);
    const symbol = node ? getSldSymbolDefinition(node.symbol_type) : null;
    const clamped = clampNodePosition(point.x - dragState.offsetX, point.y - dragState.offsetY, symbol?.width ?? 120);
    onMoveNode(dragState.nodeId, clamped.x, clamped.y);
  }

  function stopNodeDrag() {
    if (!dragState) return;
    setDragState(null);
  }

  function findNearestTerminal(point: { x: number; y: number }) {
    let best:
      | {
          nodeId: string;
          terminalId: string;
          distance: number;
        }
      | null = null;

    for (const node of session.nodes) {
      for (const terminal of node.terminals) {
        const tx = node.x + terminal.x;
        const ty = node.y + terminal.y;
        const dx = tx - point.x;
        const dy = ty - point.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance <= TERMINAL_SNAP_RADIUS && (!best || distance < best.distance)) {
          best = {
            nodeId: node.id,
            terminalId: terminal.id,
            distance,
          };
        }
      }
    }

    return best;
  }

  function trySnapAtClientPoint(clientX: number, clientY: number) {
    const point = canvasPoint(clientX, clientY);
    if (!point) return false;
    const nearest = findNearestTerminal(point);
    if (!nearest) return false;
    onBeginOrCompleteConnection(nearest.nodeId, nearest.terminalId);
    return true;
  }

  const draftPreviewPoints = useMemo(() => {
    if (!wireDraft || wireDraft.points.length === 0 || !wireDraft.cursor) return null;
    const last = wireDraft.points[wireDraft.points.length - 1];
    const tail = orthogonalLeg(last, wireDraft.cursor);
    return [...wireDraft.points, ...tail];
  }, [wireDraft]);

  const selectedNode = useMemo(
    () => session.nodes.find((node) => node.id === selectedNodeId) ?? null,
    [session.nodes, selectedNodeId]
  );

  const selectedEdge = useMemo(
    () => session.edges.find((edge) => edge.id === selectedEdgeId) ?? null,
    [session.edges, selectedEdgeId]
  );

  const selectedSummary = useMemo(() => {
    if (selectedNode) {
      const cleanLabel = selectedNode.label.replace(/\s+\d+$/, "").trim();
      return `Selected: ${cleanLabel || selectedNode.symbol_type}`;
    }

    if (selectedEdge) {
      const fromNode = session.nodes.find((node) => node.id === selectedEdge.from_node_id);
      const toNode = session.nodes.find((node) => node.id === selectedEdge.to_node_id);

      const fromLabel = fromNode?.label ?? selectedEdge.from_node_id;
      const toLabel = toNode?.label ?? selectedEdge.to_node_id;

      return `Selected: Connection (${fromLabel} → ${toLabel})`;
    }

    return "Selected: none";
  }, [selectedNode, selectedEdge, session.nodes]);

  function isTerminalConnected(nodeId: string, terminalId: string) {
    return session.edges.some(
      (edge) =>
        (edge.from_node_id === nodeId && edge.from_terminal_id === terminalId) ||
        (edge.to_node_id === nodeId && edge.to_terminal_id === terminalId)
    );
  }

  const isWireMode = session.tool_settings.tool_mode === "connect";

  function normalizeSldSession(input: unknown): SldSessionState | null {
    const root = input as Record<string, unknown>;

    const candidate =
      root && typeof root === "object" && root.interfaces && typeof root.interfaces === "object"
        ? (root.interfaces as Record<string, unknown>).single_line_diagram_builder
        : input;

    if (!candidate || typeof candidate !== "object") return null;
    const source = candidate as Record<string, unknown>;

    const rawNodes = Array.isArray(source.nodes) ? source.nodes : [];
    const rawEdges = Array.isArray(source.edges) ? source.edges : [];

    const nodes: SldSessionState["nodes"] = [];
    for (const node of rawNodes) {
      if (!node || typeof node !== "object") continue;
      const value = node as Record<string, unknown>;
      if (
        typeof value.id !== "string" ||
        typeof value.symbol_type !== "string" ||
        typeof value.label !== "string" ||
        typeof value.x !== "number" ||
        typeof value.y !== "number"
      ) {
        continue;
      }

      const terminals: SldSessionState["nodes"][number]["terminals"] = [];
      if (Array.isArray(value.terminals)) {
        for (const terminal of value.terminals) {
          if (!terminal || typeof terminal !== "object") continue;
          const next = terminal as Record<string, unknown>;
          if (
            typeof next.id !== "string" ||
            typeof next.x !== "number" ||
            typeof next.y !== "number" ||
            (next.role !== "line" && next.role !== "in" && next.role !== "out")
          ) {
            continue;
          }

          terminals.push({
            id: next.id,
            x: next.x,
            y: next.y,
            role: next.role,
          });
        }
      }

      nodes.push({
        id: value.id,
        symbol_type: value.symbol_type,
        label: value.label,
        x: value.x,
        y: value.y,
        rotation_deg: typeof value.rotation_deg === "number" ? value.rotation_deg : 0,
        terminals,
        metadata: value.metadata as Record<string, unknown> | undefined,
      });
    }

    const edges: SldSessionState["edges"] = [];
    for (const edge of rawEdges) {
      if (!edge || typeof edge !== "object") continue;
      const value = edge as Record<string, unknown>;
      if (
        typeof value.id !== "string" ||
        typeof value.from_node_id !== "string" ||
        typeof value.from_terminal_id !== "string" ||
        typeof value.to_node_id !== "string" ||
        typeof value.to_terminal_id !== "string"
      ) {
        continue;
      }

      const points: number[][] = [];
      if (Array.isArray(value.points)) {
        for (const point of value.points) {
          if (Array.isArray(point) && point.length >= 2 && typeof point[0] === "number" && typeof point[1] === "number") {
            points.push([point[0], point[1]]);
          }
        }
      }

      edges.push({
        id: value.id,
        from_node_id: value.from_node_id,
        from_terminal_id: value.from_terminal_id,
        to_node_id: value.to_node_id,
        to_terminal_id: value.to_terminal_id,
        points,
        metadata: value.metadata as Record<string, unknown> | undefined,
      });
    }

    const rawToolSettings =
      source.tool_settings && typeof source.tool_settings === "object"
        ? (source.tool_settings as Record<string, unknown>)
        : {};

    const rawViewport =
      rawToolSettings.viewport && typeof rawToolSettings.viewport === "object"
        ? (rawToolSettings.viewport as Record<string, unknown>)
        : {};

    const rawPos =
      rawViewport.pos && typeof rawViewport.pos === "object"
        ? (rawViewport.pos as Record<string, unknown>)
        : {};

    const toolMode =
      rawToolSettings.tool_mode === "select" || rawToolSettings.tool_mode === "pan" || rawToolSettings.tool_mode === "connect"
        ? rawToolSettings.tool_mode
        : "select";

    return {
      schema_version: "sld-v1",
      nodes,
      edges,
      tool_settings: {
        tool_mode: toolMode,
        viewport: {
          scale: typeof rawViewport.scale === "number" ? rawViewport.scale : 1,
          pos: {
            x: typeof rawPos.x === "number" ? rawPos.x : 0,
            y: typeof rawPos.y === "number" ? rawPos.y : 0,
          },
        },
      },
    };
  }

  async function handleImportSldFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.currentTarget.value = "";
    if (!file) return;

    try {
      const raw = await file.text();
      const parsed = JSON.parse(raw) as unknown;
      const normalized = normalizeSldSession(parsed);

      if (!normalized) {
        setImportError("Invalid SLD JSON format.");
        return;
      }

      onLoadSession(normalized);
      setImportError(null);
    } catch {
      setImportError("Failed to import SLD JSON.");
    }
  }

  return (
    <div style={{ display: "flex", height: "100%", background: "#f8fafc", minWidth: 0 }}>
      <div
        style={{
          width: paletteCollapsed ? 42 : 250,
          borderRight: "1px solid #dbe1ea",
          padding: paletteCollapsed ? "10px 6px" : 10,
          overflow: "auto",
          background: "#ffffff",
          transition: "width 0.15s ease",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: paletteCollapsed ? "center" : "space-between",
            marginBottom: 8,
          }}
        >
          {!paletteCollapsed && (
            <div style={{ fontSize: 13, fontWeight: 700, color: "#0f172a" }}>SLD Symbol Palette</div>
          )}
          <button
            style={{
              ...TOOL_BUTTON_STYLE,
              padding: "4px 6px",
                minWidth: 34,
              lineHeight: 1,
              border: "1px solid #cfd7e3",
              background: "#fff",
            }}
            onClick={() => setPaletteCollapsed((prev) => !prev)}
            title={paletteCollapsed ? "Expand palette" : "Collapse palette"}
          >
            {paletteCollapsed ? ">" : "<"}
          </button>
        </div>

        {!paletteCollapsed &&
          palette.map((symbol) => (
            <div
              key={symbol.type}
              draggable
              onDragStart={(e) => e.dataTransfer.setData("application/x-sld-symbol", symbol.type)}
              onClick={() => {
                if (symbol.kind === "wire") {
                  onSetToolMode("connect");
                }
              }}
              style={{
                border: "1px solid #d8dde6",
                borderRadius: 6,
                padding: "9px 8px",
                marginBottom: 8,
                cursor: "grab",
                textAlign: "left",
                fontSize: 13,
                background:
                  symbol.kind === "wire" && isWireMode
                    ? "#e8f0ff"
                    : "#fafbfc",
                display: "flex",
                alignItems: "center",
                gap: 8,
                color: "#0f172a",
              }}
            >
              {symbol.kind === "wire" ? (
                <svg width="28" height="10" viewBox="0 0 28 10" aria-hidden>
                  <polyline points="1,5 12,5 12,2 27,2" fill="none" stroke="#111" strokeWidth="1.5" />
                </svg>
              ) : (
                <div
                  style={{
                    width: 18,
                    height: 18,
                    border: "1px solid #777",
                    borderRadius: 4,
                    background: "#fff",
                  }}
                />
              )}
              {symbol.label}
            </div>
          ))}

        {!paletteCollapsed && (
          <div style={{ marginTop: 14, fontSize: 12, color: "#666", textAlign: "left" }}>
            Drag symbols into the canvas. Use Connect mode and click terminals to wire nodes.
          </div>
        )}
      </div>

      <div
        style={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          background: "#f8fafc",
        }}
      >
        <div
          style={{
            display: "flex",
            gap: 8,
            flexWrap: "wrap",
            padding: "10px 12px",
            borderBottom: "1px solid #e2e8f0",
            background: "#ffffff",
          }}
        >
          {(["select", "connect", "pan"] as SldToolMode[]).map((mode) => (
            <button
              key={mode}
              style={{
                ...TOOL_BUTTON_STYLE,
                background: session.tool_settings.tool_mode === mode ? "#e8f0ff" : "#fff",
                border: session.tool_settings.tool_mode === mode ? "1px solid #9db6ff" : "1px solid #cfd7e3",
              }}
              onClick={() => onSetToolMode(mode)}
            >
              {mode.charAt(0).toUpperCase() + mode.slice(1)}
            </button>
          ))}
          <button style={TOOL_BUTTON_STYLE} onClick={onUndo} disabled={!canUndo}>
            Undo
          </button>
          <button style={TOOL_BUTTON_STYLE} onClick={onRedo} disabled={!canRedo}>
            Redo
          </button>
          <button
            style={TOOL_BUTTON_STYLE}
            onClick={onDeleteSelection}
            disabled={selectedNodeId === null}
            title={selectedNodeId ? "Delete selected symbol" : "Select a symbol to delete"}
          >
            Delete Symbol
          </button>
          <button
            style={TOOL_BUTTON_STYLE}
            onClick={onDeleteSelection}
            disabled={selectedEdgeId === null}
            title={selectedEdgeId ? "Remove selected connection" : "Select a connection to remove"}
          >
            Remove Connection
          </button>
          <button style={TOOL_BUTTON_STYLE} onClick={onCancelDrafts}>
            Cancel Draft
          </button>
          <button style={TOOL_BUTTON_STYLE} onClick={onClearAll}>
            Clear Canvas
          </button>
          <button style={TOOL_BUTTON_STYLE} onClick={() => importInputRef.current?.click()}>
            Import SLD JSON
          </button>
          <input
            ref={importInputRef}
            type="file"
            accept=".json,application/json"
            style={{ display: "none" }}
            onChange={(e) => void handleImportSldFile(e)}
          />
          <div
            style={{
              alignSelf: "center",
              padding: "4px 8px",
              borderRadius: 999,
              border: "1px solid #d6deea",
              background: "#f8fafc",
              fontSize: 12,
              color: "#334155",
            }}
          >
            {selectedSummary}
          </div>
          <div style={{ marginLeft: "auto", fontSize: 12, color: "#475569", alignSelf: "center" }}>
            Nodes: {session.nodes.length} · Edges: {session.edges.length}
          </div>
        </div>

        {importError && (
          <div
            style={{
              margin: "8px 12px",
              padding: "8px 10px",
              fontSize: 12,
              borderRadius: 6,
              border: "1px solid #fecaca",
              background: "#fef2f2",
              color: "#7f1d1d",
            }}
          >
            {importError}
          </div>
        )}

        <div
          ref={canvasRef}
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          onMouseMove={handleCanvasMouseMove}
          onMouseUp={stopNodeDrag}
          onMouseLeave={() => {
            stopNodeDrag();
            onUpdateWireDraftCursor(null);
          }}
          onClick={(e) => {
            if (session.tool_settings.tool_mode === "connect") {
              if (trySnapAtClientPoint(e.clientX, e.clientY)) {
                return;
              }

              const point = canvasPoint(e.clientX, e.clientY);
              if (!point) return;

              if (wireDraft) {
                onAddWireDraftCorner([point.x, point.y]);
                return;
              }
            }
            onSelectNode(null);
            onSelectEdge(null);
          }}
          style={{
            flex: 1,
            position: "relative",
            margin: 10,
            border: "1px solid #d7deea",
            borderRadius: 8,
            backgroundColor: "#ffffff",
            backgroundImage:
              "linear-gradient(to right, #f1f1f1 1px, transparent 1px), linear-gradient(to bottom, #f1f1f1 1px, transparent 1px)",
            backgroundSize: "24px 24px",
            overflow: "hidden",
          }}
        >
          <svg
            width="100%"
            height="100%"
            style={{ position: "absolute", inset: 0, overflow: "visible" }}
          >
            {session.edges.map((edge) => {
              const points = edge.points;
              if (points.length < 2) return null;
              const selected = edge.id === selectedEdgeId;
              const polylinePoints = points.map((point) => `${point[0]},${point[1]}`).join(" ");
              return (
                <g key={edge.id}>
                  <polyline
                    points={polylinePoints}
                    fill="none"
                    stroke={selected ? "#2563eb" : "#1f2937"}
                    strokeWidth={selected ? 3 : 2}
                    pointerEvents="stroke"
                    style={{ pointerEvents: "stroke", cursor: "pointer" }}
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectEdge(edge.id);
                    }}
                  />
                </g>
              );
            })}

            {draftPreviewPoints && draftPreviewPoints.length >= 2 && (
              <polyline
                points={draftPreviewPoints.map((point) => `${point[0]},${point[1]}`).join(" ")}
                fill="none"
                stroke="#f97316"
                strokeWidth={2}
                strokeDasharray="8 6"
              />
            )}
          </svg>

          {session.nodes.map((node) => {
            const symbol = getSldSymbolDefinition(node.symbol_type);
            if (!symbol) return null;

            const selected = node.id === selectedNodeId;
            const boxHeight = SLD_CANVAS_NODE_HEIGHT;
            const isCircularSymbol = CIRCULAR_SYMBOL_TYPES.has(node.symbol_type);
            return (
              <div
                key={node.id}
                onMouseDown={(e) => {
                  e.stopPropagation();
                  onSelectNode(node.id);
                  if (session.tool_settings.tool_mode !== "select") return;
                  startNodeDrag(e, node.id, node.x, node.y);
                }}
                onClick={(e) => {
                  e.stopPropagation();
                  if (session.tool_settings.tool_mode !== "connect") return;
                  trySnapAtClientPoint(e.clientX, e.clientY);
                }}
                style={{
                  position: "absolute",
                  left: node.x,
                  top: node.y,
                  width: symbol.width,
                  height: boxHeight,
                  border: isCircularSymbol ? "none" : `2px solid ${selected ? "#2563eb" : "#999"}`,
                  borderRadius: isCircularSymbol ? 999 : 8,
                  background: isCircularSymbol ? "transparent" : "#fff",
                  boxSizing: "border-box",
                  cursor: session.tool_settings.tool_mode === "select" ? "move" : "default",
                  userSelect: "none",
                }}
              >
                <SldSymbolGlyph type={node.symbol_type as SldSymbolType} width={symbol.width} height={boxHeight} />

                {node.terminals.map((terminal) => (
                  <button
                    key={`${node.id}-${terminal.id}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (
                        session.tool_settings.tool_mode === "connect" ||
                        reconnectDraft !== null
                      ) {
                        onBeginOrCompleteConnection(node.id, terminal.id);
                      }
                    }}
                    title={`${terminal.id} (${terminal.role})`}
                    style={{
                      position: "absolute",
                      left: terminal.x - 5,
                      top: terminal.y - 5,
                      width: 10,
                      height: 10,
                      borderRadius: "50%",
                      border: "1px solid #000",
                      background: (() => {
                        if (
                          wireDraft?.fromNodeId === node.id &&
                          wireDraft.fromTerminalId === terminal.id
                        ) {
                          return "#f97316";
                        }
                        if (isTerminalConnected(node.id, terminal.id)) return "#000";
                        return "#9ca3af";
                      })(),
                      padding: 0,
                      cursor:
                        session.tool_settings.tool_mode === "connect" || reconnectDraft
                          ? "crosshair"
                          : "default",
                    }}
                  />
                ))}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
