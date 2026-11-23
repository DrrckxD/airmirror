# AirMirror

Mirroring layar iPhone ke Windows **tanpa kabel**, plus kontrol iPhone dari PC memakai ESP32 sebagai mouse Bluetooth.

- **Mirroring**: PC jadi AirPlay receiver (memakai [UxPlay](https://github.com/FDH2/UxPlay)). Di iPhone cukup Control Center, Screen Mirroring.
- **GUI**: `airmirror.py` (customtkinter): nama perangkat, resolusi, FPS, fullscreen, suara, rekam MP4.
- **Kontrol iPhone**: ESP32 jadi mouse BLE ("AirMirror Mouse") untuk AssistiveTouch iOS. PC mengirim perintah lewat USB serial. Klik di jendela mirror menjadi tap di iPhone, ada kalibrasi otomatis.

> AirPlay hanya mengirim layar, jadi kontrol tidak lewat AirPlay. Konten berDRM (Netflix dkk.) tampil hitam, itu pembatasan Apple.

## Isi repo

| Path | Fungsi |
|---|---|
| `airmirror.py` | GUI utama |
| `phonectl.py` | Koneksi serial ke ESP32, overlay klik, kalibrasi kursor |
| `bundle_uxplay.sh` | Mengumpulkan `uxplay.exe` + DLL + plugin GStreamer ke `uxplay/` |
| `esp32-mouse/` | Firmware ESP32 (PlatformIO) |

## Persiapan (Windows)

1. Install [MSYS2](https://www.msys2.org/) dan Python 3.12.
2. Build UxPlay di shell **MSYS2 UCRT64**:
   ```bash
   pacman -S --needed mingw-w64-ucrt-x86_64-{gcc,cmake,ninja,pkgconf,openssl,libplist,gstreamer,gst-plugins-base,gst-plugins-good,gst-plugins-bad,gst-libav,libx264,ntldd} git
   git clone --depth 1 https://github.com/FDH2/UxPlay.git
   cd UxPlay && mkdir build && cd build && cmake -G Ninja -DCMAKE_BUILD_TYPE=Release .. && ninja
   ```
3. Salin `uxplay.exe` ke folder `uxplay/` di sebelah `airmirror.py`, lalu bundel dependensinya (dari shell UCRT64):
   ```bash
   bash bundle_uxplay.sh
   ```
4. Install dependensi Python:
   ```powershell
   py -m pip install customtkinter pyserial pillow numpy
   ```
5. Jalankan:
   ```powershell
   py airmirror.py
   ```
6. (Opsional) Jadikan `.exe`:
   ```powershell
   py -m pip install pyinstaller
   py -m PyInstaller --onefile --windowed --collect-all customtkinter --name AirMirror airmirror.py
   ```
   Taruh `AirMirror.exe` sejajar dengan folder `uxplay/`.

## Cara pakai mirroring

1. Klik **Mulai**. Izinkan **Private networks** di Windows Firewall. Kalau Wi-Fi berprofil *Public*, ubah ke Private atau buat rule firewall untuk `uxplay.exe`.
2. iPhone dan PC di jaringan yang sama. Di iPhone: Control Center, Screen Mirroring, pilih nama perangkat.

## Kontrol iPhone dengan ESP32

Butuh board **ESP32 klasik** (punya Bluetooth), mis. ESP32 DevKit.

1. Flash firmware:
   ```powershell
   cd esp32-mouse
   py -m pip install platformio
   py -m platformio run -t upload
   ```
   Kalau gagal "Wrong boot mode", tahan tombol **BOOT** saat proses menyambung.
2. Di iPhone: Settings, Accessibility, Touch, **AssistiveTouch** ON, lalu Devices, Bluetooth Devices, pilih **AirMirror Mouse**.
3. Di AirMirror tab **Kontrol**: Cari & hubungkan ESP32, nyalakan kontrol, pilih kecepatan, lalu **Kalibrasi otomatis**.

Mouse BLE hanya bergerak relatif, jadi posisi tap dihitung dari pojok kiri-atas dan bisa meleset sedikit. Kalibrasi diukur per kecepatan kursor.

## Kredit

- [UxPlay](https://github.com/FDH2/UxPlay) (GPL-3.0), mesin AirPlay receiver.
- [ESP32-BLE-Mouse](https://github.com/T-vK/ESP32-BLE-Mouse), library mouse BLE.
