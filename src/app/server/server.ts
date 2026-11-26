import { analytics, createApp, genie, lakebase, server, serving } from '@databricks/appkit';
import { setupOpsRoutes } from './routes/ops';

// analytics: KPI header queries on the warehouse (config/queries, service principal).
// genie: the embedded space; its built-in routes run on behalf of the signed-in user.
// lakebase: the queue (synced table) and decisions (app.reorder_decisions), service principal.
// serving: the what-if forecast from bigbox-demand-forecast, called server-side as the service principal.
createApp({
  plugins: [analytics(), genie(), lakebase(), server(), serving()],
  onPluginsReady(appkit) {
    setupOpsRoutes(appkit);
  },
}).catch(console.error);
