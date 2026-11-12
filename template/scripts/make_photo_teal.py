#!/usr/bin/env python3
# ภาพรวม (photo) สไตล์ "เขียวหัวเป็ด/ขาว" (teal & white) — สไตล์พื้นสว่างโทนเย็น
# แรงบันดาลใจจาก template/photo/02.jpeg (ใช้แค่โทนสีและแนวเลย์เอาต์ ไม่คัดลอกแบรนด์หรือภาพ)
# เลย์เอาต์: หัวภาพ (โลโก้ ชื่อโครงการเขียวหัวเป็ด แคปซูลรหัส) → รูปหลักเต็มกว้างขอบล่างจางเป็นพื้นขาว
#   → แถวรูปรอง 1–3 ช่อง กรอบขาวมุมโค้งซ้อนขอบรูปหลัก → รายการสเปก/จุดเด่นพร้อมไอคอนวงกลมเขียวหัวเป็ด
#   → ราคาตัวใหญ่ระหว่างเส้นคั่น → แถบติดต่อเขียวหัวเป็ดเต็มกว้างด้านล่าง
# อ่านรูป ข้อความ และค่าครอปจาก timeline.json (ไม่ hard-code ข้อความ)
#   - รูป: shots ตามลำดับ (ช็อตแรก = รูปหลัก ช็อต 2–4 = แถวรูปรอง) อ่านจาก graded/ (รูปที่ color_grade.py ปรับแล้ว)
#   - ข้อความ: role code / title / price / contact ; บรรทัดอื่นทุกกลุ่ม (sub, highlights ฯลฯ) = รายการสเปกพร้อมไอคอน
#   - บรรทัดที่มีคำว่า "ภาพห้องตัวอย่าง" = ป้ายมุมขวาล่างของรูปหลัก
# ใช้: <venv>/bin/python make_photo.py [ffmpeg-path]
#   env: PHOTO_TIMELINE (ค่าเริ่ม ./timeline.json), PHOTO_IMG_DIR (ค่าเริ่ม ./graded), PHOTO_OUT_DIR (ค่าเริ่ม ./photo)
# Pillow ในเครื่องไม่มี libraqm -> ข้อความทั้งหมดวาดด้วย ffmpeg drawtext (harfbuzz) ผ่าน fontfile=/textfile=
# สีและแสงของรูป: ใช้ color_grade.py STYLE = 'teal'
import json, math, os, re, shutil, subprocess, sys, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
TIMELINE = os.environ.get('PHOTO_TIMELINE') or os.path.join(HERE, 'timeline.json')
IMG_DIR = os.environ.get('PHOTO_IMG_DIR') or os.path.join(HERE, 'graded')
LOGO = os.path.join(ROOT, 'global', 'logo.png')
OUT_DIR = os.environ.get('PHOTO_OUT_DIR') or os.path.join(HERE, 'photo')
OUT = os.path.join(OUT_DIR, 'photo.jpg')
TTC = '/System/Library/Fonts/Supplemental/SukhumvitSet.ttc'
FONT_IDX = {'bold': 5, 'semi': 4, 'regular': 2}
FFMPEG = sys.argv[1] if len(sys.argv) > 1 else '/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg'

W, H = 1080, 1350
M = 54    # ระยะขอบซ้ายขวา 5%
TOP = 68  # ระยะขอบบนล่าง 5%
SS = 3    # supersample สำหรับรูปทรงโค้งและไอคอน

# ---- ค่าที่ photo agent ปรับได้ต่องาน ----
HERO_Y0, HERO_Y1 = 214, 616   # รูปหลักเต็มกว้าง (ขอบล่าง 130px จางเป็นพื้นขาว)
FADE = 130
THUMB_Y0, THUMB_H = 548, 196  # แถวรูปรองซ้อนขอบล่างรูปหลัก
SPEC_Y0 = 772                 # บรรทัดแรกของรายการสเปก
SPEC_ROW = 56                 # ระยะห่างแถวสเปก
SPEC_SIZE = 32                # ขนาดตัวอักษรสเปก (ลดเองถ้ายาวเกิน ต่ำสุด 26)
BAR_Y0 = 1168                 # แถบติดต่อเริ่มที่นี่ ยาวถึงขอบล่างภาพ

# ---- สี ----
BG = (246, 250, 250)          # ขาวอมเขียวจางมาก
TEAL = (22, 72, 83)           # #164853 เขียวหัวเป็ดเข้ม (หัวข้อ ไอคอน แถบติดต่อ)
TEAL_D = (14, 52, 61)         # เข้มกว่า สำหรับไล่เฉดแถบ
TEAL_L = (58, 124, 136)       # อ่อน สำหรับเส้นคั่น
MINT = (214, 233, 233)        # เขียวจาง สำหรับลายพื้นหลัง
SHADOW = (10, 40, 46)
TXT_TEAL = '164853'
TXT_DARK = '1E3A40'
TXT_SOFT = '4E6E74'
TXT_WHITE = 'FFFFFF'
TXT_MINT = 'BFE3E3'


def load_timeline():
  with open(TIMELINE, encoding='utf-8') as f:
    return json.load(f)


def collect_texts(tl):
  # คืน dict: code, title, price, badge, specs[], contacts[] ข้อความตาม timeline ทุกตัวอักษร
  out = {'code': None, 'title': None, 'price': None, 'badge': None, 'specs': [], 'contacts': []}
  for grp in tl['texts']:
    for l in grp['lines']:
      t, r = l['text'], l.get('role', '')
      if 'ภาพห้องตัวอย่าง' in t:
        out['badge'] = out['badge'] or t
      elif r == 'code' and out['code'] is None:
        out['code'] = t
      elif r == 'title' and out['title'] is None:
        out['title'] = t
      elif r == 'price' and out['price'] is None:
        out['price'] = t
      elif r == 'contact':
        out['contacts'].append(t)
      else:
        out['specs'].append(t)
  for k in ('code', 'title', 'price'):
    if not out[k]:
      sys.exit('timeline ไม่มีบรรทัด role %s' % k)
  if not out['contacts']:
    sys.exit('timeline ไม่มีบรรทัด role contact')
  return out


def code_label(code):
  code = str(code)
  return code if code.startswith('รหัส') else 'รหัส ' + code


def split_price(price):
  # "ขายเพียง 2.8 ล้านบาท" -> ("ขายเพียง", "2.8 ล้านบาท") ; "ค่าเช่า 11,000 บาท/เดือน" -> ("ค่าเช่า", "11,000 บาท/เดือน")
  m = re.match(r'^(\D+?)\s+(\d.*)$', price)
  return (m.group(1), m.group(2)) if m else ('', price)


def spec_icon(text):
  t = text
  if 'ห้องนอน' in t or 'สตูดิโอ' in t:
    return 'bed'
  if 'จอดรถ' in t:
    return 'car'
  if 'ตร.ม.' in t or 'ตร.ว.' in t or 'ตรว.' in t or 'ไร่' in t:
    return 'area'
  if 'ใกล้' in t or 'กม.' in t or 'สถานี' in t or 'BTS' in t or 'MRT' in t:
    return 'pin'
  if any(k in t for k in ('สระ', 'ฟิตเนส', 'รปภ', 'กล้อง', 'ส่วนกลาง', 'ความปลอดภัย')):
    return 'shield'
  if 'ชั้น' in t or 'ตึก' in t or 'อาคาร' in t:
    return 'building'
  if 'เฟอร์นิเจอร์' in t or 'ตกแต่ง' in t or 'เครื่องใช้' in t:
    return 'sofa'
  return 'home'


# ---------- รูป ----------

def crop_cover(im, w, h, focus):
  # ครอปให้เต็มช่องโดยรักษาสัดส่วน (ไม่ยืด/บีบ) focus = จุดศูนย์กลางที่ต้องการ (สัดส่วนของรูป)
  sw, sh = im.size
  ar = w / h
  if sw / sh > ar:
    ch, cw = sh, sh * ar
  else:
    cw, ch = sw, sw / ar
  fx, fy = focus
  x0 = min(max(fx * sw - cw / 2, 0), sw - cw)
  y0 = min(max(fy * sh - ch / 2, 0), sh - ch)
  return im.resize((w, h), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))


def load_shot(shot, w, h):
  p = os.path.join(IMG_DIR, shot['file'])
  if not os.path.exists(p):
    sys.exit('ไม่พบรูป %s (ต้องปรับสีด้วย color_grade.py ลง graded/ ก่อน)' % p)
  return crop_cover(Image.open(p).convert('RGB'), w, h, tuple(shot.get('focus') or (0.5, 0.5)))


def rounded_mask(w, h, r):
  m = Image.new('L', (w * SS, h * SS), 0)
  ImageDraw.Draw(m).rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), r * SS, fill=255)
  return m.resize((w, h), Image.LANCZOS)


def soft_shadow(canvas, box, r, off=8, blur=12, alpha=70):
  x, y, w, h = box
  pad = blur * 3
  lay = Image.new('L', (w + pad * 2, h + pad * 2), 0)
  ImageDraw.Draw(lay).rounded_rectangle((pad, pad, pad + w, pad + h), r, fill=alpha)
  lay = lay.filter(ImageFilter.GaussianBlur(blur))
  canvas.paste(Image.new('RGB', lay.size, SHADOW), (x - pad, y - pad + off), lay)


def framed_photo(canvas, shot, box, border=6, r=18):
  x, y, w, h = box
  soft_shadow(canvas, box, r)
  canvas.paste(Image.new('RGB', (w, h), (255, 255, 255)), (x, y), rounded_mask(w, h, r))
  iw, ih = w - border * 2, h - border * 2
  canvas.paste(load_shot(shot, iw, ih), (x + border, y + border), rounded_mask(iw, ih, r - border))


# ---------- พื้นหลัง ----------

def background():
  yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
  img = np.ones((H, W, 3), np.float32) * np.array(BG, np.float32)
  # วงกลมเขียวจางมุมขวาบนและซ้ายกลาง (ลายพื้นเบาๆ ไม่ทับข้อความ)
  for cx, cy, r in [(W * 0.98, 40, 230), (-60, H * 0.70, 260)]:
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    k = np.clip((r - d) / 6, 0, 1)[..., None] * 0.55
    img = img * (1 - k) + np.array(MINT, np.float32) * k
  return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def place_hero(canvas, shot):
  h = HERO_Y1 - HERO_Y0
  im = load_shot(shot, W, h)
  a = np.ones(h, np.float32)
  a[h - FADE:] = np.linspace(1, 0, FADE) ** 1.4
  mask = Image.fromarray(np.tile((a * 255).astype(np.uint8)[:, None], (1, W)))
  canvas.paste(im, (0, HERO_Y0), mask)


def teal_bar(w, h):
  y = np.linspace(0, 1, h)[:, None, None]
  a, b = np.array(TEAL, np.float32), np.array(TEAL_D, np.float32)
  g = a + (b - a) * y
  return Image.fromarray(np.repeat(g, w, axis=1).astype(np.uint8))


def hline(canvas, x0, x1, y, color, th=2):
  canvas.paste(Image.new('RGB', (x1 - x0, th), color), (x0, y))


# ---------- ไอคอน (วงกลมเขียวหัวเป็ด สัญลักษณ์ขาว วาดเอง) ----------

def icon_base(size, fill=TEAL):
  S = size * SS
  im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
  d = ImageDraw.Draw(im)
  d.ellipse((0, 0, S - 1, S - 1), fill=fill + (255,))
  return im, d, S


WH = (255, 255, 255, 255)


def draw_icon(kind, size):
  im, d, S = icon_base(size)
  lw = max(int(S * 0.055), 2)
  if kind == 'bed':
    x0, x1 = S * 0.24, S * 0.76
    d.line((x0, S * 0.32, x0, S * 0.70), fill=WH, width=lw)
    d.line((x1, S * 0.50, x1, S * 0.70), fill=WH, width=lw)
    d.rectangle((x0, S * 0.50, x1, S * 0.60), fill=WH)
    d.rounded_rectangle((S * 0.30, S * 0.40, S * 0.45, S * 0.49), S * 0.03, fill=WH)
  elif kind == 'area':
    a, b = S * 0.29, S * 0.71
    d.rectangle((a, a, b, b), outline=WH, width=lw)
    p, q = S * 0.38, S * 0.62
    d.line((p, q, q, p), fill=WH, width=lw)
    ah = S * 0.09
    d.polygon([(q + lw * 0.3, p - lw * 0.3), (q - ah, p - lw * 0.3), (q + lw * 0.3, p + ah)], fill=WH)
    d.polygon([(p - lw * 0.3, q + lw * 0.3), (p + ah, q + lw * 0.3), (p - lw * 0.3, q - ah)], fill=WH)
  elif kind == 'car':
    d.rounded_rectangle((S * 0.22, S * 0.46, S * 0.78, S * 0.64), S * 0.05, fill=WH)
    d.polygon([(S * 0.32, S * 0.46), (S * 0.38, S * 0.33), (S * 0.62, S * 0.33), (S * 0.68, S * 0.46)], fill=WH)
    d.polygon([(S * 0.37, S * 0.45), (S * 0.41, S * 0.37), (S * 0.59, S * 0.37), (S * 0.63, S * 0.45)], fill=TEAL + (255,))
    for cx in (0.34, 0.66):
      d.ellipse((S * (cx - 0.07), S * 0.58, S * (cx + 0.07), S * 0.72), fill=WH)
      d.ellipse((S * (cx - 0.03), S * 0.62, S * (cx + 0.03), S * 0.68), fill=TEAL + (255,))
  elif kind == 'shield':
    pts = [(S * 0.5, S * 0.22), (S * 0.74, S * 0.31), (S * 0.71, S * 0.55), (S * 0.5, S * 0.78),
           (S * 0.29, S * 0.55), (S * 0.26, S * 0.31)]
    d.polygon(pts, outline=WH, width=lw)
    d.line((S * 0.39, S * 0.50, S * 0.47, S * 0.58, S * 0.62, S * 0.42), fill=WH, width=lw, joint='curve')
  elif kind == 'pin':
    cx, cy, r = S * 0.5, S * 0.42, S * 0.17
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=WH)
    d.polygon([(cx - r * 0.9, cy + r * 0.45), (cx + r * 0.9, cy + r * 0.45), (cx, S * 0.78)], fill=WH)
    r2 = r * 0.42
    d.ellipse((cx - r2, cy - r2, cx + r2, cy + r2), fill=TEAL + (255,))
  elif kind == 'building':
    d.rectangle((S * 0.34, S * 0.25, S * 0.66, S * 0.74), outline=WH, width=lw)
    for rr in range(4):
      for k in range(2):
        x = S * (0.40 + k * 0.13)
        y = S * (0.32 + rr * 0.095)
        d.rectangle((x, y, x + S * 0.07, y + S * 0.05), fill=WH)
  elif kind == 'sofa':
    d.rounded_rectangle((S * 0.27, S * 0.36, S * 0.73, S * 0.54), S * 0.04, outline=WH, width=lw)
    d.rounded_rectangle((S * 0.20, S * 0.48, S * 0.80, S * 0.64), S * 0.05, fill=WH)
    d.line((S * 0.26, S * 0.64, S * 0.26, S * 0.72), fill=WH, width=lw)
    d.line((S * 0.74, S * 0.64, S * 0.74, S * 0.72), fill=WH, width=lw)
  elif kind == 'phone':
    rr, wdt = S * 0.24, int(S * 0.11)
    cx, cy = S * 0.56, S * 0.44
    d.arc((cx - rr, cy - rr, cx + rr, cy + rr), 45, 225, fill=WH, width=wdt)
    for ang in (45, 225):
      ex = cx + (rr - wdt / 2) * math.cos(math.radians(ang))
      ey = cy + (rr - wdt / 2) * math.sin(math.radians(ang))
      er = S * 0.1
      d.ellipse((ex - er, ey - er, ex + er, ey + er), fill=WH)
  elif kind == 'line':
    # ตัวอักษร "LINE" เรียบๆ ไม่ใช้โลโก้ทางการ
    f = ImageFont.truetype(TTC, int(S * 0.27), index=FONT_IDX['bold'])
    bb = d.textbbox((0, 0), 'LINE', font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    d.text(((S - tw) / 2 - bb[0], (S - th) / 2 - bb[1]), 'LINE', font=f, fill=WH)
  else:  # home
    d.polygon([(S * 0.5, S * 0.24), (S * 0.77, S * 0.48), (S * 0.23, S * 0.48)], fill=WH)
    d.rectangle((S * 0.31, S * 0.47, S * 0.69, S * 0.74), fill=WH)
    d.rectangle((S * 0.45, S * 0.58, S * 0.55, S * 0.74), fill=TEAL + (255,))
  return im.resize((size, size), Image.LANCZOS)


def paste_icon(canvas, ico, x, y):
  canvas.paste(ico, (int(x), int(y)), ico)


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


def spec_rows(tx, specs, isz):
  # จับคู่บรรทัดสั้นสองบรรทัดติดกันเป็นสองคอลัมน์ บรรทัดยาวอยู่แถวเดียวเต็มกว้าง
  half = (W - 2 * M) // 2 - isz - 30
  full = W - 2 * M - isz - 18
  # บรรทัดสั้นจับคู่กับบรรทัดสั้นถัดไป (ข้ามบรรทัดยาวได้) เพื่อประหยัดแถว
  fits = lambda t: tx.width(t, SPEC_SIZE, 'semi') <= half
  rest = list(specs)
  rows = []
  while rest:
    a = rest.pop(0)
    if fits(a):
      j = next((k for k, t in enumerate(rest) if fits(t)), None)
      if j is not None:
        rows.append([a, rest.pop(j)])
        continue
    rows.append([a])
  return rows, half, full


def main():
  tl = load_timeline()
  T = collect_texts(tl)
  shots = tl['shots']
  tmp = tempfile.mkdtemp(prefix='photo_', dir=os.environ.get('PHOTO_TMP'))
  try:
    tx = Texts(tmp)
    cv = background()

    # ---- หัวภาพ: โลโก้ + ชื่อโครงการเขียวหัวเป็ด + แคปซูลรหัสเขียวหัวเป็ด ----
    ls = 118
    lx, ly = M, TOP
    ring = rounded_mask(ls + 6, ls + 6, (ls + 6) // 2)
    cv.paste(Image.new('RGB', (ls + 6, ls + 6), TEAL), (lx - 3, ly - 3), ring)
    logo = Image.open(LOGO).convert('RGBA').resize((ls, ls), Image.LANCZOS)
    cv.paste(logo, (lx, ly), logo)
    tx0 = lx + ls + 26
    ts = fit_size(tx, T['title'], 62, 'bold', W - M - tx0, 40)
    tx.add(T['title'], ts, 'bold', TXT_TEAL, tx0, 134)
    code = code_label(T['code'])
    cs, ch = 28, 42
    cw = int(tx.width(code, cs, 'semi')) + 44
    cy0 = 152
    cv.paste(Image.new('RGB', (cw, ch), TEAL), (tx0, cy0), rounded_mask(cw, ch, ch // 2))
    tx.add(code, cs, 'semi', TXT_WHITE, tx0 + cw / 2, cy0 + 30, 'center')
    hline(cv, tx0 + cw + 18, W - M, cy0 + ch // 2, TEAL_L, 2)

    # ---- รูปหลัก + ป้ายห้องตัวอย่าง ----
    place_hero(cv, shots[0])
    if T['badge']:
      bs = 26
      bw = int(tx.width(T['badge'], bs, 'semi')) + 36
      bx, by = W - M - bw, HERO_Y0 + 18
      cv.paste(Image.new('RGB', (bw, 40), TEAL), (bx, by), rounded_mask(bw, 40, 20))
      tx.add(T['badge'], bs, 'semi', TXT_WHITE, bx + bw / 2, by + 28, 'center')

    # ---- แถวรูปรอง 1–3 ช่อง ----
    thumbs = shots[1:4]
    if thumbs:
      gap = 18
      n = len(thumbs)
      tw_ = (W - 2 * M - gap * (n - 1)) // n
      for k, s in enumerate(thumbs):
        framed_photo(cv, s, (M + k * (tw_ + gap), THUMB_Y0, tw_, THUMB_H))

    # ---- รายการสเปก/จุดเด่น ----
    isz = 46
    rows, half, full = spec_rows(tx, T['specs'], isz)
    y = SPEC_Y0 if thumbs else THUMB_Y0 + 20
    for row in rows:
      for k, text in enumerate(row):
        x = M + k * ((W - 2 * M) // 2)
        paste_icon(cv, draw_icon(spec_icon(text), isz), x, y)
        maxw = half if len(row) == 2 else full
        fs = fit_size(tx, text, SPEC_SIZE, 'semi', maxw, 26)
        tx.add(text, fs, 'semi', TXT_DARK, x + isz + 16, y + isz / 2 + 11)
      y += SPEC_ROW
    if y > BAR_Y0 - 100:
      sys.exit('รายการสเปกยาวเกิน (%d แถว) ลดบรรทัดใน timeline หรือลด SPEC_ROW' % len(rows))

    # ---- ราคา: ตัวใหญ่กลางภาพ มีเส้นคั่นซ้ายขวา ----
    lead, main_ = split_price(T['price'])
    py = (y + BAR_Y0) // 2 + 4
    ls_, ms_ = 34, 62
    ms_ = fit_size(tx, main_, ms_, 'bold', W - 2 * M - 260, 44)
    lw_ = tx.width(lead, ls_, 'semi') if lead else 0
    mw_ = tx.width(main_, ms_, 'bold')
    sp = 16 if lead else 0
    tot = lw_ + sp + mw_
    px0 = (W - tot) / 2
    base = py + ms_ * 0.36
    if lead:
      tx.add(lead, ls_, 'semi', TXT_SOFT, px0, base)
    tx.add(main_, ms_, 'bold', TXT_TEAL, px0 + lw_ + sp, base)
    hline(cv, M, int(px0 - 24), py, TEAL_L, 2)
    hline(cv, int(px0 + tot + 24), W - M, py, TEAL_L, 2)

    # ---- แถบติดต่อเต็มกว้างด้านล่าง ----
    cv.paste(teal_bar(W, H - BAR_Y0), (0, BAR_Y0))
    hline(cv, 0, W, BAR_Y0, TEAL_L, 3)
    contacts = T['contacts']
    bold = [c for c in contacts if c.startswith('โทร') or c.lower().startswith('line')]
    other = [c for c in contacts if c not in bold]
    ci = 44
    colw = (W - 2 * M) // 2
    b1 = BAR_Y0 + 62
    for k, c in enumerate(bold[:2]):
      x = M + k * colw
      ic = 'phone' if c.startswith('โทร') else 'line'
      ico = draw_icon(ic, ci).copy()
      # ไอคอนติดต่อ: วงกลมขาว สัญลักษณ์เขียวหัวเป็ด (กลับสีจากไอคอนสเปก)
      a = np.asarray(ico).copy()
      inside = a[..., 3] > 0
      wh = (a[..., 0] > 200) & inside
      a[inside & ~wh, :3] = (255, 255, 255)
      a[wh, :3] = TEAL
      ico = Image.fromarray(a)
      paste_icon(cv, ico, x, b1 - 33)
      fs = fit_size(tx, c, 36, 'bold', colw - ci - 26, 32)
      tx.add(c, fs, 'bold', TXT_WHITE, x + ci + 14, b1)
    b2 = H - TOP - 6
    for k, c in enumerate(other[:2]):
      x = M + k * colw
      if ': ' in c:
        lab, val = c.split(': ', 1)
        lab += ':'
      else:
        lab, val = '', c
      sz = 32
      while sz > 26 and tx.width(lab + ' ' + val, sz, 'regular') > colw - 12:
        sz -= 1
      lw = tx.width(lab, sz, 'semi') if lab else 0
      spw = tx.width(' ', sz, 'regular') if lab else 0
      if lab:
        tx.add(lab, sz, 'semi', TXT_MINT, x, b2)
      tx.add(val, sz, 'regular', TXT_WHITE, x + lw + spw, b2)
    if len(bold) > 2 or len(other) > 2:
      sys.exit('ช่องทางติดต่อเกิน 4 ช่อง')

    os.makedirs(OUT_DIR, exist_ok=True)
    basep = os.path.join(tmp, 'base.png')
    cv.save(basep)
    outp = os.path.join(tmp, 'out.png')
    tx.render(basep, outp)
    res = Image.open(outp).convert('RGB')
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
