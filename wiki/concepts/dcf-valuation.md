---
title: DCF Valuation (Two-Stage)
created: 2026-05-12
updated: 2026-05-12
type: concept
tags: [dcf, valuation, intrinsic-value, safety-margin, gordon-growth]
---

# DCF Valuation

Two-stage Discounted Cash Flow model used by [[buffett-filter]] to compute intrinsic value and safety margin. All tunable parameters live in `config/settings.yaml` — this page documents the concept and methodology, not current values.

## Free Cash Flow

```
FCF = Operating Cash Flow - Capital Expenditure
```

Both components extracted from 同花顺 cash flow statement via [[data-sources|AKShare]]. For financial stocks, a modified earnings-based approach is used since CapEx is not meaningful.

## Growth Rate

Estimated from 5-year median net profit growth rate, clamped between configurable floor and ceiling.
- **Floor**: Prevents negative growth destroying terminal value
- **Ceiling**: Caps unrealistic extrapolation
- **Method**: Median over mean to resist outlier years

## Two-Stage Model

### Stage 1: Explicit Forecast

Project FCF for N years at the estimated growth rate. Discount each year back to present.

```
PV_explicit = Σ( FCF_t / (1 + r)^t ), t = 1..N
```

### Stage 2: Gordon Growth Terminal Value

```
Terminal Value = FCF_N × (1 + g) / (r - g)
PV_terminal = Terminal Value / (1 + r)^N
```

### Intrinsic Value

```
Intrinsic = PV_explicit + PV_terminal
```

## Safety Margin

```
Safety Margin = (Intrinsic Value - Market Price) / Intrinsic Value
```

If margin is >= threshold (config), the stock passes Filter 3. In [[buffett-filter|composite scoring]], safety margin carries the highest weight — even a great company is a poor investment at the wrong price.

## Parameters (all in settings.yaml)

| Parameter | Config path | What it controls |
|-----------|------------|------------------|
| Discount rate | `buffett.margin_of_safety.dcf_discount_rate` | Required return for China equities |
| Terminal growth | `buffett.margin_of_safety.growth_rate_terminal` | Perpetual growth assumption |
| Explicit years | (`buffett`) | Balance between forecastability and terminal weight |
| Growth floor | `buffett.valuation.growth_min` | Prevents destructive DCF |
| Growth ceiling | `buffett.valuation.growth_max` | Caps optimism |
| Safety threshold | `buffett.margin_of_safety.safety_margin_pct` | Minimum margin to pass Filter 3 |

## See Also

- [[buffett-filter]] — Filter 3 uses this DCF
- [[data-sources]] — Cash flow data source
- [[financial-cache]] — Performance optimization for repeat queries
