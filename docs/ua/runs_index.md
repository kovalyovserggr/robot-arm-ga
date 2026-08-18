# runs_index.md — куратований реєстр прогонів (з мета-поясненнями)

Джерело сирих фактів — docs/ua/runs_index_auto.md (не редагувати
вручну). Тут — лише офіційні/значущі прогони з поясненням "навіщо".
Технічні/тестові прогони (population<100, max_generations=1 тощо)
з runs_index_auto.md сюди навмисно не переносяться.

| run_id | дата | git-хеш | optimizer | сід | серія | мета |
|---|---|---|---|---|---|---|
| run_20260809_165204 | 09.08 16:52 | f830cc7 | nsga2 | 30 | fig4-curriculum-self-paced | Рис.4, прогін №1 self-paced |
| run_20260809_173652 | 09.08 17:36 | f830cc7 | nsga2 | 31 | fig4-curriculum-self-paced | Рис.4, прогін №2 self-paced |
| run_20260809_181843 | 09.08 18:18 | f830cc7 | nsga2 | 32 | fig4-curriculum-self-paced | Рис.4, прогін №3 self-paced |
| run_20260809_230221 | 09.08 23:02 | f830cc7 | nsga2 | 32 | fig4-curriculum-open-loop | Рис.4, прогін №1 open-loop |
| run_20260810_084828 | 10.08 08:48 | f830cc7 | nsga2 | 31 | fig4-curriculum-open-loop | Рис.4, прогін №2 open-loop |
| run_20260810_102634 | 10.08 10:26 | f830cc7 | nsga2 | 30 | fig4-curriculum-open-loop | Рис.4, прогін №3 open-loop; Open-loop 0/3, self-paced 2/3 |
| run_20260810_131108 | 10.08 13:11 | c11893b | nsga2 | 40 | fig-nsga2-vs-baseline-nsga2 | Рис.5/8/чемпіони, гілка nsga2 |
| run_20260810_135744 | 10.08 13:57 | c11893b | nsga2 | 41 | fig-nsga2-vs-baseline-nsga2 | те саме |
| run_20260810_144209 | 10.08 14:42 | c11893b | nsga2 | 42 | fig-nsga2-vs-baseline-nsga2 | те саме |
| run_20260810_164525 | 10.08 16:45 | c11893b | nsga2 | 43 | fig-nsga2-vs-baseline-nsga2 | ЗАСТАРІЛИЙ (tolerance-баг) — використано лише для Рис.8, НЕ для таблиці чемпіонів |
| run_20260810_172937 | 10.08 17:29 | c11893b | nsga2 | 44 | fig-nsga2-vs-baseline-nsga2 | Рис.5/8/чемпіони |
| run_20260810_181322 | 10.08 18:13 | c11893b | weighted_sum | 40 | fig-nsga2-vs-baseline-weightedsum | Рис.5/чемпіони, гілка baseline |
| run_20260810_185434 | 10.08 18:54 | c11893b | weighted_sum | 41 | fig-nsga2-vs-baseline-weightedsum | те саме |
| run_20260810_193553 | 10.08 19:35 | c11893b | weighted_sum | 42 | fig-nsga2-vs-baseline-weightedsum | те саме |
| run_20260810_201629 | 10.08 20:16 | c11893b | weighted_sum | 43 | fig-nsga2-vs-baseline-weightedsum | те саме |
| run_20260810_213316 | 10.08 21:33 | c11893b | weighted_sum | 44 | fig-nsga2-vs-baseline-weightedsum | те саме |
| run_20260812_101137 | 12.08 10:11 | 0e1f93b | nsga2 | 43 | fig-nsga2-vs-baseline-nsga2 | КОРЕКТНИЙ перезапуск сіда 43 після фіксу tolerance-off-by-one — використовувати для таблиці чемпіонів і Рис.9/10 |
| run_20260813_105512 | 13.08 10:55 | 4f8d137 | weighted_sum | 30 | fig6-mutation-constant | Рис.6, гілка A (constant) |
| run_20260813_113727 | 13.08 11:37 | 4f8d137 | weighted_sum | 31 | fig6-mutation-constant | те саме |
| run_20260813_122323 | 13.08 12:23 | 4f8d137 | weighted_sum | 32 | fig6-mutation-constant | те саме |
| run_20260813_131819 | 13.08 13:18 | 4f8d137 | weighted_sum | 30 | fig6-mutation-annealing | Рис.6, гілка B (annealing) |
| run_20260813_142001 | 13.08 14:20 | 4f8d137 | weighted_sum | 31 | fig6-mutation-annealing | те саме |
| run_20260813_150440 | 13.08 15:04 | 4f8d137 | weighted_sum | 32 | fig6-mutation-annealing | те саме |
| run_20260813_154956 | 13.08 15:49 | 4f8d137 | weighted_sum | 30 | fig6-mutation-pcontrol | Рис.6, гілка C (p_control) |
| run_20260813_163445 | 13.08 16:34 | 4f8d137 | weighted_sum | 31 | fig6-mutation-pcontrol | те саме; Т22 — σ провалилась до підлоги рано, пояснює аномалію (success=0%, precision~0.3-0.4мм) |
| run_20260813_171846 | 13.08 17:18 | 4f8d137 | weighted_sum | 32 | fig6-mutation-pcontrol | те саме |
| run_20260813_180113 | 13.08 18:01 | 4f8d137 | weighted_sum | 30 | fig6-mutation-selfadaptive | Рис.6, гілка D (self_adaptive, реалізовано вперше цієї сесії) |
| run_20260813_205007 | 13.08 20:50 | 4f8d137 | weighted_sum | 31 | fig6-mutation-selfadaptive | те саме |
| run_20260813_214339 | 13.08 21:43 | 4f8d137 | weighted_sum | 32 | fig6-mutation-selfadaptive | те саме |
| run_20260814_200424 | 14.08 20:04 | 7293d97 | nsga2 | 30 | fig7-gate-04 | Рис.7, гілка A (gate=4%) |
| run_20260814_212308 | 14.08 21:23 | 7293d97 | nsga2 | 31 | fig7-gate-04 | те саме |
| run_20260814_220529 | 14.08 22:05 | 7293d97 | nsga2 | 32 | fig7-gate-04 | те саме |
| run_20260814_230518 | 14.08 23:05 | 7293d97 | nsga2 | 30 | fig7-gate-25 | Рис.7, гілка B (gate=25%) |
| run_20260815_100922 | 15.08 10:09 | 7293d97 | nsga2 | 31 | fig7-gate-25 | те саме |
| run_20260815_105304 | 15.08 10:53 | 7293d97 | nsga2 | 32 | fig7-gate-25 | те саме |
| run_20260815_113735 | 15.08 11:37 | 7293d97 | nsga2 | 30 | fig7-gate-50 | Рис.7, гілка C (gate=50%) |
| run_20260815_123221 | 15.08 12:32 | 7293d97 | nsga2 | 31 | fig7-gate-50 | те саме; Т23 — gate=50% дав 2/3 успішних сідів проти 1/3 при 4%/25% |
| run_20260815_134127 | 15.08 13:41 | 7293d97 | nsga2 | 32 | fig7-gate-50 | те саме |
| — | 12.08 | 0e1f93b | nsga2 | 43 | robustness-Т7 | Т7 robustness-тест (stage_fixed_genomes, 90 клонів чемпіона 43): success 100%→43.3%→20% при шумі 0°/0.1°/0.5° |
| run_20260816_114602 | 16.08 11:46 | 5c77700 | nsga2 | 40 | fig-nsga2-vs-baseline-nsga2 | Перезапуск для запасу точності: tolerance=20.37мм, precision=16.81мм, запас=3.56мм |
| run_20260816_122706 | 16.08 12:27 | 5c77700 | nsga2 | 41 | fig-nsga2-vs-baseline-nsga2 | те саме: tolerance=23.02мм, precision=20.01мм, запас=3.01мм |
| run_20260816_131939 | 16.08 13:19 | 5c77700 | nsga2 | 42 | fig-nsga2-vs-baseline-nsga2 | ВИКЛЮЧЕНО — success=False (немає справжнього успіху для виміру запасу) |
| run_20260816_143445 | 16.08 14:34 | 5c77700 | nsga2 | 44 | fig-nsga2-vs-baseline-nsga2 | те саме: tolerance=10.39мм, precision=6.84мм, запас=3.55мм |

## Технічні/допоміжні прогони (НЕ для рисунків статті)
Повний список — у runs_index_auto.md. Категорії: ранні
тести до офіційного старту серій (до 09.08 15:50), короткі
population=20/тестові robustness-стейджі (12.08 22:37-23:17),
дублікат сіда 42 (run_20260816_131843, ймовірно перервана спроба
за хвилину до справжньої 131939).
