# RobotArmGA — Evolutionary Co-Optimization of a Robotic Arm for Assembly

Client–server framework for co-optimizing the **structure (DH parameters)
and motion (phase keyframes)** of a 6R manipulator performing a
pick-and-place assembly operation (mounting a module on an agricultural
drone), with **efficiency and reliability (wear) criteria**.

- **Server** (Python, FastAPI): evolutionary engine — GA with weighted-sum
  baseline (NSGA-II in progress), P-controller of mutation step size,
  self-paced curriculum of task difficulty with hysteresis (Schmitt trigger).
- **Client** (Unity 6, C#): massively parallel physical evaluation —
  up to 100 isolated platforms per generation, PhysX reduced-coordinate
  articulation solver, automatic metric collection.

The HTTP/JSON protocol is engine-agnostic: the server sees only genomes
and raw metrics, so evaluation back-ends are interchangeable.

## Requirements

- Unity **6000.3.8f1** (URP template) + package `com.unity.nuget.newtonsoft-json`
- Python **3.12+** — `pip install -r requirements.txt`

## Quick start

1. Start the server:
   ```bash
   cd ga-server
   python -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```
   Swagger UI for manual testing: http://127.0.0.1:8000/docs
2. Open the Unity project, scene `SampleScene`; on the experiment
   GameObject check in the Inspector:
   `GAExperimentClient` — Server Url `http://127.0.0.1:8000`,
   Population Size 100, Construction Gene Count 18, Motion Gene Count 24;
   `ExperimentOrchestrator` — Platform Count 100, assigned Object Material.
3. Press Play (or run a built player; `-batchmode -nographics` supported).
   An on-screen HUD shows generation, current tolerance, grasp radius
   and success rate.
4. Per-run logs are written to `ga-server/logs/run_YYYYMMDD_HHMMSS/`
   (one JSON per generation + `config.json` + `champion.json`).
   Convergence plots:
   ```bash
   python plot_convergence.py logs result.png   # picks the latest run
   ```
5. Champion replay: empty scene → `ChampionReplay` component →
   Play (fetches the best individual via `GET /experiment/champion`).

## Protocol

| Method | Path | Purpose |
|---|---|---|
| POST | `/experiment/start`   | config → generation 0 |
| POST | `/experiment/results` | raw metrics of gen N → genomes of gen N+1 |
| GET  | `/experiment/status`  | generation index, convergence history |
| GET  | `/experiment/champion`| best individual of the run (genome + metrics) |

Fitness is computed **server-side from raw metrics** (assembly time,
mechanical work per joint, wear uniformity W_cv, peak wear W_max,
precision, collisions, success flag) — the client never aggregates.

## Repository layout

```
RobotArmGA/   Unity project (sources only)
ga-server/    Python server (engine, protocol, plotting)
docs/en/      design documents (this language)
docs/ua/      lab notebook and originals (Ukrainian)
figures/      final article figures
```

Key documents: `docs/en/DECISIONS.md` (architectural decision records),
`docs/en/GENOME_SPEC.md` (genome and environment specification).

## Reproducibility

Fixed server/client seeds, fixed physics timestep (0.02 s), per-run
`config.json` with full experiment configuration; official series are
run from tagged code versions. Raw logs of reported series are archived
separately (see Data Availability of the article).

## License

MIT (see LICENSE).
