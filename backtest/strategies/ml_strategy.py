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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

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
        self._factors = alpha_factors()
        self._feature_names: List[str] = []
        self._load_model()

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
            print(f"[MLStrategy] ⚠️ 模型未找到: {model_path}, 将返回中性评分")

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

        如果模型未加载, 返回 50 (中性)。
        """
        if self._model is None or self._model._model is None:
            return 50.0

        # 检查数据充分性
        if idx < 60 or prices is None:
            return 50.0

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
            if self._feature_names and name not in self._feature_names:
                continue
            val = factor.compute(df, idx)
            features[name] = val if not (isinstance(val, float) and np.isnan(val)) else 0.0

        # 预测
        X = pd.DataFrame([features])
        if self._feature_names:
            X = X.reindex(columns=self._feature_names, fill_value=0)
        X = X.fillna(0)

        try:
            pred = float(self._model.predict(X)[0])
        except Exception:
            return 50.0

        # 映射预测值 → 评分 (0-100)
        # 使用 sigmoid: 预测值越大 → 评分越高
        score = 50.0 + 50.0 * np.tanh(pred * 5)  # tanh 压缩到 [-1,1]
        return max(0.0, min(100.0, score))

    def should_rebalance(self, dt, regime: str, last_regime=None) -> bool:
        """每月初调仓"""
        if dt.month != self._last_rebalance_month:
            self._last_rebalance_month = dt.month
            return True
        return False

    @property
    def is_ready(self) -> bool:
        return self._model is not None and self._model._model is not None
