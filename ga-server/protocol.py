"""
Протокол обміну між GA-сервером (Python) та симуляційним клієнтом (Unity).

Цикл:
  1. Unity  -> POST /experiment/start   (конфігурація)
  2. Server -> покоління 0 (список геномів)
  3. Unity  проганяє експеримент: N площадок, роботи монтують деталь
  4. Unity  -> POST /experiment/results (fitness-метрики кожної особини)
  5. Server -> покоління N+1 (або done=true, якщо критерій зупинки)
  6. goto 3
"""
from pydantic import BaseModel, Field


# ── Геном особини ────────────────────────────────────────────────────────────
class Genome(BaseModel):
    individual_id: int
    # Гени конструкції: довжини ланок, параметри шарнірів тощо.
    # Порядок і семантика фіксуються в описі експерименту (стаття, дод. A).
    construction: list[float]
    # Гени рухів: параметри траєкторії / ключові кути по фазах монтажу.
    motion: list[float]


class Generation(BaseModel):
    generation_id: int
    genomes: list[Genome]
    done: bool = False                      # критерій зупинки GA досягнуто
    best_fitness: float | None = None       # найкращий fitness попер. покоління
    success_tolerance: float = 0.005        # curriculum: допуск монтажу, м


# ── Результати експерименту з боку Unity ────────────────────────────────────
class IndividualResult(BaseModel):
    individual_id: int
    fitness: float = 0.0                    # рахується на СЕРВЕРІ (див. main.py)
    # Сирі метрики з симуляції (GENOME_SPEC.md §5):
    assembly_time: float = 0.0              # T: час монтажу, с
    energy: float = 0.0                     # E: механічна робота, Дж
    wear_cv: float = 0.0                    # W_cv: нерівномірність зносу
    wear_max: float = 0.0                   # W_max: піковий знос вузла, Дж
    joint_work: list[float] = []            # робота по кожному з 6 суглобів
    precision_error: float = 0.0            # похибка позиціонування, м
    collisions: int = 0                     # кількість колізій
    success: bool = False                   # чи завершено монтаж у допуску

class GenerationResults(BaseModel):
    generation_id: int
    results: list[IndividualResult]


# ── Конфігурація експерименту ────────────────────────────────────────────────
class ExperimentConfig(BaseModel):
    population_size: int = Field(default=50, ge=2, le=500)
    construction_gene_count: int = 8
    motion_gene_count: int = 24
    max_generations: int = 100
    target_fitness: float | None = None     # рання зупинка, якщо досягнуто
    seed: int | None = None                 # відтворюваність для статті!
    # Стратегія керування сигмою мутації (експеримент Т4/Т4а):
    #   constant  — фіксована σ0 (baseline)
    #   annealing — детермінований відпал σ(g) = max(σ_min, σ0·0.99^g)
    #   p_control — P-контролер: σ ∝ похибці позиціонування найкращої особини
    mutation_strategy: str = "p_control"
    # Уставки curriculum-регулятора (тригер Шмітта, експеримент Т10):
    curriculum_gate_tighten: float = 0.25   # стискати допуск, якщо успіх >=
    curriculum_gate_loosen: float = 0.02    # відпускати, якщо успіх < (0 = вимкн.)
