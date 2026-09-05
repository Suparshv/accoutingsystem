import { RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useApi } from "@/hooks/useApi";
import { useAuth } from "@/hooks/useAuth";
import type { DashboardStats } from "@/types/api";

// SPEC.md §9 dashboard: one endpoint, one round trip, three tile groups —
// exactly the App Dashboard tiles in the mockup.
export default function Dashboard() {
  const { user } = useAuth();
  const path = "/dashboard";
  const { data, loading, error, refetch } = useApi<DashboardStats>(path, [path]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-text_primary">Dashboard</h1>
        <p className="text-sm text-text_secondary">
          {user?.name ? `Signed in as ${user.name}. ` : ""}
          Counts come straight from the database — nothing here is hardcoded.
        </p>
      </div>

      {loading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {Array.from({ length: 9 }).map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded border border-border bg-surface" />
          ))}
        </div>
      )}

      {!loading && error && (
        <div className="flex flex-col items-center gap-3 rounded border border-border px-4 py-10 text-center">
          <p className="text-sm text-danger">{error.message}</p>
          <Button type="button" variant="outline" size="sm" onClick={refetch}>
            <RotateCcw className="mr-2 h-4 w-4" />
            Retry
          </Button>
        </div>
      )}

      {!loading && !error && data && (
        <div className="flex flex-col gap-6">
          <TileGroup
            title="Sales"
            tiles={[
              { label: "All", value: data.sales.all },
              { label: "Confirmed", value: data.sales.confirmed },
              { label: "Draft", value: data.sales.draft },
            ]}
          />
          <TileGroup
            title="Purchase"
            tiles={[
              { label: "All", value: data.purchase.all },
              { label: "Confirmed", value: data.purchase.confirmed },
              { label: "Draft", value: data.purchase.draft },
            ]}
          />
          <TileGroup
            title="Budget"
            tiles={[
              { label: "Achieved", value: data.budget.achieved },
              { label: "Budget", value: data.budget.budget },
              { label: "Committed", value: data.budget.committed },
            ]}
          />
        </div>
      )}
    </div>
  );
}

function TileGroup({
  title,
  tiles,
}: {
  title: string;
  tiles: { label: string; value: number }[];
}) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-text_secondary">
        {title}
      </h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {tiles.map((tile) => (
          <div key={tile.label} className="rounded border border-border bg-background p-5">
            <p className="text-sm text-text_secondary">{tile.label}</p>
            <p className="mt-1 text-3xl font-semibold tabular-nums text-text_primary">
              {tile.value}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
