import type { ComponentType } from "react";

export type CadPrimitive =
  | {
      type: "line";
      points: [number, number, number, number];
      stroke: number;
      strokeWidth: number;
    }
  | {
      type: "polyline";
      points: number[][];
      stroke: number;
      strokeWidth: number;
      closed: boolean;
    }
  | {
      type: "text";
      text: string;
      x: number;
      y: number;
      fontSize: number;
      fill: number;
    };

export type CadScene = {
  primitives: CadPrimitive[];
};

export type CadRendererProps = {
  width: number;
  height: number;
  pos: { x: number; y: number };
  scale: number;
  scene: CadScene;
};

export type CadRendererAdapter = {
  id: "svg" | "pixi";
  Component: ComponentType<CadRendererProps>;
};
