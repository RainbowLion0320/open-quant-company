"""
ML 模型层 — LightGBM 基线 + 时间序列 CV

借鉴 Qlib Model 层设计:
  - 统一 fit/predict 接口
  - 时间序列交叉验证
  - 模型注册表 (版本化)

用法:
  model = LightGBMRegressor()
  model.fit(X_train, y_train)
  preds = model.predict(X_test)
  ic = model.evaluate(X_test, y_test)
"""
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import pickle
import json

import numpy as np
import pandas as pd

from data.db import get_store_dir

MODEL_DIR = get_store_dir().parent / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


class BaseModel:
    """ML 模型基类"""

    name: str = "base"

    def fit(self, X: pd.DataFrame, y: pd.Series, **kwargs):
        raise NotImplementedError

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError

    def evaluate(self, X: pd.DataFrame, y: pd.Series) -> Dict[str, float]:
        """评估: IC Rank, ICIR"""
        preds = self.predict(X)

        # IC Rank
        from scipy.stats import spearmanr
        ic, _ = spearmanr(preds, y)
        ic = ic if not np.isnan(ic) else 0.0

        # 月度 IC 序列
        if hasattr(X, 'index') and isinstance(X.index, pd.DatetimeIndex):
            monthly_ic = []
            for month, idx in X.groupby(X.index.to_period("M")).groups.items():
                if len(idx) >= 5:
                    p = preds[list(idx)]
                    y_m = y.iloc[list(idx)]
                    ic_m, _ = spearmanr(p, y_m)
                    if not np.isnan(ic_m):
                        monthly_ic.append(ic_m)
            icir = np.mean(monthly_ic) / (np.std(monthly_ic) + 1e-9) if monthly_ic else 0.0
        else:
            icir = 0.0

        return {"ic": ic, "icir": icir}

    def save(self, version: str = ""):
        """保存模型"""
        if not version:
            version = datetime.now().strftime("%Y%m%d_%H%M")
        path = MODEL_DIR / f"{self.name}_{version}.pkl"
        with open(path, "wb") as f:
            pickle.dump(self, f)
        # 更新元数据
        meta_path = MODEL_DIR / "registry.json"
        meta = {}
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
        meta[version] = {
            "model": self.name,
            "saved_at": datetime.now().isoformat(),
            "file": str(path.name),
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
        return str(path)

    @classmethod
    def load(cls, version: str) -> "BaseModel":
        meta_path = MODEL_DIR / "registry.json"
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            if version in meta:
                path = MODEL_DIR / meta[version]["file"]
                with open(path, "rb") as f:
                    return pickle.load(f)
        raise FileNotFoundError(f"Model version {version} not found")

    @classmethod
    def list_versions(cls) -> List[dict]:
        meta_path = MODEL_DIR / "registry.json"
        if meta_path.exists():
            with open(meta_path) as f:
                return json.load(f)
        return {}


class LightGBMRegressor(BaseModel):
    """LightGBM 回归模型 — 预测下月收益率排名"""

    name = "lgbm"

    def __init__(
        self,
        num_leaves: int = 31,
        learning_rate: float = 0.05,
        n_estimators: int = 200,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        reg_alpha: float = 0.1,
        reg_lambda: float = 0.1,
        min_child_samples: int = 20,
        random_state: int = 42,
        **kwargs,
    ):
        self.num_leaves = num_leaves
        self.learning_rate = learning_rate
        self.n_estimators = n_estimators
        self.subsample = subsample
        self.colsample_bytree = colsample_bytree
        self.reg_alpha = reg_alpha
        self.reg_lambda = reg_lambda
        self.min_child_samples = min_child_samples
        self.random_state = random_state
        self._model = None
        self._feature_names: List[str] = []
        self._train_ic: float = 0.0
        self._val_ic: float = 0.0

    def fit(self, X: pd.DataFrame, y: pd.Series, X_val=None, y_val=None, **kwargs):
        try:
            import lightgbm as lgb
            self._use_lgb = True
        except (ImportError, OSError):
            from sklearn.ensemble import GradientBoostingRegressor as GBR
            self._use_lgb = False

        self._feature_names = list(X.columns)

        if self._use_lgb:
            self._model = lgb.LGBMRegressor(
                num_leaves=getattr(self, 'num_leaves', 31),
                learning_rate=getattr(self, 'learning_rate', 0.05),
                n_estimators=getattr(self, 'n_estimators', 200),
                subsample=getattr(self, 'subsample', 0.8),
                colsample_bytree=getattr(self, 'colsample_bytree', 0.8),
                reg_alpha=getattr(self, 'reg_alpha', 0.1),
                reg_lambda=getattr(self, 'reg_lambda', 0.1),
                min_child_samples=getattr(self, 'min_child_samples', 20),
                random_state=getattr(self, 'random_state', 42),
                verbose=-1,
                **kwargs,
            )
        else:
            print("  [INFO] LightGBM unavailable, using sklearn GradientBoostingRegressor")
            self._model = GBR(
                n_estimators=getattr(self, 'n_estimators', 200),
                learning_rate=getattr(self, 'learning_rate', 0.05),
                max_depth=5,
                subsample=getattr(self, 'subsample', 0.8),
                random_state=getattr(self, 'random_state', 42),
                **{k: v for k, v in kwargs.items() if k in ('min_samples_leaf',)},
            )

        self._model.fit(X, y)
        self._train_ic = self.evaluate(X, y)["ic"]

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("Model not fitted")
        return self._model.predict(X[self._feature_names])

    def feature_importance(self) -> pd.Series:
        """返回特征重要性"""
        if self._model is None:
            return pd.Series()
        return pd.Series(
            self._model.feature_importances_,
            index=self._feature_names,
        ).sort_values(ascending=False)


def prepare_xy(
    features_df: pd.DataFrame,
    target_col: str = "ret_fwd_20d",
    skip_cols: List[str] = None,
) -> Tuple[pd.DataFrame, pd.Series]:
    """
    准备训练数据: X=因子, y=未来收益率。

    注意: 需要外部确保 target_col 不是前视的(PIT 约束)。
    """
    if skip_cols is None:
        skip_cols = ["symbol", "date", "month", "name", target_col]

    cols = [c for c in features_df.columns if c not in skip_cols]
    # 只保留数值列
    numeric_cols = []
    for c in cols:
        if features_df[c].dtype in ('float64', 'float32', 'int64', 'int32', 'bool'):
            numeric_cols.append(c)
    X = features_df[numeric_cols].fillna(0)
    y = features_df[target_col].fillna(0)

    return X, y
