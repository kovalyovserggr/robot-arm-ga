# RobotArmGA — Architectural Decision Records (ADR)

Recorded: 2026-07-08, updated 2026-07-09 (v1.1 amendments marked).
Project: co-optimization of the structure and motion kinematics of a
robotic arm for mounting a module on an agricultural drone.
Target: Scopus article (MDPI Machines) + dissertation chapter.
Ukrainian originals of all working documents: docs/ua/.

## R1. Architecture: client–server, HTTP REST
- Unity 6 (client, physical experiment) ↔ Python FastAPI (server, EA).
- Engine-agnostic protocol: the server operates on genomes and raw
  metrics only. Synchronization — long polling; RNG seeds fixed in config.
- Status: implemented; end-to-end cycle verified.

## R2. Simulator: Unity 6 (PhysX) + cross-validation in MuJoCo
- Main experiments: Unity ArticulationBody (reduced-coordinate PhysX
  solver — the same family as NVIDIA Isaac). Fixed timestep, fixed
  seeds, physically isolated platforms.
- Cross-validation: 5–10 final Pareto-optimal individuals reproduced in
  MuJoCo as an independent engine → "Cross-engine validation" subsection.
- Side contribution: engine-agnostic evaluation protocol.

## R3. Topology: fixed, six revolute joints (6R)
- The number of links does not evolve (fixed-length genome, standard
  evolutionary operators).

## R4. Structural genes: DH parameters
- Per link i: a_i (link length), α_i (twist), d_i (axial offset) →
  6×3 = 18 genes. Non-redundant encoding; standard convention familiar
  to reviewers. Deployed in Unity as a Transform chain.

## R5. Motion genes: key joint angles per phase (direct encoding, FK)
- 4 assembly phases (approach/grasp → transfer → positioning →
  placement) × 6 joints = 24 genes; stored normalized in [-1, 1],
  expanded to angles within joint limits.
- Keyframe tracking via ArticulationBody drives (PD-type).
- IK is not used inside the genome (it produces a discontinuous fitness
  landscape); IK is allowed only for seeding part of the initial
  population.
- Extension (separate experiment): +4 phase-duration genes.
- Total: 42 genes.

## R6. Criteria (multi-objective efficiency + reliability)
- T — operation time.
- E — energy as mechanical work, E = Σ_t Σ_i |τ_i·Δθ_i|. The drive
  torque is estimated from the drive model τ = k(θ* − θ) − c·θ̇,
  clamped by the force limit (Unity does not expose the internally
  applied drive torque directly).
- W_cv — wear unevenness: coefficient of variation of accumulated
  per-joint work (wear proxy justified by the Archard model).
- W_max — peak accumulated work of the most loaded joint.
- Constraint (not a criterion): successful assembly within the position
  tolerance → constrained domination in NSGA-II. A motionless
  individual is infeasible by definition.
- v1.1 amendment: success additionally requires near-zero part velocity
  at placement (≤ 0.3 m/s) — "placed, not thrown" (closes the
  fly-through exploit observed in the v1.0 champion).

## R7. Optimization method: two stages
- Stage 1 (baseline): hierarchical weighted sum, classical GA.
- Stage 2 (main): NSGA-II with constrained domination, Pareto front.
- The stage comparison is a separate results subsection.
- NSGA-III noted as a perspective (4–5 objectives is the comfort limit
  of NSGA-II).

## R8. Population 100, platforms 100
Justification (triangle of constraints):
1) EA: 2–4 × genome length (42) → 84–168; NSGA-II needs ~100 to
   maintain the front across 4 objectives (canonical Deb settings);
2) Physics: 100 arms × 6 joints — within PhysX CPU capacity;
3) Time: platforms ≥ population → generation wall time is independent
   of population size. Larger populations are evaluated in batches
   (protocol supports it).

## R9. Reproducibility (mandatory for all experiments)
- Fixed: server seed, client seeds, physics timestep, Unity/package
  versions. Per-generation JSON logs; per-run config.json.
- Official series: ≥3 seeds per point; code version = git tag.

## R10. Article positioning
- Contribution: co-optimization of structure (DH) and motion kinematics
  under efficiency AND reliability criteria (wear uniformity/peak) with
  constrained-domination NSGA-II, validated on a parallelized physical
  simulation of an assembly operation; engine-agnostic protocol;
  closed-loop control of the evolutionary search (step-size
  P-controller, self-paced curriculum with hysteresis).
- Related work: four camps — (A) NSGA-II trajectories; (B) structural
  optimization; (C) morphology+control co-design; (D) wear/reliability.
  Gap = (C) ∩ (D). Differentiation from wear studies: they optimize the
  placement/trajectory of a fixed machine; here the machine itself is
  designed for minimal and uniform wear.
- Reviewer-risk mitigation: sim-only → cross-validation (R2) +
  limitations; "game engine" → PhysX/Isaac argument (R2); simplified
  wear → honest proxy + Archard (R6); "yet another NSGA-II" →
  structural genes and reliability criteria in the title/abstract.
