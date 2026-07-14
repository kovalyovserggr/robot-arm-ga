"""
GA-сервер для оптимізації конструкції та кінематики роботизованої руки.
Запуск:  uvicorn main:app --host 127.0.0.1 --port 8000
Swagger: http://127.0.0.1:8000/docs  (інтерактивне тестування без Unity)
"""
import pathlib
from datetime import datetime
from fastapi import FastAPI, HTTPException
from protocol import ExperimentConfig, Generation, GenerationResults
from ga_engine import GAEngine

app = FastAPI(title="GA Robot-Arm Optimization Server", version="0.2")

# ── Згортка критеріїв (baseline, Р7 етап 1) ─────────────────────────────
# Калібрування по реальному прогону 2026-07-08: E ~ 10^3 Дж, W_max ~ 10^2..10^3
T_REF, E_REF, W_REF = 30.0, 2000.0, 1000.0
W_T, W_E, W_CV, W_MAX = 0.30, 0.30, 0.20, 0.20   # ваги критеріїв
FAIL_PENALTY, PREC_SCALE, COLL_PENALTY = 5.0, 3.0, 0.05
FAIL_EFF_DISCOUNT = 0.1  # до успіху ефективність майже не важить

# Self-paced curriculum (замкнений контур, аналогічно P-контролеру сигми):
# допуск стискається ЛИШЕ коли популяція демонструє успішність — інакше
# розклад відривається від реального темпу навчання (спостереження
# прогону 2026-07-08: масова втрата навички захвату на поколіннях 80-90,
# коли ворота стиснулись швидше за уточнення популяції).
TOL_START, TOL_MIN, TOL_MAX = 0.05, 0.005, 0.08
TOL_SHRINK = 0.96                    # крок стискання 4%
# Уставки регулятора (тригер Шмітта) — з конфігу експерименту (Т10):
# стискати при успіху >= gate_tighten, відпускати при < gate_loosen.
# Гістерезис не дає системі "деренчати" на межі і вимирати остаточно.

def update_tolerance(success_rate: float) -> float:
    cfg = STATE["config"]
    tol = STATE.get("tolerance", TOL_START)
    if success_rate >= cfg.curriculum_gate_tighten:
        tol = max(TOL_MIN, tol * TOL_SHRINK)
    elif cfg.curriculum_gate_loosen > 0 and success_rate < cfg.curriculum_gate_loosen:
        tol = min(TOL_MAX, tol / TOL_SHRINK)
    STATE["tolerance"] = tol
    return tol

def weighted_sum_fitness(r) -> float:
    eff = (W_T * r.assembly_time / T_REF
           + W_E * r.energy / E_REF
           + W_CV * r.wear_cv
           + W_MAX * r.wear_max / W_REF
           + COLL_PENALTY * r.collisions)
    if r.success:
        return -eff
    # Ієрархія стимулів: невдахам головний градієнт — ТОЧНІСТЬ.
    # Ефективність дисконтується, щоб еволюція не виводила "ледарів",
    # які мінімізують енергію замість досягати цілі.
    return -(FAIL_PENALTY + PREC_SCALE * r.precision_error
             + FAIL_EFF_DISCOUNT * eff)

STATE: dict = {"engine": None, "config": None, "log_dir": None}
LOG_ROOT = pathlib.Path("logs"); LOG_ROOT.mkdir(exist_ok=True)


@app.post("/experiment/start", response_model=Generation)
def start_experiment(cfg: ExperimentConfig):
    """Ініціалізує GA і повертає покоління 0."""
    engine = GAEngine(cfg.population_size, cfg.construction_gene_count,
                      cfg.motion_gene_count, cfg.seed,
                      mutation_strategy=cfg.mutation_strategy)
    # Кожен прогін — у власну папку: logs/run_YYYYMMDD_HHMMSS
    run_dir = LOG_ROOT / f"run_{datetime.now():%Y%m%d_%H%M%S}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(cfg.model_dump_json(indent=2),
                                         encoding="utf-8")
    STATE["engine"], STATE["config"], STATE["log_dir"] = engine, cfg, run_dir
    STATE["tolerance"] = TOL_START
    STATE["champion"] = None
    return Generation(generation_id=0, genomes=engine.init_population(),
                      success_tolerance=STATE["tolerance"])


@app.post("/experiment/results", response_model=Generation)
def submit_results(res: GenerationResults):
    """Приймає fitness покоління N, повертає покоління N+1 (або done)."""
    engine: GAEngine = STATE["engine"]
    cfg: ExperimentConfig = STATE["config"]
    if engine is None:
        raise HTTPException(409, "Experiment not started. POST /experiment/start first.")
    if res.generation_id != engine.generation_id:
        raise HTTPException(409, f"Expected results for generation "
                                 f"{engine.generation_id}, got {res.generation_id}.")

    # Етап 1 (Р7): скалярна згортка рахується ТУТ, із сирих метрик.
    # Ваги — в одному місці; перехід на NSGA-II не змінить клієнта.
    for r in res.results:
        r.fitness = weighted_sum_fitness(r)

    # Успішність покоління -> оновлення допуску (тригер Шмітта, Т10)
    success_rate = sum(r.success for r in res.results) / max(len(res.results), 1)
    tol = update_tolerance(success_rate)

    # Повний лог результатів — сировина для таблиць/графіків статті
    import json as _json
    log_payload = res.model_dump()
    log_payload["tolerance"] = tol
    log_payload["success_rate"] = success_rate
    (STATE["log_dir"] / f"gen_{res.generation_id:04d}.json").write_text(
        _json.dumps(log_payload, indent=2), encoding="utf-8")

    # Чемпіон: найкраща особина за весь прогін — геном + метрики.
    # Фіксується ДО next_generation, поки популяція ще стара.
    best_r = max(res.results, key=lambda r: r.fitness)
    champ = STATE.get("champion")
    if champ is None or best_r.fitness > champ["fitness"]:
        genome = next((g for g in engine.population
                       if g.individual_id == best_r.individual_id), None)
        if genome is not None:
            champ = {"generation": res.generation_id,
                     "fitness": best_r.fitness,
                     "tolerance": tol,
                     "metrics": best_r.model_dump(),
                     "genome": genome.model_dump()}
            STATE["champion"] = champ
            (STATE["log_dir"] / "champion.json").write_text(
                _json.dumps(champ, indent=2), encoding="utf-8")

    genomes = engine.next_generation(res.results)
    best = engine.best_fitness()

    done = engine.generation_id >= cfg.max_generations or (
        cfg.target_fitness is not None and best is not None
        and best >= cfg.target_fitness)

    return Generation(generation_id=engine.generation_id, genomes=genomes,
                      done=done, best_fitness=best,
                      success_tolerance=tol)


@app.get("/experiment/status")
def status():
    """Стан GA: номер покоління, історія збіжності. Зручно для моніторингу."""
    engine: GAEngine = STATE["engine"]
    if engine is None:
        return {"running": False}
    return {"running": True, "generation": engine.generation_id,
            "history": engine.history}


@app.get("/experiment/champion")
def champion():
    """Найкраща особина прогону: геном + метрики (для ChampionReplay)."""
    ch = STATE.get("champion")
    if ch is None:
        raise HTTPException(404, "Чемпіона ще немає — прогін не стартував "
                                 "або жодне покоління не оцінене.")
    return ch
