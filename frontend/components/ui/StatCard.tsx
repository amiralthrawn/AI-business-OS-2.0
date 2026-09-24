import Link from "next/link";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import Card from "@/components/ui/Card";
import Sparkline, { type SparkPoint } from "@/components/ui/Sparkline";

interface StatCardProps {
  label: string;
  value: React.ReactNode;
  href?: string;
  sparkline?: number[] | SparkPoint[];
  // Shown in place of the line when the real history is too thin to draw one.
  sparklineEmpty?: string;
  sparklineTone?: string;
  badge?: { label: string; tone: BadgeTone };
  emphasize?: boolean;
}

// The one metric tile, from a plain data-page count (label + value) up to a
// full Command Center KPI (+ sparkline + trend badge). Every variant shares
// the same card shell so the visual language stays one system.
export default function StatCard({ label, value, href, sparkline, sparklineEmpty, sparklineTone, badge, emphasize }: StatCardProps) {
  const content = (
    <>
      <p className="text-[13px] font-medium text-text-soft">{label}</p>
      <p
        className={`mt-3 figure text-[28px] md:text-[34px] ${
          emphasize ? "text-danger" : "text-text"
        }`}
      >
        {value}
      </p>
      {(sparkline || sparklineEmpty || badge) && (
        <div className="mt-3.5 flex min-h-[26px] items-center justify-between gap-3">
          {sparkline && sparkline.length > 0 && typeof sparkline[0] === "object" ? (
            <Sparkline series={sparkline as SparkPoint[]} tone={sparklineTone} width={96} ariaLabel={`${label} par mois`} />
          ) : sparkline ? (
            <Sparkline points={sparkline as number[]} tone={sparklineTone} />
          ) : sparklineEmpty ? (
            <span className="text-[11.5px] text-text-faint">{sparklineEmpty}</span>
          ) : (
            <span />
          )}
          {badge && <Badge label={badge.label} tone={badge.tone} />}
        </div>
      )}
    </>
  );

  const className = `p-6 transition-colors ${href ? "hover:border-border-strong" : ""} ${
    emphasize ? "border-danger-soft" : ""
  }`;

  if (href) {
    return (
      <Link href={href}>
        <Card className={className}>{content}</Card>
      </Link>
    );
  }

  return <Card className={className}>{content}</Card>;
}
