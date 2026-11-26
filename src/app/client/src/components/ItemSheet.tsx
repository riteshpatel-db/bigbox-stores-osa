// Item detail: the recommendation and why, a what-if on the forecast (Model Serving endpoint),
// and the planner's decision (approve / override / reject), written to Lakebase.
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Input,
  Label,
  Separator,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  Skeleton,
  Textarea,
  ToggleGroup,
  ToggleGroupItem,
} from '@databricks/appkit-ui/react';
import { useEffect, useState } from 'react';
import { api, fmt, type DecisionSaved, type Item, type QueueRow, type WhatIfResult } from '../lib/api';

type Action = 'approve' | 'override' | 'reject';
const isAction = (v: string): v is Action => v === 'approve' || v === 'override' || v === 'reject';

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="font-medium tabular-nums">{value}</div>
    </div>
  );
}

function WhatIf({ item }: { item: Item['item'] }) {
  const [discount, setDiscount] = useState('10');
  const [price, setPrice] = useState(item.unit_price.toFixed(2));
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const d = Number(discount) / 100;
  const p = Number(price);
  const valid = Number.isFinite(d) && d >= 0 && d <= 0.5 && Number.isFinite(p) && p > 0;

  function run() {
    setBusy(true);
    setError(null);
    api
      .whatif({ store_id: item.store_id, sku_id: item.sku_id, promo_discount: d, unit_price: p })
      .then(setResult)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false));
  }

  return (
    <div className="space-y-3">
      <h3 className="font-semibold">What-if: today’s forecast</h3>
      <div className="flex items-end gap-3">
        <div className="space-y-1">
          <Label htmlFor="disc">Promotion discount %</Label>
          <Input id="disc" className="w-28" value={discount} onChange={(e) => setDiscount(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="price">List price $</Label>
          <Input id="price" className="w-28" value={price} onChange={(e) => setPrice(e.target.value)} />
        </div>
        <Button onClick={run} disabled={!valid || busy}>
          {busy ? 'Scoring…' : 'Forecast'}
        </Button>
      </div>
      {!valid && <p className="text-xs text-destructive">Discount 0–50 %, price above 0.</p>}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {result && (
        <div className="grid grid-cols-3 gap-3 text-sm">
          <Fact label="Batch forecast (tonight's run)" value={`${fmt.dec(result.batch_forecast, 2)} units`} />
          <Fact label="Endpoint, same row" value={`${fmt.dec(result.endpoint_baseline, 2)} units`} />
          <Fact
            label={`With ${fmt.pct(result.edited.promo_discount, 0)} off $${result.edited.unit_price.toFixed(2)}`}
            value={`${fmt.dec(result.whatif_forecast, 2)} units (${result.whatif_forecast >= result.endpoint_baseline ? '+' : ''}${fmt.pct(result.whatif_forecast / result.endpoint_baseline - 1, 0)})`}
          />
          <p className="col-span-3 text-xs text-muted-foreground">
            bigbox-demand-forecast (@champion), {result.ms} ms. The what-if changes today’s forecast only; the
            recommended order is recomputed by tonight’s batch run.
          </p>
        </div>
      )}
    </div>
  );
}

function DecisionForm({ item, onSaved }: { item: Item['item']; onSaved: (d: DecisionSaved) => void }) {
  const [action, setAction] = useState<Action>('approve');
  const [qty, setQty] = useState(String(item.recommended_order_qty));
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const q = Number(qty);
  const qtyValid = Number.isInteger(q) && q >= 0;
  const valid = action === 'approve' || (reason.trim() !== '' && (action === 'reject' || qtyValid));

  function save() {
    setBusy(true);
    setError(null);
    api
      .decide({
        store_id: item.store_id,
        sku_id: item.sku_id,
        action,
        final_qty: action === 'override' ? q : undefined,
        reason: action === 'approve' ? undefined : reason.trim(),
      })
      .then(onSaved)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false));
  }

  return (
    <div className="space-y-3">
      <h3 className="font-semibold">Decision</h3>
      <ToggleGroup type="single" variant="outline" value={action} onValueChange={(v) => isAction(v) && setAction(v)}>
        <ToggleGroupItem value="approve">Approve {fmt.int(item.recommended_order_qty)}</ToggleGroupItem>
        <ToggleGroupItem value="override">Override</ToggleGroupItem>
        <ToggleGroupItem value="reject">Reject</ToggleGroupItem>
      </ToggleGroup>
      {action === 'override' && (
        <div className="space-y-1">
          <Label htmlFor="qty">Order quantity (units; case pack {item.case_pack})</Label>
          <Input
            id="qty"
            className="w-32"
            value={qty}
            aria-invalid={!qtyValid}
            onChange={(e) => setQty(e.target.value)}
          />
        </div>
      )}
      {action !== 'approve' && (
        <div className="space-y-1">
          <Label htmlFor="why">Reason (required)</Label>
          <Textarea
            id="why"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. local event this weekend"
          />
        </div>
      )}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <Button onClick={save} disabled={!valid || busy}>
        {busy ? 'Saving…' : 'Save decision'}
      </Button>
    </div>
  );
}

export function ItemSheet({
  row,
  onClose,
  onSaved,
}: {
  row: QueueRow | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const key = row ? `${row.store_id}/${row.sku_id}` : null;
  // Responses are tagged with the item they belong to, so a stale one is never shown.
  const [loaded, setLoaded] = useState<{ key: string; data?: Item; error?: string } | null>(null);
  const [saved, setSaved] = useState<{ key: string; decision: DecisionSaved } | null>(null);

  useEffect(() => {
    if (!key) return;
    let live = true;
    const [store, sku] = key.split('/');
    api
      .item(store ?? '', sku ?? '')
      .then((data) => live && setLoaded({ key, data }))
      .catch((e: unknown) => live && setLoaded({ key, error: e instanceof Error ? e.message : String(e) }));
    return () => {
      live = false;
    };
  }, [key]);

  const current = loaded?.key === key ? loaded : null;
  const data = current?.data ?? null;
  const error = current?.error ?? null;
  const done = saved?.key === key ? saved.decision : null;
  const it = data?.item;
  return (
    <Sheet open={row !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle>
            {row?.store_id} · {row?.sku_id}
          </SheetTitle>
          <SheetDescription>
            {it
              ? `${it.category}, ${it.format} store, ${it.region}. On hand as of ${fmt.ts(it.as_of_ts)}.`
              : 'Loading…'}
          </SheetDescription>
        </SheetHeader>
        <div className="px-4 pb-6 space-y-5">
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          {!it && !error && <Skeleton className="h-64" />}
          {it && (
            <>
              <div className="flex gap-2">
                {it.queue_reason && (
                  <Badge variant={it.queue_reason === 'STOCKOUT_RISK' ? 'destructive' : 'outline'}>
                    {it.queue_reason === 'STOCKOUT_RISK' ? 'stockout risk' : 'overstock'}
                  </Badge>
                )}
                <Badge variant="secondary">queue #{it.priority}</Badge>
                {it.perishable && <Badge variant="secondary">perishable, {it.shelf_life_days} days</Badge>}
              </div>
              <div className="grid grid-cols-3 gap-3 text-sm">
                <Fact label="On hand / on order" value={`${fmt.int(it.on_hand)} / ${fmt.int(it.on_order_units)}`} />
                <Fact label="Lead time" value={`${it.lead_time_days} days`} />
                <Fact
                  label="Forecast today / next 7 days"
                  value={`${fmt.dec(it.forecast_today)} / ${fmt.dec(it.forecast_next_7d)}`}
                />
                <Fact label="Demand until delivery" value={fmt.dec(it.demand_until_delivery)} />
                <Fact label="Stockout risk" value={fmt.pct(it.stockout_risk, 0)} />
                <Fact label="Expected lost sales" value={fmt.usd(it.expected_lost_sales)} />
                <Fact
                  label="Reorder point / order-up-to"
                  value={`${fmt.dec(it.reorder_point, 0)} / ${fmt.dec(it.order_up_to, 0)}`}
                />
                <Fact
                  label="Recommended order"
                  value={`${fmt.int(it.recommended_order_qty)} units, ${fmt.usd(it.recommended_order_value)}`}
                />
                <Fact label="Days of supply" value={it.days_of_supply === null ? '-' : fmt.dec(it.days_of_supply)} />
              </div>
              <p className="text-xs text-muted-foreground">
                Model {it.model_version} of bigbox_fe_bar.ml.demand_lgbm; policy in src/ml/policy.yaml.
              </p>
              <Separator />
              <WhatIf item={it} />
              <Separator />
              {done ? (
                <Alert>
                  <AlertDescription>
                    Saved: {done.action}, {fmt.int(done.final_qty)} units (recommended {fmt.int(done.recommended_qty)}).
                    Decision {done.decision_id.slice(0, 8)}, {fmt.ts(done.decided_at)}. It reaches
                    gold.reorder_decisions with the next refresh’s write-back.
                  </AlertDescription>
                </Alert>
              ) : (
                <DecisionForm
                  item={it}
                  onSaved={(d) => {
                    if (key) setSaved({ key, decision: d });
                    onSaved();
                  }}
                />
              )}
              {data && data.decisions.length > 0 && (
                <div className="space-y-1 text-xs text-muted-foreground">
                  <div className="font-medium text-foreground">Earlier decisions on this item</div>
                  {data.decisions.map((d) => (
                    <div key={d.decision_id}>
                      {fmt.ts(d.decided_at)}: {d.action} {fmt.int(d.final_qty)} (rec. {fmt.int(d.recommended_qty)}) by{' '}
                      {d.decided_by}
                      {d.reason ? `, "${d.reason}"` : ''}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
