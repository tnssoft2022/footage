"""Text overlay (transparent) + grade filter from timeline.json.

Run:  <venv>/bin/python make_effect.py <ffmpeg-path> [timeline.json]
Out:  effect/overlay.mov (qtrle argb, alpha)  +  effect/grade.txt (one-line filter chain)
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from fontTools.ttLib import TTCollection

FFMPEG = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
TL = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "timeline.json")
OUTDIR = os.path.join(HERE, "effect")
OVERLAY = os.path.join(OUTDIR, "overlay.mov")
GRADE = os.path.join(OUTDIR, "grade.txt")

THAI_TTC = "/System/Library/Fonts/Supplemental/SukhumvitSet.ttc"
DIDOT_TTC = "/System/Library/Fonts/Supplemental/Didot.ttc"
FONT_FACES = {  # font key in timeline -> (ttc, subfont name)
  "th-regular": (THAI_TTC, "Sukhumvit Set Text"),
  "th-bold": (THAI_TTC, "Sukhumvit Set Bold"),
  "en-title": (DIDOT_TTC, "Didot"),
}

# safe area inside the video frame overlay (x 15-85 %, y 18-78 %)
SAFE = (288, 194, 1632, 842)
SIZE = {"code": 36, "title": 64, "sub": 46, "price": 60, "contact": 40}
ASC, DESC = 1.08, 0.46   # line spacing factors (Thai upper marks / lower marks)
FADE = 0.5         # per-line fade in/out
STAGGER = 0.22     # delay between lines
SLIDE = 12         # px rise while fading in
PAD = 44           # inner padding of the lower-third block


def run(cmd):
  r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
  if r.returncode:
    sys.stderr.write("\n".join(l for l in r.stderr.splitlines() if "drawtext=" not in l)[-3000:])
    raise SystemExit(r.returncode)


def hexrgb(c):
  c = c.lstrip("#")
  return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def extract_fonts(tmp):
  """Split needed faces out of .ttc (drawtext cannot pick a face inside a collection)."""
  out, cache, metrics = {}, {}, {}
  for key, (ttc, name) in FONT_FACES.items():
    if ttc not in cache:
      cache[ttc] = TTCollection(ttc)
    for f in cache[ttc].fonts:
      if f["name"].getDebugName(4) == name:
        path = os.path.join(tmp, key + ".ttf")
        f.save(path)
        out[key] = path
        metrics[key] = (f.getBestCmap(), f["hmtx"].metrics, f["head"].unitsPerEm)
        break
    else:
      raise SystemExit(f"font face not found: {name}")
  return out, metrics


def text_width(metrics, key, text, size):
  cmap, hmtx, upm = metrics[key]
  adv = 0
  for ch in text:
    g = cmap.get(ord(ch))
    if g:
      adv += hmtx[g][0]
  return adv * size / upm


def save_png(rgba, path, tmp):
  raw = os.path.join(tmp, "buf.rgba")
  rgba.astype(np.uint8).tofile(raw)
  h, w = rgba.shape[:2]
  run([FFMPEG, "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-i", raw,
       "-frames:v", "1", path])


def soft_rect(w, h, x0, y0, x1, y1, feather):
  """0..1 mask: 1 inside the box, smooth falloff of `feather` px toward its edges."""
  yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
  fx = np.clip(np.minimum(xx - x0, x1 - xx) / feather, 0, 1)
  fy = np.clip(np.minimum(yy - y0, y1 - yy) / feather, 0, 1)
  s = lambda v: v * v * (3 - 2 * v)
  return s(fx) * s(fy)


def layout(tset, metrics, W, H):
  """Return per-line (x_expr, baseline_y, size, fontkey) + bar/accent geometry."""
  lines = tset["lines"]
  sizes = [SIZE.get(l["role"], 44) for l in lines]
  widths = [text_width(metrics, l["font"], l["text"], s) for l, s in zip(lines, sizes)]
  gaps = []
  for i, (l, s) in enumerate(zip(lines, sizes)):
    nxt = sizes[i + 1] if i + 1 < len(sizes) else s
    g = s * DESC + nxt * ASC   # baseline-to-baseline: this line's descent + next line's ascent
    if l.get("rule_after"):
      g += 40
    gaps.append(g)
  sx0, sy0, sx1, sy1 = SAFE
  out = []
  if tset["anchor"] == "center":
    block_h = sum(gaps[:-1]) + sizes[0] * 0.8 + sizes[-1] * 0.35
    top = (sy0 + sy1) / 2 - block_h / 2
    base = top + sizes[0] * 0.8
    rules = []
    for i, (l, s) in enumerate(zip(lines, sizes)):
      out.append(("(w-text_w)/2", base, s, l["font"]))
      if l.get("rule_after"):
        ry = base + s * 0.35 + (gaps[i] - s * 0.35 - sizes[i + 1] * 0.8) / 2
        rules.append((W / 2 - 170, ry, W / 2 + 170))
      base += gaps[i]
    pw = max(widths) + 2 * 110
    box = (W / 2 - pw / 2, top - 60, W / 2 + pw / 2, top + block_h + 60)
    return out, box, rules, None, widths
  # bottom-left lower third
  block_h = sum(gaps[:-1]) + sizes[0] * 0.8 + sizes[-1] * 0.3
  bottom = sy1 - PAD
  top = bottom - block_h
  base = top + sizes[0] * 0.8
  tx = sx0 + PAD + 22
  for i, (l, s) in enumerate(zip(lines, sizes)):
    out.append((f"{tx:.0f}", base, s, l["font"]))
    base += gaps[i]
  accent = (sx0 + PAD - 2, top - 4, bottom + 4)   # gold vertical line x, y0, y1
  box = (sx0, top - PAD, min(sx1, tx + max(widths) + 220), sy1)
  return out, box, [], accent, widths


def bar_png(tset, geo, style, W, H, path, tmp):
  pos, box, rules, accent, _ = geo
  img = np.zeros((H, W, 4), np.float32)
  bx0, by0, bx1, by1 = box
  if tset["anchor"] == "center":
    m = soft_rect(W, H, bx0, by0, bx1, by1, 70) * 0.50
  else:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    # dark on the left, fading to nothing on the right; all edges feathered inside the box
    sm = lambda v: v * v * (3 - 2 * v)
    hx = np.clip(1 - (xx - bx0) / (bx1 - bx0), 0, 1) ** 1.3
    hx *= sm(np.clip((xx - bx0) / 28, 0, 1))
    vy = sm(np.clip((yy - by0) / 60, 0, 1)) * sm(np.clip((by1 - yy) / 30, 0, 1))
    m = 0.62 * hx * vy
  img[..., :3] = (8, 7, 6)
  img[..., 3] = m * 255
  gold = hexrgb(style["accent"])

  def paint(x0, y0, x1, y1, a=1.0):
    x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    sub = img[y0:y1, x0:x1]
    al = a
    sub[..., :3] = sub[..., :3] * (1 - al) + np.array(gold) * al
    sub[..., 3] = 255 * (al + sub[..., 3] / 255 * (1 - al))

  if accent:
    ax, ay0, ay1 = accent
    paint(ax, ay0, ax + 3, ay1)
  for rx0, ry, rx1 in rules:
    # thin rule tapering at both ends
    for x in range(int(rx0), int(rx1)):
      u = (x - rx0) / (rx1 - rx0)
      a = min(1.0, min(u, 1 - u) / 0.18)
      paint(x, ry - 1, x + 1, ry + 1, a)
  save_png(img, path, tmp)


def alpha_expr(a, b):
  return f"clip((t-{a:.3f})/{FADE},0,1)*clip(({b:.3f}-t)/{FADE},0,1)"


def overlay(tl, fonts, metrics, tmp):
  W, H, FPS, DUR = tl["w"], tl["h"], tl["fps"], tl["duration"]
  style = tl["text_style"]
  white = style["color"].lstrip("#")
  inputs, chain, report = [], [], []
  prev = "[0:v]"
  chain.append(f"color=c=black@0:s={W}x{H}:r={FPS}:d={DUR},format=rgba[c0]")
  prev = "[c0]"
  for k, ts in enumerate(tl["texts"]):
    geo = layout(ts, metrics, W, H)
    pos, box, rules, accent, widths = geo
    t_in, t_out = ts["t_in"], ts["t_out"]
    png = os.path.join(tmp, f"bar_{ts['id']}.png")
    bar_png(ts, geo, style, W, H, png, tmp)
    inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{DUR}", "-i", png]
    idx = len(inputs) // 8
    lab = f"[b{k}]"
    chain.append(
      f"[{idx - 1}:v]format=rgba,fade=t=in:st={t_in}:d={FADE}:alpha=1,"
      f"fade=t=out:st={t_out - FADE:.3f}:d={FADE}:alpha=1{lab}")
    nxt = f"[o{k}]"
    chain.append(f"{prev}{lab}overlay=0:0:format=auto:enable='between(t,{t_in},{t_out})'{nxt}")
    prev = nxt
    draws = []
    for i, (line, (x, base, size, fk)) in enumerate(zip(ts["lines"], pos)):
      tf = os.path.join(tmp, f"t_{ts['id']}_{i}.txt")
      with open(tf, "w", encoding="utf-8") as f:
        f.write(line["text"])
      a = t_in + i * STAGGER
      ae = alpha_expr(a, t_out)
      rise = f"{SLIDE}*(1-clip((t-{a:.3f})/{FADE},0,1))"
      draws.append(
        f"drawtext=fontfile={fonts[fk]}:textfile={tf}:expansion=none:"
        f"fontsize={size}:fontcolor=0x{white}:y_align=baseline:"
        f"shadowcolor=black@0.45:shadowx=2:shadowy=2:"
        f"x='{x}':y='{base:.1f}+{rise}':alpha='{ae}':enable='between(t,{t_in},{t_out})'")
    nxt = f"[d{k}]"
    chain.append(f"{prev}{','.join(draws)}{nxt}")
    prev = nxt
    full_from = t_in + (len(ts["lines"]) - 1) * STAGGER + FADE
    full_to = t_out - FADE
    report.append((ts["id"], t_in, t_out, ts["anchor"], full_from, full_to, box))
  chain[-1] = chain[-1][: -len(prev)] + "[out]"
  graph = os.path.join(tmp, "overlay.txt")
  with open(graph, "w", encoding="utf-8") as f:
    f.write(";\n".join(chain))
  run([FFMPEG, "-y", *inputs, "-/filter_complex", graph, "-map", "[out]",
       "-r", str(FPS), "-t", f"{DUR}", "-c:v", "qtrle", "-pix_fmt", "argb", OVERLAY])
  return report


def grade(tl):
  """Warm luxury tone + light vignette; end card background eases into blur + dim."""
  W, FPS = tl["w"], tl["fps"]
  st = tl["end"]["start"]
  ramp = tl["xf"]               # ease in over the crossfade into the end card
  sig = 18.0
  ease = lambda u: 0.5 - 0.5 * math.cos(math.pi * u)
  n = int(round(ramp * FPS))
  cmds = []
  for i in range(n + 1):
    t = st + i / FPS
    s = max(0.05, sig * ease(i / n))
    cmds.append(f"{t:.4f} gblur@endblur sigma {s:.3f}, gblur@endblur sigmaV {s:.3f}")
  parts = []
  if tl.get("grade", {}).get("warm"):
    parts.append("colorbalance=rs=0.025:gs=0.005:bs=-0.03:rm=0.02:bm=-0.025:rh=0.01:bh=-0.015")
  parts.append("eq=saturation=1.05:contrast=1.02")
  if tl.get("grade", {}).get("vignette"):
    parts.append("vignette=angle=0.42")
  parts.append(f"sendcmd=c='{';'.join(cmds)}'")
  parts.append(f"gblur@endblur=sigma=0.05:sigmaV=0.05:steps=2:enable='gte(t,{st})'")
  parts.append(
    f"eq=brightness='-0.12*(0.5-0.5*cos(PI*clip((t-{st})/{ramp},0,1)))':eval=frame")
  return ",".join(parts)


def main():
  with open(TL, encoding="utf-8") as f:
    tl = json.load(f)
  os.makedirs(OUTDIR, exist_ok=True)
  tmp = tempfile.mkdtemp(prefix="fx_")
  try:
    fonts, metrics = extract_fonts(tmp)
    rep = overlay(tl, fonts, metrics, tmp)
  finally:
    shutil.rmtree(tmp, ignore_errors=True)
  with open(GRADE, "w", encoding="utf-8") as f:
    f.write(grade(tl) + "\n")
  for r in rep:
    print(f"{r[0]:6s} {r[1]:5.1f}-{r[2]:5.1f} {r[3]:11s} full {r[4]:.2f}-{r[5]:.2f} "
          f"({r[5] - r[4]:.2f}s) box {tuple(round(v) for v in r[6])}")
  print("wrote", OVERLAY, GRADE)


if __name__ == "__main__":
  main()
