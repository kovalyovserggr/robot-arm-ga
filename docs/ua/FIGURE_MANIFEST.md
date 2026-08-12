#  маніфест серій — сирі дані для docs/ua/FIGURE_MANIFEST.md
fig04_curriculum_comparison.png :
Comparison of self-paced (Schmitt-trigger) vs. open-loop curriculum strategies across 3 seeds each. Self-paced achieves breakthrough in 2/3 seeds (generation ~105–125) and sustains 15–40% success rate; open-loop fails to converge in all 3 seeds within 200 generations, with the tolerance schedule outpacing the population's actual capability."


| Seed | Метод | success | покоління | T, с | E, Дж | W_cv | W_max, Дж | M, м | W_max/M |
|---|---|---|---|---|---|---|---|---|---|
| 40 | nsga2 | так | 56 | 8.3 | 3.17e+03 | 0.132 | 618 | 0.72 | 859 |
| 40 | weighted_sum | так | 195 | 7.74 | 2e+03 | 0.328 | 442 | 1.01 | 438 |
| 41 | nsga2 | так | 103 | 8.82 | 1.56e+03 | 0.388 | 405 | 0.565 | 716 |
| 41 | weighted_sum | так | 199 | 8.54 | 1.16e+03 | 0.138 | 226 | 1.34 | 169 |
| 42 | nsga2 | так | 66 | 9.18 | 2.16e+03 | 0.454 | 575 | 0.572 | 1e+03 |
| 42 | weighted_sum | так | 199 | 7.66 | 779 | 0.016 | 133 | 0.857 | 156 |
| 43 | nsga2 | так | 173 | 7.74 | 1.55e+03 | 0.396 | 354 | 0.33 | 1.07e+03 |
| 43 | weighted_sum | так | 195 | 7.06 | 2.76e+03 | 0.508 | 804 | 0.771 | 1.04e+03 |
| 44 | nsga2 | так | 132 | 7.06 | 2.25e+03 | 0.409 | 694 | 1.01 | 688 |
| 44 | weighted_sum | так | 197 | 7.98 | 965 | 0.02 | 165 | 0.858 | 193 |

**Середнє по успішних чемпіонах:**

| Метод | M, м (mean) | W_cv (mean) | W_max/M (mean) | E, Дж (mean) | T, с (mean) |
|---|---|---|---|---|---|
| nsga2 | 0.639 | 0.356 | 867 | 2.14e+03 | 8.22 |
| weighted_sum | 0.967 | 0.202 | 400 | 1.53e+03 | 7.8 |



(Рис.8,run_20260810_131108 run_20260810_135744 run_20260810_144209 run_20260810_164525 run_20260810_172937, fig-nsga2-vs-baseline-nsga2);
"Fig. 8. Pareto front projection (M vs. W_cv) aggregated from the final 10 generations of 5 NSGA-II runs (colored by seed; gray = dominated feasible individuals). The trade-off is primarily inter-seed: within a single run, construction genes converge early (epistatic lock-in), so front diversity along M emerges mainly across independent runs rather than within one."