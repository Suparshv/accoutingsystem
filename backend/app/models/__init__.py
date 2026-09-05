"""Model package. Importing a model here is what registers it with Base.metadata
so init_db()'s create_all can see it. Add one line per model module.
"""

from app.models.account import Account, Journal  # noqa: F401
from app.models.journal_entry import JournalEntry, JournalEntryLine  # noqa: F401
from app.models.sequence import Sequence  # noqa: F401
"""Import every model so Base.metadata.create_all sees all tables."""

from app.models.analytic import AnalyticAccount  # noqa: F401
from app.models.partner import Partner  # noqa: F401
from app.models.product import Product, ProductCategory  # noqa: F401
from app.models.user import User  # noqa: F401
