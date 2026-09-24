import Badge from "@/components/ui/Badge";
import { BASIS_HINT, BASIS_LABEL, BASIS_TONE, CONFIDENCE_LABEL } from "@/lib/objects";
import type { Confidence, ValueBasis } from "@/lib/types";

// The nature of a value, shown next to it everywhere it matters -- an
// estimate is always labelled as one (brain/decisions.md #34).
export default function BasisBadge({ basis, confidence }: { basis: ValueBasis; confidence?: Confidence | string | null }) {
  const label = confidence && confidence !== "none" && basis !== "observed" ? `${BASIS_LABEL[basis]} · ${CONFIDENCE_LABEL[confidence as Confidence] ?? confidence}` : BASIS_LABEL[basis];
  return (
    <span title={BASIS_HINT[basis]}>
      <Badge label={label} tone={BASIS_TONE[basis]} />
    </span>
  );
}
