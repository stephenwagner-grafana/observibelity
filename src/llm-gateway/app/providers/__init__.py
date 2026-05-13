"""Provider plugins for the llm-gateway.

Discovery is driven by the `observibelity.providers` entry-point group declared
in pyproject.toml. `discover_providers()` instantiates one of each plugin and
returns them keyed by name. The same pattern is used by deploy-doctor's
provider registry (see tools/deploy_doctor/providers/__init__.py).
"""
from __future__ import annotations

import logging
from importlib.metadata import entry_points

from .base import CompleteRequest, CompleteResponse, Provider

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "observibelity.providers"


def discover_providers(configs: dict[str, dict] | None = None) -> dict[str, Provider]:
    """Load every registered provider plugin.

    Args:
        configs: Optional per-provider config mapping (e.g. {"anthropic": {"model": "..."}}).

    Returns:
        Dict of provider-name -> instantiated Provider. Plugins that fail to import or
        construct are logged and skipped rather than failing the whole gateway, so a
        misconfigured Ollama doesn't take down the Anthropic path.
    """
    configs = configs or {}
    providers: dict[str, Provider] = {}

    try:
        eps = entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:
        # importlib.metadata < 3.10 returns dict-like; use getter form.
        eps = entry_points().get(ENTRY_POINT_GROUP, [])  # type: ignore[assignment]

    for ep in eps:
        try:
            cls = ep.load()
            instance = cls(config=configs.get(ep.name))
            providers[ep.name] = instance
            log.info("loaded provider plugin: %s -> %s", ep.name, cls.__name__)
        except Exception as exc:  # noqa: BLE001 — keep gateway up even if one plugin fails.
            log.warning("failed to load provider %s: %s", ep.name, exc)

    return providers


__all__ = [
    "CompleteRequest",
    "CompleteResponse",
    "Provider",
    "discover_providers",
]
