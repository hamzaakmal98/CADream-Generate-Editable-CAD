export type CadIrSchemaVersion = "cad-ir-v1";

export type CadUnits =
  | "unitless"
  | "millimeter"
  | "centimeter"
  | "meter"
  | "inch"
  | "foot"
  | "unknown";

export type CadIrLineweight = "bylayer" | "byblock" | number;

export type CadIrColor =
  | { mode: "bylayer" }
  | { mode: "byblock" }
  | { mode: "aci"; aci: number }
  | { mode: "rgb"; rgb: [number, number, number] };

export type CadIrLinetype = { mode: "bylayer" } | { mode: "byblock" } | { mode: "named"; name: string };

export type CadIrLayer = {
  id: string;
  name: string;
  visible: boolean;
  locked?: boolean;
  color?: CadIrColor;
  linetype?: CadIrLinetype;
  lineweight?: CadIrLineweight;
};

export type CadIrEntityBase = {
  id: string;
  type: "LINE" | "LWPOLYLINE" | "CIRCLE" | "ARC" | "TEXT" | "MTEXT" | "INSERT";
  layerId: string;
  handle?: string;
  sourceHandle?: string;
  color?: CadIrColor;
  linetype?: CadIrLinetype;
  lineweight?: CadIrLineweight;
  xdata?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
};

export type CadIrLineEntity = CadIrEntityBase & {
  type: "LINE";
  start: [number, number];
  end: [number, number];
};

export type CadIrPolylineVertex = {
  x: number;
  y: number;
  bulge?: number;
};

export type CadIrLwPolylineEntity = CadIrEntityBase & {
  type: "LWPOLYLINE";
  vertices: CadIrPolylineVertex[];
  closed: boolean;
};

export type CadIrCircleEntity = CadIrEntityBase & {
  type: "CIRCLE";
  center: [number, number];
  radius: number;
};

export type CadIrArcEntity = CadIrEntityBase & {
  type: "ARC";
  center: [number, number];
  radius: number;
  startAngleDeg: number;
  endAngleDeg: number;
};

export type CadIrTextEntity = CadIrEntityBase & {
  type: "TEXT" | "MTEXT";
  text: string;
  insertionPoint: [number, number];
  height: number;
  rotationDeg?: number;
  styleName?: string;
};

export type CadIrInsertAttrib = {
  tag: string;
  text: string;
};

export type CadIrInsertEntity = CadIrEntityBase & {
  type: "INSERT";
  blockName: string;
  insertionPoint: [number, number];
  rotationDeg: number;
  xScale: number;
  yScale: number;
  zScale?: number;
  rowCount?: number;
  colCount?: number;
  rowSpacing?: number;
  colSpacing?: number;
  attributes?: CadIrInsertAttrib[];
};

export type CadIrEntity =
  | CadIrLineEntity
  | CadIrLwPolylineEntity
  | CadIrCircleEntity
  | CadIrArcEntity
  | CadIrTextEntity
  | CadIrInsertEntity;

export type CadIrBlockDefinition = {
  name: string;
  basePoint?: [number, number];
  entityIds: string[];
  metadata?: Record<string, unknown>;
};

export type CadIrDrawing = {
  schemaVersion: CadIrSchemaVersion;
  coordinateSpace: "cad_world";
  units: CadUnits;
  sourceFileName: string | null;
  layers: CadIrLayer[];
  entitiesById: Record<string, CadIrEntity>;
  modelSpaceEntityIds: string[];
  blocksByName: Record<string, CadIrBlockDefinition>;
  extents?: {
    min: [number, number];
    max: [number, number];
  };
  sitePlan?: CadIrSitePlan;
  metadata?: Record<string, unknown>;
};

export type CadIrSitePlanBess = {
  placementId: number;
  label: string;
  position: { x: number; y: number };
  insert: {
    blockName: string | null;
    rotationDeg: number;
    xScale: number;
    yScale: number;
  };
};

export type CadIrSitePlanPoi = {
  position: { x: number; y: number };
};

export type CadIrSitePlanCable = {
  cableId: number;
  points: Array<{ x: number; y: number }>;
  topology: {
    fromBessId: number | null;
    toBessId: number | null;
    toPoi: boolean;
  };
};

export type CadIrSitePlan = {
  schemaVersion: "cad-ir-site-v1";
  coordinateSpace: "cad_world";
  entities: {
    bess: CadIrSitePlanBess[];
    poi: CadIrSitePlanPoi | null;
    cablePaths: CadIrSitePlanCable[];
  };
};
