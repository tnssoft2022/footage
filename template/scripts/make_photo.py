#!/usr/bin/env python3
# ภาพรวม (photo) สไตล์ Uptown — ต้นแบบ คัดลอกไปที่ work/<รหัส>/make_photo.py
# ใช้: <venv>/bin/python make_photo.py <ffmpeg-path>
# อ่านรูป ข้อความ และค่าครอปจาก timeline.json (ไม่ hard-code ข้อความ)
# มีหลายเลย์เอาต์ เลือกอัตโนมัติตามจำนวนรูปและแนวรูป (ดู LAYOUTS / choose_layout)
# Pillow ในเครื่องไม่มี libraqm -> ข้อความทั้งหมดวาดด้วย ffmpeg drawtext (harfbuzz) ผ่าน fontfile=/textfile=
import hashlib, json, math, os, shutil, subprocess, sys, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
TIMELINE = os.environ.get('PHOTO_TIMELINE') or os.path.join(HERE, 'timeline.json')
LOGO = os.path.join(ROOT, 'global', 'logo.png')
OUT_DIR = os.environ.get('PHOTO_OUT_DIR') or os.path.join(HERE, 'photo')
OUT = os.path.join(OUT_DIR, 'photo.jpg')
TTC = '/System/Library/Fonts/Supplemental/SukhumvitSet.ttc'
FONT_IDX = {'bold': 5, 'regular': 2}
FFMPEG = sys.argv[1] if len(sys.argv) > 1 else '/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg'

W, H = 1080, 1350
M = 54  # ระยะขอบ 5%
SS = 3  # supersample สำหรับรูปทรงโค้ง

# สี Uptown
GOLD = (226, 196, 138)
GOLD_D = (201, 168, 106)
CREAM = (254, 248, 240)
RED_EDGE = (75, 10, 15)
RED_LIGHT = (122, 20, 36)
SHADOW = (34, 3, 6)
ICON_RED = (110, 16, 29)
TXT_SPEC = '5A0C14'
TXT_SUB = '8C3A42'
TXT_PRICE = '7A1424'
TXT_GOLD = 'E2C48A'
TXT_CREAM = 'FEF8F0'

# ---- ค่าที่ photo agent ตั้งได้ต่องาน (ปล่อย None = เลือกอัตโนมัติ) ----
# LAYOUT: ชื่อเลย์เอาต์ใน LAYOUTS (หรือ env PHOTO_LAYOUT) ถ้า None เลือกตามรูปด้วย choose_layout()
LAYOUT = None
# IMAGES: ลำดับรูปที่ต้องการ [รูปหลัก, รูปรอง...] ถ้า None ใช้ลำดับช็อตใน timeline (ช็อตแรก = รูปหลัก)
#   รูปรองจะถูกจับคู่กับช่องตามแนวรูป (รูปแนวตั้งลงช่องแนวตั้งก่อน)
IMAGES = None
# focus = จุดกึ่งกลางที่ต้องการ (สัดส่วนของรูป) ถ้า shot ใน timeline มี crop/focus จะใช้ค่าจาก timeline ก่อน
FOCUS_HINT = {}

# ---- เลย์เอาต์: ช่องรูปในพื้นที่ (x, y, w, h) เป็นสัดส่วนของพื้นที่รูป ช่องแรก = รูปหลัก ----
# พื้นที่รูป = กว้างเต็ม (ขอบ 5%) อยู่ระหว่างหัวภาพกับแผงข้อมูล (สูงราว 640-680px)
# need = จำนวนรูปขั้นต่ำ, hero = แนวรูปหลักที่เหมาะ ('land' / 'port' / None = ได้ทั้งคู่)
LAYOUTS = {
  # รูปหลักเต็มกว้าง + รูปรอง 3 รูปเรียงแถว (แบบเดิม)
  'hero3': {'need': 4, 'hero': 'land', 'slots': lambda w, h, g: [
    (0, 0, w, h - 220 - g)] + [(i * ((w - 2 * g) // 3 + g), h - 220, (w - 2 * g) // 3, 220) for i in range(3)]},
  # รูปหลักเต็มกว้าง + รูปรอง 2 รูปใหญ่
  'hero2': {'need': 3, 'hero': 'land', 'slots': lambda w, h, g: [
    (0, 0, w, h - 260 - g), (0, h - 260, (w - g) // 2, 260), ((w - g) // 2 + g, h - 260, (w - g) // 2, 260)]},
  # ตาราง 2x2 เท่ากัน
  'grid4': {'need': 4, 'hero': None, 'slots': lambda w, h, g: [
    (0, 0, (w - g) // 2, (h - g) // 2), ((w - g) // 2 + g, 0, (w - g) // 2, (h - g) // 2),
    (0, (h - g) // 2 + g, (w - g) // 2, (h - g) // 2), ((w - g) // 2 + g, (h - g) // 2 + g, (w - g) // 2, (h - g) // 2)]},
  # ซ้าย: รูปหลักแนวนอน + รูปแนวนอนเล็กด้านล่าง / ขวา: รูปแนวตั้งสูงเต็ม (เหมาะกับชุดที่มีรูปแนวตั้ง)
  'trio': {'need': 3, 'hero': 'land', 'slots': lambda w, h, g: [
    (0, 0, w - 360 - g, int(h * 0.6)), (0, int(h * 0.6) + g, w - 360 - g, h - int(h * 0.6) - g), (w - 360, 0, 360, h)]},
  # ซ้าย: รูปหลักแนวตั้งสูงเต็ม / ขวา: รูปรอง 2 รูปซ้อน
  'side': {'need': 3, 'hero': 'port', 'slots': lambda w, h, g: [
    (0, 0, int(w * 0.56), h), (int(w * 0.56) + g, 0, w - int(w * 0.56) - g, (h - g) // 2),
    (int(w * 0.56) + g, (h - g) // 2 + g, w - int(w * 0.56) - g, (h - g) // 2)]},
  # รูปแนวตั้ง 2 รูปคู่กันสูงเต็ม
  'duo': {'need': 2, 'hero': 'port', 'slots': lambda w, h, g: [
    (0, 0, (w - g) // 2, h), ((w - g) // 2 + g, 0, (w - g) // 2, h)]},
  # รูปหลักแนวนอนใหญ่ + รูปแนวนอนอีกรูปด้านล่าง (งานที่มี 2 รูป)
  'stack': {'need': 2, 'hero': 'land', 'slots': lambda w, h, g: [
    (0, 0, w, int(h * 0.6)), (0, int(h * 0.6) + g, w, h - int(h * 0.6) - g)]},
  # รูปเดียวเต็มพื้นที่ (งานที่มีรูปน้อยมาก)
  'single': {'need': 1, 'hero': None, 'slots': lambda w, h, g: [(0, 0, w, h)]},
}


def lerp(a, b, t):
  return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def load_timeline():
  with open(TIMELINE, encoding='utf-8') as f:
    return json.load(f)


def texts_by_role(tl):
  # ดึงข้อความตามทุกตัวอักษรจาก timeline
  # อ่านตาม role ไม่ใช่ตามลำดับบรรทัด: ป้าย "ภาพห้องตัวอย่าง" แยกออกก่อน
  # (มักใช้ role code ซ้ำกับรหัส) และราคาหาจากบรรทัด role price
  t = {x['id']: x for x in tl['texts']}
  is_label = lambda l: 'ภาพห้องตัวอย่าง' in l['text']
  labels = []
  for x in tl['texts']:
    for l in x['lines']:
      if is_label(l) and l['text'] not in labels:
        labels.append(l['text'])
  open_lines = {}
  for l in t['open']['lines']:
    if not is_label(l):
      open_lines.setdefault(l['role'], l['text'])
  specs, floor = [], []
  if 'specs' in t:
    for l in t['specs']['lines']:
      if is_label(l) or l['role'] == 'price':
        continue
      (specs if l['role'] == 'title' or not specs else floor).append(l['text'])
  if 'floor' in t:
    floor += [l['text'] for l in t['floor']['lines'] if not is_label(l)]
  price = None
  for x in tl['texts']:
    if x['id'] == 'end':
      continue
    for l in x['lines']:
      if l['role'] == 'price' and price is None:
        price = l['text']
      elif x['id'] == 'price' and not is_label(l) and l['text'] not in floor:
        floor.append(l['text'])
  if price is None:
    price = next((l['text'] for l in t['end']['lines'] if l['role'] == 'price'), None)
  # กลุ่มอื่น (เช่น location, furnished) เป็นบรรทัดเสริมในแผงข้อมูล
  extras = []
  for x in tl['texts']:
    if x['id'] in ('open', 'specs', 'floor', 'price', 'end'):
      continue
    for l in x['lines']:
      if not is_label(l) and l['role'] != 'price' and l['text'] not in extras:
        extras.append(l['text'])
  return {
    'extras': extras,
    'code': str(tl['code']) if tl.get('code') else open_lines['code'],
    'title': open_lines['title'],
    'sub': open_lines.get('sub'),
    'specs': specs,
    'floor': floor,
    'price': price,
    'contacts': [l['text'] for l in t['end']['lines'] if l['role'] == 'contact'],
    'labels': labels,
  }


# ---------- รูป ----------

def grade(im):
  # โทนอุ่นเล็กน้อย (ใกล้เคียง colorbalance rs=.03 bs=-.03 + eq contrast 1.04) ไม่ดันขาวโพลน
  a = np.asarray(im.convert('RGB')).astype(np.float32) / 255.0
  a = (a - 0.5) * 1.04 + 0.5
  a[..., 0] = a[..., 0] * 1.025 + 0.004
  a[..., 1] = a[..., 1] * 1.005
  a[..., 2] = a[..., 2] * 0.965
  a = np.clip(a, 0, 0.985)
  return Image.fromarray((a * 255 + 0.5).astype(np.uint8))


def focus_from(name):
  f = {'top-right': (1.0, 0.0), 'top-left': (0.0, 0.0), 'center': (0.5, 0.5),
       'bottom-right': (1.0, 1.0), 'bottom-left': (0.0, 1.0), 'top': (0.5, 0.0), 'bottom': (0.5, 1.0)}
  return f.get(name, (0.5, 0.5))


def crop_cover(im, w, h, shot):
  sw, sh = im.size
  # พื้นที่ที่อนุญาต: ใช้ crop ของ timeline ถ้ามี เพื่อไม่ให้สิ่งที่ตั้งใจตัดกลับมา
  if 'crop' in shot:
    c = shot['crop']
    rx0, ry0, rx1, ry1 = c['x0'] * sw, c['y0'] * sh, c['x1'] * sw, c['y1'] * sh
    fx, fy = focus_from(shot.get('focus', 'center'))
  else:
    rx0, ry0, rx1, ry1 = 0, 0, sw, sh
    fx, fy = FOCUS_HINT.get(shot['file'], (0.5, 0.5))
  rw, rh = rx1 - rx0, ry1 - ry0
  ar = w / h
  if rw / rh > ar:
    ch, cw = rh, rh * ar
  else:
    cw, ch = rw, rw / ar
  if 'crop' in shot:
    x0 = rx0 + (rw - cw) * fx
    y0 = ry0 + (rh - ch) * fy
  else:
    x0 = min(max(fx * sw - cw / 2, rx0), rx1 - cw)
    y0 = min(max(fy * sh - ch / 2, ry0), ry1 - ch)
  return im.resize((w, h), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))


def rounded_mask(w, h, r):
  m = Image.new('L', (w * SS, h * SS), 0)
  ImageDraw.Draw(m).rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), r * SS, fill=255)
  return m.resize((w, h), Image.LANCZOS)


def gold_gradient(w, h):
  x = np.linspace(0, 1, w)[None, :]
  y = np.linspace(0, 1, h)[:, None]
  t = (x * 0.7 + y * 0.3)
  t = 0.5 - 0.5 * np.cos(t * 2 * math.pi)  # D -> L -> D
  a = np.array(GOLD_D, np.float32)
  b = np.array(GOLD, np.float32)
  g = a + (b - a) * t[..., None]
  return Image.fromarray(g.astype(np.uint8))


def drop_shadow(canvas, box, r, off=8, blur=12, alpha=170):
  x, y, w, h = box
  pad = blur * 3
  lay = Image.new('L', (w + pad * 2, h + pad * 2), 0)
  ImageDraw.Draw(lay).rounded_rectangle((pad, pad, pad + w, pad + h), r, fill=alpha)
  lay = lay.filter(ImageFilter.GaussianBlur(blur))
  col = Image.new('RGB', lay.size, SHADOW)
  canvas.paste(col, (x - pad, y - pad + off), lay)


def place_photo(canvas, im, box, border=3, r=14):
  x, y, w, h = box
  drop_shadow(canvas, box, r)
  canvas.paste(gold_gradient(w, h), (x, y), rounded_mask(w, h, r))
  iw, ih = w - border * 2, h - border * 2
  canvas.paste(im.resize((iw, ih), Image.LANCZOS) if im.size != (iw, ih) else im,
               (x + border, y + border), rounded_mask(iw, ih, r - border))


# ---------- พื้นหลัง ----------

def background():
  yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
  # แสงจากขวาบน
  lx, ly = W * 0.88, H * 0.08
  d = np.sqrt((xx - lx) ** 2 + (yy - ly) ** 2) / math.hypot(W, H)
  t = np.clip(1 - d / 0.95, 0, 1) ** 1.6
  e = np.array(RED_EDGE, np.float32)
  l = np.array(RED_LIGHT, np.float32)
  img = e + (l - e) * t[..., None]
  # ลายผ้าไหมทแยงจางๆ
  rng = np.random.default_rng(17)
  n = rng.normal(0, 1, (H // 6 + 2, W // 6 + 2)).astype(np.float32)
  n = np.asarray(Image.fromarray(((n * 40) + 128).clip(0, 255).astype(np.uint8)).resize((W * 2, H * 2), Image.BICUBIC)).astype(np.float32)[:H, :W]
  silk = np.sin((xx + yy) * 0.9 + (n - 128) / 18.0) * 0.5 + np.sin((xx + yy) * 0.13) * 0.5
  img *= (1 + 0.035 * silk)[..., None]
  # vignette
  cx, cy = W / 2, H / 2
  v = np.sqrt(((xx - cx) / (W * 0.62)) ** 2 + ((yy - cy) / (H * 0.62)) ** 2)
  img *= (1 - 0.32 * np.clip(v - 0.55, 0, 1) ** 1.4)[..., None]
  bg = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
  # เส้นคลื่นทองบางๆ ด้านล่าง
  lay = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
  dr = ImageDraw.Draw(lay)
  for k in range(5):
    base = (1180 + k * 26) * SS
    amp = (16 + k * 4) * SS
    ph = k * 0.7
    alpha = int(255 * (0.15 + 0.03 * k))  # 15%-27%
    pts = []
    for px in range(-20, W + 21, 6):
      yv = base + amp * math.sin(px / W * 2 * math.pi * 1.15 + ph) + amp * 0.35 * math.sin(px / W * 2 * math.pi * 2.7 + ph * 2)
      pts.append((px * SS, yv))
    dr.line(pts, fill=GOLD + (alpha,), width=int(1.6 * SS), joint='curve')
  lay = lay.resize((W, H), Image.LANCZOS)
  bg = bg.convert('RGBA')
  bg.alpha_composite(lay)
  return bg.convert('RGB')


def fade_line(canvas, x0, x1, y, th=2):
  w = x1 - x0
  a = np.ones(w, np.float32)
  fade = int(w * 0.45)
  a[w - fade:] = np.linspace(1, 0, fade)
  a[:20] = np.linspace(0.3, 1, 20)
  mask = Image.fromarray(np.tile((a * 230).astype(np.uint8)[None, :], (th, 1)))
  canvas.paste(gold_gradient(w, th), (x0, y), mask)


# ---------- แคปซูล ไอคอน ----------

def capsule(canvas, box, fill, border_w=2):
  x, y, w, h = box
  r = h // 2
  canvas.paste(gold_gradient(w, h), (x, y), rounded_mask(w, h, r))
  iw, ih = w - border_w * 2, h - border_w * 2
  canvas.paste(Image.new('RGB', (iw, ih), fill), (x + border_w, y + border_w), rounded_mask(iw, ih, r - border_w))


def icon_base(size):
  S = size * SS
  im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
  d = ImageDraw.Draw(im)
  d.ellipse((0, 0, S - 1, S - 1), fill=GOLD + (255,))
  b = int(2.5 * SS)
  d.ellipse((b, b, S - 1 - b, S - 1 - b), fill=ICON_RED + (255,))
  return im, d, S


def icon_phone(size):
  im, d, S = icon_base(size)
  # หูโทรศัพท์: โค้งหนา + ปลายสองด้าน
  c = S * 0.5
  rr = S * 0.24
  wdt = int(S * 0.11)
  cx, cy = c + S * 0.06, c - S * 0.06
  a0, a1 = 45, 225  # ปลายบนซ้าย (หูฟัง) / ล่างขวา (ปากพูด) โค้งไปทางซ้ายล่าง
  d.arc((cx - rr, cy - rr, cx + rr, cy + rr), a0, a1, fill=CREAM + (255,), width=wdt)
  for ang in (a0, a1):
    ex = cx + (rr - wdt / 2) * math.cos(math.radians(ang))
    ey = cy + (rr - wdt / 2) * math.sin(math.radians(ang))
    er = S * 0.1
    d.ellipse((ex - er, ey - er, ex + er, ey + er), fill=CREAM + (255,))
  return im.resize((size, size), Image.LANCZOS)


def icon_line(size):
  im, d, S = icon_base(size)
  f = ImageFont.truetype(TTC, int(S * 0.27), index=FONT_IDX['bold'])
  bb = d.textbbox((0, 0), 'LINE', font=f)
  tw, th = bb[2] - bb[0], bb[3] - bb[1]
  d.text(((S - tw) / 2 - bb[0], (S - th) / 2 - bb[1]), 'LINE', font=f, fill=CREAM + (255,))
  return im.resize((size, size), Image.LANCZOS)


# ---------- ข้อความ (ffmpeg drawtext) ----------

class Texts:
  def __init__(self, tmp):
    self.tmp = tmp
    self.items = []
    self.fonts = {}
    from fontTools.ttLib import TTCollection
    col = TTCollection(TTC)
    for k, i in FONT_IDX.items():
      p = os.path.join(tmp, k + '.ttf')
      col.fonts[i].save(p)
      self.fonts[k] = p

  def width(self, text, size, weight):
    # ประมาณความกว้างด้วย Pillow (basic layout) ใช้เพื่อจัดแคปซูล/ย่อขนาด ตำแหน่งจริงคำนวณใน drawtext
    return ImageFont.truetype(TTC, size, index=FONT_IDX[weight]).getlength(text)

  def add(self, text, size, weight, color, x, baseline, align='left'):
    p = os.path.join(self.tmp, 't%02d.txt' % len(self.items))
    with open(p, 'w', encoding='utf-8') as f:
      f.write(text)
    if align == 'center':
      xe = '%d-text_w/2' % round(x)
    elif align == 'right':
      xe = '%d-text_w' % round(x)
    else:
      xe = '%d' % round(x)
    self.items.append("drawtext=fontfile='%s':textfile='%s':fontsize=%d:fontcolor=0x%s:x=%s:y=%d:y_align=baseline"
                      % (self.fonts[weight], p, size, color, xe, round(baseline)))

  def render(self, base_png, out_png):
    fs = os.path.join(self.tmp, 'filter.txt')
    with open(fs, 'w', encoding='utf-8') as f:
      f.write('[0:v]' + ','.join(self.items) + '[v]')
    subprocess.run([FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-i', base_png,
                    '-/filter_complex', fs, '-map', '[v]', '-frames:v', '1', out_png], check=True)


def fit_size(tx, text, size, weight, maxw, minsize):
  while size > minsize and tx.width(text, size, weight) > maxw:
    size -= 1
  return size


# ---------- เลือกเลย์เอาต์และรูป ----------

def orient(path, shot):
  # แนวของส่วนที่ใช้ได้จริง (ถ้า shot มี crop ใช้ขนาดหลังครอป)
  w, h = Image.open(path).size
  c = shot.get('crop')
  if c:
    w, h = w * (c['x1'] - c['x0']), h * (c['y1'] - c['y0'])
  return 'port' if h > w * 1.05 else 'land'


def photo_list(tl):
  # รูปที่ใช้ได้ = รูปใน shots (ไม่นับการ์ดปิด) ไม่ซ้ำ ตามลำดับช็อต หรือตาม IMAGES ถ้าตั้งไว้
  shots = [s for s in tl['shots'] if s.get('kind', 'shot') != 'end' and not s.get('end')]
  files = []
  for s in shots:
    if s['file'] not in files:
      files.append(s['file'])
  if IMAGES:
    bad = [f for f in IMAGES if f not in files]
    if bad:
      sys.exit('รูป %s ไม่อยู่ใน shots ของ timeline' % ', '.join(bad))
    files = list(IMAGES)
  return files


def choose_layout(code, files, ori):
  # เลือกจากเลย์เอาต์ที่เข้ากับรูป แล้วสุ่มแบบคงที่ตามรหัส (รหัสเดิมได้แบบเดิมเสมอ งานต่างกันได้แบบต่างกัน)
  forced = os.environ.get('PHOTO_LAYOUT') or LAYOUT
  if forced:
    if forced not in LAYOUTS:
      sys.exit('ไม่มีเลย์เอาต์ %s (มี: %s)' % (forced, ', '.join(LAYOUTS)))
    return forced
  # นับแนวของรูปรอง: ช่องรูปรองแต่ละแบบต้องมีรูปแนวเดียวกันพอ ไม่งั้นต้องครอปเสียภาพเยอะ
  n = len(files)
  hero = ori[files[0]]
  ports = sum(1 for f in files[1:] if ori[f] == 'port')
  lands = n - 1 - ports
  cands = []
  if hero == 'port':
    if n >= 3:
      cands.append('side')
    if ports >= 1:
      cands.append('duo')
  else:
    if lands >= 1 and ports >= 1:
      cands.append('trio')
    if lands >= 2:
      cands.append('hero2')
    if lands >= 3:
      cands += ['hero3', 'grid4']
    if not cands and n >= 2:
      cands.append('stack')
  cands = [c for c in cands if LAYOUTS[c]['need'] <= n] or ['single']
  k = int(hashlib.md5(str(code).encode()).hexdigest(), 16) % len(cands)
  return cands[k]


def assign(files, ori, slots):
  # ช่องแรก = รูปหลัก ช่องที่เหลือจับคู่ตามแนว: ช่องแนวตั้งรับรูปแนวตั้งก่อน ช่องแนวนอนรับรูปแนวนอนก่อน
  # ถ้าตั้ง IMAGES ไว้ ใช้ตามลำดับนั้นตรงๆ (agent เลือกให้ครอบคลุมห้องต่างกันเอง)
  # ถ้าไม่ตั้ง: เลือกรูปที่อยู่ห่างจากรูปที่เลือกแล้วในลำดับช็อตมากที่สุด เพราะช็อตที่ติดกันมักเป็นห้องเดียวกัน
  if IMAGES:
    return files[:len(slots)]
  idx = {f: i for i, f in enumerate(files)}
  out = [files[0]]
  left = files[1:]
  for (_, _, w, h) in slots[1:]:
    if not left:
      break
    want = 'port' if h > w else 'land'
    pool = [f for f in left if ori[f] == want] or left
    pick = max(pool, key=lambda f: (min(abs(idx[f] - idx[o]) for o in out), -idx[f]))
    out.append(pick)
    left.remove(pick)
  return out


def main():
  tl = load_timeline()
  T = texts_by_role(tl)
  img_dir = tl['img_dir']
  if not os.path.isabs(img_dir):
    img_dir = os.path.join(ROOT, img_dir)
  by_file = {}
  for s in tl['shots']:
    by_file.setdefault(s['file'], s)
  files = photo_list(tl)
  ori = {f: orient(os.path.join(img_dir, f), by_file[f]) for f in files}
  layout = choose_layout(tl.get('code', T['code']), files, ori)
  # แผงข้อมูลยืดตามจำนวนบรรทัดเสริม ฐานแผงคงที่ที่ y 1084 พื้นที่รูปอยู่ระหว่างหัวภาพกับแผง
  extra_h = 38 * len(T['extras'])
  py = 904 - extra_h
  gap = 18
  ry0, ry1 = 208, py - gap
  slots = LAYOUTS[layout]['slots'](W - 2 * M, ry1 - ry0, gap)
  use = assign(files, ori, slots)
  slots = slots[:len(use)]
  print('layout', layout, 'images', use)
  tmp = tempfile.mkdtemp(prefix='photo_', dir=os.environ.get('PHOTO_TMP'))
  try:
    tx = Texts(tmp)
    cv = background()

    # หัวภาพ
    logo = Image.open(LOGO).convert('RGBA').resize((128, 128), Image.LANCZOS)
    cv.paste(logo, (M, 40), logo)
    tx0 = M + 128 + 24
    code_size = 30
    cw = int(tx.width(T['code'], code_size, 'regular')) + 48
    capsule(cv, (W - M - cw, 44, cw, 50), (92, 14, 24))
    tx.add(T['code'], code_size, 'regular', TXT_GOLD, W - M - cw / 2, 80, 'center')
    if T['sub']:
      tx.add(T['sub'], 32, 'regular', TXT_CREAM, tx0, 82)
    ts = fit_size(tx, T['title'], 52, 'bold', W - M - tx0, 36)
    tx.add(T['title'], ts, 'bold', TXT_GOLD, tx0, 150)
    fade_line(cv, M, W - M, 190, 2)

    # รูป
    for (sx, sy, sw, sh), f in zip(slots, use):
      box = (M + sx, ry0 + sy, sw, sh)
      im = grade(Image.open(os.path.join(img_dir, f)))
      place_photo(cv, crop_cover(im, box[2] - 6, box[3] - 6, by_file[f]), box)
    hx, hy, hw, hh = slots[0]
    for lab in T['labels']:
      # ป้ายแคปซูลมุมขวาล่างของรูปหลัก
      lw = int(tx.width(lab, 24, 'regular')) + 32
      lx, ly = M + hx + hw - 14 - lw, ry0 + hy + hh - 14 - 40
      capsule(cv, (lx, ly, lw, 40), (92, 14, 24))
      tx.add(lab, 24, 'regular', TXT_CREAM, lx + lw / 2, ly + 28, 'center')

    # แผงข้อมูล
    px, pw, ph = M, W - 2 * M, 180 + extra_h
    drop_shadow(cv, (px, py, pw, ph), 22, off=6, blur=10, alpha=150)
    capsule_like = rounded_mask(pw, ph, 22)
    cv.paste(gold_gradient(pw, ph), (px, py), capsule_like)
    cv.paste(Image.new('RGB', (pw - 4, ph - 4), CREAM), (px + 2, py + 2), rounded_mask(pw - 4, ph - 4, 20))
    spec = ' '.join(T['specs'])
    tx.add(spec, 36, 'bold', TXT_SPEC, px + 36, py + 56)
    if T['floor']:
      tx.add(' '.join(T['floor']), 32, 'regular', TXT_SUB, px + pw - 36, py + 56, 'right')
    for i, e in enumerate(T['extras']):
      es = fit_size(tx, e, 30, 'regular', pw - 72, 24)
      tx.add(e, es, 'regular', TXT_SUB, px + 36, py + 56 + 40 * (i + 1))
    rl = Image.new('L', (pw - 72, 2), 0)
    ra = np.concatenate([np.linspace(0, 1, 60), np.ones(pw - 72 - 120), np.linspace(1, 0, 60)])
    rl = Image.fromarray(np.tile((ra * 255).astype(np.uint8)[None, :], (2, 1)))
    cv.paste(gold_gradient(pw - 72, 2), (px + 36, py + 80 + extra_h), rl)
    ps = fit_size(tx, T['price'], 58, 'bold', pw - 72, 40)
    tx.add(T['price'], ps, 'bold', TXT_PRICE, W / 2, py + 152 + extra_h, 'center')

    # ช่องทางติดต่อ
    contacts = T['contacts']
    tel = next(c for c in contacts if c.startswith('โทร'))
    line = next(c for c in contacts if c.lower().startswith('line'))
    rest = [c for c in contacts if c not in (tel, line)]
    cy, chh = 1102, 74
    cw2 = (W - 2 * M - gap) // 2
    for i, (txt, ic) in enumerate(((tel, icon_phone), (line, icon_line))):
      x = M + i * (cw2 + gap)
      capsule(cv, (x, cy, cw2, chh), CREAM)
      isz = 56
      ico = ic(isz)
      cv.paste(ico, (x + 10, cy + (chh - isz) // 2), ico)
      area0 = x + 10 + isz + 12
      area1 = x + cw2 - 22
      fs = fit_size(tx, txt, 36, 'bold', area1 - area0, 32)
      tx.add(txt, fs, 'bold', TXT_SPEC, (area0 + area1) / 2, cy + chh / 2 + fs * 0.36, 'center')
    by = 1222
    for c in rest:
      if ': ' in c:
        lab, val = c.split(': ', 1)
        lab += ':'
      else:
        lab, val = '', c
      sz = 32
      sp = tx.width(' ', sz, 'regular')
      lw = tx.width(lab, sz, 'bold')
      vw = tx.width(val, sz, 'regular')
      x0 = W / 2 - (lw + sp + vw) / 2
      if lab:
        tx.add(lab, sz, 'bold', TXT_GOLD, x0, by)
      tx.add(val, sz, 'regular', TXT_CREAM, x0 + lw + sp, by)
      by += 46

    os.makedirs(OUT_DIR, exist_ok=True)
    base = os.path.join(tmp, 'base.png')
    cv.save(base)
    outp = os.path.join(tmp, 'out.png')
    tx.render(base, outp)
    res = Image.open(outp).convert('RGB')
    icc = None
    try:
      from PIL import ImageCms
      icc = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    except Exception:
      pass
    kw = {'quality': 92, 'subsampling': 0, 'optimize': True}
    if icc:
      kw['icc_profile'] = icc
    res.save(OUT, 'JPEG', **kw)
    print('wrote', OUT, res.size, 'layout', layout)
  finally:
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
  main()
