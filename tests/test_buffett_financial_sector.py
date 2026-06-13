def test_financial_sector_moat_uses_net_margin_and_relaxed_leverage(monkeypatch):
    from signals import buffett

    monkeypatch.setattr(
        buffett,
        "_buffett_config",
        lambda: {
            "moat": {
                "min_roe_years": 3,
                "min_roe": 0.15,
                "max_debt_equity": 1.0,
                "min_gross_margin": 0.30,
                "sectors": {
                    "bank": {
                        "min_roe": 0.10,
                        "max_debt_equity": 12.0,
                        "skip_gross_margin": True,
                        "min_net_margin": 0.20,
                    }
                },
            }
        },
    )

    avg_roe, avg_gm, debt_equity, passed, details, avg_nm = buffett.assess_moat(
        roe_history=[0.11, 0.12, 0.13],
        gross_margin_history=[],
        debt_equity=8.0,
        net_margin_history=[0.24, 0.25, 0.26],
        sector="bank",
    )

    assert passed is True
    assert avg_roe == 0.12
    assert avg_gm == 0
    assert avg_nm == 0.25
    assert debt_equity == 8.0
    assert any("销售净利率" in detail for detail in details)


def test_buffett_config_is_cached_per_process(monkeypatch):
    from signals import buffett

    calls = []
    config = {
        "margin_of_safety": {
            "dcf_discount_rate": 0.10,
            "growth_rate_terminal": 0.03,
            "safety_margin_pct": 0.30,
        },
        "valuation": {"growth_period": 5, "terminal_pe": 20, "growth_default": 0.05},
        "moat": {
            "min_roe_years": 3,
            "min_roe": 0.10,
            "max_debt_equity": 1.0,
            "min_gross_margin": 0.20,
        },
        "circle_of_competence": {"industries": ["测试行业"]},
        "scoring": {},
    }

    def fake_get_section(section, default):
        calls.append(section)
        return config

    monkeypatch.setattr(buffett, "get_section", fake_get_section)
    cache_clear = getattr(buffett._buffett_config, "cache_clear", None)
    if cache_clear:
        cache_clear()

    first = buffett._buffett_config()
    second = buffett._buffett_config()

    assert first is second
    assert calls == ["buffett"]
