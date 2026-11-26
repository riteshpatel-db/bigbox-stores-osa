// KPI header: the last 7 complete days vs the 7 before, from the governed metric views
// (serving.availability_kpis, serving.sales_kpis) on the SQL warehouse.
import {
  Alert,
  AlertDescription,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Skeleton,
  useAnalyticsQuery,
} from '@databricks/appkit-ui/react';
import { sql } from '@databricks/appkit-ui/js';
import { fmt } from '../lib/api';

interface Kpi {
  label: string;
  current: number;
  prior: number;
  format: (x: number) => string;
  higherIsBetter: boolean;
  // ratios show the change in points, money and counts in per cent
  delta: 'points' | 'relative';
}

function Delta({ kpi }: { kpi: Kpi }) {
  const diff = kpi.delta === 'points' ? (kpi.current - kpi.prior) * 100 : (kpi.current / kpi.prior - 1) * 100;
  const good = kpi.higherIsBetter ? diff > 0 : diff < 0;
  const tone = Math.abs(diff) < 0.05 ? 'text-muted-foreground' : good ? 'text-success' : 'text-destructive';
  const unit = kpi.delta === 'points' ? ' pts' : ' %';
  return (
    <span className={`text-xs font-medium ${tone}`}>
      {diff >= 0 ? '+' : ''}
      {diff.toFixed(1)}
      {unit} vs prior 7 days ({kpi.format(kpi.prior)})
    </span>
  );
}

export function KpiHeader({ anchor }: { anchor: string }) {
  const params = { anchor: sql.date(anchor) };
  const av = useAnalyticsQuery('kpi_availability', params);
  const sales = useAnalyticsQuery('kpi_sales', params);
  const loading = av.loading || sales.loading;
  const error = av.error ?? sales.error;

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>KPIs could not be loaded from the SQL warehouse: {String(error)}</AlertDescription>
      </Alert>
    );
  }
  if (loading || !av.data || !sales.data) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
    );
  }
  const cur = av.data.find((r) => r.period === 'current');
  const pri = av.data.find((r) => r.period === 'prior');
  const sc = sales.data.find((r) => r.period === 'current');
  const sp = sales.data.find((r) => r.period === 'prior');
  if (!cur || !pri || !sc || !sp) {
    return (
      <Alert>
        <AlertDescription>No KPI data for the 14 days to {fmt.day(anchor)}.</AlertDescription>
      </Alert>
    );
  }
  const kpis: Kpi[] = [
    {
      label: 'On-shelf availability',
      current: cur.on_shelf_availability,
      prior: pri.on_shelf_availability,
      format: (x) => fmt.pct(x),
      higherIsBetter: true,
      delta: 'points',
    },
    {
      label: 'In-stock at close',
      current: cur.in_stock_pct,
      prior: pri.in_stock_pct,
      format: (x) => fmt.pct(x),
      higherIsBetter: true,
      delta: 'points',
    },
    {
      label: 'Lost sales to stockouts',
      current: cur.lost_sales,
      prior: pri.lost_sales,
      format: fmt.usd,
      higherIsBetter: false,
      delta: 'relative',
    },
    {
      label: 'Perishable shrink',
      current: cur.shrink_pct,
      prior: pri.shrink_pct,
      format: (x) => fmt.pct(x),
      higherIsBetter: false,
      delta: 'points',
    },
    {
      label: 'Online fill rate',
      current: cur.online_fill_rate,
      prior: pri.online_fill_rate,
      format: (x) => fmt.pct(x),
      higherIsBetter: true,
      delta: 'points',
    },
    {
      label: 'Revenue',
      current: sc.total_revenue,
      prior: sp.total_revenue,
      format: fmt.usd,
      higherIsBetter: true,
      delta: 'relative',
    },
  ];
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        {kpis.map((k) => (
          <Card key={k.label} className="gap-2 py-4">
            <CardHeader className="px-4">
              <CardDescription>{k.label}</CardDescription>
              <CardTitle className="text-2xl tabular-nums">{k.format(k.current)}</CardTitle>
            </CardHeader>
            <CardContent className="px-4">
              <Delta kpi={k} />
            </CardContent>
          </Card>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        7 days {fmt.day(cur.first_day)} – {fmt.day(cur.last_day)} vs {fmt.day(pri.first_day)} – {fmt.day(pri.last_day)}.
        Source: metric views serving.availability_kpis and serving.sales_kpis (one definition per KPI), queried as the
        app’s service principal.
      </p>
    </div>
  );
}
