# Gann Breach Definition Sweep - Results

Spec: `docs/superpowers/specs/2026-10-16-gann-breach-definition-sweep-design.md`.
RELIANCE is explore-only (its holdout was spent 2026-09-03), so every row of each corpus is read (`--slice all`). Nothing here is confirmed; AAPL is the confirmation.

## Run

- generated: 2026-10-16 20:30
- bars: `C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/bars` (no fetching)
- gate reference: `C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/reliance_5m_x1/events.parquet`
- close1: `C:\Dev\GannTesting\gann-visualizer\backend\logs\corpus\breach_sweep\reliance_5m_x1_close1`
- wick1: `C:\Dev\GannTesting\gann-visualizer\backend\logs\corpus\breach_sweep\reliance_5m_x1_wick1`
- close2: `C:\Dev\GannTesting\gann-visualizer\backend\logs\corpus\breach_sweep\reliance_5m_x1_close2`
- close3: `C:\Dev\GannTesting\gann-visualizer\backend\logs\corpus\breach_sweep\reliance_5m_x1_close3`

## Regression gate - close2 rebuild against the existing corpus

**PASSED** - 5326759 rows match on all 72 columns

## Selection (pre-registered)

**Chosen rule: `close2`** (breach_mode close, confirmation_closes 2)

close2 chosen: best z 4.357; candidates within 0.1 of it: close2; the earliest in the order close1, wick1, close2, close3 wins

- eligible (above all shadows): close1, wick1, close2, close3
- tie candidates (z within 0.1 of the best): close2

Pooled lag-free reach rate, real against the shadows:

| rule | real | n | shadow min | shadow max | missing | above all | z |
|---|---|---|---|---|---|---|---|
| close1 | 0.5219 | 10054 | 0.4996 | 0.5165 | 0 | yes | 3.46 |
| wick1 | 0.5298 | 5344 | 0.5024 | 0.5243 | 0 | yes | 3.61 |
| close2 | 0.5352 | 4555 | 0.5016 | 0.5249 | 0 | yes | 4.36 |
| close3 | 0.5511 | 2446 | 0.5014 | 0.5440 | 0 | yes | 2.85 |

## Dropped share - real against shadow

Rows removed by either lag-free filter over targeted rows. If the real share is outside the shadow range, the filtered real and shadow sets are not like-for-like, and a pass on them reads as "pass, selection differs".

| rule | real dropped | targeted n (raced, timeouts included) | shadow min | shadow max | outside shadow range | entry-only dropped (real) |
|---|---|---|---|---|---|---|
| close1 | 0.4100 | 17044 | 0.3861 | 0.3955 | yes | 0.0000 |
| wick1 | 0.7419 | 20704 | 0.7291 | 0.7411 | yes | 0.5320 |
| close2 | 0.6922 | 14803 | 0.6760 | 0.6854 | yes | 0.0000 |
| close3 | 0.8163 | 13320 | 0.8052 | 0.8129 | yes | 0.0000 |

## Plain reach_next_rate (the old, lag-laden statistic, for reading)

| rule | real | n | shadow min | shadow max | missing | above all | z |
|---|---|---|---|---|---|---|---|
| close1 | 0.6814 | 17042 | 0.6599 | 0.6726 | 0 | yes | 4.90 |
| wick1 | 0.4341 | 20703 | 0.4164 | 0.4216 | 0 | yes | 13.04 |
| close2 | 0.7876 | 14801 | 0.7718 | 0.7760 | 0 | yes | 14.25 |
| close3 | 0.8420 | 13319 | 0.8270 | 0.8326 | 0 | yes | 8.29 |

## Touch density - the fairness check

| rule | real | n | shadow min | shadow max | missing | above all | z |
|---|---|---|---|---|---|---|---|
| close1 | 0.7423 | 24646 | 0.7186 | 0.7386 | 0 | yes | 2.83 |
| wick1 | 0.1625 | 4764 | 0.1126 | 0.1294 | 0 | yes | 9.40 |
| close2 | 0.8395 | 29963 | 0.8100 | 0.8342 | 0 | yes | 2.70 |
| close3 | 0.9045 | 32927 | 0.8793 | 0.9058 | 0 | no | 2.07 |

## The 13 pre-declared groups, lag-free reach rate

### close1

| group | real | n | shadow min | shadow max | missing | above all | z |
|---|---|---|---|---|---|---|---|
| level_source=center | 0.5425 | 2638 | 0.5086 | 0.5314 | 0 | yes | 4.73 |
| level_source=moon | 0.5028 | 4640 | 0.4785 | 0.5081 | 0 | no | 1.48 |
| level_source=sun | 0.5342 | 2776 | 0.5146 | 0.5298 | 0 | yes | 2.87 |
| level_ring_bin=10-19 | 0.5268 | 9427 | 0.5032 | 0.5179 | 0 | yes | 4.79 |
| level_kind=sub | 0.5191 | 8944 | 0.4991 | 0.5164 | 0 | yes | 2.70 |
| level_kind=major | 0.5441 | 1110 | 0.4979 | 0.5272 | 0 | yes | 4.22 |
| level_is_halfway=False | 0.5221 | 8822 | 0.5002 | 0.5165 | 0 | yes | 3.99 |
| level_is_halfway=True | 0.5203 | 1232 | 0.4866 | 0.5287 | 0 | no | 1.21 |
| level_degree=0 | 0.5390 | 1447 | 0.4984 | 0.5233 | 0 | yes | 4.49 |
| level_degree=90 | 0.5041 | 1591 | 0.4769 | 0.4975 | 0 | yes | 2.92 |
| level_degree=135 | 0.5295 | 1188 | 0.4756 | 0.5180 | 0 | yes | 2.93 |
| level_degree=225 | 0.5085 | 1001 | 0.4530 | 0.5068 | 0 | yes | 2.03 |
| level_sub_index=5 | 0.5493 | 1298 | 0.4862 | 0.5181 | 0 | yes | 5.42 |

### wick1

| group | real | n | shadow min | shadow max | missing | above all | z |
|---|---|---|---|---|---|---|---|
| level_source=center | 0.5401 | 1348 | 0.5074 | 0.5459 | 0 | no | 1.68 |
| level_source=moon | 0.5106 | 2605 | 0.4751 | 0.5183 | 0 | no | 1.45 |
| level_source=sun | 0.5557 | 1391 | 0.5116 | 0.5528 | 0 | yes | 2.16 |
| level_ring_bin=10-19 | 0.5327 | 5007 | 0.5032 | 0.5226 | 0 | yes | 4.58 |
| level_kind=sub | 0.5288 | 4735 | 0.5008 | 0.5210 | 0 | yes | 3.74 |
| level_kind=major | 0.5369 | 609 | 0.5080 | 0.5508 | 0 | no | 0.66 |
| level_is_halfway=False | 0.5311 | 4690 | 0.5040 | 0.5270 | 0 | yes | 3.52 |
| level_is_halfway=True | 0.5199 | 654 | 0.4775 | 0.5191 | 0 | yes | 2.28 |
| level_degree=0 | 0.5777 | 772 | 0.5138 | 0.5533 | 0 | yes | 4.99 |
| level_degree=90 | 0.5152 | 788 | 0.4664 | 0.5076 | 0 | yes | 2.76 |
| level_degree=135 | 0.5008 | 607 | 0.4867 | 0.5259 | 0 | no | 0.22 |
| level_degree=225 | 0.5149 | 538 | 0.4338 | 0.5321 | 0 | no | 1.02 |
| level_sub_index=5 | 0.5556 | 666 | 0.4936 | 0.5281 | 0 | yes | 4.70 |

### close2

| group | real | n | shadow min | shadow max | missing | above all | z |
|---|---|---|---|---|---|---|---|
| level_source=center | 0.5506 | 1177 | 0.5077 | 0.5385 | 0 | yes | 3.85 |
| level_source=moon | 0.5265 | 2097 | 0.4911 | 0.5286 | 0 | no | 2.63 |
| level_source=sun | 0.5355 | 1281 | 0.5097 | 0.5357 | 0 | no | 2.29 |
| level_ring_bin=10-19 | 0.5365 | 4207 | 0.5032 | 0.5256 | 0 | yes | 4.99 |
| level_kind=sub | 0.5355 | 4084 | 0.5006 | 0.5253 | 0 | yes | 4.77 |
| level_kind=major | 0.5329 | 471 | 0.4827 | 0.5503 | 0 | no | 1.38 |
| level_is_halfway=False | 0.5308 | 3977 | 0.4999 | 0.5265 | 0 | yes | 2.96 |
| level_is_halfway=True | 0.5657 | 578 | 0.4863 | 0.5332 | 0 | yes | 4.43 |
| level_degree=0 | 0.5526 | 666 | 0.4743 | 0.5495 | 0 | yes | 1.71 |
| level_degree=90 | 0.5210 | 737 | 0.4745 | 0.5193 | 0 | yes | 2.78 |
| level_degree=135 | 0.5422 | 533 | 0.4732 | 0.5556 | 0 | no | 1.06 |
| level_degree=225 | 0.5406 | 468 | 0.4626 | 0.5312 | 0 | yes | 2.31 |
| level_sub_index=5 | 0.5583 | 575 | 0.4792 | 0.5274 | 0 | yes | 4.34 |

### close3

| group | real | n | shadow min | shadow max | missing | above all | z |
|---|---|---|---|---|---|---|---|
| level_source=center | 0.5587 | 605 | 0.5118 | 0.5596 | 0 | no | 2.35 |
| level_source=moon | 0.5387 | 1151 | 0.4836 | 0.5448 | 0 | no | 1.89 |
| level_source=sun | 0.5652 | 690 | 0.5013 | 0.5554 | 0 | yes | 2.80 |
| level_ring_bin=10-19 | 0.5514 | 2229 | 0.5037 | 0.5381 | 0 | yes | 3.57 |
| level_kind=sub | 0.5538 | 2185 | 0.5024 | 0.5429 | 0 | yes | 3.33 |
| level_kind=major | 0.5287 | 261 | 0.4477 | 0.5754 | 0 | no | 0.62 |
| level_is_halfway=False | 0.5390 | 2130 | 0.4955 | 0.5516 | 0 | no | 1.50 |
| level_is_halfway=True | 0.6329 | 316 | 0.4820 | 0.5759 | 0 | yes | 4.71 |
| level_degree=0 | 0.5665 | 346 | 0.4809 | 0.5643 | 0 | yes | 2.18 |
| level_degree=90 | 0.5631 | 428 | 0.4395 | 0.5381 | 0 | yes | 3.18 |
| level_degree=135 | 0.5668 | 277 | 0.4624 | 0.5864 | 0 | no | 1.11 |
| level_degree=225 | 0.5455 | 253 | 0.4531 | 0.5339 | 0 | yes | 2.15 |
| level_sub_index=5 | 0.5719 | 292 | 0.5000 | 0.5623 | 0 | yes | 2.42 |
