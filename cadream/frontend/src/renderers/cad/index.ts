import type { CadRendererAdapter } from "./types";
import PixiCadRenderer from "./adapters/PixiCadRenderer";
import SvgCadRenderer from "./adapters/SvgCadRenderer";

export const SVG_CAD_RENDERER: CadRendererAdapter = {
  id: "svg",
  Component: SvgCadRenderer,
};

export const PIXI_CAD_RENDERER: CadRendererAdapter = {
  id: "pixi",
  Component: PixiCadRenderer,
};

export const CAD_RENDERERS: Record<CadRendererAdapter["id"], CadRendererAdapter> = {
  svg: SVG_CAD_RENDERER,
  pixi: PIXI_CAD_RENDERER,
};
