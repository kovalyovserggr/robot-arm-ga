"""
GA-сервер для оптимізації конструкції та кінематики роботизованої руки.
Запуск:  python -m uvicorn main:app --host 127.0.0.1 --port 8000
Swagger: http://127.0.0.1:8000/docs
"""
import json as _json
import pathlib
import subprocess
from datetime import datetime
from fastapi import FastAPI, HTTPException
from protocol import ExperimentConfig, Generation, GenerationResults, Genome
from ga_engine import GAEngine
from nsga2_engine import NSGA2Engine

app = FastAPI(title="GA Robot-Arm Optimization Server", version="0.3")

# Т7 (robustness): "підкладені" наперед геноми для НАСТУПНОГО
# /experiment/start — одноразове використання, дозволяє прогнати
# конкретні (напр. збурені) геноми через звичайний Unity-цикл без
# жодних змін клієнта. Заповнюється /experiment/stage_fixed_genomes.
PENDING_FIXED_GENOMES: list[dict] | None = None

# ── Stage 1 baseline: зважена згортка (Р7) ──────────────────────────────
T_REF, E_REF, W_REF = 30.0, 2000.0, 1000.0
W_T, W_E, W_CV, W_MAX = 0.30, 0.30, 0.20, 0.20
FAIL_PENALTY, PREC_SCALE, COLL_PENALTY = 5.0, 3.0, 0.05
FAIL_EFF_DISCOUNT = 0.1

def weighted_sum_fitness(r) -> float:
    """Обчислюється завжди (для логів/графіків/дотикового вибору
    чемпіона), незалежно від того, який рушій керує відбором."""
    eff = (W_T * r.assembly_time / T_REF
           + W_E * r.energy / E_REF
           + W_CV * r.wear_cv
           + W_MAX * r.wear_max / W_REF
           + COLL_PENALTY * r.collisions)
    if r.success:
        return -eff
    return -(FAIL_PENALTY + PREC_SCALE * r.precision_error + FAIL_EFF_DISCOUNT * eff)


# ── Self-paced curriculum допуску (тригер Шмітта, Т10) ──────────────────
TOL_START, TOL_MIN, TOL_MAX = 0.05, 0.005, 0.08
TOL_SHRINK = 0.96

def update_tolerance(success_rate: float, generation_id: int, cfg) -> float:
    if cfg.curriculum_strategy == "open_loop":
        # Сліпий розклад (Серія A, докод-git епоха): не залежить від
        # success_rate взагалі — стискається за календарем поколінь.
        tol = max(TOL_MIN, TOL_START * (0.98 ** generation_id))
        STATE["tolerance"] = tol
        return tol
    if cfg.curriculum_strategy != "self_paced":
        raise ValueError(f"Невідома curriculum_strategy: {cfg.curriculum_strategy}")
    # self_paced: тригер Шмітта (реалізація без змін)
    tol = STATE.get("tolerance", TOL_START)
    if success_rate >= cfg.curriculum_gate_tighten:
        tol = max(TOL_MIN, tol * TOL_SHRINK)
    elif cfg.curriculum_gate_loosen > 0 and success_rate < cfg.curriculum_gate_loosen:
        tol = min(TOL_MAX, tol / TOL_SHRINK)
    STATE["tolerance"] = tol
    return tol


STATE: dict = {"engine": None, "config": None, "log_dir": None}
LOG_ROOT = pathlib.Path("logs"); LOG_ROOT.mkdir(exist_ok=True)

ENGINES = {"weighted_sum": GAEngine, "nsga2": NSGA2Engine}


@app.post("/experiment/stage_fixed_genomes")
def stage_fixed_genomes(genomes: list[Genome]):
    """Т7 (robustness): підкладає ЯВНИЙ список геномів для наступного
    /experiment/start — сервер віддасть саме їх замість випадкової
    популяції. Постав Unity Population Size = len(genomes),
    Max Generations = 1, потім Play. Одноразово — після використання
    очищається."""
    global PENDING_FIXED_GENOMES
    PENDING_FIXED_GENOMES = [g.model_dump() for g in genomes]
    return {"staged": len(PENDING_FIXED_GENOMES),
            "note": "Постав Unity Population Size="
                    f"{len(PENDING_FIXED_GENOMES)}, Max Generations=1, тоді Play."}


@app.post("/experiment/start", response_model=Generation)
def start_experiment(cfg: ExperimentConfig):
    """Ініціалізує обраний рушій (Р7: weighted_sum | nsga2) і повертає
    покоління 0."""
    EngineClass = ENGINES.get(cfg.optimizer)
    if EngineClass is None:
        raise HTTPException(400, f"Невідомий optimizer: {cfg.optimizer!r}. "
                                 f"Доступні: {list(ENGINES)}")
    engine = EngineClass(cfg.population_size, cfg.construction_gene_count,
                         cfg.motion_gene_count, cfg.seed,
                         mutation_strategy=cfg.mutation_strategy)

    run_dir = LOG_ROOT / f"run_{datetime.now():%Y%m%d_%H%M%S}"
    run_dir.mkdir(parents=True, exist_ok=True)
    cfg_payload = cfg.model_dump()
    try:
        cfg_payload["git_commit"] = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=pathlib.Path(__file__).parent).stdout.strip() or "unknown"
    except Exception:
        cfg_payload["git_commit"] = "unknown"
    cfg_payload["server_version"] = app.version
    (run_dir / "config.json").write_text(_json.dumps(cfg_payload, indent=2),
                                         encoding="utf-8")

    # Автофакти прогону (регламент §5): ЛИШЕ об'єктивні поля, без
    # інтерпретації — сенс/висновок дописуєш вручну в docs/ua/runs_index.md
    # після прогону. Окремий файл, щоб не ризикувати автоправками
    # куратованого журналу.
    try:
        idx_dir = pathlib.Path(__file__).parent.parent / "docs" / "ua"
        idx_dir.mkdir(parents=True, exist_ok=True)
        idx_path = idx_dir / "runs_index_auto.md"
        if not idx_path.exists():
            idx_path.write_text(
                "# Автофакти прогонів (без інтерпретації) — сирі дані для "
                "docs/ua/runs_index.md\n\n"
                "| run_id | дата | git-хеш | optimizer | сід | population | "
                "max_generations | мета (заповнити вручну) |\n"
                "|---|---|---|---|---|---|---|---|\n", encoding="utf-8")
        with idx_path.open("a", encoding="utf-8") as f:
            f.write(f"| {run_dir.name} | {datetime.now():%Y-%m-%d %H:%M} | "
                    f"{cfg_payload['git_commit']} | {cfg.optimizer} | "
                    f"{cfg.seed} | {cfg.population_size} | "
                    f"{cfg.max_generations} | <TODO> |\n")
    except Exception as e:
        print(f"[runs_index_auto] запис не вдався (не критично): {e}")

    STATE["engine"], STATE["config"], STATE["log_dir"] = engine, cfg, run_dir
    STATE["tolerance"] = TOL_START
    STATE["champion"] = None
    STATE["git_commit"] = cfg_payload["git_commit"]

    global PENDING_FIXED_GENOMES
    if PENDING_FIXED_GENOMES is not None:
        if len(PENDING_FIXED_GENOMES) != cfg.population_size:
            raise HTTPException(400, f"Підкладено {len(PENDING_FIXED_GENOMES)} геномів, "
                                     f"а Population Size={cfg.population_size} — мають "
                                     f"збігатись. Постав Population Size="
                                     f"{len(PENDING_FIXED_GENOMES)}.")
        engine.generation_id = 0
        engine.population = [
            Genome(individual_id=i, construction=g["construction"], motion=g["motion"])
            for i, g in enumerate(PENDING_FIXED_GENOMES)
        ]
        PENDING_FIXED_GENOMES = None  # одноразово
        genomes = engine.population
    else:
        genomes = engine.init_population()

    return Generation(generation_id=0, genomes=genomes,
                      success_tolerance=STATE["tolerance"])


@app.post("/experiment/results", response_model=Generation)
def submit_results(res: GenerationResults):
    """Приймає сирі метрики покоління N, повертає покоління N+1."""
    engine = STATE["engine"]
    cfg: ExperimentConfig = STATE["config"]
    if engine is None:
        raise HTTPException(409, "Experiment not started. POST /experiment/start first.")
    if res.generation_id != engine.generation_id:
        raise HTTPException(409, f"Expected results for generation "
                                 f"{engine.generation_id}, got {res.generation_id}.")

    # Скалярний fitness — завжди для логів/champion tie-break, НЕ для
    # відбору під NSGA-II (той працює з сирими метриками напряму).
    for r in res.results:
        r.fitness = weighted_sum_fitness(r)

    # FIX (сесія 2026-08): захоплюємо ДІЮЧИЙ допуск ДО того, як
    # update_tolerance() його перезапише на значення для НАСТУПНОГО
    # покоління. Раніше champion.json зберігав tol ПІСЛЯ оновлення —
    # тобто допуск, стиснутий уже ЗАВДЯКИ успіху цього самого чемпіона,
    # а не той (ширший), під який він реально пройшов монтаж. Наслідок:
    # ChampionReplay вимагав від чемпіона суворішого порогу, ніж той,
    # для якого він оптимізувався — детермінований, стабільний
    # псевдо-провал при повторному відтворенні (виявлено спостереженням
    # Сергія: 10 повторів поспіль дають ІДЕНТИЧНИЙ провал — не шум).
    active_tol = STATE.get("tolerance", TOL_START)

    success_rate = sum(r.success for r in res.results) / max(len(res.results), 1)
    tol = update_tolerance(success_rate, engine.generation_id, cfg)

    # Стара популяція (та, що щойно оцінена) — потрібна для геному
    # чемпіона; next_generation() її замінить.
    prev_pop_by_id = {g.individual_id: g for g in engine.population}

    # Крок еволюції — ДО логування, щоб забрати engine.last_eval
    # (об'єктиви/ранг/crowding NSGA-II) саме для цього покоління.
    genomes = engine.next_generation(res.results)
    best = engine.best_fitness()

    log_payload = res.model_dump()
    log_payload["tolerance"] = active_tol  # FIX: діючий на це покоління, не наступний
    log_payload["success_rate"] = success_rate
    log_payload["optimizer"] = cfg.optimizer
    last_eval = getattr(engine, "last_eval", None)
    if last_eval:
        for r in log_payload["results"]:
            ev = last_eval.get(r["individual_id"])
            if ev:
                r.update(ev)
    (STATE["log_dir"] / f"gen_{res.generation_id:04d}.json").write_text(
        _json.dumps(log_payload, indent=2), encoding="utf-8")

    # Чемпіон: серед rank-0 фронту (якщо є — NSGA-II), інакше
    # глобальний максимум скалярного fitness (weighted_sum).
    front_ids = getattr(engine, "front_ids", None)
    pool = ([r for r in res.results if r.individual_id in front_ids]
            if front_ids else res.results) or res.results
    best_r = max(pool, key=lambda r: r.fitness)
    champ = STATE.get("champion")
    genome_of_best = prev_pop_by_id.get(best_r.individual_id)
    if genome_of_best is not None and (champ is None or best_r.fitness > champ["fitness"]):
        ev = (last_eval or {}).get(best_r.individual_id, {})
        champ = {"generation": res.generation_id, "fitness": best_r.fitness,
                 "tolerance": active_tol, "metrics": best_r.model_dump(),
                 "objectives": ev.get("objectives"), "rank": ev.get("rank"),
                 "genome": genome_of_best.model_dump()}
        STATE["champion"] = champ
        (STATE["log_dir"] / "champion.json").write_text(
            _json.dumps(champ, indent=2), encoding="utf-8")

    done = engine.generation_id >= cfg.max_generations or (
        cfg.target_fitness is not None and best is not None and best >= cfg.target_fitness)

    if done:
        try:
            from plot_convergence import generate_convergence_plot
            out = generate_convergence_plot(STATE["log_dir"])
            print(f"[GA] Прогін завершено, графік: {out}")
        except Exception as e:
            out = None
            print(f"[GA] Автопобудова графіка не вдалась (не критично): {e}")

        # Автоматизація FIGURE_MANIFEST: лише для позначених серій
        # (series_label непорожній) — групує прогони під одним лейблом,
        # людина лише дописує "Назва/зміст" і фінальний вибір рисунка.
        if cfg.series_label:
            try:
                idx_dir = pathlib.Path(__file__).parent.parent / "docs" / "ua"
                idx_dir.mkdir(parents=True, exist_ok=True)
                man_path = idx_dir / "figure_manifest_auto.md"
                if not man_path.exists():
                    man_path.write_text(
                        "# Автоматичний маніфест серій — сирі дані для "
                        "docs/ua/FIGURE_MANIFEST.md\n\n"
                        "| series_label | run_id | git-хеш | сід | графік |\n"
                        "|---|---|---|---|---|\n", encoding="utf-8")
                with man_path.open("a", encoding="utf-8") as f:
                    f.write(f"| {cfg.series_label} | {STATE['log_dir'].name} | "
                            f"{STATE.get('git_commit', 'unknown')} | {cfg.seed} | {out} |\n")
            except Exception as e:
                print(f"[figure_manifest_auto] запис не вдався (не критично): {e}")

    return Generation(generation_id=engine.generation_id, genomes=genomes,
                      done=done, best_fitness=best, success_tolerance=tol)


@app.get("/experiment/status")
def status():
    engine = STATE.get("engine")
    if engine is None:
        return {"running": False}
    return {"running": True, "generation": engine.generation_id,
            "optimizer": STATE["config"].optimizer, "history": engine.history}


@app.get("/experiment/champion")
def champion():
    ch = STATE.get("champion")
    if ch is None:
        raise HTTPException(404, "Чемпіона ще немає.")
    return ch


@app.post("/experiment/champion/load")
def load_champion_from_run(run_id: str):
    """Підвантажує champion.json ЗАВЕРШЕНОГО прогону в поточну пам'ять
    сервера (STATE["champion"]), щоб ChampionReplay.cs (живий GET
    /experiment/champion) міг показати чемпіона старого прогону навіть
    після рестарту сервера — файл на диску переживає рестарти, пам'ять
    STATE ні. Виклик: POST /experiment/champion/load?run_id=run_20260810_131108
    """
    ch_path = LOG_ROOT / run_id / "champion.json"
    if not ch_path.exists():
        raise HTTPException(404, f"Немає champion.json у {LOG_ROOT / run_id}")
    ch = _json.loads(ch_path.read_text(encoding="utf-8"))
    STATE["champion"] = ch
    return {"loaded": run_id, "generation": ch.get("generation"),
            "fitness": ch.get("fitness")}


@app.get("/experiment/pareto_front")
def pareto_front():
    """Поточний фронт Парето (rank-0): id + об'єктиви. Порожньо для
    weighted_sum-рушія (там немає фронту за визначенням)."""
    engine = STATE.get("engine")
    if engine is None:
        raise HTTPException(404, "Experiment not started.")
    front_ids = getattr(engine, "front_ids", set())
    last_eval = getattr(engine, "last_eval", {})
    return {"generation": engine.generation_id,
            "front": [{"individual_id": i, **last_eval.get(i, {})}
                      for i in sorted(front_ids)]}
