#!/usr/bin/env python3
# ภาพรวม (photo) งาน 00000131 — สไตล์ "ดำ + ทอง หรูหราโมเดิร์น" (แยกจากแบบแดงทองของ template)
# เริ่มจากสำเนา template/scripts/make_photo.py แล้วเปลี่ยนสไตล์/เลย์เอาต์ทั้งหมด
# งานนี้ไม่มี timeline.json: รูป ค่าครอป และข้อความตั้งไว้ในสคริปต์ (ตาม brief ของ footage-assistant)
# ใช้: <venv>/bin/python make_photo.py <ffmpeg-path>
# Pillow ในเครื่องไม่มี libraqm -> ข้อความทั้งหมดวาดด้วย ffmpeg drawtext (harfbuzz) ผ่าน fontfile=/textfile=
# ข้อความสีทองไล่เฉด: วาด drawtext สีขาวลงเลเยอร์มาสก์แยก แล้วเทเกรเดียนต์ทองผ่านมาสก์
import math, os, shutil, subprocess, sys, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
CODE = '00000131'
IMG_DIR = os.path.join(ROOT, 'assets', CODE)
LOGO = os.path.join(ROOT, 'global', 'logo.png')
OUT_DIR = os.path.join(HERE, 'photo')
OUT = os.path.join(OUT_DIR, 'photo.jpg')
TTC = '/System/Library/Fonts/Supplemental/SukhumvitSet.ttc'
FONT_IDX = {'bold': 5, 'regular': 2}
FFMPEG = sys.argv[1] if len(sys.argv) > 1 else '/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg'

W, H = 1080, 1350
M = 54  # ระยะขอบ 5%
SS = 3  # supersample สำหรับรูปทรง/ไอคอน

# ---- ข้อความ (ตาม brief ทุกตัวอักษร) ----
TXT = {
  'code': '00000131',
  'deal': 'ให้เช่า',
  'title': 'เมโทร สกาย บางซื่อ-ประชาชื่น',
  'specs': [('bed', '2 ห้องนอน'), ('bath', '2 ห้องน้ำ'), ('area', '45.22 ตร.ม.'), ('bldg', 'ตึก C ชั้น 3')],
  'furnished': 'พร้อมเฟอร์นิเจอร์และเครื่องใช้ไฟฟ้า',
  # "ค่าเช่า 16,000 บาท/เดือน" แยกเป็น 3 ส่วนเพื่อเน้นตัวเลข (อ่านต่อกันได้ตรงตัวอักษร)
  'price': ('ค่าเช่า', '16,000', 'บาท/เดือน'),
  'tel': 'โทร 064-535-9426',
  'line': 'Line: @uptownassets',
  'whatsapp': 'WhatsApp: +66 64 514 4624',
  'email': 'Email: pang@uptownassets.com',
}

# ---- รูป: ไฟล์ + กรอบที่อนุญาต (สัดส่วน x0,y0,x1,y1) + จุดโฟกัสในกรอบ ----
# 15 นั่งเล่น: ใช้ทั้งความกว้าง ช่วง y 0.08-0.70 (ภาพทิวลิป โซฟา ม่าน หน้าต่าง)
# ตัดล่าง y>0.70 ออก เพราะเครื่องดูดฝุ่นแดงอยู่ที่ x 0.81-0.95, y 0.71-0.79 (ตรวจจากภาพซูม)
# รูปต้นฉบับแนวตั้ง: วางรูปทั้งช่วงนี้แบบไม่ครอปเพิ่ม (fit ตามความสูง) ตรงกลาง
# ด้านข้างเติมด้วยรูปเดียวกันเบลอ+มืด แล้วขอบรูปไล่จางเข้าหากัน (ไม่ยืด/บีบ)
HERO = {'file': '15.jpeg', 'crop': (0.0, 0.08, 1.0, 0.70), 'focus': (0.5, 0.5), 'fit': True}
THUMBS = [
  {'file': '09.jpeg', 'crop': (0.0, 0.0, 1.0, 1.0), 'focus': (0.5, 0.55)},   # ห้องนอนใหญ่ หัวเตียงชั้นไม้
  {'file': '11.jpeg', 'crop': (0.0, 0.0, 1.0, 1.0), 'focus': (0.5, 0.6)},    # มุมทานอาหาร
  {'file': '04.jpeg', 'crop': (0.0, 0.30, 1.0, 0.82), 'focus': (0.5, 0.5)},  # ตู้ทีวีบิวท์อิน + ห้องนอนผ่านประตู (ไม่ใช้ 12: เห็นห้องน้ำ)
]

# ---- สี ----
BG_DARK = (10, 10, 12)
BG_LIGHT = (34, 33, 37)
GOLD_HI = (248, 230, 172)
GOLD_MID = (220, 184, 110)
GOLD_LO = (160, 120, 56)
GOLD_LINE = (212, 175, 100)
WHITE = 'FFFFFF'
SOFT = 'D9D6CF'
INK = '111111'


def lerp(a, b, t):
  return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def metal(w, h, horizontal=False):
  # ทองไล่เฉดแบบโลหะ: สว่างด้านบน เข้มกลาง สว่างอีกครั้งล่าง
  t = np.linspace(0, 1, w if horizontal else h)
  stops = [(0.0, GOLD_HI), (0.45, GOLD_MID), (0.62, GOLD_LO), (1.0, GOLD_MID)]
  out = np.zeros((len(t), 3), np.float32)
  for i in range(len(stops) - 1):
    a, ca = stops[i]
    b, cb = stops[i + 1]
    m = (t >= a) & (t <= b)
    k = ((t[m] - a) / (b - a))[:, None]
    out[m] = np.array(ca) + (np.array(cb) - np.array(ca)) * k
  if horizontal:
    arr = np.tile(out[None, :, :], (h, 1, 1))
  else:
    arr = np.tile(out[:, None, :], (1, w, 1))
  return Image.fromarray(arr.astype(np.uint8))


# ---------- รูป ----------

def grade(im):
  # โทนอุ่นเล็กน้อย (ใกล้ colorbalance rs=.03 bs=-.03 + eq contrast 1.04) ไม่ดันขาวโพลน
  a = np.asarray(im.convert('RGB')).astype(np.float32) / 255.0
  a = (a - 0.5) * 1.04 + 0.5
  a[..., 0] = a[..., 0] * 1.025 + 0.004
  a[..., 1] = a[..., 1] * 1.005
  a[..., 2] = a[..., 2] * 0.965
  a = np.clip(a, 0, 0.985)
  return Image.fromarray((a * 255 + 0.5).astype(np.uint8))


def code_label(code):
  # แคปซูลรหัสต้องมีคำว่า "รหัส" นำหน้าเสมอ
  code = str(code)
  return code if code.startswith('รหัส') else 'รหัส ' + code


def crop_cover(im, w, h, spec):
  # ครอปให้เต็มช่องโดยไม่ยืด/บีบ ภายในกรอบที่อนุญาตเท่านั้น
  sw, sh = im.size
  c = spec['crop']
  rx0, ry0, rx1, ry1 = c[0] * sw, c[1] * sh, c[2] * sw, c[3] * sh
  fx, fy = spec['focus']
  rw, rh = rx1 - rx0, ry1 - ry0
  ar = w / h
  if rw / rh > ar:
    ch, cw = rh, rh * ar
  else:
    cw, ch = rw, rw / ar
  x0 = rx0 + (rw - cw) * fx
  y0 = ry0 + (rh - ch) * fy
  return im.resize((w, h), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))


def rounded_mask(w, h, r):
  m = Image.new('L', (w * SS, h * SS), 0)
  ImageDraw.Draw(m).rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), r * SS, fill=255)
  return m.resize((w, h), Image.LANCZOS)


def ring_mask(w, h, r, bw):
  m = Image.new('L', (w * SS, h * SS), 0)
  d = ImageDraw.Draw(m)
  d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), r * SS, fill=255)
  d.rounded_rectangle((bw * SS, bw * SS, (w - bw) * SS - 1, (h - bw) * SS - 1), max(r - bw, 0) * SS, fill=0)
  return m.resize((w, h), Image.LANCZOS)


def shadow(canvas, box, r, off=8, blur=14, alpha=200):
  x, y, w, h = box
  pad = blur * 3
  lay = Image.new('L', (w + pad * 2, h + pad * 2), 0)
  ImageDraw.Draw(lay).rounded_rectangle((pad, pad, pad + w, pad + h), r, fill=alpha)
  lay = lay.filter(ImageFilter.GaussianBlur(blur))
  canvas.paste(Image.new('RGB', lay.size, (0, 0, 0)), (x - pad, y - pad + off), lay)


def gold_frame(canvas, box, r, bw=2):
  x, y, w, h = box
  canvas.paste(metal(w, h, horizontal=True), (x, y), ring_mask(w, h, r, bw))


# ---------- พื้นหลัง ----------

def background():
  yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
  # เทาถ่าน แสงนุ่มจากกลางล่าง (ใต้รูปหลัก) ขอบมืด
  d = np.sqrt(((xx - W * 0.5) / W) ** 2 + ((yy - H * 0.72) / H) ** 2)
  t = np.clip(1 - d / 0.75, 0, 1) ** 1.5
  img = np.array(BG_DARK, np.float32) + (np.array(BG_LIGHT, np.float32) - np.array(BG_DARK, np.float32)) * t[..., None]
  # เกรนละเอียดกันแถบสี
  rng = np.random.default_rng(131)
  img += rng.normal(0, 1.4, (H, W, 1)).astype(np.float32)
  bg = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
  # เส้นทแยงทองบางๆ มุมขวาล่าง (โมเดิร์น) อยู่ใต้บรรทัดติดต่อ ไม่ทับข้อความ
  lay = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
  dr = ImageDraw.Draw(lay)
  for k in range(4):
    a = int(255 * (0.18 + 0.06 * k))
    off = k * 22
    dr.line(((W - 150 + off) * SS, H * SS, (W - 40 + off) * SS, (H - 110) * SS), fill=GOLD_MID + (a,), width=int(1.4 * SS))
  bg = bg.convert('RGBA')
  bg.alpha_composite(lay.resize((W, H), Image.LANCZOS))
  return bg.convert('RGB')


def hero_block(canvas, hero_h, fade0):
  im = grade(Image.open(os.path.join(IMG_DIR, HERO['file'])))
  if HERO.get('fit'):
    sw, sh = im.size
    c = HERO['crop']
    region = im.crop((int(c[0] * sw), int(c[1] * sh), int(c[2] * sw), int(c[3] * sh)))
    dw = int(round(region.size[0] * hero_h / region.size[1]))
    fg = region.resize((dw, hero_h), Image.LANCZOS)
    back = crop_cover(region, W, hero_h, {'crop': (0, 0, 1, 1), 'focus': (0.5, 0.5)})
    back = back.filter(ImageFilter.GaussianBlur(36))
    back = Image.fromarray((np.asarray(back).astype(np.float32) * 0.38).astype(np.uint8))
    feather = 90
    fa = np.ones(dw, np.float32)
    rmp = np.linspace(0, 1, feather)
    fa[:feather] = rmp * rmp * (3 - 2 * rmp)
    fa[dw - feather:] = fa[:feather][::-1]
    fm = Image.fromarray((fa * 255).astype(np.uint8)[None, :].repeat(hero_h, 0))
    back.paste(fg, ((W - dw) // 2, 0), fm)
    ph = back
  else:
    ph = crop_cover(im, W, hero_h, HERO)
  # ไล่จางลงสู่พื้นดำ (ล่าง) + มืดลงเล็กน้อยด้านบนให้โลโก้/รหัสเด่น
  a = np.ones(hero_h, np.float32)
  n = hero_h - fade0
  s = np.linspace(0, 1, n)
  a[fade0:] = 1 - (s * s * (3 - 2 * s))
  top = np.ones(hero_h, np.float32)
  tt = np.clip(np.arange(hero_h) / 220.0, 0, 1)
  top = 0.55 + 0.45 * (tt * tt * (3 - 2 * tt))
  arr = np.asarray(ph).astype(np.float32) * top[:, None, None]
  mask = Image.fromarray((a * 255).astype(np.uint8)[:, None].repeat(W, 1))
  canvas.paste(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)), (0, 0), mask)


def thumb(canvas, spec, box):
  x, y, w, h = box
  shadow(canvas, box, 12)
  im = grade(Image.open(os.path.join(IMG_DIR, spec['file'])))
  b = 2
  canvas.paste(crop_cover(im, w - 2 * b, h - 2 * b, spec), (x + b, y + b), rounded_mask(w - 2 * b, h - 2 * b, 10))
  gold_frame(canvas, box, 12, b)


def fade_rule(canvas, x0, x1, y, th=2, both=True):
  w = x1 - x0
  a = np.ones(w, np.float32)
  f = int(w * 0.3)
  a[w - f:] = np.linspace(1, 0, f)
  if both:
    a[:f] = np.linspace(0, 1, f)
  mask = Image.fromarray(np.tile((a * 235).astype(np.uint8)[None, :], (th, 1)))
  canvas.paste(metal(w, th, horizontal=True), (x0, y), mask)


# ---------- ไอคอน (วาดเอง: วงกลมดำขอบทอง เส้นทอง) ----------

def icon_circle(size, bw=2.5):
  S = size * SS
  im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
  d = ImageDraw.Draw(im)
  d.ellipse((0, 0, S - 1, S - 1), fill=GOLD_MID + (255,))
  b = int(bw * SS)
  d.ellipse((b, b, S - 1 - b, S - 1 - b), fill=(16, 16, 18, 255))
  return im, d, S


def finish(im, size):
  return im.resize((size, size), Image.LANCZOS)


def icon_spec(kind, size):
  im, d, S = icon_circle(size)
  g = GOLD_HI + (255,)
  lw = max(2, int(S * 0.045))
  u = S / 100.0
  if kind == 'bed':
    d.rounded_rectangle((26 * u, 36 * u, 32 * u, 70 * u), 2 * u, fill=g)          # หัวเตียง
    d.rounded_rectangle((26 * u, 52 * u, 76 * u, 62 * u), 3 * u, fill=g)          # ฟูก
    d.rounded_rectangle((35 * u, 43 * u, 50 * u, 51 * u), 3 * u, fill=g)          # หมอน
    d.rectangle((70 * u, 60 * u, 76 * u, 70 * u), fill=g)                         # ขาท้าย
  elif kind == 'bath':
    # ฝักบัว (ห้องนี้มีฝักบัว ไม่มีอ่าง): ท่อแนวตั้ง แขนท่อ หัวฝักบัว และสายน้ำ
    d.line((34 * u, 78 * u, 34 * u, 28 * u), fill=g, width=lw)                    # ท่อตั้ง
    d.arc((34 * u - 0, 22 * u, 46 * u, 34 * u), 180, 270, fill=g, width=lw)
    d.line((40 * u, 22 * u, 56 * u, 22 * u), fill=g, width=lw)                    # แขนท่อ
    d.line((58 * u, 22 * u, 58 * u, 32 * u), fill=g, width=lw)
    d.chord((44 * u, 30 * u, 72 * u, 58 * u), 180, 360, fill=g)                   # หัวฝักบัว
    d.rectangle((44 * u, 43 * u, 72 * u, 46 * u), fill=g)
    for k, xx in enumerate((48, 54, 60, 66)):                                     # สายน้ำ
      d.line((xx * u, (52 + (k % 2) * 3) * u, (xx - 2) * u, (62 + (k % 2) * 3) * u), fill=g, width=lw)
      d.line(((xx - 3) * u, (68 + (k % 2) * 3) * u, (xx - 4) * u, (72 + (k % 2) * 3) * u), fill=g, width=lw)
  elif kind == 'area':
    d.rectangle((30 * u, 30 * u, 70 * u, 70 * u), outline=g, width=lw)           # กรอบพื้นที่
    for (ax, ay, bx, by) in ((38, 62, 62, 38),):
      d.line((ax * u, ay * u, bx * u, by * u), fill=g, width=lw)
    d.polygon(((62 * u, 38 * u), (52 * u, 38 * u), (62 * u, 48 * u)), fill=g)    # หัวลูกศร
    d.polygon(((38 * u, 62 * u), (48 * u, 62 * u), (38 * u, 52 * u)), fill=g)
  elif kind == 'bldg':
    d.rectangle((34 * u, 24 * u, 66 * u, 76 * u), outline=g, width=lw)           # ตัวตึก
    for r in range(4):
      for c in range(2):
        x0 = (41 + c * 12) * u
        y0 = (31 + r * 10) * u
        d.rectangle((x0, y0, x0 + 6 * u, y0 + 5 * u), fill=g)
    d.rectangle((46 * u, 70 * u, 54 * u, 76 * u), fill=g)                         # ประตู
  return finish(im, size)


def icon_phone(size):
  im, d, S = icon_circle(size)
  c = S * 0.5
  rr = S * 0.24
  wdt = int(S * 0.11)
  cx, cy = c + S * 0.06, c - S * 0.06
  for ang0, ang1 in ((45, 225),):
    d.arc((cx - rr, cy - rr, cx + rr, cy + rr), ang0, ang1, fill=GOLD_HI + (255,), width=wdt)
    for ang in (ang0, ang1):
      ex = cx + (rr - wdt / 2) * math.cos(math.radians(ang))
      ey = cy + (rr - wdt / 2) * math.sin(math.radians(ang))
      er = S * 0.1
      d.ellipse((ex - er, ey - er, ex + er, ey + er), fill=GOLD_HI + (255,))
  return finish(im, size)


def icon_line(size):
  # ตัวอักษร "LINE" เรียบๆ (ไม่ใช่โลโก้ทางการ)
  im, d, S = icon_circle(size)
  f = ImageFont.truetype(TTC, int(S * 0.27), index=FONT_IDX['bold'])
  bb = d.textbbox((0, 0), 'LINE', font=f)
  tw, th = bb[2] - bb[0], bb[3] - bb[1]
  d.text(((S - tw) / 2 - bb[0], (S - th) / 2 - bb[1]), 'LINE', font=f, fill=GOLD_HI + (255,))
  return finish(im, size)


# ---------- ข้อความ (ffmpeg drawtext) ----------

class Texts:
  def __init__(self, tmp):
    self.tmp = tmp
    self.plain = []
    self.gold = []
    self.bands = []
    self.fonts = {}
    self.n = 0
    from fontTools.ttLib import TTCollection
    col = TTCollection(TTC)
    for k, i in FONT_IDX.items():
      p = os.path.join(tmp, k + '.ttf')
      col.fonts[i].save(p)
      self.fonts[k] = p

  def width(self, text, size, weight):
    # ประมาณความกว้างด้วย Pillow (ใช้จัดตำแหน่ง/ย่อขนาด) ตำแหน่งจริงคำนวณใน drawtext
    return ImageFont.truetype(TTC, size, index=FONT_IDX[weight]).getlength(text)

  def add(self, text, size, weight, color, x, baseline, align='left', shadow=False):
    p = os.path.join(self.tmp, 't%02d.txt' % self.n)
    self.n += 1
    with open(p, 'w', encoding='utf-8') as f:
      f.write(text)
    xe = {'center': '%d-text_w/2', 'right': '%d-text_w'}.get(align, '%d') % round(x)
    base = "drawtext=fontfile='%s':textfile='%s':fontsize=%d:x=%s:y=%d:y_align=baseline" % (
      self.fonts[weight], p, size, xe, round(baseline))
    if color == 'gold':
      if shadow:
        self.plain.append(base + ':fontcolor=black@0.75:shadowx=0:shadowy=0'.replace(':x=', ':x=3+').replace(':y=', ':y=4+'))
      self.gold.append(base + ':fontcolor=white')
      self.bands.append((baseline - size * 0.98, baseline + size * 0.32))
    else:
      extra = ':shadowx=2:shadowy=3:shadowcolor=black@0.7' if shadow else ''
      self.plain.append(base + ':fontcolor=0x%s%s' % (color, extra))

  def _run(self, src, items, out):
    fs = os.path.join(self.tmp, 'f%d.txt' % self.n)
    self.n += 1
    with open(fs, 'w', encoding='utf-8') as f:
      f.write('[0:v]' + (','.join(items) if items else 'null') + '[v]')
    subprocess.run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-i', src,
                    '-/filter_complex', fs, '-map', '[v]', '-frames:v', '1', out], check=True)

  def render(self, canvas):
    base = os.path.join(self.tmp, 'base.png')
    canvas.save(base)
    out = os.path.join(self.tmp, 'plain.png')
    self._run(base, self.plain, out)
    res = Image.open(out).convert('RGB')
    if self.gold:
      blank = os.path.join(self.tmp, 'blank.png')
      Image.new('RGB', (W, H), (0, 0, 0)).save(blank)
      mp = os.path.join(self.tmp, 'mask.png')
      self._run(blank, self.gold, mp)
      mask = Image.open(mp).convert('L')
      # เกรเดียนต์ทองต่อบรรทัด (แถบแนวตั้งตามขนาดตัวอักษร)
      gold = Image.new('RGB', (W, H), GOLD_MID)
      for (y0, y1) in self.bands:
        y0, y1 = max(0, int(y0)), min(H, int(math.ceil(y1)))
        gold.paste(metal(W, y1 - y0), (0, y0))
      res.paste(gold, (0, 0), mask)
    return res


def fit_size(tx, text, size, weight, maxw, minsize):
  while size > minsize and tx.width(text, size, weight) > maxw:
    size -= 1
  return size


# ---------- ประกอบภาพ ----------

def main():
  tmp = tempfile.mkdtemp(prefix='photo_', dir=os.environ.get('PHOTO_TMP'))
  try:
    tx = Texts(tmp)
    cv = background()

    # รูปหลักเต็มความกว้างครึ่งบน ไล่จางลงสู่พื้นดำ
    hero_h, fade0 = 680, 500
    hero_block(cv, hero_h, fade0)

    # หัวภาพ: โลโก้ซ้ายบน รหัสในแคปซูลขอบทองขวาบน
    logo = Image.open(LOGO).convert('RGBA').resize((120, 120), Image.LANCZOS)
    # โลโก้และแคปซูลรหัสห่างขอบบน 5% (y 68)
    shadow(cv, (M, 68, 120, 120), 60, off=4, blur=10, alpha=170)
    cv.paste(logo, (M, 68), logo)
    cs = 32
    code = code_label(TXT['code'])
    cw = int(tx.width(code, cs, 'bold')) + 52
    ch = 54
    cx0 = W - M - cw
    cv.paste(Image.new('RGB', (cw, ch), (12, 12, 14)), (cx0, 68), rounded_mask(cw, ch, ch // 2))
    gold_frame(cv, (cx0, 68, cw, ch), ch // 2, 2)
    tx.add(code, cs, 'bold', WHITE, cx0 + cw / 2, 68 + ch / 2 + cs * 0.36, 'center')

    # ป้าย "ให้เช่า" (แคปซูลทองทึบ) + ชื่อโครงการทองไล่เฉด ทับส่วนที่จางของรูปหลัก
    ds = 30
    dw = int(tx.width(TXT['deal'], ds, 'bold')) + 44
    dy = 504
    cv.paste(metal(dw, 46, horizontal=True), (M, dy), rounded_mask(dw, 46, 23))
    tx.add(TXT['deal'], ds, 'bold', INK, M + dw / 2, dy + 23 + ds * 0.36, 'center')
    ts = fit_size(tx, TXT['title'], 62, 'bold', W - 2 * M, 40)
    tx.add(TXT['title'], ts, 'bold', 'gold', M, 620, shadow=True)
    fade_rule(cv, M, W - M, 646, 2, both=False)

    # รูปเล็ก 3 รูปเรียงแถว
    gap = 18
    tw = (W - 2 * M - 2 * gap) // 3
    ty, th = 664, 168
    for i, spec in enumerate(THUMBS):
      thumb(cv, spec, (M + i * (tw + gap), ty, tw, th))

    # แถวไอคอนสเปก
    isz = 78
    iy = 852
    colw = (W - 2 * M) / 4
    for i, (kind, label) in enumerate(TXT['specs']):
      cx = M + colw * (i + 0.5)
      ic = icon_spec(kind, isz)
      cv.paste(ic, (int(cx - isz / 2), iy), ic)
      ls = fit_size(tx, label, 30, 'bold', colw - 12, 24)
      tx.add(label, ls, 'bold', WHITE, cx, iy + isz + 40, 'center')
    # เส้นคั่นแนวตั้งบางระหว่างคอลัมน์
    for i in range(1, 4):
      x = int(M + colw * i)
      m = np.concatenate([np.linspace(0, 1, 30), np.ones(50), np.linspace(1, 0, 30)])
      cv.paste(metal(1, len(m)), (x, iy + 8), Image.fromarray((m * 120).astype(np.uint8)[:, None]))

    # เฟอร์นิเจอร์
    fs = 28
    tx.add(TXT['furnished'], fs, 'regular', SOFT, W / 2, 1014, 'center')

    # กล่องราคา ขอบทอง
    bx, by, bw, bh = M + 60, 1034, W - 2 * M - 120, 104
    shadow(cv, (bx, by, bw, bh), 16, off=6, blur=12, alpha=200)
    cv.paste(Image.new('RGB', (bw, bh), (14, 14, 16)), (bx, by), rounded_mask(bw, bh, 16))
    gold_frame(cv, (bx, by, bw, bh), 16, 3)
    lab, num, unit = TXT['price']
    s1, s2, s3 = 32, 72, 32
    sp = tx.width(' ', s1, 'regular')
    w1, w2, w3 = tx.width(lab, s1, 'regular'), tx.width(num, s2, 'bold'), tx.width(unit, s1, 'regular')
    total = w1 + w2 + w3 + 2 * sp * 1.6
    x0 = W / 2 - total / 2
    base_y = by + bh / 2 + s2 * 0.36
    tx.add(lab, s1, 'regular', WHITE, x0, base_y)
    tx.add(num, s2, 'bold', 'gold', x0 + w1 + sp * 1.6, base_y)
    tx.add(unit, s3, 'regular', WHITE, x0 + w1 + w2 + sp * 3.2, base_y)

    # ช่องทางติดต่อ
    fade_rule(cv, M, W - M, 1160, 1)
    rowy = 1176
    icz = 54
    colw2 = (W - 2 * M) / 2
    for i, (txt, ic) in enumerate(((TXT['tel'], icon_phone), (TXT['line'], icon_line))):
      cx = M + colw2 * (i + 0.5)
      sz = fit_size(tx, txt, 36, 'bold', colw2 - icz - 30, 32)
      tw2 = tx.width(txt, sz, 'bold')
      gx = cx - (icz + 14 + tw2) / 2
      ico = ic(icz)
      cv.paste(ico, (int(gx), rowy), ico)
      tx.add(txt, sz, 'bold', WHITE, gx + icz + 14, rowy + icz / 2 + sz * 0.36)
    # WhatsApp / Email: หัวข้อทอง ค่าเป็นสีขาว บรรทัดเดียวกัน
    sz = 32
    parts = []
    for c in (TXT['whatsapp'], TXT['email']):
      l, v = c.split(': ', 1)
      parts.append((l + ':', v))
    sp = tx.width(' ', sz, 'regular')
    sep = 40
    widths = [tx.width(l, sz, 'bold') + sp + tx.width(v, sz, 'regular') for l, v in parts]
    total = sum(widths) + sep
    if total > W - 2 * M:
      sys.exit('WhatsApp/Email ยาวเกินบรรทัด (%d)' % total)
    x = W / 2 - total / 2
    yb = 1276
    for (l, v), wd in zip(parts, widths):
      tx.add(l, sz, 'bold', 'gold', x, yb)
      tx.add(v, sz, 'regular', WHITE, x + tx.width(l, sz, 'bold') + sp, yb)
      x += wd + sep
    # จุดคั่นทอง
    dx = W / 2 - total / 2 + widths[0] + sep / 2
    dd = ImageDraw.Draw(cv)
    dd.ellipse((dx - 3, yb - 14, dx + 3, yb - 8), fill=GOLD_MID)

    res = tx.render(cv)
    os.makedirs(OUT_DIR, exist_ok=True)
    kw = {'quality': 92, 'subsampling': 0, 'optimize': True}
    try:
      from PIL import ImageCms
      kw['icc_profile'] = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    except Exception:
      pass
    res.save(OUT, 'JPEG', **kw)
    print('wrote', OUT, res.size)
  finally:
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
  main()
