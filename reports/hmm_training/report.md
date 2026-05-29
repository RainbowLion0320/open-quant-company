# HMM Regime Training Report

- States: 3
- Training rows: 3921
- Log-likelihood: 17847.40
- AIC: -35396.79
- BIC: -34461.95
- Degrees of freedom: [30.0, 30.0, 30.0]

## Transition Matrix
```
[[0.94076299 0.04735414 0.01188287]
 [0.0353862  0.95362297 0.01099082]
 [0.01045821 0.02112559 0.9684162 ]]
```

## Regime Quality
- bull_count: 1204
- bull_mean_fwd_20d: -0.0005629877367799614
- sideways_count: 1702
- sideways_mean_fwd_20d: 0.0027024150336469365
- bear_count: 1015
- bear_mean_fwd_20d: 0.007916834101249468
- return_separation: -0.008479821838029429
- bull_ratio: 0.3070645243560316
- sideways_ratio: 0.43407294057638357
- bear_ratio: 0.2588625350675848
- turnovers: 172
- avg_dwell: 22.664739884393065
- mean_entropy: 1.0752806859091568

## Walk-Forward Results
- 2010-2013 → 2014-2014: separation=0.0139, avg_dwell=26.6
- 2011-2014 → 2015-2015: separation=-0.0366, avg_dwell=26.4
- 2012-2015 → 2016-2016: separation=0.0042, avg_dwell=26.4
- 2013-2016 → 2017-2017: separation=-0.0038, avg_dwell=15.4
- 2014-2017 → 2018-2018: separation=0.0074, avg_dwell=30.7
- 2015-2018 → 2019-2019: separation=-0.0968, avg_dwell=46.2
- 2016-2019 → 2020-2020: separation=0.0254, avg_dwell=23.0
- 2017-2020 → 2021-2021: separation=-0.0100, avg_dwell=26.3
- 2018-2021 → 2022-2022: separation=0.0214, avg_dwell=26.1
- 2019-2022 → 2023-2023: separation=0.0175, avg_dwell=22.9
- 2020-2023 → 2024-2024: separation=0.0098, avg_dwell=15.2
- 2021-2024 → 2025-2025: separation=0.0101, avg_dwell=20.4
- 2022-2025 → 2026-2026: separation=0.0028, avg_dwell=8.8

## Champion Comparison
- Agreement rate: 37.80%
- bull: HMM=-0.0006, Champion=0.0000
- sideways: HMM=0.0027, Champion=0.0020
- bear: HMM=0.0079, Champion=0.0045