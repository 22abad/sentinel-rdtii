from __future__ import annotations

from providers import get_provider


def configured_provider(provider: str | None = None, model: str | None = None):
    """Return the requested provider or the app default provider."""
    if provider:
        return get_provider(provider, model=model)

    import main as main_module

    return main_module._get_provider()
