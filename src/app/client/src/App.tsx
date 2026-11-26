import { createBrowserRouter, RouterProvider, Link, NavLink, Outlet, useLocation } from 'react-router';
import { useEffect, useState } from 'react';
import {
  Badge,
  Button,
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@databricks/appkit-ui/react';
import { FileQuestionMark } from 'lucide-react';
import { OpsPage } from './pages/ops/OpsPage';
import { GeniePage } from './pages/genie/GeniePage';
import { api } from './lib/api';

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
    isActive ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'
  }`;

function Layout() {
  const [me, setMe] = useState<string | null>(null);
  useEffect(() => {
    api
      .whoami()
      .then((w) => setMe(w.email ?? w.user))
      .catch(() => setMe(null));
  }, []);
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="border-b px-4 md:px-6 py-3 flex flex-wrap items-center gap-4">
        <h1 className="text-lg font-semibold text-foreground">Bigbox Stores · Store Ops</h1>
        <nav className="flex gap-1">
          <NavLink to="/" end className={navLinkClass}>
            Overview & queue
          </NavLink>
          <NavLink to="/genie" className={navLinkClass}>
            Ask Genie
          </NavLink>
        </nav>
        <Badge variant="secondary" className="ml-auto">
          {me ?? 'Signed in'}
        </Badge>
      </header>
      <main className="flex-1 p-4 md:p-6">
        <Outlet />
      </main>
    </div>
  );
}

function NotFoundPage() {
  const { pathname } = useLocation();
  return (
    <Empty>
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <FileQuestionMark />
        </EmptyMedia>
        <EmptyTitle>Page not found</EmptyTitle>
        <EmptyDescription>
          There is no page at <code className="break-all">{pathname}</code>
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button asChild>
          <Link to="/">Back to the overview</Link>
        </Button>
      </EmptyContent>
    </Empty>
  );
}

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: '/', element: <OpsPage /> },
      { path: '/genie', element: <GeniePage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
