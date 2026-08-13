"""
GA-ядро (Р7, Stage 1 — baseline зі зваженою згорткою). Турнірна
селекція, рівномірний кросовер, гаусова мутація з керованою сигмою.
Сюди підключається твій реальний GA з дисертації за потреби:
достатньо зберегти сигнатури init_population() та next_generation().
"""
import math
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
        self.mutation_sigma = 0.15        # σ0 (constant / старт annealing / self_adaptive)
        self.elitism = 2

        # ── Керування сигмою (Т4/Т4а) ──────────────────────────────────
        self.mutation_strategy = mutation_strategy
        self.sigma_min, self.sigma_max = 0.02, 0.15
        self.kp = 0.15                    # P-контролер: σ = Kp · prec_best
        self.best_precision = None        # сурогат відстані до оптимуму

        # Т4: self_adaptive — σ їде РАЗОМ з кожною особиною (не глобальне
        # число), успадковується від батьків і самомутується за
        # лог-нормальним правилом класичних Evolution Strategies
        # (Rechenberg/Schwefel): σ' = σ·exp(τ·N(0,1)). τ = 1/√(2n) —
        # канонічний темп самоадаптації для n-вимірного генома.
        self.tau = 1.0 / math.sqrt(2 * (construction_genes + motion_genes))
        self.sigmas: dict[int, float] = {}  # individual_id -> власна σ


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
        self.sigmas = {g.individual_id: self.mutation_sigma for g in pop}
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
        # Для логування: self_adaptive не має ОДНОГО глобального числа —
        # логуємо середню σ популяції (діагностичний орієнтир для Рис.6).
        sigma_for_log = (sum(self.sigmas.values()) / len(self.sigmas)
                         if self.mutation_strategy == "self_adaptive" and self.sigmas
                         else self.current_sigma())
        self.history.append({"generation": self.generation_id,
                             "best": best, "mean": mean, "sigma": sigma_for_log})

        new_pop: list[Genome] = []
        new_sigmas: dict[int, float] = {}
        for g in scored[:self.elitism]:
            new_id = len(new_pop)
            new_pop.append(g.model_copy(update={"individual_id": new_id}))
            # Еліта переходить БЕЗ мутації — і без самомутації σ, за тим
            # самим принципом (нащадок мутує, батько-еліта — ні).
            new_sigmas[new_id] = self.sigmas.get(g.individual_id, self.mutation_sigma)

        while len(new_pop) < self.pop_size:
            p1 = self._tournament(scored, fit)
            p2 = self._tournament(scored, fit)
            c_constr, c_motion = self._crossover(p1, p2)

            if self.mutation_strategy == "self_adaptive":
                parent_sigma = (self.sigmas.get(p1.individual_id, self.mutation_sigma) +
                                self.sigmas.get(p2.individual_id, self.mutation_sigma)) / 2
                child_sigma = min(self.sigma_max, max(self.sigma_min,
                                  parent_sigma * math.exp(self.tau * self.rng.gauss(0, 1))))
            else:
                child_sigma = self.current_sigma()

            self._mutate(c_constr, lo=-1.0, hi=1.0, sigma=child_sigma)
            self._mutate(c_motion, lo=-1.0, hi=1.0, sigma=child_sigma)
            new_id = len(new_pop)
            new_pop.append(Genome(individual_id=new_id,
                                  construction=c_constr, motion=c_motion))
            new_sigmas[new_id] = child_sigma

        self.generation_id += 1
        self.population = new_pop
        self.sigmas = new_sigmas
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
        """Сигма мутації за обраною стратегією (Т4/Т4а). Для
        self_adaptive повертає СЕРЕДНЮ по популяції (лише для
        діагностики/логування — реальна мутація використовує σ
        КОЖНОЇ особини окремо, див. next_generation)."""
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
        if s == "self_adaptive":
            return (sum(self.sigmas.values()) / len(self.sigmas)
                   if self.sigmas else self.mutation_sigma)
        raise ValueError(f"Невідома стратегія мутації: {s}")

    def _mutate(self, genes: list[float], lo: float, hi: float, sigma: float):
        for i in range(len(genes)):
            if self.rng.random() < self.mutation_rate:
                genes[i] = min(hi, max(lo, genes[i] + self.rng.gauss(0, sigma)))
