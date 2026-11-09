"""TEST002 tour video: Ken Burns + crossfade + generated music.

Run:  <venv>/bin/python make_video.py <ffmpeg-path>
"""
import os
import re
import subprocess
import sys
import wave

import numpy as np

FFMPEG = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
CODE = "TEST002"
IMG = os.path.join(HERE, "images")
WORK = os.path.join(HERE, "work")
OUT = os.path.join(HERE, "output", f"{CODE}.mp4")
FONT = "/System/Library/Fonts/HelveticaNeue.ttc"

W, H, FPS = 1920, 1080, 30
SHOT = 3.5   # visible time per shot
XF = 0.8     # crossfade length
CLIP = SHOT + XF

# tour order: entrance -> overview -> angles -> best shot
ORDER = [
  ("6.jpg", "in"),     # lobby / lifts
  ("1.jpg", "out"),    # overview through glass doors
  ("3.jpg", "right"),  # bed + balcony
  ("4.jpg", "left"),   # TV + desk
  ("5.jpg", "in"),     # TV + aircon
  ("2.jpg", "out"),    # dining corner (portrait)
  ("7.jpg", "in"),     # finale (portrait)
]


def run(cmd):
  subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def base_frame(src, dst, w, h):
  """2x-res still: wide shots cover-fill; taller ones sit centered on a blurred copy."""
  probe = subprocess.run([FFMPEG, "-i", src], capture_output=True, text=True).stderr
  m = re.search(r"Video:.*?\b(\d{2,5})x(\d{2,5})\b", probe)
  iw, ih = int(m.group(1)), int(m.group(2))
  bw, bh = w * 2, h * 2
  if iw / ih >= 1.6:
    vf = f"scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh}"
  else:
    vf = (
      f"split[a][b];"
      f"[a]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
      f"gblur=sigma=40,eq=brightness=-0.06[bg];"
      f"[b]scale={bw}:{bh}:force_original_aspect_ratio=decrease[fg];"
      f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
    )
  run([FFMPEG, "-y", "-i", src, "-filter_complex", vf, "-frames:v", "1", dst])


def kenburns(still, dst, move):
  n = int(round(CLIP * FPS))
  p = f"(on/{n - 1})"
  ease = f"(0.5-0.5*cos(PI*{p}))"
  zmax = 1.10
  if move == "in":
    z, x, y = f"1+{zmax - 1}*{ease}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
  elif move == "out":
    z, x, y = f"{zmax}-{zmax - 1}*{ease}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
  elif move == "right":
    z, x, y = f"{zmax}", f"(iw-iw/zoom)*{ease}", "ih/2-(ih/zoom/2)"
  else:  # left
    z, x, y = f"{zmax}", f"(iw-iw/zoom)*(1-{ease})", "ih/2-(ih/zoom/2)"
  vf = f"zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={W}x{H}:fps={FPS},format=yuv420p"
  run([FFMPEG, "-y", "-loop", "1", "-framerate", str(FPS), "-i", still, "-vf", vf,
       "-frames:v", str(n), "-c:v", "libx264", "-crf", "14", "-preset", "medium", dst])


def music(dst, seconds, sr=48000):
  """Soft self-made instrumental: warm pad chords + gentle plucked arpeggio."""
  t = np.arange(int(seconds * sr)) / sr
  out = np.zeros((len(t), 2))
  # I - vi - IV - V in C, 4 s per chord
  chords = [[60, 64, 67, 72], [57, 60, 64, 69], [53, 57, 60, 65], [55, 59, 62, 67]]
  hz = lambda m: 440 * 2 ** ((m - 69) / 12)
  bar = 4.0
  for i in range(int(np.ceil(seconds / bar))):
    notes = chords[i % 4]
    s, e = int(i * bar * sr), min(int((i + 1) * bar * sr + 0.6 * sr), len(t))
    seg = t[s:e] - i * bar
    env = np.minimum(1, seg / 0.8) * np.minimum(1, np.maximum(0, (bar + 0.6 - seg) / 0.9))
    for k, m in enumerate(notes):
      f = hz(m - 12)
      tone = np.sin(2 * np.pi * f * seg) + 0.3 * np.sin(2 * np.pi * 2 * f * seg)
      det = np.sin(2 * np.pi * f * 1.004 * seg)
      out[s:e, 0] += 0.06 * env * (tone + 0.5 * det)
      out[s:e, 1] += 0.06 * env * (tone + 0.5 * np.sin(2 * np.pi * f * 0.996 * seg))
    out[s:e, :] += (0.08 * env * np.sin(2 * np.pi * hz(notes[0] - 24) * seg))[:, None]
    # arpeggio, eighth notes at 120 bpm
    pattern = [0, 1, 2, 3, 2, 1, 2, 3]
    for j, idx in enumerate(pattern):
      ns = s + int(j * 0.5 * sr)
      ne = min(ns + int(1.4 * sr), len(t))
      if ns >= len(t):
        break
      tt = t[ns:ne] - t[ns]
      f = hz(notes[idx] + 12)
      pluck = np.exp(-tt * 4.0) * np.minimum(1, tt / 0.005)
      sig = 0.05 * pluck * (np.sin(2 * np.pi * f * tt) + 0.2 * np.sin(2 * np.pi * 3 * f * tt))
      pan = 0.3 + 0.4 * (j % 2)
      out[ns:ne, 0] += sig * (1 - pan)
      out[ns:ne, 1] += sig * pan
  # simple stereo echo for space
  d = int(0.33 * sr)
  echo = np.zeros_like(out)
  echo[d:, 0] = out[:-d, 1] * 0.3
  echo[d:, 1] = out[:-d, 0] * 0.3
  out += echo
  out /= np.max(np.abs(out)) * 1.25
  pcm = (out * 32767).astype("<i2")
  with wave.open(dst, "wb") as wf:
    wf.setnchannels(2)
    wf.setsampwidth(2)
    wf.setframerate(sr)
    wf.writeframes(pcm.tobytes())


def main():
  os.makedirs(WORK, exist_ok=True)
  os.makedirs(os.path.dirname(OUT), exist_ok=True)
  clips = []
  for i, (name, move) in enumerate(ORDER):
    still = os.path.join(WORK, f"still{i}.png")
    clip = os.path.join(WORK, f"clip{i}.mp4")
    base_frame(os.path.join(IMG, name), still, W, H)
    kenburns(still, clip, move)
    clips.append(clip)
    print("shot", i + 1, name, move, flush=True)

  total = len(clips) * SHOT + XF
  wav = os.path.join(WORK, "music.wav")
  music(wav, total + 1)
  print("music done", flush=True)

  inputs, chain = [], []
  for c in clips:
    inputs += ["-i", c]
  prev = "[0:v]"
  for i in range(1, len(clips)):
    lab = f"[v{i}]"
    chain.append(f"{prev}[{i}:v]xfade=transition=fade:duration={XF}:offset={i * SHOT:.3f}{lab}")
    prev = lab
  title = (
    f"drawtext=fontfile={FONT}:text='{CODE}':fontsize=150:fontcolor=white:"
    f"shadowcolor=black@0.55:shadowx=4:shadowy=4:x=(w-tw)/2:y=(h-th)/2:"
    f"alpha='if(lt(t,0.4),0,if(lt(t,1.2),(t-0.4)/0.8,if(lt(t,2.6),1,if(lt(t,3.3),(3.3-t)/0.7,0))))'"
  )
  chain.append(f"{prev}{title},fade=t=in:st=0:d=0.6,fade=t=out:st={total - 1.2:.3f}:d=1.2,format=yuv420p[v]")
  a = len(clips)
  chain.append(
    f"[{a}:a]atrim=0:{total:.3f},afade=t=in:st=0:d=2.5,afade=t=out:st={total - 3:.3f}:d=3,"
    f"loudnorm=I=-18:TP=-2:LRA=7,aresample=48000[a]"
  )
  run([FFMPEG, "-y", *inputs, "-i", wav, "-filter_complex", ";".join(chain),
       "-map", "[v]", "-map", "[a]", "-r", str(FPS),
       "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
       "-profile:v", "high", "-movflags", "+faststart",
       "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-t", f"{total:.3f}", OUT])
  print("wrote", OUT, f"{total:.1f}s")


if __name__ == "__main__":
  main()
