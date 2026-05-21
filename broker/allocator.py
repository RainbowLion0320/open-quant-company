"""
Asset Allocator — 跨资产动态分配引擎

核心理念: 市场 regime 决定大类资产权重，大类内各资产按各自策略评分选标的。

Bull:  equity↑  bond↓  cash→
Bear:  bond↑   gold↑  equity↓
Volatile: cash↑  reduce all

Config-driven: settings.yaml → assets.{type}.enabled + alloc_weight
Allocator 动态覆盖 config 静态权重。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import yaml
from pathlib import Path


import copy


@dataclass
class AssetAllocation:
    """单个资产类型的分配结果"""
    asset_type: str          # "stock", "etf", "bond", "crypto"
    label: str               # "A股股票"
    weight: float            # 分配权重 (0-1, 所有资产总和=1)
    symbols: List[str]       # 该资产内被选中的标的
    scores: Dict[str, float] # 各标的评分
    total_value: float       # 该资产总投入金额


@dataclass
class PortfolioAllocation:
    """完整投资组合分配"""
    regime: str              # "bull", "bear", "sideways", "unknown"
    allocations: List[AssetAllocation] = field(default_factory=list)
    total_capital: float = 1_000_000.0  # 总资金
    cash_reserve: float = 0.0  # 现金保留

    @property
    def total_allocated(self) -> float:
        return sum(a.weight * self.total_capital for a in self.allocations)


# ── Regime → Weight matrix ──
# Configuration override from settings.yaml → asset_allocation.regime_weights
REGIME_WEIGHTS_DEFAULT = {
    "bull": {
        "stock": 0.60, "etf": 0.25, "bond": 0.05, "cash": 0.10,
    },
    "sideways": {
        "stock": 0.35, "etf": 0.25, "bond": 0.20, "cash": 0.20,
    },
    "bear": {
        "stock": 0.10, "etf": 0.10, "bond": 0.40, "cash": 0.40,
    },
    "unknown": {
        "stock": 0.20, "etf": 0.15, "bond": 0.30, "cash": 0.35,
    },
}


class AssetAllocator:
    """Regime-aware multi-asset allocation engine."""

    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or Path("~/quant-agent/config/settings.yaml").expanduser()
        self._regime_weights = copy.deepcopy(REGIME_WEIGHTS_DEFAULT)
        self._load_config()

    def _load_config(self):
        """Load regime weights from config if available."""
        try:
            with open(self._config_path) as f:
                cfg = yaml.safe_load(f) or {}
            alloc_cfg = cfg.get("asset_allocation", {})
            rw = alloc_cfg.get("regime_weights", {})
            for regime, weights in rw.items():
                if regime in self._regime_weights:
                    self._regime_weights[regime].update(weights)
        except Exception:
            pass  # Use defaults

    def get_weights(self, regime: str) -> Dict[str, float]:
        """Get asset weights for a given market regime."""
        regime_key = regime if regime in self._regime_weights else "unknown"
        return dict(self._regime_weights[regime_key])

    def allocate(
        self,
        regime: str,
        enabled_assets: Dict[str, bool],
        asset_signals: Dict[str, List[dict]],  # asset_type → [{symbol, score, ...}]
        total_capital: float = 1_000_000.0,
        max_positions_per_asset: int = 8,
    ) -> PortfolioAllocation:
        """
        Allocate capital across enabled asset classes.

        Args:
            regime: Market regime ("bull", "bear", "sideways")
            enabled_assets: {asset_type: enabled} from config
            asset_signals: {asset_type: [{symbol, score, name, ...}]}
            total_capital: Total portfolio capital
            max_positions_per_asset: Max symbols per asset class

        Returns:
            PortfolioAllocation with per-asset breakdowns
        """
        base_weights = self.get_weights(regime)

        # Only consider enabled assets
        active_types = [t for t, enabled in enabled_assets.items() if enabled]
        if not active_types:
            return PortfolioAllocation(regime=regime, total_capital=total_capital)

        # Normalize weights to sum to 1-cash
        raw_sum = sum(base_weights.get(t, 0) for t in active_types)
        cash_weight = base_weights.get("cash", 0.10)

        allocations = []
        for asset_type in active_types:
            raw_w = base_weights.get(asset_type, 0)
            if raw_w <= 0 or raw_sum <= 0:
                continue

            norm_w = raw_w / raw_sum * (1 - cash_weight)
            signals = asset_signals.get(asset_type, [])

            # Select top-N by score within this asset class
            sorted_signals = sorted(signals, key=lambda s: s.get("score", 0), reverse=True)
            selected = sorted_signals[:max_positions_per_asset]

            if not selected:
                # No signals — push weight to cash
                cash_weight += norm_w
                continue

            # Equal-weight within asset class (each position gets norm_w / N)
            per_pos_w = norm_w / len(selected)
            per_pos_value = total_capital * per_pos_w

            allocations.append(AssetAllocation(
                asset_type=asset_type,
                label=self._asset_label(asset_type),
                weight=norm_w,
                symbols=[s["symbol"] for s in selected],
                scores={s["symbol"]: s.get("score", 0) for s in selected},
                total_value=total_capital * norm_w,
            ))

        return PortfolioAllocation(
            regime=regime,
            allocations=allocations,
            total_capital=total_capital,
            cash_reserve=total_capital * cash_weight,
        )

    def _asset_label(self, asset_type: str) -> str:
        labels = {
            "stock": "A股股票", "etf": "ETF基金",
            "bond": "债券", "futures": "期货", "crypto": "加密货币",
        }
        return labels.get(asset_type, asset_type)

    def summary(self, allocation: PortfolioAllocation) -> str:
        """Human-readable allocation summary."""
        lines = [f"Portfolio: {allocation.regime} regime | {allocation.total_capital:,.0f} 元"]
        for a in allocation.allocations:
            lines.append(
                f"  {a.label} ({a.asset_type}): {a.weight*100:.0f}% = {a.total_value:,.0f} 元"
                f" → {len(a.symbols)} positions"
            )
        lines.append(f"  Cash reserve: {allocation.cash_reserve:,.0f} 元 ({allocation.cash_reserve/allocation.total_capital*100:.0f}%)")
        return "\n".join(lines)
