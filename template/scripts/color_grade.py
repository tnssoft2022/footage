#!/usr/bin/env python3
# สคริปต์ฐานปรับสีและแสงรูปก่อนทำภาพรวม (footage-assistant-photo)
# คัดลอกไปที่ work/<รหัส>/color_grade.py แล้วแก้ค่าในส่วน "ตั้งค่างาน" ห้ามแก้ไฟล์นี้ในที่
#
# ใช้งาน:
#   python color_grade.py                      ปรับรูปใน FILES จาก SRC ลง DST แล้วพิมพ์ตารางก่อน/หลัง
#   python color_grade.py --compare <โฟลเดอร์>  ทำภาพเปรียบเทียบก่อน/หลังด้วย
#   python color_grade.py --measure <ภาพ> x:y:w:h [x:y:w:h ...]
#                                              วัดค่าในกรอบ (เช่นช่องรูปในภาพรวม): luma, ความอิ่มสี, ผนัง R−B/G−B
#
# ลำดับการปรับ (ได้ผลจากงาน 00000017, 00000433, 00000957):
#   1. ดึงสีเหลือง–ส้ม (ไฟหลอด) เข้าหา luma ของตัวเอง เฉพาะรูปที่ตั้ง yellow
#   2. white balance ใน linear light ให้ผนังขาวได้ R−B/G−B ตามเป้าของสไตล์ ไม่แตะส่วนที่สว่างมาก
#   3. ลดความอิ่มสีอุ่นบนผนัง (ส่วนบนของรูป ไม่ลงไปถึงพื้นไม้)
#   4. S-curve เบาๆ
#   5. บีบสีที่จัดเกิน (ผ้าปูเตียงฟ้า ฯลฯ)
#   6. เพิ่มความอิ่มของไม้เล็กน้อย
#   7. exposure บน linear luminance แบบมี shoulder ไปที่ luma เป้าหมาย (แทน gamma ที่ชนขอบ)
#   8. วัดผนังซ้ำแล้วแก้ WB อีก 2 รอบ (ขั้นก่อนหน้าทำให้สีเลื่อน)
#   9. unsharp เล็กน้อย และไม่ให้มีพิกเซลขาวโพลนเพิ่มจากต้นฉบับ
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

# ---------------- ตั้งค่างาน (แก้ในสำเนา) ----------------
SRC = 'uploads/<ts>/originals'       # ต้นฉบับก่อนปรับแสง ห้ามใช้ images/
DST = 'work/<รหัส>/graded'
FILES = ['01.jpg']                   # เฉพาะรูปใน shots
STYLE = 'navy'                       # navy | black | minimal | red

# เป้าหมายตามสไตล์: ผนัง R−B, G−B (หน่วย 0–255) และ luma เฉลี่ยของรูป
STYLE_TARGETS = {
  'navy': {'rb': 2.0, 'gb': 2.0, 'luma': 160.0},
  'black': {'rb': 2.0, 'gb': 2.0, 'luma': 160.0},
  'minimal': {'rb': 6.0, 'gb': 2.0, 'luma': 160.0},
  'red': {'rb': 5.0, 'gb': 2.0, 'luma': 160.0},
}

# ค่ากลาง ใช้กับทุกรูป
DEFAULTS = {
  'wb_max': 0.60,       # gain WB ต่อช่องสีอยู่ในช่วง 1/(1+wb_max)–(1+wb_max) ไฟเหลืองจัดใช้ 0.45 ไฟส้มทั้งห้องใช้ได้ถึง ~8
  'wb_protect': 0.88,   # luma (0–1) ที่เริ่มไม่ปรับ WB เพื่อกันหน้าต่าง/โคมไฟเพี้ยน (ไฟส้มทั้งห้องตั้ง 0.97)
  'yellow': 0.0,        # 0–1 ดึงสีเหลือง–ส้ม (hue 12–yellow_hue°) ที่ความอิ่ม ≤ yellow_sat เข้าหา luma
  'yellow_sat': 0.60,
  'yellow_hue': 68,
  'wall_desat': 0.45,   # ลดความอิ่มสีอุ่นบนผนัง
  'wall_ymax': 0.65,    # ทำแค่ส่วนบนของรูป (สัดส่วนความสูง) กันพื้นไม้ซีด
  'curve': 0.12,        # ความแรง S-curve (0 = ไม่ใช้)
  'chroma_max': 0.55,   # ความอิ่มที่เกินค่านี้ถูกบีบลงครึ่งหนึ่ง
  'blue_desat': 0.25,   # ลดความอิ่มสีฟ้า/น้ำเงินจัด (hue 180–250°, ความอิ่ม > 0.30)
  'wood': 1.08,         # คูณความอิ่มของไม้ (hue 15–45°)
  'sat': 1.0,           # คูณความอิ่มทั้งรูป (รูปที่แก้ไฟส้มแรงแล้วออกเทาหม่น ใช้ 1.3–1.5)
  'luma': None,         # None = ใช้ค่าของสไตล์
  'knee': 0.78,         # จุดเริ่ม shoulder ของ exposure (linear)
  'sharpen': (1.2, 55, 3),
  'rb': None,           # None = ใช้ค่าของสไตล์
  'gb': None,
  'wall_box': None,     # (x0, y0, x1, y1) สัดส่วน 0–1 ถ้าตั้ง ใช้วัดผนังเฉพาะกรอบนี้
}

# ค่าแยกรายรูป ใส่เฉพาะรูปที่ค่ากลางยังไม่ได้ผล เช่น
#   '02.jpg': {'wb_max': 0.45, 'yellow': 1.0},          ห้องน้ำไฟเหลือง
#   '01.jpg': {'wb_max': 1.5, 'yellow': 0.85, 'yellow_sat': 0.95, 'yellow_hue': 100, 'sat': 1.4},
#                                                       ไฟส้มจัดทั้งห้อง (ห้าม wb_max สูงมาก ช่องน้ำเงินแทบเป็นศูนย์ จะขยายจุดรบกวนเป็นคราบ)
#   '08.jpg': {'luma': 165},                            ช่องมีโซฟาเข้มเต็ม ตั้ง luma สูงขึ้นให้ช่องในภาพรวมสว่างเท่ากัน
OVERRIDES = {}
# --------------------------------------------------------


def to_lin(a):
  return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def to_srgb(a):
  a = np.clip(a, 0, 1)
  return np.where(a <= 0.0031308, a * 12.92, 1.055 * a ** (1 / 2.4) - 0.055)


def luma(a):
  return a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722


def rgb_to_hsv(a):
  r, g, b = a[..., 0], a[..., 1], a[..., 2]
  mx = a.max(-1)
  mn = a.min(-1)
  d = mx - mn
  s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0)
  dd = np.maximum(d, 1e-6)
  h = np.where(mx == r, ((g - b) / dd) % 6, np.where(mx == g, (b - r) / dd + 2, (r - g) / dd + 4))
  h = np.where(d < 1e-6, 0, h) * 60.0
  return h, s, mx


def hsv_to_rgb(h, s, v):
  c = v * s
  hp = (h / 60.0) % 6
  x = c * (1 - np.abs(hp % 2 - 1))
  z = np.zeros_like(h)
  i = np.floor(hp).astype(int)
  r = np.choose(i, [c, x, z, z, x, c])
  g = np.choose(i, [x, c, c, x, z, z])
  b = np.choose(i, [z, z, x, c, c, x])
  m = v - c
  return np.stack([r + m, g + m, b + m], -1)


def smooth(e0, e1, x):
  t = np.clip((x - e0) / max(e1 - e0, 1e-6), 0, 1)
  return t * t * (3 - 2 * t)


def hue_band(h, lo, hi, soft=8.0):
  return smooth(lo - soft, lo, h) * (1 - smooth(hi, hi + soft, h))


def wall_mask(a, box=None):
  # ผนังขาว/เพดาน: สว่าง ความอิ่มต่ำ อยู่ส่วนบน 65% ของรูป
  h_, w_ = a.shape[:2]
  _, s, v = rgb_to_hsv(a)
  y = luma(a)
  m = (y > 0.45) & (y < 0.95) & (s < 0.45) & (v < 0.985)
  rows = np.arange(h_)[:, None] < h_ * 0.65
  m &= rows
  if box:
    x0, y0, x1, y1 = box
    bm = np.zeros_like(m)
    bm[int(y0 * h_):int(y1 * h_), int(x0 * w_):int(x1 * w_)] = True
    m &= bm
  if m.sum() < 500:
    # รูปที่ผนังน้อย ใช้ส่วนที่สว่างที่สุด 20% แทน
    m = y >= np.quantile(y, 0.8)
  return m


def wall_stats(a, m):
  c = a[m].mean(0) * 255
  return c, c[0] - c[2], c[1] - c[2]


def settings(name):
  # ลำดับ: ค่ากลาง → เป้าของสไตล์ (ถ้าค่ากลางไม่ได้ตั้ง rb/gb/luma) → ค่าแยกรายรูป
  p = dict(DEFAULTS)
  for k, v in STYLE_TARGETS[STYLE].items():
    if p.get(k) is None:
      p[k] = v
  p.update(OVERRIDES.get(name, {}))
  return p


def white_balance(a, m, p):
  lin = to_lin(a)
  wl = lin[m].mean(0)
  # สีเป้าหมายของผนัง (sRGB) ที่ความสว่างเดิม
  ws = a[m].mean(0)
  g = ws[1]
  tgt = np.array([g + (p['rb'] - p['gb']) / 255, g, g - p['gb'] / 255])
  tl = to_lin(np.clip(tgt, 0, 1))
  gain = tl / np.maximum(wl, 1e-6)
  gain = gain / (gain @ np.array([0.2126, 0.7152, 0.0722]))   # คงความสว่างเดิม
  gain = np.clip(gain, 1 / (1 + p['wb_max']), 1 + p['wb_max'])
  y = luma(a)
  w = 1 - smooth(p['wb_protect'], 0.99, y)
  out = lin * (1 + (gain - 1) * w[..., None])
  return to_srgb(out)


def pull_to_luma(a, k, mask):
  y = luma(a)[..., None]
  return a + (y - a) * (k * mask)[..., None]


def grade(img, p):
  a = np.asarray(img.convert('RGB')).astype(np.float32) / 255.0
  orig_max = a.max(-1)
  h_ = a.shape[0]
  m = wall_mask(a, p.get('wall_box'))

  # 1. ไฟเหลือง–ส้ม (ทำก่อน WB เพื่อให้ WB แก้ส่วนที่เหลือไปที่เป้าพอดี ไม่เลยเป้า)
  if p['yellow'] > 0:
    h, s, v = rgb_to_hsv(a)
    mk = hue_band(h, 12, p['yellow_hue']) * (1 - smooth(p['yellow_sat'], p['yellow_sat'] + 0.2, s)) * smooth(0.12, 0.3, v)
    a = pull_to_luma(a, p['yellow'], mk)

  # 2. white balance
  a = white_balance(a, m, p)

  # 3. สีอุ่นบนผนัง
  if p['wall_desat'] > 0:
    h, s, v = rgb_to_hsv(a)
    rows = 1 - smooth(p['wall_ymax'] - 0.08, p['wall_ymax'], np.arange(h_)[:, None] / h_)
    mk = (hue_band(h, 0, 60) + hue_band(h, 330, 360)) * (1 - smooth(0.25, 0.40, s)) * smooth(0.5, 0.65, v) * rows
    a = pull_to_luma(a, p['wall_desat'], np.clip(mk, 0, 1))

  # 4. S-curve บน luma
  if p['curve'] > 0:
    y = luma(a)
    y2 = y + (smooth(0, 1, y) - y) * p['curve']
    a = a * (y2 / np.maximum(y, 1e-4))[..., None]
    a = np.clip(a, 0, 1)

  # 5–6. ความอิ่มสี
  h, s, v = rgb_to_hsv(np.clip(a, 0, 1))
  s = np.where(s > p['chroma_max'], p['chroma_max'] + (s - p['chroma_max']) * 0.5, s)
  if p['blue_desat'] > 0:
    s = s * (1 - p['blue_desat'] * hue_band(h, 180, 250) * smooth(0.25, 0.35, s))
  if p['wood'] != 1:
    s = s * (1 + (p['wood'] - 1) * hue_band(h, 15, 45) * smooth(0.15, 0.25, s) * (1 - smooth(0.75, 0.9, s)))
  s = np.clip(s * p['sat'], 0, 1)
  a = hsv_to_rgb(h, s, v)

  # 7. exposure ให้ luma เฉลี่ยได้ตามเป้า
  lin = to_lin(np.clip(a, 0, 1))
  L = luma(lin)
  k = p['knee']

  def tone(e):
    x = L * e
    return np.where(x <= k, x, k + (1 - k) * (1 - np.exp(-(x - k) / (1 - k))))

  def mean_out(e):
    Lo = tone(e)
    r = lin * (Lo / np.maximum(L, 1e-6))[..., None]
    return float(luma(to_srgb(r)).mean() * 255), r

  lo, hi = 0.2, 6.0
  for _ in range(30):
    mid = (lo * hi) ** 0.5
    mv, _ = mean_out(mid)
    if mv < p['luma']:
      lo = mid
    else:
      hi = mid
  _, lin = mean_out((lo * hi) ** 0.5)
  # สีที่เกิน 1 ให้ลดความอิ่มเข้าหาขาวแทนการตัดช่องสี
  over = lin.max(-1, keepdims=True)
  Lw = luma(lin)[..., None]
  t = np.clip((over - 1) / np.maximum(over - Lw, 1e-6), 0, 1)
  lin = np.where(over > 1, lin + (Lw - lin) * t, lin)
  a = to_srgb(lin)

  # 8. ขั้นอื่นทำให้ผนังเลื่อนไปจากเป้า วัดผนังซ้ำแล้วแก้ WB อีก 2 รอบ
  for _ in range(2):
    a = white_balance(a, m, p)

  # 9. unsharp แล้วไม่ให้ขาวโพลนเพิ่มจากต้นฉบับ
  out = Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8))
  if p['sharpen']:
    r, pc, th = p['sharpen']
    out = out.filter(ImageFilter.UnsharpMask(radius=r, percent=pc, threshold=th))
  b = np.asarray(out).astype(np.float32)
  cap = np.where(orig_max < 250 / 255, 249.0, 255.0)[..., None]
  b = np.minimum(b, cap)
  return Image.fromarray(b.astype(np.uint8))


def stats(img, m=None):
  a = np.asarray(img.convert('RGB')).astype(np.float32) / 255.0
  if m is None:
    m = wall_mask(a)
  _, rb, gb = wall_stats(a, m)
  _, s, _ = rgb_to_hsv(a)
  y = luma(a) * 255
  blown = float((a.max(-1) >= 250 / 255).mean() * 100)
  return rb, gb, float(y.mean()), float(s.mean()), blown


def compare(src, dst, path):
  w = 600
  a = src.convert('RGB')
  b = dst.convert('RGB')
  h = int(a.height * w / a.width)
  sheet = Image.new('RGB', (w * 2 + 10, h), 'white')
  sheet.paste(a.resize((w, h), Image.LANCZOS), (0, 0))
  sheet.paste(b.resize((w, h), Image.LANCZOS), (w + 10, 0))
  sheet.save(path, quality=88)


def measure(path, boxes):
  img = Image.open(path).convert('RGB')
  a = np.asarray(img).astype(np.float32) / 255.0
  print('กรอบ\tluma\tความอิ่ม\tผนัง R−B\tผนัง G−B')
  for bx in boxes:
    x, y, w, h = [int(v) for v in bx.split(':')]
    c = a[y:y + h, x:x + w]
    m = wall_mask(c)
    _, rb, gb = wall_stats(c, m)
    _, s, _ = rgb_to_hsv(c)
    print(f'{bx}\t{luma(c).mean() * 255:.1f}\t{s.mean():.3f}\t{rb:+.1f}\t{gb:+.1f}')


def main():
  args = sys.argv[1:]
  if args and args[0] == '--measure':
    measure(args[1], args[2:])
    return
  cmp_dir = None
  if args and args[0] == '--compare':
    cmp_dir = args[1]
    os.makedirs(cmp_dir, exist_ok=True)
  os.makedirs(DST, exist_ok=True)
  print(f'สไตล์ {STYLE} เป้า {STYLE_TARGETS[STYLE]}')
  print('รูป\tR−B ก่อน→หลัง\tG−B ก่อน→หลัง\tluma ก่อน→หลัง\tอิ่ม ก่อน→หลัง\t≥250% ก่อน→หลัง')
  for f in FILES:
    src = Image.open(os.path.join(SRC, f)).convert('RGB')
    p = settings(f)
    a = np.asarray(src).astype(np.float32) / 255.0
    m = wall_mask(a, p.get('wall_box'))
    out = grade(src, p)
    out.save(os.path.join(DST, f), quality=95, subsampling=0)
    b0 = stats(src, m)
    b1 = stats(out, m)
    print(f'{f}\t{b0[0]:+.1f}→{b1[0]:+.1f}\t{b0[1]:+.1f}→{b1[1]:+.1f}\t'
          f'{b0[2]:.1f}→{b1[2]:.1f}\t{b0[3]:.3f}→{b1[3]:.3f}\t{b0[4]:.2f}→{b1[4]:.2f}')
    if cmp_dir:
      compare(src, out, os.path.join(cmp_dir, 'compare_' + f))


if __name__ == '__main__':
  main()
