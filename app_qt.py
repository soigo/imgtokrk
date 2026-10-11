"""
Image to Karaoke — desktop (PyQt5)

Айдентика: кремовая бумага + чёрная графика (по референсу).
Крупные шрифты, DPI-масштабирование, панель с прокруткой.

Ядро (детекция слов, раскрытие, буфер, звук) — в core.py рядом.

Запуск:  run_qt.bat   (или: python app_qt.py)
Требуется: pip install PyQt5 Pillow numpy
"""

import os
import sys
import math
import time
import traceback

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QRectF, QPointF
from PyQt5.QtGui import (QFont, QColor, QPainter, QPen, QPixmap, QImage, QCursor,
                         QKeySequence, QPainterPath, QIcon)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QLineEdit, QFileDialog, QSpinBox,
    QColorDialog, QProgressBar, QFrame, QSlider, QCheckBox, QComboBox,
    QMessageBox, QShortcut, QSizePolicy, QStyle, QScrollArea
)

from PIL import Image
import core

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# ── масштаб интерфейса (заполняется в main() по DPI экрана) ──
_SCALE = 1.0


def S(v):
    """Масштабирует размер под DPI экрана."""
    return max(1, int(round(v * _SCALE)))


def log_uncaught(exc_type, exc, tb):
    with open(os.path.join(APP_DIR, "app_error.log"), "a", encoding="utf-8") as f:
        f.write("".join(traceback.format_exception(exc_type, exc, tb)) + "\n")


sys.excepthook = log_uncaught


# ============================================================
# 1. АЙДЕНТИКА — бумага/чернила, две темы
# ============================================================

PALETTES = {
    "paper": {
        "bg_main":     "#F0E8D6",   # кремовая бумага
        "rail":        "#2F4A75",   # глубокий синий (как в шаблоне)
        "rail_deep":   "#26406A",   # приподнятые поверхности на рейле
        "rail_text":   "#F4EDDD",   # кремовый текст на синем
        "rail_dim":    "#B9C4D8",   # приглушённый текст на синем
        "card":        "#F6F0E2",   # кремовая карточка (превью)
        "raised":      "#E6DCC4",
        "border":      "#5A4326",   # тёплые коричневые чернила
        "text_main":   "#2E2418",
        "text_second": "#7A6A50",
        "field":       "#FFFFFF",
        "accent":      "#A87B54",   # тёплый тан/дерево
    },
    "ink": {
        "bg_main":     "#241D15",   # тёмный кофе
        "rail":        "#1B2A44",
        "rail_deep":   "#22345A",
        "rail_text":   "#F0E8D6",
        "rail_dim":    "#93A2BC",
        "card":        "#2E2618",
        "raised":      "#3A3020",
        "border":      "#D8C9A8",
        "text_main":   "#F0E8D6",
        "text_second": "#B0A184",
        "field":       "#171208",
        "accent":      "#C99B6E",
    },
}

COLORS = dict(PALETTES["paper"])
_THEME = "paper"


def make_noise_tile(theme="paper", size=128, alpha=7):
    """Едва заметная бумажная текстура — тайл для drawTiledPixmap."""
    import numpy as np
    rng = np.random.default_rng(11)
    noise = rng.integers(0, 255, size=(size, size), dtype=np.uint8)
    img = np.zeros((size, size, 4), dtype=np.uint8)
    if theme == "paper":
        img[..., :3] = 23            # тёмные вкрапления
    else:
        img[..., :3] = 242           # светлые вкрапления
    img[..., 3] = (noise < 96) * alpha
    qimg = QImage(img.tobytes(), size, size, 4 * size, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


def build_stylesheet():
    c = COLORS
    return f"""
    QMainWindow, QWidget {{
        background-color: {c['bg_main']};
        color: {c['text_main']};
        font-family: 'Franklin Gothic Medium', 'Franklin Gothic', 'Segoe UI', sans-serif;
        font-size: {S(15)}px;
    }}

    /* ── синий рейл (как синие блоки в шаблоне) ── */
    QFrame#Rail {{
        background-color: {c['rail']};
        border: {S(1)}px solid {c['rail_deep']};
        border-radius: {S(16)}px;
    }}
    QFrame#Rail QLabel {{ color: {c['rail_text']}; background: transparent; }}
    QFrame#Rail QLabel#Subtitle {{ color: {c['rail_dim']}; }}
    QFrame#Rail QLabel#Section {{ color: {c['accent']}; }}
    QFrame#Rail QLabel#Mono {{ color: {c['rail_dim']}; font-family: 'Consolas', monospace; font-size: {S(13)}px; }}
    QFrame#Rail QLabel#Title {{
        font-family: 'Bodoni MT', 'Playfair Display', 'Didot', Georgia, serif;
        font-size: {S(30)}px;
        font-weight: 700;
        color: {c['rail_text']};
        padding: {S(2)}px 0;
    }}

    /* ── кремовая сцена превью ── */
    QFrame#Stage {{
        background-color: {c['card']};
        border: {S(1)}px solid {c['border']};
        border-radius: {S(16)}px;
    }}
    QFrame#Stage QLabel {{ color: {c['text_main']}; background: transparent; }}
    QFrame#Stage QLabel#Subtitle {{ color: {c['text_second']}; }}
    QFrame#Stage QLabel#Mono {{
        color: {c['text_second']};
        font-family: 'Consolas', monospace;
        font-size: {S(13)}px;
    }}

    /* ── поля ввода (белые, как в шаблоне) ── */
    QLineEdit, QTextEdit, QSpinBox, QComboBox {{
        background-color: {c['field']};
        color: {c['text_main']};
        border: {S(1)}px solid {c['rail_deep']};
        border-radius: {S(8)}px;
        padding: {S(8)}px {S(10)}px;
        font-size: {S(15)}px;
        selection-background-color: {c['accent']};
        selection-color: {c['card']};
    }}
    QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
        border: {S(2)}px solid {c['accent']};
    }}
    QComboBox::drop-down {{ border: none; width: {S(20)}px; }}
    QComboBox QAbstractItemView {{
        background-color: {c['field']};
        color: {c['text_main']};
        border: {S(1)}px solid {c['rail_deep']};
        selection-background-color: {c['accent']};
        selection-color: {c['card']};
    }}

    /* ── кнопки на рейле: аутлайн кремового ── */
    QFrame#Rail QPushButton {{
        background-color: transparent;
        color: {c['rail_text']};
        border: {S(1)}px solid {c['rail_dim']};
        border-radius: {S(8)}px;
        padding: {S(9)}px {S(14)}px;
        font-size: {S(14)}px;
        font-weight: 600;
    }}
    QFrame#Rail QPushButton:hover {{
        background-color: {c['rail_deep']};
        border: {S(1)}px solid {c['rail_text']};
    }}
    QFrame#Rail QPushButton:pressed {{
        background-color: {c['rail_text']};
        color: {c['rail']};
    }}
    QFrame#Rail QPushButton:disabled {{ color: {c['rail_dim']}; border-color: {c['rail_deep']}; }}
    QFrame#Rail QPushButton:focus {{ border: {S(2)}px solid {c['accent']}; }}

    /* ── главная кнопка: тёплое дерево ── */
    QPushButton#Primary {{
        background-color: {c['accent']};
        color: {c['card']};
        border: {S(1)}px solid {c['accent']};
        font-size: {S(15)}px;
        font-weight: 700;
        padding: {S(13)}px {S(18)}px;
        border-radius: {S(8)}px;
    }}
    QPushButton#Primary:hover {{ background-color: {c['rail_text']}; border-color: {c['rail_text']}; color: {c['rail']}; }}
    QPushButton#Primary:pressed {{ background-color: {c['border']}; border-color: {c['border']}; }}
    QPushButton#Primary:disabled {{ background-color: {c['rail_deep']}; color: {c['rail_dim']}; border-color: {c['rail_deep']}; }}

    /* ── сегменты режима ── */
    QPushButton#SegOn {{
        background-color: {c['rail_text']};
        color: {c['rail']};
        border: {S(1)}px solid {c['rail_text']};
        font-weight: 700;
    }}
    QPushButton#SegOff {{
        background-color: transparent;
        color: {c['rail_dim']};
        border: {S(1)}px solid {c['rail_dim']};
    }}

    /* ── прогресс ── */
    QProgressBar {{
        background-color: {c['rail_deep']};
        border: {S(1)}px solid {c['rail_dim']};
        border-radius: {S(8)}px;
        height: {S(22)}px;
        text-align: center;
        font-family: 'Consolas', monospace;
        font-size: {S(12)}px;
        color: {c['rail_text']};
    }}
    QProgressBar::chunk {{ background-color: {c['accent']}; border-radius: {S(7)}px; }}

    /* ── слайдеры ── */
    QSlider::groove:horizontal {{
        background: {c['rail_deep']};
        border: {S(1)}px solid {c['rail_dim']};
        border-radius: {S(6)}px;
        height: {S(10)}px;
    }}
    QSlider::handle:horizontal {{
        background: {c['accent']};
        border: none;
        width: {S(18)}px;
        margin: {-S(6)}px 0;
        border-radius: {S(9)}px;
    }}
    QSlider::sub-page:horizontal {{ background: {c['rail_dim']}; border-radius: {S(6)}px; }}

    /* ── чекбокс ── */
    QCheckBox {{ spacing: {S(8)}px; font-size: {S(14)}px; color: {c['rail_text']}; }}
    QCheckBox::indicator {{
        width: {S(17)}px; height: {S(17)}px;
        border: {S(1)}px solid {c['rail_dim']};
        border-radius: {S(4)}px;
        background: {c['rail_deep']};
    }}
    QCheckBox::indicator:checked {{ background-color: {c['accent']}; border-color: {c['accent']}; }}

    /* ── скролл ── */
    QScrollBar:vertical {{ background: {c['rail']}; width: {S(12)}px; border-radius: {S(6)}px; }}
    QScrollBar::handle:vertical {{ background: {c['rail_dim']}; border-radius: {S(6)}px; min-height: {S(24)}px; }}
    QScrollBar::handle:vertical:hover {{ background: {c['accent']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
    QScrollBar:horizontal {{ height: 0; }}
    """
def pil_to_qpixmap(pil_img):
    """Надёжная конвертация: через файл (кастомный drawPixmap на mixed-DPI
    конфигурациях не композитится, QLabel.setPixmap работает всегда)."""
    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")
    try:
        pil_img.save(_SRC_TMP, "PNG")
        return QPixmap(_SRC_TMP)
    except Exception:
        data = pil_img.tobytes()
        qimg = QImage(data, pil_img.width, pil_img.height, 3 * pil_img.width,
                      QImage.Format_RGB888)
        return QPixmap.fromImage(qimg.copy())


def chip_style(hexv, rounded=6):
    return (f"background-color: {hexv}; "
            f"border: {S(1)}px solid {COLORS['border']}; "
            f"border-radius: {S(rounded)}px;")


class TrackLabel(QWidget):
    """Заголовок секции капсом с ручной разрядкой букв (letter-spacing)."""

    def __init__(self, text, size=12, color=None, tracking=None, parent=None):
        super().__init__(parent)
        self.text = text.upper()
        self.size = S(size)
        self.tracking = S(2.0 if tracking is None else tracking)
        self.color = QColor(color or COLORS["accent"])
        self.font = QFont()
        self.font.setFamilies(["Franklin Gothic Demi", "Franklin Gothic Medium",
                               "Segoe UI", "sans-serif"])
        self.font.setPixelSize(self.size)
        self.font.setBold(True)
        fm = self.fontMetrics()
        self.width_px = sum(fm.horizontalAdvance(ch) for ch in self.text) \
            + self.tracking * max(0, len(self.text) - 1)
        self.setFixedHeight(fm.height() + S(4))

    def sizeHint(self):
        from PyQt5.QtCore import QSize
        return QSize(int(self.width_px), self.height())

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(self.font)
        p.setPen(QPen(self.color))
        fm = p.fontMetrics()
        x, baseline = 0, fm.ascent() + S(2)
        for ch in self.text:
            p.drawText(int(x), baseline, ch)
            x += fm.horizontalAdvance(ch) + self.tracking


class Logo(QWidget):
    """Марка в духе референса: ракета маркером + пунктирный след."""

    def __init__(self, size=40, color=None, parent=None):
        super().__init__(parent)
        self.color = QColor(color or COLORS["rail_text"])
        self.accent = QColor(COLORS["accent"])
        self.setFixedSize(S(size), S(size))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        ink = self.color
        acc = self.accent
        s = min(self.width(), self.height())
        u = s / 40.0
        pen = QPen(ink, max(1.6, 2.4 * u))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(ink)

        # корпус ракеты (лёгкая неправильность линий — handmade)
        body = QPainterPath()
        body.moveTo(20 * u, 2 * u)
        body.cubicTo(27 * u, 9 * u, 29 * u, 17 * u, 28 * u, 25 * u)
        body.cubicTo(24 * u, 29 * u, 16 * u, 29.5 * u, 12 * u, 25 * u)
        body.cubicTo(11 * u, 17 * u, 13 * u, 9 * u, 20 * u, 2 * u)
        p.drawPath(body)

        # иллюминатор
        p.setBrush(QColor(COLORS["card"]))
        p.drawEllipse(int(17 * u), int(10 * u), int(6 * u), int(6 * u))

        # стабилизаторы
        p.setBrush(ink)
        fins = QPainterPath()
        fins.moveTo(13 * u, 20 * u)
        fins.lineTo(7 * u, 30 * u)
        fins.lineTo(13 * u, 29 * u)
        fins.closeSubpath()
        fins.moveTo(27 * u, 20 * u)
        fins.lineTo(33 * u, 30 * u)
        fins.lineTo(27 * u, 29 * u)
        fins.closeSubpath()
        p.drawPath(fins)

        # след — пунктирная дуга акцентом
        p.setPen(QPen(acc, max(1.6, 2.2 * u), Qt.DashLine, Qt.RoundCap))
        trail = QPainterPath()
        trail.moveTo(24 * u, 32 * u)
        trail.cubicTo(33 * u, 35 * u, 38 * u, 31 * u, 38 * u, 22 * u)
        p.drawPath(trail)


class IconButton(QPushButton):
    """Кнопки транспорта: линейные иконки, нарисованные вручную."""

    def __init__(self, icon, command=None, size=44, color=None, parent=None):
        super().__init__(parent)
        self.icon = icon
        self.color = QColor(color or COLORS["rail_text"])
        if command:
            self.clicked.connect(command)
        self.setFixedSize(S(size), S(size))
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = min(self.width(), self.height())
        hovered = self.underMouse()
        pressed = self.isDown()
        col = QColor(COLORS["accent"]) if (hovered or pressed) else self.color
        w = max(2.0, 2.6 * s / 44.0)
        p.setPen(QPen(col, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))

        cx, cy, r = s / 2, s / 2, s * 0.26
        if self.icon == "play":
            path = QPainterPath()
            path.moveTo(cx - r * 0.6, cy - r)
            path.lineTo(cx + r, cy)
            path.lineTo(cx - r * 0.6, cy + r)
            path.closeSubpath()
            if pressed:
                p.setBrush(col)
            p.drawPath(path)
        elif self.icon == "pause":
            for dx in (-r * 0.55, r * 0.55):
                p.drawLine(int(cx + dx - w / 2), int(cy - r),
                           int(cx + dx - w / 2), int(cy + r))
        elif self.icon == "stop":
            if pressed:
                p.setBrush(col)
            p.drawRect(QRectF(cx - r * 0.8, cy - r * 0.8,
                              r * 1.6, r * 1.6))
        elif self.icon == "prev":
            path = QPainterPath()
            path.moveTo(cx - r * 0.2, cy - r)
            path.lineTo(cx - r * 1.2, cy)
            path.lineTo(cx - r * 0.2, cy + r)
            path.closeSubpath()
            p.drawPath(path)
            p.drawLine(int(cx + r * 1.0), int(cy - r),
                       int(cx + r * 1.0), int(cy + r))
        elif self.icon == "theme":
            # полумесяц/солнце — переключатель темы
            if _THEME == "paper":
                p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
                p.setBrush(QColor(COLORS["card"]))
                p.setPen(Qt.NoPen)
                p.drawEllipse(QRectF(cx - r * 0.2, cy - r * 1.2,
                                     r * 2, r * 2))
            else:
                for i in range(8):
                    ang = i * 45
                    rad = math.radians(ang)
                    p.drawLine(int(cx + math.cos(rad) * r * 0.5),
                               int(cy + math.sin(rad) * r * 0.5),
                               int(cx + math.cos(rad) * r),
                               int(cy + math.sin(rad) * r))
                p.drawEllipse(QRectF(cx - r * 0.3, cy - r * 0.3,
                                     r * 0.6, r * 0.6))
        super().paintEvent(e)


# ============================================================
# 2. ПОТОК ГЕНЕРАЦИИ
# ============================================================

class GenWorker(QThread):
    progress = pyqtSignal(int, int)
    ok = pyqtSignal(int, str)
    fail = pyqtSignal(str)

    def __init__(self, mode, params):
        super().__init__()
        self.mode, self.params = mode, params

    def run(self):
        try:
            cb = lambda i, t: self.progress.emit(i, t)
            if self.mode == "reveal":
                paths, words, lines = core.render_reveal(progress=cb, **self.params)
                msg = f"Готово: {len(paths)} кадров · {len(words)} слов · {len(lines)} строк"
            else:
                paths = core.render_font(progress=cb, **self.params)
                msg = f"Готово: {len(paths)} кадров · {len(paths)} слов"
            self.ok.emit(len(paths), msg)
        except Exception as e:
            self.fail.emit(str(e))


# ============================================================
# 3. ПРЕВЬЮ
# ============================================================

class Preview(QWidget):
    """Рзображение — нативный QLabel (надёжно на any-DPI конфигурациях),
    поверх — прозрачный оверлей с рамками слов, чипом зума и областью текста."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setMinimumSize(S(460), S(360))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.pixmap = None
        self.img_w = self.img_h = 0
        self.view_scale, self.view_off = 1.0, QPointF(0, 0)
        self.zoom, self.pan = 1.0, QPointF(0, 0)
        self.panning, self._pan_from, self._drag_from = False, None, None

        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background: transparent;")
        self.label.hide()

    # ── геометрия вида ──
    def target_rect(self):
        if not self.pixmap:
            return QRectF()
        dw, dh = self.img_w * self.view_scale, self.img_h * self.view_scale
        ox = (self.width() - dw) / 2 if dw <= self.width() \
            else min(0, max(self.width() - dw, self.pan.x()))
        oy = (self.height() - dh) / 2 if dh <= self.height() \
            else min(0, max(self.height() - dh, self.pan.y()))
        self.view_off = QPointF(ox, oy)
        return QRectF(ox, oy, dw, dh)

    def _layout_image(self):
        """Пересчитывает размер и позицию QLabel с картинкой."""
        if not self.pixmap:
            return
        pad = S(10)
        avail_w = max(1, self.width() - pad * 2)
        avail_h = max(1, self.height() - pad * 2)
        self.view_scale = min(avail_w / max(1, self.img_w),
                              avail_h / max(1, self.img_h)) * self.zoom
        t = self.target_rect()
        dw, dh = max(1, int(t.width())), max(1, int(t.height()))
        self.label.setGeometry(int(t.x()), int(t.y()), dw, dh)
        scaled = self.pixmap.scaled(dw, dh, Qt.KeepAspectRatio,
                                    Qt.SmoothTransformation)
        self.label.setPixmap(scaled)
        self.label.show()
        self.label.raise_()

    def img_to_view(self, x0, y0, x1, y1):
        s, off = self.view_scale, self.view_off
        return QRectF(x0 * s + off.x(), y0 * s + off.y(),
                      (x1 - x0) * s, (y1 - y0) * s)

    def view_to_img(self, x, y):
        s, off = self.view_scale, self.view_off
        return ((x - off.x()) / s, (y - off.y()) / s)

    def set_pixmap(self, pix):
        self.pixmap = pix
        self.img_w, self.img_h = pix.width(), pix.height()
        self.zoom, self.pan = 1.0, QPointF(0, 0)
        self._layout_image()
        self.update()

    def resizeEvent(self, e):
        self._layout_image()
        super().resizeEvent(e)

    # ── отрисовка (только векторный оверлей — картинку рисует QLabel) ──
    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(COLORS["card"]))
        if not self.pixmap:
            self.label.hide()
            p.setPen(QColor(COLORS["text_second"]))
            p.setFont(QFont("Franklin Gothic Medium", S(15)))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "🚀 Image to Karaoke\n\nоткройте скриншот с субтитрами\n"
                       "или вставьте из буфера (Ctrl+V)")
            return

        pad = S(10)
        avail_w, avail_h = self.width() - pad * 2, self.height() - pad * 2
        self.view_scale = min(avail_w / max(1, self.img_w),
                              avail_h / max(1, self.img_h)) * self.zoom
        t = self.target_rect()

        # подложка «отпечаток на столе»: смещённая рамка под изображением
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["border"]))
        p.drawRect(QRectF(t.x() + S(7), t.y() + S(7), t.width(), t.height()))
        p.setBrush(QColor(COLORS["card"]))
        p.drawRect(t)

        if (self.win.showing_source and self.win.mode == "reveal"
                and self.win.words):
            ink = QColor(COLORS["border"])
            for i, (x0, y0, x1, y1) in enumerate(self.win.words):
                r = self.img_to_view(x0, y0, x1, y1)
                hot = i == self.win.hover_idx
                p.setPen(QPen(QColor(COLORS["accent"] if hot else ink),
                              S(3) if hot else S(1)))
                p.drawRect(r)
                if hot:
                    p.setFont(QFont("Consolas", S(11)))
                    label = f"#{i + 1} · {x1 - x0}×{y1 - y0}px"
                    tw = p.fontMetrics().horizontalAdvance(label) + S(14)
                    chip = QRectF(r.x(), max(S(4), r.y() - S(28)),
                                  tw, S(22))
                    p.setPen(QPen(QColor(COLORS["accent"]), S(1)))
                    p.setBrush(QColor(COLORS["card"]))
                    p.drawRoundedRect(chip, S(4), S(4))
                    p.setPen(QColor(COLORS["accent"]))
                    p.drawText(chip, Qt.AlignCenter, label)

        if self.win.mode == "font":
            if self._drag_from is not None:
                cur = self.mapFromGlobal(QCursor.pos())
                a = self.view_to_img(self._drag_from.x(), self._drag_from.y())
                b = self.view_to_img(cur.x(), cur.y())
                r = QRectF(min(a[0], b[0]), min(a[1], b[1]),
                           abs(b[0] - a[0]), abs(b[1] - a[1]))
                p.setPen(QPen(QColor(COLORS["accent"]), S(2), Qt.DashLine))
                p.drawRect(r)
            elif self.win.font_box:
                x0, y0, x1, y1 = self.win.font_box
                p.setPen(QPen(QColor(COLORS["accent"]), S(2), Qt.DashLine))
                p.drawRect(self.img_to_view(x0, y0, x1, y1))

        p.setPen(QPen(QColor(COLORS["border"]), S(1)))
        p.drawRect(t)

        if self.zoom > 1.001:
            badge = f"×{self.zoom:.2f}"
            f = QFont("Consolas", S(12))
            p.setFont(f)
            tw = p.fontMetrics().horizontalAdvance(badge) + S(14)
            r = QRectF(self.width() - tw - S(12), S(12), tw, S(24))
            p.setPen(QPen(QColor(COLORS["border"]), S(1)))
            p.setBrush(QColor(COLORS["card"]))
            p.drawRoundedRect(r, S(4), S(4))
            p.setPen(QColor(COLORS["text_main"]))
            p.drawText(r, Qt.AlignCenter, badge)

    # ── мышь ──
    def wheelEvent(self, e):
        if not self.win.img_rgb:
            return
        up = e.angleDelta().y() > 0
        if e.modifiers() & Qt.ControlModifier:
            self.set_zoom(self.zoom * (1.12 if up else 1 / 1.12))
        elif self.win.frames:
            self.win.step(1 if not up else -1)
        else:
            self.set_zoom(self.zoom * (1.12 if up else 1 / 1.12))

    def set_zoom(self, z):
        if not self.win.img_rgb:
            return
        self.zoom = max(0.25, min(6.0, z))
        if self.zoom <= 1.001:
            self.pan = QPointF(0, 0)
        self._layout_image()
        self.update()

    def mouseMoveEvent(self, e):
        if self.panning and self._pan_from is not None:
            d = e.pos() - self._pan_from
            self._pan_from = e.pos()
            self.pan += QPointF(d.x(), d.y())
            self._layout_image()
            self.update()
            return
        if self._drag_from is not None:
            self.update()
            return
        if not self.win.img_rgb or self.win.frames or self.win.mode != "reveal":
            return
        ix, iy = self.view_to_img(e.x(), e.y())
        hit = -1
        for i, (x0, y0, x1, y1) in enumerate(self.win.words):
            if x0 <= ix <= x1 and y0 <= iy <= y1:
                hit = i
                break
        if hit != self.win.hover_idx:
            self.win.hover_idx = hit
            self.update()

    def mousePressEvent(self, e):
        if not self.win.img_rgb:
            return
        if e.button() == Qt.MiddleButton:
            self.panning, self._pan_from = True, e.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return
        if e.button() != Qt.LeftButton:
            return
        if self.win.mode == "reveal" and self.win.eyedrop:
            ix, iy = self.view_to_img(e.x(), e.y())
            ix, iy = int(ix), int(iy)
            if 0 <= ix < self.win.img_rgb.width and 0 <= iy < self.win.img_rgb.height:
                self.win.set_bg(self.win.img_rgb.getpixel((ix, iy)))
            return
        if self.win.mode == "font":
            self._drag_from = e.pos()
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self.panning = False
            self.setCursor(Qt.ArrowCursor)
            return
        if self._drag_from is not None and e.button() == Qt.LeftButton:
            a = self.view_to_img(self._drag_from.x(), self._drag_from.y())
            b = self.view_to_img(e.x(), e.y())
            self._drag_from = None
            box = (int(min(a[0], b[0])), int(min(a[1], b[1])),
                   int(max(a[0], b[0])), int(max(a[1], b[1])))
            if box[2] - box[0] > 8 and box[3] - box[1] > 8:
                self.win.font_box = box
                self.win.box_lbl.setText(
                    f"({box[0]}, {box[1]}) — ({box[2]}, {box[3]})")
            self.update()

    def reset_zoom(self):
        self.zoom, self.pan = 1.0, QPointF(0, 0)
        if self.pixmap:
            self._layout_image()
        self.update()


# ============================================================
# 4. ГЛАВНОЕ ОКНО
# ============================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image to Karaoke — desktop")
        self.resize(S(1320), S(900))
        self.setMinimumSize(S(1100), S(700))
        icon_path = os.path.join(APP_DIR, "app_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.settings = core.load_settings()
        self.mode = self.settings.get("mode", "reveal")
        self.image_path = ""
        self.img_rgb = None
        self.img_np = None
        self.words, self.lines = [], []
        self.hover_idx = -1
        self.eyedrop = False
        self.font_box = None
        self.text_rgb = (255, 255, 255)
        self.showing_source = True
        self.frames, self.frame_idx = [], 0
        self.playing = False
        self._pix_cache = {}
        self.worker = None
        self._t0 = 0.0

        theme = self.settings.get("theme", "paper")
        global _THEME
        _THEME = theme
        COLORS.clear()
        COLORS.update(PALETTES.get(theme, PALETTES["paper"]))
        self._noise = make_noise_tile(_THEME)

        self._build_ui()
        self._build_shortcuts()
        self.apply_settings_to_ui()
        self.bg_chip.setStyleSheet(chip_style(self.bg_hex.text()))
        self.switch_mode(self.mode)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(COLORS["bg_main"]))
        if self._noise:
            p.drawTiledPixmap(self.rect(), self._noise)

    # ── сборка UI ──
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(S(18), S(18), S(18), S(18))
        lay.setSpacing(S(16))

        # ═══ левая панель (с прокруткой) ═══
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(S(450))
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        left = QFrame()
        left.setObjectName("Rail")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(S(18), S(18), S(18), S(18))
        ll.setSpacing(S(4))

        # заголовок: марка + название + переключатель темы
        head_row = QHBoxLayout()
        head_row.setSpacing(S(10))
        self.logo = Logo(44)
        head_row.addWidget(self.logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(QLabel("Image to Karaoke", objectName="Title"))
        titles.addWidget(QLabel("караоке-кадры из скриншота",
                                objectName="Subtitle"))
        head_row.addLayout(titles, 1)
        self.btn_theme = IconButton("theme", command=self.toggle_theme)
        head_row.addWidget(self.btn_theme)
        ll.addLayout(head_row)

        seg = QHBoxLayout()
        seg.setSpacing(S(8))
        self.seg_reveal = QPushButton("с картинки", clicked=lambda: self.switch_mode("reveal"))
        self.seg_font = QPushButton("шрифт", clicked=lambda: self.switch_mode("font"))
        seg.addWidget(self.seg_reveal)
        seg.addWidget(self.seg_font)
        ll.addLayout(seg)

        # ── изображение ──
        ll.addWidget(self._section("Рзображение"))
        self.img_lbl = QLabel("файл не выбран")
        self.img_lbl.setObjectName("Subtitle")
        self.img_lbl.setWordWrap(True)
        ll.addWidget(self.img_lbl)
        row = QHBoxLayout()
        row.setSpacing(S(8))
        row.addWidget(QPushButton("Открыть…", clicked=self.choose_image))
        row.addWidget(QPushButton("Вставить (Ctrl+V)", clicked=self.paste_image))
        ll.addLayout(row)

        # ── папка ──
        ll.addWidget(self._section("Папка для кадров"))
        self.out_edit = QLineEdit()
        self.out_edit.setFont(QFont("Consolas", S(11)))
        ll.addWidget(self.out_edit)
        row = QHBoxLayout()
        row.setSpacing(S(8))
        row.addWidget(QPushButton("Сменить папку…", clicked=self.pick_out))
        self.btn_open_out = QPushButton("Открыть папку", clicked=self.open_out)
        self.btn_open_out.setEnabled(False)
        row.addWidget(self.btn_open_out)
        ll.addLayout(row)
        self.wout_lbl = QLabel("кадров будет: —")
        self.wout_lbl.setObjectName("Mono")
        ll.addWidget(self.wout_lbl)

        # ── reveal-группа ──
        self.reveal_group = QWidget()
        rg = QVBoxLayout(self.reveal_group)
        rg.setContentsMargins(0, 0, 0, 0)
        rg.setSpacing(S(4))
        rg.addWidget(self._section("Фон карточки"))
        bgrow = QHBoxLayout()
        bgrow.setSpacing(S(6))
        self.bg_chip = QPushButton(clicked=lambda: self.pick_color_dialog("bg"))
        self.bg_chip.setFixedSize(S(48), S(36))
        bgrow.addWidget(self.bg_chip)
        self.bg_hex = QLineEdit("#323237")
        self.bg_hex.setFont(QFont("Consolas", S(11)))
        self.bg_hex.setMaximumWidth(S(96))
        self.bg_hex.editingFinished.connect(self.bg_from_hex)
        bgrow.addWidget(self.bg_hex)
        self.btn_eye = QPushButton("пипетка", clicked=self.toggle_eyedrop)
        self.btn_auto = QPushButton("авто", clicked=self.auto_bg)
        bgrow.addWidget(self.btn_eye)
        bgrow.addWidget(self.btn_auto)
        bgrow.addStretch()
        rg.addLayout(bgrow)

        self.reveal_sliders = {}
        for key, label, frm, to, val in [
            ("ink", "порог текста", 10, 120, 45),
            ("erase", "затирание фона", 2, 40, 14),
            ("space", "зазор = пробел", 5, 24, 10),
            ("dilate", "распухание", 0, 6, 2),
        ]:
            r = QHBoxLayout()
            lab = QLabel(label)
            lab.setObjectName("Subtitle")
            r.addWidget(lab, 1)
            num = QLabel(str(val))
            num.setObjectName("Mono")
            num.setFixedWidth(S(30))
            r.addWidget(num)
            sl = QSlider(Qt.Horizontal)
            sl.setRange(frm, to)
            sl.setValue(val)
            sl.valueChanged.connect(lambda v, n=num: n.setText(str(v)))
            sl.sliderReleased.connect(self.analyze)
            r.addWidget(sl, 2)
            rg.addLayout(r)
            self.reveal_sliders[key] = sl

        self.info_lbl = QLabel("слов: — · строк: —")
        self.info_lbl.setObjectName("Mono")
        rg.addWidget(self.info_lbl)
        ll.addWidget(self.reveal_group)

        # ── font-группа ──
        self.font_group = QWidget()
        fg = QVBoxLayout(self.font_group)
        fg.setContentsMargins(0, 0, 0, 0)
        fg.setSpacing(S(4))
        fg.addWidget(self._section("Субтитры"))
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("текст, который появится по словам…")
        self.text_edit.setPlainText("бабы как вы заебали")
        self.text_edit.setFixedHeight(S(110))
        self.text_edit.textChanged.connect(self.update_word_count)
        fg.addWidget(self.text_edit)

        fr = QHBoxLayout()
        fr.setSpacing(S(8))
        fr.addWidget(QLabel("кегль:"))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 200)
        self.size_spin.setValue(24)
        self.size_spin.setFixedWidth(S(80))
        fr.addWidget(self.size_spin)
        self.text_chip = QPushButton(clicked=lambda: self.pick_color_dialog("text"))
        self.text_chip.setFixedSize(S(44), S(30))
        self.text_chip.setStyleSheet(chip_style("#ffffff"))
        fr.addWidget(self.text_chip)
        fr.addStretch()
        fg.addLayout(fr)

        self.font_edit = QLineEdit("C:/Windows/Fonts/segoeui.ttf")
        self.font_edit.setFont(QFont("Consolas", S(10)))
        fg.addWidget(self.font_edit)

        fg.addWidget(self._section("Область текста"))
        fg.addWidget(QLabel("выделите мышью на превью", objectName="Subtitle"))
        self.box_lbl = QLabel("—")
        self.box_lbl.setObjectName("Mono")
        fg.addWidget(self.box_lbl)
        fg.addWidget(QPushButton("сбросить область", clicked=self.clear_font_box))
        ll.addWidget(self.font_group)

        # ── прогресс / звук / запуск ──
        ll.addWidget(self._section("Прогресс"))
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        ll.addWidget(self.progress)
        self.prog_lbl = QLabel("ожидает запуска")
        self.prog_lbl.setObjectName("Mono")
        ll.addWidget(self.prog_lbl)

        ll.addWidget(self._section("Звук"))
        snd = QHBoxLayout()
        snd.setSpacing(S(8))
        self.sound_chk = QCheckBox("алерт по завершении")
        self.sound_chk.stateChanged.connect(self.save_sound)
        self.sound_combo = QComboBox()
        self.sound_combo.addItems(["короткий", "мелодия", "системный"])
        self.sound_combo.currentIndexChanged.connect(self.save_sound)
        snd.addWidget(self.sound_chk)
        snd.addWidget(self.sound_combo)
        snd.addStretch()
        ll.addLayout(snd)

        ll.addStretch()
        self.run_btn = QPushButton("СГЕНЕРИРОВАТЬ КАДРЫ", objectName="Primary")
        self.run_btn.clicked.connect(self.run_generation)
        ll.addWidget(self.run_btn)
        hint = QLabel("колесо — кадры · Ctrl+колесо — зум\nСКМ — панорама · 0 — сброс")
        hint.setObjectName("Mono")
        ll.addWidget(hint)

        scroll.setWidget(left)

        # ═══ правая панель ═══
        right = QFrame()
        right.setObjectName("Stage")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(S(14), S(14), S(14), S(14))
        rl.setSpacing(S(10))

        self.preview = Preview(self)
        rl.addWidget(self.preview, 1)

        tr = QHBoxLayout()
        tr.setSpacing(S(10))
        st = self.style()
        for icon, slot in [
            ("prev", lambda: self.step(-1)),
            ("play", self.toggle_play),
            ("stop", self.stop_play),
        ]:
            b = IconButton(icon, command=slot,
                           color=COLORS["border"])
            setattr(self, f"btn_{icon}", b)
            tr.addWidget(b)
        self.tc_lbl = QLabel("кадр — / —")
        self.tc_lbl.setObjectName("Mono")
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setEnabled(False)
        self.slider.sliderMoved.connect(self.on_scrub)
        tr.addWidget(self.slider, 1)
        tr.addWidget(self.tc_lbl)
        rl.addLayout(tr)

        self.status = QLabel("Откройте изображение, чтобы начать")
        self.status.setObjectName("Subtitle")
        self.status.setWordWrap(True)
        rl.addWidget(self.status)

        lay.addWidget(scroll)
        lay.addWidget(right, 1)

        self.play_timer = QTimer(self)
        self.play_timer.setInterval(90)
        self.play_timer.timeout.connect(self._tick)

    def _section(self, text):
        return TrackLabel(text)

    def _build_shortcuts(self):
        def guarded(fn):
            def wrapper():
                fw = QApplication.focusWidget()
                if isinstance(fw, (QTextEdit, QLineEdit)):
                    return
                fn()
            return wrapper

        QShortcut(QKeySequence("Ctrl+C"), self, self.copy_image)
        QShortcut(QKeySequence("Ctrl+V"), self, self.paste_image)
        QShortcut(QKeySequence("Space"), self, guarded(self.toggle_play))
        QShortcut(QKeySequence("Left"), self, guarded(lambda: self.step(-1)))
        QShortcut(QKeySequence("Right"), self, guarded(lambda: self.step(1)))
        QShortcut(QKeySequence("0"), self, guarded(self.preview.reset_zoom))
        QShortcut(QKeySequence("Escape"), self, self.stop_play)

    def apply_settings_to_ui(self):
        self.sound_chk.setChecked(bool(self.settings.get("sound", True)))
        self.sound_combo.setCurrentText(
            {"short": "короткий", "melody": "мелодия",
             "system": "системный"}.get(self.settings.get("sound_style", "short"),
                                        "короткий"))

    # ── режим ──
    def switch_mode(self, mode):
        if self.mode != mode:
            self.mode = mode
            self.settings["mode"] = mode
            core.save_settings(self.settings)
        self.font_box = None
        self.box_lbl.setText("—")
        self.words, self.lines, self.hover_idx = [], [], -1
        self.reveal_group.setVisible(mode == "reveal")
        self.font_group.setVisible(mode == "font")
        self.seg_reveal.setObjectName("SegOn" if mode == "reveal" else "SegOff")
        self.seg_font.setObjectName("SegOn" if mode == "font" else "SegOff")
        for b in (self.seg_reveal, self.seg_font):
            b.style().unpolish(b)
            b.style().polish(b)
        if mode == "reveal" and self.img_np is not None:
            self.analyze()
        self.update_word_count()
        self.preview.update()

    # ── изображение ──
    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self.load_image(path)

    def load_image(self, path):
        try:
            img = Image.open(path).convert("RGB")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть файл:\n{e}")
            return
        self.stop_play()
        self.image_path = path
        self.img_rgb = img
        self.img_np = core.np.asarray(img)
        self.frames, self.frame_idx = [], 0
        self.showing_source = True
        self.slider.setEnabled(False)
        self.tc_lbl.setText("кадр — / —")
        self.btn_open_out.setEnabled(False)
        self.img_lbl.setText(os.path.basename(path))
        stem = os.path.splitext(os.path.basename(path))[0]
        self.out_edit.setText(os.path.join(os.path.dirname(path), f"{stem}_karaoke"))
        self.set_bg(core.dominant_color(img))
        self.update_word_count()
        self.preview.set_pixmap(pil_to_qpixmap(img))
        self.status.setText(f"Загружено: {os.path.basename(path)} "
                            f"({img.width}×{img.height})")

    def set_bg(self, rgb):
        hexv = core.rgb_to_hex(rgb)
        self.bg_hex.setText(hexv)
        self.bg_chip.setStyleSheet(chip_style(hexv))
        self.analyze()

    def bg_from_hex(self):
        try:
            core.hex_to_rgb(self.bg_hex.text())
        except ValueError:
            return
        self.bg_chip.setStyleSheet(chip_style(self.bg_hex.text()))
        self.analyze()

    def pick_color_dialog(self, which="bg"):
        cur = core.hex_to_rgb(self.bg_hex.text()) if which == "bg" else self.text_rgb
        col = QColorDialog.getColor(QColor(*cur), self, "Выбери цвет")
        if not col.isValid():
            return
        rgb = (col.red(), col.green(), col.blue())
        if which == "bg":
            self.set_bg(rgb)
        else:
            self.text_rgb = rgb
            self.text_chip.setStyleSheet(chip_style(col.name()))

    def toggle_eyedrop(self):
        self.eyedrop = not self.eyedrop
        self.btn_eye.setText("пипетка ✓" if self.eyedrop else "пипетка")
        self.preview.setCursor(QCursor(Qt.CrossCursor) if self.eyedrop else QCursor())

    def auto_bg(self):
        if self.img_rgb is None:
            self.flash("Сначала откройте изображение")
            return
        self.set_bg(core.dominant_color(self.img_rgb))

    def clear_font_box(self):
        self.font_box = None
        self.box_lbl.setText("—")
        self.preview.update()

    # ── детекция ──
    def analyze(self):
        if self.img_np is None or self.mode != "reveal":
            return
        try:
            bg = core.hex_to_rgb(self.bg_hex.text())
        except ValueError:
            return
        try:
            self.lines, self.words, _ = core.detect_words(
                self.img_np, bg,
                ink_threshold=self.reveal_sliders["ink"].value(),
                erase_threshold=self.reveal_sliders["erase"].value(),
                space_gap=self.reveal_sliders["space"].value(),
                dilate=self.reveal_sliders["dilate"].value())
        except Exception as e:
            self.info_lbl.setText(f"ошибка: {e}")
            return
        self.info_lbl.setText(f"слов: {len(self.words)} · строк: {len(self.lines)}")
        self.update_word_count()
        self.hover_idx = -1
        self.preview.update()

    def update_word_count(self):
        n_text = len(self.text_edit.toPlainText().split())
        n = len(self.words) if (self.mode == "reveal" and self.words) else n_text
        self.wout_lbl.setText(f"кадров будет: {n}")

    # ── папка ──
    def pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "Куда сохранять кадры")
        if d:
            self.out_edit.setText(d)

    def open_out(self):
        out = self.out_edit.text().strip()
        if out and os.path.isdir(out):
            os.startfile(out)
        else:
            QMessageBox.information(self, "Папка не найдена",
                                    "Сначала сгенерируйте кадры или выберите папку.")

    # ── буфер обмена ──
    def copy_image(self):
        if self.img_rgb is None:
            self.flash("Нечего копировать — откройте изображение")
            return
        if self.frames:
            img = Image.open(self.frames[self.frame_idx]).convert("RGB")
            name = os.path.basename(self.frames[self.frame_idx])
        else:
            img = self.img_rgb.copy()
            name = os.path.basename(self.image_path or "preview.png")
        QApplication.clipboard().setPixmap(pil_to_qpixmap(img))
        self.flash(f"Скопировано в буфер: {name} ({img.width}×{img.height})")

    def paste_image(self):
        mime = QApplication.clipboard().mimeData()
        tmp = os.path.join(os.environ.get("TEMP", "."),
                           "karaoke_frames_clipboard.png")
        loaded_from = None

        if mime.hasImage():
            pix = QApplication.clipboard().pixmap()
            if pix.isNull():
                self.flash("В буфере нет изображения")
                return
            pix.save(tmp, "PNG")
            loaded_from = tmp
        elif mime.hasUrls():
            for u in mime.urls():
                p = u.toLocalFile()
                if p.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp")):
                    loaded_from = p
                    break
        elif mime.hasText():
            p = mime.text().strip().strip('"')
            if os.path.isfile(p):
                loaded_from = p

        if loaded_from is None:
            self.flash("В буфере нет изображения")
            return
        self.load_image(loaded_from)
        if loaded_from == tmp:
            self.flash(f"Вставлено из буфера "
                       f"({self.img_rgb.width}×{self.img_rgb.height})")
        else:
            self.flash(f"Загружено: {os.path.basename(loaded_from)}")

    def flash(self, msg):
        self.status.setText(msg)

    # ── генерация ──
    def run_generation(self):
        if self.img_rgb is None:
            QMessageBox.information(self, "Нет изображения",
                                    "Сначала откройте скриншот.")
            return
        out = self.out_edit.text().strip()
        if not out:
            QMessageBox.information(self, "Нет папки", "Укажите папку для кадров.")
            return

        self.stop_play()
        self.frames = []
        self.run_btn.setEnabled(False)
        self.progress.setValue(0)
        self.prog_lbl.setText("генерация…")
        self.status.setText("Генерация…")
        self._t0 = time.time()

        try:
            if self.mode == "reveal":
                params = dict(
                    input_path=self.image_path, out_dir=out,
                    bg=core.hex_to_rgb(self.bg_hex.text()),
                    ink_threshold=self.reveal_sliders["ink"].value(),
                    erase_threshold=self.reveal_sliders["erase"].value(),
                    space_gap=self.reveal_sliders["space"].value(),
                    dilate=self.reveal_sliders["dilate"].value())
            else:
                text = self.text_edit.toPlainText().strip()
                if not text:
                    raise RuntimeError("Введите текст субтитров.")
                box = self.font_box or (20, 20, self.img_rgb.width - 20,
                                        self.img_rgb.height - 20)
                params = dict(
                    input_path=self.image_path, out_dir=out, text=text, box=box,
                    text_color=self.text_rgb,
                    font_size=self.size_spin.value(),
                    font_path=self.font_edit.text().strip() or None)
        except ValueError as e:
            self.run_btn.setEnabled(True)
            QMessageBox.critical(self, "Ошибка", str(e))
            return

        self.worker = GenWorker(self.mode, params)
        self.worker.progress.connect(self.on_progress)
        self.worker.ok.connect(self.on_finished)
        self.worker.fail.connect(self.on_failed)
        self.worker.start()

    def on_progress(self, i, total):
        self.progress.setMaximum(total)
        self.progress.setValue(i)
        self.prog_lbl.setText(f"кадр {i} / {total}")

    def on_finished(self, total, msg):
        self.run_btn.setEnabled(True)
        self.btn_open_out.setEnabled(True)
        elapsed = time.time() - self._t0
        self.prog_lbl.setText(f"{msg}  ·  {elapsed:.1f} с")
        out = self.out_edit.text().strip()
        self.status.setText(f"{msg}  ·  сохранено в {out}")
        self.frames = core.list_frames(out)
        self.frame_idx = 0
        self.slider.setEnabled(bool(self.frames))
        self.slider.setMaximum(max(0, len(self.frames) - 1))
        self.slider.setValue(0)
        self.show_frame(0)
        if self.settings.get("sound"):
            core.play_sound("done", self.settings.get("sound_style", "short"))
        self.toggle_play()

    def on_failed(self, err):
        self.run_btn.setEnabled(True)
        self.prog_lbl.setText("ошибка")
        self.status.setText(f"Ошибка: {err}")
        with open(os.path.join(APP_DIR, "app_error.log"), "a", encoding="utf-8") as f:
            f.write(f"\n--- generate failed ---\n{err}\n")
        if self.settings.get("sound"):
            core.play_sound("error", self.settings.get("sound_style", "short"))
        QMessageBox.critical(self, "Ошибка", err)

    def save_sound(self):
        self.settings["sound"] = self.sound_chk.isChecked()
        self.settings["sound_style"] = {
            "короткий": "short", "мелодия": "melody", "системный": "system"
        }.get(self.sound_combo.currentText(), "short")
        core.save_settings(self.settings)
        if self.settings["sound"]:
            core.play_sound("done", self.settings["sound_style"])

    # ── транспорт ──
    def show_frame(self, idx):
        if not self.frames:
            return
        self.frame_idx = max(0, min(len(self.frames) - 1, idx))
        self.tc_lbl.setText(f"кадр {self.frame_idx + 1:03d} / {len(self.frames):03d}")
        if not self.slider.isSliderDown():
            self.slider.setValue(self.frame_idx)
        pix = self._pix_cache.get(self.frame_idx)
        if pix is None:
            pix = QPixmap(self.frames[self.frame_idx])
            if len(self._pix_cache) > 4:
                self._pix_cache.clear()
            self._pix_cache[self.frame_idx] = pix
        self.showing_source = False
        self.preview.set_pixmap(pix)

    def on_scrub(self, value):
        if self.frames:
            self.show_frame(value)

    def step(self, delta):
        if self.frames:
            self.show_frame(self.frame_idx + delta)

    def toggle_play(self):
        if not self.frames:
            return
        self.playing = not self.playing
        self.btn_play.icon = "pause" if self.playing else "play"
        self.btn_play.update()
        if self.playing:
            if self.frame_idx >= len(self.frames) - 1:
                self.show_frame(0)
            self.play_timer.start()

    def _tick(self):
        if self.playing:
            self.show_frame((self.frame_idx + 1) % len(self.frames))

    def stop_play(self):
        if self.playing:
            self.playing = False
            self.play_timer.stop()
            self.btn_play.icon = "play"
            self.btn_play.update()

    # ── тема ──
    def toggle_theme(self):
        global _THEME
        _THEME = "ink" if _THEME == "paper" else "paper"
        COLORS.clear()
        COLORS.update(PALETTES[_THEME])
        self.settings["theme"] = _THEME
        core.save_settings(self.settings)
        self._noise = make_noise_tile(_THEME)
        QApplication.instance().setStyleSheet(build_stylesheet())
        # чипы и подсветку сегментов перекрашиваем вручную
        self.bg_chip.setStyleSheet(chip_style(self.bg_hex.text()))
        self.text_chip.setStyleSheet(chip_style(self._text_hex()))
        self.switch_mode(self.mode)
        for w in self.findChildren(QWidget):
            w.update()
        self.update()

    def _text_hex(self):
        return core.rgb_to_hex(self.text_rgb)


# ============================================================
# 5. ЗАПУСК
# ============================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    try:
        _SCALE = max(1.0, app.primaryScreen().logicalDotsPerInch() / 96.0)
    except Exception:
        _SCALE = 1.0
    _theme0 = core.load_settings().get("theme", "paper")
    _THEME = _theme0
    COLORS.clear()
    COLORS.update(PALETTES.get(_theme0, PALETTES["paper"]))
    app.setStyleSheet(build_stylesheet())
    win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec_())

