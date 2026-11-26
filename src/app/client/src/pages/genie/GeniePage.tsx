// Ask Genie: the space "Bigbox Stores - Store Ops", embedded. Genie's routes run on behalf of the
// signed-in user (user_api_scopes: dashboards.genie), so answers respect that user's own access.
import { Badge, GenieChat } from '@databricks/appkit-ui/react';
import { useEffect, useState } from 'react';
import { api } from '../../lib/api';

export function GeniePage() {
  const [me, setMe] = useState<string | null>(null);
  useEffect(() => {
    api
      .whoami()
      .then((w) => setMe(w.email ?? w.user))
      .catch(() => setMe(null));
  }, []);
  return (
    <div className="space-y-4 w-full max-w-4xl mx-auto">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-2xl font-bold text-foreground">Ask Genie</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Questions about availability, lost sales, shrink, sales, supplier fill, tonight’s queue and planner
            decisions, answered from the same metric views as the KPIs above.
          </p>
        </div>
        <Badge variant="secondary">{me ?? 'Signed in'}</Badge>
      </div>
      <div className="h-[min(640px,70vh)] border rounded-lg overflow-hidden">
        <GenieChat alias="default" placeholder="e.g. Which stores lost the most sales to stockouts last week?" />
      </div>
      <p className="text-xs text-muted-foreground">
        AI-generated from your data via Genie: open the SQL under each answer and check it before you rely on a number.
        Queries run with your own permissions (on behalf of {me ?? 'you'}), so region filters apply. “Last week” and
        “yesterday” mean the latest complete days in the data.
      </p>
    </div>
  );
}
