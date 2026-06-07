from pathlib import Path


FRONTEND_SRC = Path("web/frontend/src")


def read_frontend(path: str) -> str:
    return (FRONTEND_SRC / path).read_text(encoding="utf-8")


VIEW_MODEL_BY_VIEW = {
    "Portfolio.vue": "usePortfolioView.ts",
    "Sectors.vue": "useSectorsView.ts",
    "Stocks.vue": "useStocksView.ts",
    "Settings.vue": "useSettingsView.ts",
}


def read_view_with_support(view: str) -> str:
    text = read_frontend(f"views/{view}")
    view_model = VIEW_MODEL_BY_VIEW.get(view)
    if view_model:
        text += "\n" + read_frontend(f"view-models/{view_model}")
    return text


def test_frontend_i18n_module_has_bilingual_contract():
    index = FRONTEND_SRC / "i18n/index.ts"
    messages = FRONTEND_SRC / "i18n/messages.ts"

    assert index.exists()
    assert messages.exists()

    index_text = index.read_text(encoding="utf-8")
    messages_text = messages.read_text(encoding="utf-8")

    for token in ("useI18n", "translate", "setLocale", "toggleLocale", "localStorage"):
      assert token in index_text

    for token in ('"zh-CN"', '"en-US"', "nav:", "common:", "pipeline:", "market:", "portfolio:"):
      assert token in messages_text


def test_app_shell_uses_localized_nav_and_sidebar_language_toggle():
    app = read_frontend("App.vue")

    assert "useI18n" in app
    assert 'class="locale-toggle"' in app
    assert "@click=\"toggleLocale\"" in app
    assert "labelKey" in app
    assert "t(item.labelKey)" in app
    assert "t('app.navAria')" in app or 't("app.navAria")' in app
    assert 'label: "市场总览"' not in app
    assert 'aria-label="主导航"' not in app


def test_module_shells_get_titles_and_tabs_from_i18n():
    for view in ("Research.vue", "DataHub.vue", "StrategyLab.vue", "SystemHub.vue"):
        text = read_frontend(f"views/{view}")
        assert "useI18n" in text
        assert ":title=" in text
        assert "computed" in text
        assert "t(" in text
        assert 'title="市场' not in text
        assert 'title="数据' not in text
        assert 'title="策略' not in text
        assert 'title="系统' not in text


def test_system_module_exposes_test_design_intelligence_tab():
    system_hub = read_frontend("views/SystemHub.vue")
    zh_modules = read_frontend("i18n/messages/zh-CN/modules.ts")
    en_modules = read_frontend("i18n/messages/en-US/modules.ts")
    api_system = read_frontend("api/modules/system.ts")
    zh_index = read_frontend("i18n/messages/zh-CN/index.ts")
    en_index = read_frontend("i18n/messages/en-US/index.ts")

    assert "TestDesign" in system_hub
    assert ("Test" + "System") not in system_hub
    assert '{ key: "tests" }' in system_hub
    assert "tests: {" in zh_modules
    assert "测试设计" in zh_modules
    assert "tests: {" in en_modules
    assert "Test Design" in en_modules
    assert "testDesign" in zh_index
    assert "testDesign" in en_index
    assert ("test" + "System") not in zh_index
    assert ("test" + "System") not in en_index
    assert "testDesign:" in api_system
    assert ("test" + "SystemSummary") not in api_system
    assert ("test" + "SystemDomains") not in api_system
    assert ("test" + "SystemRuns") not in api_system


def test_high_traffic_views_use_i18n_for_static_copy():
    for view in (
        "Market.vue",
        "Pipeline.vue",
        "Portfolio.vue",
        "Sectors.vue",
        "Stocks.vue",
        "Settings.vue",
    ):
        text = read_view_with_support(view)
        assert "useI18n" in text
        assert "t(" in text
