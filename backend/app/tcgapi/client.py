"""Retired import compatibility. No network access is possible through this client."""
import logging
from app.common.catalog_identity import local_card_id, parse_release_date, split_card_number
DEFAULT_BASE_URL = "https://api.tcgapi.dev/v1"  # Historical identity; never requested.
logger = logging.getLogger(__name__)
class TCGAPIConfigurationError(RuntimeError):
    pass
class TCGAPIClient:
    def __init__(self, *args, **kwargs):
        logger.error("Retired TCGAPI client requested; use the PPT refresh service")
        raise TCGAPIConfigurationError("TCGAPI is retired; use Pokémon Price Tracker")
