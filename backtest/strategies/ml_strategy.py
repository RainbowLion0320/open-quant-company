"""
ML 策略 — 将训练好的 LightGBM 模型封装为 BaseStrategy

用法:
  from backtest.strategies.ml_strategy import MLStrategy
  strategy = MLStrategy("lgbm_best")  # 自动加载最新模型
  score = strategy.score("600519", prices, 100, "bull")
"""
import sys, os, pickle, json
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import numpy as np


from backtest.strategies.base import BaseStrategy
from signals.expression import alpha_factors
from models import MODEL_DIR


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
        self._load_model()
        self._load_regime_models()

    def _load_model(self):
        """加载训练好的模型和元数据"""
        # 尝试加载最新版本
        meta_path = MODEL_DIR / "lgbm_best_meta.json"
        model_path = MODEL_DIR / f"lgbm_{self.model_version}.pkl"

        if model_path.exists():
            with open(model_path, "rb") as f:
                self._model = pickle.load(f)
        elif meta_path.exists():
            # 从 registry 加载最新
            try:
                self._model = pickle.load(open(
                    MODEL_DIR / f"lgbm_{self.model_version}.pkl", "rb"))
            except Exception:
                pass

        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
                self._feature_names = meta.get("features", [])

        if self._model is None:
            print(f"[MLStrategy] ⚠️ 模型未找到: {model_path}, 将跳过 ML 入选")

    def _load_regime_models(self):
        """加载 bull/bear/sideways 专属模型。"""
        for regime in ("bull", "bear", "sideways"):
            model_path = MODEL_DIR / f"lgbm_{regime}.pkl"
            if not model_path.exists():
                continue
            try:
                with open(model_path, "rb") as f:
                    model = pickle.load(f)
                self._regime_models[regime] = model
            except Exception:
                continue
            meta_path = MODEL_DIR / f"lgbm_{regime}_meta.json"
            if meta_path.exists():
                try:
                    with open(meta_path) as f:
                        self._regime_features[regime] = json.load(f).get("features", [])
                except Exception:
                    pass

    def _select_model(self, regime: str):
        if regime in self._regime_models:
            return self._regime_models[regime], self._regime_features.get(regime, self._feature_names)
        return self._model, self._feature_names

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

        # 确保 prices 是 DataFrame (有 OHLCV 列)
        if isinstance(prices, pd.Series):
            df = pd.DataFrame({"close": prices})
            for col in ["open", "high", "low", "volume"]:
                df[col] = df["close"]  # fallback: 用 close 近似其他列
        else:
            df = prices

        # 计算因子
        features = {}
        for name, factor in self._factors.items():
            if feature_names and name not in feature_names:
                continue
            val = factor.compute(df, idx)
            features[name] = val if not (isinstance(val, float) and np.isnan(val)) else 0.0

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
