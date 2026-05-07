"""Lookup table: brokers.adapter_class string -> Python class.

When you add a new broker, write the adapter, import it here, and add it
to ``REGISTRY``. The DB row's ``adapter_class`` column then refers to it
by string name. Keeping the registry explicit (vs. auto-discovery) makes
imports predictable and avoids surprises in production.
"""
from __future__ import annotations

from typing import Type

from .adapter_base import BrokerAdapter
from .adapters.capital_com import CapitalComAdapter
from .adapters.manual import ManualAdapter


REGISTRY: dict[str, Type[BrokerAdapter]] = {
    "CapitalComAdapter": CapitalComAdapter,
    "ManualAdapter": ManualAdapter,
}


def get_adapter_class(name: str) -> Type[BrokerAdapter]:
    """Resolve adapter class by name. Raises KeyError if unknown."""
    try:
        return REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"Unknown broker adapter '{name}'. Known: {list(REGISTRY)}"
        ) from exc
