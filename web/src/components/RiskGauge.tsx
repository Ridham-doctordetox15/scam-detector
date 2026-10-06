"use client";

import * as m from "motion/react-m";
import { useI18n } from "@/i18n/I18nProvider";
import { fmt } from "@/lib/format";
import type { RiskLevel } from "@/lib/types";

const LEVELS: RiskLevel[] = ["low", "medium", "high"];
const CX = 100;
const CY = 100;
const R = 78;
const GAP_DEG = 4;

/** Needle angle (degrees, 180 = pointing left) for the middle of each band. Band only, no value. */
const NEEDLE_DEG: Record<RiskLevel, number> = { low: 150, medium: 90, high: 30 };

const point = (deg: number, r = R) => {
  const rad = (deg * Math.PI) / 180;
  return { x: CX + r * Math.cos(rad), y: CY - r * Math.sin(rad) };
};

function arc(fromDeg: number, toDeg: number): string {
  const a = point(fromDeg);
  const b = point(toDeg);
  return `M ${a.x.toFixed(2)} ${a.y.toFixed(2)} A ${R} ${R} 0 0 1 ${b.x.toFixed(2)} ${b.y.toFixed(2)}`;
}

/**
 * A semicircle with three equal bands (Low, Medium, High). The needle points to the middle of the
 * active band, so the gauge shows the band and nothing finer: the API returns no score.
 * Exposed as one labelled image ("Risk level: High"), not as a meter, so no value is implied.
 */
export function RiskGauge({ risk }: { risk: RiskLevel }) {
  const { t } = useI18n();
  const label = fmt(t.result.gaugeLabel, { risk: t.result.gaugeBand[risk] });
  const target = NEEDLE_DEG[risk];

  return (
    <svg viewBox="0 0 200 122" role="img" aria-label={label} data-testid="risk-gauge" className="w-full max-w-[220px]">
      {LEVELS.map((level, i) => {
        const from = 180 - i * 60 - (i === 0 ? 0 : GAP_DEG / 2);
        const to = 180 - (i + 1) * 60 + (i === 2 ? 0 : GAP_DEG / 2);
        const active = level === risk;
        return (
          <path
            key={level}
            d={arc(from, to)}
            fill="none"
            strokeLinecap="round"
            strokeWidth={active ? 15 : 11}
            style={{ stroke: `var(--risk-${level}-solid)`, opacity: active ? 1 : 0.28 }}
          />
        );
      })}
      {/* Needle: drawn pointing right (0 deg) and rotated to the band; sweeps in from Low. */}
      <m.g
        initial={{ rotate: -180 }}
        animate={{ rotate: -target }}
        transition={{ type: "spring", stiffness: 90, damping: 14, mass: 0.9 }}
        style={{ originX: `${CX}px`, originY: `${CY}px`, transformBox: "view-box" }}
      >
        <line x1={CX} y1={CY} x2={CX + R - 20} y2={CY} strokeWidth={4} strokeLinecap="round" style={{ stroke: "var(--foreground)" }} />
      </m.g>
      <circle cx={CX} cy={CY} r={8} style={{ fill: "var(--foreground)" }} />
      <circle cx={CX} cy={CY} r={3.5} style={{ fill: "var(--card)" }} />
      <g aria-hidden="true" fontSize="10" fontWeight={600} style={{ fill: "var(--muted-foreground)" }}>
        <text x={point(180).x} y={CY + 18} textAnchor="middle">{t.result.gaugeBand.low}</text>
        <text x={CX} y={11} textAnchor="middle">{t.result.gaugeBand.medium}</text>
        <text x={point(0).x} y={CY + 18} textAnchor="middle">{t.result.gaugeBand.high}</text>
      </g>
    </svg>
  );
}
