import type { SldSymbolType } from "../../types/sld";

type SldSymbolGlyphProps = {
  type: SldSymbolType;
  width: number;
  height: number;
};

const STROKE = "#111";
const STROKE_WIDTH = 1.6;

function RectLabel({ text, x, y, width, height }: { text: string; x: number; y: number; width: number; height: number }) {
  return (
    <>
      <rect x={x} y={y} width={width} height={height} fill="white" stroke={STROKE} strokeWidth={STROKE_WIDTH} />
      <text x={x + width / 2} y={y + height / 2 + 4} textAnchor="middle" fontSize="10" fill={STROKE}>
        {text}
      </text>
    </>
  );
}

export default function SldSymbolGlyph({ type, width, height }: SldSymbolGlyphProps) {
  const w = width;
  const h = height;

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
      {type === "utility-grid" && (
        <>
          <circle cx={w / 2} cy={h / 2} r={Math.min(w, h) * 0.32} fill="white" stroke={STROKE} strokeWidth={STROKE_WIDTH} />
          <text x={w / 2} y={h / 2 - 2} textAnchor="middle" fontSize="10" fill={STROKE}>Utility</text>
          <text x={w / 2} y={h / 2 + 10} textAnchor="middle" fontSize="10" fill={STROKE}>Grid</text>
        </>
      )}

      {type === "utility-meter" && (
        <RectLabel text="Utility Meter" x={6} y={10} width={w - 12} height={h - 20} />
      )}

      {type === "main-disconnect" && <RectLabel text="Main Disconnect" x={6} y={10} width={w - 12} height={h - 20} />}

      {type === "main-distribution-panel" && <RectLabel text="Main Distribution Panel" x={4} y={10} width={w - 8} height={h - 20} />}

      {type === "eqore-computing-unit" && (
        <>
          <RectLabel text="EQORE" x={6} y={8} width={w - 12} height={h - 16} />
          <text x={w / 2} y={h / 2 + 14} textAnchor="middle" fontSize="10" fill={STROKE}>Computing Unit</text>
        </>
      )}

      {type === "battery-system-electrical-disconnect" && (
        <RectLabel text="Battery System Electrical Disconnect" x={4} y={8} width={w - 8} height={h - 16} />
      )}

      {type === "battery-storage-system-breaker" && (
        <>
          <RectLabel text="Battery Storage" x={8} y={8} width={w - 16} height={h - 16} />
          <text x={w / 2} y={h / 2 + 14} textAnchor="middle" fontSize="10" fill={STROKE}>System Breaker</text>
        </>
      )}

      {type === "inverter" && (
        <>
          <rect x={8} y={8} width={w - 16} height={h - 16} fill="white" stroke={STROKE} strokeWidth={STROKE_WIDTH} />
          <line x1={12} y1={h - 16} x2={w - 12} y2={16} stroke={STROKE} strokeWidth={STROKE_WIDTH} />
          <line x1={12} y1={h - 20} x2={w - 20} y2={h - 20} stroke={STROKE} strokeWidth={STROKE_WIDTH} />
          <text x={w / 2} y={h / 2 + 4} textAnchor="middle" fontSize="10" fill={STROKE}>Inverter</text>
        </>
      )}

      {type === "isolation-transformer" && (
        <>
          <rect x={6} y={8} width={w - 12} height={h - 16} fill="white" stroke={STROKE} strokeWidth={STROKE_WIDTH} />
          <circle cx={w * 0.42} cy={h * 0.5} r={h * 0.16} fill="none" stroke={STROKE} strokeWidth={STROKE_WIDTH} />
          <circle cx={w * 0.58} cy={h * 0.5} r={h * 0.16} fill="none" stroke={STROKE} strokeWidth={STROKE_WIDTH} />
        </>
      )}

      {type === "transformer" && (
        <>
          <rect x={6} y={8} width={w - 12} height={h - 16} fill="white" stroke={STROKE} strokeWidth={STROKE_WIDTH} />
          <text x={w / 2} y={h / 2 + 4} textAnchor="middle" fontSize="10" fill={STROKE}>Transformer</text>
        </>
      )}

      {type === "subpanel" && <RectLabel text="208/120V Subpanel" x={6} y={8} width={w - 12} height={h - 16} />}

      {type === "bess" && (
        <>
          <rect x={8} y={8} width={w - 16} height={h - 16} fill="white" stroke={STROKE} strokeWidth={STROKE_WIDTH} />
          <text x={w / 2} y={h / 2 + 4} textAnchor="middle" fontSize="11" fill={STROKE}>BESS</text>
        </>
      )}

      {type === "load" && (
        <>
          <circle cx={w / 2} cy={h / 2} r={Math.min(w, h) * 0.32} fill="white" stroke={STROKE} strokeWidth={STROKE_WIDTH} />
          <text x={w / 2} y={h / 2 + 4} textAnchor="middle" fontSize="11" fill={STROKE}>Load</text>
        </>
      )}

      {type === "current-sensor-input" && (
        <>
          <line x1={8} y1={h / 2} x2={w - 8} y2={h / 2} stroke={STROKE} strokeWidth={STROKE_WIDTH} />
          <ellipse cx={w / 2} cy={h / 2} rx={16} ry={6} fill="white" stroke={STROKE} strokeWidth={STROKE_WIDTH} />
          <text x={w / 2} y={h / 2 - 10} textAnchor="middle" fontSize="9" fill={STROKE}>Current Sensor</text>
        </>
      )}
    </svg>
  );
}
