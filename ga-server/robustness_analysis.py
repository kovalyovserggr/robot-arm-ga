"""
robustness_analysis.py — Т7: стійкість чемпіона до шуму привода.

Два кроки, між якими — реальний прогін в Unity:

  1. stage   — генерує зашумлені клони чемпіона (шум лише на гени руху,
     construction незмінний — Т7 моделює повторюваність привода, не
     похибку виготовлення), підкладає їх через уже наявний
     /experiment/stage_fixed_genomes, друкує інструкцію для Unity.

  2. analyze — після завершення того прогону (Population Size = N,
     Max Generations = 1) читає gen_0000.json нового run_id і зводить
     success rate / середню похибку по рівнях шуму.

Рівень 0.0° у --noise-deg — контрольна група (чистий геном, без
навмисного шуму) — водночас вимірює й чистий фізичний недетермінізм
(gen0005_prog1/prog2 з ранішої сесії), окремо від навмисного збурення.

Приклад:
  python robustness_analysis.py stage --run-id run_20260812_101137 \
      --noise-deg 0.0 0.1 0.5 --samples-per-level 30 --seed 7

  # -> у Unity: Population Size=90, Construction/Motion Gene Count як
  #    у виводу нижче, Max Generations=1, Play.

  python robustness_analysis.py analyze --run-id run_NOVYI_ID \
      --source-run-id run_20260812_101137
"""
import argparse
import json
import pathlib
import random
import urllib.parse
import urllib.request

DEG_TO_GENE = 1.0 / 150.0  # мотор-ген розгортається на ±150° при g∈[-1,1] -> 150°/одиницю


def build_noisy_population(champion_construction, champion_motion,
                           noise_deg_levels, samples_per_level, seed):
    """Повертає (population, order) — population готовий список для
    stage_fixed_genomes, order[i] = рівень шуму individual_id=i (для
    подальшого analyze; порядок конструюється тут ОДИН РАЗ і мусить
    лишатись тим самим для обох команд)."""
    rng = random.Random(seed)
    pop, order = [], []
    for level in noise_deg_levels:
        gene_std = level * DEG_TO_GENE
        for _ in range(samples_per_level):
            motion = [
                max(-1.0, min(1.0, x + (rng.gauss(0, gene_std) if gene_std > 0 else 0.0)))
                for x in champion_motion
            ]
            pop.append({"individual_id": len(pop),
                        "construction": list(champion_construction),
                        "motion": motion})
            order.append(level)
    return pop, order


def cmd_stage(args):
    logs_dir = pathlib.Path(args.logs_dir)
    champ_path = logs_dir / args.run_id / "champion.json"
    if not champ_path.exists():
        raise FileNotFoundError(f"Немає {champ_path}")
    champ = json.loads(champ_path.read_text(encoding="utf-8"))
    genome = champ["genome"]

    pop, order = build_noisy_population(
        genome["construction"], genome["motion"],
        args.noise_deg, args.samples_per_level, args.seed)

    plan_path = logs_dir / f"_robustness_plan_{args.run_id}.json"
    plan_path.write_text(json.dumps({
        "source_run_id": args.run_id, "noise_deg_levels": args.noise_deg,
        "samples_per_level": args.samples_per_level, "seed": args.seed,
        "order": order,
    }, indent=2), encoding="utf-8")

    # FIX: передаємо ДІЮЧИЙ допуск чемпіона (champion.tolerance —
    # коректний завдяки попередньому фіксу off-by-one), а не дефолтні
    # 50мм сервера. Без цього навіть точні копії успішного генома
    # хибно провалюються, бо оцінюються за занадто суворим порогом,
    # під який вони не оптимізувались (виявлено на реальних даних).
    champion_tolerance = champ.get("tolerance")
    query = urllib.parse.urlencode(
        {"initial_tolerance": champion_tolerance} if champion_tolerance is not None else {})
    url = f"{args.server_url}/experiment/stage_fixed_genomes"
    if query:
        url += f"?{query}"
    body = json.dumps(pop).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req).read())

    print(resp["note"])
    print(f"Population Size            = {len(pop)}")
    print(f"Construction Gene Count    = {len(genome['construction'])}")
    print(f"Motion Gene Count          = {len(genome['motion'])}")
    print(f"Max Generations            = 1")
    print(f"Допуск чемпіона (передано) = "
         f"{champion_tolerance*1000:.2f} мм" if champion_tolerance is not None
         else "Допуск чемпіона            = <ВІДСУТНІЙ у champion.json! "
              "Буде дефолт 50мм — може дати хибні провали, як минулого разу>")
    print(f"Рівні шуму (° на ген руху) = {args.noise_deg}, "
         f"по {args.samples_per_level} на рівень")
    print(f"План збережено: {plan_path}  (знадобиться для analyze)")


def cmd_analyze(args):
    logs_dir = pathlib.Path(args.logs_dir)
    plan_path = logs_dir / f"_robustness_plan_{args.source_run_id}.json"
    if not plan_path.exists():
        raise FileNotFoundError(f"Немає плану {plan_path} — спершу виконай stage")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    order = plan["order"]

    gen_file = logs_dir / args.run_id / "gen_0000.json"
    if not gen_file.exists():
        raise FileNotFoundError(f"Немає {gen_file} — прогін в Unity ще не завершено?")
    gen = json.loads(gen_file.read_text(encoding="utf-8"))
    results = {r["individual_id"]: r for r in gen["results"]}

    by_level: dict[float, list] = {}
    for iid, level in enumerate(order):
        r = results.get(iid)
        if r is None:
            continue
        by_level.setdefault(level, []).append(r)

    print(f"{'Рівень шуму, °':<18}{'n':<6}{'success, %':<14}{'precision mean, мм':<20}"
         f"{'precision std, мм':<20}")
    lines = []
    for level in sorted(by_level):
        items = by_level[level]
        n = len(items)
        succ_rate = 100.0 * sum(1 for r in items if r.get("success")) / n
        precs = [r.get("precision_error", 0.0) * 1000 for r in items]
        prec_mean = sum(precs) / n
        prec_std = (sum((p - prec_mean) ** 2 for p in precs) / n) ** 0.5
        row = f"{level:<18}{n:<6}{succ_rate:<14.1f}{prec_mean:<20.2f}{prec_std:<20.2f}"
        print(row)
        lines.append({"noise_deg": level, "n": n, "success_rate_pct": succ_rate,
                      "precision_mean_mm": prec_mean, "precision_std_mm": prec_std})

    if args.output:
        out = pathlib.Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(lines, indent=2), encoding="utf-8")
        print(f"\nЗбережено: {out}")


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--server-url", default="http://127.0.0.1:8000")
    common.add_argument("--logs-dir", default="logs")

    ap = argparse.ArgumentParser(description=__doc__, parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("stage", parents=[common],
                       help="Підготувати й підкласти зашумлену популяцію")
    s.add_argument("--run-id", required=True)
    s.add_argument("--noise-deg", nargs="+", type=float, default=[0.0, 0.1, 0.5])
    s.add_argument("--samples-per-level", type=int, default=30)
    s.add_argument("--seed", type=int, default=None)

    a = sub.add_parser("analyze", parents=[common],
                       help="Звести результат після прогону в Unity")
    a.add_argument("--run-id", required=True, help="run_id НОВОГО прогону (результат Unity)")
    a.add_argument("--source-run-id", required=True, help="run_id чемпіона, з якого стейджили")
    a.add_argument("--output", default=None)

    args = ap.parse_args()
    (cmd_stage if args.cmd == "stage" else cmd_analyze)(args)


if __name__ == "__main__":
    main()
