// TS types mirroring the backend's Pydantic schemas (SPEC.md §4, §7, §9).
// Money fields come over the wire as strings (SPEC.md §9 money_wire_format) —
// never numbers — so they're typed `string` here and formatted via
// MoneyDisplay, never used in arithmetic. Confirmed against the backend:
// schemas/common.py serialises Decimal with PlainSerializer(f"{v:.2f}").
//
// Types below the "not yet on the backend" divider are written from SPEC.md §9
// because their routers don't exist yet — see SETUP_NOTES/summary.

export type UserRole = "admin" | "accountant" | "contact";
export type PartnerType = "customer" | "vendor" | "both";
export type ProductType = "goods" | "service" | "combo";

export type AccountGroup = "balance_sheet" | "profit_and_loss";
export type AccountType =
  | "asset"
  | "liability"
  | "bank"
  | "capital"
  | "cash"
  | "income"
  | "expense"
  | "other_expense";
export type JournalType = "sales" | "purchase" | "bank" | "cash";
export type JournalEntryState = "draft" | "posted" | "cancelled";
export type DocumentState = "draft" | "confirmed" | "cancelled";
export type PaymentStatus = "not_paid" | "partial" | "paid";
export type PaymentType = "send" | "receive";
export type PaymentState = "draft" | "confirmed" | "cancelled";
export type BudgetState = "draft" | "confirmed" | "revised" | "cancelled";
export type BudgetLineType = "income" | "expense";

export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type Partner = {
  id: number;
  name: string;
  email: string | null;
  phone: string | null;
  partner_type: PartnerType;
  street: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  pincode: string | null;
  is_active: boolean;
};

export type PartnerInput = {
  name: string;
  email?: string | null;
  phone?: string | null;
  partner_type: PartnerType;
  street?: string | null;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  pincode?: string | null;
};

export type ProductCategory = {
  id: number;
  name: string;
};

export type Product = {
  id: number;
  name: string;
  product_type: ProductType;
  category_id: number | null;
  sales_price: string;
  cost_price: string;
  is_active: boolean;
};

export type ProductInput = {
  name: string;
  product_type: ProductType;
  category_id?: number | null;
  sales_price: string;
  cost_price: string;
};

export type AnalyticAccount = {
  id: number;
  name: string;
  is_active: boolean;
};

export type AnalyticAccountInput = {
  name: string;
};

// --- accounting (backend routers exist: /accounts, /journals, /journal-entries) ---

export type Account = {
  id: number;
  code: string;
  name: string;
  account_group: AccountGroup;
  account_type: AccountType;
  is_archived: boolean;
};

export type AccountInput = {
  code: string;
  name: string;
  account_group: AccountGroup;
  account_type: AccountType;
};

export type Journal = {
  id: number;
  name: string;
  journal_type: JournalType;
  default_account_id: number;
};

export type JournalInput = {
  name: string;
  journal_type: JournalType;
  default_account_id: number;
};

export type JournalEntryListRow = {
  id: number;
  date: string;
  number: string;
  partner_name: string | null;
  journal_name: string;
  total_amount: string;
  state: JournalEntryState;
};

export type JournalEntryLine = {
  id: number;
  account_id: number;
  account_name: string | null;
  partner_id: number | null;
  partner_name: string | null;
  label: string | null;
  debit: string;
  credit: string;
  sequence: number;
};

export type JournalEntry = {
  id: number;
  number: string;
  entry_date: string;
  journal_id: number;
  journal_name: string | null;
  partner_id: number | null;
  partner_name: string | null;
  reference: string | null;
  state: JournalEntryState;
  source_type: string | null;
  source_id: number | null;
  total_amount: string;
  lines: JournalEntryLine[];
};

export type JournalEntryLineInput = {
  account_id: number;
  partner_id: number | null;
  label: string | null;
  debit: string;
  credit: string;
};

export type JournalEntryInput = {
  entry_date: string;
  journal_id: number;
  partner_id: number | null;
  reference: string | null;
  lines: JournalEntryLineInput[];
};

export type AppUser = {
  id: number;
  name: string;
  login_id: string;
  email: string;
  role: UserRole;
  partner_id: number | null;
  is_active: boolean;
};

export type CreateUserInput = {
  name: string;
  login_id: string;
  email: string;
  role: UserRole;
  password: string;
  confirm_password: string;
  partner_id: number | null;
};

// --- NOT YET ON THE BACKEND ------------------------------------------------
// Everything below is typed from SPEC.md §9's contract. The routers don't
// exist yet, so these pages currently render their error state against a 404.

export type DocumentLine = {
  id?: number;
  product_id: number;
  product_name?: string | null;
  account_id?: number | null;
  account_name?: string | null;
  analytic_account_id: number | null;
  analytic_account_name?: string | null;
  quantity: string;
  unit_price: string;
  line_total: string;
  sequence?: number;
};

export type DocumentLineInput = {
  product_id: number;
  account_id?: number | null;
  analytic_account_id: number | null;
  quantity: string;
  unit_price: string;
};

export type SalesOrder = {
  id: number;
  number: string;
  customer_id: number;
  customer_name: string | null;
  order_date: string;
  state: DocumentState;
  total_amount: string;
};

export type SalesOrderDetail = SalesOrder & {
  lines: DocumentLine[];
  // Non-null once this order has been converted to a customer invoice.
  invoice_id: number | null;
};

export type PurchaseOrder = {
  id: number;
  number: string;
  vendor_id: number;
  vendor_name: string | null;
  order_date: string;
  state: DocumentState;
  total_amount: string;
};

export type PurchaseOrderDetail = PurchaseOrder & {
  lines: DocumentLine[];
  // Non-null once this order has been converted to a vendor bill.
  bill_id: number | null;
};

export type CustomerInvoice = {
  id: number;
  number: string;
  customer_id: number;
  customer_name: string | null;
  invoice_reference: string | null;
  invoice_date: string;
  due_date: string | null;
  state: DocumentState;
  total_amount: string;
  amount_paid: string;
  amount_due: string;
  payment_status: PaymentStatus;
  source_so_id: number | null;
  journal_entry_id: number | null;
};

export type CustomerInvoiceDetail = CustomerInvoice & { lines: DocumentLine[] };

export type VendorBill = {
  id: number;
  number: string;
  vendor_id: number;
  vendor_name: string | null;
  bill_reference: string | null;
  bill_date: string;
  due_date: string | null;
  state: DocumentState;
  total_amount: string;
  amount_paid: string;
  amount_due: string;
  payment_status: PaymentStatus;
  source_po_id: number | null;
  journal_entry_id: number | null;
};

export type VendorBillDetail = VendorBill & { lines: DocumentLine[] };

export type Payment = {
  id: number;
  number: string;
  payment_type: PaymentType;
  partner_id: number;
  partner_name: string | null;
  journal_id: number;
  amount: string;
  payment_date: string;
  note: string | null;
  state: PaymentState;
  invoice_id: number | null;
  bill_id: number | null;
  journal_entry_id: number | null;
};

export type PaymentInput = {
  payment_type: PaymentType;
  partner_id: number;
  journal_id: number;
  amount: string;
  payment_date: string;
  note: string | null;
  invoice_id?: number | null;
  bill_id?: number | null;
};

export type BudgetLine = {
  id?: number;
  analytic_account_id: number;
  analytic_account_name?: string | null;
  line_type: BudgetLineType;
  committed_amount: string;
  achieved_amount?: string | null;
  achieved_percent?: string | null;
  amount_to_achieve?: string | null;
  sequence?: number;
};

export type Budget = {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
  responsible_id: number | null;
  responsible_name?: string | null;
  state: BudgetState;
  revision_of_id: number | null;
  revised_with_id: number | null;
};

export type BudgetDetail = Budget & { lines: BudgetLine[] };

export type BudgetInput = {
  name: string;
  start_date: string;
  end_date: string;
  responsible_id: number | null;
  lines: {
    analytic_account_id: number;
    line_type: BudgetLineType;
    committed_amount: string;
  }[];
};

export type BalanceSheetRow = {
  label: string;
  account_type: AccountType;
  balance: string;
};

export type BalanceSheet = {
  assets: BalanceSheetRow[];
  liabilities: BalanceSheetRow[];
  total_assets: string;
  total_liabilities: string;
  is_balanced: boolean;
};

export type ProfitAndLoss = {
  income: { income_from_sales: string; total_income: string };
  expenses: {
    purchase_expense: string;
    other_expense: string;
    total_expenses: string;
  };
  net_income: string;
};

export type TrialBalanceRow = {
  account_code: string;
  account_name: string;
  total_debit: string;
  total_credit: string;
};

export type TrialBalance = {
  rows: TrialBalanceRow[];
  grand_total_debit: string;
  grand_total_credit: string;
  is_balanced: boolean;
};

export type BudgetSummaryRow = {
  budget_id: number;
  budget_name: string;
  committed_amount: string;
  achieved_amount: string;
  achieved_percent: string;
};

export type DashboardStats = {
  sales: { all: number; confirmed: number; draft: number };
  purchase: { all: number; confirmed: number; draft: number };
  budget: { achieved: number; budget: number; committed: number };
};

export type PortalDocument = {
  id: number;
  document_type: "invoice" | "bill";
  number: string;
  date: string;
  total_amount: string;
  amount_due: string;
  payment_status: PaymentStatus;
  state: DocumentState;
};
