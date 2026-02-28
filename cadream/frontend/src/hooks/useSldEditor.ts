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
  if (fromRole === "out" && toRole === "in") return true;
  if (fromRole === "in" && toRole === "out") return true;
  return false;
}

function rerouteEdges(edges: SldEdge[], nodes: SldNode[]): SldEdge[] {
  return edges.map((edge) => ({
    ...edge,
    points: buildOrthogonalEdgePoints(edge, nodes),
  }));
}

export function useSldEditor() {
  const [session, setSession] = useState<SldSessionState>(defaultSldSession);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [wireDraft, setWireDraft] = useState<SldWireDraft | null>(null);
  const [reconnectDraft, setReconnectDraft] = useState<SldReconnectDraft | null>(null);

  const issues = useMemo(() => validateSldSession(session), [session]);

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
    setSession(next);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setWireDraft(null);
    setReconnectDraft(null);
  }

  function absoluteTerminalPoint(node: SldNode, terminalId: string): number[] | null {
    const terminal = node.terminals.find((item) => item.id === terminalId);
    if (!terminal) return null;
    return [node.x + terminal.x, node.y + terminal.y];
  }

  function addNode(symbolType: SldSymbolType, x: number, y: number) {
    const symbol = getSldSymbolDefinition(symbolType);
    if (!symbol) return;

    setSession((prev) => {
      const nextCounter = computeNextCounter(prev.nodes.map((node) => node.id), "node");
      const nodeId = makeDeterministicId("node", nextCounter);

      const node: SldNode = {
        id: nodeId,
        symbol_type: symbol.type,
        label: `${symbol.label} ${nextCounter}`,
        x,
        y,
        rotation_deg: 0,
        terminals: symbol.terminals.map((terminal) => ({
          id: terminal.id,
          x: terminal.x,
          y: terminal.y,
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
    setSession((prev) => {
      const nodes = prev.nodes.map((node) => (node.id === nodeId ? { ...node, x, y } : node));
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
      setSession((prev) => {
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
      setSession((prev) => ({
        ...prev,
        edges: prev.edges.filter((edge) => edge.id !== selectedEdgeId),
      }));
      setSelectedEdgeId(null);
    }
  }

  function clearAll() {
    loadSession(defaultSldSession());
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
      setSession((prev) => {
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

    if (
      !canConnect(
        { node: fromNode, terminalId: wireDraft.fromTerminalId },
        { node: toNode, terminalId }
      )
    ) {
      setWireDraft(null);
      return;
    }

    const endPoint = absoluteTerminalPoint(toNode, terminalId);
    if (!endPoint) {
      setWireDraft(null);
      return;
    }

    setSession((prev) => {
      const nextCounter = computeNextCounter(prev.edges.map((edge) => edge.id), "edge");
      const edgeId = makeDeterministicId("edge", nextCounter);

      const committed = wireDraft.points.length > 0 ? wireDraft.points : [endPoint];
      const last = committed[committed.length - 1] ?? endPoint;
      const tail = orthogonalLeg(last, endPoint);
      const routedPoints = collapseDuplicatePoints([...committed, ...tail]);

      const nextEdge: SldEdge = {
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
    setToolMode,
    loadSession,
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
