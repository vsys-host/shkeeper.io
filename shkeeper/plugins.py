"""Optional paid feature plugins (e.g. Multishkeeper admin UI).

Plugins are discovered by package name. Set SHKEEPER_PLUGINS to a
comma-separated list (default: shkeeper_multishkeeper). Missing packages
are skipped — public core runs without them.
"""

from __future__ import annotations

import importlib
import logging
import os
from typing import Callable

logger = logging.getLogger(__name__)

DEFAULT_PLUGINS = ("shkeeper_multishkeeper",)

_loaded: dict[str, object] = {}


def configured_plugin_names() -> list[str]:
    raw = os.environ.get("SHKEEPER_PLUGINS")
    if raw is None:
        return list(DEFAULT_PLUGINS)
    return [name.strip() for name in raw.split(",") if name.strip()]


def is_loaded(name: str) -> bool:
    return name in _loaded


def has_multishkeeper() -> bool:
    return is_loaded("shkeeper_multishkeeper")


def load_plugins(app) -> dict[str, object]:
    """Import and register configured plugins. Safe if packages are absent."""
    for name in configured_plugin_names():
        if name in _loaded:
            continue
        try:
            module = importlib.import_module(name)
        except ImportError:
            logger.debug("Plugin %s not installed; skipping", name)
            continue

        register: Callable | None = getattr(module, "register", None)
        if register is None:
            logger.warning("Plugin %s has no register(app); skipping", name)
            continue

        register(app)
        _loaded[name] = module
        logger.info("Loaded plugin %s", name)

    app.extensions["shkeeper_plugins"] = dict(_loaded)

    @app.context_processor
    def inject_plugins():
        return {"has_multishkeeper": has_multishkeeper()}

    return _loaded
