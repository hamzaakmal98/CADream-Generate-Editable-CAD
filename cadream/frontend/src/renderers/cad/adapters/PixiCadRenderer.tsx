import { useEffect, useRef, useState } from "react";
import { Application, Container, Graphics, Text, TextStyle } from "pixi.js";
import type { CadRendererProps } from "../types";
import SvgCadRenderer from "./SvgCadRenderer";

export default function PixiCadRenderer({ width, height, pos, scale, scene }: CadRendererProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const appRef = useRef<Application | null>(null);
  const rootRef = useRef<Container | null>(null);
  const [ready, setReady] = useState(false);
  const [initFailed, setInitFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function setup() {
      if (!hostRef.current || appRef.current) return;

      try {
        setInitFailed(false);
        const app = new Application();
        await app.init({
          width,
          height,
          backgroundAlpha: 0,
          antialias: true,
          autoDensity: true,
          resolution: window.devicePixelRatio || 1,
        });

        if (cancelled) {
          app.destroy();
          return;
        }

        hostRef.current.appendChild(app.canvas);
        const root = new Container();
        app.stage.addChild(root);

        appRef.current = app;
        rootRef.current = root;
        setReady(true);
      } catch {
        setReady(false);
        setInitFailed(true);
      }
    }

    setup();

    return () => {
      cancelled = true;
      setReady(false);
      if (appRef.current) {
        appRef.current.destroy();
      }
      appRef.current = null;
      rootRef.current = null;
    };
  }, [width, height]);

  useEffect(() => {
    if (!appRef.current) return;
    appRef.current.renderer.resize(width, height);
  }, [width, height]);

  useEffect(() => {
    if (!ready) return;
    const root = rootRef.current;
    if (!root) return;

    root.removeChildren();

    const graphics = new Graphics();

    for (const primitive of scene.primitives) {
      if (primitive.type === "line") {
        graphics.moveTo(primitive.points[0], primitive.points[1]);
        graphics.lineTo(primitive.points[2], primitive.points[3]);
        graphics.stroke({
          width: primitive.strokeWidth / Math.max(scale, 0.0001),
          color: primitive.stroke,
          cap: "round",
          join: "round",
          miterLimit: 2,
        });
        continue;
      }

      if (primitive.type === "polyline") {
        if (primitive.points.length > 0) {
          graphics.moveTo(primitive.points[0][0], primitive.points[0][1]);
          for (let idx = 1; idx < primitive.points.length; idx += 1) {
            graphics.lineTo(primitive.points[idx][0], primitive.points[idx][1]);
          }
          if (primitive.closed && primitive.points.length > 1) {
            graphics.lineTo(primitive.points[0][0], primitive.points[0][1]);
          }
          graphics.stroke({
            width: primitive.strokeWidth / Math.max(scale, 0.0001),
            color: primitive.stroke,
            cap: "round",
            join: "round",
            miterLimit: 2,
          });
        }
        continue;
      }

      const text = new Text({
        text: primitive.text,
        style: new TextStyle({
          fill: primitive.fill,
          fontSize: primitive.fontSize / Math.max(scale, 0.0001),
        }),
      });
      text.x = primitive.x;
      text.y = primitive.y;
      text.scale.y = -1;
      root.addChild(text);
    }

    root.addChild(graphics);
    root.position.set(pos.x, pos.y);
    root.scale.set(scale, -scale);
  }, [ready, scene, pos.x, pos.y, scale]);

  const useSvgFallback = !ready || initFailed;

  if (useSvgFallback) {
    return <SvgCadRenderer width={width} height={height} pos={pos} scale={scale} scene={scene} />;
  }

  return (
    <div
      ref={hostRef}
      style={{
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
      }}
    />
  );
}
