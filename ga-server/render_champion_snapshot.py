"""
render_champion_snapshot.py — Рис.9: чистий офлайн-скріншот чемпіона
(геометрія руки, повна поза після 4 фаз). Використовує ВЖЕ ДОВЕДЕНИЙ
mujoco_bridge.py (Кроки 1-2, перевірені на 53 геномах) — не малює
схему "з нуля", а рендерить справжню фізичну модель.

Потребує програмного рендерера (немає дисплея на сервері):
  MUJOCO_GL=osmesa python render_champion_snapshot.py --run-id ...
(Якщо є дисплей — MUJOCO_GL можна не задавати, спрацює звичний GPU-шлях)
"""
import argparse
import json
import pathlib

import mujoco
import mujoco_bridge as mb


def render_frame_array(construction: list[float], motion: list[float],
                       t: float, width: int = 640, height: int = 480):
    """Рендерить один кадр у момент t (с), повертає numpy-масив
    (H,W,3) — БЕЗ запису у файл. Спільна основа для одиночного і
    багатопанельного режимів."""
    xml = mb.build_mjcf(construction)
    m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)  # критично для t=0 (0 кроків циклу нижче)

    import math
    steps = int(t / m.opt.timestep)
    for _ in range(steps):
        targets_deg = mb.target_thetas_at(motion, min(d.time, sum(mb.PHASE_DURATIONS)))
        d.ctrl[:] = [math.radians(x) for x in targets_deg]
        mujoco.mj_step(m, d)

    # Камера "збоку-згори" — АВТО-центрування на фактичне положення
    # руки в цій позі (не фіксована точка простору), інакше при
    # зігнутих/віддалених позах рука виходить із кадру.
    body_xpos = d.xpos[1:]  # без worldbody (індекс 0)
    center = body_xpos.mean(axis=0)
    span = float((body_xpos.max(axis=0) - body_xpos.min(axis=0)).max())

    cam = mujoco.MjvCamera()
    mujoco.mjv_defaultFreeCamera(m, cam)
    cam.lookat = center.tolist()
    cam.distance = max(0.35, span * 1.8)
    cam.azimuth = 130
    cam.elevation = -20

    r = mujoco.Renderer(m, height=height, width=width)
    r.update_scene(d, camera=cam)
    return r.render()


def render_snapshot(construction: list[float], motion: list[float],
                    t: float, out_path: str,
                    width: int = 640, height: int = 480):
    """Один кадр -> файл (сумісність зі старим API)."""
    import PIL.Image
    img = render_frame_array(construction, motion, t, width, height)
    PIL.Image.fromarray(img).save(out_path)
    return out_path


def render_multi_panel(construction: list[float], motion: list[float],
                       times: list[float], out_path: str,
                       width: int = 640, height: int = 480,
                       gap: int = 16, label_h: int = 34):
    """Кілька моментів -> ОДИН комбінований рисунок (панелі поруч,
    підписані а)/б)/в)... з часом під кожною)."""
    import PIL.Image
    import PIL.ImageDraw
    import PIL.ImageFont
    import string

    frames = [render_frame_array(construction, motion, t, width, height) for t in times]
    n = len(frames)
    total_w = n * width + (n - 1) * gap
    total_h = height + label_h
    canvas = PIL.Image.new("RGB", (total_w, total_h), "white")
    draw = PIL.ImageDraw.Draw(canvas)
    font = PIL.ImageFont.load_default()

    labels = string.ascii_lowercase
    for i, (frame, t) in enumerate(zip(frames, times)):
        x0 = i * (width + gap)
        canvas.paste(PIL.Image.fromarray(frame), (x0, 0))
        text = f"{labels[i]}) t={t:g}s"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text((x0 + (width - tw) // 2, height + 8), text, fill="black", font=font)

    canvas.save(out_path)
    return out_path


def main():
    ap = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--logs-dir", default="logs")
    ap.add_argument("--t", type=float, nargs="+", default=[0.0],
        help="Один чи кілька моментів симуляції, с (0 = стартова поза). "
            "Кілька значень -> ОДИН комбінований рисунок з підписаними панелями.")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    champ_path = pathlib.Path(args.logs_dir) / args.run_id / "champion.json"
    champ = json.loads(champ_path.read_text(encoding="utf-8"))
    genome = champ["genome"]

    if len(args.t) == 1:
        out = render_snapshot(genome["construction"], genome["motion"], args.t[0], args.output)
    else:
        out = render_multi_panel(genome["construction"], genome["motion"], args.t, args.output)
    print(f"Збережено: {out}")


if __name__ == "__main__":
    main()
