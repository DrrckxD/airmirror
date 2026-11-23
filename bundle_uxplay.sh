#!/bin/bash
# Jalankan di MSYS2 UCRT64:  bash bundle_uxplay.sh
# Mengumpulkan uxplay.exe + semua DLL + plugin GStreamer yang dibutuhkan ke folder ./uxplay
set -e
cd "$(dirname "$0")"
OUT=uxplay
SRC=/ucrt64
PLUGINS="coreelements app playback typefindfunctions videoconvertscale videoparsersbad libav \
audioconvert audioresample volume level audioparsers d3d11 d3d12 wasapi2 wasapi autodetect \
isomp4 videorate audiorate"

mkdir -p "$OUT/plugins"
EXE=$OUT/uxplay.exe
[ -f "$EXE" ] || { echo "uxplay.exe tidak ada di $OUT"; exit 1; }

FILES="$EXE"
for p in $PLUGINS; do
  f="$SRC/lib/gstreamer-1.0/libgst$p.dll"
  if [ -f "$f" ]; then cp -f "$f" "$OUT/plugins/"; FILES="$FILES $f"; else echo "skip plugin: $p"; fi
done
cp -f "$SRC/libexec/gstreamer-1.0/gst-plugin-scanner.exe" "$OUT/"
FILES="$FILES $SRC/libexec/gstreamer-1.0/gst-plugin-scanner.exe"

# kumpulkan dependensi DLL (rekursif) yang berada di /ucrt64
for f in $FILES; do
  ntldd -R "$f" 2>/dev/null | awk '/=>/ {print $3}' | tr '\\' '/' | grep -i "ucrt64/bin" || true
done | sed 's#^\([A-Za-z]\):#/\L\1#' | sort -u > /tmp/dlls.txt

n=0
while read -r d; do
  [ -f "$d" ] && cp -f "$d" "$OUT/" && n=$((n+1))
done < /tmp/dlls.txt
echo "DLL disalin: $n"
du -sh "$OUT"
