"""
compare_champions.py — зводить champion.json пар прогонів nsga2 vs
weighted_sum (той самий Seed) в одну порівняльну таблицю: M, W_cv,
W_max, T, E, success. Відповідає на питання "хто дав кращого
чемпіона за якістю", а не "хто швидше прорвався" (це вже видно на
fig05_curriculum_comparison — швидкість прориву тут навмисно
ІГНОРУЄТЬСЯ, дивимось лише на фінальний результат).

УВАГА: weighted_sum-прогони НЕ мають готового поля champion.objectives
(його рахує лише NSGA2Engine) — M і W_max_over_M для ОБОХ рушіїв
дораховуються тут самостійно з генів чемпіона (genome_seed.decode_material,
те саме джерело істини, що й у сервері) — так порівняння чесне для
обох методів однаково.

Запуск:
  python compare_champions.py \
    --pair "40:run_nsga2_id_40,run_weightedsum_id_40" \
    --pair "41:run_nsga2_id_41,run_weightedsum_id_41" \
    ...
    --output champions_comparison.md
"""
import argparse
import json
import pathlib
import statistics

from genome_seed import decode_material

M_FLOOR = 0.05  # дзеркало nsga2_engine.M_FLOOR — захист від ділення на ~0


def load_champion(logs_dir: pathlib.Path, run_id: str) -> dict | None:
    p = logs_dir / run_id / "champion.json"
    if not p.exists():
        return None
    ch = json.loads(p.read_text(encoding="utf-8"))
    m = decode_material(ch["genome"]["construction"])
    metrics = ch["metrics"]
    w_max = metrics.get("wear_max")
    return {
        "run_id": run_id,
        "success": bool(metrics.get("success", False)),
        "generation": ch.get("generation"),
        "T": metrics.get("assembly_time"),
        "E": metrics.get("energy"),
        "W_cv": metrics.get("wear_cv"),
        "W_max": w_max,
        "M": m,
        "W_max_over_M": (w_max / max(m, M_FLOOR)) if (m is not None and w_max is not None) else None,
    }


def fmt(v, nd=3):
    if v is None:
        return "\u2014"
    if isinstance(v, bool):
        return "\u0442\u0430\u043a" if v else "\u043d\u0456"
    if isinstance(v, (int,)):
        return str(v)
    return f"{v:.{nd}g}"


def stats_of(rows, key, engine_idx, only_success=True):
    """Зведена статистика по n сідів: mean, std (генеральне, pstdev — бо
    n=5 це вся серія, не вибірка з більшої популяції), min, max, n."""
    vals = []
    for _, nsga, ws in rows:
        d = nsga if engine_idx == 0 else ws
        if d is None:
            continue
        if only_success and not d.get("success"):
            continue
        v = d.get(key)
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    return {
        "mean": sum(vals) / len(vals),
        "std": statistics.pstdev(vals) if len(vals) > 1 else 0.0,
        "min": min(vals), "max": max(vals), "n": len(vals),
    }


def fmt_stats(s, nd=3):
    if s is None:
        return "\u2014"
    def g(v): return f"{v:.{nd}g}"
    return f"{g(s['mean'])} \u00b1 {g(s['std'])} [{g(s['min'])}\u2013{g(s['max'])}]"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pair", action="append", required=True,
        help='Формат: "Seed:nsga2_run_id,weighted_sum_run_id". Можна кілька разів.')
    ap.add_argument("--logs-dir", default="logs")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    logs_dir = pathlib.Path(args.logs_dir)
    rows = []
    for s in args.pair:
        if ":" not in s or "," not in s:
            raise ValueError(f'--pair має формат "Seed:nsga2_id,weightedsum_id" — отримано: {s!r}')
        seed, rest = s.split(":", 1)
        nsga_id, ws_id = [x.strip() for x in rest.split(",", 1)]
        rows.append((seed.strip(), load_champion(logs_dir, nsga_id),
                     load_champion(logs_dir, ws_id)))

    lines = [
        "| Seed | \u041c\u0435\u0442\u043e\u0434 | success | \u043f\u043e\u043a\u043e\u043b\u0456\u043d\u043d\u044f | T, \u0441 | E, \u0414\u0436 | W_cv | W_max, \u0414\u0436 | M, \u043c | W_max/M |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for seed, nsga, ws in rows:
        for label, d in [("nsga2", nsga), ("weighted_sum", ws)]:
            if d is None:
                lines.append(f"| {seed} | {label} | \u041d\u0415\u041c\u0410\u0404 champion.json | | | | | | | |")
                continue
            lines.append(
                f"| {seed} | {label} | {fmt(d['success'])} | {fmt(d['generation'])} | "
                f"{fmt(d['T'])} | {fmt(d['E'])} | {fmt(d['W_cv'])} | {fmt(d['W_max'])} | "
                f"{fmt(d['M'])} | {fmt(d['W_max_over_M'])} |"
            )

    lines += ["", "**\u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430 \u043f\u043e \u0443\u0441\u043f\u0456\u0448\u043d\u0438\u0445 \u0447\u0435\u043c\u043f\u0456\u043e\u043d\u0430\u0445 (mean \u00b1 std [min\u2013max], n \u0441\u0456\u0434\u0456\u0432):**", "",
        "| \u041c\u0435\u0442\u043e\u0434 | n | M, \u043c | W_cv | W_max/M | E, \u0414\u0436 | T, \u0441 |",
        "|---|---|---|---|---|---|---|"]
    for label, idx in [("nsga2", 0), ("weighted_sum", 1)]:
        n_succ = stats_of(rows, "M", idx)
        n_succ = n_succ["n"] if n_succ else 0
        lines.append(
            f"| {label} | {n_succ} | {fmt_stats(stats_of(rows,'M',idx))} | "
            f"{fmt_stats(stats_of(rows,'W_cv',idx))} | "
            f"{fmt_stats(stats_of(rows,'W_max_over_M',idx))} | "
            f"{fmt_stats(stats_of(rows,'E',idx))} | "
            f"{fmt_stats(stats_of(rows,'T',idx))} |"
        )
    lines += ["",
        "*\u041f\u0440\u0438\u043c\u0456\u0442\u043a\u0430: \u0448\u0438\u0440\u043e\u043a\u0438\u0439 \u0440\u043e\u0437\u043a\u0438\u0434 "
        "(\u043d\u0430\u043f\u0440. W_cv \u043c\u0456\u0436 \u0441\u0456\u0434\u0430\u043c\u0438) \u2014 \u043e\u0447\u0456\u043a\u0443\u0432\u0430\u043d\u0438\u0439 "
        "\u0435\u0444\u0435\u043a\u0442 \u043f\u0440\u0438 n=5; \u0434\u0438\u0432. individual seed rows \u0432\u0438\u0449\u0435 \u0434\u043b\u044f "
        "\u0437\u043d\u0430\u043a\u0430 \u0440\u043e\u0437\u0431\u0456\u0436\u043d\u043e\u0441\u0442\u0456 (\u043d\u0430\u043f\u0440. seed 42/43 W_cv "
        "\u043c\u0430\u044e\u0442\u044c \u043f\u0440\u043e\u0442\u0438\u043b\u0435\u0436\u043d\u0438\u0439 \u0437\u043d\u0430\u043a \u043f\u0435\u0440\u0435\u0432\u0430\u0433\u0438).*"]

    text = "\n".join(lines)
    print(text)
    if args.output:
        out_path = pathlib.Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"\n\u0417\u0431\u0435\u0440\u0435\u0436\u0435\u043d\u043e: {args.output}")


if __name__ == "__main__":
    main()
