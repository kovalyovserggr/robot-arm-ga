"""
mujoco_bridge.py — Рис.11 (МuJoCo крос-валідація), Крок 1: генератор
MJCF-моделі 6R-руки з генів конструкції + незалежна перевірка
кінематики (без самого MuJoCo — чиста матрична FK для звірки).

DH-ланцюжок (той самий, що ArmBuilder.cs/decode_material):
  зсув по x на a_i -> поворот навколо x на alpha_i -> зсув по z на d_i
  -> суглоб обертається навколо (нового) z на theta_i.

MuJoCo body задає ОДИН зсув (pos) + ОДИН поворот (euler), тому три
кроки (Tx(a)*Rx(alpha)*Tz(d)) звести до одного pos+euler:
  pos   = (a_i, -d_i*sin(alpha_i), d_i*cos(alpha_i))   [Tz(d) у
          повернутій Rx(alpha) системі -> проекція на y,z батька]
  euler = (alpha_i, 0, 0)
  joint (hinge, axis z) сидить у ЦІЙ ЖЕ body — його вісь z вже
  правильна (та, що постала після повороту alpha).
"""
import math
import xml.etree.ElementTree as ET

from genome_seed import LINKS, A_MAX, D_MAX, unpack_link_length, ALPHA_MIN, ALPHA_MAX

TOOL_LENGTH = 0.08     # м, ефектор уздовж x останньої ланки (GENOME_SPEC §3)
LINK_RADIUS = 0.025    # м, радіус капсули (GENOME_SPEC §3, LinkRadius)
JOINT_LIMIT_DEG = 150.0


def unpack_angle(g: float, lo: float, hi: float) -> float:
    """Дзеркало GenomeSpec.Unpack (без забороненої зони — застосовно
    для alpha_i і, окремо, для кутів фаз руху)."""
    g = max(-1.0, min(1.0, g))
    return lo + (g + 1.0) * 0.5 * (hi - lo)


def decode_dh_params(construction: list[float]) -> list[tuple[float, float, float]]:
    """construction[18] -> [(a_i, alpha_i_deg, d_i), ...] для 6 ланок.
    Дзеркало genome_seed.decode_material, але повертає ПОВНИЙ кортеж
    (a, alpha, d) на ланку, не лише суму M."""
    params = []
    for i in range(LINKS):
        a_i = unpack_link_length(construction[i], A_MAX)
        alpha_i = unpack_angle(construction[6 + i], ALPHA_MIN, ALPHA_MAX)
        d_i = unpack_link_length(construction[12 + i], D_MAX)
        params.append((a_i, alpha_i, d_i))
    return params


def build_mjcf(construction: list[float], model_name: str = "robot_arm") -> str:
    """Генерує MJCF (XML) 6R-руки з генів конструкції. Повертає рядок,
    готовий для mujoco.MjModel.from_xml_string()."""
    dh = decode_dh_params(construction)

    mujoco = ET.Element("mujoco", model=model_name)
    ET.SubElement(mujoco, "compiler", angle="degree")
    # FIX: implicitfast значно стабільніший за явний Euler (дефолт) для
    # жорстких position-актуаторів при нашому кроці 0.02с — явний
    # інтегратор із kp=2000 і низьким демпфуванням генерував NaN/Inf.
    ET.SubElement(mujoco, "option", timestep="0.02", gravity="0 0 -9.81",
                 integrator="implicitfast")

    default = ET.SubElement(mujoco, "default")
    ET.SubElement(default, "joint", damping="0.5", frictionloss="0.0")
    # FIX: рука НЕ повинна зіштовхуватись САМА З СОБОЮ. MuJoCo виключає
    # контакт лише для ПРЯМОЇ пари батько-нащадок — для злитих
    # (нульової довжини) ланок кілька "корпусів приводу" опиняються в
    # ОДНІЙ точці, і непрямі пари (через одне тіло й далі) все одно
    # зіштовхуються, даючи вибухові сили з першого кроку. Тому вся рука
    # (contype=2, conaffinity=1) не бачить сама себе (2&1=0), але й
    # надалі зіткнеться з підлогою/деталлю (contype=1, conaffinity=2
    # на них, встановлено нижче) — той самий принцип, що самоколізія
    # ArticulationBody-ланцюжка вимкнена в Unity за замовчуванням.
    ET.SubElement(default, "geom", type="capsule", size=str(LINK_RADIUS),
                 rgba="0.75 0.78 0.85 1", contype="2", conaffinity="1")

    worldbody = ET.SubElement(mujoco, "worldbody")
    ET.SubElement(worldbody, "light", pos="0 0 2", diffuse="1 1 1")
    ET.SubElement(worldbody, "geom", name="floor", type="plane",
                 size="1.5 1.5 0.05", rgba="0.55 0.55 0.52 1",
                 contype="1", conaffinity="2")

    actuators_xml = []
    parent = worldbody
    for i, (a_i, alpha_i, d_i) in enumerate(dh):
        alpha_rad = math.radians(alpha_i)
        pos = (a_i, -d_i * math.sin(alpha_rad), d_i * math.cos(alpha_rad))

        # FIX: попередня версія малювала капсулу ЛИШЕ для складової a_i
        # (вздовж локального x дочірнього тіла) — жодного сегмента для
        # d_i. Для геномів, де довжина сидить переважно в d_i (а не a_i),
        # це давало "розкидані кульки" без видимих з'єднань, хоча сама
        # кінематика (позиції суглобів) лишалась правильною (Крок 1
        # це підтвердив). Тепер малюю ОДИН стрижень на ПОВНИЙ вектор
        # зсуву (a_i І d_i разом) у БАТЬКІВСЬКОМУ тілі — фізично це один
        # реальний лінк між сусідніми суглобами, якою б не була
        # пропорція a_i/d_i в ньому.
        connector_len = math.sqrt(pos[0]**2 + pos[1]**2 + pos[2]**2)
        if connector_len > 1e-6:
            ET.SubElement(parent, "geom", name=f"link{i+1}_connector",
                         fromto=f"0 0 0 {pos[0]:.6f} {pos[1]:.6f} {pos[2]:.6f}")

        body = ET.SubElement(parent, "body", name=f"link{i+1}",
                             pos=f"{pos[0]:.6f} {pos[1]:.6f} {pos[2]:.6f}",
                             euler=f"{alpha_i:.6f} 0 0")
        ET.SubElement(body, "joint", name=f"joint{i+1}", type="hinge",
                     axis="0 0 1", pos="0 0 0",
                     range=f"-{JOINT_LIMIT_DEG} {JOINT_LIMIT_DEG}")
        # Корпус приводу — завжди присутній (навіть для злитих/нульових
        # ланок), гарантує ненульову масу тіла (вимога MuJoCo) і фізично
        # осмислений: реальний привід має масу незалежно від довжини
        # сусідньої ланки (той самий аргумент, що обґрунтовує заборонену
        # зону, v1.3).
        ET.SubElement(body, "geom", name=f"actuator_housing{i+1}", type="sphere",
                     size=str(LINK_RADIUS * 1.2), pos="0 0 0")
        actuators_xml.append(f"joint{i+1}")
        parent = body

    # Ефектор — сайт на кінці останньої ланки (+ToolLength уздовж x)
    ET.SubElement(parent, "site", name="effector",
                 pos=f"{TOOL_LENGTH:.6f} 0 0", size="0.01")

    actuator = ET.SubElement(mujoco, "actuator")
    for jname in actuators_xml:
        # kv (демпфування) обов'язкове для position-актуаторів такої
        # жорсткості (kp=2000) — без нього чистий "пружинний" привід
        # схильний до коливань/нестабільності. kv≈2·√kp — критичне
        # демпфування, стандартна евристика для PD-регуляторів.
        ET.SubElement(actuator, "position", name=f"act_{jname}", joint=jname,
                     kp="2000", kv="90", ctrlrange=f"-{JOINT_LIMIT_DEG} {JOINT_LIMIT_DEG}")

    return ET.tostring(mujoco, encoding="unicode")


# ── Незалежна перевірка: чиста матрична FK (без MuJoCo взагалі) ─────────

def _rot_x(deg: float):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [[1, 0, 0], [0, c, -s], [0, s, c]]


def _rot_z(deg: float):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def _mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _mat_vec(m, v):
    return [sum(m[i][k] * v[k] for k in range(3)) for i in range(3)]


def _vec_add(a, b):
    return [a[i] + b[i] for i in range(3)]


def forward_kinematics(construction: list[float], thetas_deg: list[float] | None = None) -> list[float]:
    """Незалежна (без MuJoCo) матрична FK за стандартною DH-схемою:
    T_i = Tx(a_i) * Rx(alpha_i) * Tz(d_i) * Rz(theta_i). Повертає
    позицію ефектора (з ToolLength) у світових координатах бази."""
    if thetas_deg is None:
        thetas_deg = [0.0] * LINKS
    dh = decode_dh_params(construction)

    R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]  # накопичена орієнтація
    p = [0.0, 0.0, 0.0]                     # накопичена позиція (world)

    for i, (a_i, alpha_i, d_i) in enumerate(dh):
        # Tx(a_i): зсув уздовж ПОТОЧНОЇ x-осі
        p = _vec_add(p, _mat_vec(R, [a_i, 0, 0]))
        # Rx(alpha_i): поворот орієнтації
        R = _mat_mul(R, _rot_x(alpha_i))
        # Tz(d_i): зсув уздовж НОВОЇ (повернутої) z-осі
        p = _vec_add(p, _mat_vec(R, [0, 0, d_i]))
        # Rz(theta_i): поворот суглоба
        R = _mat_mul(R, _rot_z(thetas_deg[i]))

    # Інструмент: зсув уздовж фінальної x-осі
    p = _vec_add(p, _mat_vec(R, [TOOL_LENGTH, 0, 0]))
    return p


# ── Крок 2: 4-фазний рух (дзеркало AssemblyPlatform.DrivePhases) ────────

PHASE_DURATIONS = [2.0, 2.5, 2.5, 2.0]  # с, ті самі, що GENOME_SPEC §3
N_PHASES = 4


def decode_motion_keyframes(motion: list[float]) -> list[list[float]]:
    """motion[24] -> [[θ1..θ6]_phase0, [θ1..θ6]_phase1, ...] у градусах.
    Дзеркало GenomeSpec.Unpack(-150,150) для кожного з 4×6 генів руху."""
    keyframes = []
    for phase in range(N_PHASES):
        thetas = [unpack_angle(motion[phase * LINKS + j], -JOINT_LIMIT_DEG, JOINT_LIMIT_DEG)
                  for j in range(LINKS)]
        keyframes.append(thetas)
    return keyframes


def target_thetas_at(motion: list[float], t: float) -> list[float]:
    """Кутові цілі всіх 6 суглобів у момент часу t (с) — лінійна
    інтерполяція між ключовими кадрами фаз, старт з нульової пози
    (θ_i(0)=0, GENOME_SPEC §3), той самий принцип, що DrivePhases()."""
    keyframes = decode_motion_keyframes(motion)
    prev = [0.0] * LINKS  # стартова поза
    t_acc = 0.0
    for phase in range(N_PHASES):
        dur = PHASE_DURATIONS[phase]
        target = keyframes[phase]
        if t <= t_acc + dur:
            frac = 0.0 if dur <= 0 else (t - t_acc) / dur
            frac = max(0.0, min(1.0, frac))
            return [prev[j] + frac * (target[j] - prev[j]) for j in range(LINKS)]
        prev = target
        t_acc += dur
    return prev  # по завершенні всіх фаз — тримати останню ціль


def run_motion(construction: list[float], motion: list[float],
              render: bool = False, settle_time: float = 3.0):
    """Прогонить повний цикл (4 фази + settle) через MuJoCo. Якщо
    render=True — відкриває інтерактивний переглядач (потребує
    дисплея; на сервері без екрана впаде — використовуй render=False
    для headless-тестів/автоматики).

    Повертає (t_log, effector_xyz_log, joint_angles_log) — для
    подальшого порівняння з Unity-метриками (Крок 3)."""
    import mujoco
    xml = build_mjcf(construction)
    m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)

    total_time = sum(PHASE_DURATIONS) + settle_time
    site_id = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "effector")

    t_log, eff_log, joints_log = [], [], []

    def step_and_log():
        t = d.time
        targets_deg = target_thetas_at(motion, min(t, sum(PHASE_DURATIONS)))
        # FIX: d.ctrl завжди в РАДІАНАХ на рівні рантайм-API, незалежно
        # від compiler angle="degree" (той стосується лише XML-парсингу).
        # Передача градусів напряму давала нереалістичні цілі (150 "рад"
        # замість 150°) -> чисельна нестабільність / зависання солвера.
        d.ctrl[:] = [math.radians(x) for x in targets_deg]
        mujoco.mj_step(m, d)
        t_log.append(d.time)
        eff_log.append(d.site_xpos[site_id].copy().tolist())
        joints_log.append(d.qpos.copy().tolist())

    if render:
        import mujoco.viewer
        with mujoco.viewer.launch_passive(m, d) as viewer:
            import time as _time
            start = _time.time()
            while d.time < total_time and viewer.is_running():
                step_and_log()
                # синхронізуємо реальний час із симуляційним для плавної анімації
                elapsed_wall = _time.time() - start
                if d.time > elapsed_wall:
                    _time.sleep(d.time - elapsed_wall)
                viewer.sync()
    else:
        while d.time < total_time:
            step_and_log()

    return t_log, eff_log, joints_log


if __name__ == "__main__":
    import argparse
    import json
    import pathlib

    ap = argparse.ArgumentParser(
        description="Крок 2: візуальний перегляд чемпіона в MuJoCo (аналог ChampionReplay)")
    ap.add_argument("--run-id", required=True, help="run_id з champion.json (напр. з логів)")
    ap.add_argument("--logs-dir", default="logs")
    ap.add_argument("--no-render", action="store_true",
                    help="Без вікна (headless) — лише порахувати й вивести підсумок")
    args = ap.parse_args()

    champ_path = pathlib.Path(args.logs_dir) / args.run_id / "champion.json"
    champ = json.loads(champ_path.read_text(encoding="utf-8"))
    genome = champ["genome"]

    print(f"Чемпіон {args.run_id}: покоління {champ.get('generation')}, "
         f"fitness={champ.get('fitness'):.4f}")
    print("Відкриваю MuJoCo-переглядач... (закрий вікно, щоб завершити)"
         if not args.no_render else "Headless-режим...")

    t_log, eff_log, joints_log = run_motion(
        genome["construction"], genome["motion"], render=not args.no_render)

    print(f"\nПрогін завершено: {len(t_log)} кроків, "
         f"фінальна позиція ефектора = {[round(x, 4) for x in eff_log[-1]]}")
