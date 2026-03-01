import type { BessPlacement, CablePath, PointOfInterconnection, RenderDoc } from "./cad";

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

function layerIdFromIndex(index: number) {
  return `layer:${index}`;
}

function colorFromLayer(layerColor?: number): CadIrColor | undefined {
  if (typeof layerColor === "number") {
    return { mode: "aci", aci: layerColor };
  }
  return undefined;
}

function convertEntity(
  entity: RenderDoc["entities"][number],
  id: string,
  layerIdByName: Record<string, string>
): CadIrEntity {
  const layerId = layerIdByName[entity.layer] ?? "layer:0";

  switch (entity.type) {
    case "LINE":
      return {
        id,
        type: "LINE",
        layerId,
        start: [entity.p1[0], entity.p1[1]],
        end: [entity.p2[0], entity.p2[1]],
      };

    case "LWPOLYLINE":
      return {
        id,
        type: "LWPOLYLINE",
        layerId,
        vertices: entity.points.map((point) => ({ x: point[0], y: point[1], bulge: 0 })),
        closed: entity.closed,
      };

    case "CIRCLE":
      return {
        id,
        type: "CIRCLE",
        layerId,
        center: [entity.center[0], entity.center[1]],
        radius: entity.r,
      };

    case "ARC":
      return {
        id,
        type: "ARC",
        layerId,
        center: [entity.center[0], entity.center[1]],
        radius: entity.r,
        startAngleDeg: entity.start_angle,
        endAngleDeg: entity.end_angle,
      };

    case "TEXT":
    case "MTEXT":
      return {
        id,
        type: entity.type,
        layerId,
        text: entity.text,
        insertionPoint: [entity.pos[0], entity.pos[1]],
        height: entity.height,
      };

    case "INSERT":
      return {
        id,
        type: "INSERT",
        layerId,
        blockName: entity.name,
        insertionPoint: [entity.pos[0], entity.pos[1]],
        rotationDeg: entity.rotation,
        xScale: entity.xscale,
        yScale: entity.yscale,
      };
  }
}

export function buildCadIrFromRenderDoc(input: {
  doc: RenderDoc;
  sourceFileName: string | null;
  units?: CadUnits;
}): CadIrDrawing {
  const layerIdByName: Record<string, string> = {};

  const layers: CadIrLayer[] = input.doc.layers.map((layer, index) => {
    const id = layerIdFromIndex(index + 1);
    layerIdByName[layer.name] = id;

    return {
      id,
      name: layer.name,
    visible: true,
    color: colorFromLayer(layer.color),
    linetype: layer.linetype ? { mode: "named", name: layer.linetype } : { mode: "bylayer" },
    };
  });

  if (!layerIdByName["0"]) {
    const id = layerIdFromIndex(layers.length + 1);
    layers.push({
      id,
      name: "0",
      visible: true,
      linetype: { mode: "bylayer" },
    });
    layerIdByName["0"] = id;
  }

  const entitiesById: Record<string, CadIrEntity> = {};
  const modelSpaceEntityIds: string[] = [];

  input.doc.entities.forEach((entity, index) => {
    const id = `ms:${index + 1}`;
    const converted = convertEntity(entity, id, layerIdByName);
    entitiesById[id] = converted;
    modelSpaceEntityIds.push(id);
  });

  const blocksByName: Record<string, CadIrBlockDefinition> = {};

  Object.entries(input.doc.blocks ?? {}).forEach(([blockName, blockEntities]) => {
    const blockEntityIds: string[] = [];

    blockEntities.forEach((entity, blockIndex) => {
      const id = `blk:${blockName}:${blockIndex + 1}`;
      const converted = convertEntity(entity, id, layerIdByName);
      entitiesById[id] = converted;
      blockEntityIds.push(id);
    });

    blocksByName[blockName] = {
      name: blockName,
      entityIds: blockEntityIds,
    };
  });

  return {
    schemaVersion: "cad-ir-v1",
    coordinateSpace: "cad_world",
    units: input.units ?? "unknown",
    sourceFileName: input.sourceFileName,
    layers,
    entitiesById,
    modelSpaceEntityIds,
    blocksByName,
    extents: input.doc.bounds
      ? {
          min: [input.doc.bounds.min[0], input.doc.bounds.min[1]],
          max: [input.doc.bounds.max[0], input.doc.bounds.max[1]],
        }
      : undefined,
  };
}

export function attachSitePlanToCadIr(
  cadIr: CadIrDrawing,
  sitePlan: {
    bessPlacements: BessPlacement[];
    poi: PointOfInterconnection | null;
    cablePaths: CablePath[];
  }
): CadIrDrawing {
  return {
    ...cadIr,
    sitePlan: {
      schemaVersion: "cad-ir-site-v1",
      coordinateSpace: "cad_world",
      entities: {
        bess: sitePlan.bessPlacements.map((item) => ({
          placementId: item.id,
          label: item.label,
          position: { x: item.x, y: item.y },
          insert: {
            blockName: item.block_name,
            rotationDeg: item.rotation,
            xScale: item.xscale,
            yScale: item.yscale,
          },
        })),
        poi: sitePlan.poi ? { position: { x: sitePlan.poi.x, y: sitePlan.poi.y } } : null,
        cablePaths: sitePlan.cablePaths.map((path) => ({
          cableId: path.id,
          points: path.points.map((point) => ({ x: point[0], y: point[1] })),
          topology: {
            fromBessId: path.from_bess_id,
            toBessId: path.to_bess_id,
            toPoi: path.to_poi,
          },
        })),
      },
    },
  };
}
