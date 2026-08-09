"""
NSGA-II (Deb et al., 2002) з обмеженим домінуванням (constrained
domination) — Р7 Stage 2, основний метод статті. Той самий публічний
інтерфейс, що й GAEngine: init_population(), next_generation(results),
best_fitness(), history — main.py перемикає рушій прапорцем optimizer.

Критерії (мінімізуються), п'ять осей (Т9, Т14):
  T            — час монтажу
  E            — механічна енергія
  W_cv         — нерівномірність зносу (коефіцієнт варіації)
  W_max_over_M — піковий знос, нормований на матеріаломісткість
                 конструкції (розділяє "велика машина" і "погано
                 розподілене навантаження" — Т14)
  M            — матеріаломісткість, M = Σ(a_i + d_i) (Т9, вісь парсимонії)

Допустимість = прапорець success (монтаж у допуску й повільно, v1.1).
Обмежене домінування (Deb, 2000):
  допустима особина завжди домінує недопустиму;
  недопустима vs недопустима: менше порушення (precision_error) домінує;
  допустима vs допустима: звичайне домінування Парето по 5 критеріях.
Жодних ваг — у цьому весь сенс Stage 2 (Р7).
"""
import random
from protocol import Genome, IndividualResult
from genome_seed import decode_material, make_seeded_individual

M_FLOOR = 0.05   # м, захист від ділення на ~0 для виродженої руки
SEED_FRACTION = 0.10  # частка засіяної (гарантовано досяжної) популяції

OBJ_NAMES_FULL = ["T", "E", "W_cv", "W_max_over_M", "M"]
OBJ_NAMES_FALLBACK = ["T", "E", "W_cv", "W_max"]


class _Rec:
    """Одна оцінена особина: геном + вектор критеріїв + допустимість."""
    __slots__ = ("genome", "obj", "feasible", "violation", "rank", "crowd")
    def __init__(self, genome, obj, feasible, violation):
        self.genome = genome
        self.obj = obj              # list[float], МІНІМІЗУЄТЬСЯ
        self.feasible = feasible
        self.violation = violation  # має сенс лише якщо не feasible
        self.rank = None
        self.crowd = 0.0


def _dominates(p: "_Rec", q: "_Rec") -> bool:
    if p.feasible and not q.feasible:
        return True
    if not p.feasible and q.feasible:
        return False
    if not p.feasible and not q.feasible:
        return p.violation < q.violation
    le = all(a <= b for a, b in zip(p.obj, q.obj))
    lt = any(a < b for a, b in zip(p.obj, q.obj))
    return le and lt


def _fast_nondominated_sort(recs: list) -> list:
    fronts = [[]]
    dom_count = [0] * len(recs)
    dominated = [[] for _ in recs]
    for i, p in enumerate(recs):
        for j, q in enumerate(recs):
            if i == j:
                continue
            if _dominates(p, q):
                dominated[i].append(j)
            elif _dominates(q, p):
                dom_count[i] += 1
        if dom_count[i] == 0:
            p.rank = 0
            fronts[0].append(p)
    k = 0
    while fronts[k]:
        nxt = []
        for p in fronts[k]:
            i = recs.index(p)
            for j in dominated[i]:
                dom_count[j] -= 1
                if dom_count[j] == 0:
                    recs[j].rank = k + 1
                    nxt.append(recs[j])
        k += 1
        fronts.append(nxt)
    fronts.pop()
    return fronts


def _crowding_distance(front: list):
    n = len(front)
    if n == 0:
        return
    for r in front:
        r.crowd = 0.0
    if n <= 2:
        for r in front:
            r.crowd = float("inf")
        return
    n_obj = len(front[0].obj)
    for m in range(n_obj):
        front.sort(key=lambda r: r.obj[m])
        front[0].crowd = front[-1].crowd = float("inf")
        span = front[-1].obj[m] - front[0].obj[m]
        if span < 1e-12:
            continue
        for i in range(1, n - 1):
            front[i].crowd += (front[i + 1].obj[m] - front[i - 1].obj[m]) / span


def _crowded_better(a, b):
    if a.rank != b.rank:
        return a if a.rank < b.rank else b
    return a if a.crowd > b.crowd else b


class NSGA2Engine:
    """Той самий публічний інтерфейс, що й GAEngine; NSGA-II всередині."""

    def __init__(self, population_size: int, construction_genes: int,
                 motion_genes: int, seed: int | None = None,
                 mutation_strategy: str = "p_control"):
        self.pop_size = population_size
        self.n_constr = construction_genes
        self.n_motion = motion_genes
        self.rng = random.Random(seed)

        self.generation_id = 0
        self.population: list[Genome] = []
        self.history: list[dict] = []

        # SBX / поліноміальна мутація — стандартні дефолти NSGA-II (Deb 2002)
        self.eta_c = 15.0
        self.eta_m = 20.0
        self.crossover_rate = 0.9
        self.mutation_strategy = mutation_strategy  # лишено для сумісності логів

        # Mating restriction (мітигація дисбалансу feasible/infeasible):
        # при дуже малій допустимій частці випадковий бінарний турнір
        # майже ніколи не парує двох допустимих одне з одним — успішна
        # пара "конструкція+рухи" щоразу схрещується з чужою геометрією
        # і розпадається (той самий епістатичний лок-ін, Т9, посилений
        # арифметикою турніру). Ймовірність підмінити випадковий вибір
        # батька на турнір ЛИШЕ серед допустимих, коли такі є.
        self.feasible_mating_bias = 0.75

        self.last_eval: dict = {}     # individual_id -> objective record
        self.front_ids: set = set()   # individual_id на rank-0
        self._warned_no_material = False

    def _bounds(self, kind: str):
        return (-1.0, 1.0)  # construction і motion — однаковий діапазон (v1.2 fix)

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

    def _evaluate(self, results: list) -> list:
        res_by_id = {r.individual_id: r for r in results}
        recs = []
        for g in self.population:
            r = res_by_id.get(g.individual_id)
            if r is None:
                continue
            m = decode_material(g.construction)
            if m is None:
                if not self._warned_no_material:
                    print(f"[NSGA2Engine] WARNING: construction_gene_count="
                          f"{self.n_constr} != 18 — M/W_max_over_M вимкнено, "
                          f"працюємо на T,E,W_cv,W_max.")
                    self._warned_no_material = True
                obj = [r.assembly_time, r.energy, r.wear_cv, r.wear_max]
            else:
                w_over_m = r.wear_max / max(m, M_FLOOR)
                obj = [r.assembly_time, r.energy, r.wear_cv, w_over_m, m]
            recs.append(_Rec(g, obj, feasible=r.success,
                             violation=0.0 if r.success else max(r.precision_error, 1e-6)))
        return recs

    def next_generation(self, results: list) -> list[Genome]:
        recs = self._evaluate(results)
        fronts = _fast_nondominated_sort(recs)
        for fr in fronts:
            _crowding_distance(fr)

        names = OBJ_NAMES_FULL if (recs and len(recs[0].obj) == 5) else OBJ_NAMES_FALLBACK
        self.front_ids = {r.genome.individual_id for r in fronts[0]} if fronts else set()
        self.last_eval = {
            r.genome.individual_id: {
                "objectives": dict(zip(names, r.obj)),
                "feasible": r.feasible, "rank": r.rank,
                # inf на межах фронту -> JSON-безпечний сентінел
                "crowding": (1e9 if r.crowd == float("inf") else r.crowd),
            } for r in recs
        }
        self.history.append({
            "generation": self.generation_id,
            "front_size": len(fronts[0]) if fronts else 0,
            "n_feasible": sum(r.feasible for r in recs),
            "n_fronts": len(fronts),
        })

        # (μ+λ)-елітизм між викликами: батьки цього виклику вже є
        # попереднім нащадковим поколінням (протокол — запит/відповідь,
        # R1), тож "λ" природно втілене без окремого буфера.
        recs.sort(key=lambda r: (r.rank, -r.crowd))
        elite = recs[: self.pop_size] if len(recs) >= self.pop_size else recs

        # Елітизм: весь rank-0 фронт переходить незмінним (не лише 2!),
        # з обмеженням, щоб один фронт не з'їв усю популяцію і не
        # вбив різноманіття пізніше, коли допустимих стане багато.
        front0_size = len(fronts[0]) if fronts else 0
        n_elite_carry = min(max(2, front0_size),
                            max(2, self.pop_size // 10), len(elite))

        new_pop: list[Genome] = []
        for r in elite[:n_elite_carry]:
            new_pop.append(r.genome.model_copy(update={"individual_id": len(new_pop)}))

        feasible_pool = [r for r in elite if r.feasible]

        def pick_parent():
            if feasible_pool and self.rng.random() < self.feasible_mating_bias:
                return self._tournament(feasible_pool)
            return self._tournament(elite)

        while len(new_pop) < self.pop_size:
            p1 = pick_parent()
            p2 = pick_parent()
            c_constr, c_motion = self._sbx(p1.genome, p2.genome)
            self._poly_mutate(c_constr, *self._bounds("construction"))
            self._poly_mutate(c_motion, *self._bounds("motion"))
            new_pop.append(Genome(individual_id=len(new_pop),
                                  construction=c_constr, motion=c_motion))

        self.generation_id += 1
        self.population = new_pop
        return self.population

    def best_fitness(self) -> float | None:
        """Для сумісності інтерфейсу (early-stop cfg.target_fitness) —
        розмір допустимого rank-0 фронту як проксі прогресу (єдиного
        скаляра при Парето-оптимізації не існує за визначенням)."""
        return float(self.history[-1]["front_size"]) if self.history else None

    def _tournament(self, pool: list):
        if len(pool) < 2:
            return pool[0]
        a, b = self.rng.sample(pool, 2)
        return _crowded_better(a, b)

    def _sbx(self, p1: Genome, p2: Genome):
        def cross(x1, x2, lo, hi):
            c1 = list(x1)
            if self.rng.random() > self.crossover_rate:
                return c1
            for i in range(len(x1)):
                if self.rng.random() > 0.5:
                    continue
                a, b = x1[i], x2[i]
                if abs(a - b) < 1e-12:
                    continue
                u = self.rng.random()
                beta = ((2 * u) ** (1 / (self.eta_c + 1)) if u <= 0.5
                        else (1 / (2 * (1 - u))) ** (1 / (self.eta_c + 1)))
                lo_v, hi_v = min(a, b), max(a, b)
                child = 0.5 * ((1 + beta) * lo_v + (1 - beta) * hi_v)
                c1[i] = min(hi, max(lo, child))
            return c1
        clo, chi = self._bounds("construction")
        mlo, mhi = self._bounds("motion")
        return (cross(p1.construction, p2.construction, clo, chi),
                cross(p1.motion, p2.motion, mlo, mhi))

    def _poly_mutate(self, genes: list, lo: float, hi: float):
        pm = 1.0 / max(len(genes), 1)
        for i in range(len(genes)):
            if self.rng.random() > pm:
                continue
            x = genes[i]
            d1 = (x - lo) / (hi - lo)
            d2 = (hi - x) / (hi - lo)
            u = self.rng.random()
            mp = 1.0 / (self.eta_m + 1)
            if u < 0.5:
                xy = 1 - d1
                val = 2 * u + (1 - 2 * u) * (xy ** (self.eta_m + 1))
                dq = val ** mp - 1
            else:
                xy = 1 - d2
                val = 2 * (1 - u) + 2 * (u - 0.5) * (xy ** (self.eta_m + 1))
                dq = 1 - val ** mp
            genes[i] = min(hi, max(lo, x + dq * (hi - lo)))
