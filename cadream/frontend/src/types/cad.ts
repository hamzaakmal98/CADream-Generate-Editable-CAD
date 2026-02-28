export type RenderLayer = { name: string; color?: number; linetype?: string };

export type RenderEntity =
  | { type: "LINE"; layer: string; p1: number[]; p2: number[] }
  | { type: "LWPOLYLINE"; layer: string; points: number[][]; closed: boolean }
  | { type: "CIRCLE"; layer: string; center: number[]; r: number }
  | {
      type: "ARC";
      layer: string;
      center: number[];
      r: number;
      start_angle: number;
      end_angle: number;
    }
  | {
      type: "TEXT" | "MTEXT";
      layer: string;
      text: string;
      pos: number[];
      height: number;
    }
  | {
      type: "INSERT";
      layer: string;
      name: string;
      pos: number[];
      rotation: number;
      xscale: number;
      yscale: number;
    };

export type RenderDoc = {
  layers: RenderLayer[];
  entities: RenderEntity[];
  bounds: null | { min: number[]; max: number[] };
  blocks?: Record<string, RenderEntity[]>;
};

export type Affine2D = {
  a: number;
  b: number;
  c: number;
  d: number;
  tx: number;
  ty: number;
};

export type ToolMode = "pan" | "place-bess" | "place-poi" | "draw-cable";

export type BessPlacement = {
  id: number;
  label: string;
  x: number;
  y: number;
  block_name: string | null;
  rotation: number;
  xscale: number;
  yscale: number;
};

export type CablePath = {
  id: number;
  points: number[][];
  from_bess_id: number | null;
  to_bess_id: number | null;
  to_poi: boolean;
};

export type PointOfInterconnection = {
  x: number;
  y: number;
};

export type BessPlacementExport = {
  id: number;
  label: string;
  cad_position: {
    x: number;
    y: number;
  };
  cad_insert: {
    block_name: string | null;
    rotation: number;
    xscale: number;
    yscale: number;
  };
};

export type SitePlacementExport = {
  schema_version: string;
  source_dxf_filename: string | null;
  coordinate_space: "cad_world";
  entities: {
    bess: BessPlacementExport[];
    poi: PointOfInterconnection | null;
    cable_paths: CablePath[];
  };
};

export type ProjectSession = {
  schema_version: "cadream-project-v1";
  source_dxf_filename: string | null;
  entities: {
    bess: BessPlacement[];
    poi: PointOfInterconnection | null;
    cable_paths: CablePath[];
  };
  tool_settings: {
    tool_mode: ToolMode;
    bess_size_factor: number;
    hidden_layers: Record<string, boolean>;
    viewport: {
      scale: number;
      pos: { x: number; y: number };
    };
  };
};
