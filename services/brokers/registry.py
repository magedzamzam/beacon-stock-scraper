"""Adapter name -> class registry."""
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
    try:
        return REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"Unknown broker adapter '{name}'. Known: {list(REGISTRY)}") from exc
