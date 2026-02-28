import type {
  BessPlacement,
  CablePath,
  PointOfInterconnection,
  RenderDoc,
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
