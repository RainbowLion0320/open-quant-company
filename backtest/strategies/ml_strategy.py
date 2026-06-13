"""
ML 策略 — 将训练好的 LightGBM 模型封装为 BaseStrategy

用法:
  from backtest.strategies.ml_strategy import MLStrategy
  strategy = MLStrategy("lgbm_best")  # 自动加载最新模型
  score = strategy.score("600519", prices, 100, "bull")
"""
from datetime import datetime
from typing import Dict, List

import pandas as pd
import numpy as np


from backtest.strategies.base import BaseStrategy
from signals.expression import alpha_factors
from models import MODEL_DIR
from models.lgbm_runtime import global_model_candidates, load_lgbm_bundle, regime_model_candidates
from data.features.feature_store import load_feature_panel
from data.market.symbols import SYMBOL_NAME
from pipeline.alpha import AlphaModel
from pipeline.types import AlphaSignal
from signals.tradability import is_tradable_stock


class MLStrategy(BaseStrategy):
    """
    ML 策略: 用训练好的 LightGBM 模型预测收益率排名。

    集成: 直接继承 BaseStrategy, 可插入策略注册表, 
    与巴菲特/控制论/多因子同台对比。
    """

    name = "ml_lgbm"
    label = "LightGBM ML"
    description = "LightGBM 回归模型预测下月收益率排名 (PIT特征 + 时间序列CV)"

    def __init__(self, model_version: str = "best"):
        super().__init__()
        self.model_version = model_version
        self._model = None
        self._regime_models: Dict[str, object] = {}
        self._regime_features: Dict[str, List[str]] = {}
        self._factors = alpha_factors()
        self._feature_names: List[str] = []
        self.load_errors: List[str] = []
        self._feature_panel: pd.DataFrame | None = None
        self._feature_months: list[str] = []
        self._feature_dates: list[str] = []
        self._pit_score_cache: Dict[tuple[str, str], dict[str, float]] = {}
        self._load_model()
        self._load_regime_models()

    def _load_model(self):
        """加载训练好的模型和元数据"""
        bundle = load_lgbm_bundle(global_model_candidates(MODEL_DIR, self.model_version))
        self.load_errors.extend(bundle.errors)
        self._model = bundle.model
        self._feature_names = bundle.feature_names
        if self._model is None:
            print(f"[MLStrategy] ⚠️ 模型未找到或不可加载: lgbm_{self.model_version}.pkl")
            for err in bundle.errors:
                print(f"[MLStrategy]   load_error: {err}")

    def _load_regime_models(self):
        """加载 bull/bear/sideways 专属模型。"""
        for regime in ("bull", "bear", "sideways"):
            bundle = load_lgbm_bundle(regime_model_candidates(MODEL_DIR, regime))
            self.load_errors.extend(bundle.errors)
            if not bundle.is_ready:
                continue
            self._regime_models[regime] = bundle.model
            self._regime_features[regime] = bundle.feature_names

    def _select_model(self, regime: str):
        if regime in self._regime_models:
            return self._regime_models[regime], self._regime_features.get(regime, self._feature_names)
        return self._model, self._feature_names

    def _ensure_feature_panel(self) -> None:
        if self._feature_panel is not None:
            return
        try:
            panel = load_feature_panel()
        except Exception as exc:
            self.load_errors.append(f"feature_panel: {exc}")
            self._feature_panel = pd.DataFrame()
            self._feature_months = []
            return
        if panel is None or panel.empty or "month" not in panel.columns or "symbol" not in panel.columns:
            self._feature_panel = pd.DataFrame()
            self._feature_months = []
            self._feature_dates = []
            return
        out = panel.copy()
        out["month"] = out["month"].astype(str)
        if "as_of_date" not in out.columns:
            self._feature_panel = pd.DataFrame()
            self._feature_months = []
            self._feature_dates = []
            return
        else:
            out["as_of_date"] = pd.to_datetime(out["as_of_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        out["symbol"] = out["symbol"].astype(str)
        out = out.dropna(subset=["as_of_date"])
        out = out.drop_duplicates(["as_of_date", "symbol"], keep="last")
        self._feature_months = sorted(out["month"].dropna().unique().tolist())
        self._feature_dates = sorted(out["as_of_date"].dropna().unique().tolist())
        self._feature_panel = out.set_index(["as_of_date", "symbol"]).sort_index()

    def _feature_date_for_price_index(self, prices: pd.Series | pd.DataFrame, idx: int) -> str | None:
        try:
            current_date = pd.Timestamp(prices.index[idx]).normalize()
        except Exception:
            return None
        if pd.isna(current_date):
            return None
        target = current_date.strftime("%Y-%m-%d")
        eligible = [as_of for as_of in self._feature_dates if as_of <= target]
        return eligible[-1] if eligible else None

    def _feature_month_for_price_index(self, prices: pd.Series | pd.DataFrame, idx: int) -> str | None:
        as_of = self._feature_date_for_price_index(prices, idx)
        if not as_of:
            return None
        return pd.Timestamp(as_of).to_period("M").strftime("%Y-%m")

    def _cache_key_for_regime(self, regime: str) -> str:
        return regime if regime in self._regime_models else "global"

    def _score_map_for_asof(
        self,
        as_of_date: str,
        regime: str,
        model,
        feature_names: list[str],
    ) -> dict[str, float]:
        if not feature_names:
            return {}
        cache_key = (as_of_date, self._cache_key_for_regime(regime))
        if cache_key not in self._pit_score_cache:
            try:
                rows = self._feature_panel.xs(as_of_date, level="as_of_date")
            except KeyError:
                self._pit_score_cache[cache_key] = {}
                return {}
            missing_columns = [name for name in feature_names if name not in rows.columns]
            if missing_columns:
                self.load_errors.append(
                    f"missing_required_features:{as_of_date}:{regime}: {','.join(missing_columns[:10])}"
                )
                self._pit_score_cache[cache_key] = {}
                return {}
            X = rows.loc[:, feature_names]
            X = X.apply(pd.to_numeric, errors="coerce")
            X = X.replace([np.inf, -np.inf], np.nan)
            missing_mask = X.isna().any(axis=1)
            if missing_mask.any():
                self.load_errors.append(
                    f"missing_required_features:{as_of_date}:{regime}: rows={int(missing_mask.sum())}"
                )
                X = X.loc[~missing_mask]
            if X.empty:
                self._pit_score_cache[cache_key] = {}
                return {}
            try:
                preds = np.asarray(model.predict(X), dtype=float)
            except Exception as exc:
                self.load_errors.append(f"pit_predict:{as_of_date}:{regime}: {exc}")
                self._pit_score_cache[cache_key] = {}
                return {}
            scores = 50.0 + 50.0 * np.tanh(preds * 5)
            scores = np.clip(scores, 0.0, 100.0)
            self._pit_score_cache[cache_key] = {
                str(sym): float(score)
                for sym, score in zip(X.index.astype(str), scores)
            }
        return self._pit_score_cache[cache_key]

    def pit_score_map(
        self,
        prices: pd.Series | pd.DataFrame,
        idx: int,
        regime: str,
    ) -> dict[str, float]:
        """Return all model scores for the point-in-time feature month."""
        model, feature_names = self._select_model(regime)
        if model is None or getattr(model, "_model", None) is None:
            return {}
        if not feature_names or idx < 60 or prices is None:
            return {}
        self._ensure_feature_panel()
        if self._feature_panel is None or self._feature_panel.empty:
            return {}
        as_of_date = self._feature_date_for_price_index(prices, idx)
        if not as_of_date:
            return {}
        return self._score_map_for_asof(as_of_date, regime, model, feature_names)

    def _pit_score(
        self,
        symbol: str,
        prices: pd.Series | pd.DataFrame,
        idx: int,
        regime: str,
    ) -> float | None:
        score = self.pit_score_map(prices, idx, regime).get(str(symbol))
        if score is None:
            return None
        return score

    def _factor_features(self, prices: pd.Series | pd.DataFrame, idx: int, feature_names: list[str]) -> dict[str, float]:
        if isinstance(prices, pd.Series):
            df = pd.DataFrame({"close": prices})
            for col in ["open", "high", "low", "volume"]:
                df[col] = df["close"]
        else:
            df = prices

        features = {}
        for name, factor in self._factors.items():
            if feature_names and name not in feature_names:
                continue
            val = factor.compute(df, idx)
            features[name] = val if not (isinstance(val, float) and np.isnan(val)) else 0.0
        return features

    def score(
        self,
        symbol: str,
        prices: pd.Series,
        idx: int,
        regime: str,
        **kwargs,
    ) -> float:
        """
        ML 评分: 计算因子 → 模型预测 → 映射到 0-100。

        如果模型未加载或历史不足, 返回 0，避免把缺数据股票选入组合。
        """
        model, feature_names = self._select_model(regime)
        if model is None or getattr(model, "_model", None) is None:
            return 0.0

        # 检查数据充分性
        if idx < 60 or prices is None:
            return 0.0

        pit_score = self._pit_score(symbol, prices, idx, regime)
        if pit_score is not None:
            return pit_score

        features = self._factor_features(prices, idx, feature_names)

        # 预测
        X = pd.DataFrame([features])
        if feature_names:
            X = X.reindex(columns=feature_names, fill_value=0)
        X = X.fillna(0)

        try:
            pred = float(model.predict(X)[0])
        except Exception:
            return 0.0

        # 映射预测值 → 评分 (0-100)
        # 使用 sigmoid: 预测值越大 → 评分越高
        score = 50.0 + 50.0 * np.tanh(pred * 5)  # tanh 压缩到 [-1,1]
        return max(0.0, min(100.0, score))

    def should_rebalance(self, dt, regime: str, last_regime=None, *args, **kwargs) -> bool:
        """月度复评；regime 切换时额外复评。"""
        if last_regime is not None and regime != last_regime:
            self._last_rebalance_month = dt.month
            return True
        if dt.month != self._last_rebalance_month:
            self._last_rebalance_month = dt.month
            return True
        return False

    @property
    def is_ready(self) -> bool:
        if self._regime_models:
            return True
        return self._model is not None and getattr(self._model, "_model", None) is not None


class MLFeatureStoreAlphaModel(AlphaModel):
    """Batch ML alpha generation from the daily as-of feature store."""

    name = MLStrategy.name
    label = MLStrategy.label

    def __init__(
        self,
        strategy: MLStrategy | None = None,
        model_version: str = "best",
        min_score: float = 30.0,
        horizon_days: int = 20,
        label: str | None = None,
    ):
        self.strategy = strategy or MLStrategy(model_version)
        self.min_score = float(min_score)
        self.horizon_days = int(horizon_days)
        self.label = label or self.label

    def generate_alpha(
        self,
        universe: list[str],
        prices: pd.DataFrame,
        date_idx: int,
        regime: str,
    ) -> list[AlphaSignal]:
        if not getattr(self.strategy, "is_ready", False):
            return []

        score_map = self.strategy.pit_score_map(prices, date_idx, regime)
        if not score_map:
            return []

        signals: list[AlphaSignal] = []
        available = set(str(col) for col in getattr(prices, "columns", []))
        ts = datetime.now().isoformat()
        for symbol in universe:
            sym = str(symbol)
            if available and sym not in available:
                continue
            score = score_map.get(sym)
            if score is None or score < self.min_score:
                continue
            if not is_tradable_stock(sym, SYMBOL_NAME.get(sym, sym)):
                continue

            direction = "buy" if score >= 50 else "hold"
            signals.append(
                AlphaSignal(
                    symbol=sym,
                    strategy=self.name,
                    direction=direction,
                    confidence=min(1.0, max(0.0, score / 100)),
                    score=round(float(score), 1),
                    horizon_days=self.horizon_days,
                    reason=f"{self.label} score={score:.1f} regime={regime}",
                    timestamp=ts,
                )
            )

        signals.sort(key=lambda s: s.score, reverse=True)
        return signals

    def generate_score_panel(
        self,
        universe: list[str],
        prices: pd.DataFrame,
        date_idx: int,
        regime: str,
    ) -> list[dict]:
        if not getattr(self.strategy, "is_ready", False):
            return []
        score_map = self.strategy.pit_score_map(prices, date_idx, regime)
        if not score_map:
            return []
        as_of_date = self.strategy._feature_date_for_price_index(prices, date_idx)
        cache_key = self.strategy._cache_key_for_regime(regime)
        rows: list[dict] = []
        ts = datetime.now().isoformat()
        available = set(str(col) for col in getattr(prices, "columns", []))
        for symbol in universe:
            sym = str(symbol)
            if available and sym not in available:
                continue
            score = score_map.get(sym)
            rows.append(
                {
                    "symbol": sym,
                    "strategy": self.name,
                    "score": float(score) if score is not None else None,
                    "horizon_days": self.horizon_days,
                    "timestamp": ts,
                    "feature_version": as_of_date or "",
                    "model_version": cache_key,
                    "data_quality": "ok" if score is not None else "missing_feature_row",
                }
            )
        return rows
