"""
plot_robustness.py — Рис.10: success rate і похибка (mean±std) за
рівнем шуму привода (Т7). Читає JSON, який виводить
robustness_analysis.py analyze --output ....

Запуск:
  python plot_robustness.py --input docs/ua/robustness_seed43.json \
      --output fig10_robustness.png
"""
import argparse
import json
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUTPUT_DIR = pathlib.Path(r"C:\simulation\images")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True,
        help="JSON з robustness_analysis.py analyze --output ...")
    ap.add_argument("--output", default=None)
    ap.add_argument("--label", default="Seed 43",
        help="Підпис чемпіона для заголовка")
    args = ap.parse_args()

    data = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8"))
    data = sorted(data, key=lambda r: r["noise_deg"])

    levels = [r["noise_deg"] for r in data]
    success = [r["success_rate_pct"] for r in data]
    prec_mean = [r["precision_mean_mm"] for r in data]
    prec_std = [r["precision_std_mm"] for r in data]
    n_vals = [r["n"] for r in data]

    fig, ax = plt.subplots(1, 2, figsize=(11, 4.5))

    labels = [f"{lv:g}\u00B0" for lv in levels]
    bars = ax[0].bar(labels, success, color="#2ca02c", width=0.5)
    for bar, n in zip(bars, n_vals):
        ax[0].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                   f"n={n}", ha="center", fontsize=9)
    ax[0].set_ylim(0, 105)
    ax[0].set_xlabel("Actuator noise level (\u00B0)")
    ax[0].set_ylabel("Success rate, %")
    ax[0].set_title(f"{args.label}: success rate vs. actuator noise")
    ax[0].grid(alpha=0.3, axis="y")

    ax[1].errorbar(levels, prec_mean, yerr=prec_std, fmt="o-",
                   color="#d62728", capsize=5, markersize=7)
    ax[1].set_xlabel("Actuator noise level (\u00B0)")
    ax[1].set_ylabel("Precision error, mm (mean \u00B1 std)")
    ax[1].set_title(f"{args.label}: precision degradation")
    ax[1].grid(alpha=0.3)

    fig.tight_layout()

    if args.output:
        out = pathlib.Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
    else:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out = OUTPUT_DIR / "robustness.png"
    fig.savefig(out, dpi=150)
    print(f"Збережено: {out}")


if __name__ == "__main__":
    main()
