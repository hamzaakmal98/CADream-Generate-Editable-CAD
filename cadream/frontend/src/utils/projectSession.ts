import type {
  BessPlacement,
  CablePath,
  PointOfInterconnection,
  ProjectSessionV1,
  ProjectSessionV2,
  RenderDoc,
  SitePlanSessionState,
  ToolMode,
} from "../types/cad";

export function pickSuggestedBessBlockName(doc: RenderDoc | null) {
  const blockNames = Object.keys(doc?.blocks ?? {});
  if (blockNames.length === 0) return null;

  const byKeyword = blockNames.find((name) => /bess|battery|enclosure|container/i.test(name));
  if (byKeyword) return byKeyword;

  const nonAnonymous = blockNames.find((name) => !name.startsWith("*"));
  return nonAnonymous ?? blockNames[0] ?? null;
}

export function isToolMode(value: unknown): value is ToolMode {
  return value === "pan" || value === "place-bess" || value === "place-poi" || value === "draw-cable";
}

export function normalizeBessPlacements(items: unknown): BessPlacement[] {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => {
      const next = item as Partial<BessPlacement>;
      if (
        typeof next?.id !== "number" ||
        typeof next?.x !== "number" ||
        typeof next?.y !== "number"
      ) {
        return null;
      }
      const label = typeof next.label === "string" ? next.label : `BESS-${next.id}`;
      return {
        id: next.id,
        label,
        x: next.x,
        y: next.y,
        block_name: typeof next.block_name === "string" ? next.block_name : null,
        rotation: typeof next.rotation === "number" ? next.rotation : 0,
        xscale: typeof next.xscale === "number" ? next.xscale : 1,
        yscale: typeof next.yscale === "number" ? next.yscale : 1,
      };
    })
    .filter((item): item is BessPlacement => item !== null);
}

export function normalizePoi(value: unknown): PointOfInterconnection | null {
  if (!value || typeof value !== "object") return null;
  const next = value as Partial<PointOfInterconnection>;
  if (typeof next.x !== "number" || typeof next.y !== "number") return null;
  return { x: next.x, y: next.y };
}

export function normalizeCablePaths(items: unknown): CablePath[] {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => {
      const next = item as Partial<CablePath>;
      if (typeof next?.id !== "number" || !Array.isArray(next?.points)) return null;

      const points = next.points
        .map((point) =>
          Array.isArray(point) &&
          point.length >= 2 &&
          typeof point[0] === "number" &&
          typeof point[1] === "number"
            ? [point[0], point[1]]
            : null
        )
        .filter((point): point is number[] => point !== null);

      if (points.length < 2) return null;

      return {
        id: next.id,
        points,
        from_bess_id: typeof next.from_bess_id === "number" ? next.from_bess_id : null,
        to_bess_id: typeof next.to_bess_id === "number" ? next.to_bess_id : null,
        to_poi: Boolean(next.to_poi),
      };
    })
    .filter((item): item is CablePath => item !== null);
}

type SitePlanDefaults = {
  scale: number;
  pos: { x: number; y: number };
};

type SitePlanSnapshotInput = {
  sourceDxfName: string | null;
  bessPlacements: BessPlacement[];
  poi: PointOfInterconnection | null;
  cablePaths: CablePath[];
  toolMode: ToolMode;
  bessSizeFactor: number;
  hiddenLayers: Record<string, boolean>;
  scale: number;
  pos: { x: number; y: number };
};

export type LoadedSitePlanSession = {
  sourceDxfName: string | null;
  bessPlacements: BessPlacement[];
  poi: PointOfInterconnection | null;
  cablePaths: CablePath[];
  toolMode: ToolMode;
  bessSizeFactor: number;
  hiddenLayers: Record<string, boolean>;
  scale: number;
  pos: { x: number; y: number };
};

function normalizeSitePlanSession(
  sitePlan: Partial<SitePlanSessionState> | undefined,
  defaults: SitePlanDefaults
): LoadedSitePlanSession {
  const nextBess = normalizeBessPlacements(sitePlan?.entities?.bess);
  const nextPoi = normalizePoi(sitePlan?.entities?.poi);
  const nextCables = normalizeCablePaths(sitePlan?.entities?.cable_paths);

  const nextToolMode = isToolMode(sitePlan?.tool_settings?.tool_mode)
    ? sitePlan.tool_settings.tool_mode
    : "pan";

  const nextBessSize =
    typeof sitePlan?.tool_settings?.bess_size_factor === "number"
      ? sitePlan.tool_settings.bess_size_factor
      : 1;

  const nextHiddenLayers =
    sitePlan?.tool_settings?.hidden_layers && typeof sitePlan.tool_settings.hidden_layers === "object"
      ? sitePlan.tool_settings.hidden_layers
      : {};

  const nextScale =
    typeof sitePlan?.tool_settings?.viewport?.scale === "number"
      ? sitePlan.tool_settings.viewport.scale
      : defaults.scale;

  const nextPos =
    typeof sitePlan?.tool_settings?.viewport?.pos?.x === "number" &&
    typeof sitePlan?.tool_settings?.viewport?.pos?.y === "number"
      ? sitePlan.tool_settings.viewport.pos
      : defaults.pos;

  const sourceDxfName =
    typeof sitePlan?.source_dxf_filename === "string" || sitePlan?.source_dxf_filename === null
      ? sitePlan.source_dxf_filename
      : null;

  return {
    sourceDxfName,
    bessPlacements: nextBess,
    poi: nextPoi,
    cablePaths: nextCables,
    toolMode: nextToolMode,
    bessSizeFactor: nextBessSize,
    hiddenLayers: nextHiddenLayers,
    scale: nextScale,
    pos: nextPos,
  };
}

export function createProjectSessionV2(input: SitePlanSnapshotInput): ProjectSessionV2 {
  return {
    schema_version: "cadream-project-v2",
    interfaces: {
      interactive_site_plan: {
        source_dxf_filename: input.sourceDxfName,
        entities: {
          bess: input.bessPlacements,
          poi: input.poi,
          cable_paths: input.cablePaths,
        },
        tool_settings: {
          tool_mode: input.toolMode,
          bess_size_factor: input.bessSizeFactor,
          hidden_layers: input.hiddenLayers,
          viewport: {
            scale: input.scale,
            pos: input.pos,
          },
        },
      },
      single_line_diagram_builder: {
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
      },
    },
  };
}

export function loadSitePlanFromAnyProjectSession(
  raw: unknown,
  defaults: SitePlanDefaults
): LoadedSitePlanSession | null {
  if (!raw || typeof raw !== "object") return null;

  const parsed = raw as { schema_version?: unknown };

  if (parsed.schema_version === "cadream-project-v2") {
    const v2 = raw as Partial<ProjectSessionV2>;
    return normalizeSitePlanSession(v2.interfaces?.interactive_site_plan, defaults);
  }

  if (parsed.schema_version === "cadream-project-v1") {
    const v1 = raw as Partial<ProjectSessionV1>;
    const legacySitePlan: Partial<SitePlanSessionState> = {
      source_dxf_filename:
        typeof v1.source_dxf_filename === "string" || v1.source_dxf_filename === null
          ? v1.source_dxf_filename
          : null,
      entities: {
        bess: v1.entities?.bess ?? [],
        poi: v1.entities?.poi ?? null,
        cable_paths: v1.entities?.cable_paths ?? [],
      },
      tool_settings: {
        tool_mode: v1.tool_settings?.tool_mode ?? "pan",
        bess_size_factor: v1.tool_settings?.bess_size_factor ?? 1,
        hidden_layers: v1.tool_settings?.hidden_layers ?? {},
        viewport: {
          scale: v1.tool_settings?.viewport?.scale ?? defaults.scale,
          pos: v1.tool_settings?.viewport?.pos ?? defaults.pos,
        },
      },
    };

    return normalizeSitePlanSession(legacySitePlan, defaults);
  }

  return null;
}
