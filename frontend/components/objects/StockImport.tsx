"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { importStockCsv } from "@/lib/api";
import type { StockImportResult } from "@/lib/types";

// CSV/Excel-export import of stock positions. Re-importing the same file
// updates rather than duplicates; unmatched rows are reported, never guessed.
export default function StockImport() {
  const router = useRouter();
  const [result, setResult] = useState<StockImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onFile(file: File) {
    setLoading(true);
    setError(null);
    try {
      setResult(await importStockCsv(await file.text(), file.name));
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import impossible.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="p-5">
      <p className="text-[13px] font-semibold text-text">Importer un fichier de stock (CSV)</p>
      <p className="mt-1 text-[12px] text-text-faint">
        Colonnes : <span className="font-mono">sku;kind;quantity;supplier;location</span> — kind = physical, supplier ou potential. Export CSV depuis Excel accepté (séparateur « ; » ou « , »).
      </p>
      <label className="mt-3 inline-flex">
        <input type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
        <Button variant="ghost" loading={loading} onClick={(e) => (e.currentTarget.previousElementSibling as HTMLInputElement | null)?.click()}>
          Choisir un fichier…
        </Button>
      </label>
      {result && (
        <div className="mt-3 text-[12.5px]">
          <p className="text-success">{result.created_or_updated} position(s) importée(s) sur {result.rows} ligne(s) — source « {result.source} ».</p>
          {result.errors.map((e) => <p key={e} className="text-danger">{e}</p>)}
        </div>
      )}
      {error && <p className="mt-2 text-[12.5px] text-danger">{error}</p>}
    </Card>
  );
}
