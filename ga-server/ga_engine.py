"""
GA-ядро (Р7, Stage 1 — baseline зі зваженою згорткою). Турнірна
селекція, рівномірний кросовер, гаусова мутація з керованою сигмою.
Сюди підключається твій реальний GA з дисертації за потреби:
достатньо зберегти сигнатури init_population() та next_generation().
"""
import random
from protocol import Genome, IndividualResult
from genome_seed import make_seeded_individual

SEED_FRACTION = 0.10  # частка засіяної (гарантовано досяжної) популяції


class GAEngine:
    def __init__(self, population_size: int, construction_genes: int,
                 motion_genes: int, seed: int | None = None,
                 mutation_strategy: str = "p_control"):
        self.pop_size = population_size
        self.n_constr = construction_genes
        self.n_motion = motion_genes
        self.rng = random.Random(seed)

        self.generation_id = 0
        self.population: list[Genome] = []
        self.history: list[dict] = []       # для графіків збіжності у статті

        # Гіперпараметри — винесені явно, бо підуть у таблицю статті
        self.tournament_k = 3
        self.crossover_rate = 0.9
        self.mutation_rate = 0.08
        self.mutation_sigma = 0.15        # σ0 (constant / старт annealing)
        self.elitism = 2

        # ── Керування сигмою (Т4/Т4а) ──────────────────────────────────
        self.mutation_strategy = mutation_strategy
        self.sigma_min, self.sigma_max = 0.02, 0.15
        self.kp = 0.15                    # P-контролер: σ = Kp · prec_best
        self.best_precision = None        # сурогат відстані до оптимуму

    # ── Ініціалізація ────────────────────────────────────────────────────
    def init_population(self) -> list[Genome]:
        self.generation_id = 0
        n_seed = max(1, int(round(self.pop_size * SEED_FRACTION)))
        pop = [make_seeded_individual(self.rng, i, self.n_constr, self.n_motion)
               for i in range(n_seed)]
        pop += [
            Genome(
                individual_id=n_seed + j,
                construction=[self.rng.uniform(-1.0, 1.0) for _ in range(self.n_constr)],
                motion=[self.rng.uniform(-1.0, 1.0) for _ in range(self.n_motion)],
            )
            for j in range(self.pop_size - n_seed)
        ]
        self.rng.shuffle(pop)
        for idx, g in enumerate(pop):
            g.individual_id = idx
        self.population = pop
        return self.population

    # ── Крок еволюції ────────────────────────────────────────────────────
    def next_generation(self, results: list[IndividualResult]) -> list[Genome]:
        fit = {r.individual_id: r.fitness for r in results}
        precs = [r.precision_error for r in results if r.precision_error > 0]
        if precs:
            self.best_precision = min(precs)
        scored = sorted(self.population, key=lambda g: fit.get(g.individual_id, -1e9),
                        reverse=True)

        best = fit.get(scored[0].individual_id, float("-inf"))
        mean = sum(fit.values()) / max(len(fit), 1)
        self.history.append({"generation": self.generation_id,
                             "best": best, "mean": mean,
                             "sigma": self.current_sigma()})

        new_pop: list[Genome] = []
        for g in scored[:self.elitism]:
            new_pop.append(g.model_copy(update={"individual_id": len(new_pop)}))

        while len(new_pop) < self.pop_size:
            p1 = self._tournament(scored, fit)
            p2 = self._tournament(scored, fit)
            c_constr, c_motion = self._crossover(p1, p2)
            self._mutate(c_constr, lo=-1.0, hi=1.0)   # FIX: було 0.0..1.0
            self._mutate(c_motion, lo=-1.0, hi=1.0)
            new_pop.append(Genome(individual_id=len(new_pop),
                                  construction=c_constr, motion=c_motion))

        self.generation_id += 1
        self.population = new_pop
        return self.population

    def best_fitness(self) -> float | None:
        return self.history[-1]["best"] if self.history else None

    # ── Оператори ────────────────────────────────────────────────────────
    def _tournament(self, scored, fit) -> Genome:
        contenders = self.rng.sample(scored, k=min(self.tournament_k, len(scored)))
        return max(contenders, key=lambda g: fit.get(g.individual_id, -1e9))

    def _crossover(self, p1: Genome, p2: Genome):
        if self.rng.random() > self.crossover_rate:
            return list(p1.construction), list(p1.motion)
        constr = [a if self.rng.random() < 0.5 else b
                  for a, b in zip(p1.construction, p2.construction)]
        motion = [a if self.rng.random() < 0.5 else b
                  for a, b in zip(p1.motion, p2.motion)]
        return constr, motion

    def current_sigma(self) -> float:
        """Сигма мутації за обраною стратегією (Т4/Т4а)."""
        s = self.mutation_strategy
        if s == "constant":
            return self.mutation_sigma
        if s == "annealing":
            return max(self.sigma_min,
                       self.mutation_sigma * (0.99 ** self.generation_id))
        if s == "p_control":
            if self.best_precision is None:
                return self.mutation_sigma
            return min(self.sigma_max,
                       max(self.sigma_min, self.kp * self.best_precision))
        raise ValueError(f"Невідома стратегія мутації: {s}")

    def _mutate(self, genes: list[float], lo: float, hi: float):
        sigma = self.current_sigma()
        for i in range(len(genes)):
            if self.rng.random() < self.mutation_rate:
                genes[i] = min(hi, max(lo, genes[i] + self.rng.gauss(0, sigma)))
