"""Model package.

Importing a model here is what registers it with Base.metadata, so
init_db()'s create_all can see every table. Add one line per model module.
"""

from app.models.account import Account, Journal  # noqa: F401
from app.models.analytic import AnalyticAccount  # noqa: F401
from app.models.budget import Budget, BudgetLine  # noqa: F401
from app.models.journal_entry import JournalEntry, JournalEntryLine  # noqa: F401
from app.models.partner import Partner  # noqa: F401
from app.models.payment import Payment  # noqa: F401
from app.models.product import Product, ProductCategory  # noqa: F401
from app.models.purchase import (  # noqa: F401
    PurchaseOrder,
    PurchaseOrderLine,
    VendorBill,
    VendorBillLine,
)
from app.models.sales import (  # noqa: F401
    CustomerInvoice,
    CustomerInvoiceLine,
    SalesOrder,
    SalesOrderLine,
)
from app.models.sequence import Sequence  # noqa: F401
from app.models.user import User  # noqa: F401
