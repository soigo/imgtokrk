"""
Karaoke Frames — настольная утилита для караоке-кадров.

Два режима:
  · «с картинки» — находит белые субтитры на скриншоте, затирает их
    и открывает по одному слову за кадр, копируя пиксели оригинала;
  · «шрифт» — рисует субтитры шрифтом поверх базового кадра.

Запуск:  run.bat   (или: python app.py)
"""

from __future__ import annotations

import os
import sys
import time
import traceback

import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageDraw, ImageTk

import core

# ── палитра: глубокий фиолет + сигнальный янтарь ──────────────────────────
BG         = "#17121f"
PANEL      = "#1f1830"
RAISED     = "#2a2138"
LINE       = "#3a2f4d"
TEXT       = "#ede8f5"
MUTED      = "#a99ec4"
ACCENT     = "#ffb454"
ACCENT_HI  = "#ffc46b"
ACCENT_DIM = "#8a5c1e"

F_UI    = ("Bahnschrift", 10)
F_UI_B  = ("Bahnschrift SemiBold", 10)
F_MONO  = ("Consolas", 10)
F_MONO_B = ("Consolas", 10, "bold")


def log_uncaught(exc_type, exc, tb):
    log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_error.log")
    with open(log, "a", encoding="utf-8") as f:
        f.write("".join(traceback.format_exception(exc_type, exc, tb)) + "\n")


sys.excepthook = log_uncaught

try:  # чёткий рендер на HiDPI — до создания Tk()
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


class Equalizer(tk.Canvas):
    """Мини-эквалайзер в шапке: пульсирует под проигрывание кадров."""

    def __init__(self, master, bars=14, **kw):
        super().__init__(master, width=bars * 7 + 4, height=30, bg=PANEL,
                         highlightthickness=0, bd=0, **kw)
        self.bars, self.energy, self.playing = bars, 0.0, False

    def pulse(self, level):
        self.energy = level
        self.render()

    def render(self):
        self.delete("all")
        bw, gap = 3, 4
        for i in range(self.bars):
            x = 2 + i * (bw + gap)
            seed = (i * 37) % 17
            amp = abs(np.sin(i * 1.3 + self.energy * 0.9 + seed))
            h = 4 + amp * (20 if self.playing else 7)
            color = ACCENT_HI if (self.playing and i % 3 == 0) else (ACCENT if self.playing else LINE)
            self.create_rectangle(x, 28 - h, x + bw, 28, fill=color, width=0)


class MiniButton(tk.Canvas):
    """Плоская кнопка с векторной иконкой."""

    def __init__(self, master, icon, command, size=26):
        super().__init__(master, width=size, height=size, bg=RAISED,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.icon, self.command, self.size = icon, command, size
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<Button-1>", self._click)
        self.draw()

    def _hover(self, on):
        self.configure(bg=LINE if on else RAISED)
        self.draw()

    def _click(self, _):
        if self.command:
            self.command()

    def draw(self):
        self.delete("all")
        s, m = self.size, 2
        if self.icon == "play":
            self.create_polygon(m + 1, m, m + 1, s - m, s - m + 1, s / 2, fill=TEXT)
        elif self.icon == "pause":
            self.create_rectangle(m + 1, m, s / 2 - 1, s - m, fill=TEXT, width=0)
            self.create_rectangle(s / 2 + 1, m, s - m - 1, s - m, fill=TEXT, width=0)
        elif self.icon == "prev":
            self.create_polygon(m + 3, m, m + 3, s - m, m + 1, s / 2, fill=TEXT)
            self.create_rectangle(m + 4, m, m + 5, s - m, fill=TEXT, width=0)
        elif self.icon == "next":
            self.create_polygon(s - m - 3, m, s - m - 3, s - m, s - m - 1, s / 2, fill=TEXT)
            self.create_rectangle(s - m - 6, m, s - m - 5, s - m, fill=TEXT, width=0)
        elif self.icon == "stop":
            self.create_rectangle(m + 4, m + 4, s - m - 4, s - m - 4, fill=TEXT, width=0)


class Slider(tk.Canvas):
    """Кастомный слайдер: дорожка + заливка + ручка. Клик и драг."""

    def __init__(self, master, command, width=520, height=26):
        super().__init__(master, width=width, height=height, bg=PANEL,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.command = command
        self.value, self.maximum = 0, 1
        self.dragging = False
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)

    def set_range(self, value, maximum):
        self.value, self.maximum = max(0, value), max(1, maximum)
        self.render()

    def _frac(self, event):
        return min(1.0, max(0.0, event.x / max(1, self.winfo_width())))

    def _press(self, e):
        self.dragging = True
        self.command(self._frac(e))

    def _drag(self, e):
        if self.dragging:
            self.command(self._frac(e))

    def _release(self, e):
        self.dragging = False

    def render(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        cy, pad = h // 2, 9
        self.create_rectangle(pad, cy - 3, w - pad, cy + 3, fill=RAISED, width=0)
        if self.maximum > 0:
            fx = pad + (w - 2 * pad) * (self.value / self.maximum)
            self.create_rectangle(pad, cy - 3, fx, cy + 3, fill=ACCENT_DIM, width=0)
            self.create_oval(fx - 7, cy - 7, fx + 7, cy + 7, fill=ACCENT, outline=PANEL, width=2)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Karaoke Frames — караоке-кадры")
        self.geometry("1240x820")
        self.minsize(1040, 680)
        self.configure(bg=BG)
        try:
            self.state("zoomed")
        except Exception:
            pass

        self.settings = core.load_settings()
        self.mode = self.settings.get("mode", "reveal")
        self.image_path = None
        self.img_rgb = None
        self.img_np = None
        self.view_scale, self.view_off = 1.0, (0, 0)
        self.zoom = 1.0
        self.pan = (0, 0)
        self._resize_job = None
        self.words, self.lines = [], []
        self.hover_idx = -1
        self.eyedrop = False
        self.font_box = None
        self.drag_start = None
        self.frames, self.frame_idx = [], 0
        self.playing = False

        self._setup_styles()
        self._build_header()
        self._build_body()
        self._build_transport()
        self._build_statusbar()

        self.bind("<Left>", lambda e: self.step(-1))
        self.bind("<Right>", lambda e: self.step(1))
        self.bind("<space>", lambda e: self.toggle_play())
        self.bind("0", lambda e: self.reset_zoom())
        self.bind("<plus>", lambda e: self.set_zoom(self.zoom * 1.2))
        self.bind("<minus>", lambda e: self.set_zoom(self.zoom / 1.2))
        self.bind("<Escape>", lambda e: (self.reset_zoom(), self.stop_play()))
        self.bind("<Control-c>", self.on_ctrl_c)
        self.bind("<Control-v>", self.on_ctrl_v)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.render_preview()

    # ═══════════════ оформление ═══════════════

    def _setup_styles(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(".", background=BG, foreground=TEXT, font=F_UI,
                     borderwidth=0, focuscolor=PANEL)
        st.configure("TFrame", background=BG)
        st.configure("Rail.TFrame", background=PANEL)
        st.configure("TLabel", background=BG, foreground=TEXT)
        st.configure("Muted.TLabel", background=PANEL, foreground=MUTED)
        st.configure("MutedBg.TLabel", background=BG, foreground=MUTED)
        st.configure("Section.TLabel", background=PANEL, foreground=ACCENT, font=F_MONO_B)
        st.configure("TEntry", fieldbackground=RAISED, foreground=TEXT,
                     insertcolor=TEXT, borderwidth=1, relief="flat", padding=5)
        st.configure("TSpinbox", fieldbackground=RAISED, foreground=TEXT,
                     arrowcolor=TEXT, borderwidth=1, arrowsize=12, padding=4)
        st.configure("TScale", background=PANEL, troughcolor=RAISED, borderwidth=0)
        st.configure("TButton", background=RAISED, foreground=TEXT, borderwidth=1,
                     bordercolor=LINE, focusthickness=0, padding=(12, 6))
        st.map("TButton", background=[("active", LINE), ("disabled", PANEL)],
               foreground=[("disabled", MUTED)], bordercolor=[("active", ACCENT_DIM)])
        st.configure("Accent.TButton", background=ACCENT, foreground="#241a08",
                     font=F_UI_B, padding=(16, 8), borderwidth=0)
        st.map("Accent.TButton", background=[("active", ACCENT_HI), ("disabled", "#6b5734")],
               foreground=[("disabled", "#9b8b70")])
        st.configure("TProgressbar", background=ACCENT, troughcolor=RAISED,
                     borderwidth=0, thickness=6)

    def _build_header(self):
        head = ttk.Frame(self, padding=(16, 12, 16, 10))
        head.pack(fill="x")

        brand = ttk.Frame(head)
        brand.pack(side="left", padx=(0, 20))
        tk.Label(brand, text="KARAOKE", bg=BG, fg=TEXT,
                 font=("Bahnschrift SemiBold", 15)).pack(anchor="w")
        tk.Label(brand, text="FRAMES · desktop", bg=BG, fg=MUTED,
                 font=F_MONO).pack(anchor="w")

        self.eq = Equalizer(head)
        self.eq.pack(side="left", padx=(0, 20))
        self.eq.render()

        seg = ttk.Frame(head)
        seg.pack(side="left")
        self.seg_btns = {}
        for i, (key, label) in enumerate([("reveal", "с картинки"), ("font", "шрифт")]):
            b = tk.Label(seg, text=label, width=11, pady=5, cursor="hand2",
                         font=F_UI_B, bg=RAISED, fg=MUTED, highlightthickness=1,
                         highlightbackground=LINE, highlightcolor=LINE)
            b.grid(row=0, column=i, padx=(0 if i == 0 else 3, 0))
            b.bind("<Button-1>", lambda e, k=key: self.switch_mode(k))
            self.seg_btns[key] = b

        paste_btn = ttk.Button(head, text="Вставить скриншот", command=self.paste_image)
        paste_btn.pack(side="right", padx=(0, 8))
        copy_btn = ttk.Button(head, text="Копировать кадр", command=self.copy_image)
        copy_btn.pack(side="right", padx=(0, 8))
        ttk.Button(head, text="Открыть изображение…",
                   command=self.open_image).pack(side="right")
        self._refresh_seg()

    def _build_body(self):
        body = ttk.Frame(self, padding=(16, 0, 16, 8))
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        rail = ttk.Frame(body, style="Rail.TFrame", padding=14)
        rail.grid(row=0, column=0, sticky="nsew")
        rail.columnconfigure(0, weight=1)
        rail.columnconfigure(1, weight=1)
        self.rail = rail
        self.reveal_widgets, self.font_widgets = [], []
        self._build_rail(rail)

        stage = ttk.Frame(body, style="Rail.TFrame")
        stage.grid(row=0, column=1, sticky="nsew", padx=(14, 0))
        stage.rowconfigure(0, weight=1)
        stage.columnconfigure(0, weight=1)
        self.stage = stage
        self.canvas = tk.Canvas(stage, bg=PANEL, highlightthickness=1,
                                highlightbackground=LINE)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.canvas.bind("<Control-MouseWheel>", self.on_ctrl_wheel)
        self.canvas.bind("<ButtonPress-2>", self.pan_start)
        self.canvas.bind("<B2-Motion>", self.pan_move)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind("<Button-3>", self.show_menu)

        self.menu = tk.Menu(self.canvas, tearoff=0, bg=PANEL, fg=TEXT, bd=0,
                            activebackground=ACCENT, activeforeground="#241a08",
                            font=F_UI)
        self.menu.add_command(label="Вставить из буфера  (Ctrl+V)",
                              command=self.paste_image)
        self.menu.add_command(label="Копировать кадр  (Ctrl+C)",
                              command=self.copy_image)
        self.menu.add_command(label="Копировать путь папки",
                              command=self.copy_out_path)
        self.menu.add_separator()
        self.menu.add_command(label="Сбросить зум  (0)", command=self.reset_zoom)
        self.menu.add_command(label="Стоп  (Esc)", command=self.stop_play)

    def _build_rail(self, rail):
        row = [0]

        def grid(w, kind=None, **kw):
            w.grid(row=row[0], column=kw.pop("col", 0), columnspan=kw.pop("span", 1),
                   sticky=kw.pop("sticky", "we"), pady=kw.pop("pady", 2),
                   padx=kw.pop("padx", 0), **kw)
            if kind == "reveal":
                self.reveal_widgets.append(w)
            elif kind == "font":
                self.font_widgets.append(w)
            return w

        def head(text, kind=None):
            grid(ttk.Label(rail, text=text, style="Section.TLabel"),
                 kind, pady=(12 if row[0] else 2, 4))

        # ── папка для кадров (общий блок) ──
        head("ПАПКА ДЛЯ КАДРОВ")
        row[0] += 1
        grid(ttk.Label(rail, text="кадры сохраняются как frame_001.png …",
                       style="Muted.TLabel"))
        row[0] += 1
        self.out_var = tk.StringVar()
        e = grid(ttk.Entry(rail, textvariable=self.out_var, font=F_MONO))
        row[0] += 1
        grid(ttk.Button(rail, text="Сменить папку…", command=self.pick_out), col=0)
        grid(ttk.Button(rail, text="Открыть папку", command=self.open_out), col=1, padx=4)
        row[0] += 1
        self.wout_lbl = grid(ttk.Label(rail, text="кадров будет: —",
                                       style="Muted.TLabel"), sticky="w")
        row[0] += 1

        # ── reveal ──
        head("ФОН КАРТОЧКИ", "reveal")
        chip_row = ttk.Frame(rail, style="Rail.TFrame")
        grid(chip_row, "reveal")
        self._chip = tk.Label(chip_row, text="", width=3, bg="#323237")
        self._chip.pack(side="left", padx=(0, 8))
        self.bg_var = tk.StringVar(value="#323237")
        e = ttk.Entry(chip_row, textvariable=self.bg_var, width=8)
        e.pack(side="left", fill="x", expand=True)
        e.bind("<Return>", lambda _: self.analyze())
        e.bind("<FocusOut>", lambda _: self.analyze())
        self.eye_btn = ttk.Button(chip_row, text="пипетка", width=9,
                                  command=self.toggle_eyedrop)
        self.eye_btn.pack(side="left", padx=(8, 0))
        self.auto_bg_btn = ttk.Button(chip_row, text="авто", width=6,
                                      command=self.auto_bg)
        self.auto_bg_btn.pack(side="left", padx=(4, 0))
        row[0] += 1

        self.reveal_rows = {}
        for key, label, frm, to, val in [
            ("ink",   "порог текста",   10, 120, 45),
            ("erase", "затирание фона",  2,  40, 14),
            ("space", "зазор = пробел",  5,  24, 10),
            ("dilate", "распухание",    0,   6,  2),
        ]:
            grid(ttk.Label(rail, text=label, style="Muted.TLabel"), "reveal", pady=(8, 0))
            row[0] += 1
            var = tk.IntVar(value=val)
            sc = ttk.Scale(rail, from_=frm, to=to, variable=var, length=120)
            sc.bind("<ButtonRelease-1>", lambda e: self.analyze())
            grid(sc, "reveal", col=0)
            num = grid(ttk.Label(rail, text=str(val), style="Muted.TLabel"),
                       "reveal", col=1, sticky="e")
            var.trace_add("write", lambda *a, n=num, v=var: n.configure(text=str(v.get())))
            self.reveal_rows[key] = var
            row[0] += 1
        self.info_lbl = grid(ttk.Label(rail, text="слов: — · строк: —",
                                       style="Muted.TLabel"), "reveal", sticky="w")

        # ── font ──
        row[0] += 1
        head("СУБТИТРЫ", "font")
        self.text_var = tk.StringVar(value="бабы как вы заебали")
        grid(ttk.Entry(rail, textvariable=self.text_var), "font")
        self.text_var.trace_add("write", lambda *a: self.update_word_count())
        row[0] += 1

        grid(ttk.Label(rail, text="кегль", style="Muted.TLabel"), "font", pady=(8, 0))
        row[0] += 1
        sz_row = ttk.Frame(rail, style="Rail.TFrame")
        grid(sz_row, "font")
        self.fs_var = tk.IntVar(value=24)
        ttk.Spinbox(sz_row, from_=8, to=120, textvariable=self.fs_var,
                    width=5).pack(side="left")
        self.tcol_chip = tk.Label(sz_row, text="", width=3, bg="#ffffff")
        self.tcol_chip.pack(side="left", padx=10)
        self.tcol_var = tk.StringVar(value="#ffffff")
        e = ttk.Entry(sz_row, textvariable=self.tcol_var, width=8)
        e.pack(side="left", fill="x", expand=True)
        e.bind("<Return>", lambda _: self.chip_from_var())
        e.bind("<FocusOut>", lambda _: self.chip_from_var())
        row[0] += 1

        head("ШРИФТ", "font")
        self.font_var = tk.StringVar(value="C:/Windows/Fonts/segoeui.ttf")
        grid(ttk.Entry(rail, textvariable=self.font_var), "font")
        row[0] += 1
        grid(ttk.Button(rail, text="выбрать…", command=self.pick_font), "font", sticky="w")
        row[0] += 1

        head("ЗАГОЛОВОК", "font")
        self.title_var = tk.StringVar()
        grid(ttk.Entry(rail, textvariable=self.title_var), "font")
        row[0] += 1

        head("ОБЛАСТЬ ТЕКСТА", "font")
        grid(ttk.Label(rail, text="выделите мышью на превью",
                       style="Muted.TLabel"), "font")
        row[0] += 1
        ttk.Button(rail, text="сбросить",
                   command=self.clear_font_box).grid(row=row[0], column=0, columnspan=2,
                                                     sticky="w", pady=2)
        self.font_widgets.append(rail.winfo_children()[-1])
        row[0] += 1
        self.box_lbl = grid(ttk.Label(rail, text="—", style="Muted.TLabel"), "font", sticky="w")
        row[0] += 1

        # ── прогресс (общий блок) ──
        head("ПРОГРЕСС")
        self.prog_bar = grid(ttk.Progressbar(rail, mode="determinate", length=200))
        row[0] += 1
        self.prog_lbl = grid(ttk.Label(rail, text="ожидает запуска",
                                       style="Muted.TLabel"), sticky="w")
        row[0] += 1

        # ── звук (общий блок) ──
        head("ЗВУК")
        sound_row = ttk.Frame(rail, style="Rail.TFrame")
        grid(sound_row)
        self.sound_var = tk.BooleanVar(value=self.settings.get("sound", True))
        ttk.Checkbutton(sound_row, text="алерт по завершении",
                        variable=self.sound_var,
                        command=self.save_sound_settings).pack(side="left")
        self.sound_style = ttk.Combobox(sound_row, width=9, state="readonly",
                                        values=["короткий", "мелодия", "системный"],
                                        font=F_UI)
        self.sound_style.set({"short": "короткий", "melody": "мелодия",
                              "system": "системный"}.get(
                                  self.settings.get("sound_style", "short"), "короткий"))
        self.sound_style.pack(side="left", padx=(8, 0))
        self.sound_style.bind("<<ComboboxSelected>>", lambda e: self.save_sound_settings())
        row[0] += 1

        # ── кнопка генерации (всегда) ──
        row[0] += 1
        self.gen_btn = ttk.Button(rail, text="СГЕНЕРИРОВАТЬ КАДРЫ",
                                  style="Accent.TButton", command=self.generate)
        grid(self.gen_btn, pady=(14, 0))

        # ── видимость по режиму ──
        for w in self.reveal_widgets:
            w.grid()
        for w in self.font_widgets:
            w.grid_remove()

    def _apply_mode(self):
        for w in self.reveal_widgets:
            (w.grid if self.mode == "reveal" else w.grid_remove)()
        for w in self.font_widgets:
            (w.grid if self.mode == "font" else w.grid_remove)()
        self._refresh_seg()

    def switch_mode(self, mode):
        if self.mode == mode:
            return
        self.mode = mode
        self.settings["mode"] = mode
        core.save_settings(self.settings)
        self.clear_font_box()
        self.words, self.lines, self.hover_idx = [], [], -1
        if mode == "reveal" and self.img_np is not None:
            self.analyze()
        self.update_word_count()
        self._apply_mode()
        self.render_preview()

    def _refresh_seg(self):
        for key, b in self.seg_btns.items():
            active = self.mode == key
            b.configure(bg=ACCENT if active else RAISED,
                        fg="#241a08" if active else MUTED)

    # ═══════════════ файловые операции ═══════════════

    def open_image(self):
        path = filedialog.askopenfilename(
            title="Выберите изображение",
            filetypes=[("Изображения", "*.png *.jpg *.jpeg *.bmp *.webp")])
        if path:
            self.load_image(path)

    def load_image(self, path):
        try:
            img = Image.open(path).convert("RGB")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл:\n{e}")
            return
        self.image_path = path
        self.img_rgb = img
        self.img_np = np.asarray(img)
        self.stop_play()
        self.frames, self.frame_idx = [], 0
        self.slider.set_range(0, 1)
        self.tc_lbl.configure(text="кадр — / —")
        self._tk = None
        stem = os.path.splitext(os.path.basename(path))[0]
        self.out_var.set(os.path.join(os.path.dirname(path), f"{stem}_karaoke"))
        self.bg_var.set(core.rgb_to_hex(core.dominant_color(img)))
        self.analyze()
        self.update_word_count()
        self.render_preview()

    def pick_out(self):
        d = filedialog.askdirectory(title="Куда сохранять кадры")
        if d:
            self.out_var.set(d)

    def pick_font(self):
        p = filedialog.askopenfilename(title="Шрифт", filetypes=[("TrueType", "*.ttf")])
        if p:
            self.font_var.set(p)

    def open_out(self):
        out = self.out_var.get().strip()
        if out and os.path.isdir(out):
            os.startfile(out)
        else:
            messagebox.showinfo("Папка не найдена",
                                "Сначала сгенерируйте кадры или выберите папку.")

    # ═══════════════ буфер обмена ═══════════════

    def copy_image(self):
        if self.img_rgb is None:
            self.flash("Нечего копировать — откройте изображение")
            return
        if self.frames:
            img = Image.open(self.frames[self.frame_idx]).convert("RGB")
            name = os.path.basename(self.frames[self.frame_idx])
        else:
            img = self.img_rgb.copy()
            self._draw_overlay(img)  # с рамками слов — удобно проверять детекцию
            name = os.path.basename(self.image_path or "preview.png")
        if core.clipboard_image_put(img):
            self.flash(f"Скопировано в буфер: {name} ({img.width}×{img.height})")
        else:
            self.flash("Буфер доступен только на Windows")

    def paste_image(self):
        img = core.clipboard_image_get()
        if img is None:
            self.flash("В буфере нет изображения")
            return
        tmp = os.path.join(os.environ.get("TEMP", "."), "karaoke_frames_clipboard.png")
        try:
            img.save(tmp)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить вставку:\n{e}")
            return
        self.load_image(tmp)
        self.flash(f"Вставлено из буфера: {img.width}×{img.height}")

    def copy_out_path(self):
        out = self.out_var.get().strip()
        if not out:
            self.flash("Папка не задана")
            return
        self.clipboard_clear()
        self.clipboard_append(out)
        self.flash(f"Путь скопирован: {out}")

    def on_ctrl_c(self, e):
        if self.focus_get() is not None and \
                self.focus_get().winfo_class() in ("TEntry", "Entry", "TSpinbox",
                                                   "Spinbox", "Text", "TCombobox"):
            return None
        self.copy_image()
        return "break"

    def on_ctrl_v(self, e):
        if self.focus_get() is not None and \
                self.focus_get().winfo_class() in ("TEntry", "Entry", "TSpinbox",
                                                   "Spinbox", "Text", "TCombobox"):
            return None
        self.paste_image()
        return "break"

    def show_menu(self, e):
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def flash(self, message):
        self.status.configure(text=message)

    def save_sound_settings(self):
        self.settings["sound"] = bool(self.sound_var.get())
        self.settings["sound_style"] = {
            "короткий": "short", "мелодия": "melody", "системный": "system"
        }.get(self.sound_style.get(), "short")
        core.save_settings(self.settings)
        if self.settings["sound"]:
            core.play_sound("done", self.settings["sound_style"])

    # ═══════════════ детекция ═══════════════

    def analyze(self):
        if self.img_np is None or self.mode != "reveal":
            return
        try:
            bg = core.hex_to_rgb(self.bg_var.get())
        except ValueError:
            return
        try:
            self.lines, self.words, _masks = core.detect_words(
                self.img_np, bg,
                ink_threshold=self.reveal_rows["ink"].get(),
                erase_threshold=self.reveal_rows["erase"].get(),
                space_gap=self.reveal_rows["space"].get(),
                dilate=self.reveal_rows["dilate"].get())
        except Exception as e:
            self.info_lbl.configure(text=f"ошибка: {e}")
            return
        self._chip.configure(bg=core.rgb_to_hex(bg))
        self.info_lbl.configure(text=f"слов: {len(self.words)} · строк: {len(self.lines)}")
        self.wout_lbl.configure(text=f"кадров будет: {max(len(self.words), len(self.text_var.get().split()))}")
        self.hover_idx = -1
        self.render_preview()

    def update_word_count(self):
        n_words_text = len(self.text_var.get().split())
        n = len(self.words) if self.mode == "reveal" and self.words else n_words_text
        self.wout_lbl.configure(text=f"кадров будет: {n}")

    def chip_from_var(self):
        try:
            self.tcol_chip.configure(bg=core.rgb_to_hex(core.hex_to_rgb(self.tcol_var.get())))
        except ValueError:
            pass

    def toggle_eyedrop(self):
        self.eyedrop = not self.eyedrop
        self.eye_btn.configure(text="пипетка ✓" if self.eyedrop else "пипетка")
        self.canvas.configure(cursor="crosshair")

    def auto_bg(self):
        if self.img_rgb is None:
            self.flash("Сначала откройте изображение")
            return
        self.bg_var.set(core.rgb_to_hex(core.dominant_color(self.img_rgb)))
        self.analyze()

    def clear_font_box(self):
        self.font_box = None
        self.box_lbl.configure(text="—")

    # ═══════════════ превью ═══════════════

    def to_image(self, cx, cy):
        sx, sy = self.view_off
        return (cx - sx) / max(0.01, self.view_scale), (cy - sy) / max(0.01, self.view_scale)

    def render_preview(self, hover=None):
        c = self.canvas
        c.delete("all")
        cw, ch = max(c.winfo_width(), 100), max(c.winfo_height(), 100)

        if self.img_rgb is None:
            self._draw_placeholder(c, cw, ch)
            return

        if self.frames:
            img = Image.open(self.frames[self.frame_idx])
        else:
            img = self.img_rgb.copy()
            self._draw_overlay(img)
        if self.drag_start and self.drag_end:
            d = ImageDraw.Draw(img)
            a, b = self.drag_start, self.drag_end
            d.rectangle([min(a[0], b[0]), min(a[1], b[1]),
                         max(a[0], b[0]), max(a[1], b[1])],
                        outline=(255, 107, 107), width=2)

        fit = min(cw / img.width, ch / img.height) * 0.96
        self.view_scale = fit * self.zoom
        dw, dh = max(1, int(img.width * self.view_scale)), max(1, int(img.height * self.view_scale))
        disp = img.resize((dw, dh), Image.LANCZOS)
        self._tk = ImageTk.PhotoImage(disp)

        ox = (cw - dw) / 2 if dw <= cw else min(0, max(cw - dw, self.pan[0]))
        oy = (ch - dh) / 2 if dh <= ch else min(0, max(ch - dh, self.pan[1]))
        self.view_off = (ox, oy)
        c.create_image(ox, oy, anchor="nw", image=self._tk)
        c.create_rectangle(ox - 1, oy - 1, ox + dw + 1, oy + dh + 1, outline=LINE)
        if self.zoom > 1.001:
            self.status.configure(text=self.status.cget("text").split("  ·  зум")[0]
                                  + f"  ·  зум {int(round(self.zoom * 100))}%")

    # ── зум / панорама / ресайз ──

    def on_wheel(self, e):
        if self.img_rgb is None:
            return
        if self.frames and not (e.state & 0x4):  # Ctrl — зум, иначе прокрутка кадров
            self.step(1 if e.delta < 0 else -1)
        else:
            self.set_zoom(self.zoom * (1.15 if e.delta > 0 else 1 / 1.15))

    def on_ctrl_wheel(self, e):
        self.set_zoom(self.zoom * (1.15 if e.delta > 0 else 1 / 1.15))

    def set_zoom(self, z):
        if self.img_rgb is None:
            return
        self.zoom = max(0.2, min(6.0, z))
        if self.zoom <= 1.001:
            self.pan = (0, 0)
        self.render_preview()

    def reset_zoom(self):
        self.zoom, self.pan = 1.0, (0, 0)
        self.render_preview()

    def pan_start(self, e):
        self._pan_from = (e.x, e.y)

    def pan_move(self, e):
        if getattr(self, "_pan_from", None) is None or self.img_rgb is None:
            return
        dx, dy = e.x - self._pan_from[0], e.y - self._pan_from[1]
        self._pan_from = (e.x, e.y)
        self.pan = (self.pan[0] + dx, self.pan[1] + dy)
        self.render_preview()

    def on_canvas_configure(self, e):
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self._after_resize)

    def _after_resize(self):
        self._resize_job = None
        self.render_preview(self.hover_idx)

    def _draw_placeholder(self, c, cw, ch):
        c.create_rectangle(cw / 2 - 200, ch / 2 - 74, cw / 2 + 200, ch / 2 + 74,
                           outline=LINE, width=2, dash=(9, 7))
        c.create_text(cw / 2, ch / 2 - 26, text="KARAOKE FRAMES", fill=MUTED,
                      font=F_MONO_B)
        c.create_text(cw / 2, ch / 2, text="откройте скриншот с субтитрами",
                      fill=MUTED, font=F_UI)
        c.create_text(cw / 2, ch / 2 + 26, text="png · jpg · jpeg · bmp · webp",
                      fill=LINE, font=F_MONO)

    def _draw_overlay(self, img):
        d = ImageDraw.Draw(img)
        if self.mode == "reveal":
            for i, (x0, y0, x1, y1) in enumerate(self.words):
                hot = i == self.hover_idx
                col = (255, 180, 84) if hot else (118, 94, 156)
                d.rectangle([x0, y0, x1, y1], outline=col, width=3 if hot else 1)
        else:
            box = self.font_box
            if box:
                self._draw_dashed(d, box, (255, 180, 84))

    def _draw_dashed(self, d, box, color, dash=9, width=2):
        x0, y0, x1, y1 = box
        for x in range(x0, x1, dash * 2):
            d.line([(x, y0), (min(x + dash, x1), y0)], fill=color, width=width)
            d.line([(x, y1), (min(x + dash, x1), y1)], fill=color, width=width)
        for y in range(y0, y1, dash * 2):
            d.line([(x0, y), (x0, min(y + dash, y1))], fill=color, width=width)
            d.line([(x1, y), (x1, min(y + dash, y1))], fill=color, width=width)

    def on_motion(self, e):
        if self.img_rgb is None or self.frames or self.mode != "reveal":
            return
        ix, iy = self.to_image(e.x, e.y)
        hit = -1
        for i, (x0, y0, x1, y1) in enumerate(self.words):
            if x0 <= ix <= x1 and y0 <= iy <= y1:
                hit = i
                break
        if hit != self.hover_idx:
            self.hover_idx = hit
            self.render_preview(hit)
        if hit >= 0:
            x0, y0, x1, y1 = self.words[hit]
            self.status.configure(text=f"слово #{hit + 1} · {x1 - x0}×{y1 - y0} px · ({x0},{y0})")

    def on_click(self, e):
        if self.img_rgb is None:
            self.open_image()
            return
        if self.mode == "reveal":
            if self.eyedrop:
                ix, iy = (int(v) for v in self.to_image(e.x, e.y))
                if 0 <= ix < self.img_rgb.width and 0 <= iy < self.img_rgb.height:
                    hexv = core.rgb_to_hex(self.img_rgb.getpixel((ix, iy)))
                    self.bg_var.set(hexv)
                    self.eyedrop = False
                    self.eye_btn.configure(text="пипетка")
                    self.analyze()
        else:
            self.drag_start = (e.x, e.y)
            self.drag_end = (e.x, e.y)
            self.render_preview()

    def on_drag(self, e):
        if self.drag_start and self.mode == "font":
            self.drag_end = (e.x, e.y)
            self.render_preview()

    def on_release(self, e):
        if self.drag_start and self.mode == "font":
            a = self.to_image(*self.drag_start)
            b = self.to_image(e.x, e.y)
            box = (int(min(a[0], b[0])), int(min(a[1], b[1])),
                   int(max(a[0], b[0])), int(max(a[1], b[1])))
            if box[2] - box[0] > 8 and box[3] - box[1] > 8:
                self.font_box = box
                self.box_lbl.configure(
                    text=f"({box[0]}, {box[1]}) — ({box[2]}, {box[3]})")
            self.drag_start = self.drag_end = None
            self.render_preview()

    # ═══════════════ транспорт ═══════════════

    def _build_transport(self):
        tr = ttk.Frame(self, style="Rail.TFrame", padding=(16, 8, 16, 10))
        tr.pack(fill="x", padx=16, pady=(0, 8))

        left = ttk.Frame(tr, style="Rail.TFrame")
        left.pack(side="left")
        MiniButton(left, "prev", lambda: self.step(-1)).pack(side="left", padx=(0, 6))
        self.play_btn = MiniButton(left, "play", self.toggle_play)
        self.play_btn.pack(side="left", padx=(0, 6))
        MiniButton(left, "stop", self.stop_play).pack(side="left")

        self.tc_lbl = tk.Label(tr, text="кадр — / —", bg=PANEL, fg=MUTED, font=F_MONO_B)
        self.tc_lbl.pack(side="right")
        self.slider = Slider(tr, command=self.on_scrub)
        self.slider.pack(side="right", fill="x", expand=True, padx=16)
        self.slider.set_range(0, 1)

    def _build_statusbar(self):
        bar = ttk.Frame(self, padding=(16, 0, 16, 12))
        bar.pack(fill="x")
        self.status = ttk.Label(bar, text="Откройте изображение, чтобы начать",
                                style="MutedBg.TLabel")
        self.status.pack(side="left")
        self.progress = ttk.Progressbar(bar, mode="determinate", length=220)
        self.progress.pack(side="right")

    def set_frames(self, paths):
        self.frames = paths
        self.slider.set_range(0, max(1, len(paths) - 1))
        self.show_frame(0)

    def show_frame(self, idx):
        if not self.frames:
            return
        self.frame_idx = max(0, min(len(self.frames) - 1, idx))
        self.tc_lbl.configure(
            text=f"кадр {self.frame_idx + 1:03d} / {len(self.frames):03d}")
        self.slider.set_range(self.frame_idx, len(self.frames) - 1)
        self.render_preview()
        self.eq.pulse(self.frame_idx * 0.7)

    def on_scrub(self, frac):
        if self.frames:
            self.show_frame(int(round(frac * (len(self.frames) - 1))))

    def step(self, delta):
        if self.frames:
            self.show_frame(self.frame_idx + delta)

    def toggle_play(self):
        if not self.frames:
            return
        self.playing = not self.playing
        self.play_btn.icon = "pause" if self.playing else "play"
        self.play_btn.draw()
        if self.playing:
            if self.frame_idx >= len(self.frames) - 1:
                self.show_frame(0)
            self._tick()

    def _tick(self):
        if not self.playing:
            return
        self.show_frame((self.frame_idx + 1) % len(self.frames))
        self.after(90, self._tick)

    def stop_play(self):
        if self.playing:
            self.playing = False
            self.play_btn.icon = "play"
            self.play_btn.draw()
        self.eq.playing = False
        self.eq.render()

    # ═══════════════ генерация ═══════════════

    def generate(self):
        if self.img_rgb is None:
            messagebox.showinfo("Нет изображения", "Сначала откройте скриншот.")
            return
        out = self.out_var.get().strip()
        if not out:
            messagebox.showinfo("Нет папки", "Укажите папку для кадров.")
            return

        self.stop_play()
        self.frames = []
        self.gen_btn.state(["disabled"])
        t0 = time.time()
        self.progress.configure(value=0, maximum=100)
        self.prog_bar.configure(value=0, maximum=100)
        self.prog_lbl.configure(text="генерация…")
        self.status.configure(text="Генерация…")

        def prog(i, total):
            self.progress.configure(maximum=total, value=i)
            self.prog_bar.configure(maximum=total, value=i)
            self.prog_lbl.configure(text=f"кадр {i} / {total}")
            self.update_idletasks()

        def done_report(kind, message):
            elapsed = time.time() - t0
            self.prog_lbl.configure(text=f"{message}  ·  {elapsed:.1f} с")
            core.play_sound(kind, self.settings.get("sound_style", "short")
                            if self.settings.get("sound") else "off")

        try:
            if self.mode == "reveal":
                bg = core.hex_to_rgb(self.bg_var.get())
                paths, words, lines = core.render_reveal(
                    self.image_path, out, bg,
                    ink_threshold=self.reveal_rows["ink"].get(),
                    erase_threshold=self.reveal_rows["erase"].get(),
                    space_gap=self.reveal_rows["space"].get(),
                    dilate=self.reveal_rows["dilate"].get(),
                    progress=prog)
                report = f"Готово: {len(paths)} кадров · {len(words)} слов · {len(lines)} строк"
                self.status.configure(text=f"{report}  ·  сохранено в {out}")
                done_report("done", report)
            else:
                text = self.text_var.get().strip()
                if not text:
                    raise RuntimeError("Введите текст субтитров.")
                box = self.font_box or (20, 20, self.img_rgb.width - 20,
                                        self.img_rgb.height - 20)
                paths = core.render_font(
                    self.image_path, out, text, box,
                    text_color=core.hex_to_rgb(self.tcol_var.get()),
                    font_size=self.fs_var.get(),
                    font_path=self.font_var.get().strip() or None,
                    title=self.title_var.get().strip(),
                    progress=prog)
                report = f"Готово: {len(paths)} кадров · {len(text.split())} слов"
                self.status.configure(text=f"{report}  ·  сохранено в {out}")
                done_report("done", report)
            self.set_frames(paths)
            self.toggle_play()
        except Exception as e:
            log_uncaught(*sys.exc_info())
            self.status.configure(text=f"Ошибка: {e}")
            self.prog_lbl.configure(text="ошибка")
            core.play_sound("error", self.settings.get("sound_style", "short")
                            if self.settings.get("sound") else "off")
            messagebox.showerror("Ошибка", str(e))
        finally:
            self.gen_btn.state(["!disabled"])
            self.progress.configure(value=0)

    def _on_close(self):
        self.playing = False
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
