# Gann Corpus Mining Report

**These are candidates, not findings.** Nothing below is confirmed. Every
number here comes from the explore slice, which the search has already seen,
so any group that looks strong is a hypothesis to test against the holdout -
once, in a batch, with the result recorded whichever way it falls.

No multiple-comparison correction is applied and none is needed, because
nothing here concludes. Correction belongs at holdout confirmation, against a
shortlist declared before that data is opened.

## Run

- corpus: `logs\corpus\reliance_5m_x1`
- symbol: RELIANCE, interval 5, scale x1
- shadows: 50
- explore events used: 3989422
- dropped to the boundary buffer: 5647 (events within 50 bars of holdout boundary bar 28166, whose outcomes would have been decided by holdout price action)

## Fairness check - read this first

Touches per bar, real against shadow. These should be close. A large
gap means the two ladders get different exposure to price, and every
comparison below it is measuring that gap rather than the levels.

| group | real | n | shadow min | shadow median | shadow max | pct |
|---|---|---|---|---|---|---|
| touch_density | 0.8271 | 22391 | 0.8015 | 0.8147 | 0.8295 | 98.0 |

## Per group

### hold_rate

| group | real | n | shadow min | shadow median | shadow max | pct |
|---|---|---|---|---|---|---|
| level_degree=0 | 0.2629 | 1742 | 0.2490 | 0.2565 | 0.2685 | 88.0 |
| level_degree=45 | 0.2655 | 1842 | 0.2475 | 0.2603 | 0.2740 | 74.0 |
| level_degree=90 | 0.2300 | 1574 | 0.2119 | 0.2182 | 0.2293 | 100.0 |
| level_degree=135 | 0.2576 | 1048 | 0.2384 | 0.2510 | 0.2621 | 80.0 |
| level_degree=180 | 0.2430 | 1033 | 0.2399 | 0.2483 | 0.2606 | 16.0 |
| level_degree=225 | 0.2157 | 853 | 0.1956 | 0.2159 | 0.2342 | 48.0 |
| level_degree=270 | 0.2449 | 788 | 0.2303 | 0.2478 | 0.2605 | 32.0 |
| level_degree=315 | 0.2369 | 1148 | 0.2138 | 0.2267 | 0.2357 | 100.0 |
| level_is_halfway=False | 0.2439 | 8728 | 0.2362 | 0.2406 | 0.2449 | 88.0 |
| level_is_halfway=True | 0.2692 | 1300 | 0.2443 | 0.2545 | 0.2645 | 100.0 |
| level_kind=major | 0.2132 | 1140 | 0.1995 | 0.2071 | 0.2186 | 84.0 |
| level_kind=sub | 0.2516 | 8888 | 0.2417 | 0.2462 | 0.2531 | 94.0 |
| level_ring_bin=10-19 | 0.2452 | 9249 | 0.2347 | 0.2399 | 0.2463 | 94.0 |
| level_ring_bin=20-29 | 0.2709 | 779 | 0.2530 | 0.2686 | 0.2859 | 56.0 |
| level_source=center | 0.2469 | 2620 | 0.2303 | 0.2413 | 0.2471 | 98.0 |
| level_source=moon | 0.2438 | 4361 | 0.2302 | 0.2365 | 0.2412 | 100.0 |
| level_source=sun | 0.2524 | 3047 | 0.2455 | 0.2533 | 0.2626 | 44.0 |
| level_sub_index=1 | 0.2577 | 1226 | 0.2318 | 0.2567 | 0.2724 | 58.0 |
| level_sub_index=2 | 0.2480 | 1266 | 0.2351 | 0.2405 | 0.2545 | 84.0 |
| level_sub_index=3 | 0.2553 | 1281 | 0.2500 | 0.2598 | 0.2712 | 24.0 |
| level_sub_index=4 | 0.2692 | 1300 | 0.2443 | 0.2545 | 0.2645 | 100.0 |
| level_sub_index=5 | 0.2533 | 1287 | 0.2244 | 0.2356 | 0.2490 | 100.0 |
| level_sub_index=6 | 0.2254 | 1269 | 0.2204 | 0.2331 | 0.2465 | 18.0 |
| level_sub_index=7 | 0.2518 | 1259 | 0.2306 | 0.2486 | 0.2543 | 74.0 |
| level_sub_index=none | 0.2132 | 1140 | 0.1995 | 0.2071 | 0.2186 | 84.0 |

### mean_retest_depth

| group | real | n | shadow min | shadow median | shadow max | pct |
|---|---|---|---|---|---|---|
| level_degree=0 | -0.0020 | 1754 | -0.0333 | -0.0005 | 0.0503 | 42.0 |
| level_degree=45 | 0.0320 | 1859 | 0.0154 | 0.0465 | 0.0558 | 4.0 |
| level_degree=90 | -0.0050 | 1586 | 0.0006 | 0.0359 | 0.0752 | 0.0 |
| level_degree=135 | 0.0409 | 1048 | 0.0308 | 0.0611 | 0.0915 | 12.0 |
| level_degree=180 | 0.0601 | 1033 | 0.0023 | 0.0373 | 0.0881 | 84.0 |
| level_degree=225 | 0.0966 | 853 | 0.0346 | 0.0834 | 0.1141 | 74.0 |
| level_degree=270 | 0.1618 | 788 | 0.1257 | 0.2040 | 0.2625 | 26.0 |
| level_degree=315 | 0.1299 | 1148 | 0.0778 | 0.1261 | 0.1507 | 60.0 |
| level_is_halfway=False | 0.0591 | 8763 | 0.0577 | 0.0665 | 0.0743 | 2.0 |
| level_is_halfway=True | -0.0046 | 1306 | 0.0255 | 0.0395 | 0.0705 | 0.0 |
| level_kind=major | 0.4618 | 1144 | 0.4277 | 0.4690 | 0.5673 | 30.0 |
| level_kind=sub | -0.0018 | 8925 | 0.0006 | 0.0091 | 0.0189 | 0.0 |
| level_ring_bin=10-19 | 0.0627 | 9290 | 0.0624 | 0.0704 | 0.0791 | 2.0 |
| level_ring_bin=20-29 | -0.0902 | 779 | -0.0607 | -0.0378 | -0.0134 | 0.0 |
| level_source=center | 0.0115 | 2633 | 0.0306 | 0.0448 | 0.0659 | 0.0 |
| level_source=moon | 0.0698 | 4377 | 0.0454 | 0.0662 | 0.0905 | 56.0 |
| level_source=sun | 0.0576 | 3059 | 0.0415 | 0.0598 | 0.0937 | 46.0 |
| level_sub_index=1 | -0.0163 | 1233 | -0.0358 | -0.0243 | 0.0039 | 64.0 |
| level_sub_index=2 | -0.0059 | 1272 | -0.0444 | -0.0200 | -0.0018 | 88.0 |
| level_sub_index=3 | -0.0527 | 1287 | -0.0570 | -0.0122 | 0.0639 | 2.0 |
| level_sub_index=4 | -0.0046 | 1306 | 0.0255 | 0.0395 | 0.0705 | 0.0 |
| level_sub_index=5 | 0.0020 | 1291 | -0.0151 | 0.0196 | 0.0440 | 10.0 |
| level_sub_index=6 | 0.0382 | 1274 | -0.0049 | 0.0335 | 0.0584 | 62.0 |
| level_sub_index=7 | 0.0269 | 1262 | -0.0448 | 0.0158 | 0.0750 | 56.0 |
| level_sub_index=none | 0.4618 | 1144 | 0.4277 | 0.4690 | 0.5673 | 30.0 |

### reach_next_rate

| group | real | n | shadow min | shadow median | shadow max | pct |
|---|---|---|---|---|---|---|
| level_degree=0 | 0.7872 | 1931 | 0.7549 | 0.7701 | 0.7839 | 100.0 |
| level_degree=45 | 0.7782 | 2056 | 0.7649 | 0.7756 | 0.7871 | 66.0 |
| level_degree=90 | 0.7538 | 1718 | 0.7269 | 0.7383 | 0.7523 | 100.0 |
| level_degree=135 | 0.8040 | 1143 | 0.7578 | 0.7724 | 0.7946 | 100.0 |
| level_degree=180 | 0.8039 | 1168 | 0.7735 | 0.7922 | 0.8085 | 98.0 |
| level_degree=225 | 0.7826 | 966 | 0.7521 | 0.7731 | 0.7787 | 100.0 |
| level_degree=270 | 0.7887 | 866 | 0.7774 | 0.8029 | 0.8135 | 16.0 |
| level_degree=315 | 0.7728 | 1241 | 0.7463 | 0.7562 | 0.7738 | 94.0 |
| level_is_halfway=False | 0.7809 | 9658 | 0.7666 | 0.7703 | 0.7741 | 100.0 |
| level_is_halfway=True | 0.7890 | 1431 | 0.7538 | 0.7634 | 0.7771 | 100.0 |
| level_kind=major | 0.8084 | 1336 | 0.7708 | 0.7865 | 0.8006 | 100.0 |
| level_kind=sub | 0.7783 | 9753 | 0.7631 | 0.7682 | 0.7700 | 100.0 |
| level_ring_bin=10-19 | 0.7846 | 10212 | 0.7682 | 0.7723 | 0.7758 | 100.0 |
| level_ring_bin=20-29 | 0.7514 | 877 | 0.7252 | 0.7415 | 0.7561 | 86.0 |
| level_source=center | 0.7873 | 2929 | 0.7627 | 0.7677 | 0.7725 | 100.0 |
| level_source=moon | 0.7676 | 4747 | 0.7498 | 0.7576 | 0.7635 | 100.0 |
| level_source=sun | 0.7972 | 3413 | 0.7834 | 0.7887 | 0.7931 | 100.0 |
| level_sub_index=1 | 0.7718 | 1341 | 0.7533 | 0.7710 | 0.7849 | 62.0 |
| level_sub_index=2 | 0.7671 | 1391 | 0.7450 | 0.7611 | 0.7693 | 90.0 |
| level_sub_index=3 | 0.7651 | 1405 | 0.7479 | 0.7694 | 0.7819 | 38.0 |
| level_sub_index=4 | 0.7890 | 1431 | 0.7538 | 0.7634 | 0.7771 | 100.0 |
| level_sub_index=5 | 0.7900 | 1414 | 0.7607 | 0.7736 | 0.7899 | 100.0 |
| level_sub_index=6 | 0.7665 | 1392 | 0.7395 | 0.7547 | 0.7807 | 66.0 |
| level_sub_index=7 | 0.7984 | 1379 | 0.7673 | 0.7812 | 0.8001 | 98.0 |
| level_sub_index=none | 0.8084 | 1336 | 0.7708 | 0.7865 | 0.8006 | 100.0 |

### rejection_rate

| group | real | n | shadow min | shadow median | shadow max | pct |
|---|---|---|---|---|---|---|
| level_degree=0 | 0.2716 | 2633 | 0.2504 | 0.2743 | 0.2869 | 42.0 |
| level_degree=45 | 0.2879 | 2855 | 0.2634 | 0.2843 | 0.2911 | 86.0 |
| level_degree=90 | 0.2837 | 2376 | 0.2729 | 0.2848 | 0.2950 | 40.0 |
| level_degree=135 | 0.3043 | 1643 | 0.2931 | 0.3097 | 0.3225 | 22.0 |
| level_degree=180 | 0.2579 | 1574 | 0.2408 | 0.2504 | 0.2719 | 72.0 |
| level_degree=225 | 0.2844 | 1350 | 0.2663 | 0.2952 | 0.3056 | 22.0 |
| level_degree=270 | 0.2624 | 1174 | 0.2447 | 0.2567 | 0.2694 | 80.0 |
| level_degree=315 | 0.2872 | 1741 | 0.2581 | 0.2730 | 0.2891 | 96.0 |
| level_is_halfway=False | 0.2822 | 13391 | 0.2690 | 0.2790 | 0.2827 | 98.0 |
| level_is_halfway=True | 0.2711 | 1955 | 0.2474 | 0.2899 | 0.2963 | 14.0 |
| level_kind=major | 0.2690 | 1818 | 0.2653 | 0.2778 | 0.2884 | 2.0 |
| level_kind=sub | 0.2824 | 13528 | 0.2664 | 0.2808 | 0.2844 | 80.0 |
| level_ring_bin=10-19 | 0.2798 | 14107 | 0.2661 | 0.2788 | 0.2830 | 70.0 |
| level_ring_bin=20-29 | 0.2922 | 1239 | 0.2735 | 0.2943 | 0.3060 | 32.0 |
| level_source=center | 0.2802 | 4043 | 0.2657 | 0.2762 | 0.2827 | 80.0 |
| level_source=moon | 0.2822 | 6588 | 0.2720 | 0.2857 | 0.2909 | 26.0 |
| level_source=sun | 0.2793 | 4715 | 0.2623 | 0.2744 | 0.2867 | 88.0 |
| level_sub_index=1 | 0.3030 | 1914 | 0.2761 | 0.2918 | 0.3071 | 70.0 |
| level_sub_index=2 | 0.2935 | 1959 | 0.2567 | 0.2820 | 0.2923 | 100.0 |
| level_sub_index=3 | 0.2785 | 1939 | 0.2721 | 0.2801 | 0.2908 | 40.0 |
| level_sub_index=4 | 0.2711 | 1955 | 0.2474 | 0.2899 | 0.2963 | 14.0 |
| level_sub_index=5 | 0.2721 | 1933 | 0.2651 | 0.2794 | 0.2876 | 22.0 |
| level_sub_index=6 | 0.2861 | 1940 | 0.2340 | 0.2569 | 0.2727 | 100.0 |
| level_sub_index=7 | 0.2722 | 1888 | 0.2629 | 0.2795 | 0.2924 | 24.0 |
| level_sub_index=none | 0.2690 | 1818 | 0.2653 | 0.2778 | 0.2884 | 2.0 |

### timeout_share

| group | real | n | shadow min | shadow median | shadow max | pct |
|---|---|---|---|---|---|---|
| level_degree=0 | 0.0000 | 1931 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_degree=45 | 0.0000 | 2056 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_degree=90 | 0.0000 | 1718 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_degree=135 | 0.0000 | 1143 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_degree=180 | 0.0000 | 1168 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_degree=225 | 0.0000 | 966 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_degree=270 | 0.0000 | 866 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_degree=315 | 0.0000 | 1241 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_is_halfway=False | 0.0000 | 9658 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_is_halfway=True | 0.0000 | 1431 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_kind=major | 0.0000 | 1336 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_kind=sub | 0.0000 | 9753 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_ring_bin=10-19 | 0.0000 | 10212 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_ring_bin=20-29 | 0.0000 | 877 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_source=center | 0.0000 | 2929 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_source=moon | 0.0000 | 4747 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_source=sun | 0.0000 | 3413 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_sub_index=1 | 0.0000 | 1341 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_sub_index=2 | 0.0000 | 1391 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_sub_index=3 | 0.0000 | 1405 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_sub_index=4 | 0.0000 | 1431 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_sub_index=5 | 0.0000 | 1414 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_sub_index=6 | 0.0000 | 1392 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_sub_index=7 | 0.0000 | 1379 | 0.0000 | 0.0000 | 0.0000 | 0.0 |
| level_sub_index=none | 0.0000 | 1336 | 0.0000 | 0.0000 | 0.0000 | 0.0 |

### touch_density

| group | real | n | shadow min | shadow median | shadow max | pct |
|---|---|---|---|---|---|---|
| level_degree=0 | 0.1494 | 4044 | 0.1395 | 0.1443 | 0.1511 | 92.0 |
| level_degree=45 | 0.1436 | 3889 | 0.1408 | 0.1432 | 0.1478 | 60.0 |
| level_degree=90 | 0.1392 | 3769 | 0.1280 | 0.1310 | 0.1363 | 100.0 |
| level_degree=135 | 0.0895 | 2422 | 0.0826 | 0.0871 | 0.0912 | 84.0 |
| level_degree=180 | 0.0774 | 2096 | 0.0717 | 0.0763 | 0.0791 | 90.0 |
| level_degree=225 | 0.0728 | 1972 | 0.0697 | 0.0729 | 0.0753 | 46.0 |
| level_degree=270 | 0.0605 | 1639 | 0.0585 | 0.0611 | 0.0624 | 32.0 |
| level_degree=315 | 0.0946 | 2560 | 0.0935 | 0.0980 | 0.1067 | 16.0 |
| level_is_halfway=False | 0.7171 | 19415 | 0.7027 | 0.7112 | 0.7208 | 94.0 |
| level_is_halfway=True | 0.1099 | 2976 | 0.0977 | 0.1050 | 0.1101 | 98.0 |
| level_kind=major | 0.0934 | 2529 | 0.0772 | 0.0810 | 0.0885 | 100.0 |
| level_kind=sub | 0.7336 | 19862 | 0.7234 | 0.7335 | 0.7442 | 50.0 |
| level_ring_bin=10-19 | 0.7576 | 20510 | 0.7376 | 0.7478 | 0.7600 | 98.0 |
| level_ring_bin=20-29 | 0.0695 | 1881 | 0.0639 | 0.0672 | 0.0706 | 90.0 |
| level_source=center | 0.2126 | 5755 | 0.2086 | 0.2127 | 0.2176 | 44.0 |
| level_source=moon | 0.3672 | 9942 | 0.3522 | 0.3605 | 0.3688 | 94.0 |
| level_source=sun | 0.2473 | 6694 | 0.2321 | 0.2413 | 0.2487 | 90.0 |
| level_sub_index=1 | 0.1031 | 2790 | 0.1034 | 0.1051 | 0.1103 | 0.0 |
| level_sub_index=2 | 0.1022 | 2767 | 0.1009 | 0.1066 | 0.1116 | 12.0 |
| level_sub_index=3 | 0.1068 | 2891 | 0.1031 | 0.1067 | 0.1121 | 50.0 |
| level_sub_index=4 | 0.1099 | 2976 | 0.0977 | 0.1050 | 0.1101 | 98.0 |
| level_sub_index=5 | 0.1091 | 2954 | 0.1008 | 0.1042 | 0.1095 | 94.0 |
| level_sub_index=6 | 0.1035 | 2801 | 0.0999 | 0.1032 | 0.1050 | 58.0 |
| level_sub_index=7 | 0.0991 | 2683 | 0.0992 | 0.1014 | 0.1060 | 0.0 |
| level_sub_index=none | 0.0934 | 2529 | 0.0772 | 0.0810 | 0.0885 | 100.0 |

## Shortlist

Groups whose real value falls outside the **entire** shadow range,
sorted by how far outside. Sample size is in the table because a
rate built on a handful of events lands outside the range easily and
means nothing.

| group | statistic | real | n | shadow min | shadow max | margin |
|---|---|---|---|---|---|---|
| level_sub_index=4 | mean_retest_depth | -0.0046 | n=1306 | 0.0255 | 0.0705 | -0.0301 |
| level_is_halfway=True | mean_retest_depth | -0.0046 | n=1306 | 0.0255 | 0.0705 | -0.0301 |
| level_ring_bin=20-29 | mean_retest_depth | -0.0902 | n=779 | -0.0607 | -0.0134 | -0.0295 |
| level_source=center | mean_retest_depth | 0.0115 | n=2633 | 0.0306 | 0.0659 | -0.0191 |
| level_source=center | reach_next_rate | 0.7873 | n=2929 | 0.7627 | 0.7725 | 0.0148 |
| level_sub_index=6 | rejection_rate | 0.2861 | n=1940 | 0.2340 | 0.2727 | 0.0134 |
| level_sub_index=4 | reach_next_rate | 0.7890 | n=1431 | 0.7538 | 0.7771 | 0.0118 |
| level_is_halfway=True | reach_next_rate | 0.7890 | n=1431 | 0.7538 | 0.7771 | 0.0118 |
| level_degree=135 | reach_next_rate | 0.8040 | n=1143 | 0.7578 | 0.7946 | 0.0094 |
| level_ring_bin=10-19 | reach_next_rate | 0.7846 | n=10212 | 0.7682 | 0.7758 | 0.0088 |
| level_kind=sub | reach_next_rate | 0.7783 | n=9753 | 0.7631 | 0.7700 | 0.0083 |
| level_sub_index=none | reach_next_rate | 0.8084 | n=1336 | 0.7708 | 0.8006 | 0.0078 |
| level_kind=major | reach_next_rate | 0.8084 | n=1336 | 0.7708 | 0.8006 | 0.0078 |
| level_is_halfway=False | reach_next_rate | 0.7809 | n=9658 | 0.7666 | 0.7741 | 0.0068 |
| level_degree=90 | mean_retest_depth | -0.0050 | n=1586 | 0.0006 | 0.0752 | -0.0056 |
| level_sub_index=none | touch_density | 0.0934 | n=2529 | 0.0772 | 0.0885 | 0.0049 |
| level_kind=major | touch_density | 0.0934 | n=2529 | 0.0772 | 0.0885 | 0.0049 |
| level_sub_index=4 | hold_rate | 0.2692 | n=1300 | 0.2443 | 0.2645 | 0.0047 |
| level_is_halfway=True | hold_rate | 0.2692 | n=1300 | 0.2443 | 0.2645 | 0.0047 |
| level_sub_index=5 | hold_rate | 0.2533 | n=1287 | 0.2244 | 0.2490 | 0.0043 |
| level_source=sun | reach_next_rate | 0.7972 | n=3413 | 0.7834 | 0.7931 | 0.0042 |
| level_source=moon | reach_next_rate | 0.7676 | n=4747 | 0.7498 | 0.7635 | 0.0041 |
| level_degree=225 | reach_next_rate | 0.7826 | n=966 | 0.7521 | 0.7787 | 0.0039 |
| level_degree=0 | reach_next_rate | 0.7872 | n=1931 | 0.7549 | 0.7839 | 0.0033 |
| level_degree=90 | touch_density | 0.1392 | n=3769 | 0.1280 | 0.1363 | 0.0029 |
| level_source=moon | hold_rate | 0.2438 | n=4361 | 0.2302 | 0.2412 | 0.0026 |
| level_kind=sub | mean_retest_depth | -0.0018 | n=8925 | 0.0006 | 0.0189 | -0.0024 |
| level_degree=90 | reach_next_rate | 0.7538 | n=1718 | 0.7269 | 0.7523 | 0.0015 |
| level_sub_index=2 | rejection_rate | 0.2935 | n=1959 | 0.2567 | 0.2923 | 0.0012 |
| level_degree=315 | hold_rate | 0.2369 | n=1148 | 0.2138 | 0.2357 | 0.0012 |
| level_degree=90 | hold_rate | 0.2300 | n=1574 | 0.2119 | 0.2293 | 0.0006 |
| level_sub_index=1 | touch_density | 0.1031 | n=2790 | 0.1034 | 0.1103 | -0.0003 |
| level_sub_index=5 | reach_next_rate | 0.7900 | n=1414 | 0.7607 | 0.7899 | 0.0001 |
| level_sub_index=7 | touch_density | 0.0991 | n=2683 | 0.0992 | 0.1060 | -0.0001 |
