"""AirMirror - mirroring iPhone ke Windows lewat AirPlay (memakai UxPlay)."""
import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from phonectl import MouseLink, client_rect_screen, find_windows_of_pid, fit_rect

HERE = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
MSYS = r"C:\msys64\ucrt64\bin"
CFG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "AirMirror")
CFG_FILE = os.path.join(CFG_DIR, "settings.json")

# palet warna
BG = "#0f1115"
CARD = "#181b22"
CARD2 = "#1f232c"
TEXT = "#e8eaf0"
MUTED = "#8b93a5"
ACCENT = "#4f8cff"
ACCENT_H = "#3a73e0"
GREEN = "#2ecc71"
RED = "#e5484d"
RED_H = "#c93a3f"
AMBER = "#f5a524"


def find_uxplay():
    for p in (os.path.join(HERE, "uxplay", "uxplay.exe"),
              os.path.join(HERE, "uxplay.exe"),
              os.path.join(MSYS, "uxplay.exe"),
              shutil.which("uxplay") or ""):
        if p and os.path.isfile(p):
            return p
    return None


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "-"


def load_cfg():
    try:
        with open(CFG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_cfg(d):
    try:
        os.makedirs(CFG_DIR, exist_ok=True)
        with open(CFG_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except OSError:
        pass


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("AirMirror")
        self.geometry("520x940")
        self.minsize(480, 860)
        self.configure(fg_color=BG)

        cfg = load_cfg()
        self.proc = None
        self.q = queue.Queue()
        self.conn = "idle"  # idle | waiting | streaming
        self.pulse_on = False

        self.name = ctk.StringVar(value=cfg.get("name", "AirMirror-PC"))
        self.res = ctk.StringVar(value=cfg.get("res", "1920x1080"))
        self.fps = ctk.StringVar(value=cfg.get("fps", "60"))
        self.fullscreen = ctk.BooleanVar(value=cfg.get("fullscreen", False))
        self.audio = ctk.BooleanVar(value=cfg.get("audio", True))
        self.record = ctk.BooleanVar(value=cfg.get("record", False))
        self.recdir = ctk.StringVar(value=cfg.get("recdir", os.path.join(os.path.expanduser("~"), "Videos")))

        self.build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.poll)
        self.after(600, self.pulse)
        if not find_uxplay():
            self.log_write("uxplay.exe tidak ditemukan. Taruh di folder 'uxplay' di sebelah AirMirror.exe.\n")

    # ---------- UI ----------
    def card(self, parent, **kw):
        return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=16, **kw)

    def build_ui(self):
        root = ctk.CTkFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=20, pady=18)

        # header
        head = ctk.CTkFrame(root, fg_color="transparent")
        head.pack(fill="x")
        logo = ctk.CTkLabel(head, text="◉", font=("Segoe UI", 30, "bold"), text_color=ACCENT, width=44)
        logo.pack(side="left")
        tt = ctk.CTkFrame(head, fg_color="transparent")
        tt.pack(side="left", padx=6)
        ctk.CTkLabel(tt, text="AirMirror", font=("Segoe UI", 22, "bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(tt, text="iPhone ke Windows, tanpa kabel", font=("Segoe UI", 12),
                     text_color=MUTED).pack(anchor="w")

        tabs = ctk.CTkTabview(root, fg_color="transparent", segmented_button_selected_color=ACCENT,
                              segmented_button_selected_hover_color=ACCENT_H,
                              segmented_button_unselected_color=CARD, segmented_button_fg_color=CARD,
                              text_color=TEXT, height=10)
        tabs.pack(fill="both", expand=True, pady=(10, 0))
        self.tabs = tabs
        main = tabs.add("Mirror")
        self.build_control(tabs.add("Kontrol"))
        root = main

        # status card
        sc = self.card(root)
        sc.pack(fill="x", pady=(16, 10))
        row = ctk.CTkFrame(sc, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(16, 4))
        self.dot = ctk.CTkLabel(row, text="●", font=("Segoe UI", 20), text_color=MUTED, width=24)
        self.dot.pack(side="left")
        self.status = ctk.CTkLabel(row, text="Tidak aktif", font=("Segoe UI", 17, "bold"), text_color=TEXT)
        self.status.pack(side="left", padx=6)
        self.substatus = ctk.CTkLabel(sc, text="Tekan Mulai untuk membuat PC ini terlihat di iPhone.",
                                      font=("Segoe UI", 12), text_color=MUTED, wraplength=420, justify="left")
        self.substatus.pack(anchor="w", padx=20)
        self.btn = ctk.CTkButton(sc, text="Mulai", height=46, corner_radius=12, font=("Segoe UI", 15, "bold"),
                                 fg_color=ACCENT, hover_color=ACCENT_H, command=self.toggle)
        self.btn.pack(fill="x", padx=18, pady=(14, 18))

        # how-to
        hc = self.card(root)
        hc.pack(fill="x", pady=5)
        ctk.CTkLabel(hc, text="Cara menyambung", font=("Segoe UI", 13, "bold"), text_color=TEXT).pack(
            anchor="w", padx=18, pady=(12, 2))
        self.howto = ctk.CTkLabel(
            hc, text="", font=("Segoe UI", 12), text_color=MUTED, justify="left", wraplength=430)
        self.howto.pack(anchor="w", padx=18, pady=(0, 12))
        self.refresh_howto()

        # settings
        st = self.card(root)
        st.pack(fill="x", pady=5)
        ctk.CTkLabel(st, text="Pengaturan", font=("Segoe UI", 13, "bold"), text_color=TEXT).pack(
            anchor="w", padx=18, pady=(12, 6))
        grid = ctk.CTkFrame(st, fg_color="transparent")
        grid.pack(fill="x", padx=18, pady=(0, 14))
        grid.columnconfigure(1, weight=1)

        def lbl(r, t):
            ctk.CTkLabel(grid, text=t, font=("Segoe UI", 12), text_color=MUTED).grid(
                row=r, column=0, sticky="w", pady=5, padx=(0, 12))

        lbl(0, "Nama perangkat")
        ent = ctk.CTkEntry(grid, textvariable=self.name, fg_color=CARD2, border_width=0, height=32)
        ent.grid(row=0, column=1, columnspan=2, sticky="ew", pady=5)
        self.name.trace_add("write", lambda *a: self.refresh_howto())

        lbl(1, "Resolusi")
        ctk.CTkOptionMenu(grid, variable=self.res, values=["1280x720", "1920x1080", "2560x1440"],
                          fg_color=CARD2, button_color=CARD2, button_hover_color="#2a2f3a",
                          height=32).grid(row=1, column=1, sticky="w", pady=5)
        ctk.CTkSegmentedButton(grid, variable=self.fps, values=["30", "60"], width=100,
                               selected_color=ACCENT, unselected_color=CARD2).grid(
            row=1, column=2, sticky="e", pady=5, padx=(8, 0))

        sw = ctk.CTkFrame(grid, fg_color="transparent")
        sw.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 2))
        ctk.CTkSwitch(sw, text="Fullscreen", variable=self.fullscreen, progress_color=ACCENT).pack(
            side="left", padx=(0, 18))
        ctk.CTkSwitch(sw, text="Suara", variable=self.audio, progress_color=ACCENT).pack(side="left")

        ctk.CTkSwitch(grid, text="Rekam ke MP4", variable=self.record, progress_color=ACCENT).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(8, 2))
        rd = ctk.CTkFrame(grid, fg_color="transparent")
        rd.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        rd.columnconfigure(0, weight=1)
        ctk.CTkEntry(rd, textvariable=self.recdir, fg_color=CARD2, border_width=0, height=30).grid(
            row=0, column=0, sticky="ew")
        ctk.CTkButton(rd, text="Pilih", width=60, height=30, fg_color=CARD2, hover_color="#2a2f3a",
                      command=self.pick_dir).grid(row=0, column=1, padx=(8, 0))

        # log
        lc = self.card(root)
        lc.pack(fill="both", expand=True, pady=(5, 0))
        top = ctk.CTkFrame(lc, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(10, 0))
        ctk.CTkLabel(top, text="Log", font=("Segoe UI", 13, "bold"), text_color=TEXT).pack(side="left")
        ctk.CTkButton(top, text="Bersihkan", width=70, height=24, fg_color="transparent", text_color=MUTED,
                      hover_color=CARD2, command=self.clear_log).pack(side="right")
        self.log = ctk.CTkTextbox(lc, fg_color=CARD2, text_color=MUTED, font=("Consolas", 10),
                                  corner_radius=10, height=110)
        self.log.pack(fill="both", expand=True, padx=14, pady=(6, 14))
        self.log.configure(state="disabled")

    # ---------- kontrol iPhone (ESP32) ----------
    PRESETS = {
        "iPhone SE / 8 (375x667)": (375, 667),
        "iPhone 12/13/14 (390x844)": (390, 844),
        "iPhone 15/16 (393x852)": (393, 852),
        "iPhone Plus/Pro Max (430x932)": (430, 932),
    }

    def build_control(self, parent):
        cfg = load_cfg()
        self.link = MouseLink()
        self.preset = ctk.StringVar(value=cfg.get("preset", "iPhone 12/13/14 (390x844)"))
        self.speed = ctk.StringVar(value=cfg.get("speed", "Sedang"))
        self.scales = cfg.get("scales", {})  # skala hasil kalibrasi per kecepatan
        self.link.set_speed(self.speed.get())
        self.scale_var = ctk.DoubleVar(value=self.scales.get(self.speed.get(), cfg.get("scale", 1.0)))
        self.ctl_on = ctk.BooleanVar(value=False)
        self.overlay = None
        self.ctl_q = queue.Queue()
        self.dragging = False
        self.apply_preset()
        threading.Thread(target=self.ctl_worker, daemon=True).start()

        c1 = self.card(parent)
        c1.pack(fill="x", pady=(6, 5))
        ctk.CTkLabel(c1, text="Koneksi ESP32", font=("Segoe UI", 13, "bold"), text_color=TEXT).pack(
            anchor="w", padx=18, pady=(12, 4))
        self.usb_lbl = ctk.CTkLabel(c1, text="● ESP32 (USB): belum terhubung", font=("Segoe UI", 12),
                                    text_color=MUTED)
        self.usb_lbl.pack(anchor="w", padx=18)
        self.ble_lbl = ctk.CTkLabel(c1, text="● iPhone (Bluetooth): belum terhubung", font=("Segoe UI", 12),
                                    text_color=MUTED)
        self.ble_lbl.pack(anchor="w", padx=18, pady=(2, 8))
        self.conn_btn = ctk.CTkButton(c1, text="Cari & hubungkan ESP32", height=36, fg_color=CARD2,
                                      hover_color="#2a2f3a", command=self.connect_esp)
        self.conn_btn.pack(fill="x", padx=18, pady=(0, 14))

        c2 = self.card(parent)
        c2.pack(fill="x", pady=5)
        ctk.CTkLabel(c2, text="Kontrol", font=("Segoe UI", 13, "bold"), text_color=TEXT).pack(
            anchor="w", padx=18, pady=(12, 4))
        ctk.CTkSwitch(c2, text="Aktifkan kontrol di jendela mirror", variable=self.ctl_on,
                      progress_color=ACCENT, command=self.toggle_overlay).pack(anchor="w", padx=18, pady=4)
        ctk.CTkLabel(c2, text="Klik = tap, tahan lalu geser = swipe, scroll mouse = scroll.",
                     font=("Segoe UI", 11), text_color=MUTED).pack(anchor="w", padx=18)
        ctk.CTkLabel(c2, text="Model iPhone", font=("Segoe UI", 12), text_color=MUTED).pack(
            anchor="w", padx=18, pady=(10, 0))
        ctk.CTkOptionMenu(c2, variable=self.preset, values=list(self.PRESETS), fg_color=CARD2,
                          button_color=CARD2, button_hover_color="#2a2f3a",
                          command=lambda _: self.apply_preset()).pack(fill="x", padx=18, pady=(2, 6))
        ctk.CTkLabel(c2, text="Kecepatan kursor (lebih cepat = lebih sedikit delay)", font=("Segoe UI", 12),
                     text_color=MUTED).pack(anchor="w", padx=18, pady=(4, 0))
        ctk.CTkSegmentedButton(c2, variable=self.speed, values=list(MouseLink.SPEEDS),
                               selected_color=ACCENT, unselected_color=CARD2,
                               command=self.on_speed).pack(fill="x", padx=18, pady=(2, 6))
        self.scale_lbl = ctk.CTkLabel(c2, text="", font=("Segoe UI", 12), text_color=MUTED)
        self.scale_lbl.pack(anchor="w", padx=18)
        ctk.CTkSlider(c2, from_=0.1, to=6.0, variable=self.scale_var, progress_color=ACCENT,
                      command=lambda _: self.apply_preset()).pack(fill="x", padx=18, pady=(2, 8))
        self.cal_btn = ctk.CTkButton(c2, text="Kalibrasi otomatis (ukur kursor di layar)", height=34,
                                     fg_color=ACCENT, hover_color=ACCENT_H, command=self.auto_calibrate)
        self.cal_btn.pack(fill="x", padx=18, pady=(0, 8))
        bt = ctk.CTkFrame(c2, fg_color="transparent")
        bt.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkButton(bt, text="Tes: tap di tengah", height=32, fg_color=CARD2, hover_color="#2a2f3a",
                      command=lambda: self.ctl_q.put(lambda: (self.link.home(), self.link.tap(0.5, 0.5)))
                      ).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ctk.CTkButton(bt, text="Home ulang kursor", height=32, fg_color=CARD2, hover_color="#2a2f3a",
                      command=lambda: self.ctl_q.put(self.link.home)
                      ).pack(side="left", expand=True, fill="x", padx=(4, 0))

        c3 = self.card(parent)
        c3.pack(fill="x", pady=5)
        ctk.CTkLabel(c3, text="Setup sekali di iPhone", font=("Segoe UI", 13, "bold"), text_color=TEXT).pack(
            anchor="w", padx=18, pady=(12, 2))
        ctk.CTkLabel(
            c3, font=("Segoe UI", 12), text_color=MUTED, justify="left", wraplength=430,
            text="1. Settings > Accessibility > Touch > AssistiveTouch: ON.\n"
                 "2. Di situ buka Devices > Bluetooth Devices > pilih \"AirMirror Mouse\".\n"
                 "3. Kalau kursor meleset, geser slider kalibrasi lalu coba \"Tes: tap di tengah\".").pack(
            anchor="w", padx=18, pady=(0, 12))
        self.apply_preset()
        self.after(500, self.ctl_status)

    def apply_preset(self):
        w, h = self.PRESETS.get(self.preset.get(), (390, 844))
        self.link.screen_w, self.link.screen_h = float(w), float(h)
        self.link.scale = round(self.scale_var.get(), 2)
        if hasattr(self, "scale_lbl"):
            self.scale_lbl.configure(text=f"Kalibrasi kecepatan kursor: x{self.link.scale:.2f}")

    def on_speed(self, name):
        self.link.set_speed(name)
        if name in self.scales:
            self.scale_var.set(self.scales[name])
            self.apply_preset()
        else:
            messagebox.showinfo("Kecepatan", f"Kecepatan \"{name}\" belum dikalibrasi. "
                                             "Klik Kalibrasi otomatis supaya tap tetap pas.")
        self.save()

    def auto_calibrate(self):
        lk = self.link
        if not lk.usb_ok:
            messagebox.showwarning("Kalibrasi", "Hubungkan ESP32 dulu.")
            return
        if not lk.phone_connected:
            messagebox.showwarning("Kalibrasi", "iPhone belum terpasang ke \"AirMirror Mouse\" lewat Bluetooth.")
            return
        r = self.video_rect()
        if not r or r[2] < 100:
            messagebox.showwarning("Kalibrasi", "Mulai mirroring dulu, dan jangan minimize jendela mirror.")
            return
        self.cal_btn.configure(state="disabled", text="Mengkalibrasi... jangan sentuh mouse")

        def grab():
            from PIL import ImageGrab
            import numpy as np
            x, y, w, h = self.video_rect() or r
            im = ImageGrab.grab(bbox=(int(x), int(y), int(x + w), int(y + h)), all_screens=True).convert("L")
            return np.asarray(im)

        def job():
            try:
                x, y, w, h = self.video_rect() or r
                s, sx, sy = lk.calibrate(grab, w, h)
                lk.scale = round(s, 2)
                self.scales[self.speed.get()] = lk.scale
                self.save()
                msg = f"Skala terukur x{s:.2f} (x: {sx:.2f}, y: {sy:.2f}). Sudah diterapkan."
                self.after(0, lambda: self.scale_var.set(min(max(s, 0.1), 6.0)))
                self.after(0, self.apply_preset)
            except Exception as e:  # noqa: BLE001
                msg = f"Gagal: {e}"
            self.after(0, lambda: (self.cal_btn.configure(
                state="normal", text="Kalibrasi otomatis (ukur kursor di layar)"),
                messagebox.showinfo("Kalibrasi", msg)))

        threading.Thread(target=job, daemon=True).start()

    def connect_esp(self):
        self.conn_btn.configure(state="disabled", text="Mencari...")

        def job():
            try:
                port = self.link.connect()
                msg = f"Terhubung di {port}"
            except Exception as e:  # noqa: BLE001
                msg = str(e)
            self.after(0, lambda: (self.conn_btn.configure(state="normal", text="Cari & hubungkan ESP32"),
                                   messagebox.showinfo("ESP32", msg)))

        threading.Thread(target=job, daemon=True).start()

    def ctl_status(self):
        lk = self.link
        self.usb_lbl.configure(
            text=f"● ESP32 (USB): {'terhubung di ' + lk.port if lk.usb_ok else 'belum terhubung'}",
            text_color=GREEN if lk.usb_ok else MUTED)
        self.ble_lbl.configure(
            text=f"● iPhone (Bluetooth): {'terhubung' if lk.phone_connected else 'belum terhubung'}",
            text_color=GREEN if lk.phone_connected else MUTED)
        self.after(500, self.ctl_status)

    def ctl_worker(self):
        while True:
            fn = self.ctl_q.get()
            try:
                fn()
            except Exception:  # noqa: BLE001
                pass

    def toggle_overlay(self):
        if self.ctl_on.get():
            if not self.link.usb_ok:
                messagebox.showwarning("Kontrol", "Hubungkan ESP32 dulu.")
                self.ctl_on.set(False)
                return
            self.overlay = tk.Toplevel(self)
            o = self.overlay
            o.overrideredirect(True)
            o.attributes("-topmost", True)
            o.attributes("-alpha", 0.01)
            o.configure(bg="black", cursor="crosshair")
            o.geometry("1x1+0+0")
            o.bind("<ButtonPress-1>", self.ov_press)
            o.bind("<B1-Motion>", self.ov_drag)
            o.bind("<ButtonRelease-1>", self.ov_release)
            o.bind("<MouseWheel>", self.ov_wheel)
            self.track_overlay()
        elif self.overlay:
            self.overlay.destroy()
            self.overlay = None

    def video_rect(self):
        if not self.proc:
            return None
        wins = find_windows_of_pid(self.proc.pid)
        best = None
        for h in wins:
            x, y, w, hh = client_rect_screen(h)
            if w > 100 and hh > 100 and (best is None or w * hh > best[2] * best[3]):
                best = (x, y, w, hh)
        if not best:
            return None
        aspect = self.link.screen_w / self.link.screen_h
        return fit_rect(*best, aspect)

    def track_overlay(self):
        if not self.overlay:
            return
        r = self.video_rect()
        if r and r[2] > 0:
            self.ov_rect = r
            self.overlay.geometry(f"{int(r[2])}x{int(r[3])}+{int(r[0])}+{int(r[1])}")
            self.overlay.deiconify()
            self.overlay.attributes("-topmost", True)
        else:
            self.ov_rect = None
            self.overlay.withdraw()
        self.after(250, self.track_overlay)

    def ov_frac(self, e):
        r = getattr(self, "ov_rect", None)
        if not r or r[2] <= 0:
            return None
        return (e.x_root - r[0]) / r[2], (e.y_root - r[1]) / r[3]

    def ov_press(self, e):
        f = self.ov_frac(e)
        if f:
            self.dragging = True
            self.ctl_q.put(lambda: self.link.press(*f))

    def ov_drag(self, e):
        f = self.ov_frac(e)
        if f and self.dragging and self.ctl_q.qsize() < 3:  # buang gerakan lama kalau antrean menumpuk
            self.ctl_q.put(lambda: self.link.drag_to(*f))

    def ov_release(self, e):
        if self.dragging:
            self.dragging = False
            f = self.ov_frac(e)
            if f:
                self.ctl_q.put(lambda: self.link.drag_to(*f))
            self.ctl_q.put(self.link.release)

    def ov_wheel(self, e):
        self.ctl_q.put(lambda: self.link.scroll(1 if e.delta > 0 else -1))

    def refresh_howto(self):
        n = self.name.get().strip() or "AirMirror-PC"
        self.howto.configure(
            text=f"1. Pastikan iPhone dan PC di WiFi yang sama.\n"
                 f"2. Di iPhone buka Control Center, lalu Screen Mirroring.\n"
                 f"3. Pilih \"{n}\".\n"
                 f"IP PC ini: {local_ip()}")

    def pick_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.recdir.set(d)

    def log_write(self, s):
        self.log.configure(state="normal")
        self.log.insert("end", s)
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def set_state(self, st, detail=None):
        self.conn = st
        if st == "idle":
            self.dot.configure(text_color=MUTED)
            self.status.configure(text="Tidak aktif")
            self.substatus.configure(text="Tekan Mulai untuk membuat PC ini terlihat di iPhone.")
            self.btn.configure(text="Mulai", fg_color=ACCENT, hover_color=ACCENT_H)
        elif st == "waiting":
            self.dot.configure(text_color=AMBER)
            self.status.configure(text="Menunggu iPhone")
            self.substatus.configure(text="Siap. Pilih perangkat ini di Screen Mirroring.")
            self.btn.configure(text="Berhenti", fg_color=RED, hover_color=RED_H)
        elif st == "streaming":
            self.dot.configure(text_color=GREEN)
            self.status.configure(text="Terhubung")
            self.substatus.configure(text=detail or "iPhone sedang di-mirror.")
            self.btn.configure(text="Berhenti", fg_color=RED, hover_color=RED_H)

    def pulse(self):
        if self.conn in ("waiting", "streaming"):
            self.pulse_on = not self.pulse_on
            base = AMBER if self.conn == "waiting" else GREEN
            self.dot.configure(text_color=base if self.pulse_on else CARD2)
        self.after(700, self.pulse)

    # ---------- logika ----------
    def save(self):
        save_cfg({"name": self.name.get(), "res": self.res.get(), "fps": self.fps.get(),
                  "fullscreen": self.fullscreen.get(), "audio": self.audio.get(),
                  "record": self.record.get(), "recdir": self.recdir.get(),
                  "preset": self.preset.get(), "scale": round(self.scale_var.get(), 2),
                  "speed": self.speed.get(), "scales": self.scales})

    def build_cmd(self, exe):
        w, h = self.res.get().split("x")
        cmd = [exe, "-n", self.name.get().strip() or "AirMirror-PC",
               "-s", f"{w}x{h}", "-fps", self.fps.get(), "-nohold"]
        if self.fullscreen.get():
            cmd.append("-fs")
        if not self.audio.get():
            cmd.extend(["-as", "0"])
        if self.record.get():
            d = self.recdir.get().strip() or os.path.join(os.path.expanduser("~"), "Videos")
            os.makedirs(d, exist_ok=True)
            cmd.extend(["-mp4", os.path.join(d, "AirMirror_" + time.strftime("%Y%m%d_%H%M%S"))])
        return cmd

    def make_env(self, exe):
        env = os.environ.copy()
        exedir = os.path.dirname(exe)
        plugins = os.path.join(exedir, "plugins")
        if os.path.isdir(plugins):
            env["PATH"] = exedir + os.pathsep + env.get("PATH", "")
            env["GST_PLUGIN_PATH"] = plugins
            env["GST_PLUGIN_SYSTEM_PATH"] = plugins
            env["GST_PLUGIN_SCANNER"] = os.path.join(exedir, "gst-plugin-scanner.exe")
            os.makedirs(CFG_DIR, exist_ok=True)
            env["GST_REGISTRY"] = os.path.join(CFG_DIR, "registry.bin")
        else:
            env["PATH"] = exedir + os.pathsep + MSYS + os.pathsep + env.get("PATH", "")
            env.setdefault("GST_PLUGIN_PATH", os.path.join(os.path.dirname(MSYS), "lib", "gstreamer-1.0"))
        return env

    def toggle(self):
        if self.proc:
            self.stop()
            return
        exe = find_uxplay()
        if not exe:
            messagebox.showerror("AirMirror", "uxplay.exe tidak ditemukan.")
            return
        self.save()
        cmd = self.build_cmd(exe)
        self.log_write("> " + " ".join(cmd) + "\n")
        try:
            self.proc = subprocess.Popen(cmd, env=self.make_env(exe), stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, text=True, errors="replace",
                                         creationflags=0x08000000)
        except OSError as e:
            messagebox.showerror("AirMirror", str(e))
            return
        threading.Thread(target=self.reader, args=(self.proc,), daemon=True).start()
        self.set_state("waiting")

    def reader(self, p):
        for line in p.stdout:
            self.q.put((p, line))
        self.q.put((p, None))

    def poll(self):
        try:
            while True:
                p, line = self.q.get_nowait()
                if line is None:
                    if p is self.proc:
                        self.proc = None
                        self.set_state("idle")
                    continue
                if p is not self.proc:
                    continue
                self.log_write(line)
                low = line.lower()
                if "begin streaming" in low or "connection opened" in low:
                    self.set_state("streaming")
                elif self.conn == "streaming" and ("connection closed" in low or "stopping" in low):
                    self.set_state("waiting")
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def stop(self):
        if self.proc:
            self.proc.terminate()

    def on_close(self):
        self.save()
        self.stop()
        self.link.send("U")
        self.link.close()
        self.destroy()


if __name__ == "__main__":
    app = App()
    if "--autostart" in sys.argv:
        app.after(500, app.toggle)
    for a in sys.argv:
        if a.startswith("--tab="):
            app.after(300, lambda t=a[6:]: app.tabs.set(t))
    app.mainloop()
