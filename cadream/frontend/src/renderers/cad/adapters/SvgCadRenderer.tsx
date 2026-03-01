import type { CadRendererProps } from "../types";

export default function SvgCadRenderer({ width, height, pos, scale, scene }: CadRendererProps) {
  return (
    <svg
      width={width}
      height={height}
      style={{
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
        overflow: "hidden",
      }}
    >
      <g transform={`translate(${pos.x} ${pos.y}) scale(${scale} ${-scale})`}>
        {scene.primitives.map((primitive, idx) => {
          if (primitive.type === "line") {
            return (
              <line
                key={`line-${idx}`}
                x1={primitive.points[0]}
                y1={primitive.points[1]}
                x2={primitive.points[2]}
                y2={primitive.points[3]}
                stroke={`#${primitive.stroke.toString(16).padStart(6, "0")}`}
                strokeWidth={primitive.strokeWidth / Math.max(scale, 0.0001)}
              />
            );
          }

          if (primitive.type === "polyline") {
            const points = primitive.points.map((point) => `${point[0]},${point[1]}`).join(" ");
            return (
              <polyline
                key={`polyline-${idx}`}
                points={points}
                fill="none"
                stroke={`#${primitive.stroke.toString(16).padStart(6, "0")}`}
                strokeWidth={primitive.strokeWidth / Math.max(scale, 0.0001)}
              />
            );
          }

          return (
            <g key={`text-${idx}`} transform={`scale(1,-1) translate(${primitive.x},${-primitive.y})`}>
              <text
                x={0}
                y={0}
                fill={`#${primitive.fill.toString(16).padStart(6, "0")}`}
                fontSize={primitive.fontSize / Math.max(scale, 0.0001)}
              >
                {primitive.text}
              </text>
            </g>
          );
        })}
      </g>
    </svg>
  );
}
