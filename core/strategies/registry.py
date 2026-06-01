"""Strategy registry.

Strategies register themselves via the `@register_strategy` class decorator:

    @register_strategy
    class MyStrategy(BaseStrategy):
        name = "my_strategy"
        ...

Once registered, callers can look up by name:

    cls = get_strategy("my_strategy")
    strat = cls(fast=10, slow=30)
"""
from __future__ import annotations

from core.strategies.base import BaseStrategy

_REGISTRY: dict[str, type[BaseStrategy]] = {}


def register_strategy(cls: type[BaseStrategy]) -> type[BaseStrategy]:
    """Class decorator. Adds the class to the registry keyed by `cls.name`."""
    if not issubclass(cls, BaseStrategy):
        raise TypeError(
            f"{cls.__name__} must inherit from BaseStrategy"
        )
    name = getattr(cls, "name", "")
    if not name:
        raise ValueError(
            f"{cls.__name__} must define a non-empty class-level `name`"
        )
    if name in _REGISTRY and _REGISTRY[name] is not cls:
        raise ValueError(
            f"Strategy name conflict: {name!r} is already registered to "
            f"{_REGISTRY[name].__name__}"
        )
    _REGISTRY[name] = cls
    return cls


def get_strategy(name: str) -> type[BaseStrategy]:
    """Return the strategy class registered under `name`."""
    if name not in _REGISTRY:
        raise KeyError(
            f"No strategy registered under {name!r}. "
            f"Available: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[name]


def list_strategies() -> list[type[BaseStrategy]]:
    """Return all registered strategy classes, sorted by name."""
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]
