"""Price mode contracts shared by data, research, backtest and execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import pandas as pd


class PriceMode(StrEnum):
    RAW = "raw"
    QFQ = "qfq"
    HFQ = "hfq"


class PriceUseCase(StrEnum):
    RESEARCH = "research"
    BACKTEST = "backtest"
    SIGNAL = "signal"
    EXECUTION = "execution"
    VALUATION = "valuation"
    DISPLAY = "display"


USE_CASE_PRICE_MODE: dict[PriceUseCase, PriceMode] = {
    PriceUseCase.RESEARCH: PriceMode.QFQ,
    PriceUseCase.BACKTEST: PriceMode.QFQ,
    PriceUseCase.SIGNAL: PriceMode.QFQ,
    PriceUseCase.EXECUTION: PriceMode.RAW,
    PriceUseCase.VALUATION: PriceMode.RAW,
    PriceUseCase.DISPLAY: PriceMode.RAW,
}


@dataclass(frozen=True)
class PriceFrameMetadata:
    requested_mode: PriceMode
    actual_mode: PriceMode
    source: str = ""
    adjustment_source: str = ""
    fallback_reason: str = ""

    @property
    def adjusted(self) -> bool:
        return self.actual_mode in {PriceMode.QFQ, PriceMode.HFQ}


def normalize_price_mode(value: str | PriceMode | None) -> PriceMode:
    if isinstance(value, PriceMode):
        return value
    text = str(value or PriceMode.QFQ.value).strip().lower()
    aliases = {
        "": PriceMode.QFQ,
        "none": PriceMode.RAW,
        "unadjusted": PriceMode.RAW,
        "no_adjust": PriceMode.RAW,
        "raw": PriceMode.RAW,
        "qfq": PriceMode.QFQ,
        "forward": PriceMode.QFQ,
        "hfq": PriceMode.HFQ,
        "backward": PriceMode.HFQ,
    }
    if text not in aliases:
        raise ValueError(f"Unsupported price mode: {value!r}")
    return aliases[text]


def normalize_price_use_case(value: str | PriceUseCase) -> PriceUseCase:
    if isinstance(value, PriceUseCase):
        return value
    try:
        return PriceUseCase(str(value).strip().lower())
    except ValueError as exc:
        raise ValueError(f"Unsupported price use case: {value!r}") from exc


def mode_for_use_case(value: str | PriceUseCase) -> PriceMode:
    return USE_CASE_PRICE_MODE[normalize_price_use_case(value)]


def attach_price_metadata(df: pd.DataFrame, metadata: PriceFrameMetadata) -> pd.DataFrame:
    df.attrs["requested_price_mode"] = metadata.requested_mode.value
    df.attrs["price_mode"] = metadata.actual_mode.value
    df.attrs["price_adjusted"] = metadata.adjusted
    df.attrs["price_source"] = metadata.source
    df.attrs["price_adjustment_source"] = metadata.adjustment_source
    df.attrs["price_fallback_reason"] = metadata.fallback_reason
    return df


def price_metadata(df: pd.DataFrame) -> PriceFrameMetadata:
    actual = normalize_price_mode(df.attrs.get("price_mode"))
    requested = normalize_price_mode(df.attrs.get("requested_price_mode", actual.value))
    return PriceFrameMetadata(
        requested_mode=requested,
        actual_mode=actual,
        source=str(df.attrs.get("price_source", "")),
        adjustment_source=str(df.attrs.get("price_adjustment_source", "")),
        fallback_reason=str(df.attrs.get("price_fallback_reason", "")),
    )


def price_attrs(metadata: PriceFrameMetadata) -> dict[str, Any]:
    return {
        "requested_price_mode": metadata.requested_mode.value,
        "price_mode": metadata.actual_mode.value,
        "price_adjusted": metadata.adjusted,
        "price_source": metadata.source,
        "price_adjustment_source": metadata.adjustment_source,
        "price_fallback_reason": metadata.fallback_reason,
    }
