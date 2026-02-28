import { useMemo, useRef, useState } from "react";
import type { DragEvent, MouseEvent } from "react";
import type { SldToolMode } from "../../types/cad";
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
  onAddNode: (type: SldSymbolType, x: number, y: number) => void;
  onMoveNode: (nodeId: string, x: number, y: number) => void;
  onSelectNode: (nodeId: string | null) => void;
  onSelectEdge: (edgeId: string | null) => void;
  onDeleteSelection: () => void;
  onBeginOrCompleteConnection: (nodeId: string, terminalId: string) => void;
  onAddWireDraftCorner: (point: number[]) => void;
  onUpdateWireDraftCursor: (point: number[] | null) => void;
  onBeginReconnect: (endpoint: "from" | "to") => void;
  onCancelDrafts: () => void;
  onClearAll: () => void;
};

const TOOL_BUTTON_STYLE = { padding: "6px 10px", border: "1px solid #ccc", borderRadius: 6 };
const TERMINAL_SNAP_RADIUS = 14;

export default function SldBuilder({
  session,
  palette,
  selectedNodeId,
  selectedEdgeId,
  wireDraft,
  reconnectDraft,
  onSetToolMode,
  onAddNode,
  onMoveNode,
  onSelectNode,
  onSelectEdge,
  onDeleteSelection,
  onBeginOrCompleteConnection,
  onAddWireDraftCorner,
  onUpdateWireDraftCursor,
  onBeginReconnect,
  onCancelDrafts,
  onClearAll,
}: SldBuilderProps) {
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const [paletteCollapsed, setPaletteCollapsed] = useState(false);
  const [dragState, setDragState] = useState<{
    nodeId: string;
    offsetX: number;
    offsetY: number;
  } | null>(null);

  const selectedNode = useMemo(
    () => session.nodes.find((node) => node.id === selectedNodeId) ?? null,
    [session.nodes, selectedNodeId]
  );

  const selectedEdge = useMemo(
    () => session.edges.find((edge) => edge.id === selectedEdgeId) ?? null,
    [session.edges, selectedEdgeId]
  );

  function canvasPoint(clientX: number, clientY: number) {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return null;
    return { x: clientX - rect.left, y: clientY - rect.top };
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

    onAddNode(symbolType as SldSymbolType, point.x, point.y);
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
    onMoveNode(dragState.nodeId, point.x - dragState.offsetX, point.y - dragState.offsetY);
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

  function isTerminalConnected(nodeId: string, terminalId: string) {
    return session.edges.some(
      (edge) =>
        (edge.from_node_id === nodeId && edge.from_terminal_id === terminalId) ||
        (edge.to_node_id === nodeId && edge.to_terminal_id === terminalId)
    );
  }

  const isWireMode = session.tool_settings.tool_mode === "connect";

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
              minWidth: 28,
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
                minWidth: 64,
              }}
              onClick={() => onSetToolMode(mode)}
            >
              {mode}
            </button>
          ))}
          <button style={TOOL_BUTTON_STYLE} onClick={onDeleteSelection}>
            Delete Selection
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
        </div>

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
                  if (session.tool_settings.tool_mode !== "connect") return;
                  e.stopPropagation();
                  trySnapAtClientPoint(e.clientX, e.clientY);
                }}
                style={{
                  position: "absolute",
                  left: node.x,
                  top: node.y,
                  width: symbol.width,
                  height: symbol.height,
                  border: `2px solid ${selected ? "#2563eb" : "#999"}`,
                  borderRadius: 8,
                  background: "#fff",
                  boxSizing: "border-box",
                  cursor: session.tool_settings.tool_mode === "select" ? "move" : "default",
                  userSelect: "none",
                }}
              >
                <SldSymbolGlyph type={node.symbol_type as SldSymbolType} width={symbol.width} height={symbol.height} />

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
        <div
          style={{
            borderTop: "1px solid #dbe1ea",
            background: "#ffffff",
            padding: "8px 12px",
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8, color: "#0f172a" }}>
            Inspector
          </div>

          <div style={{ display: "flex", gap: 20, flexWrap: "wrap", fontSize: 12, color: "#334155" }}>
            <div>
              <div style={{ fontWeight: 700 }}>Summary</div>
              <div>Nodes: {session.nodes.length}</div>
              <div>Edges: {session.edges.length}</div>
            </div>

            <div>
              <div style={{ fontWeight: 700 }}>Selection</div>
              {selectedNode ? (
                <>
                  <div>Node: {selectedNode.id}</div>
                  <div>Type: {selectedNode.symbol_type}</div>
                  <div>
                    Position: {Math.round(selectedNode.x)}, {Math.round(selectedNode.y)}
                  </div>
                </>
              ) : selectedEdge ? (
                <>
                  <div>Edge: {selectedEdge.id}</div>
                  <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                    <button style={TOOL_BUTTON_STYLE} onClick={() => onBeginReconnect("from")}>
                      Reconnect Start
                    </button>
                    <button style={TOOL_BUTTON_STYLE} onClick={() => onBeginReconnect("to")}>
                      Reconnect End
                    </button>
                  </div>
                </>
              ) : (
                <div>No selection</div>
              )}
            </div>

            <div>
              <div style={{ fontWeight: 700 }}>Terminal Legend</div>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: "50%",
                    display: "inline-block",
                    background: "#9ca3af",
                    border: "1px solid #000",
                  }}
                />
                Open
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: "50%",
                    display: "inline-block",
                    background: "#000",
                    border: "1px solid #000",
                  }}
                />
                Connected
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: "50%",
                    display: "inline-block",
                    background: "#f97316",
                    border: "1px solid #000",
                  }}
                />
                Active start
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
