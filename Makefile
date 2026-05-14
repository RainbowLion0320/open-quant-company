# Quant Agent — 维护命令
PYTHON = /Users/fushao/.hermes/hermes-agent/venv/bin/python3

.PHONY: clean cache-clean pyc-clean dist-clean

# 清理 Python 字节码缓存
pyc-clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete

# 清理数据缓存（超过 365 天的 parquet 文件，即真正的僵尸缓存）
cache-clean:
	find data/cache -name '*.parquet' -mtime +365 -delete
	@echo "清理完成: $$(find data/cache -name '*.parquet' | wc -l) 个文件保留"

# 强制清空全部缓存（重新拉全量数据前使用）
cache-reset:
	rm -f data/cache/*.parquet
	@echo "缓存已清空"

# 清理临时文件
tmp-clean:
	rm -rf tmp/ *.tmp *.log

# 日常清理（安全，不删数据）
clean: pyc-clean tmp-clean

# 深度清理（含数据缓存）
dist-clean: clean cache-clean
	@echo "深度清理完成"

# 扫描全量股票 (日频 cron 标准入口)
scan:
	$(PYTHON) scripts/compute_signals.py

# 三策略对比回测
backtest:
	$(PYTHON) backtest/run_all_strategies.py

# 市场状态检测
regime:
	$(PYTHON) -c "from cybernetics.orchestrator import QuantOrchestrator; o=QuantOrchestrator(); s=o.detect(); print(f'Regime: {s.regime.value} | {s.index_ma_trend}')"

# Web 仪表盘 (Vue 3 + FastAPI)
web:
	cd web/frontend && npm run build
	$(PYTHON) -m web.api

web-dev:
	$(PYTHON) -m web.api

web-stop:
	pkill -f "web.api" || true
