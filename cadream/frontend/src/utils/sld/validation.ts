import type { SldEdge, SldNode, SldSessionState } from "../../types/cad";
import type { SldValidationIssue } from "../../types/sld";
import { getSldSymbolDefinition } from "./symbolRegistry";

function nearlyEqual(a: number, b: number, eps = 0.5) {
  return Math.abs(a - b) <= eps;
}

export function orthogonalLeg(start: number[], end: number[]): number[][] {
  if (nearlyEqual(start[0], end[0]) || nearlyEqual(start[1], end[1])) {
    return [end];
  }

  const dx = Math.abs(end[0] - start[0]);
  const dy = Math.abs(end[1] - start[1]);

  if (dx >= dy) {
    return [
      [end[0], start[1]],
      [end[0], end[1]],
    ];
  }

  return [
    [start[0], end[1]],
    [end[0], end[1]],
  ];
}

export function collapseDuplicatePoints(points: number[][]): number[][] {
  const next: number[][] = [];
  for (const point of points) {
    const prev = next[next.length - 1];
    if (!prev || !nearlyEqual(prev[0], point[0]) || !nearlyEqual(prev[1], point[1])) {
      next.push(point);
    }
  }
  return next;
}

function getTerminal(node: SldNode, terminalId: string) {
  return node.terminals.find((terminal) => terminal.id === terminalId) ?? null;
}

function endpointExists(nodesById: Map<string, SldNode>, nodeId: string, terminalId: string) {
  const node = nodesById.get(nodeId);
  if (!node) return false;
  return getTerminal(node, terminalId) !== null;
}

function isRoleCompatible(fromRole: "line" | "in" | "out", toRole: "line" | "in" | "out") {
  if (fromRole === "line" || toRole === "line") return true;
  if (fromRole === "out" && toRole === "in") return true;
  if (fromRole === "in" && toRole === "out") return true;
  return false;
}

export function validateSldSession(session: SldSessionState): SldValidationIssue[] {
  const issues: SldValidationIssue[] = [];
  const nodesById = new Map<string, SldNode>(session.nodes.map((node) => [node.id, node]));

  for (const edge of session.edges) {
    const hasFrom = endpointExists(nodesById, edge.from_node_id, edge.from_terminal_id);
    const hasTo = endpointExists(nodesById, edge.to_node_id, edge.to_terminal_id);

    if (!hasFrom || !hasTo) {
      issues.push({
        code: "DANGLING_EDGE_ENDPOINT",
        severity: "error",
        edgeId: edge.id,
        message: `Edge ${edge.id} references a node or terminal that no longer exists.`,
      });
      continue;
    }

    const fromNode = nodesById.get(edge.from_node_id);
    const toNode = nodesById.get(edge.to_node_id);
    if (!fromNode || !toNode) continue;

    const fromTerminal = getTerminal(fromNode, edge.from_terminal_id);
    const toTerminal = getTerminal(toNode, edge.to_terminal_id);

    if (!fromTerminal || !toTerminal) continue;

    if (!isRoleCompatible(fromTerminal.role, toTerminal.role)) {
      issues.push({
        code: "INVALID_EDGE_ENDPOINT",
        severity: "error",
        edgeId: edge.id,
        message: `Edge ${edge.id} connects incompatible terminal roles (${fromTerminal.role} → ${toTerminal.role}).`,
      });
    }
  }

  for (const node of session.nodes) {
    const symbol = getSldSymbolDefinition(node.symbol_type);
    if (!symbol) continue;

    for (const terminalTemplate of symbol.terminals) {
      if (!terminalTemplate.required) continue;
      const hasConnection = session.edges.some(
        (edge) =>
          (edge.from_node_id === node.id && edge.from_terminal_id === terminalTemplate.id) ||
          (edge.to_node_id === node.id && edge.to_terminal_id === terminalTemplate.id)
      );

      if (!hasConnection) {
        issues.push({
          code: "MISSING_REQUIRED_TERMINAL_CONNECTION",
          severity: "warning",
          nodeId: node.id,
          message: `${node.label}: required terminal '${terminalTemplate.id}' is not connected.`,
        });
      }
    }
  }

  return issues;
}

export function buildStraightEdgePoints(
  edge: Pick<SldEdge, "from_node_id" | "from_terminal_id" | "to_node_id" | "to_terminal_id">,
  nodes: SldNode[]
): number[][] {
  const nodesById = new Map<string, SldNode>(nodes.map((node) => [node.id, node]));
  const fromNode = nodesById.get(edge.from_node_id);
  const toNode = nodesById.get(edge.to_node_id);
  if (!fromNode || !toNode) return [];

  const fromTerminal = fromNode.terminals.find((terminal) => terminal.id === edge.from_terminal_id);
  const toTerminal = toNode.terminals.find((terminal) => terminal.id === edge.to_terminal_id);
  if (!fromTerminal || !toTerminal) return [];

  return [
    [fromNode.x + fromTerminal.x, fromNode.y + fromTerminal.y],
    [toNode.x + toTerminal.x, toNode.y + toTerminal.y],
  ];
}

export function buildOrthogonalEdgePoints(
  edge: Pick<SldEdge, "from_node_id" | "from_terminal_id" | "to_node_id" | "to_terminal_id">,
  nodes: SldNode[]
): number[][] {
  const nodesById = new Map<string, SldNode>(nodes.map((node) => [node.id, node]));
  const fromNode = nodesById.get(edge.from_node_id);
  const toNode = nodesById.get(edge.to_node_id);
  if (!fromNode || !toNode) return [];

  const fromTerminal = fromNode.terminals.find((terminal) => terminal.id === edge.from_terminal_id);
  const toTerminal = toNode.terminals.find((terminal) => terminal.id === edge.to_terminal_id);
  if (!fromTerminal || !toTerminal) return [];

  const start: number[] = [fromNode.x + fromTerminal.x, fromNode.y + fromTerminal.y];
  const end: number[] = [toNode.x + toTerminal.x, toNode.y + toTerminal.y];

  return collapseDuplicatePoints([start, ...orthogonalLeg(start, end)]);
}
