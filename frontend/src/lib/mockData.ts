import type {
  Account,
  AnalyticAccount,
  AppUser,
  BalanceSheet,
  Budget,
  BudgetDetail,
  BudgetSummaryRow,
  CustomerInvoice,
  CustomerInvoiceDetail,
  DashboardStats,
  Journal,
  JournalEntry,
  JournalEntryListRow,
  Page,
  Partner,
  Payment,
  Product,
  ProductCategory,
  ProfitAndLoss,
  PurchaseOrder,
  PurchaseOrderDetail,
  SalesOrder,
  SalesOrderDetail,
  TrialBalance,
  VendorBill,
  VendorBillDetail,
} from "@/types/api";

function paginate<T>(items: T[], page = 1, pageSize = 20): Page<T> {
  return {
    items,
    total: items.length,
    page,
    page_size: pageSize,
  };
}

export const MOCK_DASHBOARD_STATS: DashboardStats = {
  sales: { all: 15, confirmed: 11, draft: 4 },
  purchase: { all: 9, confirmed: 7, draft: 2 },
  budget: { achieved: 188000, budget: 245000, committed: 210000 },
};

export const MOCK_PARTNERS: Partner[] = [
  {
    id: 1,
    name: "Sharma Luxury Living",
    email: "rahul@sharmaliving.com",
    phone: "+91 98200 12345",
    partner_type: "customer",
    street: "14 Linking Road, Bandra",
    city: "Mumbai",
    state: "Maharashtra",
    country: "India",
    pincode: "400050",
    is_active: true,
  },
  {
    id: 2,
    name: "Aura Home Furnishings",
    email: "contact@aurahome.in",
    phone: "+91 99301 54321",
    partner_type: "customer",
    street: "5th Block, Koramangala",
    city: "Bengaluru",
    state: "Karnataka",
    country: "India",
    pincode: "560034",
    is_active: true,
  },
  {
    id: 3,
    name: "Heritage Teak & Lumber Co.",
    email: "orders@heritageteak.com",
    phone: "+91 94470 98765",
    partner_type: "vendor",
    street: "Timber Yard, Industrial Estate",
    city: "Kochi",
    state: "Kerala",
    country: "India",
    pincode: "682020",
    is_active: true,
  },
  {
    id: 4,
    name: "Apex Hardware & Fittings",
    email: "sales@apexhardware.com",
    phone: "+91 98111 23456",
    partner_type: "vendor",
    street: "GIDC Industrial Zone",
    city: "Ahmedabad",
    state: "Gujarat",
    country: "India",
    pincode: "380015",
    is_active: true,
  },
  {
    id: 5,
    name: "Metro Interior Studio",
    email: "accounts@metrointeriors.in",
    phone: "+91 98710 44556",
    partner_type: "both",
    street: "Connaught Place, Outer Circle",
    city: "New Delhi",
    state: "Delhi",
    country: "India",
    pincode: "110001",
    is_active: true,
  },
];

export const MOCK_PRODUCT_CATEGORIES: ProductCategory[] = [
  { id: 1, name: "Chairs & Seating" },
  { id: 2, name: "Dining & Tables" },
  { id: 3, name: "Sofas & Couches" },
  { id: 4, name: "Storage & Wardrobes" },
  { id: 5, name: "Interior Services" },
];

export const MOCK_PRODUCTS: Product[] = [
  {
    id: 1,
    name: "Ergonomic Mesh Office Chair",
    product_type: "goods",
    category_id: 1,
    sales_price: "4500.00",
    cost_price: "2600.00",
    is_active: true,
  },
  {
    id: 2,
    name: "Solid Sheesham Dining Table (6-Seater)",
    product_type: "goods",
    category_id: 2,
    sales_price: "24000.00",
    cost_price: "15000.00",
    is_active: true,
  },
  {
    id: 3,
    name: "Velvet 3-Seater Chesterfield Sofa",
    product_type: "goods",
    category_id: 3,
    sales_price: "38500.00",
    cost_price: "22000.00",
    is_active: true,
  },
  {
    id: 4,
    name: "Teakwood Coffee Table with Glass Top",
    product_type: "goods",
    category_id: 2,
    sales_price: "7800.00",
    cost_price: "4300.00",
    is_active: true,
  },
  {
    id: 5,
    name: "On-site Furniture Assembly & Installation",
    product_type: "service",
    category_id: 5,
    sales_price: "1500.00",
    cost_price: "600.00",
    is_active: true,
  },
];

export const MOCK_ANALYTICS: AnalyticAccount[] = [
  { id: 1, name: "Main Retail Showroom", is_active: true },
  { id: 2, name: "B2B Corporate Projects", is_active: true },
  { id: 3, name: "Custom Woodworking Workshop", is_active: true },
];

export const MOCK_ACCOUNTS: Account[] = [
  {
    id: 1,
    code: "1000",
    name: "HDFC Bank Operating A/c",
    account_group: "balance_sheet",
    account_type: "bank",
    is_archived: false,
  },
  {
    id: 2,
    code: "1010",
    name: "Showroom Cash Drawer",
    account_group: "balance_sheet",
    account_type: "cash",
    is_archived: false,
  },
  {
    id: 3,
    code: "1100",
    name: "Trade Debtors (Accounts Receivable)",
    account_group: "balance_sheet",
    account_type: "asset",
    is_archived: false,
  },
  {
    id: 4,
    code: "1200",
    name: "Finished Furniture Inventory",
    account_group: "balance_sheet",
    account_type: "asset",
    is_archived: false,
  },
  {
    id: 5,
    code: "2000",
    name: "Trade Creditors (Accounts Payable)",
    account_group: "balance_sheet",
    account_type: "liability",
    is_archived: false,
  },
  {
    id: 6,
    code: "3000",
    name: "Share Capital & Retained Earnings",
    account_group: "balance_sheet",
    account_type: "capital",
    is_archived: false,
  },
  {
    id: 7,
    code: "4000",
    name: "Furniture Sales Revenue",
    account_group: "profit_and_loss",
    account_type: "income",
    is_archived: false,
  },
  {
    id: 8,
    code: "5000",
    name: "Direct Raw Material & Purchase Cost",
    account_group: "profit_and_loss",
    account_type: "expense",
    is_archived: false,
  },
  {
    id: 9,
    code: "5100",
    name: "Workshop & Showroom Operations",
    account_group: "profit_and_loss",
    account_type: "other_expense",
    is_archived: false,
  },
];

export const MOCK_JOURNALS: Journal[] = [
  { id: 1, name: "Customer Invoices", journal_type: "sales", default_account_id: 7 },
  { id: 2, name: "Vendor Bills", journal_type: "purchase", default_account_id: 8 },
  { id: 3, name: "HDFC Bank Journal", journal_type: "bank", default_account_id: 1 },
  { id: 4, name: "Cash Register Journal", journal_type: "cash", default_account_id: 2 },
];

export const MOCK_SALES_ORDERS: SalesOrder[] = [
  {
    id: 1,
    number: "SO-2026-001",
    customer_id: 1,
    customer_name: "Sharma Luxury Living",
    order_date: "2026-09-01",
    state: "confirmed",
    total_amount: "42500.00",
  },
  {
    id: 2,
    number: "SO-2026-002",
    customer_id: 2,
    customer_name: "Aura Home Furnishings",
    order_date: "2026-09-03",
    state: "confirmed",
    total_amount: "38500.00",
  },
  {
    id: 3,
    number: "SO-2026-003",
    customer_id: 5,
    customer_name: "Metro Interior Studio",
    order_date: "2026-09-04",
    state: "draft",
    total_amount: "15300.00",
  },
];

export const MOCK_SALES_ORDER_DETAILS: Record<number, SalesOrderDetail> = {
  1: {
    ...MOCK_SALES_ORDERS[0],
    lines: [
      {
        id: 1,
        product_id: 2,
        product_name: "Solid Sheesham Dining Table (6-Seater)",
        analytic_account_id: 1,
        analytic_account_name: "Main Retail Showroom",
        quantity: "1",
        unit_price: "24000.00",
        line_total: "24000.00",
      },
      {
        id: 2,
        product_id: 1,
        product_name: "Ergonomic Mesh Office Chair",
        analytic_account_id: 1,
        analytic_account_name: "Main Retail Showroom",
        quantity: "4",
        unit_price: "4250.00",
        line_total: "17000.00",
      },
      {
        id: 3,
        product_id: 5,
        product_name: "On-site Furniture Assembly & Installation",
        analytic_account_id: 1,
        analytic_account_name: "Main Retail Showroom",
        quantity: "1",
        unit_price: "1500.00",
        line_total: "1500.00",
      },
    ],
  },
  2: {
    ...MOCK_SALES_ORDERS[1],
    lines: [
      {
        id: 4,
        product_id: 3,
        product_name: "Velvet 3-Seater Chesterfield Sofa",
        analytic_account_id: 1,
        analytic_account_name: "Main Retail Showroom",
        quantity: "1",
        unit_price: "38500.00",
        line_total: "38500.00",
      },
    ],
  },
  3: {
    ...MOCK_SALES_ORDERS[2],
    lines: [
      {
        id: 5,
        product_id: 4,
        product_name: "Teakwood Coffee Table with Glass Top",
        analytic_account_id: 2,
        analytic_account_name: "B2B Corporate Projects",
        quantity: "2",
        unit_price: "7650.00",
        line_total: "15300.00",
      },
    ],
  },
};

export const MOCK_CUSTOMER_INVOICES: CustomerInvoice[] = [
  {
    id: 1,
    number: "INV-2026-001",
    customer_id: 1,
    customer_name: "Sharma Luxury Living",
    invoice_reference: "SO-2026-001",
    invoice_date: "2026-09-02",
    due_date: "2026-09-17",
    state: "confirmed",
    total_amount: "42500.00",
    amount_paid: "25000.00",
    amount_due: "17500.00",
    payment_status: "partial",
    source_so_id: 1,
    journal_entry_id: 101,
  },
  {
    id: 2,
    number: "INV-2026-002",
    customer_id: 2,
    customer_name: "Aura Home Furnishings",
    invoice_reference: "SO-2026-002",
    invoice_date: "2026-09-03",
    due_date: "2026-09-18",
    state: "confirmed",
    total_amount: "38500.00",
    amount_paid: "38500.00",
    amount_due: "0.00",
    payment_status: "paid",
    source_so_id: 2,
    journal_entry_id: 102,
  },
];

export const MOCK_CUSTOMER_INVOICE_DETAILS: Record<number, CustomerInvoiceDetail> = {
  1: {
    ...MOCK_CUSTOMER_INVOICES[0],
    lines: [
      {
        id: 1,
        product_id: 2,
        product_name: "Solid Sheesham Dining Table (6-Seater)",
        account_id: 7,
        account_name: "4000 Furniture Sales Revenue",
        analytic_account_id: 1,
        quantity: "1",
        unit_price: "24000.00",
        line_total: "24000.00",
      },
      {
        id: 2,
        product_id: 1,
        product_name: "Ergonomic Mesh Office Chair",
        account_id: 7,
        account_name: "4000 Furniture Sales Revenue",
        analytic_account_id: 1,
        quantity: "4",
        unit_price: "4250.00",
        line_total: "17000.00",
      },
      {
        id: 3,
        product_id: 5,
        product_name: "On-site Furniture Assembly & Installation",
        account_id: 7,
        account_name: "4000 Furniture Sales Revenue",
        analytic_account_id: 1,
        quantity: "1",
        unit_price: "1500.00",
        line_total: "1500.00",
      },
    ],
  },
  2: {
    ...MOCK_CUSTOMER_INVOICES[1],
    lines: [
      {
        id: 4,
        product_id: 3,
        product_name: "Velvet 3-Seater Chesterfield Sofa",
        account_id: 7,
        account_name: "4000 Furniture Sales Revenue",
        analytic_account_id: 1,
        quantity: "1",
        unit_price: "38500.00",
        line_total: "38500.00",
      },
    ],
  },
};

export const MOCK_PURCHASE_ORDERS: PurchaseOrder[] = [
  {
    id: 1,
    number: "PO-2026-001",
    vendor_id: 3,
    vendor_name: "Heritage Teak & Lumber Co.",
    order_date: "2026-08-25",
    state: "confirmed",
    total_amount: "45000.00",
  },
  {
    id: 2,
    number: "PO-2026-002",
    vendor_id: 4,
    vendor_name: "Apex Hardware & Fittings",
    order_date: "2026-08-28",
    state: "confirmed",
    total_amount: "12800.00",
  },
];

export const MOCK_PURCHASE_ORDER_DETAILS: Record<number, PurchaseOrderDetail> = {
  1: {
    ...MOCK_PURCHASE_ORDERS[0],
    lines: [
      {
        id: 1,
        product_id: 2,
        product_name: "Kiln-dried Teak Timber Planks (500 sq ft)",
        analytic_account_id: 3,
        analytic_account_name: "Custom Woodworking Workshop",
        quantity: "500",
        unit_price: "90.00",
        line_total: "45000.00",
      },
    ],
  },
  2: {
    ...MOCK_PURCHASE_ORDERS[1],
    lines: [
      {
        id: 2,
        product_id: 4,
        product_name: "Heavy-duty Telescopic Drawer Slides & Handles",
        analytic_account_id: 3,
        analytic_account_name: "Custom Woodworking Workshop",
        quantity: "80",
        unit_price: "160.00",
        line_total: "12800.00",
      },
    ],
  },
};

export const MOCK_VENDOR_BILLS: VendorBill[] = [
  {
    id: 1,
    number: "BILL-2026-001",
    vendor_id: 3,
    vendor_name: "Heritage Teak & Lumber Co.",
    bill_reference: "HT-9842",
    bill_date: "2026-08-27",
    due_date: "2026-09-10",
    state: "confirmed",
    total_amount: "45000.00",
    amount_paid: "45000.00",
    amount_due: "0.00",
    payment_status: "paid",
    source_po_id: 1,
    journal_entry_id: 103,
  },
  {
    id: 2,
    number: "BILL-2026-002",
    vendor_id: 4,
    vendor_name: "Apex Hardware & Fittings",
    bill_reference: "APX-3310",
    bill_date: "2026-08-30",
    due_date: "2026-09-14",
    state: "confirmed",
    total_amount: "12800.00",
    amount_paid: "0.00",
    amount_due: "12800.00",
    payment_status: "not_paid",
    source_po_id: 2,
    journal_entry_id: 104,
  },
];

export const MOCK_VENDOR_BILL_DETAILS: Record<number, VendorBillDetail> = {
  1: {
    ...MOCK_VENDOR_BILLS[0],
    lines: [
      {
        id: 1,
        product_id: 2,
        product_name: "Kiln-dried Teak Timber Planks (500 sq ft)",
        account_id: 8,
        account_name: "5000 Direct Raw Material & Purchase Cost",
        analytic_account_id: 3,
        quantity: "500",
        unit_price: "90.00",
        line_total: "45000.00",
      },
    ],
  },
  2: {
    ...MOCK_VENDOR_BILLS[1],
    lines: [
      {
        id: 2,
        product_id: 4,
        product_name: "Heavy-duty Telescopic Drawer Slides & Handles",
        account_id: 8,
        account_name: "5000 Direct Raw Material & Purchase Cost",
        analytic_account_id: 3,
        quantity: "80",
        unit_price: "160.00",
        line_total: "12800.00",
      },
    ],
  },
};

export const MOCK_PAYMENTS: Payment[] = [
  {
    id: 1,
    number: "REC-2026-001",
    payment_type: "receive",
    partner_id: 1,
    partner_name: "Sharma Luxury Living",
    journal_id: 3,
    amount: "25000.00",
    payment_date: "2026-09-03",
    note: "Part payment for Dining Table SO-001",
    state: "confirmed",
    invoice_id: 1,
    bill_id: null,
    journal_entry_id: 105,
  },
  {
    id: 2,
    number: "REC-2026-002",
    payment_type: "receive",
    partner_id: 2,
    partner_name: "Aura Home Furnishings",
    journal_id: 3,
    amount: "38500.00",
    payment_date: "2026-09-04",
    note: "Full settlement for Chesterfield Sofa",
    state: "confirmed",
    invoice_id: 2,
    bill_id: null,
    journal_entry_id: 106,
  },
  {
    id: 3,
    number: "PAY-2026-001",
    payment_type: "send",
    partner_id: 3,
    partner_name: "Heritage Teak & Lumber Co.",
    journal_id: 3,
    amount: "45000.00",
    payment_date: "2026-08-30",
    note: "Lumber batch payment BILL-001",
    state: "confirmed",
    invoice_id: null,
    bill_id: 1,
    journal_entry_id: 107,
  },
];

export const MOCK_JOURNAL_ENTRIES_ROWS: JournalEntryListRow[] = [
  {
    id: 101,
    date: "2026-09-02",
    number: "JE-2026-001",
    partner_name: "Sharma Luxury Living",
    journal_name: "Customer Invoices",
    total_amount: "42500.00",
    state: "posted",
  },
  {
    id: 102,
    date: "2026-09-03",
    number: "JE-2026-002",
    partner_name: "Aura Home Furnishings",
    journal_name: "Customer Invoices",
    total_amount: "38500.00",
    state: "posted",
  },
  {
    id: 103,
    date: "2026-08-27",
    number: "JE-2026-003",
    partner_name: "Heritage Teak & Lumber Co.",
    journal_name: "Vendor Bills",
    total_amount: "45000.00",
    state: "posted",
  },
  {
    id: 104,
    date: "2026-08-30",
    number: "JE-2026-004",
    partner_name: "Apex Hardware & Fittings",
    journal_name: "Vendor Bills",
    total_amount: "12800.00",
    state: "posted",
  },
];

export const MOCK_JOURNAL_ENTRY_DETAILS: Record<number, JournalEntry> = {
  101: {
    id: 101,
    number: "JE-2026-001",
    entry_date: "2026-09-02",
    journal_id: 1,
    journal_name: "Customer Invoices",
    partner_id: 1,
    partner_name: "Sharma Luxury Living",
    reference: "INV-2026-001",
    state: "posted",
    source_type: "invoice",
    source_id: 1,
    total_amount: "42500.00",
    lines: [
      {
        id: 1,
        account_id: 3,
        account_name: "1100 Trade Debtors",
        partner_id: 1,
        partner_name: "Sharma Luxury Living",
        label: "Invoice INV-2026-001 receivable",
        debit: "42500.00",
        credit: "0.00",
        sequence: 1,
      },
      {
        id: 2,
        account_id: 7,
        account_name: "4000 Furniture Sales Revenue",
        partner_id: null,
        partner_name: null,
        label: "Sales income",
        debit: "0.00",
        credit: "42500.00",
        sequence: 2,
      },
    ],
  },
};

export const MOCK_BUDGETS: Budget[] = [
  {
    id: 1,
    name: "FY26 Q3 Showroom Sales & Production",
    start_date: "2026-07-01",
    end_date: "2026-09-30",
    responsible_id: 1,
    responsible_name: "Demo Admin",
    state: "confirmed",
    revision_of_id: null,
    revised_with_id: null,
  },
  {
    id: 2,
    name: "FY26 Q2 Workshop Expansion & Tools",
    start_date: "2026-04-01",
    end_date: "2026-06-30",
    responsible_id: 1,
    responsible_name: "Demo Admin",
    state: "confirmed",
    revision_of_id: null,
    revised_with_id: null,
  },
];

export const MOCK_BUDGET_DETAILS: Record<number, BudgetDetail> = {
  1: {
    ...MOCK_BUDGETS[0],
    lines: [
      {
        id: 1,
        analytic_account_id: 1,
        analytic_account_name: "Main Retail Showroom",
        line_type: "income",
        committed_amount: "150000.00",
        achieved_amount: "112000.00",
        achieved_percent: "74.67",
        amount_to_achieve: "38000.00",
      },
      {
        id: 2,
        analytic_account_id: 3,
        analytic_account_name: "Custom Woodworking Workshop",
        line_type: "expense",
        committed_amount: "60000.00",
        achieved_amount: "48000.00",
        achieved_percent: "80.00",
        amount_to_achieve: "12000.00",
      },
    ],
  },
  2: {
    ...MOCK_BUDGETS[1],
    lines: [
      {
        id: 3,
        analytic_account_id: 3,
        analytic_account_name: "Custom Woodworking Workshop",
        line_type: "expense",
        committed_amount: "40000.00",
        achieved_amount: "38000.00",
        achieved_percent: "95.00",
        amount_to_achieve: "2000.00",
      },
    ],
  },
};

export const MOCK_BUDGET_SUMMARIES: BudgetSummaryRow[] = [
  {
    budget_id: 1,
    budget_name: "FY26 Q3 Showroom Sales & Production",
    committed_amount: "210000.00",
    achieved_amount: "160000.00",
    achieved_percent: "76.19",
  },
  {
    budget_id: 2,
    budget_name: "FY26 Q2 Workshop Expansion & Tools",
    committed_amount: "40000.00",
    achieved_amount: "38000.00",
    achieved_percent: "95.00",
  },
];

export const MOCK_BALANCE_SHEET: BalanceSheet = {
  assets: [
    { label: "HDFC Bank Operating Account", account_type: "bank", balance: "108500.00" },
    { label: "Showroom Petty Cash Drawer", account_type: "cash", balance: "6200.00" },
    { label: "Trade Debtors (Receivables)", account_type: "asset", balance: "17500.00" },
    { label: "Finished Furniture Inventory", account_type: "asset", balance: "94000.00" },
  ],
  liabilities: [
    { label: "Trade Creditors (Payables)", account_type: "liability", balance: "12800.00" },
    { label: "Owner Capital & Accumulated Profit", account_type: "capital", balance: "213400.00" },
  ],
  total_assets: "226200.00",
  total_liabilities: "226200.00",
  is_balanced: true,
};

export const MOCK_PROFIT_AND_LOSS: ProfitAndLoss = {
  income: {
    income_from_sales: "81000.00",
    total_income: "81000.00",
  },
  expenses: {
    purchase_expense: "57800.00",
    other_expense: "8400.00",
    total_expenses: "66200.00",
  },
  net_income: "14800.00",
};

export const MOCK_TRIAL_BALANCE: TrialBalance = {
  rows: [
    { account_code: "1000", account_name: "HDFC Bank Operating A/c", total_debit: "108500.00", total_credit: "0.00" },
    { account_code: "1010", account_name: "Showroom Cash Drawer", total_debit: "6200.00", total_credit: "0.00" },
    { account_code: "1100", account_name: "Trade Debtors (Receivables)", total_debit: "17500.00", total_credit: "0.00" },
    { account_code: "1200", account_name: "Finished Furniture Inventory", total_debit: "94000.00", total_credit: "0.00" },
    { account_code: "2000", account_name: "Trade Creditors (Payables)", total_debit: "0.00", total_credit: "12800.00" },
    { account_code: "3000", account_name: "Share Capital & Retained Earnings", total_debit: "0.00", total_credit: "213400.00" },
  ],
  grand_total_debit: "226200.00",
  grand_total_credit: "226200.00",
  is_balanced: true,
};

export const MOCK_USERS: AppUser[] = [
  {
    id: 1,
    name: "Demo Admin",
    login_id: "admin",
    email: "admin@urbanfurniture.com",
    role: "admin",
    partner_id: null,
    is_active: true,
  },
  {
    id: 2,
    name: "Sunita Verma",
    login_id: "accountant",
    email: "accounts@urbanfurniture.com",
    role: "accountant",
    partner_id: null,
    is_active: true,
  },
];

/**
 * Route dispatcher for GET requests in Demo Mode
 */
export function getMockResponse<T>(path: string): T | undefined {
  const url = path.startsWith("/") ? path : `/${path}`;
  const base = url.split("?")[0];

  if (base.includes("__none__")) {
    return null as unknown as T;
  }

  if (base === "/dashboard") {
    return MOCK_DASHBOARD_STATS as unknown as T;
  }

  // Masters
  if (base === "/partners") {
    return paginate(MOCK_PARTNERS) as unknown as T;
  }
  if (base === "/products") {
    return paginate(MOCK_PRODUCTS) as unknown as T;
  }
  if (base === "/product-categories") {
    return MOCK_PRODUCT_CATEGORIES as unknown as T;
  }
  if (base === "/analytic-accounts") {
    return paginate(MOCK_ANALYTICS) as unknown as T;
  }

  // Accounting
  if (base === "/accounts") {
    return paginate(MOCK_ACCOUNTS) as unknown as T;
  }
  if (base === "/journals") {
    return paginate(MOCK_JOURNALS) as unknown as T;
  }
  if (base === "/journal-entries") {
    return paginate(MOCK_JOURNAL_ENTRIES_ROWS) as unknown as T;
  }
  const jeMatch = base.match(/^\/journal-entries\/(\d+)$/);
  if (jeMatch) {
    const id = Number(jeMatch[1]);
    return (MOCK_JOURNAL_ENTRY_DETAILS[id] ?? MOCK_JOURNAL_ENTRY_DETAILS[101]) as unknown as T;
  }

  // Sales
  if (base === "/sales-orders") {
    return paginate(MOCK_SALES_ORDERS) as unknown as T;
  }
  const soMatch = base.match(/^\/sales-orders\/(\d+)$/);
  if (soMatch) {
    const id = Number(soMatch[1]);
    return (MOCK_SALES_ORDER_DETAILS[id] ?? MOCK_SALES_ORDER_DETAILS[1]) as unknown as T;
  }

  if (base === "/customer-invoices") {
    return paginate(MOCK_CUSTOMER_INVOICES) as unknown as T;
  }
  const invMatch = base.match(/^\/customer-invoices\/(\d+)$/);
  if (invMatch) {
    const id = Number(invMatch[1]);
    return (MOCK_CUSTOMER_INVOICE_DETAILS[id] ?? MOCK_CUSTOMER_INVOICE_DETAILS[1]) as unknown as T;
  }

  // Purchase
  if (base === "/purchase-orders") {
    return paginate(MOCK_PURCHASE_ORDERS) as unknown as T;
  }
  const poMatch = base.match(/^\/purchase-orders\/(\d+)$/);
  if (poMatch) {
    const id = Number(poMatch[1]);
    return (MOCK_PURCHASE_ORDER_DETAILS[id] ?? MOCK_PURCHASE_ORDER_DETAILS[1]) as unknown as T;
  }

  if (base === "/vendor-bills") {
    return paginate(MOCK_VENDOR_BILLS) as unknown as T;
  }
  const billMatch = base.match(/^\/vendor-bills\/(\d+)$/);
  if (billMatch) {
    const id = Number(billMatch[1]);
    return (MOCK_VENDOR_BILL_DETAILS[id] ?? MOCK_VENDOR_BILL_DETAILS[1]) as unknown as T;
  }

  // Payments & Receipts
  if (base === "/payments") {
    return paginate(MOCK_PAYMENTS) as unknown as T;
  }

  // Budgets
  if (base === "/budgets") {
    return paginate(MOCK_BUDGETS) as unknown as T;
  }
  const budgetMatch = base.match(/^\/budgets\/(\d+)$/);
  if (budgetMatch) {
    const id = Number(budgetMatch[1]);
    return (MOCK_BUDGET_DETAILS[id] ?? MOCK_BUDGET_DETAILS[1]) as unknown as T;
  }

  // Reports
  if (base === "/reports/balance-sheet") {
    return MOCK_BALANCE_SHEET as unknown as T;
  }
  if (base === "/reports/profit-and-loss") {
    return MOCK_PROFIT_AND_LOSS as unknown as T;
  }
  if (base === "/reports/trial-balance") {
    return MOCK_TRIAL_BALANCE as unknown as T;
  }
  if (base === "/reports/budget") {
    return paginate(MOCK_BUDGET_SUMMARIES) as unknown as T;
  }

  // Users
  if (base === "/users") {
    return paginate(MOCK_USERS) as unknown as T;
  }

  return undefined;
}
