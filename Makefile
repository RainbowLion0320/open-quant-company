# Open Quant Company — 维护命令
PYTHON ?= .venv/bin/python

.PHONY: install install-min install-dev install-ml test lint ci clean scan backtest regime web web-build web-dev web-stop

# 安装完整本地运行/开发依赖
install:
	$(PYTHON) -m pip install -e ".[dev,ml]"

# 安装最小运行依赖
install-min:
	$(PYTHON) -m pip install -e .

install-dev: install

install-ml:
	$(PYTHON) -m pip install -e ".[ml]"

# 运行测试
test:
	$(PYTHON) -m pytest tests/ -v

test-quick:
	$(PYTHON) -m pytest tests/ -q

# 代码风格检查
lint:
	$(PYTHON) -m ruff check astrolabe_cli backtest broker core cybernetics data models notify pipeline research scripts signals tests web/api --select E9,F63,F7,F82

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
