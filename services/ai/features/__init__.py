"""AI features: one module per feature, each calling services.ai.register()
with its AIFeature spec. Import a new feature module here."""
from services.ai.features import weekly_words  # noqa: F401
