"""Import every model so Base.metadata.create_all sees all tables."""

from app.models.analytic import AnalyticAccount  # noqa: F401
from app.models.partner import Partner  # noqa: F401
from app.models.product import Product, ProductCategory  # noqa: F401
from app.models.user import User  # noqa: F401
