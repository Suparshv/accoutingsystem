import { useState } from "react";
import { DataTable, type DataTableColumn } from "@/components/shared/DataTable";
import { KanbanGrid } from "@/components/shared/KanbanGrid";
import { ViewSwitcher, type ViewMode } from "@/components/shared/ViewSwitcher";
import { FormShell } from "@/components/shared/FormShell";
import { StatusBadge, type Status } from "@/components/shared/StatusBadge";
import { MoneyDisplay } from "@/components/shared/MoneyDisplay";
import { MoneyInput } from "@/components/shared/MoneyInput";
import { LineItemsTable, type LineItemColumn } from "@/components/shared/LineItemsTable";

// This route (/dev/components) is NOT part of the real app navigation. It
// exists purely so every shared component can be eyeballed in one place
// with mock data, without hunting through real pages. Delete it once real
// pages exist and each component has a genuine caller to demo it instead.

type Contact = {
  id: number;
  name: string;
  email: string;
  type: string;
  balance: number;
};

const MOCK_CONTACTS: Contact[] = [
  { id: 1, name: "Rahul Sharma", email: "rahul@example.com", type: "Customer", balance: 12500 },
  { id: 2, name: "Priya Traders", email: "priya@example.com", type: "Vendor", balance: 4300 },
  { id: 3, name: "Meera Furnishings", email: "meera@example.com", type: "Customer", balance: 0 },
  { id: 4, name: "Aakash Woodworks", email: "aakash@example.com", type: "Vendor", balance: 87650 },
  { id: 5, name: "Nisha Interiors", email: "nisha@example.com", type: "Customer", balance: 2100 },
];

const ALL_STATUSES: Status[] = [
  "draft",
  "confirmed",
  "posted",
  "cancelled",
  "paid",
  "partial",
  "not_paid",
  "revised",
];

type DataTableDemoState = "success" | "loading" | "error" | "empty";

type POLine = {
  product: string;
  quantity: number;
  unitPrice: number;
  lineTotal: number;
};

type JELine = {
  account: string;
  debit: number;
  credit: number;
};

export default function ComponentsPreview() {
  const [demoState, setDemoState] = useState<DataTableDemoState>("success");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("list");
  const [moneyValue, setMoneyValue] = useState("1999.99");

  const [poLines, setPoLines] = useState<POLine[]>([
    { product: "Chair", quantity: 3, unitPrice: 2000, lineTotal: 6000 },
    { product: "Sofa", quantity: 1, unitPrice: 4000, lineTotal: 4000 },
  ]);

  const [jeLines, setJeLines] = useState<JELine[]>([
    { account: "Debtors A/c", debit: 10000, credit: 0 },
    { account: "Sales Income A/c", debit: 0, credit: 9000 },
  ]);
  const [jeBalanced, setJeBalanced] = useState(false);

  const contactColumns: DataTableColumn<Contact>[] = [
    { key: "name", header: "Name" },
    { key: "email", header: "Email" },
    { key: "type", header: "Type" },
    {
      key: "balance",
      header: "Balance",
      align: "right",
      render: (row) => <MoneyDisplay value={row.balance} />,
    },
  ];

  const poColumns: LineItemColumn<POLine>[] = [
    { key: "product", header: "Product", render: (row) => row.product },
    { key: "quantity", header: "Qty", align: "right", render: (row) => row.quantity },
    {
      key: "unitPrice",
      header: "Unit Price",
      align: "right",
      render: (row) => <MoneyDisplay value={row.unitPrice} />,
    },
    {
      key: "lineTotal",
      header: "Line Total",
      align: "right",
      render: (row) => <MoneyDisplay value={row.lineTotal} />,
    },
  ];

  const jeColumns: LineItemColumn<JELine>[] = [
    { key: "account", header: "Account", render: (row) => row.account },
    {
      key: "debit",
      header: "Debit",
      align: "right",
      render: (row) => <MoneyDisplay value={row.debit} />,
    },
    {
      key: "credit",
      header: "Credit",
      align: "right",
      render: (row) => <MoneyDisplay value={row.credit} />,
    },
  ];

  const tableRows = demoState === "empty" ? [] : MOCK_CONTACTS;
  const tableError =
    demoState === "error" ? { message: "Could not load contacts. Please try again." } : null;

  return (
    <div className="flex flex-col gap-10 pb-16">
      <div>
        <h1 className="text-2xl font-semibold text-text_primary">Shared component preview</h1>
        <p className="text-sm text-text_secondary">
          Internal dev route (/dev/components) — mock data only, not part of the real app.
        </p>
      </div>

      <Section title="StatusBadge">
        <div className="flex flex-wrap gap-2">
          {ALL_STATUSES.map((status) => (
            <StatusBadge key={status} status={status} />
          ))}
        </div>
      </Section>

      <Section title="MoneyDisplay / MoneyInput">
        <div className="flex flex-col gap-4">
          <div className="flex gap-8">
            <MoneyDisplay value={100000} />
            <MoneyDisplay value={"1234.5"} />
            <MoneyDisplay value={0} />
          </div>
          <div className="max-w-xs">
            <label className="mb-1 block text-xs font-medium text-text_secondary">
              Amount
            </label>
            <MoneyInput value={moneyValue} onChange={setMoneyValue} />
            <p className="mt-1 text-xs text-text_secondary">
              Raw string value: "{moneyValue}"
            </p>
          </div>
        </div>
      </Section>

      <Section title="DataTable + ViewSwitcher + KanbanGrid (Contacts)">
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <ViewSwitcher value={viewMode} onChange={setViewMode} />
            <div className="flex gap-2">
              {(["success", "loading", "error", "empty"] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setDemoState(s)}
                  className={`rounded-md border border-border px-2 py-1 text-xs font-medium ${
                    demoState === s ? "bg-primary text-primary-foreground" : "text-text_secondary"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {viewMode === "list" ? (
            <DataTable
              columns={contactColumns}
              rows={tableRows}
              loading={demoState === "loading"}
              error={tableError}
              page={page}
              pageSize={5}
              total={tableRows.length}
              onPageChange={setPage}
              searchValue={search}
              onSearchChange={setSearch}
              getRowId={(row) => row.id}
              onRetry={() => setDemoState("success")}
              emptyMessage="No contacts yet — add your first customer or vendor."
            />
          ) : (
            <KanbanGrid
              items={tableRows}
              loading={demoState === "loading"}
              getItemId={(row) => row.id}
              emptyMessage="No contacts yet."
              renderCard={(row) => (
                <div className="flex flex-col gap-1">
                  <p className="font-medium text-text_primary">{row.name}</p>
                  <p className="text-sm text-text_secondary">{row.email}</p>
                  <p className="text-xs uppercase tracking-wide text-text_secondary">
                    {row.type}
                  </p>
                  <MoneyDisplay value={row.balance} className="mt-2" />
                </div>
              )}
            />
          )}
        </div>
      </Section>

      <Section title="FormShell (state pipeline)">
        <FormShell
          title="Vendor Bill BILL/2026/0001"
          state="confirmed"
          onBack={() => {}}
          actions={[
            { label: "Save", variant: "outline", onClick: () => {} },
            { label: "Confirm", onClick: () => {} },
          ]}
        >
          <p className="text-sm text-text_secondary">
            Form fields go here — this is just the shell (title, back button, action row,
            and state pipeline). Real bill fields land in the next phase.
          </p>
        </FormShell>
      </Section>

      <Section title="LineItemsTable — document variant (e.g. Purchase Order)">
        <LineItemsTable
          rows={poLines}
          columns={poColumns}
          getLineTotal={(row) => row.lineTotal}
          onAddRow={() =>
            setPoLines((prev) => [
              ...prev,
              { product: "New product", quantity: 1, unitPrice: 0, lineTotal: 0 },
            ])
          }
          onRemoveRow={(index) => setPoLines((prev) => prev.filter((_, i) => i !== index))}
        />
      </Section>

      <Section title="LineItemsTable — journal_entry variant">
        <div className="flex flex-col gap-2">
          <LineItemsTable
            variant="journal_entry"
            rows={jeLines}
            columns={jeColumns}
            getDebit={(row) => row.debit}
            getCredit={(row) => row.credit}
            onBalanceChange={setJeBalanced}
            onAddRow={() =>
              setJeLines((prev) => [...prev, { account: "New account", debit: 0, credit: 0 }])
            }
            onRemoveRow={(index) => setJeLines((prev) => prev.filter((_, i) => i !== index))}
          />
          <p className="text-xs text-text_secondary">
            Post button would be {jeBalanced ? "enabled" : "disabled"} right now — the two lines
            above are deliberately left unbalanced to show the red difference.
          </p>
        </div>
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold text-text_primary">{title}</h2>
      {children}
    </section>
  );
}
