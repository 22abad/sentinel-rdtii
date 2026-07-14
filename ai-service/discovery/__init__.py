"""Official-source-first legal discovery package."""

from .schemas import (
    DiscoverySearchRequest,
    DiscoverySearchResponse,
    LegalCandidate,
    LegalSourceConfig,
    RawSearchHit,
)
from .service import DiscoveryService, StrictLiveDiscoveryError

__all__ = [
    "DiscoverySearchRequest",
    "DiscoverySearchResponse",
    "DiscoveryService",
    "StrictLiveDiscoveryError",
    "LegalCandidate",
    "LegalSourceConfig",
    "RawSearchHit",
]
