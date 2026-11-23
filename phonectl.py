"""Kontrol iPhone dari PC lewat ESP32 (mouse BLE). Protokol: lihat esp32-mouse/src/main.cpp."""
import ctypes
import ctypes.wintypes as wt
import queue
import threading
import time

import serial
import serial.tools.list_ports

user32 = ctypes.windll.user32


class MouseLink:
    """Koneksi serial ke ESP32 + pelacakan posisi kursor virtual di iPhone."""

    def __init__(self):
        self.ser = None
        self.port = None
        self.phone_connected = False
        self.q = queue.Queue()
        self.lock = threading.Lock()
        self.cx = 0.0  # posisi kursor perkiraan (hitungan mouse dari pojok kiri-atas)
        self.cy = 0.0
        self.gestures = 0
        self.screen_w = 390.0  # lebar/tinggi layar iPhone dalam point
        self.screen_h = 844.0
        self.scale = 1.0  # hitungan mouse per point (kalibrasi)

    # ---------- koneksi ----------
    @staticmethod
    def find_port():
        for p in serial.tools.list_ports.comports():
            try:
                s = serial.Serial(p.device, 115200, timeout=0.6, write_timeout=0.6)
            except (serial.SerialException, OSError):
                continue
            try:
                time.sleep(0.15)
                s.reset_input_buffer()
                s.write(b"P\n")
                end = time.time() + 1.0
                buf = b""
                while time.time() < end:
                    buf += s.read(64)
                    if b"PONG" in buf:
                        return p.device
            finally:
                s.close()
        return None

    def connect(self, port=None):
        port = port or self.find_port()
        if not port:
            raise RuntimeError("ESP32 tidak ditemukan. Colok board lewat USB dan pastikan firmware sudah di-flash.")
        self.close()
        self.ser = serial.Serial(port, 115200, timeout=0.1, write_timeout=1)
        self.port = port
        threading.Thread(target=self._reader, args=(self.ser,), daemon=True).start()
        self.send("S")
        return port

    def close(self):
        s, self.ser = self.ser, None
        if s:
            try:
                s.close()
            except OSError:
                pass
        self.port = None
        self.phone_connected = False

    @property
    def usb_ok(self):
        return self.ser is not None

    def _reader(self, ser):
        buf = b""
        while ser is self.ser:
            try:
                buf += ser.read(64)
            except (serial.SerialException, OSError):
                break
            while b"\n" in buf:
                ln, buf = buf.split(b"\n", 1)
                t = ln.decode(errors="ignore").strip()
                if t in ("CONN 1", "EVENT connected"):
                    self.phone_connected = True
                elif t in ("CONN 0", "EVENT disconnected"):
                    self.phone_connected = False
                self.q.put(t)
        if ser is self.ser:
            self.ser = None
            self.phone_connected = False

    def send(self, cmd):
        s = self.ser
        if not s:
            return False
        try:
            with self.lock:
                s.write((cmd + "\n").encode())
            return True
        except (serial.SerialException, OSError):
            self.ser = None
            return False

    # ---------- gerakan ----------
    def home(self):
        self.send("H")
        self.cx = self.cy = 0.0
        self.gestures = 0
        time.sleep(0.3)  # tunggu ESP32 selesai mengirim laporan homing

    def _clamp(self):
        self.cx = min(max(self.cx, 0.0), self.screen_w * self.scale)
        self.cy = min(max(self.cy, 0.0), self.screen_h * self.scale)

    # Akselerasi pointer iOS bergantung pada kecepatan gerak. Dengan kecepatan konstan dan rendah
    # (STEP_PC hitungan tiap INTERVAL detik) hubungan hitungan -> point jadi stabil dan bisa dikalibrasi.
    SPEEDS = {"Pelan": (8, 0.010), "Sedang": (20, 0.008), "Cepat": (40, 0.008)}
    STEP_PC, INTERVAL = SPEEDS["Sedang"]

    def set_speed(self, name):
        self.STEP_PC, self.INTERVAL = self.SPEEDS.get(name, self.SPEEDS["Sedang"])

    def slow_move(self, dx, dy):
        n = max(1, -(-max(abs(dx), abs(dy)) // self.STEP_PC))
        t0 = time.perf_counter()
        px = py = 0
        for i in range(1, n + 1):
            nx, ny = round(dx * i / n), round(dy * i / n)
            if nx != px or ny != py:
                self.send(f"M {nx - px} {ny - py}")
                px, py = nx, ny
            wait = t0 + i * self.INTERVAL - time.perf_counter()
            if wait > 0:
                time.sleep(wait)

    def move_to(self, fx, fy):
        """fx,fy = posisi 0..1 di layar iPhone."""
        tx = min(max(fx, 0.0), 1.0) * self.screen_w * self.scale
        ty = min(max(fy, 0.0), 1.0) * self.screen_h * self.scale
        dx, dy = round(tx - self.cx), round(ty - self.cy)
        if dx or dy:
            self.slow_move(dx, dy)
        self.cx, self.cy = tx, ty

    def calibrate(self, grab, video_w_px, video_h_px):
        """Ukur skala (hitungan mouse per point) dari posisi kursor asli di layar mirror.
        grab() -> array grayscale 2D dari area video. Mengembalikan skala baru."""
        self.home()
        self.slow_move(250, 250)
        time.sleep(0.8)
        a = grab()
        self.slow_move(320, 0)
        time.sleep(0.8)
        b = grab()
        self.slow_move(0, 320)
        time.sleep(0.8)
        c = grab()
        self.cx, self.cy = 570.0, 570.0
        mx = measure_shift(a, b, axis=1)
        my = measure_shift(b, c, axis=0)
        px_x = mx * self.screen_w / video_w_px  # point yang ditempuh
        px_y = my * self.screen_h / video_h_px
        if px_x < 5 or px_y < 5:
            raise RuntimeError("Kursor tidak terdeteksi di layar mirror. Pastikan AssistiveTouch aktif dan "
                               "iPhone sedang tersambung.")
        sx, sy = 320.0 / px_x, 320.0 / px_y
        if not (0.1 < sx < 6 and 0.1 < sy < 6):
            raise RuntimeError(f"Hasil ukur tidak masuk akal (x{sx:.2f} / y{sy:.2f}).")
        return (sx + sy) / 2.0, sx, sy

    def press(self, fx, fy):
        if self.gestures >= 12:  # kurangi drift dengan homing berkala
            self.home()
        self.gestures += 1
        self.move_to(fx, fy)
        self.send("D")

    def drag_to(self, fx, fy):
        self.move_to(fx, fy)

    def release(self):
        self.send("U")

    def tap(self, fx, fy):
        self.press(fx, fy)
        self.release()

    def scroll(self, n):
        self.send(f"W {int(n)}")


def measure_shift(a, b, axis):
    """Jarak (piksel) antara posisi kursor di frame a dan b, dari selisih gambar.
    axis=1 -> geser horizontal, axis=0 -> vertikal."""
    import numpy as np
    d = np.abs(b.astype(np.int16) - a.astype(np.int16))
    mask = d > 18
    ys, xs = np.nonzero(mask)
    if len(xs) < 30:
        return 0.0
    pos = (xs if axis == 1 else ys).astype(np.float64)
    # 2-means 1D: kursor lama dan kursor baru
    c1, c2 = float(pos.min()), float(pos.max())
    for _ in range(20):
        sel = np.abs(pos - c1) <= np.abs(pos - c2)
        if sel.all() or (~sel).all():
            return 0.0
        n1, n2 = pos[sel].mean(), pos[~sel].mean()
        if abs(n1 - c1) < 0.01 and abs(n2 - c2) < 0.01:
            break
        c1, c2 = n1, n2
    return abs(c2 - c1)


# ---------- overlay di atas jendela mirror ----------
def find_windows_of_pid(pid):
    res = []
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def cb(hwnd, _):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            res.append(hwnd)
        return True

    user32.EnumWindows(CB(cb), 0)
    return res


def client_rect_screen(hwnd):
    """Persegi area konten jendela (x, y, w, h) dalam piksel layar."""
    r = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    pt = wt.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y, r.right - r.left, r.bottom - r.top


def fit_rect(x, y, w, h, aspect):
    """Persegi video (aspect = lebar/tinggi) yang ditampilkan di tengah area w x h."""
    if w <= 0 or h <= 0:
        return x, y, 0, 0
    if w / h > aspect:
        vw, vh = h * aspect, h
    else:
        vw, vh = w, w / aspect
    return x + (w - vw) / 2, y + (h - vh) / 2, vw, vh
