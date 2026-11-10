"""00000017 edit: Ken Burns + crossfade + generated music (no text, no grade).

All timing comes from timeline.json. Functions adapted from work/make_video.py
(luxury style: cosine easing, pan 70% of travel, slow pad + piano music).

Run:  <venv>/bin/python make_edit.py <ffmpeg-path> [<tmp-dir>]
Out:  edit/edit.mp4  (1920x1080 30fps H.264 CRF 12, AAC stereo 48k 192k)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave

import numpy as np

FFMPEG = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
TL = json.load(open(os.path.join(HERE, "timeline.json"), encoding="utf-8"))
CODE = TL["code"]
IMG = TL["img_dir"]
W, H, FPS = TL["w"], TL["h"], TL["fps"]
XF = TL["xf"]
DUR = TL["duration"]
KB = TL.get("kenburns", {})
PAN = KB.get("pan_frac", 0.7)
OUT = os.path.join(HERE, "edit", "edit.mp4")
SS = 2  # supersample factor for the zoompan source still
FOCUS = {
  "center": (0.5, 0.5), "top": (0.5, 0.0), "bottom": (0.5, 1.0), "left": (0.0, 0.5), "right": (1.0, 0.5),
  "top-left": (0.0, 0.0), "top-right": (1.0, 0.0), "bottom-left": (0.0, 1.0), "bottom-right": (1.0, 1.0),
}


def run(cmd):
  r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
  if r.returncode:
    sys.stderr.write(r.stderr[-3000:])
    raise SystemExit(f"ffmpeg failed: {' '.join(cmd[:6])} ...")


def frames(sec):
  return int(round(sec * FPS))


def src_size(src):
  probe = subprocess.run([FFMPEG, "-i", src], capture_output=True, text=True).stderr
  m = re.search(r"Video:.*?\b(\d{2,5})x(\d{2,5})\b", probe)
  return int(m.group(1)), int(m.group(2))


def base_frame(src, dst, fit, crop=None):
  """SSx-res still. cover: centered cover-fill; blur-pad: centered on a blurred copy;
  crop: fraction box of the source (already 16:9) scaled to fill."""
  iw, ih = src_size(src)
  bw, bh = W * SS, H * SS
  pre = ""
  if crop:
    x0, y0 = int(round(crop["x0"] * iw)), int(round(crop["y0"] * ih))
    x1, y1 = int(round(crop["x1"] * iw)), int(round(crop["y1"] * ih))
    pre = f"crop={x1 - x0}:{y1 - y0}:{x0}:{y0},"
  if fit == "blur-pad":
    vf = (
      f"{pre}split[a][b];"
      f"[a]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
      f"gblur=sigma=40,eq=brightness=-0.06[bg];"
      f"[b]scale={bw}:{bh}:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
      f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
    )
  else:
    vf = f"{pre}scale={bw}:{bh}:force_original_aspect_ratio=increase:flags=lanczos,crop={bw}:{bh}"
  run([FFMPEG, "-y", "-i", src, "-filter_complex", vf, "-frames:v", "1", dst])


def kenburns(still, dst, move, seconds, zmax, focus="center"):
  """Cosine-eased zoom/pan; pans use only PAN (70%) of the available travel."""
  n = frames(seconds)
  p = f"(on/{n - 1})"
  ease = f"(0.5-0.5*cos(PI*{p}))"
  fx, fy = FOCUS.get(focus, (0.5, 0.5))
  zx, zy = f"(iw-iw/zoom)*{fx}", f"(ih-ih/zoom)*{fy}"
  a, b = (1 - PAN) / 2, PAN
  if move == "in":
    z, x, y = f"1+{zmax - 1:.4f}*{ease}", zx, zy
  elif move == "out":
    z, x, y = f"{zmax:.4f}-{zmax - 1:.4f}*{ease}", zx, zy
  elif move == "right":
    z, x, y = f"{zmax:.4f}", f"(iw-iw/zoom)*({a:.3f}+{b:.3f}*{ease})", zy
  else:  # left
    z, x, y = f"{zmax:.4f}", f"(iw-iw/zoom)*({a:.3f}+{b:.3f}*(1-{ease}))", zy
  vf = f"zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={W}x{H}:fps={FPS},format=yuv420p"
  run([FFMPEG, "-y", "-loop", "1", "-framerate", str(FPS), "-i", still, "-vf", vf,
       "-frames:v", str(n), "-c:v", "libx264", "-crf", "8", "-preset", "medium", dst])


def music(dst, seconds, sr=48000):
  """Calm luxury instrumental: long pad chords + slow broken-chord piano."""
  t = np.arange(int(seconds * sr)) / sr
  out = np.zeros((len(t), 2))
  hz = lambda m: 440 * 2 ** ((m - 69) / 12)
  # Dmaj9 - Bm9 - Gmaj7 - A(sus) , 6 s per chord (about 60 bpm, 6 beats)
  chords = [[62, 66, 69, 73, 76], [59, 62, 66, 69, 73], [55, 59, 62, 66, 69], [57, 62, 64, 69, 71]]
  bar = 6.0
  for i in range(int(np.ceil(seconds / bar))):
    notes = chords[i % 4]
    s, e = int(i * bar * sr), min(int((i + 1) * bar * sr + 1.5 * sr), len(t))
    if s >= len(t):
      break
    seg = t[s:e] - i * bar
    env = np.minimum(1, seg / 1.8) * np.clip((bar + 1.5 - seg) / 2.0, 0, 1)
    for m in notes[:4]:
      f = hz(m - 12)
      for side, det in ((0, 1.003), (1, 0.997)):
        tone = (np.sin(2 * np.pi * f * seg) + 0.25 * np.sin(2 * np.pi * 2 * f * seg)
                + 0.5 * np.sin(2 * np.pi * f * det * seg))
        out[s:e, side] += 0.045 * env * tone
    out[s:e, :] += (0.07 * env * np.sin(2 * np.pi * hz(notes[0] - 24) * seg))[:, None]
    # piano: broken chord, one note per beat, last beat rests
    pattern = [0, 2, 4, 3, 1, None]
    for j, idx in enumerate(pattern):
      if idx is None:
        continue
      ns = s + int(j * 1.0 * sr)
      ne = min(ns + int(3.0 * sr), len(t))
      if ns >= len(t):
        break
      tt = t[ns:ne] - t[ns]
      f = hz(notes[idx] + 12)
      env_p = np.exp(-tt * 1.6) * np.minimum(1, tt / 0.004)
      sig = 0.06 * env_p * (np.sin(2 * np.pi * f * tt) + 0.35 * np.exp(-tt * 3) * np.sin(2 * np.pi * 2 * f * tt)
                            + 0.12 * np.exp(-tt * 6) * np.sin(2 * np.pi * 3 * f * tt))
      pan = 0.35 + 0.3 * (j % 2)
      out[ns:ne, 0] += sig * (1 - pan)
      out[ns:ne, 1] += sig * pan
  # soft stereo echo for space
  for d_s, g in ((0.37, 0.28), (0.74, 0.14)):
    d = int(d_s * sr)
    echo = np.zeros_like(out)
    echo[d:, 0] = out[:-d, 1] * g
    echo[d:, 1] = out[:-d, 0] * g
    out += echo
  out /= np.max(np.abs(out)) * 1.25
  pcm = (out * 32767).astype("<i2")
  with wave.open(dst, "wb") as wf:
    wf.setnchannels(2)
    wf.setsampwidth(2)
    wf.setframerate(sr)
    wf.writeframes(pcm.tobytes())


def main():
  tmp = sys.argv[2] if len(sys.argv) > 2 else tempfile.mkdtemp(prefix=f"edit_{CODE}_")
  os.makedirs(tmp, exist_ok=True)
  os.makedirs(os.path.dirname(OUT), exist_ok=True)
  zdef = KB.get("zmax", 1.06)
  segs = [dict(file=s["file"], move=s["move"], zmax=s.get("zmax", zdef), fit=s.get("fit", "cover"),
               crop=s.get("crop"), focus=s.get("focus", "center"), start=s["start"], len=s["len"])
          for s in TL["shots"]]
  e = TL["end"]
  # end card: plain image + camera move; blur/dim is done by the effect layer
  segs.append(dict(file=e["src"], move=e["move"], zmax=e.get("zmax", zdef), fit=e.get("fit", "cover"),
                   crop=e.get("crop"), focus=e.get("focus", "center"), start=e["start"], len=e["len"]))
  clips = []
  for i, s in enumerate(segs):
    still = os.path.join(tmp, f"still{i}.png")
    clip = os.path.join(tmp, f"clip{i}.mp4")
    base_frame(os.path.join(IMG, s["file"]), still, s["fit"], s["crop"])
    kenburns(still, clip, s["move"], s["len"], s["zmax"], s["focus"])
    clips.append(clip)
    print("shot", i + 1, s["file"], s["move"], s["fit"], f"{s['start']}+{s['len']}", flush=True)

  wav = os.path.join(tmp, "music.wav")
  music(wav, DUR + 1)
  print("music done", flush=True)

  inputs, chain = [], []
  for c in clips:
    inputs += ["-i", c]
  prev = "[0:v]"
  for i in range(1, len(clips)):
    lab = f"[v{i}]"
    off = frames(segs[i]["start"]) / FPS
    chain.append(f"{prev}[{i}:v]xfade=transition=fade:duration={XF}:offset={off:.4f}{lab}")
    prev = lab
  chain.append(f"{prev}format=yuv420p[v]")
  m = TL.get("music", {})
  fi, fo = m.get("fade_in", 3), m.get("fade_out", 4)
  a = len(clips)
  chain.append(
    f"[{a}:a]atrim=0:{DUR:.3f},afade=t=in:st=0:d={fi},afade=t=out:st={DUR - fo:.3f}:d={fo},"
    f"loudnorm=I=-18:TP=-2:LRA=7,aresample=48000[a]"
  )
  fc = os.path.join(tmp, "filter.txt")
  with open(fc, "w") as f:
    f.write(";\n".join(chain))
  run([FFMPEG, "-y", *inputs, "-i", wav, "-/filter_complex", fc,
       "-map", "[v]", "-map", "[a]", "-r", str(FPS),
       "-c:v", "libx264", "-preset", "slow", "-crf", "12", "-pix_fmt", "yuv420p",
       "-profile:v", "high", "-movflags", "+faststart",
       "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-ar", "48000", "-t", f"{DUR:.3f}", OUT])
  if len(sys.argv) <= 2:
    shutil.rmtree(tmp, ignore_errors=True)
  print("wrote", OUT, f"{DUR:.1f}s")


if __name__ == "__main__":
  main()
