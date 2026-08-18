"""
mujoco_assembly.py — Рис.11, Крок 3: повний цикл захват+встановлення+
метрики в MuJoCo, дзеркало AssemblyPlatform.cs/GenomeSpec.cs рядок у
рядок. CLI: даєш run_id(и) -> сам дістає champion.json, жене через
MuJoCo, друкує Unity vs MuJoCo поруч.

ПРИПУЩЕННЯ (не підтверджено ArmBuilder.cs, якого не було в чаті):
Unity PartPickupPos/MountPos задані в Y-up конвенції; MuJoCo-модель
тут Z-up (gravity "0 0 -9.81"). Застосовую перетворення (x,y,z)_Unity
-> (x,z,y)_MuJoCo. Якщо після --render рука візуально НЕ дотягується
до цілей — це перше місце для перевірки.

Спрощення (задокументовано, не б'є по T/E/W_cv/precision/success —
лише по діагностичному path_efficiency): деталь — MuJoCo mocap-тіло
(кінематичне). Під час "захвату" її позиція КІНЕМАТИЧНО прив'язується
до ефектора (жорсткий зсув, обчислений у момент захвату) — це
еквівалент ідеально жорсткого FixedJoint без люфту. Unity після
success руйнує FixedJoint і деталь падає вільно (це продовжує
накопичувати path_efficiency) — тут після success деталь просто
"замирає" на місці (mocap не може вільно падати). Основні валідовані
метрики цього не торкається.
"""
import argparse
import json
import math
import pathlib

import mujoco_bridge as mb

# ── Константи середовища (дзеркало GenomeSpec.cs) ────────────────────────
PART_PICKUP_POS_UNITY = (-0.45, 0.20, 0.0)
MOUNT_POS_UNITY = (0.50, 0.25, 0.10)
PART_MASS = 0.15
DRIVE_STIFFNESS = 2000.0
DRIVE_DAMPING = 100.0
DRIVE_FORCE_LIMIT = 300.0
GRASP_REL_SPEED_LIMIT = 0.5      # м/с
MOUNT_INSTALL_OFFSET_UNITY = (0.0, 0.04, 0.0)   # Vector3.up*0.04
PLATFORM_TIME_LIMIT = 30.0
SETTLE_AFTER_CYCLE = 3.0
PART_HALF_SIZE = 0.02             # м (Unity: scale 0.04 -> півдовжина 0.02)


def _unity_to_mujoco(v):
    """(x,y,z)_Unity[Y-up] -> (x,z,y)_MuJoCo[Z-up]. Див. застереження
    у docstring модуля — перевір --render, якщо сумніваєшся."""
    return (v[0], v[2], v[1])


PART_PICKUP_POS = _unity_to_mujoco(PART_PICKUP_POS_UNITY)
MOUNT_POS = _unity_to_mujoco(MOUNT_POS_UNITY)
MOUNT_INSTALL_OFFSET = _unity_to_mujoco(MOUNT_INSTALL_OFFSET_UNITY)
MOUNT_TARGET = tuple(MOUNT_POS[i] + MOUNT_INSTALL_OFFSET[i] for i in range(3))


def build_mjcf_with_part(construction: list[float]) -> str:
    """Розширює build_mjcf() деталлю (mocap) + декоративними
    підставками (PartStand/Mount, дзеркало Unity MakeStatic — лише
    для візуальної звірки з ChampionReplay, на фізику НЕ впливають,
    contype=0/conaffinity=0)."""
    import xml.etree.ElementTree as ET
    xml_str = mb.build_mjcf(construction)
    root = ET.fromstring(xml_str)
    worldbody = root.find("worldbody")

    stand_pos = tuple(PART_PICKUP_POS[i] - (0, 0, 0.115)[i] for i in range(3))
    ET.SubElement(worldbody, "geom", name="part_stand", type="box",
                 size="0.04 0.04 0.085", pos=f"{stand_pos[0]:.6f} {stand_pos[1]:.6f} {stand_pos[2]:.6f}",
                 rgba="0.6 0.55 0.4 1", contype="0", conaffinity="0")
    mount_platform_pos = tuple(MOUNT_POS[i] - (0, 0, 0.02)[i] for i in range(3))
    ET.SubElement(worldbody, "geom", name="mount_platform", type="box",
                 size="0.05 0.05 0.02", pos=f"{mount_platform_pos[0]:.6f} {mount_platform_pos[1]:.6f} {mount_platform_pos[2]:.6f}",
                 rgba="0.3 0.5 0.75 1", contype="0", conaffinity="0")

    part = ET.SubElement(worldbody, "body", name="part", mocap="true",
                         pos=f"{PART_PICKUP_POS[0]:.6f} {PART_PICKUP_POS[1]:.6f} {PART_PICKUP_POS[2]:.6f}")
    ET.SubElement(part, "geom", name="part_geom", type="box",
                 size=f"{PART_HALF_SIZE} {PART_HALF_SIZE} {PART_HALF_SIZE}",
                 rgba="0.85 0.25 0.2 1", contype="0", conaffinity="0")

    ET.SubElement(worldbody, "site", name="mount_marker",
                 pos=f"{MOUNT_TARGET[0]:.6f} {MOUNT_TARGET[1]:.6f} {MOUNT_TARGET[2]:.6f}",
                 size="0.012", rgba="0.2 0.8 0.3 0.6")

    return ET.tostring(root, encoding="unicode")


def _dist(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def run_assembly(genome: dict, tolerance: float, render: bool = False) -> dict:
    """Повний цикл: фази руху + захват + встановлення + метрики.
    Дзеркало AssemblyPlatform.FixedUpdate()/Finish() формула за
    формулою. tolerance — ДІЮЧИЙ допуск чемпіона (champion.json
    "tolerance", коректний після фіксу off-by-one)."""
    import mujoco
    import numpy as np

    construction, motion = genome["construction"], genome["motion"]
    grasp_radius = min(0.080, max(0.010, 2.0 * tolerance))

    xml = build_mjcf_with_part(construction)
    m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)

    site_id = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "effector")
    part_mocap_id = m.body("part").mocapid[0]

    cycle = sum(mb.PHASE_DURATIONS)
    total_time = cycle + SETTLE_AFTER_CYCLE

    joint_work = [0.0] * mb.LINKS
    prev_joint_pos = [0.0] * mb.LINKS
    grasped = False
    success = False
    best_precision = float("inf")
    best_approach = float("inf")
    grasp_offset = None
    grasp_pos = None
    part_prev_pos = None
    path_length = 0.0
    t_success = None
    best_approach_t = None
    best_approach_speed = None

    prev_eff_pos = None

    def phase_index(t):
        acc = 0.0
        for i, dur in enumerate(mb.PHASE_DURATIONS):
            acc += dur
            if t <= acc:
                return i
        return len(mb.PHASE_DURATIONS) - 1

    def step_once():
        nonlocal grasped, success, best_precision, best_approach
        nonlocal grasp_offset, grasp_pos, part_prev_pos, path_length, t_success, prev_eff_pos
        nonlocal best_approach_t, best_approach_speed

        t = d.time
        # ── DrivePhases ──
        targets_deg = mb.target_thetas_at(motion, min(t, cycle))
        d.ctrl[:] = [math.radians(x) for x in targets_deg]

        # ── MeasureEnergy (ПЕРЕД mj_step — τ рахуємо з ПОТОЧНОГО стану,
        #    так само як Unity читає ab.xDrive/jointPosition до кроку
        #    фізики цього кадру) ──
        for i in range(mb.LINKS):
            pos = d.qpos[i]
            vel = d.qvel[i]
            target_rad = math.radians(targets_deg[i])
            tau = DRIVE_STIFFNESS * (target_rad - pos) - DRIVE_DAMPING * vel
            tau = max(-DRIVE_FORCE_LIMIT, min(DRIVE_FORCE_LIMIT, tau))
            joint_work[i] += abs(tau * (pos - prev_joint_pos[i]))
            prev_joint_pos[i] = pos

        mujoco.mj_step(m, d)

        eff_pos = tuple(d.site_xpos[site_id])
        part_pos = tuple(d.mocap_pos[part_mocap_id]) if grasped else PART_PICKUP_POS

        # ── TryGrasp ──
        if not grasped:
            dist = _dist(eff_pos, part_pos)
            eff_vel = (0.0, 0.0, 0.0) if prev_eff_pos is None else tuple(
                (eff_pos[i] - prev_eff_pos[i]) / m.opt.timestep for i in range(3))
            rel_speed = math.sqrt(sum(v * v for v in eff_vel))
            if dist < best_approach:
                best_approach = dist
                best_approach_t = t
                best_approach_speed = rel_speed
            if dist <= grasp_radius:
                if rel_speed <= GRASP_REL_SPEED_LIMIT:
                    grasped = True
                    grasp_offset = tuple(part_pos[i] - eff_pos[i] for i in range(3))
                    grasp_pos = part_pos
                    part_prev_pos = part_pos
                    path_length = 0.0

        # ── Кінематичне тримання (спрощення, див. docstring) ──
        if grasped and not success:
            new_part_pos = tuple(eff_pos[i] + grasp_offset[i] for i in range(3))
            d.mocap_pos[part_mocap_id] = new_part_pos
            part_pos = new_part_pos
            # TrackPath
            path_length += _dist(part_pos, part_prev_pos)
            part_prev_pos = part_pos

        # ── TryInstall ──
        if grasped and not success:
            err = _dist(part_pos, MOUNT_TARGET)
            best_precision = min(best_precision, err)
            if phase_index(t) >= 3 and err <= tolerance:
                success = True
                t_success = t

        prev_eff_pos = eff_pos

    if render:
        import mujoco.viewer
        import time as _time
        with mujoco.viewer.launch_passive(m, d) as viewer:
            start = _time.time()
            while d.time < total_time and viewer.is_running() and not success:
                step_once()
                elapsed = _time.time() - start
                if d.time > elapsed:
                    _time.sleep(d.time - elapsed)
                viewer.sync()
            # settle: дати добігти, якщо ще не встигло після success
            while d.time < total_time and viewer.is_running():
                step_once()
                elapsed = _time.time() - start
                if d.time > elapsed:
                    _time.sleep(d.time - elapsed)
                viewer.sync()
    else:
        while d.time < total_time and not success:
            step_once()
        while d.time < total_time:
            step_once()

    # ── Finish (дзеркало AssemblyPlatform.Finish) ──
    mean_w = sum(joint_work) / mb.LINKS
    max_w = max(joint_work)
    sd_w = math.sqrt(sum((w - mean_w) ** 2 for w in joint_work) / mb.LINKS)

    if grasped:
        prec = 1.0 if best_precision == float("inf") else best_precision
    else:
        approach = 0.0 if best_approach == float("inf") else best_approach
        prec = 1.0 + approach
    if not math.isfinite(prec) or prec > 10.0:
        prec = 10.0

    path_eff = 0.0
    if grasped:
        final_part_pos = tuple(d.mocap_pos[part_mocap_id])
        straight = _dist(grasp_pos, final_part_pos)
        path_eff = path_length / max(straight, 0.01)
        if not math.isfinite(path_eff):
            path_eff = 0.0

    return {
        "assembly_time": t_success if success else PLATFORM_TIME_LIMIT,
        "energy": sum(joint_work),
        "wear_cv": (sd_w / mean_w) if mean_w > 1e-6 else 10.0,
        "wear_max": max_w,
        "precision_error": prec,
        "success": success,
        "path_efficiency": path_eff,
        "_diag_best_approach_t": best_approach_t,
        "_diag_best_approach_speed": best_approach_speed,
        "_diag_grasp_radius": grasp_radius,
        "_diag_ever_grasped": grasped,
    }


def compare_one(run_id: str, logs_dir: pathlib.Path, render: bool = False) -> dict:
    champ_path = logs_dir / run_id / "champion.json"
    champ = json.loads(champ_path.read_text(encoding="utf-8"))
    unity = champ["metrics"]
    tolerance = champ.get("tolerance", 0.05)

    mujoco_result = run_assembly(champ["genome"], tolerance, render=render)

    return {"run_id": run_id, "unity": unity, "mujoco": mujoco_result}


def print_comparison(results: list[dict]):
    fields = [("success", "{}"), ("assembly_time", "{:.2f}"), ("energy", "{:.1f}"),
              ("wear_cv", "{:.3f}"), ("wear_max", "{:.1f}"),
              ("precision_error", "{:.4f}"), ("path_efficiency", "{:.2f}")]
    for r in results:
        print(f"\n=== {r['run_id']} ===")
        print(f"{'метрика':<18}{'Unity':<15}{'MuJoCo':<15}")
        for key, fmt in fields:
            u = r["unity"].get(key)
            j = r["mujoco"].get(key)
            u_s = fmt.format(u) if u is not None else "?"
            j_s = fmt.format(j) if j is not None else "?"
            print(f"{key:<18}{u_s:<15}{j_s:<15}")
        mj = r["mujoco"]
        if not mj.get("success") and not mj.get("_diag_ever_grasped"):
            print(f"  [діагностика] найкраще наближення на t={mj['_diag_best_approach_t']:.2f}с, "
                 f"швидкість тоді={mj['_diag_best_approach_speed']:.3f} м/с "
                 f"(поріг захвату={mj['_diag_grasp_radius']*1000:.1f}мм, "
                 f"допуск швидкості={GRASP_REL_SPEED_LIMIT}м/с)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", nargs="+", required=True,
        help="Один чи кілька run_id — сам дістане champion.json і порівняє")
    ap.add_argument("--logs-dir", default="logs")
    ap.add_argument("--render", action="store_true",
        help="Показати MuJoCo-переглядач для ПЕРШОГО run_id (перевірка reachability)")
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    logs_dir = pathlib.Path(args.logs_dir)
    results = []
    for i, run_id in enumerate(args.run_id):
        print(f"Прогін {run_id}...")
        results.append(compare_one(run_id, logs_dir, render=(args.render and i == 0)))

    print_comparison(results)

    if args.output:
        out = pathlib.Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nЗбережено: {out}")


if __name__ == "__main__":
    main()
