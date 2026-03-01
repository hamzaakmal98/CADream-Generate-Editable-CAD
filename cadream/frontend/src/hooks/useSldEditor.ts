import { useMemo, useState } from "react";
import type { SldEdge, SldNode, SldSessionState, SldToolMode } from "../types/cad";
import type { SldReconnectDraft, SldSymbolType, SldWireDraft } from "../types/sld";
import { computeNextCounter, makeDeterministicId } from "../utils/sld/ids";
import { SLD_PALETTE_ITEMS, getSldSymbolDefinition } from "../utils/sld/symbolRegistry";
import {
  buildOrthogonalEdgePoints,
  collapseDuplicatePoints,
  orthogonalLeg,
  validateSldSession,
} from "../utils/sld/validation";

const SLD_GRID_SIZE = 24;
const SLD_CANVAS_NODE_HEIGHT = 64;
const SLD_MIN_ROW_GAP = 48;
const SLD_ROW_START_MARGIN = 24;

function snapToGrid(value: number) {
  return Math.round(value / SLD_GRID_SIZE) * SLD_GRID_SIZE;
}

function snapUpToGrid(value: number) {
  return Math.ceil(value / SLD_GRID_SIZE) * SLD_GRID_SIZE;
}

function nodeWidth(node: SldNode) {
  const symbol = getSldSymbolDefinition(node.symbol_type);
  if (symbol) return symbol.width;
  return Math.max(120, ...node.terminals.map((terminal) => terminal.x), 120);
}

function normalizeNodeTerminals(node: SldNode): SldNode {
  const symbol = getSldSymbolDefinition(node.symbol_type);
  const sourceHeight = symbol?.height ?? Math.max(1, ...node.terminals.map((terminal) => terminal.y), 1);
  const scaleY = SLD_CANVAS_NODE_HEIGHT / Math.max(sourceHeight, 1);

  return {
    ...node,
    x: snapToGrid(node.x),
    y: snapToGrid(node.y),
    terminals: node.terminals.map((terminal) => ({
      ...terminal,
      y: terminal.y * scaleY,
    })),
  };
}

function normalizeSldSessionGeometry(session: SldSessionState): SldSessionState {
  const normalizedNodes = session.nodes.map((node) => normalizeNodeTerminals(node));

  const rows = new Map<number, SldNode[]>();
  for (const node of normalizedNodes) {
    const rowKey = Math.round(node.y / SLD_GRID_SIZE);
    const bucket = rows.get(rowKey);
    if (bucket) {
      bucket.push(node);
    } else {
      rows.set(rowKey, [node]);
    }
  }

  const positionedById = new Map<string, SldNode>();
  const orderedRows = [...rows.keys()].sort((a, b) => a - b);
  for (const rowKey of orderedRows) {
    const rowNodes = [...(rows.get(rowKey) ?? [])].sort((a, b) => a.x - b.x);
    let nextX = SLD_ROW_START_MARGIN;

    for (const node of rowNodes) {
      const width = nodeWidth(node);
      const targetX = snapUpToGrid(Math.max(node.x, nextX));
      positionedById.set(node.id, { ...node, x: targetX });
      nextX = targetX + width + SLD_MIN_ROW_GAP;
    }
  }

  const nodes = normalizedNodes.map((node) => positionedById.get(node.id) ?? node);
  const edges = rerouteEdges(session.edges, nodes);

  return {
    ...session,
    nodes,
    edges,
  };
}

function defaultSldSession(): SldSessionState {
  return {
    schema_version: "sld-v1",
    nodes: [],
    edges: [],
    tool_settings: {
      tool_mode: "select",
      viewport: {
        scale: 1,
        pos: { x: 0, y: 0 },
      },
    },
  };
}

function hasEndpoint(node: SldNode, terminalId: string) {
  return node.terminals.some((terminal) => terminal.id === terminalId);
}

function terminalRole(node: SldNode, terminalId: string) {
  return node.terminals.find((terminal) => terminal.id === terminalId)?.role ?? null;
}

function canConnect(
  from: { node: SldNode; terminalId: string },
  to: { node: SldNode; terminalId: string }
): boolean {
  if (from.node.id === to.node.id && from.terminalId === to.terminalId) return false;

  if (!hasEndpoint(from.node, from.terminalId) || !hasEndpoint(to.node, to.terminalId)) return false;

  const fromRole = terminalRole(from.node, from.terminalId);
  const toRole = terminalRole(to.node, to.terminalId);
  if (!fromRole || !toRole) return false;
  if (fromRole === "line" || toRole === "line") return true;
  return fromRole === "out" && toRole === "in";
}

function shouldFlipEdgeDirection(edge: SldEdge, nodesById: Map<string, SldNode>) {
  const fromNode = nodesById.get(edge.from_node_id);
  const toNode = nodesById.get(edge.to_node_id);
  if (!fromNode || !toNode) return false;

  const fromRole = terminalRole(fromNode, edge.from_terminal_id);
  const toRole = terminalRole(toNode, edge.to_terminal_id);
  if (!fromRole || !toRole) return false;
  if (fromRole === "line" || toRole === "line") return false;
  return fromRole === "in" && toRole === "out";
}

function canonicalizeEdgeDirection(edge: SldEdge, nodesById: Map<string, SldNode>): SldEdge {
  if (!shouldFlipEdgeDirection(edge, nodesById)) return edge;

  return {
    ...edge,
    from_node_id: edge.to_node_id,
    from_terminal_id: edge.to_terminal_id,
    to_node_id: edge.from_node_id,
    to_terminal_id: edge.from_terminal_id,
    points: [...edge.points].reverse(),
  };
}

function rerouteEdges(edges: SldEdge[], nodes: SldNode[]): SldEdge[] {
  const nodesById = new Map<string, SldNode>(nodes.map((node) => [node.id, node]));

  return edges.map((edge) => {
    const oriented = canonicalizeEdgeDirection(edge, nodesById);
    return {
      ...oriented,
      points: buildOrthogonalEdgePoints(oriented, nodes),
    };
  });
}

export function useSldEditor() {
  const [session, setSession] = useState<SldSessionState>(defaultSldSession);
  const [undoStack, setUndoStack] = useState<SldSessionState[]>([]);
  const [redoStack, setRedoStack] = useState<SldSessionState[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [wireDraft, setWireDraft] = useState<SldWireDraft | null>(null);
  const [reconnectDraft, setReconnectDraft] = useState<SldReconnectDraft | null>(null);

  const issues = useMemo(() => validateSldSession(session), [session]);

  function commitSession(updater: (prev: SldSessionState) => SldSessionState) {
    setSession((prev) => {
      const next = updater(prev);
      if (next === prev) return prev;
      setUndoStack((history) => [...history.slice(-99), prev]);
      setRedoStack([]);
      return next;
    });
  }

  function setToolMode(mode: SldToolMode) {
    setSession((prev) => ({
      ...prev,
      tool_settings: {
        ...prev.tool_settings,
        tool_mode: mode,
      },
    }));
    setWireDraft(null);
    setReconnectDraft(null);
  }

  function loadSession(next: SldSessionState) {
    setSession(normalizeSldSessionGeometry(next));
    setUndoStack([]);
    setRedoStack([]);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setWireDraft(null);
    setReconnectDraft(null);
  }

  function undo() {
    setUndoStack((history) => {
      if (history.length === 0) return history;
      const previous = history[history.length - 1];
      setRedoStack((redo) => [...redo.slice(-99), session]);
      setSession(previous);
      setWireDraft(null);
      setReconnectDraft(null);
      setSelectedNodeId(null);
      setSelectedEdgeId(null);
      return history.slice(0, -1);
    });
  }

  function redo() {
    setRedoStack((history) => {
      if (history.length === 0) return history;
      const next = history[history.length - 1];
      setUndoStack((undoHistory) => [...undoHistory.slice(-99), session]);
      setSession(next);
      setWireDraft(null);
      setReconnectDraft(null);
      setSelectedNodeId(null);
      setSelectedEdgeId(null);
      return history.slice(0, -1);
    });
  }

  function absoluteTerminalPoint(node: SldNode, terminalId: string): number[] | null {
    const terminal = node.terminals.find((item) => item.id === terminalId);
    if (!terminal) return null;
    return [node.x + terminal.x, node.y + terminal.y];
  }

  function addNode(symbolType: SldSymbolType, x: number, y: number) {
    const symbol = getSldSymbolDefinition(symbolType);
    if (!symbol) return;

    commitSession((prev) => {
      const nextCounter = computeNextCounter(prev.nodes.map((node) => node.id), "node");
      const nodeId = makeDeterministicId("node", nextCounter);

      const node: SldNode = {
        id: nodeId,
        symbol_type: symbol.type,
        label: `${symbol.label} ${nextCounter}`,
        x: snapToGrid(x),
        y: snapToGrid(y),
        rotation_deg: 0,
        terminals: symbol.terminals.map((terminal) => ({
          id: terminal.id,
          x: terminal.x,
          y: terminal.y * (SLD_CANVAS_NODE_HEIGHT / Math.max(symbol.height, 1)),
          role: terminal.role,
        })),
        metadata: {
          cad_block_name: symbol.cad_block_name,
          cad_layer: symbol.cad_layer,
        },
      };

      return { ...prev, nodes: [...prev.nodes, node] };
    });

    setSelectedNodeId(null);
    setSelectedEdgeId(null);
  }

  function moveNode(nodeId: string, x: number, y: number) {
    commitSession((prev) => {
      const snappedX = snapToGrid(x);
      const snappedY = snapToGrid(y);
      const nodes = prev.nodes.map((node) => (node.id === nodeId ? { ...node, x: snappedX, y: snappedY } : node));
      const edges = rerouteEdges(prev.edges, nodes);
      return { ...prev, nodes, edges };
    });
  }

  function selectNode(nodeId: string | null) {
    setSelectedNodeId(nodeId);
    setSelectedEdgeId(null);
  }

  function selectEdge(edgeId: string | null) {
    setSelectedEdgeId(edgeId);
    setSelectedNodeId(null);
  }

  function deleteSelection() {
    if (selectedNodeId) {
      commitSession((prev) => {
        const nodes = prev.nodes.filter((node) => node.id !== selectedNodeId);
        const edges = prev.edges.filter(
          (edge) => edge.from_node_id !== selectedNodeId && edge.to_node_id !== selectedNodeId
        );
        return { ...prev, nodes, edges };
      });
      setSelectedNodeId(null);
      return;
    }

    if (selectedEdgeId) {
      commitSession((prev) => ({
        ...prev,
        edges: prev.edges.filter((edge) => edge.id !== selectedEdgeId),
      }));
      setSelectedEdgeId(null);
    }
  }

  function clearAll() {
    commitSession(() => defaultSldSession());
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setWireDraft(null);
    setReconnectDraft(null);
  }

  function updateWireDraftCursor(point: number[] | null) {
    setWireDraft((prev) => (prev ? { ...prev, cursor: point } : prev));
  }

  function addWireDraftCorner(point: number[]) {
    setWireDraft((prev) => {
      if (!prev || prev.points.length === 0) return prev;
      const last = prev.points[prev.points.length - 1];
      const leg = orthogonalLeg(last, point);
      return {
        ...prev,
        points: collapseDuplicatePoints([...prev.points, ...leg]),
      };
    });
  }

  function beginOrCompleteConnection(nodeId: string, terminalId: string) {
    const node = session.nodes.find((item) => item.id === nodeId);
    if (!node) return;

    if (reconnectDraft) {
      commitSession((prev) => {
        const edge = prev.edges.find((item) => item.id === reconnectDraft.edgeId);
        if (!edge) return prev;

        const endpointNode = prev.nodes.find((item) => item.id === nodeId);
        if (!endpointNode) return prev;

        const nextEdge =
          reconnectDraft.endpoint === "from"
            ? {
                ...edge,
                from_node_id: nodeId,
                from_terminal_id: terminalId,
              }
            : {
                ...edge,
                to_node_id: nodeId,
                to_terminal_id: terminalId,
              };

        const fromNode = prev.nodes.find((item) => item.id === nextEdge.from_node_id);
        const toNode = prev.nodes.find((item) => item.id === nextEdge.to_node_id);
        if (!fromNode || !toNode) return prev;

        if (
          !canConnect(
            { node: fromNode, terminalId: nextEdge.from_terminal_id },
            { node: toNode, terminalId: nextEdge.to_terminal_id }
          )
        ) {
          return prev;
        }

        const edges = prev.edges.map((item) =>
          item.id === edge.id
            ? {
                ...nextEdge,
                points: buildOrthogonalEdgePoints(nextEdge, prev.nodes),
              }
            : item
        );

        return { ...prev, edges };
      });

      setReconnectDraft(null);
      return;
    }

    if (!wireDraft) {
      const startPoint = absoluteTerminalPoint(node, terminalId);
      if (!startPoint) return;
      setWireDraft({
        fromNodeId: nodeId,
        fromTerminalId: terminalId,
        points: [startPoint],
        cursor: null,
      });
      return;
    }

    const fromNode = session.nodes.find((item) => item.id === wireDraft.fromNodeId);
    const toNode = session.nodes.find((item) => item.id === nodeId);
    if (!fromNode || !toNode) {
      setWireDraft(null);
      return;
    }

    const directConnection = canConnect(
      { node: fromNode, terminalId: wireDraft.fromTerminalId },
      { node: toNode, terminalId }
    );

    const reverseConnection = canConnect(
      { node: toNode, terminalId },
      { node: fromNode, terminalId: wireDraft.fromTerminalId }
    );

    if (!directConnection && !reverseConnection) {
      setWireDraft(null);
      return;
    }

    const endPoint = absoluteTerminalPoint(toNode, terminalId);
    if (!endPoint) {
      setWireDraft(null);
      return;
    }

    commitSession((prev) => {
      const nextCounter = computeNextCounter(prev.edges.map((edge) => edge.id), "edge");
      const edgeId = makeDeterministicId("edge", nextCounter);

      const committed = wireDraft.points.length > 0 ? wireDraft.points : [endPoint];
      const last = committed[committed.length - 1] ?? endPoint;
      const tail = orthogonalLeg(last, endPoint);
      const routedPoints = collapseDuplicatePoints([...committed, ...tail]);

      const shouldFlip = !directConnection && reverseConnection;

      const nextEdge: SldEdge = shouldFlip
        ? {
            id: edgeId,
            from_node_id: nodeId,
            from_terminal_id: terminalId,
            to_node_id: wireDraft.fromNodeId,
            to_terminal_id: wireDraft.fromTerminalId,
            points: buildOrthogonalEdgePoints(
              {
                from_node_id: nodeId,
                from_terminal_id: terminalId,
                to_node_id: wireDraft.fromNodeId,
                to_terminal_id: wireDraft.fromTerminalId,
              },
              prev.nodes
            ),
          }
        : {
            id: edgeId,
            from_node_id: wireDraft.fromNodeId,
            from_terminal_id: wireDraft.fromTerminalId,
            to_node_id: nodeId,
            to_terminal_id: terminalId,
            points: routedPoints,
          };
      return { ...prev, edges: [...prev.edges, nextEdge] };
    });

    setWireDraft(null);
  }

  function beginReconnect(endpoint: "from" | "to") {
    if (!selectedEdgeId) return;
    setReconnectDraft({ edgeId: selectedEdgeId, endpoint });
    setWireDraft(null);
  }

  function cancelDrafts() {
    setWireDraft(null);
    setReconnectDraft(null);
  }

  return {
    session,
    palette: SLD_PALETTE_ITEMS,
    selectedNodeId,
    selectedEdgeId,
    wireDraft,
    reconnectDraft,
    issues,
    canUndo: undoStack.length > 0,
    canRedo: redoStack.length > 0,
    setToolMode,
    loadSession,
    undo,
    redo,
    addNode,
    moveNode,
    selectNode,
    selectEdge,
    deleteSelection,
    clearAll,
    beginOrCompleteConnection,
    addWireDraftCorner,
    updateWireDraftCursor,
    beginReconnect,
    cancelDrafts,
  };
}
