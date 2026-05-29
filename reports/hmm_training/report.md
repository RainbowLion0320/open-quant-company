# HMM Regime Training Report

- States: 3
- Training rows: 1977
- Log-likelihood: 9541.79
- AIC: -18785.58
- BIC: -17952.77
- Degrees of freedom: [30.0, 30.0, 30.0]

## Transition Matrix
```
[[0.97483178 0.01215646 0.01301176]
 [0.03591182 0.9542814  0.00980679]
 [0.01020465 0.02798697 0.96180838]]
```

## Regime Quality
- bull_count: 964
- bull_mean_fwd_20d: -0.0036957266298101076
- sideways_count: 547
- sideways_mean_fwd_20d: 0.009527439148875478
- bear_count: 466
- bear_mean_fwd_20d: 0.008434247014019415
- return_separation: -0.012129973643829523
- bull_ratio: 0.4876074860900354
- sideways_ratio: 0.2766818411734952
- bear_ratio: 0.2357106727364694
- turnovers: 63
- avg_dwell: 30.890625
- mean_entropy: 1.0464161246538444

## Walk-Forward Results
- 2018-2021 → 2022-2022: separation=0.0214, avg_dwell=26.1
- 2019-2022 → 2023-2023: separation=0.0175, avg_dwell=22.9
- 2020-2023 → 2024-2024: separation=0.0098, avg_dwell=15.2
- 2021-2024 → 2025-2025: separation=0.0101, avg_dwell=20.4
- 2022-2025 → 2026-2026: separation=0.0028, avg_dwell=8.8

## Champion Comparison
- Agreement rate: 28.53%
- bull: HMM=-0.0037, Champion=0.0000
- sideways: HMM=0.0095, Champion=0.0014
- bear: HMM=0.0084, Champion=0.0050