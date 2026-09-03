# Gann Corpus Mining Report

**These are candidates, not findings.** Nothing below is confirmed. Every
number here comes from the explore slice, which the search has already seen,
so any group that looks strong is a hypothesis to test against the holdout -
once, in a batch, with the result recorded whichever way it falls.

No multiple-comparison correction is applied and none is needed, because
nothing here concludes. Correction belongs at holdout confirmation, against a
shortlist declared before that data is opened.

## Run

- slice: holdout
- corpus: `logs\corpus\reliance_5m_x1`
- symbol: RELIANCE, interval 5, scale x1
- shadows: 50
- holdout events used: 1331690
- dropped to the boundary buffer: 0 (events within 50 bars of holdout boundary bar 28166, whose outcomes would have been decided by holdout price action)

## Fairness check - read this first

Touches per bar, real against shadow. These should be close. A large
gap means the two ladders get different exposure to price, and every
comparison below it is measuring that gap rather than the levels.

| group | real | n | shadow min | shadow median | shadow max | pct |
|---|---|---|---|---|---|---|
| touch_density | 0.8810 | 7554 | 0.8369 | 0.8532 | 0.8729 | 100.0 |

## Per group

### hold_rate

| group | real | n | shadow min | shadow median | shadow max | pct |
|---|---|---|---|---|---|---|
| level_degree=0 | 0.3066 | 137 | 0.2846 | 0.3160 | 0.3453 | 32.0 |
| level_degree=45 | 0.2395 | 263 | 0.2428 | 0.2643 | 0.2956 | 0.0 |
| level_degree=90 | 0.3048 | 420 | 0.2488 | 0.2780 | 0.2979 | 100.0 |
| level_degree=135 | 0.2457 | 525 | 0.2335 | 0.2462 | 0.2618 | 50.0 |
| level_degree=180 | 0.2870 | 648 | 0.2519 | 0.2665 | 0.2918 | 92.0 |
| level_degree=225 | 0.2588 | 568 | 0.2315 | 0.2486 | 0.2694 | 82.0 |
| level_degree=270 | 0.3365 | 416 | 0.3114 | 0.3244 | 0.3449 | 84.0 |
| level_degree=315 | 0.2253 | 364 | 0.2249 | 0.2476 | 0.2632 | 2.0 |
| level_is_halfway=False | 0.2660 | 2929 | 0.2557 | 0.2608 | 0.2693 | 86.0 |
| level_is_halfway=True | 0.3350 | 412 | 0.3083 | 0.3297 | 0.3488 | 64.0 |
| level_kind=major | 0.2420 | 376 | 0.1995 | 0.2247 | 0.2401 | 100.0 |
| level_kind=sub | 0.2786 | 2965 | 0.2697 | 0.2758 | 0.2824 | 74.0 |
| level_ring_bin=10-19 | 0.2745 | 3341 | 0.2628 | 0.2697 | 0.2760 | 92.0 |
| level_source=center | 0.2864 | 894 | 0.2667 | 0.2794 | 0.2921 | 82.0 |
| level_source=moon | 0.2660 | 1440 | 0.2466 | 0.2560 | 0.2640 | 100.0 |
| level_source=sun | 0.2761 | 1007 | 0.2648 | 0.2824 | 0.2969 | 26.0 |
| level_sub_index=1 | 0.2667 | 420 | 0.2592 | 0.2727 | 0.2833 | 14.0 |
| level_sub_index=2 | 0.2517 | 429 | 0.2458 | 0.2613 | 0.2771 | 10.0 |
| level_sub_index=3 | 0.2820 | 422 | 0.2701 | 0.2940 | 0.3174 | 10.0 |
| level_sub_index=4 | 0.3350 | 412 | 0.3083 | 0.3297 | 0.3488 | 64.0 |
| level_sub_index=5 | 0.3061 | 428 | 0.2391 | 0.2717 | 0.2904 | 100.0 |
| level_sub_index=6 | 0.2682 | 425 | 0.2286 | 0.2488 | 0.2607 | 100.0 |
| level_sub_index=7 | 0.2424 | 429 | 0.2309 | 0.2599 | 0.2898 | 6.0 |
| level_sub_index=none | 0.2420 | 376 | 0.1995 | 0.2247 | 0.2401 | 100.0 |

### mean_retest_depth

| group | real | n | shadow min | shadow median | shadow max | pct |
|---|---|---|---|---|---|---|
| level_degree=0 | 0.1642 | 137 | 0.0539 | 0.1753 | 0.2541 | 40.0 |
| level_degree=45 | 0.1855 | 262 | 0.0546 | 0.1345 | 0.1936 | 92.0 |
| level_degree=90 | 0.2753 | 414 | 0.1595 | 0.2003 | 0.2658 | 100.0 |
| level_degree=135 | -0.0479 | 525 | -0.0836 | -0.0526 | -0.0246 | 60.0 |
| level_degree=180 | -0.0694 | 661 | -0.0692 | -0.0177 | 0.0254 | 0.0 |
| level_degree=225 | 0.1082 | 568 | 0.0537 | 0.1408 | 0.1740 | 28.0 |
| level_degree=270 | 0.0141 | 416 | -0.0430 | -0.0062 | 0.0844 | 78.0 |
| level_degree=315 | 0.0257 | 364 | 0.0050 | 0.0403 | 0.1149 | 36.0 |
| level_is_halfway=False | 0.0718 | 2932 | 0.0538 | 0.0660 | 0.0937 | 66.0 |
| level_is_halfway=True | -0.0478 | 415 | -0.0773 | -0.0338 | 0.0352 | 28.0 |
| level_kind=major | 0.5619 | 375 | 0.3647 | 0.4112 | 0.6049 | 94.0 |
| level_kind=sub | -0.0067 | 2972 | -0.0082 | 0.0114 | 0.0262 | 6.0 |
| level_ring_bin=10-19 | 0.0570 | 3347 | 0.0380 | 0.0555 | 0.0864 | 54.0 |
| level_source=center | 0.0103 | 894 | -0.0065 | 0.0434 | 0.0932 | 22.0 |
| level_source=moon | 0.0881 | 1443 | 0.0664 | 0.0950 | 0.1504 | 28.0 |
| level_source=sun | 0.0539 | 1010 | -0.0133 | 0.0128 | 0.0509 | 100.0 |
| level_sub_index=1 | -0.0581 | 420 | -0.1005 | -0.0566 | -0.0070 | 50.0 |
| level_sub_index=2 | -0.0315 | 429 | -0.0289 | 0.0224 | 0.0570 | 0.0 |
| level_sub_index=3 | -0.0080 | 421 | -0.0014 | 0.0494 | 0.0821 | 0.0 |
| level_sub_index=4 | -0.0478 | 415 | -0.0773 | -0.0338 | 0.0352 | 28.0 |
| level_sub_index=5 | 0.0023 | 431 | 0.0160 | 0.0529 | 0.1112 | 0.0 |
| level_sub_index=6 | 0.0433 | 427 | -0.0071 | 0.0217 | 0.0894 | 64.0 |
| level_sub_index=7 | 0.0506 | 429 | -0.0384 | 0.0048 | 0.0480 | 100.0 |
| level_sub_index=none | 0.5619 | 375 | 0.3647 | 0.4112 | 0.6049 | 94.0 |

### reach_next_rate

| group | real | n | shadow min | shadow median | shadow max | pct |
|---|---|---|---|---|---|---|
| level_degree=0 | 0.8385 | 161 | 0.8025 | 0.8364 | 0.8598 | 66.0 |
| level_degree=45 | 0.8701 | 308 | 0.8408 | 0.8613 | 0.8805 | 72.0 |
| level_degree=90 | 0.8111 | 450 | 0.7744 | 0.7939 | 0.8085 | 100.0 |
| level_degree=135 | 0.7776 | 562 | 0.7522 | 0.7778 | 0.7956 | 48.0 |
| level_degree=180 | 0.7911 | 723 | 0.7190 | 0.7354 | 0.7668 | 100.0 |
| level_degree=225 | 0.7910 | 622 | 0.7656 | 0.7749 | 0.7919 | 98.0 |
| level_degree=270 | 0.8220 | 472 | 0.8081 | 0.8188 | 0.8406 | 70.0 |
| level_degree=315 | 0.7961 | 407 | 0.7650 | 0.7843 | 0.8086 | 84.0 |
| level_is_halfway=False | 0.8015 | 3249 | 0.7730 | 0.7838 | 0.7923 | 100.0 |
| level_is_halfway=True | 0.8268 | 456 | 0.7783 | 0.8214 | 0.8352 | 86.0 |
| level_kind=major | 0.8184 | 446 | 0.7571 | 0.7892 | 0.8131 | 100.0 |
| level_kind=sub | 0.8027 | 3259 | 0.7790 | 0.7878 | 0.7954 | 100.0 |
| level_ring_bin=10-19 | 0.8046 | 3705 | 0.7784 | 0.7873 | 0.7975 | 100.0 |
| level_source=center | 0.8250 | 1000 | 0.7636 | 0.7941 | 0.8207 | 100.0 |
| level_source=moon | 0.8006 | 1585 | 0.7605 | 0.7729 | 0.7855 | 100.0 |
| level_source=sun | 0.7920 | 1120 | 0.7889 | 0.7980 | 0.8209 | 22.0 |
| level_sub_index=1 | 0.7741 | 456 | 0.7646 | 0.7849 | 0.8206 | 12.0 |
| level_sub_index=2 | 0.7961 | 466 | 0.7253 | 0.7577 | 0.7978 | 98.0 |
| level_sub_index=3 | 0.8272 | 463 | 0.7778 | 0.7934 | 0.8180 | 100.0 |
| level_sub_index=4 | 0.8268 | 456 | 0.7783 | 0.8214 | 0.8352 | 86.0 |
| level_sub_index=5 | 0.8093 | 472 | 0.7588 | 0.7817 | 0.8046 | 100.0 |
| level_sub_index=6 | 0.7940 | 466 | 0.7748 | 0.7934 | 0.8072 | 52.0 |
| level_sub_index=7 | 0.7917 | 480 | 0.7691 | 0.7787 | 0.8172 | 86.0 |
| level_sub_index=none | 0.8184 | 446 | 0.7571 | 0.7892 | 0.8131 | 100.0 |

### rejection_rate

| group | real | n | shadow min | shadow median | shadow max | pct |
|---|---|---|---|---|---|---|
| level_degree=0 | 0.2184 | 206 | 0.1970 | 0.2217 | 0.2500 | 46.0 |
| level_degree=45 | 0.2117 | 392 | 0.2327 | 0.2436 | 0.2650 | 0.0 |
| level_degree=90 | 0.2908 | 643 | 0.2581 | 0.2782 | 0.3169 | 70.0 |
| level_degree=135 | 0.2364 | 736 | 0.2432 | 0.2643 | 0.2835 | 0.0 |
| level_degree=180 | 0.2866 | 998 | 0.2787 | 0.2910 | 0.3059 | 32.0 |
| level_degree=225 | 0.2924 | 879 | 0.2771 | 0.2862 | 0.3035 | 72.0 |
| level_degree=270 | 0.2250 | 609 | 0.2311 | 0.2464 | 0.2787 | 0.0 |
| level_degree=315 | 0.3306 | 608 | 0.2828 | 0.3064 | 0.3250 | 100.0 |
| level_is_halfway=False | 0.2709 | 4452 | 0.2734 | 0.2785 | 0.2828 | 0.0 |
| level_is_halfway=True | 0.2649 | 619 | 0.2336 | 0.2525 | 0.2804 | 82.0 |
| level_kind=major | 0.2802 | 621 | 0.2547 | 0.2937 | 0.3103 | 16.0 |
| level_kind=sub | 0.2688 | 4450 | 0.2660 | 0.2743 | 0.2825 | 14.0 |
| level_ring_bin=10-19 | 0.2702 | 5071 | 0.2697 | 0.2756 | 0.2803 | 4.0 |
| level_source=center | 0.2769 | 1383 | 0.2620 | 0.2804 | 0.3023 | 40.0 |
| level_source=moon | 0.2764 | 2189 | 0.2615 | 0.2743 | 0.2861 | 66.0 |
| level_source=sun | 0.2548 | 1499 | 0.2524 | 0.2692 | 0.2882 | 2.0 |
| level_sub_index=1 | 0.2853 | 638 | 0.2500 | 0.2937 | 0.3217 | 28.0 |
| level_sub_index=2 | 0.2568 | 627 | 0.2419 | 0.2768 | 0.3109 | 22.0 |
| level_sub_index=3 | 0.2905 | 654 | 0.2694 | 0.2884 | 0.3078 | 68.0 |
| level_sub_index=4 | 0.2649 | 619 | 0.2336 | 0.2525 | 0.2804 | 82.0 |
| level_sub_index=5 | 0.2423 | 619 | 0.2429 | 0.2700 | 0.2952 | 0.0 |
| level_sub_index=6 | 0.2658 | 632 | 0.2382 | 0.2703 | 0.2879 | 32.0 |
| level_sub_index=7 | 0.2738 | 661 | 0.2452 | 0.2623 | 0.3100 | 76.0 |
| level_sub_index=none | 0.2802 | 621 | 0.2547 | 0.2937 | 0.3103 | 16.0 |

### timeout_share

| group | real | n | shadow min | shadow median | shadow max | pct |
|---|---|---|---|---|---|---|
| level_degree=0 | 0.0000 | 161 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_degree=45 | 0.0000 | 308 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_degree=90 | 0.0000 | 450 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_degree=135 | 0.0000 | 562 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_degree=180 | 0.0028 | 725 | 0.0000 | 0.0000 | 0.0014 | 100.0 |
| level_degree=225 | 0.0000 | 622 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_degree=270 | 0.0000 | 472 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_degree=315 | 0.0000 | 407 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_is_halfway=False | 0.0000 | 3249 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_is_halfway=True | 0.0044 | 458 | 0.0000 | 0.0000 | 0.0022 | 100.0 |
| level_kind=major | 0.0000 | 446 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_kind=sub | 0.0006 | 3261 | 0.0000 | 0.0000 | 0.0003 | 100.0 |
| level_ring_bin=10-19 | 0.0005 | 3707 | 0.0000 | 0.0000 | 0.0003 | 100.0 |
| level_source=center | 0.0000 | 1000 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_source=moon | 0.0013 | 1587 | 0.0000 | 0.0000 | 0.0006 | 100.0 |
| level_source=sun | 0.0000 | 1120 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_sub_index=1 | 0.0000 | 456 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_sub_index=2 | 0.0000 | 466 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_sub_index=3 | 0.0000 | 463 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_sub_index=4 | 0.0044 | 458 | 0.0000 | 0.0000 | 0.0022 | 100.0 |
| level_sub_index=5 | 0.0000 | 472 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_sub_index=6 | 0.0000 | 466 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_sub_index=7 | 0.0000 | 480 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_sub_index=none | 0.0000 | 446 | 0.0000 | 0.0000 | 0.0000 | 0.0 |

### touch_density

| group | real | n | shadow min | shadow median | shadow max | pct |
|---|---|---|---|---|---|---|
| level_degree=0 | 0.0336 | 288 | 0.0304 | 0.0324 | 0.0358 | 80.0 |
| level_degree=45 | 0.0639 | 548 | 0.0608 | 0.0672 | 0.0725 | 18.0 |
| level_degree=90 | 0.1114 | 955 | 0.1053 | 0.1109 | 0.1198 | 54.0 |
| level_degree=135 | 0.1246 | 1068 | 0.1164 | 0.1221 | 0.1290 | 68.0 |
| level_degree=180 | 0.1887 | 1618 | 0.1689 | 0.1824 | 0.1896 | 84.0 |
| level_degree=225 | 0.1606 | 1377 | 0.1356 | 0.1481 | 0.1556 | 100.0 |
| level_degree=270 | 0.1035 | 887 | 0.0931 | 0.1002 | 0.1064 | 86.0 |
| level_degree=315 | 0.0948 | 813 | 0.0837 | 0.0939 | 0.0980 | 56.0 |
| level_is_halfway=False | 0.7723 | 6622 | 0.7263 | 0.7508 | 0.7666 | 100.0 |
| level_is_halfway=True | 0.1087 | 932 | 0.0980 | 0.1040 | 0.1186 | 86.0 |
| level_kind=major | 0.1057 | 906 | 0.0830 | 0.0862 | 0.0906 | 100.0 |
| level_kind=sub | 0.7754 | 6648 | 0.7477 | 0.7676 | 0.7856 | 72.0 |
| level_ring_bin=10-19 | 0.8810 | 7554 | 0.8369 | 0.8532 | 0.8729 | 100.0 |
| level_source=center | 0.2190 | 1878 | 0.2175 | 0.2292 | 0.2400 | 2.0 |
| level_source=moon | 0.4040 | 3464 | 0.3649 | 0.3775 | 0.3960 | 100.0 |
| level_source=sun | 0.2580 | 2212 | 0.2403 | 0.2470 | 0.2594 | 98.0 |
| level_sub_index=1 | 0.1139 | 977 | 0.1073 | 0.1167 | 0.1250 | 16.0 |
| level_sub_index=2 | 0.1209 | 1037 | 0.1030 | 0.1111 | 0.1201 | 100.0 |
| level_sub_index=3 | 0.1057 | 906 | 0.1025 | 0.1098 | 0.1216 | 20.0 |
| level_sub_index=4 | 0.1087 | 932 | 0.0980 | 0.1040 | 0.1186 | 86.0 |
| level_sub_index=5 | 0.1046 | 897 | 0.1029 | 0.1074 | 0.1149 | 4.0 |
| level_sub_index=6 | 0.1130 | 969 | 0.1010 | 0.1059 | 0.1171 | 80.0 |
| level_sub_index=7 | 0.1085 | 930 | 0.1017 | 0.1093 | 0.1181 | 36.0 |
| level_sub_index=none | 0.1057 | 906 | 0.0830 | 0.0862 | 0.0906 | 100.0 |

## Shortlist

Groups whose real value falls outside the **entire** shadow range,
sorted by how far outside. Sample size is in the table because a
rate built on a handful of events lands outside the range easily and
means nothing.

| group | statistic | real | n | shadow min | shadow max | margin |
|---|---|---|---|---|---|---|
| level_degree=180 | reach_next_rate | 0.7911 | n=723 | 0.7190 | 0.7668 | 0.0244 |
| level_degree=45 | rejection_rate | 0.2117 | n=392 | 0.2327 | 0.2650 | -0.0209 |
| level_sub_index=5 | hold_rate | 0.3061 | n=428 | 0.2391 | 0.2904 | 0.0157 |
| level_source=moon | reach_next_rate | 0.8006 | n=1585 | 0.7605 | 0.7855 | 0.0151 |
| level_sub_index=none | touch_density | 0.1057 | n=906 | 0.0830 | 0.0906 | 0.0150 |
| level_kind=major | touch_density | 0.1057 | n=906 | 0.0830 | 0.0906 | 0.0150 |
| level_sub_index=5 | mean_retest_depth | 0.0023 | n=431 | 0.0160 | 0.1112 | -0.0138 |
| level_degree=90 | mean_retest_depth | 0.2753 | n=414 | 0.1595 | 0.2658 | 0.0096 |
| level_sub_index=3 | reach_next_rate | 0.8272 | n=463 | 0.7778 | 0.8180 | 0.0092 |
| level_is_halfway=False | reach_next_rate | 0.8015 | n=3249 | 0.7730 | 0.7923 | 0.0091 |
| level_ring_bin=10-19 | touch_density | 0.8810 | n=7554 | 0.8369 | 0.8729 | 0.0082 |
| level_source=moon | touch_density | 0.4040 | n=3464 | 0.3649 | 0.3960 | 0.0080 |
| level_sub_index=6 | hold_rate | 0.2682 | n=425 | 0.2286 | 0.2607 | 0.0076 |
| level_kind=sub | reach_next_rate | 0.8027 | n=3259 | 0.7790 | 0.7954 | 0.0073 |
| level_ring_bin=10-19 | reach_next_rate | 0.8046 | n=3705 | 0.7784 | 0.7975 | 0.0071 |
| level_degree=90 | hold_rate | 0.3048 | n=420 | 0.2488 | 0.2979 | 0.0069 |
| level_degree=135 | rejection_rate | 0.2364 | n=736 | 0.2432 | 0.2835 | -0.0068 |
| level_sub_index=3 | mean_retest_depth | -0.0080 | n=421 | -0.0014 | 0.0821 | -0.0066 |
| level_degree=270 | rejection_rate | 0.2250 | n=609 | 0.2311 | 0.2787 | -0.0062 |
| level_is_halfway=False | touch_density | 0.7723 | n=6622 | 0.7263 | 0.7666 | 0.0057 |
| level_degree=315 | rejection_rate | 0.3306 | n=608 | 0.2828 | 0.3250 | 0.0056 |
| level_sub_index=none | reach_next_rate | 0.8184 | n=446 | 0.7571 | 0.8131 | 0.0053 |
| level_kind=major | reach_next_rate | 0.8184 | n=446 | 0.7571 | 0.8131 | 0.0053 |
| level_degree=225 | touch_density | 0.1606 | n=1377 | 0.1356 | 0.1556 | 0.0050 |
| level_sub_index=5 | reach_next_rate | 0.8093 | n=472 | 0.7588 | 0.8046 | 0.0047 |
| level_source=center | reach_next_rate | 0.8250 | n=1000 | 0.7636 | 0.8207 | 0.0043 |
| level_degree=45 | hold_rate | 0.2395 | n=263 | 0.2428 | 0.2956 | -0.0032 |
| level_source=sun | mean_retest_depth | 0.0539 | n=1010 | -0.0133 | 0.0509 | 0.0030 |
| level_degree=90 | reach_next_rate | 0.8111 | n=450 | 0.7744 | 0.8085 | 0.0026 |
| level_sub_index=7 | mean_retest_depth | 0.0506 | n=429 | -0.0384 | 0.0480 | 0.0026 |
| level_sub_index=2 | mean_retest_depth | -0.0315 | n=429 | -0.0289 | 0.0570 | -0.0026 |
| level_is_halfway=False | rejection_rate | 0.2709 | n=4452 | 0.2734 | 0.2828 | -0.0025 |
| level_sub_index=4 | timeout_share | 0.0044 | n=458 | 0.0000 | 0.0022 | 0.0022 |
| level_is_halfway=True | timeout_share | 0.0044 | n=458 | 0.0000 | 0.0022 | 0.0022 |
| level_source=moon | hold_rate | 0.2660 | n=1440 | 0.2466 | 0.2640 | 0.0020 |
| level_sub_index=none | hold_rate | 0.2420 | n=376 | 0.1995 | 0.2401 | 0.0019 |
| level_kind=major | hold_rate | 0.2420 | n=376 | 0.1995 | 0.2401 | 0.0019 |
| level_degree=180 | timeout_share | 0.0028 | n=725 | 0.0000 | 0.0014 | 0.0014 |
| level_sub_index=2 | touch_density | 0.1209 | n=1037 | 0.1030 | 0.1201 | 0.0008 |
| level_source=moon | timeout_share | 0.0013 | n=1587 | 0.0000 | 0.0006 | 0.0006 |
| level_sub_index=5 | rejection_rate | 0.2423 | n=619 | 0.2429 | 0.2952 | -0.0006 |
| level_kind=sub | timeout_share | 0.0006 | n=3261 | 0.0000 | 0.0003 | 0.0003 |
| level_ring_bin=10-19 | timeout_share | 0.0005 | n=3707 | 0.0000 | 0.0003 | 0.0003 |
| level_degree=180 | mean_retest_depth | -0.0694 | n=661 | -0.0692 | 0.0254 | -0.0002 |
