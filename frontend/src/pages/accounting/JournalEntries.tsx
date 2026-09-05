import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { DataTable, type DataTableColumn } from "@/components/shared/DataTable";
import { FormShell } from "@/components/shared/FormShell";
import { LineItemsTable, type LineItemColumn } from "@/components/shared/LineItemsTable";
import { MoneyDisplay } from "@/components/shared/MoneyDisplay";
import { MoneyInput } from "@/components/shared/MoneyInput";
import { StatusBadge, type Status } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useApi } from "@/hooks/useApi";
import { api, normaliseError } from "@/lib/api";
import { toast } from "@/hooks/use-toast";
import type {
  Account,
  Journal,
  JournalEntry,
  JournalEntryListRow,
  Page,
  Partner,
} from "@/types/api";

const PAGE_SIZE = 20;
const NO_PARTNER = "none";

type DraftLine = {
  account_id: string;
  label: string;
  debit: string;
  credit: string;
};

const BLANK_LINE: DraftLine = { account_id: "", label: "", debit: "0.00", credit: "0.00" };

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

type Mode =
  | { kind: "list" }
  | { kind: "create" }
  | { kind: "view"; entryId: number };

export default function JournalEntries() {
  const [mode, setMode] = useState<Mode>({ kind: "list" });
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 400);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const query = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (search) query.set("search", search);
  const path = `/journal-entries?${query.toString()}`;

  const { data, loading, error, refetch } = useApi<Page<JournalEntryListRow>>(path, [path]);

  const columns: DataTableColumn<JournalEntryListRow>[] = [
    { key: "date", header: "Date" },
    { key: "number", header: "Number" },
    { key: "partner_name", header: "Partner", render: (row) => row.partner_name ?? "—" },
    { key: "journal_name", header: "Journal" },
    {
      key: "total_amount",
      header: "Amount",
      align: "right",
      render: (row) => <MoneyDisplay value={row.total_amount} />,
    },
    {
      key: "state",
      header: "Status",
      render: (row) => <StatusBadge status={row.state as Status} />,
    },
  ];

  if (mode.kind === "create") {
    return (
      <JournalEntryForm
        onBack={() => setMode({ kind: "list" })}
        onPosted={async () => {
          setMode({ kind: "list" });
          await refetch();
        }}
      />
    );
  }

  if (mode.kind === "view") {
    return (
      <JournalEntryView
        entryId={mode.entryId}
        onBack={() => setMode({ kind: "list" })}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-text_primary">Journal Entries</h1>
          <p className="text-sm text-text_secondary">
            The ledger. Posted entries can't be edited or deleted — reverse an entry to
            undo it.
          </p>
        </div>
        <Button type="button" onClick={() => setMode({ kind: "create" })}>
          <Plus className="mr-2 h-4 w-4" />
          New Entry
        </Button>
      </div>

      <DataTable
        columns={columns}
        rows={data?.items ?? []}
        loading={loading}
        error={error ? { message: error.message } : null}
        page={page}
        pageSize={PAGE_SIZE}
        total={data?.total ?? 0}
        onPageChange={setPage}
        onRowClick={(row) => setMode({ kind: "view", entryId: row.id })}
        searchValue={searchInput}
        onSearchChange={setSearchInput}
        onRetry={refetch}
        getRowId={(row) => row.id}
        emptyMessage="No journal entries yet — confirm an invoice or bill, or post a manual entry."
      />
    </div>
  );
}

function JournalEntryForm({
  onBack,
  onPosted,
}: {
  onBack: () => void;
  onPosted: () => void;
}) {
  const [entryDate, setEntryDate] = useState(today());
  const [journalId, setJournalId] = useState("");
  const [partnerId, setPartnerId] = useState(NO_PARTNER);
  const [reference, setReference] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([{ ...BLANK_LINE }, { ...BLANK_LINE }]);
  const [isBalanced, setIsBalanced] = useState(true);
  const [posting, setPosting] = useState(false);

  const { data: journals } = useApi<Page<Journal>>("/journals?page=1&page_size=100", []);
  const { data: accounts } = useApi<Page<Account>>("/accounts?page=1&page_size=100", []);
  const { data: partners } = useApi<Page<Partner>>("/partners?page=1&page_size=100", []);

  function updateLine(index: number, patch: Partial<DraftLine>) {
    setLines((prev) => prev.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  }

  const columns: LineItemColumn<DraftLine>[] = [
    {
      key: "account_id",
      header: "Account",
      render: (row, index) => (
        <Select
          value={row.account_id}
          onValueChange={(value) => updateLine(index, { account_id: value })}
        >
          <SelectTrigger className="min-w-[12rem]">
            <SelectValue placeholder="Select account" />
          </SelectTrigger>
          <SelectContent>
            {(accounts?.items ?? []).map((account) => (
              <SelectItem key={account.id} value={String(account.id)}>
                {account.code} — {account.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ),
    },
    {
      key: "label",
      header: "Label",
      render: (row, index) => (
        <Input
          value={row.label}
          onChange={(e) => updateLine(index, { label: e.target.value })}
          placeholder="Optional"
        />
      ),
    },
    {
      key: "debit",
      header: "Debit",
      align: "right",
      render: (row, index) => (
        <MoneyInput
          value={row.debit}
          // A line is either a debit or a credit, never both (§7.5 CHECK) —
          // typing in one side clears the other.
          onChange={(value) => updateLine(index, { debit: value, credit: "0.00" })}
        />
      ),
    },
    {
      key: "credit",
      header: "Credit",
      align: "right",
      render: (row, index) => (
        <MoneyInput
          value={row.credit}
          onChange={(value) => updateLine(index, { credit: value, debit: "0.00" })}
        />
      ),
    },
  ];

  async function handlePost() {
    setPosting(true);
    try {
      await api.post<JournalEntry>("/journal-entries", {
        entry_date: entryDate,
        journal_id: Number(journalId),
        partner_id: partnerId === NO_PARTNER ? null : Number(partnerId),
        reference: reference.trim() || null,
        lines: lines
          .filter((line) => line.account_id)
          .map((line) => ({
            account_id: Number(line.account_id),
            partner_id: null,
            label: line.label.trim() || null,
            debit: line.debit || "0.00",
            credit: line.credit || "0.00",
          })),
      });
      toast({ title: "Journal entry posted" });
      onPosted();
    } catch (e) {
      const apiError = normaliseError(e);
      toast({
        variant: "destructive",
        title: "Could not post entry",
        description: apiError.message,
      });
    } finally {
      setPosting(false);
    }
  }

  const canPost = isBalanced && !!journalId && lines.some((line) => line.account_id);

  return (
    <FormShell
      title="New Journal Entry"
      onBack={onBack}
      actions={[
        { label: "Cancel", variant: "outline", onClick: onBack },
        {
          label: posting ? "Posting..." : "Post",
          onClick: handlePost,
          disabled: !canPost || posting,
        },
      ]}
    >
      <div className="flex flex-col gap-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="entry_date">Accounting Date</Label>
            <Input
              id="entry_date"
              type="date"
              value={entryDate}
              onChange={(e) => setEntryDate(e.target.value)}
            />
          </div>

          <div>
            <Label htmlFor="journal_id">Journal</Label>
            <Select value={journalId} onValueChange={setJournalId}>
              <SelectTrigger id="journal_id">
                <SelectValue placeholder="Select journal" />
              </SelectTrigger>
              <SelectContent>
                {(journals?.items ?? []).map((journal) => (
                  <SelectItem key={journal.id} value={String(journal.id)}>
                    {journal.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label htmlFor="partner_id">Partner</Label>
            <Select value={partnerId} onValueChange={setPartnerId}>
              <SelectTrigger id="partner_id">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_PARTNER}>No partner</SelectItem>
                {(partners?.items ?? []).map((partner) => (
                  <SelectItem key={partner.id} value={String(partner.id)}>
                    {partner.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label htmlFor="reference">Reference</Label>
            <Input
              id="reference"
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              placeholder="Optional"
            />
          </div>
        </div>

        <LineItemsTable
          variant="journal_entry"
          rows={lines}
          columns={columns}
          getDebit={(row) => row.debit}
          getCredit={(row) => row.credit}
          onBalanceChange={setIsBalanced}
          addLabel="Add line"
          onAddRow={() => setLines((prev) => [...prev, { ...BLANK_LINE }])}
          onRemoveRow={(index) => setLines((prev) => prev.filter((_, i) => i !== index))}
        />

        {!isBalanced && (
          <p className="rounded border border-danger bg-danger/5 px-3 py-2 text-sm text-danger">
            Debit and credit amounts do not match. Post stays disabled until they balance.
          </p>
        )}
      </div>
    </FormShell>
  );
}

function JournalEntryView({ entryId, onBack }: { entryId: number; onBack: () => void }) {
  const path = `/journal-entries/${entryId}`;
  const { data: entry, loading, error, refetch } = useApi<JournalEntry>(path, [path]);

  if (loading) {
    return <p className="text-sm text-text_secondary">Loading entry...</p>;
  }

  if (error) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-sm text-danger">{error.message}</p>
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={refetch}>
            Retry
          </Button>
          <Button type="button" variant="ghost" onClick={onBack}>
            Back
          </Button>
        </div>
      </div>
    );
  }

  if (!entry) return null;

  return (
    <FormShell
      title={entry.number}
      onBack={onBack}
      actions={[{ label: "Back to list", variant: "outline", onClick: onBack }]}
    >
      <div className="flex flex-col gap-6">
        <dl className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-text_secondary">Date</dt>
            <dd className="text-text_primary">{entry.entry_date}</dd>
          </div>
          <div>
            <dt className="text-text_secondary">Journal</dt>
            <dd className="text-text_primary">{entry.journal_name ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-text_secondary">Partner</dt>
            <dd className="text-text_primary">{entry.partner_name ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-text_secondary">Status</dt>
            <dd>
              <StatusBadge status={entry.state as Status} />
            </dd>
          </div>
        </dl>

        <div className="overflow-hidden rounded border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Account</TableHead>
                <TableHead>Partner</TableHead>
                <TableHead>Label</TableHead>
                <TableHead className="text-right">Debit</TableHead>
                <TableHead className="text-right">Credit</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entry.lines.map((line) => (
                <TableRow key={line.id}>
                  <TableCell>{line.account_name ?? line.account_id}</TableCell>
                  <TableCell>{line.partner_name ?? "—"}</TableCell>
                  <TableCell>{line.label ?? "—"}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    <MoneyDisplay value={line.debit} />
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    <MoneyDisplay value={line.credit} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        <p className="text-xs text-text_secondary">
          Posted entries cannot be edited or deleted. To undo one, post a reversing entry.
        </p>
      </div>
    </FormShell>
  );
}
