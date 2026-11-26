// Director of Operations overview: KPI header (warehouse) and tonight's queue (Lakebase).
import { Alert, AlertDescription, Skeleton } from '@databricks/appkit-ui/react';
import { useEffect, useState } from 'react';
import { ItemSheet } from '../../components/ItemSheet';
import { KpiHeader } from '../../components/KpiHeader';
import { Queue } from '../../components/Queue';
import { api, fmt, type QueueRow, type Snapshot } from '../../lib/api';

// KPIs cover complete days: the day before the recommendation snapshot.
function dayBefore(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

export function OpsPage() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<QueueRow | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    api
      .snapshot()
      .then(setSnap)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [refreshKey]);

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>The recommendation snapshot could not be read from Lakebase: {error}</AlertDescription>
      </Alert>
    );
  }
  if (!snap) return <Skeleton className="h-40" />;
  return (
    <div className="space-y-6 w-full max-w-7xl mx-auto">
      <div>
        <h2 className="text-2xl font-bold text-foreground">Store operations</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Recommendations for the night of {fmt.day(snap.forecast_date)}, from on hand as of {fmt.ts(snap.as_of_ts)}{' '}
          (scored {fmt.ts(snap.scored_at)}, model version {snap.model_version}): {fmt.int(snap.stockout_risk)} stockout
          risks, {fmt.int(snap.overstock)} overstocks, {fmt.usd(snap.order_value)} of orders at cost.
        </p>
      </div>
      <KpiHeader anchor={dayBefore(snap.forecast_date)} />
      <Queue refreshKey={refreshKey} onOpen={setOpen} />
      <ItemSheet row={open} onClose={() => setOpen(null)} onSaved={() => setRefreshKey((k) => k + 1)} />
    </div>
  );
}
