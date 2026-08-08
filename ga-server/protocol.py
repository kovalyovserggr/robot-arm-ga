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
    # Порядок і семантика фіксуються в описі експерименту (GENOME_SPEC.md).
    # УВАГА (v1.2): гени зберігаються нормованими в [-1, 1] — те саме,
    # що й motion. Раніше construction генерувались у [0,1], через що
    # Unity-декодер (очікує [-1,1]) міг видавати лише верхню половину
    # фізичного діапазону кожного параметра. Виправлено в обох рушіях.
    construction: list[float]
    motion: list[float]


class Generation(BaseModel):
    generation_id: int
    genomes: list[Genome]
    done: bool = False                      # критерій зупинки GA досягнуто
    best_fitness: float | None = None       # найкращий fitness / розмір фронту
    success_tolerance: float = 0.005        # curriculum: допуск монтажу, м


# ── Результати експерименту з боку Unity ────────────────────────────────────
class IndividualResult(BaseModel):
    individual_id: int
    fitness: float = 0.0                    # рахується на СЕРВЕРІ (логування)
    assembly_time: float = 0.0              # T: час монтажу, с
    energy: float = 0.0                     # E: механічна робота, Дж
    wear_cv: float = 0.0                    # W_cv: нерівномірність зносу
    wear_max: float = 0.0                   # W_max: піковий знос вузла, Дж
    joint_work: list[float] = []            # робота по кожному з 6 суглобів
    precision_error: float = 0.0            # похибка позиціонування, м
    collisions: int = 0                     # кількість колізій
    success: bool = False                   # чи завершено монтаж у допуску
    # ДІАГНОСТИЧНЕ (сесія 2026-08): реальний шлях деталі / пряма між
    # захватом і монтажем. НЕ використовується у критеріях/відборі —
    # спершу дивимось на розподіл і кореляцію з E, перш ніж вирішувати,
    # чи варта окремого критерію (bloat критеріїв, Р7). 1.0 = ідеально
    # пряма; > 1.0 = зайві рухи/тягання по підлозі. 0.0, якщо не
    # захоплено (немає що міряти).
    path_efficiency: float = 0.0

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
    # Стратегія керування сигмою мутації — ЛИШЕ для optimizer="weighted_sum"
    # (Т4/Т4а). NSGA-II використовує SBX + поліноміальну мутацію (Р7).
    mutation_strategy: str = "p_control"
    # Уставки curriculum-регулятора (тригер Шмітта, Т10):
    curriculum_gate_tighten: float = 0.25
    curriculum_gate_loosen: float = 0.02
    # Р7: вибір рушія оптимізації —
    #   "weighted_sum" — Stage 1 baseline (ga_engine.GAEngine)
    #   "nsga2"        — Stage 2, основний метод (nsga2_engine.NSGA2Engine)
    optimizer: str = "nsga2"
