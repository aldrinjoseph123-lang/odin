"""AI features: one module per feature, each calling services.ai.register()
with its AIFeature spec. Import a new feature module here; the order here is
the order Settings → AI lists them."""
from services.ai.features import weekly_words  # noqa: F401,I001
from services.ai.features import raid_proposals  # noqa: F401
from services.ai.features import health_explained  # noqa: F401
from services.ai.features import portfolio_narrative  # noqa: F401
from services.ai.features import signoff_summary  # noqa: F401
from services.ai.features import customer_words  # noqa: F401
from services.ai.features import sow_plan  # noqa: F401
from services.ai.features import chase_draft  # noqa: F401
