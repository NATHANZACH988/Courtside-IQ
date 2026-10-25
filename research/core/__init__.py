"""Shared research primitives for sport-specific adapters; no production scoring authority."""

from .evidence import (
    EvidenceLedger,
    Event,
    MarketQuote,
    Observation,
    PregameSnapshot,
    SourceProof,
    SPORT_MARKETS,
)

__all__ = [
    "EvidenceLedger",
    "Event",
    "MarketQuote",
    "Observation",
    "PregameSnapshot",
    "SourceProof",
    "SPORT_MARKETS",
]
