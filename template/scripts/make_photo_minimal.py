#!/usr/bin/env python3
# ภาพรวม (photo) งาน 00000126 — สไตล์ "มินิมอล สว่าง ครีม/เบจ + เขียวเสจ/น้ำตาลไม้"
# ดัดแปลงจาก template/scripts/make_photo.py (ส่วน Texts / grade / ffmpeg drawtext) แต่เปลี่ยนสไตล์ทั้งหมด
# งานแก้หลังส่ง ไม่มี timeline.json -> ตั้งรูปและข้อความไว้ในสคริปต์ (คัดลอกตามที่ brief กำหนดทุกตัวอักษร)
# ใช้: <venv>/bin/python make_photo.py <ffmpeg-path>
# Pillow ในเครื่องไม่มี libraqm -> ข้อความทั้งหมดวาดด้วย ffmpeg drawtext (harfbuzz) ผ่าน fontfile=/textfile=
import math, os, shutil, subprocess, sys, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
IMG_DIR = os.path.join(ROOT, 'assets', '00000126')
LOGO = os.path.join(ROOT, 'global', 'logo.png')
OUT_DIR = os.environ.get('PHOTO_OUT_DIR') or os.path.join(HERE, 'photo')
OUT = os.path.join(OUT_DIR, 'photo.jpg')
TTC = '/System/Library/Fonts/Supplemental/SukhumvitSet.ttc'
FONT_IDX = {'bold': 5, 'semi': 4, 'medium': 3, 'regular': 2}
FFMPEG = sys.argv[1] if len(sys.argv) > 1 else '/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg'

W, H = 1080, 1350
M = 54  # ระยะขอบ 5%
SS = 4  # supersample สำหรับเส้นไอคอน

# ---- ข้อความ (ตาม brief ทุกตัวอักษร) ----
T = {
  'code': '00000126',
  'sub': 'ให้เช่า',
  'title': 'เทมโป้ วัน รามคำแหง – พระราม 9',
  'price': 'ค่าเช่า 8,500 บาท/เดือน',
  'label': 'ภาพห้องตัวอย่าง',
  # แถวไอคอนสเปก: (ไอคอน, บรรทัด) — มาจาก "1 ห้องนอน · 26 ตร.ม." / "ตึก A ชั้น 5" /
  # "ตกแต่งพร้อมเฟอร์นิเจอร์และเครื่องใช้ไฟฟ้า" (ตัดบรรทัดเพื่อให้ลงช่อง ข้อความครบทุกตัว)
  'specs': [
    ('bed', ['1 ห้องนอน']),
    ('area', ['26 ตร.ม.']),
    ('building', ['ตึก A ชั้น 5']),
    ('sofa', ['ตกแต่งพร้อมเฟอร์นิเจอร์', 'และเครื่องใช้ไฟฟ้า']),
  ],
  'contacts': [
    ('phone', 'โทร 064-535-9426'),
    ('line', 'Line: @uptownassets'),
    ('chat', 'WhatsApp: +66 64 514 4624'),
    ('mail', 'Email: pang@uptownassets.com'),
  ],
}

# ---- รูป: (ไฟล์, ช่อง, focus x, focus y) ช่องแรก = รูปหลัก ----
# 06 มุมโต๊ะทานอาหารกระจก (หลัก) / 11 ห้องนอน (แนวตั้ง) / 09 นั่งเล่นโซฟาฟ้า / 10 ชั้นวางทีวี+ครัว
# ช่องจัดให้ใกล้ขนาดจริงของรูป (500x333 / 333x500) ขยายสูงสุด ~1.28 เท่า (รูปหลัก) ที่เหลือไม่ขยาย
IMAGES = [
  ('06.jpeg', 0.5, 0.45),
  ('11.jpeg', 0.5, 0.6),
  ('09.jpeg', 0.5, 0.55),
  ('10.jpeg', 0.5, 0.3),
]
LAYOUT = 'mosaic'  # รูปหลัก + แนวตั้งด้านขวา / แถวล่าง 2 รูป

# ---- สี ----
BG = (247, 242, 234)        # ครีม
BAND = (233, 225, 211)      # เบจ (แถบติดต่อ)
SAGE = (125, 139, 106)      # เขียวเสจ
SAGE_D = (78, 91, 69)       # เสจเข้ม (แบนเนอร์ราคา)
WOOD = (160, 122, 85)       # น้ำตาลไม้
INK = (59, 49, 40)          # น้ำตาลเข้ม
RULE = (214, 202, 184)      # เส้นคั่น
TXT_INK = '3B3128'
TXT_SUB = '75665A'
TXT_SAGE = '5E6D52'
TXT_WHITE = 'FFFFFF'


# ---------- รูป ----------

def grade(im):
  # โทนอุ่นเล็กน้อยให้เข้ากับวิดีโอ ไม่ดันขาวโพลน
  a = np.asarray(im.convert('RGB')).astype(np.float32) / 255.0
  a = (a - 0.5) * 1.04 + 0.5
  a[..., 0] = a[..., 0] * 1.025 + 0.004
  a[..., 1] = a[..., 1] * 1.005
  a[..., 2] = a[..., 2] * 0.965
  a = np.clip(a, 0, 0.985)
  return Image.fromarray((a * 255 + 0.5).astype(np.uint8))


def crop_cover(im, w, h, fx, fy):
  # ครอปรักษาสัดส่วน (ไม่ยืด/บีบ) แล้วย่อ/ขยายลงช่อง
  sw, sh = im.size
  ar = w / h
  if sw / sh > ar:
    ch, cw = sh, sh * ar
  else:
    cw, ch = sw, sw / ar
  x0 = min(max(fx * sw - cw / 2, 0), sw - cw)
  y0 = min(max(fy * sh - ch / 2, 0), sh - ch)
  print('  crop %dx%d of %dx%d -> %dx%d (scale %.2f)' % (cw, ch, sw, sh, w, h, w / cw))
  return im.resize((w, h), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))


def rounded_mask(w, h, r):
  m = Image.new('L', (w * SS, h * SS), 0)
  ImageDraw.Draw(m).rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), r * SS, fill=255)
  return m.resize((w, h), Image.LANCZOS)


def place(cv, im, box, r=10):
  x, y, w, h = box
  cv.paste(im, (x, y), rounded_mask(w, h, r))


def pill(cv, box, fill, outline=None, ow=2):
  x, y, w, h = box
  lay = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
  d = ImageDraw.Draw(lay)
  d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), h * SS // 2, fill=fill,
                      outline=outline, width=ow * SS if outline else 0)
  lay = lay.resize((w, h), Image.LANCZOS)
  cv.paste(lay, (x, y), lay)


# ---------- ไอคอนเส้นบาง (วาดเอง) ----------

class Icon:
  def __init__(self, size, color, lw=2.2):
    self.s = size
    self.S = size * SS
    self.im = Image.new('RGBA', (self.S, self.S), (0, 0, 0, 0))
    self.d = ImageDraw.Draw(self.im)
    self.c = color + (255,)
    self.w = max(1, int(round(lw * SS)))

  def p(self, x, y):
    return (x * self.S, y * self.S)

  def line(self, pts):
    self.d.line([self.p(*q) for q in pts], fill=self.c, width=self.w, joint='curve')
    for q in (pts[0], pts[-1]):
      x, y = self.p(*q)
      r = self.w / 2
      self.d.ellipse((x - r, y - r, x + r, y + r), fill=self.c)

  def rect(self, x0, y0, x1, y1, r=0.0):
    self.d.rounded_rectangle(self.p(x0, y0) + self.p(x1, y1), int(r * self.S), outline=self.c, width=self.w)

  def arc(self, x0, y0, x1, y1, a0, a1):
    self.d.arc(self.p(x0, y0) + self.p(x1, y1), a0, a1, fill=self.c, width=self.w)

  def ellipse(self, x0, y0, x1, y1):
    self.d.ellipse(self.p(x0, y0) + self.p(x1, y1), outline=self.c, width=self.w)

  def done(self):
    return self.im.resize((self.s, self.s), Image.LANCZOS)


def draw_icon(kind, size, color, lw=2.2):
  ic = Icon(size, color, lw)
  if kind == 'bed':
    ic.line([(0.08, 0.22), (0.08, 0.82)])
    ic.line([(0.92, 0.50), (0.92, 0.82)])
    ic.line([(0.08, 0.68), (0.92, 0.68)])
    ic.rect(0.08, 0.50, 0.92, 0.68, 0.03)
    ic.rect(0.16, 0.36, 0.40, 0.50, 0.05)
  elif kind == 'area':
    ic.rect(0.12, 0.12, 0.88, 0.88, 0.04)
    ic.line([(0.30, 0.70), (0.70, 0.30)])
    ic.line([(0.30, 0.52), (0.30, 0.70), (0.48, 0.70)])
    ic.line([(0.52, 0.30), (0.70, 0.30), (0.70, 0.48)])
  elif kind == 'building':
    ic.rect(0.22, 0.10, 0.78, 0.90, 0.02)
    ic.line([(0.08, 0.90), (0.92, 0.90)])
    for yy in (0.24, 0.40, 0.56):
      ic.line([(0.36, yy), (0.42, yy)])
      ic.line([(0.58, yy), (0.64, yy)])
    ic.rect(0.43, 0.70, 0.57, 0.90, 0.0)
  elif kind == 'sofa':
    ic.rect(0.22, 0.28, 0.78, 0.56, 0.06)
    ic.rect(0.06, 0.44, 0.22, 0.76, 0.05)
    ic.rect(0.78, 0.44, 0.94, 0.76, 0.05)
    ic.line([(0.22, 0.62), (0.78, 0.62)])
    ic.line([(0.22, 0.76), (0.78, 0.76)])
    ic.line([(0.14, 0.76), (0.14, 0.86)])
    ic.line([(0.86, 0.76), (0.86, 0.86)])
  elif kind == 'phone':
    # หูโทรศัพท์แบบเส้น
    ic.line([(0.26, 0.14), (0.40, 0.14), (0.46, 0.32), (0.36, 0.40)])
    ic.arc(0.18, 0.06, 1.42, 1.30, 180, 225)
    ic.line([(0.36, 0.40), (0.42, 0.52), (0.50, 0.60), (0.60, 0.64)])
    ic.line([(0.60, 0.64), (0.68, 0.54), (0.86, 0.60), (0.86, 0.74)])
    ic.line([(0.26, 0.14), (0.18, 0.24), (0.18, 0.40), (0.26, 0.58), (0.42, 0.76), (0.60, 0.84), (0.76, 0.84), (0.86, 0.74)])
  elif kind == 'line':
    # กรอบมนเรียบๆ + ตัวอักษร LINE (ไม่ใช้โลโก้ทางการ)
    ic.rect(0.04, 0.14, 0.96, 0.86, 0.18)
    f = ImageFont.truetype(TTC, int(ic.S * 0.34), index=FONT_IDX['bold'])
    bb = ic.d.textbbox((0, 0), 'LINE', font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    ic.d.text(((ic.S - tw) / 2 - bb[0], (ic.S - th) / 2 - bb[1]), 'LINE', font=f, fill=ic.c)
  elif kind == 'chat':
    # กล่องข้อความทั่วไป (ไม่ใช่โลโก้ WhatsApp)
    ic.rect(0.08, 0.14, 0.92, 0.70, 0.14)
    ic.line([(0.26, 0.70), (0.20, 0.88), (0.42, 0.70)])
    for xx in (0.32, 0.50, 0.68):
      ic.d.ellipse((ic.p(xx - 0.035, 0.385) + ic.p(xx + 0.035, 0.455)), fill=ic.c)
  elif kind == 'mail':
    ic.rect(0.06, 0.20, 0.94, 0.80, 0.06)
    ic.line([(0.08, 0.24), (0.50, 0.56), (0.92, 0.24)])
  return ic.done()


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
    # ประมาณความกว้างด้วย Pillow (basic layout) ใช้จัดช่อง ตำแหน่งจริงคำนวณใน drawtext
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


# ---------- เลย์เอาต์ ----------

def mosaic_slots(x0, y0, w, g):
  # แถวบน: รูปหลักแนวนอน + รูปแนวตั้งด้านขวา (สูง 400) / แถวล่าง: 2 รูปแนวนอนกว้างเท่ากัน (สูง 250)
  top, bot = 400, 250
  pw = 318
  hw = w - pw - g
  bw = (w - g) // 2
  return [
    (x0, y0, hw, top),
    (x0 + hw + g, y0, pw, top),
    (x0, y0 + top + g, bw, bot),
    (x0 + bw + g, y0 + top + g, w - bw - g, bot),
  ]


def main():
  tmp = tempfile.mkdtemp(prefix='photo_', dir=os.environ.get('PHOTO_TMP'))
  try:
    tx = Texts(tmp)
    cv = Image.new('RGB', (W, H), BG)

    # ---- หัวภาพ: โลโก้ซ้าย / รหัสในแคปซูลเส้นบางขวา ----
    lg = 84
    logo = Image.open(LOGO).convert('RGBA').resize((lg, lg), Image.LANCZOS)
    cv.paste(logo, (M, 46), logo)
    cs = 30
    cw = int(tx.width(T['code'], cs, 'semi')) + 44
    pill(cv, (W - M - cw, 62, cw, 52), None, INK + (255,), 2)
    tx.add(T['code'], cs, 'semi', TXT_INK, W - M - cw / 2, 98, 'center')
    # ป้าย "ให้เช่า" แคปซูลเสจ ต่อจากโลโก้
    ss = 30
    sw = int(tx.width(T['sub'], ss, 'semi')) + 44
    sx = M + lg + 22
    pill(cv, (sx, 62, sw, 52), SAGE + (255,))
    tx.add(T['sub'], ss, 'semi', TXT_WHITE, sx + sw / 2, 98, 'center')

    # ชื่อโครงการตัวหนา + เส้นไม้สั้นใต้ชื่อ
    ts = fit_size(tx, T['title'], 58, 'bold', W - 2 * M, 40)
    tx.add(T['title'], ts, 'bold', TXT_INK, M, 198)
    cv.paste(Image.new('RGB', (64, 4), WOOD), (M, 220))

    # ---- รูป ----
    gap = 14
    slots = mosaic_slots(M, 246, W - 2 * M, gap)
    for (f, fx, fy), box in zip(IMAGES, slots):
      print(f, box)
      im = grade(Image.open(os.path.join(IMG_DIR, f)))
      place(cv, crop_cover(im, box[2], box[3], fx, fy), box)
    hx, hy, hw, hh = slots[0]
    ls = 24
    lw = int(tx.width(T['label'], ls, 'regular')) + 32
    lx, ly = hx + hw - 14 - lw, hy + hh - 14 - 40
    pill(cv, (lx, ly, lw, 40), BG + (235,))
    tx.add(T['label'], ls, 'regular', TXT_INK, lx + lw / 2, ly + 28, 'center')
    py0 = slots[2][1] + slots[2][3]  # ล่างสุดของรูป

    # ---- แบนเนอร์ราคา: แถบเสจเข้มทึบ ตัวขาว เต็มกว้าง ----
    by0, bh = py0 + 18, 80
    cv.paste(Image.new('RGB', (W - 2 * M, bh), SAGE_D), (M, by0), rounded_mask(W - 2 * M, bh, 10))
    ps = fit_size(tx, T['price'], 52, 'bold', W - 2 * M - 80, 40)
    tx.add(T['price'], ps, 'bold', TXT_WHITE, W / 2, by0 + bh / 2 + ps * 0.36, 'center')

    # ---- แถวไอคอนสเปก ----
    iy0 = by0 + bh + 22
    widths = [200, 196, 232]
    widths.append(W - 2 * M - sum(widths))
    x = M
    isz = 50
    for i, ((kind, lines), cwid) in enumerate(zip(T['specs'], widths)):
      if i:
        cv.paste(Image.new('RGB', (2, 100), RULE), (x, iy0 + 6))
      ico = draw_icon(kind, isz, SAGE_D, 2.0)
      cx = x + cwid / 2
      cv.paste(ico, (int(cx - isz / 2), iy0), ico)
      if len(lines) == 1:
        tx.add(lines[0], 30, 'semi', TXT_INK, cx, iy0 + isz + 44, 'center')
      else:
        for k, ln in enumerate(lines):
          fs = fit_size(tx, ln, 26, 'semi', cwid - 20, 22)
          tx.add(ln, fs, 'semi', TXT_INK, cx, iy0 + isz + 34 + k * 32, 'center')
      x += cwid
    iy1 = iy0 + 112

    # ---- แถบติดต่อด้านล่าง (เบจ เต็มกว้าง) 2 แถว ----
    ty = iy1 + 28
    cv.paste(Image.new('RGB', (W, H - ty), BAND), (0, ty))
    cv.paste(Image.new('RGB', (W, 2), RULE), (0, ty))
    csz, isz2 = 32, 34
    rows = [ty + 50, ty + 100]
    # คอลัมน์ขวาชิดขอบขวา (Email ยาว) คอลัมน์ซ้ายชิดขอบซ้าย
    rw = max(tx.width(t, csz, 'medium') for _, t in T['contacts'][1::2]) + isz2 + 12
    rx = int(W - M - rw)
    for i, (kind, txt) in enumerate(T['contacts']):
      cx = M if i % 2 == 0 else rx
      bl = rows[i // 2]
      ico = draw_icon(kind, isz2, WOOD, 2.2)
      cv.paste(ico, (cx, int(bl - csz * 0.36 - isz2 / 2)), ico)
      fs = csz
      tx.add(txt, fs, 'medium', TXT_INK, cx + isz2 + 12, bl)
    print('contact strip top', ty, 'rows', rows)

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
    print('wrote', OUT, res.size, 'layout', LAYOUT)
  finally:
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
  main()
