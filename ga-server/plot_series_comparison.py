"""
plot_series_comparison.py — порівняльний рисунок для статті (Рис.4, 6, 7...):
кілька гілок/серій (curriculum strategy, mutation strategy, уставки тощо),
у кожній кілька сідів, накладені криві "успіх, %" і "похибка (min)" поруч —
2 рядки × N стовпців (N = кількість серій).

ДЖЕРЕЛО ДАНИХ: run_id-папки в logs/ (кожна — з config.json і gen_*.json),
передаються ЯВНО через --series (безпечніше за автосканування директорії,
бо ми вже мали випадки мітки series_label, що не відповідала фактичному
режиму прогону — краще один раз звірити run_id вручну, ніж довіряти
автогрупуванню наосліп).

Приклад для Рис.4 (self-paced vs open-loop, по 3 сіди):
  python plot_series_comparison.py ^
    --series "Self-paced:run_20260809_165204,run_20260809_173652,run_20260809_181843" ^
    --series "Open-loop:run_20260809_230221,run_20260810_084828,run_20260810_102634" ^
    --output C:\\simulation\\images\\article_figures\\fig04_curriculum_comparison.png

Без --logs-dir шукає run_id-папки в ./logs (запускати з ga-server/, як і
plot_convergence.py). Без --output — автозбереження в OUTPUT_DIR (той самий,
що в plot_convergence.py) з іменем fig_comparison_<таймстемп>.png.
"""
import argparse
import datetime
import json
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUTPUT_DIR = pathlib.Path(r"C:\simulation\images")
PALETTE = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]  # до 5 сідів/серію


def load_run(logs_dir: pathlib.Path, run_id: str) -> dict:
    run_dir = logs_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Не знайдено папку прогону: {run_dir}")
    cfg_path = run_dir / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}

    g_ids, succ, prec_min, tol = [], [], [], []
    for f in sorted(run_dir.glob("gen_*.json")):
        g = json.loads(f.read_text(encoding="utf-8"))
        rs = g.get("results", [])
        if not rs:
            continue
        g_ids.append(g["generation_id"])
        succ.append(100.0 * sum(bool(r.get("success", False)) for r in rs) / len(rs))
        prec_min.append(min(r.get("precision_error", 1.0) for r in rs))
        tol.append(g.get("tolerance"))

    if not g_ids:
        raise ValueError(f"У {run_dir} немає жодного gen_*.json з результатами")

    return {"run_id": run_id, "seed": cfg.get("seed"),
            "curriculum_strategy": cfg.get("curriculum_strategy"),
            "g_ids": g_ids, "succ": succ, "prec_min": prec_min, "tol": tol}


def parse_series_arg(s: str):
    if ":" not in s:
        raise ValueError(f'--series має формат "Назва:run_id1,run_id2,..." — отримано: {s!r}')
    label, ids = s.split(":", 1)
    run_ids = [x.strip() for x in ids.split(",") if x.strip()]
    if not run_ids:
        raise ValueError(f"Серія {label!r} не містить жодного run_id")
    return label.strip(), run_ids


def build_figure(groups: list[tuple[str, list[dict]]]):
    n = len(groups)
    fig, ax = plt.subplots(2, n, figsize=(5.5 * n, 8), squeeze=False)
    fig.suptitle("Series comparison — success rate and precision", fontsize=13)

    for col, (label, runs) in enumerate(groups):
        for i, r in enumerate(runs):
            color = PALETTE[i % len(PALETTE)]
            seed_lbl = f"seed={r['seed']}" if r["seed"] is not None else r["run_id"]
            ax[0, col].plot(r["g_ids"], r["succ"], color=color, lw=1.6, label=seed_lbl)
            ax[1, col].semilogy(r["g_ids"], r["prec_min"], color=color, lw=1.6, label=seed_lbl)
            if any(t is not None for t in r["tol"]):
                ax[1, col].semilogy(r["g_ids"], [t if t else None for t in r["tol"]],
                                    color=color, ls=":", lw=1.0, alpha=0.55)

        ax[0, col].set_title(f"{label}\nsuccessful assemblies, %")
        ax[0, col].set_ylim(-2, 102)
        ax[0, col].legend(fontsize=8, loc="upper left")
        ax[0, col].set_xlabel("Generation"); ax[0, col].grid(alpha=0.3)

        ax[1, col].axhline(0.005, color="red", ls="--", lw=0.8, label="5 mm tolerance")
        ax[1, col].set_title(f"{label}\nprecision (min), m — dotted = tolerance")
        ax[1, col].legend(fontsize=8, loc="upper right")
        ax[1, col].set_xlabel("Generation"); ax[1, col].grid(alpha=0.3)

    fig.tight_layout()
    return fig


def main():
    ap = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--series", action="append", required=True,
        help='Формат: "Назва:run_id1,run_id2,run_id3". Можна вказувати кілька разів.')
    ap.add_argument("--logs-dir", default="logs")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    logs_dir = pathlib.Path(args.logs_dir)
    groups = []
    for s in args.series:
        label, run_ids = parse_series_arg(s)
        runs = [load_run(logs_dir, rid) for rid in run_ids]
        groups.append((label, runs))
        print(f"{label}: {len(runs)} прогонів "
              f"(сіди: {[r['seed'] for r in runs]})")

    fig = build_figure(groups)

    if args.output:
        out = pathlib.Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
    else:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out = OUTPUT_DIR / f"fig_comparison_{ts}.png"
    fig.savefig(out, dpi=150)
    print(f"Збережено: {out}")


if __name__ == "__main__":
    main()
