import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { RequireAuth } from "@/components/RequireAuth";
import { AuthProvider } from "@/hooks/useAuth";
import { Toaster } from "@/components/ui/toaster";
import ComponentsPreview from "@/dev/ComponentsPreview";
import Login from "@/pages/auth/Login";
import Signup from "@/pages/auth/Signup";
import Dashboard from "@/pages/dashboard/Dashboard";
import Contacts from "@/pages/masters/Contacts";
import Products from "@/pages/masters/Products";
import Analytics from "@/pages/masters/Analytics";
import SalesOrders from "@/pages/sales/SalesOrders";
import CustomerInvoices from "@/pages/sales/CustomerInvoices";
import PurchaseOrders from "@/pages/purchase/PurchaseOrders";
import VendorBills from "@/pages/purchase/VendorBills";
import Payments from "@/pages/payments/Payments";
import ChartOfAccounts from "@/pages/accounting/ChartOfAccounts";
import Journals from "@/pages/accounting/Journals";
import JournalEntries from "@/pages/accounting/JournalEntries";
import Budgets from "@/pages/budgets/Budgets";
import BalanceSheet from "@/pages/reports/BalanceSheet";
import ProfitAndLoss from "@/pages/reports/ProfitAndLoss";
import TrialBalance from "@/pages/reports/TrialBalance";
import BudgetReport from "@/pages/reports/BudgetReport";
import MyDocuments from "@/pages/portal/MyDocuments";
import Users from "@/pages/admin/Users";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster />
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />

          {/* Temporary — not part of real navigation, and deliberately not
              behind the auth guard so anyone reviewing components doesn't
              need a login. See ComponentsPreview.tsx. */}
          <Route element={<AppShell />}>
            <Route path="/dev/components" element={<ComponentsPreview />} />
          </Route>

          <Route
            element={
              <RequireAuth>
                <AppShell />
              </RequireAuth>
            }
          >
            <Route path="/" element={<Dashboard />} />

            <Route path="/sales/orders" element={<SalesOrders />} />
            <Route path="/sales/invoices" element={<CustomerInvoices />} />
            <Route
              path="/sales/receipts"
              element={
                <Payments
                  paymentType="receive"
                  title="Receipts"
                  description="Money received from customers against confirmed invoices."
                />
              }
            />

            <Route path="/purchase/orders" element={<PurchaseOrders />} />
            <Route path="/purchase/bills" element={<VendorBills />} />
            <Route
              path="/purchase/payments"
              element={
                <Payments
                  paymentType="send"
                  title="Payments"
                  description="Money paid to vendors against confirmed bills."
                />
              }
            />

            <Route path="/masters/contacts" element={<Contacts />} />
            <Route path="/masters/products" element={<Products />} />
            <Route path="/masters/analytics" element={<Analytics />} />
            <Route path="/budgets" element={<Budgets />} />
            <Route path="/accounting/accounts" element={<ChartOfAccounts />} />
            <Route path="/accounting/journals" element={<Journals />} />
            <Route path="/accounting/journal-entries" element={<JournalEntries />} />

            <Route path="/reports/balance-sheet" element={<BalanceSheet />} />
            <Route path="/reports/profit-and-loss" element={<ProfitAndLoss />} />
            <Route path="/reports/budget" element={<BudgetReport />} />
            <Route path="/reports/trial-balance" element={<TrialBalance />} />

            <Route
              path="/portal/invoices"
              element={
                <MyDocuments
                  documentType="invoice"
                  title="My Invoices"
                  description="Invoices issued to you. Pay any that are still due."
                />
              }
            />
            <Route
              path="/portal/bills"
              element={
                <MyDocuments
                  documentType="bill"
                  title="My Bills"
                  description="Bills raised against you."
                />
              }
            />

            <Route path="/settings/users" element={<Users />} />
          </Route>

          {/* Fallback route: redirects any unrecognized path to avoid blank white screens */}
          <Route path="*" element={<Navigate to="/dev/components" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
