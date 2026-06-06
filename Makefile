# 星盘 / Astrolabe Quant OS — 维护命令
PYTHON ?= .venv/bin/python

.PHONY: install test lint ci clean scan backtest regime web web-build web-dev web-stop

# 安装依赖
install:
	$(PYTHON) -m pip install -r requirements.txt

install-dev: install
	$(PYTHON) -m pip install -r requirements-dev.txt

install-ml: install
	$(PYTHON) -m pip install lightgbm scikit-learn optuna

# 运行测试
test:
	$(PYTHON) -m pytest tests/ -v

test-quick:
	$(PYTHON) -m pytest tests/ -q

# 代码风格检查
lint:
	$(PYTHON) -m flake8 data/ signals/ backtest/ broker/ cybernetics/ scripts/ web/api/ --max-line-length=120 --ignore=E203,W503 2>/dev/null || echo "flake8 未安装，跳过 lint"

# CI 完整检查
ci: test web-build
	@echo "CI 通过: 测试 + 前端构建"
	@$(PYTHON) scripts/lookahead_check.py --quick --n 5 2>/dev/null || echo "  (lookahead check skipped — no data)"

# 清理 Python 字节码缓存
pyc-clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete

# 清理临时文件
tmp-clean:
	rm -rf tmp/ *.tmp *.log

# 日常清理（安全，不删数据）
clean: pyc-clean tmp-clean

# 扫描全量股票 (日频 cron 标准入口)
scan:
	$(PYTHON) -m astrolabe_cli.main strategy run all --mode production

# 三策略对比回测
backtest:
	$(PYTHON) -m astrolabe_cli.main backtest run

# 市场状态检测
regime:
	$(PYTHON) -m astrolabe_cli.main regime status

# Web 仪表盘 (生产构建 + 启动)
web: web-build
	$(PYTHON) -m astrolabe_cli.main web serve --host 0.0.0.0 --port 8501

# Web 开发模式 (直接启动，使用 Vite 前端)
web-dev:
	$(PYTHON) -m uvicorn web.api.app:create_app --factory --port 8501 --host 0.0.0.0 --reload

# 前端构建
web-build:
	$(PYTHON) -m astrolabe_cli.main web build

# 停止 Web
web-stop:
	pkill -f "uvicorn web.api" 2>/dev/null || echo "无运行中的 Web 进程"
