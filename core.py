"""
Ядро настольной утилиты Karaoke Frames.

Два режима:
  1. reveal — субтитры уже нарисованы на картинке: детектируем строки и слова,
     затираем их фоном, затем открываем по одному слову за кадр,
     копируя пиксели оригинала (пиксельно точный результат).
  2. font — субтитры не нарисованы: рисуем текст шрифтом поверх базового кадра.

Только numpy + Pillow, без сетевых зависимостей.
"""

from __future__ import annotations

import json
import os
import re
import sys
import struct
import threading
import time
from collections import Counter

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
DEFAULT_SETTINGS = {"mode": "reveal", "sound": True, "sound_style": "short",
                    "theme": "paper"}


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {**DEFAULT_SETTINGS, **{k: v for k, v in data.items()
                                       if k in DEFAULT_SETTINGS}}
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _beep(freq, ms):
    try:
        import winsound
        winsound.Beep(freq, ms)
    except Exception:
        pass


def play_sound(kind="done", style="short"):
    """Звуковой алерт в отдельном потоке (не блокирует UI)."""
    if style == "off":
        return
    if not sys.platform.startswith("win"):
        return

    seq = {
        ("done", "short"):   [(880, 80), (1318, 110)],
        ("done", "melody"):  [(659, 90), (880, 90), (1175, 90), (1760, 150)],
        ("done", "system"):  "system",
        ("error", "short"):  [(392, 120), (311, 160)],
        ("error", "melody"): [(330, 100), (262, 100), (220, 220)],
        ("error", "system"): "hand",
    }.get((kind, style))

    def run():
        if seq == "system":
            try:
                import winsound
                winsound.MessageBeep(
                    winsound.MB_ICONASTERISK if kind == "done" else winsound.MB_ICONHAND)
            except Exception:
                pass
            return
        if seq == "hand":
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONHAND)
            except Exception:
                pass
            return
        for freq, ms in (seq or []):
            _beep(freq, ms)
            time.sleep(0.02)

    threading.Thread(target=run, daemon=True).start()

FONT_CANDIDATES = [
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/verdana.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


# ================= общие helpers =================

def hex_to_rgb(hx):
    hx = hx.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", hx):
        raise ValueError(f"Неверный цвет: {hx}")
    return tuple(int(hx[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(v))) for v in rgb))


def load_font(size, candidates=FONT_CANDIDATES):
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def list_frames(out_dir):
    files = [f for f in os.listdir(out_dir)
             if f.lower().endswith(".png") and re.match(r"frame_\d+\.png", f, re.I)]
    return [os.path.join(out_dir, f) for f in sorted(files)]


def dominant_color(img, sample=220):
    """Самый частый цвет изображения — обычно фон карточки со скриншота."""
    small = img.copy()
    small.thumbnail((sample, sample))
    cnt = Counter(small.getdata())
    return tuple(int(c) for c in cnt.most_common(1)[0][0])


# ================= буфер обмена =================

IS_WINDOWS = sys.platform == "win32"


def clipboard_image_put(img):
    """Кладёт изображение в системный буфер как CF_DIB (Windows). True при успехе."""
    if not IS_WINDOWS:
        return False
    img = img.convert("RGB")
    w, h = img.size
    flipped = img.transpose(Image.FLIP_TOP_BOTTOM)   # DIB: строки снизу вверх
    b, g, r = flipped.split()                        # DIB: порядок BGR
    raw = Image.merge("RGB", (b, g, r)).tobytes()
    stride = (w * 3 + 3) // 4 * 4                    # строки выровнены на 4 байта
    if w * 3 != stride:
        rows = bytearray()
        for y in range(h):
            s = y * w * 3
            rows += raw[s:s + w * 3] + b"\x00" * (stride - w * 3)
        rows = bytes(rows)
    else:
        rows = raw
    dib = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(rows), 0, 0, 0, 0) + rows
    try:
        import ctypes
        import io

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        def _put(fmt, payload):
            hglob = kernel32.GlobalAlloc(0x0042, len(payload))  # GMEM_MOVEABLE|ZEROINIT
            if not hglob:
                return False
            ptr = kernel32.GlobalLock(hglob)
            if not ptr:
                kernel32.GlobalFree(hglob)
                return False
            ctypes.memmove(ptr, payload, len(payload))
            kernel32.GlobalUnlock(hglob)
            user32.SetClipboardData(fmt, hglob)
            return True

        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            _put(8, dib)                       # CF_DIB (BGR, читается всеми программами)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            fmt_png = user32.RegisterClipboardFormatW("PNG")
            if fmt_png:
                _put(fmt_png, buf.getvalue())  # PNG-формат (Chrome, msg-редакторы)
        finally:
            user32.CloseClipboard()
        return True
    except Exception:
        return False


def clipboard_image_get():
    """Достаёт изображение из буфера (скриншот из Win+Shift+S, копия файла)."""
    try:
        from PIL import ImageGrab
        res = ImageGrab.grabclipboard()
    except Exception:
        return None
    if res is None:
        return None
    if isinstance(res, (list, tuple)):          # буфер со списком файлов
        for p in res:
            try:
                return Image.open(p).convert("RGB")
            except Exception:
                continue
        return None
    return res.convert("RGB")


# ================= режим reveal (детекция с картинки) =================

def detect_words(arr, bg, ink_threshold=45, erase_threshold=14,
                 space_gap=10, dilate=2, min_pixels=4,
                 small_fragment_h=12, fragment_gap=20, white_min_channel=200):
    """
    Ищет строки белого текста и режет их на слова.
    arr: numpy HxWx3 uint8, bg: (r,g,b)
    Возвращает (lines, words, word_masks):
      lines — список (y0,y1),
      words — список (x0,y0,x1,y1),
      word_masks — список (box, submask) для попиксельного копирования слова.
    """
    diff = np.abs(arr.astype(np.int16) - np.array(bg, dtype=np.int16)).max(axis=2)
    ink = diff > ink_threshold
    h, w = ink.shape

    row_ink = ink.sum(axis=1)
    bands = []
    y = 0
    while y < h:
        if row_ink[y] > min_pixels:
            y0 = y
            while y < h and row_ink[y] > min_pixels:
                y += 1
            bands.append({"y0": y0, "y1": y - 1})
        else:
            y += 1

    for b in bands:
        col_ink = ink[b["y0"]:b["y1"] + 1].any(axis=0)
        xs = np.flatnonzero(col_ink)
        b["xs"] = set(xs.tolist())
        seg = arr[b["y0"]:b["y1"] + 1][ink[b["y0"]:b["y1"] + 1]]
        # доля «белых» пикселей: у строк текста она высока, у эмодзи/пилюль — нет
        b["white_ratio"] = float(((seg > 150).all(axis=1)).mean()) if len(seg) else 0.0

    # Мелкие фрагменты (диакритика, «й») цепляем к следующей строке с тем же x
    for i, b in enumerate(bands):
        if b["y1"] - b["y0"] + 1 > small_fragment_h:
            continue
        for c in bands[i + 1:]:
            if c["y0"] - b["y1"] > fragment_gap:
                break
            if c.get("attached"):
                continue
            if min(b["xs"]) <= max(c["xs"]) and max(b["xs"]) >= min(c["xs"]):
                c["y0"] = min(c["y0"], b["y0"])
                c["xs"].update(b["xs"])
                b["attached"] = True
                break

    lines, words, word_masks = [], [], []
    for b in bands:
        if b.get("attached"):
            continue
        if b["white_ratio"] < 0.5:
            continue  # не текст (заголовок/реакции/подписи)
        y0, y1 = b["y0"], b["y1"]
        lines.append((y0, y1))
        xs = sorted(b["xs"])
        # разбиение по зазорам
        chunks = []
        cur = [xs[0], xs[0]]
        for x in xs[1:]:
            if x - cur[1] >= space_gap:
                chunks.append(tuple(cur))
                cur = [x, x]
            else:
                cur[1] = x
        chunks.append(tuple(cur))
        for wx0, wx1 in chunks:
            rows = np.flatnonzero(ink[y0:y1 + 1, wx0:wx1 + 1].any(axis=1))
            wy0, wy1 = int(y0 + rows.min()), int(y0 + rows.max())
            x0, y0p, x1, y1p = int(wx0 - dilate), wy0 - dilate, int(wx1 + dilate), wy1 + dilate
            x0c, y0c = max(0, x0), max(0, y0p)
            x1c, y1c = min(w, x1 + 1), min(h, y1p + 1)
            sub = ink[y0c:y1c, x0c:x1c]
            words.append((x0, y0p, x1, y1p))
            word_masks.append(((x0c, y0c, x1c, y1c), sub))
    return lines, words, word_masks


def render_reveal(input_path, out_dir, bg, ink_threshold=45, erase_threshold=14,
                  space_gap=10, dilate=2, progress=None):
    """Генерирует кадры reveal-режима. Возвращает список путей PNG."""
    os.makedirs(out_dir, exist_ok=True)
    img = Image.open(input_path).convert("RGB")
    original = np.asarray(img)
    base = original.copy()

    lines, words, word_masks = detect_words(original, bg, ink_threshold, erase_threshold,
                                            space_gap, dilate)
    if not words:
        raise RuntimeError("Не найдено строк текста. Проверьте цвет фона и пороги.")

    # затираем текст, восстанавливая локальный фон (он может быть с градиентом)
    y_min = min(y0 for y0, _ in lines)
    y_max = max(y1 for _, y1 in lines)
    bg_arr = np.array(bg, dtype=np.int16)
    diff = np.abs(base.astype(np.int16) - bg_arr).max(axis=2)

    # зоны слов (с небольшим запасом) — там фон должен стать идеально ровным,
    # иначе от нераскрытых строк остаются «призраки» из антиалиасинга
    box_zone = np.zeros(diff.shape, dtype=bool)
    for wx0, wy0, wx1, wy1 in words:
        box_zone[max(0, wy0 - 3):wy1 + 4, max(0, wx0 - 3):wx1 + 4] = True
    region = (diff > erase_threshold) | box_zone
    region = region[y_min:y_max + 1]
    for i, y in enumerate(range(y_min, y_max + 1)):
        fix = region[i]
        if not fix.any():
            continue
        row = base[y]
        keep = ~fix
        n = len(row)
        idx = np.arange(n)
        left = np.maximum.accumulate(np.where(keep, idx, -1))
        right = np.minimum.accumulate(np.where(keep, idx, n))
        # предпочитаем ближайший слева, иначе ближайший справа
        nearest = np.where(left >= 0, left, right)
        if nearest.max() >= n:
            nearest = np.clip(nearest, 0, n - 1)
        colors = row[nearest]
        row = row.copy()
        row[fix] = colors[fix]
        base[y] = row

    paths = []
    mask = np.zeros(original.shape[:2], dtype=bool)
    total = len(word_masks)
    for i, (box, sub) in enumerate(word_masks, 1):
        x0, y0, x1, y1 = box
        mask[y0:y1, x0:x1] |= sub          # пиксели самого слова, без фоновых швов
        frame = np.where(mask[..., None], original, base)
        path = os.path.join(out_dir, f"frame_{i:03d}.png")
        Image.fromarray(frame).save(path)
        paths.append(path)
        if progress:
            progress(i, total)
    return paths, words, lines


# ================= режим font (рисуем текст) =================

def wrap_words(words, font, max_width):
    lines, cur = [], ""
    for word in words:
        test = (cur + " " + word).strip()
        if font.getbbox(test)[2] - font.getbbox(test)[0] <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def render_font(input_path, out_dir, text, box, text_color=(255, 255, 255),
                bg_color=None, font_size=24, font_path=None, title="",
                title_color=(137, 185, 223), title_box=None, title_font_size=20,
                padding=10, line_spacing=8, progress=None):
    """Рисует субтитры шрифтом. Возвращает список путей PNG."""
    os.makedirs(out_dir, exist_ok=True)
    words = text.split()
    if not words:
        raise RuntimeError("Текст пустой.")

    img = Image.open(input_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    x1, y1, x2, y2 = [int(v) for v in box]
    if bg_color is not None:
        draw.rectangle((x1, y1, x2, y2), fill=tuple(bg_color))

    font = load_font(font_size, [font_path] + FONT_CANDIDATES if font_path else FONT_CANDIDATES)
    title_font = load_font(title_font_size) if title else None

    text_x, text_y = x1 + padding, y1 + padding
    max_width = max(10, x2 - x1 - padding * 2)
    line_height = font_size + line_spacing
    if title_box and title_font:
        tx1, ty1, tx2, ty2 = [int(v) for v in title_box]
        title_x, title_y = tx1 + padding, ty1 + padding
    else:
        title_x = title_y = None

    paths = []
    for i in range(1, len(words) + 1):
        frame = img.copy()
        d = ImageDraw.Draw(frame)
        if title and title_font and title_x is not None:
            d.text((title_x, title_y), title, fill=tuple(title_color), font=title_font)
        lines = wrap_words(words[:i], font, max_width)
        y = text_y
        for line in lines:
            d.text((text_x, y), line, fill=tuple(text_color), font=font)
            y += line_height
        path = os.path.join(out_dir, f"frame_{i:03d}.png")
        frame.save(path)
        paths.append(path)
        if progress:
            progress(i, len(words))
    return paths
