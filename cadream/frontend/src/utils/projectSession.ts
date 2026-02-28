import type {
  BessPlacement,
  CablePath,
  PointOfInterconnection,
  ProjectSessionV1,
  ProjectSessionV2,
  RenderDoc,
  SldEdge,
  SldNode,
  SldSessionState,
  SldToolMode,
  SitePlanSessionState,
  SldTerminal,
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

type SldDefaults = {
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
  sldSession: SldSessionState;
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

export type LoadedProjectSession = {
  sitePlan: LoadedSitePlanSession;
  sldSession: SldSessionState;
};

function isSldToolMode(value: unknown): value is SldToolMode {
  return value === "select" || value === "pan" || value === "connect";
}

function normalizeSldTerminal(value: unknown): SldTerminal | null {
  if (!value || typeof value !== "object") return null;
  const next = value as Partial<SldTerminal>;
  if (typeof next.id !== "string") return null;
  if (typeof next.x !== "number" || typeof next.y !== "number") return null;
  if (next.role !== "line" && next.role !== "in" && next.role !== "out") return null;
  return {
    id: next.id,
    x: next.x,
    y: next.y,
    role: next.role,
  };
}

function normalizeSldNode(value: unknown): SldNode | null {
  if (!value || typeof value !== "object") return null;
  const next = value as Partial<SldNode>;
  if (typeof next.id !== "string") return null;
  if (typeof next.symbol_type !== "string" || typeof next.label !== "string") return null;
  if (typeof next.x !== "number" || typeof next.y !== "number") return null;

  const terminals = Array.isArray(next.terminals)
    ? next.terminals
        .map((terminal) => normalizeSldTerminal(terminal))
        .filter((terminal): terminal is SldTerminal => terminal !== null)
    : [];

  return {
    id: next.id,
    symbol_type: next.symbol_type,
    label: next.label,
    x: next.x,
    y: next.y,
    rotation_deg: typeof next.rotation_deg === "number" ? next.rotation_deg : 0,
    terminals,
    metadata: next.metadata,
  };
}

function normalizeSldEdge(value: unknown): SldEdge | null {
  if (!value || typeof value !== "object") return null;
  const next = value as Partial<SldEdge>;
  if (
    typeof next.id !== "string" ||
    typeof next.from_node_id !== "string" ||
    typeof next.from_terminal_id !== "string" ||
    typeof next.to_node_id !== "string" ||
    typeof next.to_terminal_id !== "string"
  ) {
    return null;
  }

  const points = Array.isArray(next.points)
    ? next.points
        .map((point) =>
          Array.isArray(point) && point.length >= 2 && typeof point[0] === "number" && typeof point[1] === "number"
            ? [point[0], point[1]]
            : null
        )
        .filter((point): point is number[] => point !== null)
    : [];

  return {
    id: next.id,
    from_node_id: next.from_node_id,
    from_terminal_id: next.from_terminal_id,
    to_node_id: next.to_node_id,
    to_terminal_id: next.to_terminal_id,
    points,
    metadata: next.metadata,
  };
}

export function createEmptySldSession(defaults?: SldDefaults): SldSessionState {
  return {
    schema_version: "sld-v1",
    nodes: [],
    edges: [],
    tool_settings: {
      tool_mode: "select",
      viewport: {
        scale: defaults?.scale ?? 1,
        pos: defaults?.pos ?? { x: 0, y: 0 },
      },
    },
  };
}

function normalizeSldSession(session: unknown, defaults: SldDefaults): SldSessionState {
  if (!session || typeof session !== "object") return createEmptySldSession(defaults);

  const next = session as Partial<SldSessionState>;

  const nodes = Array.isArray(next.nodes)
    ? next.nodes.map((node) => normalizeSldNode(node)).filter((node): node is SldNode => node !== null)
    : [];

  const edges = Array.isArray(next.edges)
    ? next.edges.map((edge) => normalizeSldEdge(edge)).filter((edge): edge is SldEdge => edge !== null)
    : [];

  const toolMode = isSldToolMode(next.tool_settings?.tool_mode) ? next.tool_settings.tool_mode : "select";

  const viewportScale =
    typeof next.tool_settings?.viewport?.scale === "number"
      ? next.tool_settings.viewport.scale
      : defaults.scale;

  const viewportPos =
    typeof next.tool_settings?.viewport?.pos?.x === "number" &&
    typeof next.tool_settings?.viewport?.pos?.y === "number"
      ? next.tool_settings.viewport.pos
      : defaults.pos;

  return {
    schema_version: "sld-v1",
    nodes,
    edges,
    tool_settings: {
      tool_mode: toolMode,
      viewport: {
        scale: viewportScale,
        pos: viewportPos,
      },
    },
  };
}

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
        ...input.sldSession,
      },
    },
  };
}

export function loadProjectFromAnySession(raw: unknown, defaults: SitePlanDefaults): LoadedProjectSession | null {
  if (!raw || typeof raw !== "object") return null;

  const parsed = raw as { schema_version?: unknown };

  if (parsed.schema_version === "cadream-project-v2") {
    const v2 = raw as Partial<ProjectSessionV2>;
    const sitePlan = normalizeSitePlanSession(v2.interfaces?.interactive_site_plan, defaults);
    const sldSession = normalizeSldSession(v2.interfaces?.single_line_diagram_builder, {
      scale: 1,
      pos: { x: 0, y: 0 },
    });
    return { sitePlan, sldSession };
  }

  if (parsed.schema_version === "cadream-project-v1") {
    const sitePlan = loadSitePlanFromAnyProjectSession(raw, defaults);
    if (!sitePlan) return null;
    return {
      sitePlan,
      sldSession: createEmptySldSession({ scale: 1, pos: { x: 0, y: 0 } }),
    };
  }

  return null;
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
