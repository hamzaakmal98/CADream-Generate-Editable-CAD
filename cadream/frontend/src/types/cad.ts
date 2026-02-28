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

export type ToolMode = "pan" | "place-bess";

export type BessPlacement = {
  id: number;
  label: string;
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
};

export type SitePlacementExport = {
  schema_version: string;
  source_dxf_filename: string | null;
  coordinate_space: "cad_world";
  entities: {
    bess: BessPlacementExport[];
  };
};
