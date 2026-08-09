"""
Спільна логіка декодування генів конструкції й засіву початкової
популяції — ЄДИНЕ джерело істини для GENE_SPLIT/LINK_MIN (v1.3,
заборонена зона) та засіву (GENOME_SPEC.md §4), щоб GAEngine і
NSGA2Engine не розходились. Дзеркало Unity GenomeSpec.cs
(UnpackLinkLength) — тримати синхронно.
"""
import random
from protocol import Genome

LINKS = 6
A_MAX, D_MAX = 0.35, 0.30
ALPHA_MIN, ALPHA_MAX = -90.0, 90.0

# v1.3: заборонена зона довжини ланки (див. GenomeSpec.cs коментар).
GENE_SPLIT = -0.5
LINK_MIN = 0.05


def unpack_link_length(g: float, l_max: float) -> float:
    g = max(-1.0, min(1.0, g))
    if g < GENE_SPLIT:
        return 0.0
    t = (g - GENE_SPLIT) / (1.0 - GENE_SPLIT)
    return LINK_MIN + t * (l_max - LINK_MIN)


def _gene_for_link_length(length: float, l_max: float) -> float:
    """Обернена до unpack_link_length: фізична довжина -> ген (лише
    для length > LINK_MIN — засів не сідає точно на межу розриву)."""
    t = (length - LINK_MIN) / (l_max - LINK_MIN)
    return GENE_SPLIT + t * (1.0 - GENE_SPLIT)


def _gene_for_angle(deg: float, lo: float, hi: float) -> float:
    return 2.0 * (deg - lo) / (hi - lo) - 1.0


def _clip(x: float) -> float:
    return max(-1.0, min(1.0, x))


def decode_material(construction: list[float]) -> float | None:
    """M = Σ(a_i + d_i). None — геном не в стандартному 18-генному
    DH-розкладі."""
    if len(construction) < 18:
        return None
    m = 0.0
    for i in range(LINKS):
        m += unpack_link_length(construction[i], A_MAX)
        m += unpack_link_length(construction[12 + i], D_MAX)
    return m


def make_seeded_individual(rng: random.Random, individual_id: int,
                           n_constr: int, n_motion: int) -> Genome:
    """Особина із завідомо досяжною конструкцією (GENOME_SPEC.md §4):
    короткі рівномірні ланки (a=0.20 м, alpha чергування 0/90°,
    d=0.08 м, з запасом від LINK_MIN) + мутаційний шум σ=0.15; рухи —
    випадкові. Гарантує, що частина покоління 0 фізично може
    дотягнутись, навіть коли заборонена зона (v1.3) звужує середню
    довжину випадкової руки — без цього при success=0% NSGA-II
    вироджується в одноцільовий пошук лише за точністю (жодних T/E/
    W_cv/M серед недопустимих) і популяція швидко кластеризується."""
    construction = [0.0] * n_constr
    if n_constr >= 18:
        a_g = _gene_for_link_length(0.20, A_MAX)
        d_g = _gene_for_link_length(0.08, D_MAX)
        for i in range(LINKS):
            alpha_deg = 0.0 if i % 2 == 0 else 90.0
            alpha_g = _gene_for_angle(alpha_deg, ALPHA_MIN, ALPHA_MAX)
            construction[i] = _clip(a_g + rng.gauss(0, 0.15))
            construction[6 + i] = _clip(alpha_g + rng.gauss(0, 0.15))
            construction[12 + i] = _clip(d_g + rng.gauss(0, 0.15))
        for i in range(18, n_constr):
            construction[i] = rng.uniform(-1.0, 1.0)
    else:
        construction = [rng.uniform(-1.0, 1.0) for _ in range(n_constr)]
    motion = [rng.uniform(-1.0, 1.0) for _ in range(n_motion)]
    return Genome(individual_id=individual_id, construction=construction, motion=motion)
