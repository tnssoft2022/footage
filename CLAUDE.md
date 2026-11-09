# footage — วิดีโอทัวร์อสังหาริมทรัพย์จากรูปภาพ

โปรเจกต์นี้แปลงชุดรูปภาพของอสังหาริมทรัพย์แต่ละรายการให้เป็นวิดีโอทัวร์ (Ken Burns + crossfade + ดนตรีประกอบที่สร้างเอง) สำหรับส่งลูกค้า ตอบผู้ใช้เป็นภาษาไทย

## โครงสร้างโฟลเดอร์
- `~/Desktop/footage/assets/<รหัส>/` — รูปต้นฉบับของแต่ละรายการ (อยู่นอกโปรเจกต์) บางรายการมี `info.rtfd` เก็บข้อมูลประกาศ
- `~/Desktop/footage/example/` — ตัวอย่างอ้างอิง (`room_tour_music.mp4`)
- `uploads/<yyyymmddhhmmss>/` — งานที่รับเข้ามา (โดย agent `footage-intake`): `images/` (01.jpg, 02.jpg, … ปรับแสงให้เท่ากันแล้ว ใช้เรนเดอร์), `originals/` (รูปเดียวกันก่อนปรับแสง), `info.txt` (ข้อมูลประกาศ), `brief.md` (brief สำหรับ footage-assistant) เก็บไว้หลังเรนเดอร์เพื่อใช้แก้หรือเรนเดอร์ซ้ำ
- `videos/<รหัส>.mp4` — วิดีโอที่เสร็จแล้ว
- `work/make_video.py` — สคริปต์ต้นแบบ **ห้ามแก้ไฟล์นี้** ให้คัดลอกไปใช้ต่อรายการ
- `work/<รหัส>/` — งานของแต่ละรายการ: `timeline.json` (เวลาช็อตและข้อความ), `make_edit.py` + `edit/edit.mp4` (วิดีโอดิบ ไม่มีข้อความ), `make_effect.py` + `effect/overlay.mov` (เลเยอร์ข้อความโปร่งใส) + `effect/grade.txt` (ฟิลเตอร์สี/เอฟเฟค), `merge.sh` (คำสั่งรวม) งานเก่าก่อน 2026-11-09 ใช้ `make_video.py` ไฟล์เดียว
- `.claude/roles/`, `.claude/agents/` — บทบาท `footage`, agent `footage-intake` (รับงาน), `footage-assistant` (วางไทม์ไลน์และรวมงาน), `footage-assistant-editor` (รูป → วิดีโอ + เพลง), `footage-assistant-effect` (ข้อความและเอฟเฟค) และ `footage-auditor` (ตรวจวิดีโอ, อ่านอย่างเดียว)

## การรันสคริปต์
- สคริปต์ (`make_video.py`, `make_edit.py`, `make_effect.py`) ต้องใช้ numpy (และ fonttools สำหรับข้อความ): สร้าง venv ชั่วคราวใน scratchpad แล้ว `pip install numpy` อย่าติดตั้งลงระบบ
- รัน: `<venv>/bin/python work/<รหัส>/make_video.py <ffmpeg-path>`
- ffmpeg: `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg` (keg-only ต้องใช้ path เต็ม) ffprobe อยู่โฟลเดอร์เดียวกัน ถ้าไม่มีให้ใช้ `imageio-ffmpeg` ใน venv
- ค่าที่ต้องแก้ในสำเนาสคริปต์: `CODE`, path รูป (`IMG`), path output (`OUT`) และ `ORDER` (ชื่อไฟล์ + ทิศกล้อง in/out/left/right) โค้ดใช้ indent 2 ช่อง

## ข้อความภาษาไทยและข้อมูลประกาศ
- อ่านข้อมูลประกาศด้วย `textutil -convert txt -stdout <assets>/<รหัส>/info.rtfd/TXT.rtf`
- ฟอนต์ไทยใช้ Sukhumvit Set (`/System/Library/Fonts/Supplemental/SukhumvitSet.ttc`) ไม่ใช้ Thonburi เพราะ Thonburi มีช่องว่างโผล่หน้า ใ/ไ
- ffmpeg drawtext หาฟอนต์ระบบผ่าน `font=` ไม่เจอ (ตัวไทยออกมาเป็นสี่เหลี่ยม) และเลือกฟอนต์ย่อยใน .ttc ไม่ได้ ต้องใช้ fonttools แตกฟอนต์ย่อยเป็น .ttf ชั่วคราวแล้วส่งผ่าน `fontfile=`
- ffmpeg-full เป็นเวอร์ชัน 9 ซึ่งไม่มี `-filter_complex_script` แล้ว ให้ใช้ `-/filter_complex <ไฟล์>` แทน

## สเปกมาตรฐาน
- 1920x1080, 30fps, H.264 mp4, เสียง AAC stereo 192k เฉลี่ยประมาณ -18 dB ไม่มี clipping
- ข้อความรหัสอสังหาริมทรัพย์เปิดต้นคลิป
- ดนตรีบรรเลงที่สร้างเอง ไม่มีเสียงพากย์ ห้ามใช้เพลงที่มีลิขสิทธิ์

## กติกาทั่วไป
- อย่าวางไฟล์ไว้ที่รากโปรเจกต์โดยตรง: วิดีโอไปที่ `videos/` รูปที่รับเข้ามาไปที่ `uploads/<timestamp>/` สคริปต์ไปที่ `work/<รหัส>/`
- เมื่องานเสร็จ ลบไฟล์ชั่วคราว (เฟรม, venv) แต่เก็บสคริปต์ timeline.json และไฟล์กลาง (edit.mp4, overlay.mov, grade.txt) ใน `work/<รหัส>/` ไว้สำหรับแก้ครั้งต่อไป
- ก่อนบอกว่าวิดีโอเสร็จ ต้องตรวจไฟล์จริงด้วย ffprobe (ขนาด, fps, codec, ความยาว, เสียง)
