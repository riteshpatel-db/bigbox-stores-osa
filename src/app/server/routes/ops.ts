// Operations routes: tonight's reorder queue and item detail (Lakebase synced table), the what-if
// (Model Serving endpoint bigbox-demand-forecast) and planner decisions (Lakebase app.reorder_decisions).
// Every route runs as the app's service principal; the signed-in user is recorded on each decision.
import type { Application, Request } from 'express';
import { z } from 'zod';

interface OpsAppKit {
  lakebase: { query(text: string, params?: unknown[]): Promise<{ rows: Record<string, unknown>[] }> };
  server: { extend(fn: (app: Application) => void): void };
  serving: (alias?: string) => { invoke(body: Record<string, unknown>): Promise<unknown> };
}

const REC = 'serving.recommendations_synced';
const DECISIONS = 'app.reorder_decisions';

function first(rows: Record<string, unknown>[]): Record<string, unknown> {
  const row = rows[0];
  if (!row) throw new Error('query returned no row');
  return row;
}

function log(event: string, fields: Record<string, unknown>) {
  console.log(JSON.stringify({ event, ts: new Date().toISOString(), ...fields }));
}

// The Apps proxy injects the signed-in identity; locally there is none.
function caller(req: Request): string | null {
  const who = req.header('x-forwarded-email') ?? req.header('x-forwarded-user');
  if (who) return who;
  return process.env.NODE_ENV === 'development' ? 'local-dev' : null;
}

const QueueQuery = z.object({
  reason: z.enum(['STOCKOUT_RISK', 'OVERSTOCK']).optional(),
  region: z.enum(['CENTRAL', 'EAST', 'SOUTH', 'WEST']).optional(),
  store: z
    .string()
    .regex(/^S\d{3}$/)
    .optional(),
  open: z.enum(['true', 'false']).optional(),
  limit: z.coerce.number().int().min(1).max(200).default(25),
  offset: z.coerce.number().int().min(0).default(0),
});

const Key = z.object({
  store_id: z.string().regex(/^S\d{3}$/),
  sku_id: z.string().regex(/^SKU\d{4}$/),
});

const WhatIf = Key.extend({
  promo_discount: z.number().min(0).max(0.5),
  unit_price: z.number().positive().max(10000).optional(),
});

const Decision = Key.extend({
  action: z.enum(['approve', 'override', 'reject']),
  final_qty: z.number().int().min(0).max(100000).optional(),
  reason: z.string().trim().max(500).optional(),
});

const Invoked = z.union([
  z.object({ ok: z.literal(true), data: z.object({ predictions: z.array(z.number()).length(2) }) }),
  z.object({ ok: z.literal(false), status: z.number().optional(), message: z.string().optional() }),
]);

// Latest decision on the same recommendation snapshot, if any.
const LATEST_DECISION = `
  LEFT JOIN LATERAL (
    SELECT d.decision_id, d.action, d.final_qty, d.decided_by, d.decided_at
    FROM ${DECISIONS} d
    WHERE d.store_id = r.store_id AND d.sku_id = r.sku_id AND d.rec_as_of_ts = r.as_of_ts
    ORDER BY d.decided_at DESC LIMIT 1
  ) d ON true`;

const QUEUE_FILTER = `
  WHERE r.queue_reason IS NOT NULL
    AND ($1::text IS NULL OR r.queue_reason = $1)
    AND ($2::text IS NULL OR r.region = $2)
    AND ($3::text IS NULL OR r.store_id = $3)
    AND ($4::boolean IS NOT TRUE OR d.action IS NULL)`;

export function setupOpsRoutes(appkit: OpsAppKit) {
  appkit.server.extend((app) => {
    app.get('/api/whoami', (req, res) => {
      res.json({
        email: req.header('x-forwarded-email') ?? null,
        user: req.header('x-forwarded-user') ?? null,
      });
    });

    app.get('/api/health', async (_req, res) => {
      const t0 = performance.now();
      try {
        const { rows } = await appkit.lakebase.query(
          `SELECT max(as_of_ts) AS as_of_ts, count(*)::int AS rows,
                  count(*) FILTER (WHERE queue_reason IS NOT NULL)::int AS queue_rows,
                  (SELECT count(*)::int FROM ${DECISIONS}) AS decisions
           FROM ${REC}`
        );
        res.json({ status: 'ok', lakebase_ms: Math.round(performance.now() - t0), ...first(rows) });
      } catch (err) {
        log('health_error', { error: String(err) });
        res.status(503).json({ status: 'error', error: 'Lakebase unavailable' });
      }
    });

    app.get('/api/snapshot', async (_req, res) => {
      try {
        const { rows } = await appkit.lakebase.query(
          `SELECT max(as_of_ts) AS as_of_ts, max(forecast_date)::text AS forecast_date,
                  max(scored_at) AS scored_at, max(model_version) AS model_version,
                  count(*) FILTER (WHERE queue_reason = 'STOCKOUT_RISK')::int AS stockout_risk,
                  count(*) FILTER (WHERE queue_reason = 'OVERSTOCK')::int AS overstock,
                  sum(recommended_order_value)::float8 AS order_value
           FROM ${REC}`
        );
        res.json(first(rows));
      } catch (err) {
        log('snapshot_error', { error: String(err) });
        res.status(500).json({ error: 'Failed to read the recommendation snapshot' });
      }
    });

    app.get('/api/queue', async (req, res) => {
      const q = QueueQuery.safeParse(req.query);
      if (!q.success) {
        res.status(400).json({ error: 'Invalid filter', issues: q.error.issues });
        return;
      }
      const { reason, region, store, open, limit, offset } = q.data;
      const params = [reason ?? null, region ?? null, store ?? null, open === 'true'];
      const t0 = performance.now();
      try {
        const [{ rows }, total] = await Promise.all([
          appkit.lakebase.query(
            `SELECT r.store_id, r.sku_id, r.region, r.category, r.perishable, r.on_hand,
                    r.on_order_units, r.case_pack, r.forecast_today, r.demand_until_delivery,
                    r.stockout_risk, r.expected_lost_sales, r.days_of_supply,
                    r.recommended_order_qty, r.recommended_order_value, r.queue_reason, r.priority,
                    r.as_of_ts, d.decision_id, d.action, d.final_qty, d.decided_by, d.decided_at
             FROM ${REC} r ${LATEST_DECISION} ${QUEUE_FILTER}
             ORDER BY r.priority LIMIT $5 OFFSET $6`,
            [...params, limit, offset]
          ),
          appkit.lakebase.query(`SELECT count(*)::int AS n FROM ${REC} r ${LATEST_DECISION} ${QUEUE_FILTER}`, params),
        ]);
        const ms = Math.round(performance.now() - t0);
        log('queue', { user: caller(req), reason, region, store, open, offset, rows: rows.length, ms });
        res.json({ total: first(total.rows).n, rows, ms });
      } catch (err) {
        log('queue_error', { error: String(err) });
        res.status(500).json({ error: 'Failed to read the queue' });
      }
    });

    app.get('/api/items/:store_id/:sku_id', async (req, res) => {
      const k = Key.safeParse(req.params);
      if (!k.success) {
        res.status(400).json({ error: 'Invalid store or SKU' });
        return;
      }
      try {
        const [item, history] = await Promise.all([
          appkit.lakebase.query(`SELECT * FROM ${REC} WHERE store_id = $1 AND sku_id = $2`, [
            k.data.store_id,
            k.data.sku_id,
          ]),
          appkit.lakebase.query(
            `SELECT decision_id, rec_as_of_ts, recommended_qty, final_qty, action, reason,
                    decided_by, decided_at
             FROM ${DECISIONS} WHERE store_id = $1 AND sku_id = $2
             ORDER BY decided_at DESC LIMIT 20`,
            [k.data.store_id, k.data.sku_id]
          ),
        ]);
        if (item.rows.length === 0) {
          res.status(404).json({ error: 'No recommendation for this store and SKU' });
          return;
        }
        log('item', { user: caller(req), ...k.data });
        res.json({ item: first(item.rows), decisions: history.rows });
      } catch (err) {
        log('item_error', { error: String(err) });
        res.status(500).json({ error: 'Failed to read the item' });
      }
    });

    // What-if: score the item's feature row as it is and with the planner's promotion / price,
    // in one request to the endpoint (the first prediction should equal the batch forecast).
    app.post('/api/whatif', async (req, res) => {
      const w = WhatIf.safeParse(req.body);
      if (!w.success) {
        res.status(400).json({ error: 'Invalid what-if', issues: w.error.issues });
        return;
      }
      try {
        const { rows } = await appkit.lakebase.query(
          `SELECT features_json, forecast_today FROM ${REC} WHERE store_id = $1 AND sku_id = $2`,
          [w.data.store_id, w.data.sku_id]
        );
        if (rows.length === 0) {
          res.status(404).json({ error: 'No recommendation for this store and SKU' });
          return;
        }
        const base = z.record(z.string(), z.unknown()).parse(JSON.parse(String(first(rows).features_json)));
        const price = w.data.unit_price ?? Number(base.unit_price);
        const edited = {
          ...base,
          unit_price: price,
          promo_discount: w.data.promo_discount,
          effective_price: Math.round(price * (1 - w.data.promo_discount) * 100) / 100,
        };
        const t0 = performance.now();
        const out = await appkit.serving().invoke({ dataframe_records: [base, edited] });
        const ms = Math.round(performance.now() - t0);
        // invoke() resolves to AppKit's execution envelope, not the bare endpoint response.
        const env = Invoked.parse(out);
        if (!env.ok) throw new Error(`endpoint ${env.status ?? ''}: ${env.message ?? 'failed'}`);
        const preds = env.data.predictions;
        log('whatif', { user: caller(req), ...w.data, baseline: preds[0], whatif: preds[1], ms });
        res.json({
          batch_forecast: Number(first(rows).forecast_today),
          endpoint_baseline: preds[0],
          whatif_forecast: preds[1],
          edited: {
            unit_price: edited.unit_price,
            promo_discount: edited.promo_discount,
            effective_price: edited.effective_price,
          },
          ms,
        });
      } catch (err) {
        log('whatif_error', { error: String(err) });
        res.status(502).json({ error: 'The forecast endpoint did not answer; try again' });
      }
    });

    app.post('/api/decisions', async (req, res) => {
      const who = caller(req);
      if (!who) {
        res.status(401).json({ error: 'No signed-in user' });
        return;
      }
      const d = Decision.safeParse(req.body);
      if (!d.success) {
        res.status(400).json({ error: 'Invalid decision', issues: d.error.issues });
        return;
      }
      const { store_id, sku_id, action, reason } = d.data;
      if (action !== 'approve' && !reason) {
        res.status(400).json({ error: 'A reason is required to override or reject' });
        return;
      }
      if (action === 'override' && d.data.final_qty === undefined) {
        res.status(400).json({ error: 'An override needs the final quantity' });
        return;
      }
      try {
        // The recommendation comes from the synced table, never from the client.
        const { rows } = await appkit.lakebase.query(
          `SELECT as_of_ts, recommended_order_qty FROM ${REC} WHERE store_id = $1 AND sku_id = $2`,
          [store_id, sku_id]
        );
        if (rows.length === 0) {
          res.status(404).json({ error: 'No recommendation for this store and SKU' });
          return;
        }
        const rec = first(rows);
        const recommended = Number(rec.recommended_order_qty);
        const final = action === 'approve' ? recommended : action === 'reject' ? 0 : (d.data.final_qty ?? recommended);
        const ins = await appkit.lakebase.query(
          `INSERT INTO ${DECISIONS}
             (store_id, sku_id, rec_as_of_ts, recommended_qty, final_qty, action, reason, decided_by)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
           RETURNING decision_id, decided_at`,
          [store_id, sku_id, rec.as_of_ts, recommended, final, action, reason ?? null, who]
        );
        const row = first(ins.rows);
        log('decision', { user: who, store_id, sku_id, action, recommended, final, decision_id: row.decision_id });
        res.status(201).json({ ...row, store_id, sku_id, action, recommended_qty: recommended, final_qty: final });
      } catch (err) {
        log('decision_error', { user: who, store_id, sku_id, error: String(err) });
        res.status(500).json({ error: 'The decision was not saved' });
      }
    });
  });
}
