import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";

type NavItem = { label: string; href: string };
type NavGroup = { label: string | null; items: NavItem[] };

// SPEC.md §13.3 — exact menu structure. role_visibility (hiding items per
// role) is not implemented yet: it needs auth, which doesn't exist yet.
// Every item is shown to everyone for now.
const NAV_GROUPS: NavGroup[] = [
  { label: null, items: [{ label: "Dashboard", href: "/" }] },
  {
    label: "Sales",
    items: [
      { label: "Sales Orders", href: "/sales/orders" },
      { label: "Customer Invoices", href: "/sales/invoices" },
      { label: "Receipts", href: "/sales/receipts" },
    ],
  },
  {
    label: "Purchase",
    items: [
      { label: "Purchase Orders", href: "/purchase/orders" },
      { label: "Vendor Bills", href: "/purchase/bills" },
      { label: "Payments", href: "/purchase/payments" },
    ],
  },
  {
    label: "Account",
    items: [
      { label: "Contacts", href: "/masters/contacts" },
      { label: "Products", href: "/masters/products" },
      { label: "Analytics", href: "/masters/analytics" },
      { label: "Analytic Budget", href: "/budgets" },
      { label: "Chart of Accounts", href: "/accounting/accounts" },
      { label: "Journals", href: "/accounting/journals" },
      { label: "Journal Entries", href: "/accounting/journal-entries" },
    ],
  },
  {
    label: "Report",
    items: [
      { label: "Balance Sheet", href: "/reports/balance-sheet" },
      { label: "Profit and Loss", href: "/reports/profit-and-loss" },
      { label: "Budget Report", href: "/reports/budget" },
      { label: "Trial Balance", href: "/reports/trial-balance" },
    ],
  },
];

type SidebarProps = {
  open: boolean;
  onClose: () => void;
};

export function Sidebar({ open, onClose }: SidebarProps) {
  return (
    <>
      {/* Mobile backdrop — SPEC.md §13.1: sidebar collapses to a hamburger drawer below 768px */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-text_primary/40 md:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-border bg-surface transition-transform duration-200 ease-in-out",
          "md:static md:z-auto md:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-14 shrink-0 items-center border-b border-border px-4">
          <span className="text-base font-semibold text-text_primary">
            Urban Furniture
          </span>
        </div>

        <nav className="flex-1 space-y-4 overflow-y-auto px-2 py-4">
          {NAV_GROUPS.map((group) => (
            <div key={group.label ?? "root"}>
              {group.label && (
                <p className="px-2 pb-1 text-xs font-medium uppercase tracking-wide text-text_secondary">
                  {group.label}
                </p>
              )}
              <ul className="space-y-0.5">
                {group.items.map((item) => (
                  <li key={item.href}>
                    <NavLink
                      to={item.href}
                      end={item.href === "/"}
                      onClick={onClose}
                      className={({ isActive }) =>
                        cn(
                          "block rounded-md px-2 py-1.5 text-sm font-medium transition-colors",
                          isActive
                            ? "bg-primary text-primary-foreground"
                            : "text-text_primary hover:bg-border/60",
                        )
                      }
                    >
                      {item.label}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      </aside>
    </>
  );
}
