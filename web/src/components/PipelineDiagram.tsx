"use client";

import { Binary, EyeOff, Image as ImageIcon, Library, Link2, MessageSquareText, Scale, ScanText, ShieldCheck, Sparkles, type LucideIcon } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";

interface NodeProps {
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  icon: LucideIcon;
  /** "stack" puts the icon above the text (narrow nodes); default is icon on the left. */
  layout?: "row" | "stack";
  tone?: "plain" | "key" | "result";
}

const LINE = 15;

function Node({ x, y, w, h, label, icon: Icon, layout = "row", tone = "plain" }: NodeProps) {
  const lines = label.split("\n");
  const fill = tone === "plain" ? "var(--card)" : "var(--accent)";
  const stroke = tone === "plain" ? "var(--input)" : "var(--primary)";
  const textColor = tone === "plain" ? "var(--foreground)" : "var(--accent-foreground)";
  const iconColor = tone === "plain" ? "var(--primary)" : "var(--accent-foreground)";

  if (layout === "stack") {
    const firstBaseline = y + 40 + 4;
    return (
      <g>
        <rect x={x} y={y} width={w} height={h} rx={12} style={{ fill, stroke }} strokeWidth={tone === "plain" ? 1 : 1.75} />
        <Icon x={x + w / 2 - 9} y={y + 10} width={18} height={18} style={{ color: iconColor }} aria-hidden="true" />
        <text textAnchor="middle" fontSize={12} fontWeight={600} style={{ fill: textColor }}>
          {lines.map((line, i) => (
            <tspan key={i} x={x + w / 2} y={firstBaseline + i * LINE}>
              {line}
            </tspan>
          ))}
        </text>
      </g>
    );
  }
  const firstBaseline = y + h / 2 - ((lines.length - 1) * LINE) / 2 + 4.5;
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={12} style={{ fill, stroke }} strokeWidth={tone === "plain" ? 1 : 1.75} />
      <Icon x={x + 12} y={y + h / 2 - 9} width={18} height={18} style={{ color: iconColor }} aria-hidden="true" />
      <text fontSize={12.5} fontWeight={600} style={{ fill: textColor }}>
        {lines.map((line, i) => (
          <tspan key={i} x={x + 40} y={firstBaseline + i * LINE}>
            {line}
          </tspan>
        ))}
      </text>
    </g>
  );
}

function Arrow({ d }: { d: string }) {
  return <path d={d} fill="none" style={{ stroke: "var(--muted-foreground)" }} strokeWidth={1.5} markerEnd="url(#pipeline-arrow)" />;
}

/**
 * The analysis pipeline as an inline SVG: one image for assistive technology, with a title and a
 * full text description (the numbered steps next to it say the same in prose).
 */
export function PipelineDiagram() {
  const { t, lang } = useI18n();
  const d = t.about.diagram;
  return (
    <svg
      viewBox="0 0 360 534"
      role="img"
      aria-labelledby="pipeline-title pipeline-desc"
      lang={lang}
      className="mx-auto block h-auto w-full max-w-[26rem]"
    >
      <title id="pipeline-title">{t.about.diagramTitle}</title>
      <desc id="pipeline-desc">{t.about.diagramDesc}</desc>
      <defs>
        <marker id="pipeline-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
          <path d="M0 0 10 5 0 10z" style={{ fill: "var(--muted-foreground)" }} />
        </marker>
      </defs>

      <Node x={10} y={8} w={160} h={44} label={d.screenshot} icon={ImageIcon} />
      <Node x={190} y={8} w={160} h={44} label={d.text} icon={MessageSquareText} />
      <Arrow d="M90 52 V74" />
      <Node x={10} y={76} w={160} h={44} label={d.ocr} icon={ScanText} />

      <Arrow d="M90 120 V144" />
      <Arrow d="M270 52 V144" />
      <Node x={10} y={146} w={340} h={52} label={d.mask} icon={EyeOff} />

      <Arrow d="M63 198 V224" />
      <Arrow d="M180 198 V224" />
      <Arrow d="M297 198 V224" />
      <Node x={10} y={226} w={106} h={76} label={d.classifier} icon={Binary} layout="stack" />
      <Node x={127} y={226} w={106} h={76} label={d.url} icon={Link2} layout="stack" />
      <Node x={244} y={226} w={106} h={76} label={d.rag} icon={Library} layout="stack" />

      <Arrow d="M63 302 V328" />
      <Arrow d="M180 302 V328" />
      <Node x={10} y={330} w={230} h={44} label={d.rules} icon={Scale} tone="key" />

      <Arrow d="M125 374 V400" />
      <Arrow d="M297 302 V400" />
      <Node x={10} y={402} w={340} h={52} label={d.llm} icon={Sparkles} />

      <Arrow d="M180 454 V480" />
      <Node x={10} y={482} w={340} h={44} label={d.output} icon={ShieldCheck} tone="result" />
    </svg>
  );
}
