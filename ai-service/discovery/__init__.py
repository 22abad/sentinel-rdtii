"""Official-source-first legal discovery package."""

from .schemas import (
    DiscoverySearchRequest,
    DiscoverySearchResponse,
    LegalCandidate,
    LegalSourceConfig,
    RawSearchHit,
)
from .service import DiscoveryService

__all__ = [
    "DiscoverySearchRequest",
    "DiscoverySearchResponse",
    "DiscoveryService",
    "LegalCandidate",
    "LegalSourceConfig",
    "RawSearchHit",
]
