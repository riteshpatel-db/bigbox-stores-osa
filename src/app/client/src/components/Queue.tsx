// Tonight's at-risk queue, read from the Lakebase synced table through /api/queue.
// Server-side filters and paging; a row opens the item detail.
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@databricks/appkit-ui/react';
import { useEffect, useState } from 'react';
import { api, fmt, type QueuePage, type QueueRow } from '../lib/api';

const PAGE = 25;
const ALL = 'all';

function DecisionBadge({ row }: { row: QueueRow }) {
  if (!row.action) return <span className="text-xs text-muted-foreground">open</span>;
  const variant = row.action === 'approve' ? 'secondary' : row.action === 'override' ? 'outline' : 'destructive';
  return <Badge variant={variant}>{row.action}</Badge>;
}

export function Queue({ refreshKey, onOpen }: { refreshKey: number; onOpen: (row: QueueRow) => void }) {
  const [reason, setReason] = useState<string>(ALL);
  const [region, setRegion] = useState<string>(ALL);
  const [store, setStore] = useState('');
  const [openOnly, setOpenOnly] = useState(false);
  const [offset, setOffset] = useState(0);
  // The last response, tagged with the request it answers: loading = the tag is not the current request.
  const [result, setResult] = useState<{ key: string; page?: QueuePage; error?: string } | null>(null);

  const storeValid = store === '' || /^S\d{3}$/.test(store);
  const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
  if (reason !== ALL) params.set('reason', reason);
  if (region !== ALL) params.set('region', region);
  if (store) params.set('store', store);
  if (openOnly) params.set('open', 'true');
  const key = `${params.toString()}#${refreshKey}`;

  useEffect(() => {
    if (!storeValid) return;
    let live = true;
    api
      .queue(new URLSearchParams(key.split('#')[0]))
      .then((page) => live && setResult({ key, page }))
      .catch((e: unknown) => live && setResult({ key, error: e instanceof Error ? e.message : String(e) }));
    return () => {
      live = false;
    };
  }, [key, storeValid]);

  const loading = storeValid && result?.key !== key;
  const page = result?.page ?? null;
  const error = result?.key === key ? (result.error ?? null) : null;

  const resetTo =
    <T,>(set: (v: T) => void) =>
    (v: T) => {
      set(v);
      setOffset(0);
    };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Tonight’s reorder queue</CardTitle>
        <CardDescription>
          Store × SKUs the policy flags, most urgent first (expected lost sales). Read from Lakebase
          (serving.recommendations_synced){page ? `, ${page.ms} ms` : ''}.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="reason">Flag</Label>
            <Select value={reason} onValueChange={resetTo(setReason)}>
              <SelectTrigger id="reason" className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All flags</SelectItem>
                <SelectItem value="STOCKOUT_RISK">Stockout risk</SelectItem>
                <SelectItem value="OVERSTOCK">Overstock</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="region">Region</Label>
            <Select value={region} onValueChange={resetTo(setRegion)}>
              <SelectTrigger id="region" className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All regions</SelectItem>
                {['CENTRAL', 'EAST', 'SOUTH', 'WEST'].map((r) => (
                  <SelectItem key={r} value={r}>
                    {r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="store">Store</Label>
            <Input
              id="store"
              className="w-28"
              placeholder="S001"
              value={store}
              aria-invalid={!storeValid}
              onChange={(e) => resetTo(setStore)(e.target.value.toUpperCase().trim())}
            />
          </div>
          <Button variant={openOnly ? 'default' : 'outline'} onClick={() => resetTo(setOpenOnly)(!openOnly)}>
            {openOnly ? 'Showing undecided only' : 'Show undecided only'}
          </Button>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>The queue could not be loaded: {error}</AlertDescription>
          </Alert>
        )}
        {loading && !page && <Skeleton className="h-96" />}
        {page && page.rows.length === 0 && (
          <Empty>
            <EmptyHeader>
              <EmptyTitle>Nothing in the queue for these filters</EmptyTitle>
              <EmptyDescription>Clear a filter, or include items that already have a decision.</EmptyDescription>
            </EmptyHeader>
          </Empty>
        )}
        {page && page.rows.length > 0 && (
          <div className={loading ? 'opacity-60' : ''}>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-right">#</TableHead>
                  <TableHead>Store</TableHead>
                  <TableHead>SKU</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Flag</TableHead>
                  <TableHead className="text-right">On hand</TableHead>
                  <TableHead className="text-right">On order</TableHead>
                  <TableHead className="text-right">Demand to delivery</TableHead>
                  <TableHead className="text-right">Stockout risk</TableHead>
                  <TableHead className="text-right">Exp. lost sales</TableHead>
                  <TableHead className="text-right">Order qty</TableHead>
                  <TableHead>Decision</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {page.rows.map((r) => (
                  <TableRow
                    key={`${r.store_id}-${r.sku_id}`}
                    className="cursor-pointer"
                    onClick={() => onOpen(r)}
                    tabIndex={0}
                    onKeyDown={(e) => e.key === 'Enter' && onOpen(r)}
                  >
                    <TableCell className="text-right tabular-nums">{r.priority}</TableCell>
                    <TableCell>{r.store_id}</TableCell>
                    <TableCell>{r.sku_id}</TableCell>
                    <TableCell>{r.category}</TableCell>
                    <TableCell>
                      <Badge variant={r.queue_reason === 'STOCKOUT_RISK' ? 'destructive' : 'outline'}>
                        {r.queue_reason === 'STOCKOUT_RISK' ? 'stockout risk' : 'overstock'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{fmt.int(r.on_hand)}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmt.int(r.on_order_units)}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmt.dec(r.demand_until_delivery)}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmt.pct(r.stockout_risk, 0)}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmt.usd(r.expected_lost_sales)}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmt.int(r.recommended_order_qty)}</TableCell>
                    <TableCell>
                      <DecisionBadge row={r} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="flex items-center justify-between pt-3 text-sm text-muted-foreground">
              <span>
                {fmt.int(offset + 1)}–{fmt.int(offset + page.rows.length)} of {fmt.int(page.total)}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE))}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={offset + PAGE >= page.total}
                  onClick={() => setOffset(offset + PAGE)}
                >
                  Next
                </Button>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
