"""
plot_convergence.py — графіки збіжності GA/NSGA-II з логів gen_*.json.

Запуск:
  python plot_convergence.py                    # найсвіжіший прогін,
                                                  # автозбереження в OUTPUT_DIR
  python plot_convergence.py logs\\run_...        # конкретний прогін
  python plot_convergence.py logs результат.png  # свій шлях/ім'я (як раніше)

Без явного шляху виводу — файл сам летить у OUTPUT_DIR з іменем, що
містить назву папки прогону і номер останнього покоління (без ризику
випадково перезаписати попередній графік).
"""
import json
import pathlib
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# За домовленістю (сесія 2026-08): графіки для статті/архіву — сюди.
# Змінити тут, якщо шлях на машині інший.
OUTPUT_DIR = pathlib.Path(r"C:\simulation\images")


def load_generations(log_dir: pathlib.Path):
    if not list(log_dir.glob("gen_*.json")):
        runs = sorted(log_dir.glob("run_*"))
        if runs:
            log_dir = runs[-1]
            print(f"Використовую найсвіжіший прогін: {log_dir}")
    gens = []
    for f in sorted(log_dir.glob("gen_*.json")):
        gens.append(json.loads(f.read_text(encoding="utf-8")))
    return gens, log_dir


def auto_output_path(log_dir: pathlib.Path, last_gen: int) -> pathlib.Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR / f"convergence_{log_dir.name}_gen{last_gen:04d}.png"


def main():
    log_root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "logs")
    explicit_out = sys.argv[2] if len(sys.argv) > 2 else None

    gens, log_dir = load_generations(log_root)
    if not gens:
        print(f"У {log_root} немає gen_*.json"); return

    g_ids, best_f, mean_f = [], [], []
    succ_rate, prec_min, prec_mean = [], [], []
    wcv_mean, wmax_best, tol_curve = [], [], []

    for g in gens:
        rs = g["results"]
        if not rs: continue
        fits = [r.get("fitness", 0.0) for r in rs]
        precs = [r.get("precision_error", 0.0) for r in rs]
        g_ids.append(g["generation_id"])
        best_f.append(max(fits))
        mean_f.append(sum(fits) / len(fits))
        succ_rate.append(100.0 * sum(r.get("success", False) for r in rs) / len(rs))
        prec_min.append(min(precs))
        prec_mean.append(sum(precs) / len(precs))
        wcv_mean.append(sum(r.get("wear_cv", 0.0) for r in rs) / len(rs))
        best = max(rs, key=lambda r: r.get("fitness", 0.0))
        wmax_best.append(best.get("wear_max", 0.0))
        tol_curve.append(g.get("tolerance"))

    fig, ax = plt.subplots(2, 2, figsize=(11, 7.5))
    fig.suptitle("Збіжність GA — оптимізація роботизованої руки", fontsize=13)

    ax[0, 0].plot(g_ids, best_f, label="best", lw=1.8)
    ax[0, 0].plot(g_ids, mean_f, label="mean", lw=1.2, alpha=0.7)
    ax[0, 0].set_title("Fitness (згортка)"); ax[0, 0].legend()

    ax[0, 1].plot(g_ids, succ_rate, color="tab:green", lw=1.8)
    ax[0, 1].set_title("Успішні монтажі, %"); ax[0, 1].set_ylim(-2, 102)

    ax[1, 0].semilogy(g_ids, prec_min, label="min", lw=1.8)
    ax[1, 0].semilogy(g_ids, prec_mean, label="mean", lw=1.2, alpha=0.7)
    ax[1, 0].axhline(0.005, color="red", ls="--", lw=0.8, label="допуск 5 мм")
    if any(t is not None for t in tol_curve):
        ax[1, 0].semilogy(g_ids, [t if t else None for t in tol_curve],
                          color="green", ls=":", lw=1.6, label="допуск curriculum")
    ax[1, 0].set_title("Похибка позиціонування, м (log)"); ax[1, 0].legend()

    ax[1, 1].plot(g_ids, wcv_mean, label="W_cv (mean)", lw=1.5, color="tab:blue")
    ax[1, 1].set_ylabel("W_cv", color="tab:blue")
    ax2 = ax[1, 1].twinx()
    ax2.plot(g_ids, wmax_best, label="W_max (best)", lw=1.5, color="tab:orange")
    ax2.set_ylabel("W_max, Дж", color="tab:orange")
    ax[1, 1].set_title("Критерії надійності")
    l1, lb1 = ax[1, 1].get_legend_handles_labels()
    l2, lb2 = ax2.get_legend_handles_labels()
    ax[1, 1].legend(l1 + l2, lb1 + lb2, loc="upper right")

    for a in ax.flat:
        a.set_xlabel("Покоління"); a.grid(alpha=0.3)
    fig.tight_layout()

    out = pathlib.Path(explicit_out) if explicit_out else auto_output_path(log_dir, g_ids[-1])
    fig.savefig(out, dpi=150)
    print(f"Збережено: {out}  (поколінь: {len(g_ids)})")


if __name__ == "__main__":
    main()
