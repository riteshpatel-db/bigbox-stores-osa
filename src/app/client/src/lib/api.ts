// Typed calls to the app's own routes (server/routes/ops.ts). Responses are parsed with zod so the
// UI never renders a shape it did not expect. Lakebase returns numerics as strings, so numbers are
// coerced.
import { z } from 'zod';

const num = z.coerce.number();
const numOrNull = z.union([z.null(), z.coerce.number()]);

export const Snapshot = z.object({
  as_of_ts: z.string(),
  forecast_date: z.string(),
  scored_at: z.string(),
  model_version: z.string(),
  stockout_risk: num,
  overstock: num,
  order_value: num,
});
export type Snapshot = z.infer<typeof Snapshot>;

export const QueueRow = z.object({
  store_id: z.string(),
  sku_id: z.string(),
  region: z.string(),
  category: z.string(),
  perishable: z.boolean(),
  on_hand: num,
  on_order_units: num,
  case_pack: num,
  forecast_today: num,
  demand_until_delivery: num,
  stockout_risk: num,
  expected_lost_sales: num,
  days_of_supply: numOrNull,
  recommended_order_qty: num,
  recommended_order_value: num,
  queue_reason: z.enum(['STOCKOUT_RISK', 'OVERSTOCK']),
  priority: num,
  as_of_ts: z.string(),
  decision_id: z.string().nullable(),
  action: z.enum(['approve', 'override', 'reject']).nullable(),
  final_qty: numOrNull,
  decided_by: z.string().nullable(),
  decided_at: z.string().nullable(),
});
export type QueueRow = z.infer<typeof QueueRow>;

export const QueuePage = z.object({ total: num, rows: z.array(QueueRow), ms: num });
export type QueuePage = z.infer<typeof QueuePage>;

export const DecisionRow = z.object({
  decision_id: z.string(),
  rec_as_of_ts: z.string(),
  recommended_qty: num,
  final_qty: num,
  action: z.enum(['approve', 'override', 'reject']),
  reason: z.string().nullable(),
  decided_by: z.string(),
  decided_at: z.string(),
});
export type DecisionRow = z.infer<typeof DecisionRow>;

export const Item = z.object({
  item: z
    .object({
      store_id: z.string(),
      sku_id: z.string(),
      region: z.string(),
      format: z.string(),
      category: z.string(),
      perishable: z.boolean(),
      as_of_ts: z.string(),
      on_hand: num,
      on_order_units: num,
      lead_time_days: num,
      case_pack: num,
      shelf_life_days: numOrNull,
      unit_price: num,
      unit_cost: num,
      forecast_today: num,
      forecast_next_7d: num,
      demand_until_delivery: num,
      stockout_risk: num,
      expected_lost_sales: num,
      days_of_supply: numOrNull,
      reorder_point: num,
      order_up_to: num,
      recommended_order_qty: num,
      recommended_order_value: num,
      queue_reason: z.string().nullable(),
      priority: num,
      model_version: z.string(),
    })
    .loose(),
  decisions: z.array(DecisionRow),
});
export type Item = z.infer<typeof Item>;

export const WhatIfResult = z.object({
  batch_forecast: num,
  endpoint_baseline: num,
  whatif_forecast: num,
  edited: z.object({ unit_price: num, promo_discount: num, effective_price: num }),
  ms: num,
});
export type WhatIfResult = z.infer<typeof WhatIfResult>;

export const DecisionSaved = z.object({
  decision_id: z.string(),
  decided_at: z.string(),
  action: z.string(),
  recommended_qty: num,
  final_qty: num,
});
export type DecisionSaved = z.infer<typeof DecisionSaved>;

export const WhoAmI = z.object({ email: z.string().nullable(), user: z.string().nullable() });

async function call<T>(schema: z.ZodType<T>, url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  const body: unknown = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = z.object({ error: z.string() }).safeParse(body);
    throw new Error(msg.success ? msg.data.error : `Request failed (${res.status})`);
  }
  return schema.parse(body);
}

export const api = {
  whoami: () => call(WhoAmI, '/api/whoami'),
  snapshot: () => call(Snapshot, '/api/snapshot'),
  queue: (params: URLSearchParams) => call(QueuePage, `/api/queue?${params.toString()}`),
  item: (store: string, sku: string) => call(Item, `/api/items/${store}/${sku}`),
  whatif: (body: { store_id: string; sku_id: string; promo_discount: number; unit_price?: number }) =>
    call(WhatIfResult, '/api/whatif', { method: 'POST', body: JSON.stringify(body) }),
  decide: (body: {
    store_id: string;
    sku_id: string;
    action: 'approve' | 'override' | 'reject';
    final_qty?: number;
    reason?: string;
  }) => call(DecisionSaved, '/api/decisions', { method: 'POST', body: JSON.stringify(body) }),
};

export const fmt = {
  pct: (x: number, digits = 1) => `${(x * 100).toFixed(digits)} %`,
  usd: (x: number) => `$${Math.round(x).toLocaleString('en-US')}`,
  int: (x: number) => Math.round(x).toLocaleString('en-US'),
  dec: (x: number, digits = 1) => x.toLocaleString('en-US', { maximumFractionDigits: digits }),
  day: (iso: string) =>
    new Date(`${iso.slice(0, 10)}T00:00:00Z`).toLocaleDateString('en-US', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      timeZone: 'UTC',
    }),
  ts: (iso: string) =>
    new Date(iso).toLocaleString('en-US', {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'UTC',
      timeZoneName: 'short',
    }),
};
