# RobotArmGA — Genome Specification v1.1

Based on decisions R3–R6 (see DECISIONS.md). Supersedes v1.0
(changes: curriculum-controlled tolerance and grasp gate, slow-placement
success condition, drive-model energy measurement, best-approach
precision gradient).

Genome: 42 real-valued genes, each stored normalized g ∈ [-1, 1].
Linear expansion into a physical parameter:

    p = p_min + (g + 1)/2 · (p_max − p_min)                    (1)

All evolutionary operators (crossover, Gaussian mutation, clipping)
act in the normalized space — a single scale for all genes.

## 1. Structural genes (18): DH parameters

Modified Denavit–Hartenberg convention. Link i (i = 1..6) is described
by the triple (a_i, α_i, d_i); the joint variable is θ_i (revolute,
axis z_i). Unity chain: Transform shift along x by a_i → rotation
about x by α_i → shift along z by d_i → ArticulationBody rotating
about local z.

| Index | Gene | Physical meaning | p_min | p_max | Unit |
|---|---|---|---|---|---|
| 0–5   | a_1..a_6 | link length (common normal of axes) | 0 | 0.35 | m |
| 6–11  | α_1..α_6 | twist between adjacent axes | −90 | +90 | ° |
| 12–17 | d_1..d_6 | offset along the joint axis | 0 | 0.30 | m |

Notes:
- a_i = 0 is deliberately allowed: zero-length links let evolution
  "discover" a spherical wrist (industrial 6R standard, a_4 = a_5 = 0).
- The α range is half a circle: α and α ± 180° combined with the sign
  of θ encode mirrored duplicates (harmful redundancy for crossover).
- Maximum reach Σ(a_i + d_i) = 3.9 m — the search space is deliberately
  wider than the workspace; non-viable "short" designs are cut off by
  the success constraint; part of the initial population is seeded with
  guaranteed-reach configurations (§4).

## 2. Motion genes (24): phase keyframes

Assembly phases j = 1..4: (1) approach and grasp → (2) transfer →
(3) positioning above the mount → (4) placement. Gene θ̂_ij is the
target angle of joint i at the end of phase j.

| Index | Gene | Physical meaning | p_min | p_max | Unit |
|---|---|---|---|---|---|
| 18–23 | j=1 | target pose, end of phase 1 | −150 | +150 | ° |
| 24–29 | j=2 | target pose, end of phase 2 | −150 | +150 | ° |
| 30–35 | j=3 | target pose, end of phase 3 | −150 | +150 | ° |
| 36–41 | j=4 | target pose, end of phase 4 | −150 | +150 | ° |

- Joint limits ±150° are typical for industrial revolute joints; fixed
  (do not evolve) in v1.x.
- Start pose θ_i(0) = 0 ∀i — identical for all individuals.
- Tracking: target angles are fed to ArticulationBody drives
  (stiffness/damping are environment constants); the target is linearly
  interpolated inside each phase (inertia and the drive smooth the
  motion).
- Phase durations are fixed in v1.x: t = (2.0, 2.5, 2.5, 2.0) s,
  9 s cycle. Extension: +4 duration genes t_j ∈ [0.5, 4.0] s
  (indices 42–45), a separate experiment.

## 3. Environment constants and event rules

| Parameter | Value | Comment |
|---|---|---|
| Arm base position | (0, 0, 0) | pedestal h = 0.10 m |
| Part pick-up position | (−0.45, 0.20, 0) m | feed stand |
| Mount point on the drone | (+0.50, 0.25, 0.10) m | seat |
| Success tolerance ε | curriculum-controlled | self-paced: shrink ×0.96 when success ≥ θ_up, loosen when < θ_down (Schmitt trigger); bounds [5, 80] mm, start 50 mm |
| Grasp gate | radius = clamp(2ε, 10–80 mm) AND relative speed ≤ 0.5 m/s | "controlled approach", no fly-by grasping |
| Placement (v1.1) | part within ε of the seat during phase ≥ 4 AND part speed ≤ 0.3 m/s | "placed, not thrown" |
| Part mass | 0.15 kg | typical drone module |
| Link linear mass | 2.0 kg/m, min 0.3 kg | uniform cylinder r = 25 mm |
| Platform time limit | 30 s simulated | watchdog |
| Physics timestep | 0.02 s | R9 |

## 4. Population initialization

- 90% of individuals: all genes ~ U(−1, 1).
- 10%: "seeded" — uniform-link construction (a_i = 0.2 m, α alternating
  0/90°, d_i = 0.05 m) + mutation noise σ = 0.15; motions random.
  Guarantees reachable arms from generation 0.
- Optional IK seeding of phases 1 and 3 poses (CCD to part/mount targets).

## 5. Measured metrics (client → IndividualResult)

| Field | Measurement |
|---|---|
| assembly_time (T) | time to success; 30 s limit if failed |
| energy (E) | E = Σ_steps Σ_i |τ_i·Δθ_i|; τ estimated from the drive model τ = k(θ*−θ) − c·θ̇, clamped by the force limit |
| joint_work[6] | accumulated |τ_i·Δθ_i| per joint |
| wear_cv (W_cv) | std(W_1..W_6) / mean(W_1..W_6) |
| wear_max (W_max) | max(W_1..W_6) |
| precision_error | grasped: best distance part↔seat (phase ≥ 3); not grasped: 1 + best approach distance effector↔part over the whole trajectory (clipped at 10 m) |
| collisions | link contacts with forbidden objects and self-collisions (adjacent segments ignored) |
| success | placement condition met before the time limit |

Fitness (Stage 1 baseline) is computed server-side from raw metrics —
all weights live in one place; the client never aggregates.

## 6. Reference figures

- Genome size: 42 (v1.x) / 46 (with phase durations).
- Population: 100 (R8). Mutation: p = 2/42 ≈ 0.05 per gene;
  step size σ controlled by strategy (constant / annealing /
  P-controller σ = clamp(K_p · best precision, 0.02–0.15)).
- One-generation JSON: 100 × 42 floats ≈ 60 KB.
- Client config (Unity Inspector): construction_gene_count = 18,
  motion_gene_count = 24, population_size = 100.
