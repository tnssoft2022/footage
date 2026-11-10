#!/usr/bin/env python3
# ภาพรวม (photo) งาน 00000130 สไตล์ "กรมท่า + ทอง" (navy & gold)
# เริ่มจากสำเนา template/scripts/make_photo.py แล้วเปลี่ยนสไตล์และเลย์เอาต์ทั้งหมด
# งานนี้ไม่มี timeline.json (งานแก้หลังส่ง) -> รูปและข้อความตั้งในสคริปต์ตาม brief
# ใช้: <venv>/bin/python make_photo.py <ffmpeg-path>
# Pillow ในเครื่องไม่มี libraqm -> ข้อความทั้งหมดวาดด้วย ffmpeg drawtext (harfbuzz) ผ่าน fontfile=/textfile=
import math, os, shutil, subprocess, sys, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
IMG_DIR = os.path.join(ROOT, 'assets', '00000130')
LOGO = os.path.join(ROOT, 'global', 'logo.png')
OUT_DIR = os.path.join(HERE, 'photo')
OUT = os.path.join(OUT_DIR, 'photo.jpg')
TTC = '/System/Library/Fonts/Supplemental/SukhumvitSet.ttc'
FONT_IDX = {'bold': 5, 'regular': 2}
FFMPEG = sys.argv[1] if len(sys.argv) > 1 else '/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg'

W, H = 1080, 1350
M = 54  # ระยะขอบซ้ายขวา 5%
SS = 3

# ---- ข้อมูลงาน (ตาม brief ทุกตัวอักษร) ----
CODE = '00000130'
TITLE = 'ทีซี กรีน พระราม 9'
# "ขาย ห้องสตูดิโอ 30 ตร.ม." แยกเป็นแถวไอคอนสเปก ("ขาย" อยู่ในแถบราคา "ขายเพียง ...")
SPECS = [('bed', 'ห้องสตูดิโอ'), ('area', '30 ตร.ม.'), ('building', 'ตึก B ชั้น 24')]
PRICE_LEAD = 'ขายเพียง'
PRICE_MAIN = '2.69 ล้านบาท'
TEL = 'โทร 064-535-9426'
LINE = 'Line: @uptownassets'
OTHER = ['WhatsApp: +66 64 514 4624', 'Email: pang@uptownassets.com']

# ---- รูป: ต่างมุมต่างโซน มีรูปเน้นเตียงรูปเดียว (12) ----
# focus = (fx, fy) สัดส่วนของระยะที่ครอปเลื่อนได้ (0 = ชิดซ้าย/บน, 1 = ชิดขวา/ล่าง)
HERO = ('12.jpeg', (0.5, 0.30))   # เตียง + โคมระย้า + ม่าน (ภาพเปิด)
INSET = ('16.jpeg', (0.5, 0.5))   # มุมรวมห้อง: ผนังทีวี โต๊ะทานอาหาร ครัว ตู้เสื้อผ้า
SMALL = ('01.jpeg', (0.5, 0.62))  # ผนังทีวี + โต๊ะสไตล์คาเฟ่

# สี กรมท่า + ทอง
NAVY_EDGE = (10, 22, 46)
NAVY_DARK = (14, 31, 61)    # #0E1F3D
NAVY_LIGHT = (27, 51, 96)   # #1B3360
GOLD = (226, 196, 138)
GOLD_L = (240, 220, 165)
GOLD_D = (184, 146, 79)
SHADOW = (4, 10, 24)
TXT_GOLD = 'E6C98E'
TXT_WHITE = 'FFFFFF'
TXT_SOFT = 'D8E0EE'
TXT_NAVY = '0E1F3D'


def grade(im):
  # โทนอุ่นเล็กน้อย (ค่าเดียวกับต้นแบบ) ไม่ดันขาวโพลน
  a = np.asarray(im.convert('RGB')).astype(np.float32) / 255.0
  a = (a - 0.5) * 1.04 + 0.5
  a[..., 0] = a[..., 0] * 1.025 + 0.004
  a[..., 1] = a[..., 1] * 1.005
  a[..., 2] = a[..., 2] * 0.965
  a = np.clip(a, 0, 0.985)
  return Image.fromarray((a * 255 + 0.5).astype(np.uint8))


def crop_cover(im, w, h, focus):
  # ครอปให้เต็มช่องโดยรักษาสัดส่วน (ไม่ยืด/บีบ)
  sw, sh = im.size
  ar = w / h
  if sw / sh > ar:
    ch, cw = sh, sh * ar
  else:
    cw, ch = sw, sw / ar
  x0 = (sw - cw) * focus[0]
  y0 = (sh - ch) * focus[1]
  return im.resize((w, h), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))


def load(spec, w, h):
  f, focus = spec
  return crop_cover(grade(Image.open(os.path.join(IMG_DIR, f))), w, h, focus)


def rounded_mask(w, h, r):
  m = Image.new('L', (w * SS, h * SS), 0)
  ImageDraw.Draw(m).rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), r * SS, fill=255)
  return m.resize((w, h), Image.LANCZOS)


def gold_gradient(w, h):
  # ทองเงาวาว: เข้ม -> สว่าง -> เข้ม ตามแนวทแยง
  x = np.linspace(0, 1, w)[None, :]
  y = np.linspace(0, 1, h)[:, None]
  t = x * 0.75 + y * 0.25
  k = 0.5 - 0.5 * np.cos(t * 2 * math.pi)
  a = np.array(GOLD_D, np.float32)
  b = np.array(GOLD_L, np.float32)
  g = a + (b - a) * k[..., None]
  return Image.fromarray(np.clip(g, 0, 255).astype(np.uint8))


def drop_shadow(canvas, box, r, off=10, blur=14, alpha=200):
  x, y, w, h = box
  pad = blur * 3
  lay = Image.new('L', (w + pad * 2, h + pad * 2), 0)
  ImageDraw.Draw(lay).rounded_rectangle((pad, pad, pad + w, pad + h), r, fill=alpha)
  lay = lay.filter(ImageFilter.GaussianBlur(blur))
  canvas.paste(Image.new('RGB', lay.size, SHADOW), (x - pad, y - pad + off), lay)


def framed_photo(canvas, spec, box, border=5, r=10):
  x, y, w, h = box
  drop_shadow(canvas, box, r)
  canvas.paste(gold_gradient(w, h), (x, y), rounded_mask(w, h, r))
  iw, ih = w - border * 2, h - border * 2
  canvas.paste(load(spec, iw, ih), (x + border, y + border), rounded_mask(iw, ih, max(r - border, 2)))


# ---------- พื้นหลัง ----------

def background():
  yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
  # แสงนุ่มจากซ้ายบนและกลางล่าง
  d1 = np.sqrt((xx - W * 0.2) ** 2 + (yy - H * 0.05) ** 2) / math.hypot(W, H)
  d2 = np.sqrt((xx - W * 0.6) ** 2 + (yy - H * 0.78) ** 2) / math.hypot(W, H)
  t = np.clip(1 - d1 / 0.8, 0, 1) ** 1.5 * 0.9 + np.clip(1 - d2 / 0.6, 0, 1) ** 2 * 0.6
  t = np.clip(t, 0, 1)
  e = np.array(NAVY_DARK, np.float32)
  l = np.array(NAVY_LIGHT, np.float32)
  img = e + (l - e) * t[..., None]
  # ลายเส้นทแยงละเอียดจางๆ (เหมือนผ้าทอ)
  img *= (1 + 0.025 * np.sin((xx - yy) * 0.55))[..., None]
  # vignette ขอบกรมท่าเข้ม
  v = np.sqrt(((xx - W / 2) / (W * 0.6)) ** 2 + ((yy - H / 2) / (H * 0.6)) ** 2)
  k = np.clip(v - 0.6, 0, 1) ** 1.3 * 0.55
  img = img * (1 - k[..., None]) + np.array(NAVY_EDGE, np.float32) * k[..., None]
  bg = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert('RGBA')
  # เส้นโค้งทองบางๆ (วงรีใหญ่ตัดขอบภาพ)
  lay = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
  dr = ImageDraw.Draw(lay)
  # วางเฉพาะมุมขวาบนกับซ้ายล่าง ไม่ให้เส้นพาดผ่านข้อความ
  for box, a, wd in [((-640, 990, 300, 1700), 70, 2.0), ((-600, 1030, 340, 1760), 45, 1.4),
                     ((800, -420, 1560, 150), 70, 2.0), ((840, -380, 1600, 180), 45, 1.4)]:
    dr.ellipse(tuple(c * SS for c in box), outline=GOLD + (a,), width=int(wd * SS))
  bg.alpha_composite(lay.resize((W, H), Image.LANCZOS))
  return bg.convert('RGB')


def gold_line(canvas, x0, x1, y, th=2, fade_l=True, fade_r=True):
  w = x1 - x0
  a = np.ones(w, np.float32)
  f = int(w * 0.35)
  if fade_l:
    a[:f] = np.linspace(0, 1, f)
  if fade_r:
    a[w - f:] = np.linspace(1, 0, f)
  mask = Image.fromarray(np.tile((a * 255).astype(np.uint8)[None, :], (th, 1)))
  canvas.paste(gold_gradient(w, th), (x0, y), mask)


# ---------- รูปหลักขอบล่างโค้ง ----------

HERO_Y0, HERO_Y1 = 196, 770


def hero_edge(x):
  # ขอบล่างของรูปหลัก: ต่ำทางซ้าย สูงขึ้นทางขวา (โค้งแบบ swoosh)
  return HERO_Y1 - 92 * min(max(x / W, 0), 1) ** 1.35


def place_hero(canvas):
  h = HERO_Y1 - HERO_Y0
  im = load(HERO, W, h)
  m = Image.new('L', (W * SS, h * SS), 0)
  pts = [(0, 0), (W * SS, 0)] + [(x * SS, (hero_edge(x) - HERO_Y0) * SS) for x in range(W, -1, -4)]
  ImageDraw.Draw(m).polygon(pts, fill=255)
  m = m.resize((W, h), Image.LANCZOS)
  canvas.paste(im, (0, HERO_Y0), m)
  # เส้นทองตามขอบโค้ง (เส้นหลักหนา + เส้นรองบางด้านล่าง)
  lay = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0))
  dr = ImageDraw.Draw(lay)
  for off, wd, a in [(0, 6, 255), (16, 2, 150)]:
    pl = [(x * SS, (hero_edge(x) + off) * SS) for x in range(-10, W + 11, 4)]
    dr.line(pl, fill=(255, 255, 255, a), width=int(wd * SS), joint='curve')
  alpha = lay.resize((W, H), Image.LANCZOS).split()[3]
  canvas.paste(gold_gradient(W, H), (0, 0), alpha)
  # เส้นทองบางที่ขอบบนของรูปหลัก
  gold_line(canvas, 0, W, HERO_Y0 - 2, 2, False, False)


# ---------- ไอคอน (วาดเอง เส้นทอง) ----------

def icon_canvas(size):
  S = size * SS
  im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
  return im, ImageDraw.Draw(im), S


def icon_ring(d, S):
  d.ellipse((0, 0, S - 1, S - 1), fill=GOLD + (255,))
  b = int(2.5 * SS)
  d.ellipse((b, b, S - 1 - b, S - 1 - b), fill=NAVY_DARK + (255,))


def icon_bed(size):
  im, d, S = icon_canvas(size)
  icon_ring(d, S)
  c = GOLD + (255,)
  lw = int(S * 0.055)
  x0, x1 = S * 0.22, S * 0.78
  d.line((x0, S * 0.32, x0, S * 0.70), fill=c, width=lw)            # หัวเตียง
  d.line((x1, S * 0.50, x1, S * 0.70), fill=c, width=lw)            # ปลายเตียง
  d.rectangle((x0, S * 0.50, x1, S * 0.60), fill=c)                 # ฟูก
  d.rounded_rectangle((S * 0.28, S * 0.40, S * 0.44, S * 0.49), S * 0.03, fill=c)  # หมอน
  d.line((x0, S * 0.66, x1, S * 0.66), fill=c, width=lw)
  return im.resize((size, size), Image.LANCZOS)


def icon_area(size):
  im, d, S = icon_canvas(size)
  icon_ring(d, S)
  c = GOLD + (255,)
  lw = int(S * 0.05)
  a, b = S * 0.28, S * 0.72
  d.rectangle((a, a, b, b), outline=c, width=lw)
  p, q = S * 0.37, S * 0.63
  d.line((p, q, q, p), fill=c, width=lw)
  ah = S * 0.09
  d.polygon([(q + lw * 0.3, p - lw * 0.3), (q - ah, p - lw * 0.3), (q + lw * 0.3, p + ah)], fill=c)
  d.polygon([(p - lw * 0.3, q + lw * 0.3), (p + ah, q + lw * 0.3), (p - lw * 0.3, q - ah)], fill=c)
  return im.resize((size, size), Image.LANCZOS)


def icon_building(size):
  im, d, S = icon_canvas(size)
  icon_ring(d, S)
  c = GOLD + (255,)
  lw = int(S * 0.045)
  d.rectangle((S * 0.33, S * 0.24, S * 0.67, S * 0.74), outline=c, width=lw)
  for r in range(4):
    for k in range(2):
      x = S * (0.40 + k * 0.13)
      y = S * (0.31 + r * 0.095)
      d.rectangle((x, y, x + S * 0.07, y + S * 0.05), fill=c)
  d.line((S * 0.24, S * 0.74, S * 0.76, S * 0.74), fill=c, width=lw)
  return im.resize((size, size), Image.LANCZOS)


def icon_phone(size):
  im, d, S = icon_canvas(size)
  d.ellipse((0, 0, S - 1, S - 1), fill=GOLD + (255,))
  c = NAVY_DARK + (255,)
  rr = S * 0.24
  wdt = int(S * 0.11)
  cx, cy = S * 0.56, S * 0.44
  a0, a1 = 45, 225
  d.arc((cx - rr, cy - rr, cx + rr, cy + rr), a0, a1, fill=c, width=wdt)
  for ang in (a0, a1):
    ex = cx + (rr - wdt / 2) * math.cos(math.radians(ang))
    ey = cy + (rr - wdt / 2) * math.sin(math.radians(ang))
    er = S * 0.1
    d.ellipse((ex - er, ey - er, ex + er, ey + er), fill=c)
  return im.resize((size, size), Image.LANCZOS)


def icon_line(size):
  # ตัวอักษร "LINE" เรียบๆ ไม่ใช้โลโก้ทางการ
  im, d, S = icon_canvas(size)
  d.ellipse((0, 0, S - 1, S - 1), fill=GOLD + (255,))
  f = ImageFont.truetype(TTC, int(S * 0.27), index=FONT_IDX['bold'])
  bb = d.textbbox((0, 0), 'LINE', font=f)
  tw, th = bb[2] - bb[0], bb[3] - bb[1]
  d.text(((S - tw) / 2 - bb[0], (S - th) / 2 - bb[1]), 'LINE', font=f, fill=NAVY_DARK + (255,))
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

  def add(self, text, size, weight, color, x, baseline, align='left', shadow=False):
    p = os.path.join(self.tmp, 't%02d.txt' % len(self.items))
    with open(p, 'w', encoding='utf-8') as f:
      f.write(text)
    if align == 'center':
      xe = '%d-text_w/2' % round(x)
    elif align == 'right':
      xe = '%d-text_w' % round(x)
    else:
      xe = '%d' % round(x)
    sh = ':shadowcolor=0x050B18@0.7:shadowx=2:shadowy=3' if shadow else ''
    self.items.append("drawtext=fontfile='%s':textfile='%s':fontsize=%d:fontcolor=0x%s:x=%s:y=%d:y_align=baseline%s"
                      % (self.fonts[weight], p, size, color, xe, round(baseline), sh))

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


def main():
  tmp = tempfile.mkdtemp(prefix='photo_', dir=os.environ.get('PHOTO_TMP'))
  try:
    tx = Texts(tmp)
    cv = background()

    # ---- หัวภาพ: โลโก้ (วงทอง) + ชื่อโครงการทอง + รหัสในแคปซูลใต้ชื่อ ----
    ls = 122
    lx, ly = M, 40
    ring = Image.new('L', ((ls + 8) * SS, (ls + 8) * SS), 0)
    ImageDraw.Draw(ring).ellipse((0, 0, (ls + 8) * SS - 1, (ls + 8) * SS - 1), fill=255)
    ring = ring.resize((ls + 8, ls + 8), Image.LANCZOS)
    cv.paste(gold_gradient(ls + 8, ls + 8), (lx - 4, ly - 4), ring)
    logo = Image.open(LOGO).convert('RGBA').resize((ls, ls), Image.LANCZOS)
    cv.paste(logo, (lx, ly), logo)
    tx0 = lx + ls + 28
    ts = fit_size(tx, TITLE, 64, 'bold', W - M - tx0, 44)
    tx.add(TITLE, ts, 'bold', TXT_GOLD, tx0, 116, shadow=True)
    cs = 30
    cw = int(tx.width(CODE, cs, 'regular')) + 44
    cy0, ch = 132, 44
    cv.paste(gold_gradient(cw, ch), (tx0, cy0), rounded_mask(cw, ch, ch // 2))
    cv.paste(Image.new('RGB', (cw - 4, ch - 4), NAVY_DARK), (tx0 + 2, cy0 + 2), rounded_mask(cw - 4, ch - 4, ch // 2 - 2))
    tx.add(CODE, cs, 'regular', TXT_GOLD, tx0 + cw / 2, cy0 + 32, 'center')
    gold_line(cv, tx0 + cw + 18, W - M, cy0 + ch // 2, 2, False, True)

    # ---- รูปหลักเต็มกว้าง ขอบล่างโค้ง + รูปรองกรอบทองซ้อนมุมขวาล่าง ----
    place_hero(cv)
    iw, ih = 426, 284  # 3:2 ตรงกับรูป 16 (800x533) ไม่ต้องครอป
    inset_box = (W - M - iw, 636, iw, ih)
    framed_photo(cv, INSET, inset_box)

    # ---- แถวสเปกพร้อมไอคอน (ซ้าย ใต้รูปหลัก) ----
    isz = 58
    icons = {'bed': icon_bed, 'area': icon_area, 'building': icon_building}
    sy = 800
    for k, (ic, txt) in enumerate(SPECS):
      y = sy + k * 68
      paste_icon(cv, icons[ic](isz), M, y)
      tx.add(txt, 42, 'bold', TXT_WHITE, M + isz + 20, y + isz / 2 + 15, shadow=True)

    # ---- แถวล่าง: รูปเล็กซ้าย + แถบราคา + ช่องทางติดต่อ ----
    by0 = 1004
    sw_ = 292
    framed_photo(cv, SMALL, (M, by0, sw_, 1294 - by0))
    rx0 = M + sw_ + 26
    rx1 = W - M
    rw = rx1 - rx0
    # แถบราคาทอง
    pb_h = 88
    drop_shadow(cv, (rx0, by0, rw, pb_h), 12, off=6, blur=10, alpha=180)
    cv.paste(gold_gradient(rw, pb_h), (rx0, by0), rounded_mask(rw, pb_h, 12))
    lead_s, main_s = 34, 56
    lw_ = tx.width(PRICE_LEAD, lead_s, 'bold')
    mw_ = tx.width(PRICE_MAIN, main_s, 'bold')
    sp = 16
    px0 = rx0 + (rw - (lw_ + sp + mw_)) / 2
    pbase = by0 + pb_h / 2 + 20
    tx.add(PRICE_LEAD, lead_s, 'bold', TXT_NAVY, px0, pbase)
    tx.add(PRICE_MAIN, main_s, 'bold', TXT_NAVY, px0 + lw_ + sp, pbase)

    # ติดต่อ: โทร / Line ตัวหนาพร้อมไอคอน, WhatsApp / Email หัวข้อทอง ค่าขาว
    ci = 44
    rows = [(TEL, icon_phone, 1136), (LINE, icon_line, 1184)]
    for txt, ic, base in rows:
      paste_icon(cv, ic(ci), rx0 + 4, base - 32)
      fs = fit_size(tx, txt, 38, 'bold', rw - ci - 24, 32)
      tx.add(txt, fs, 'bold', TXT_WHITE, rx0 + ci + 20, base)
    gold_line(cv, rx0, rx1, 1202, 1, False, True)
    base = 1234
    for c in OTHER:
      lab, val = c.split(': ', 1)
      lab += ':'
      sz = 32
      lw = tx.width(lab, sz, 'bold')
      spw = tx.width(' ', sz, 'regular')
      tx.add(lab, sz, 'bold', TXT_GOLD, rx0 + 4, base)
      tx.add(val, sz, 'regular', TXT_SOFT, rx0 + 4 + lw + spw, base)
      base += 38

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
