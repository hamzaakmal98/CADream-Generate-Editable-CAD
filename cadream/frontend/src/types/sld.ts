import type { SldEdge, SldNode, SldSessionState, SldTerminal } from "./cad";

export type SldSymbolType =
  | "utility-grid"
  | "utility-meter"
  | "main-disconnect"
  | "main-distribution-panel"
  | "eqore-computing-unit"
  | "battery-system-electrical-disconnect"
  | "battery-storage-system-breaker"
  | "inverter"
  | "isolation-transformer"
  | "transformer"
  | "subpanel"
  | "bess"
  | "load"
  | "current-sensor-input";

export type SldTerminalTemplate = {
  id: string;
  x: number;
  y: number;
  role: SldTerminal["role"];
  required: boolean;
};

export type SldSymbolDefinition = {
  type: SldSymbolType;
  label: string;
  width: number;
  height: number;
  cad_block_name: string;
  cad_layer: string;
  terminals: SldTerminalTemplate[];
};

export type SldPaletteItem = {
  type: SldSymbolType | "wire";
  label: string;
  kind: "node" | "wire";
};

export type SldValidationSeverity = "error" | "warning";

export type SldValidationIssueCode =
  | "DANGLING_EDGE_ENDPOINT"
  | "INVALID_EDGE_ENDPOINT"
  | "MISSING_REQUIRED_TERMINAL_CONNECTION";

export type SldValidationIssue = {
  code: SldValidationIssueCode;
  severity: SldValidationSeverity;
  message: string;
  nodeId?: string;
  edgeId?: string;
};

export type SldConnectionDraft = {
  fromNodeId: string;
  fromTerminalId: string;
};

export type SldReconnectDraft = {
  edgeId: string;
  endpoint: "from" | "to";
};

export type SldWireDraft = {
  fromNodeId: string;
  fromTerminalId: string;
  points: number[][];
  cursor: number[] | null;
};

export type SldViewModel = {
  session: SldSessionState;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  wireDraft: SldWireDraft | null;
  reconnectDraft: SldReconnectDraft | null;
  issues: SldValidationIssue[];
};

export type SldGraphState = Pick<SldSessionState, "nodes" | "edges">;

export function isSldNode(value: unknown): value is SldNode {
  return Boolean(value) && typeof value === "object" && (value as Partial<SldNode>).id !== undefined;
}

export function isSldEdge(value: unknown): value is SldEdge {
  return Boolean(value) && typeof value === "object" && (value as Partial<SldEdge>).id !== undefined;
}
