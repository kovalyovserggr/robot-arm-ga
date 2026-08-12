"""
plot_pareto_front.py — Рис.8: 2D-проекції фронту Парето NSGA-II-прогону.

Збирає допустимих (feasible=True) особин з останніх --last-n-gens
поколінь у СПІЛЬНИЙ архів і ПЕРЕРАХОВУЄ справжнє недоміноване множення
по всіх наявних критеріях одночасно (T, E, W_cv, W_max_over_M, M) —
НЕ довіряє полю "rank" із логів напряму, бо те написане окремо для
кожного покоління: особина з rank=0 у своєму поколінні могла вже бути
домінована кимось з іншого покоління після об'єднання в архів.

Малює кожну запитану пару критеріїв (--pairs) в окремій панелі:
недомінований архівний фронт — великі кольорові маркери (з'єднані
лінією за зростанням X, стандартна конвенція для читабельності),
допустимі, але доміновані — дрібні сірі точки.

Запуск (дефолт: пари M-W_cv і E-W_max_over_M — компроміс, знайдений
раніше у champions_comparison):
  python plot_pareto_front.py --run-id run_20260810_131108

Кілька останніх поколінь разом (щільніший архів) і свої пари критеріїв:
  python plot_pareto_front.py --run-id run_... --last-n-gens 15 \
    --pairs "M,W_cv" "E,W_max_over_M" "T,M"
"""
import argparse
import json
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUTPUT_DIR = pathlib.Path(r"C:\simulation\images")
DEFAULT_PAIRS = [("M", "W_cv"), ("E", "W_max_over_M")]


def load_archive(run_dir: pathlib.Path, last_n: int, tag: str) -> list[dict]:
    """Допустимі особини з останніх last_n gen_*.json, з їхніми objectives.
    tag — мітка джерела (run_id/seed), щоб потім відрізняти на графіку
    при об'єднанні кількох прогонів в один архів."""
    files = sorted(run_dir.glob("gen_*.json"))
    if not files:
        raise FileNotFoundError(f"У {run_dir} немає gen_*.json")
    files = files[-last_n:]

    archive = []
    n_missing_obj = 0
    for f in files:
        g = json.loads(f.read_text(encoding="utf-8"))
        for r in g.get("results", []):
            if not r.get("feasible"):
                continue
            obj = r.get("objectives")
            if not obj or "M" not in obj:
                n_missing_obj += 1
                continue
            archive.append({"generation": g["generation_id"],
                            "individual_id": r.get("individual_id"),
                            "tag": tag, "obj": obj})
    if n_missing_obj:
        print(f"[!] {tag}: пропущено {n_missing_obj} допустимих особин без повного "
              f"вектора objectives")
    return archive


def dominates_full(a: dict, b: dict) -> bool:
    """Домінування по ВСІХ спільних ключах objectives (мінімізація)."""
    keys = a.keys()
    le = all(a[k] <= b[k] for k in keys)
    lt = any(a[k] < b[k] for k in keys)
    return le and lt


def nondominated_mask(archive: list[dict]) -> list[bool]:
    objs = [item["obj"] for item in archive]
    n = len(objs)
    dominated = [False] * n
    for i in range(n):
        for j in range(n):
            if i != j and dominates_full(objs[j], objs[i]):
                dominated[i] = True
                break
    return [not d for d in dominated]


SEED_PALETTE = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
                "#8c564b", "#e377c2"]


def build_figure(archive: list[dict], front_mask: list[bool],
                 pairs: list[tuple[str, str]], color_by_seed: bool):
    n = len(pairs)
    fig, ax = plt.subplots(1, n, figsize=(6 * n, 5.5), squeeze=False)
    ax = ax[0]
    n_front = sum(front_mask)
    tags = sorted(set(a["tag"] for a in archive))
    tag_color = {t: SEED_PALETTE[i % len(SEED_PALETTE)] for i, t in enumerate(tags)}

    title = f"Pareto front projections (archive: {len(archive)} feasible individuals"
    if len(tags) > 1:
        title += f" from {len(tags)} runs"
    title += f", {n_front} non-dominated)"
    fig.suptitle(title, fontsize=13)

    for col, (xk, yk) in enumerate(pairs):
        xs_dom = [a["obj"][xk] for a, m in zip(archive, front_mask) if not m]
        ys_dom = [a["obj"][yk] for a, m in zip(archive, front_mask) if not m]
        ax[col].scatter(xs_dom, ys_dom, s=14, color="lightgray",
                        label=f"feasible, dominated (n={len(xs_dom)})", zorder=1)

        front_items = [a for a, m in zip(archive, front_mask) if m]
        front_sorted = sorted(front_items, key=lambda a: a["obj"][xk])
        if front_sorted:
            fx = [a["obj"][xk] for a in front_sorted]
            fy = [a["obj"][yk] for a in front_sorted]
            ax[col].plot(fx, fy, color="#888888", lw=1.0, ls="--", alpha=0.5, zorder=2)
            if color_by_seed and len(tags) > 1:
                for t in tags:
                    tx = [a["obj"][xk] for a in front_sorted if a["tag"] == t]
                    ty = [a["obj"][yk] for a in front_sorted if a["tag"] == t]
                    if tx:
                        ax[col].scatter(tx, ty, s=45, color=tag_color[t],
                                        edgecolor="black", linewidth=0.5,
                                        label=f"{t} (n={len(tx)})", zorder=3)
            else:
                ax[col].scatter(fx, fy, s=45, color="#d62728", edgecolor="black",
                                linewidth=0.5, label=f"non-dominated (n={len(fx)})", zorder=3)

        ax[col].set_xlabel(xk); ax[col].set_ylabel(yk)
        ax[col].set_title(f"{yk} vs {xk}")
        ax[col].legend(fontsize=7)
        ax[col].grid(alpha=0.3)

    fig.tight_layout()
    return fig


def main():
    ap = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", nargs="+", required=True,
        help="Один чи кілька run_id (кілька -> об'єднаний багатосідовий архів)")
    ap.add_argument("--logs-dir", default="logs")
    ap.add_argument("--last-n-gens", type=int, default=1,
        help="Скільки останніх поколінь КОЖНОГО прогону об'єднати в архів")
    ap.add_argument("--pairs", nargs="+", default=None,
        help='Пари критеріїв "X,Y" (за замовч.: "M,W_cv" "E,W_max_over_M")')
    ap.add_argument("--color-by-seed", action="store_true",
        help="Розфарбувати недомінований фронт за джерельним run_id (для кількох --run-id)")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    logs_dir = pathlib.Path(args.logs_dir)
    archive = []
    for run_id in args.run_id:
        part = load_archive(logs_dir / run_id, args.last_n_gens, tag=run_id)
        print(f"{run_id}: {len(part)} допустимих особин "
              f"(останні {args.last_n_gens} покоління)")
        archive.extend(part)

    if not archive:
        raise ValueError("Жодної допустимої особини з повним вектором objectives "
                         "не знайдено в жодному прогоні — нема що малювати")

    front_mask = nondominated_mask(archive)
    print(f"Разом: {len(archive)} допустимих особин, "
          f"недомінованих у повному 5D-просторі: {sum(front_mask)}")

    if args.pairs:
        pairs = [tuple(p.split(",")) for p in args.pairs]
    else:
        pairs = DEFAULT_PAIRS

    fig = build_figure(archive, front_mask, pairs, args.color_by_seed)

    if args.output:
        out = pathlib.Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
    else:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        tag = args.run_id[0] if len(args.run_id) == 1 else f"multi{len(args.run_id)}"
        out = OUTPUT_DIR / f"pareto_front_{tag}.png"
    fig.savefig(out, dpi=150)
    print(f"Збережено: {out}")


if __name__ == "__main__":
    main()
