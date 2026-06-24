"""PaperBroker state snapshot and position access helpers."""
from __future__ import annotations

from data.market.assets.contracts import instrument_key
from broker.models import Position
from broker.state import PaperBrokerState


class PaperStateMixin:
    @classmethod
    def from_state(cls, state: PaperBrokerState, **kwargs):
        """Create a PaperBroker from a persisted state snapshot."""
        kwargs.setdefault("initial_cash", state.cash)
        broker = cls(**kwargs)
        broker.restore_state(state)
        return broker

    def restore_state(self, state: PaperBrokerState) -> None:
        """Restore account state without exposing private fields to callers."""
        self._cash = float(state.cash)
        self._frozen_cash = float(state.frozen_cash)
        self._peak_equity = float(state.peak_equity)
        self._order_counter = int(state.order_counter)
        self._positions = {}
        for code, data in (state.positions or {}).items():
            self._positions[str(code)] = Position(
                code=str(code),
                name=str(data.get("name", "")),
                volume=int(data.get("volume", 0)),
                avg_cost=float(data.get("avg_cost", 0.0)),
                current_price=float(data.get("current_price", 0.0)),
                asset_type=str(data.get("asset_type", "stock") or "stock"),
            )
        self._today_sells = {}
        self._today_buys = {}

    def snapshot_state(self) -> PaperBrokerState:
        """Return a serializable snapshot of current account state."""
        return PaperBrokerState(
            cash=self._cash,
            frozen_cash=self._frozen_cash,
            peak_equity=self._peak_equity,
            positions={
                code: {
                    "volume": p.volume,
                    "avg_cost": p.avg_cost,
                    "name": p.name or "",
                    "current_price": p.current_price,
                    "asset_type": p.asset_type,
                }
                for code, p in self._positions.items()
                if p.volume > 0
            },
            order_counter=self._order_counter,
        )

    def get_position(self, code: str, asset_type: str = "stock") -> Position | None:
        """Return a single open position by code, if present."""
        pos = self._positions.get(instrument_key(asset_type, code))
        if pos is None and asset_type == "stock":
            pos = self._positions.get(code)
        if pos is None or pos.volume <= 0:
            return None
        return pos

    def get_position_codes(self) -> list[str]:
        """Return open position codes without exposing the internal dict."""
        return [code for code, pos in self._positions.items() if pos.volume > 0]
