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
    ET.SubElement(mujoco, "option", timestep="0.02", gravity="0 0 -9.81")

    default = ET.SubElement(mujoco, "default")
    ET.SubElement(default, "joint", damping="0.1", frictionloss="0.0")
    ET.SubElement(default, "geom", type="capsule", size=str(LINK_RADIUS),
                 rgba="0.75 0.78 0.85 1")

    worldbody = ET.SubElement(mujoco, "worldbody")
    ET.SubElement(worldbody, "light", pos="0 0 2", diffuse="1 1 1")
    ET.SubElement(worldbody, "geom", name="floor", type="plane",
                 size="1.5 1.5 0.05", rgba="0.55 0.55 0.52 1")

    actuators_xml = []
    parent = worldbody
    for i, (a_i, alpha_i, d_i) in enumerate(dh):
        alpha_rad = math.radians(alpha_i)
        pos = (a_i, -d_i * math.sin(alpha_rad), d_i * math.cos(alpha_rad))
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
        # Візуальний сегмент ланки — капсула вздовж локального X довжиною a_i
        # (лише якщо a_i > 0, інакше сегмент "злитий", як і в Unity)
        if a_i > 1e-6:
            ET.SubElement(body, "geom", name=f"seg{i+1}",
                         fromto=f"0 0 0 {a_i:.6f} 0 0")
        actuators_xml.append(f"joint{i+1}")
        parent = body

    # Ефектор — сайт на кінці останньої ланки (+ToolLength уздовж x)
    ET.SubElement(parent, "site", name="effector",
                 pos=f"{TOOL_LENGTH:.6f} 0 0", size="0.01")

    actuator = ET.SubElement(mujoco, "actuator")
    for jname in actuators_xml:
        ET.SubElement(actuator, "position", name=f"act_{jname}", joint=jname,
                     kp="2000", ctrlrange=f"-{JOINT_LIMIT_DEG} {JOINT_LIMIT_DEG}")

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
