# Quant Agent — 维护命令

.PHONY: clean cache-clean pyc-clean dist-clean

# 清理 Python 字节码缓存
pyc-clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete

# 清理数据缓存（超过24小时的 parquet）
cache-clean:
	find data/cache -name '*.parquet' -mtime +1 -delete
	@echo "清理完成: $$(find data/cache -name '*.parquet' | wc -l) 个文件保留"

# 清理临时文件
tmp-clean:
	rm -rf tmp/ *.tmp *.log

# 日常清理（安全，不删数据）
clean: pyc-clean tmp-clean

# 深度清理（含数据缓存）
dist-clean: clean cache-clean
	@echo "深度清理完成"

# 扫描全量股票
scan:
	python scripts/scan_all.py

# 回测（默认精选池）
backtest:
	python backtest/run_ma_cross.py

# 市场状态检测
regime:
	python -c "from cybernetics.orchestrator import QuantOrchestrator; o=QuantOrchestrator(); s=o.detect(); print(f'Regime: {s.regime.value} | {s.index_ma_trend}')"

# 系统状态
status:
	python main.py status
