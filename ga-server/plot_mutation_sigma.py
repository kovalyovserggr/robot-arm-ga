"""
plot_mutation_sigma.py — Рис.6 (доповнення): траєкторія σ мутації по
поколіннях для кожної стратегії (Т4/Т4а). Читає поле "sigma", яке
main.py зберігає в кожному gen_*.json (для self_adaptive — СЕРЕДНЄ по
популяції на те покоління; для constant/annealing/p_control — єдине
глобальне число, застосоване до всіх особин однаково).

Для кожної групи (стратегії) малює жирну лінію — середнє по сідах
групи, і тонкі напівпрозорі лінії — окремі сіди (щоб бачити розкид
між ними, не лише загальний тренд).

Запуск (той самий формат --series, що й plot_series_comparison.py):
  python plot_mutation_sigma.py \
    --series "Constant:run1,run2,run3" \
    --series "Annealing:run4,run5,run6" \
    --series "P-control:run7,run8,run9" \
    --series "Self-adaptive:run10,run11,run12" \
    --output fig06b_mutation_sigma.png
"""
import argparse
import json
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUTPUT_DIR = pathlib.Path(r"C:\simulation\images")
PALETTE = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]


def load_sigma_curve(logs_dir: pathlib.Path, run_id: str):
    run_dir = logs_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Не знайдено папку прогону: {run_dir}")
    g_ids, sigmas = [], []
    for f in sorted(run_dir.glob("gen_*.json")):
        g = json.loads(f.read_text(encoding="utf-8"))
        if g.get("sigma") is None:
            continue
        g_ids.append(g["generation_id"])
        sigmas.append(g["sigma"])
    if not g_ids:
        raise ValueError(f"У {run_dir} немає поля sigma в жодному gen_*.json "
                         f"(старі логи до фіксу sigma-persistence?)")
    return g_ids, sigmas


def mean_curve(curves: list[tuple[list[int], list[float]]]):
    """Вирівнює по мінімальній спільній довжині (усі мають бути
    однаковими, якщо max_generations був той самий у всій серії)."""
    min_len = min(len(g) for g, _ in curves)
    if min_len < max(len(g) for g, _ in curves):
        print(f"[!] Прогони в групі мають різну довжину — обрізаю до {min_len} поколінь")
    g_ids = curves[0][0][:min_len]
    mean_sig = [sum(c[1][i] for c in curves) / len(curves) for i in range(min_len)]
    return g_ids, mean_sig


def main():
    ap = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--series", action="append", required=True,
        help='Формат: "Назва:run_id1,run_id2,run_id3" — можна кілька разів')
    ap.add_argument("--logs-dir", default="logs")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    logs_dir = pathlib.Path(args.logs_dir)
    fig, ax = plt.subplots(figsize=(9, 6))

    for i, s in enumerate(args.series):
        if ":" not in s:
            raise ValueError(f'--series має формат "Назва:run_id1,..." — отримано: {s!r}')
        label, ids = s.split(":", 1)
        run_ids = [x.strip() for x in ids.split(",") if x.strip()]
        color = PALETTE[i % len(PALETTE)]
        curves = [load_sigma_curve(logs_dir, rid) for rid in run_ids]

        for g_ids, sigmas in curves:
            ax.plot(g_ids, sigmas, color=color, lw=0.8, alpha=0.35)

        mg, ms = mean_curve(curves)
        ax.plot(mg, ms, color=color, lw=2.2,
               label=f"{label.strip()} (mean of {len(curves)})")
        print(f"{label.strip()}: {len(curves)} прогонів, "
             f"σ на старті\u2248{ms[0]:.4f}, наприкінці\u2248{ms[-1]:.4f}")

    ax.set_yscale("log")
    ax.set_xlabel("Generation")
    ax.set_ylabel("Mutation step size (\u03c3)")
    ax.set_title("Mutation step size over generations, by strategy")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()

    if args.output:
        out = pathlib.Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
    else:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out = OUTPUT_DIR / "mutation_sigma.png"
    fig.savefig(out, dpi=150)
    print(f"Збережено: {out}")


if __name__ == "__main__":
    main()
