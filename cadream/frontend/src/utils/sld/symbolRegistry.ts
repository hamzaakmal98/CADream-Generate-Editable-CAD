import type { SldPaletteItem, SldSymbolDefinition, SldSymbolType } from "../../types/sld";

const SYMBOLS: SldSymbolDefinition[] = [
  {
    type: "utility-grid",
    label: "Utility Grid",
    width: 96,
    height: 56,
    cad_block_name: "SLD_UTILITY_GRID",
    cad_layer: "SLD-EQUIP",
    terminals: [{ id: "out", x: 96, y: 28, role: "out", required: true }],
  },
  {
    type: "utility-meter",
    label: "Utility Meter",
    width: 96,
    height: 56,
    cad_block_name: "SLD_UTILITY_METER",
    cad_layer: "SLD-EQUIP",
    terminals: [
      { id: "in", x: 0, y: 28, role: "in", required: true },
      { id: "out", x: 96, y: 28, role: "out", required: true },
    ],
  },
  {
    type: "main-disconnect",
    label: "Main Disconnect",
    width: 130,
    height: 64,
    cad_block_name: "SLD_MAIN_DISCONNECT",
    cad_layer: "SLD-EQUIP",
    terminals: [
      { id: "in", x: 0, y: 32, role: "in", required: true },
      { id: "out", x: 130, y: 32, role: "out", required: true },
    ],
  },
  {
    type: "main-distribution-panel",
    label: "Main Distribution Panel",
    width: 150,
    height: 64,
    cad_block_name: "SLD_MAIN_DISTRIBUTION_PANEL",
    cad_layer: "SLD-EQUIP",
    terminals: [
      { id: "in", x: 0, y: 26, role: "in", required: true },
      { id: "out", x: 150, y: 26, role: "out", required: true },
    ],
  },
  {
    type: "eqore-computing-unit",
    label: "EQORE Computing Unit",
    width: 160,
    height: 64,
    cad_block_name: "SLD_EQORE_COMPUTING_UNIT",
    cad_layer: "SLD-EQUIP",
    terminals: [
      { id: "in", x: 0, y: 24, role: "in", required: true },
      { id: "out", x: 160, y: 24, role: "out", required: true },
      { id: "com", x: 80, y: 64, role: "line", required: false },
    ],
  },
  {
    type: "battery-system-electrical-disconnect",
    label: "Battery System Electrical Disconnect",
    width: 190,
    height: 64,
    cad_block_name: "SLD_BATTERY_SYSTEM_ELECTRICAL_DISCONNECT",
    cad_layer: "SLD-EQUIP",
    terminals: [
      { id: "in", x: 0, y: 32, role: "in", required: true },
      { id: "out", x: 190, y: 32, role: "out", required: true },
    ],
  },
  {
    type: "battery-storage-system-breaker",
    label: "Battery Storage System Breaker",
    width: 180,
    height: 64,
    cad_block_name: "SLD_BATTERY_STORAGE_SYSTEM_BREAKER",
    cad_layer: "SLD-EQUIP",
    terminals: [
      { id: "in", x: 0, y: 32, role: "in", required: true },
      { id: "out", x: 180, y: 32, role: "out", required: true },
    ],
  },
  {
    type: "inverter",
    label: "Inverter",
    width: 108,
    height: 60,
    cad_block_name: "SLD_INVERTER",
    cad_layer: "SLD-EQUIP",
    terminals: [
      { id: "in", x: 0, y: 30, role: "in", required: true },
      { id: "out", x: 108, y: 30, role: "out", required: true },
      { id: "dc", x: 54, y: 60, role: "line", required: false },
    ],
  },
  {
    type: "isolation-transformer",
    label: "Isolation Transformer",
    width: 146,
    height: 60,
    cad_block_name: "SLD_ISOLATION_TRANSFORMER",
    cad_layer: "SLD-EQUIP",
    terminals: [
      { id: "in", x: 0, y: 30, role: "in", required: true },
      { id: "out", x: 146, y: 30, role: "out", required: true },
    ],
  },
  {
    type: "transformer",
    label: "Transformer",
    width: 110,
    height: 60,
    cad_block_name: "SLD_TRANSFORMER",
    cad_layer: "SLD-EQUIP",
    terminals: [
      { id: "in", x: 0, y: 30, role: "in", required: true },
      { id: "out", x: 110, y: 30, role: "out", required: true },
    ],
  },
  {
    type: "subpanel",
    label: "208/120V Subpanel",
    width: 130,
    height: 60,
    cad_block_name: "SLD_SUBPANEL_208_120V",
    cad_layer: "SLD-EQUIP",
    terminals: [
      { id: "in", x: 0, y: 30, role: "in", required: true },
      { id: "out", x: 130, y: 30, role: "out", required: false },
    ],
  },
  {
    type: "bess",
    label: "BESS",
    width: 110,
    height: 64,
    cad_block_name: "SLD_BESS_GOTION_EDGE_760",
    cad_layer: "SLD-EQUIP",
    terminals: [
      { id: "out", x: 110, y: 32, role: "out", required: true },
      { id: "com", x: 55, y: 64, role: "line", required: false },
    ],
  },
  {
    type: "load",
    label: "Load",
    width: 92,
    height: 52,
    cad_block_name: "SLD_LOAD",
    cad_layer: "SLD-EQUIP",
    terminals: [{ id: "in", x: 0, y: 26, role: "in", required: true }],
  },
  {
    type: "current-sensor-input",
    label: "Current Sensor Input",
    width: 150,
    height: 52,
    cad_block_name: "SLD_CURRENT_SENSOR_INPUT",
    cad_layer: "SLD-EQUIP",
    terminals: [
      { id: "in", x: 0, y: 26, role: "line", required: false },
      { id: "out", x: 150, y: 26, role: "line", required: false },
    ],
  },
];

export const SLD_SYMBOL_REGISTRY: Record<SldSymbolType, SldSymbolDefinition> = {
  "utility-grid": SYMBOLS[0],
  "utility-meter": SYMBOLS[1],
  "main-disconnect": SYMBOLS[2],
  "main-distribution-panel": SYMBOLS[3],
  "eqore-computing-unit": SYMBOLS[4],
  "battery-system-electrical-disconnect": SYMBOLS[5],
  "battery-storage-system-breaker": SYMBOLS[6],
  inverter: SYMBOLS[7],
  "isolation-transformer": SYMBOLS[8],
  transformer: SYMBOLS[9],
  subpanel: SYMBOLS[10],
  bess: SYMBOLS[11],
  load: SYMBOLS[12],
  "current-sensor-input": SYMBOLS[13],
};

export const SLD_SYMBOL_PALETTE = SYMBOLS;

export const SLD_PALETTE_ITEMS: SldPaletteItem[] = [
  ...SYMBOLS.map((symbol) => ({
    type: symbol.type,
    label: symbol.label,
    kind: "node" as const,
  })),
  {
    type: "wire",
    label: "Wire",
    kind: "wire",
  },
];

export function getSldSymbolDefinition(type: string): SldSymbolDefinition | null {
  if (type in SLD_SYMBOL_REGISTRY) return SLD_SYMBOL_REGISTRY[type as SldSymbolType];
  return null;
}
