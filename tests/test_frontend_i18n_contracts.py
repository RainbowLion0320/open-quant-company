from pathlib import Path


FRONTEND_SRC = Path("web/frontend/src")


def read_frontend(path: str) -> str:
    return (FRONTEND_SRC / path).read_text(encoding="utf-8")


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


def test_high_traffic_views_use_i18n_for_static_copy():
    for view in (
        "Market.vue",
        "Pipeline.vue",
        "Portfolio.vue",
        "Sectors.vue",
        "Stocks.vue",
        "Settings.vue",
    ):
        text = read_frontend(f"views/{view}")
        assert "useI18n" in text
        assert "t(" in text
