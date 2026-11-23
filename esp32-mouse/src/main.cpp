// AirMirror Mouse: ESP32 jadi mouse Bluetooth LE untuk iPhone (pakai AssistiveTouch).
// PC mengirim perintah teks lewat USB serial (115200), satu perintah per baris:
//   M dx dy   gerak kursor relatif (boleh besar, dipecah otomatis)
//   H         homing: dorong kursor ke pojok kiri-atas
//   C         klik kiri         D = tahan kiri     U = lepas kiri
//   R         klik kanan
//   W n       scroll roda (n positif = ke atas)
//   S         tanya status      -> "CONN 1" atau "CONN 0"
//   P         ping              -> "PONG"
#include <Arduino.h>
#include <BleMouse.h>

BleMouse mouse("AirMirror Mouse", "AirMirror", 100);

static const int STEP = 100;      // max per laporan HID (<=127)
static const int STEP_DELAY = 6;  // ms antar laporan; konstan supaya akselerasi iOS stabil

bool lastConn = false;
String line;

void moveBy(int dx, int dy) {
  while (dx != 0 || dy != 0) {
    int sx = constrain(dx, -STEP, STEP);
    int sy = constrain(dy, -STEP, STEP);
    mouse.move(sx, sy);
    dx -= sx;
    dy -= sy;
    delay(STEP_DELAY);
  }
}

void handle(const String &cmd) {
  if (cmd.length() == 0) return;
  char c = cmd[0];
  if (c == 'P') {
    Serial.println("PONG");
    return;
  }
  if (c == 'S') {
    Serial.println(mouse.isConnected() ? "CONN 1" : "CONN 0");
    return;
  }
  if (!mouse.isConnected()) {
    Serial.println("ERR notconnected");
    return;
  }
  if (c == 'M') {
    int dx = 0, dy = 0;
    if (sscanf(cmd.c_str() + 1, "%d %d", &dx, &dy) == 2) moveBy(dx, dy);
  } else if (c == 'H') {
    // 40 laporan x 100 = 4000 hitungan ke kiri-atas, cukup melewati layar iPhone mana pun
    for (int i = 0; i < 40; i++) {
      mouse.move(-STEP, -STEP);
      delay(STEP_DELAY);
    }
  } else if (c == 'C') {
    mouse.click(MOUSE_LEFT);
  } else if (c == 'D') {
    mouse.press(MOUSE_LEFT);
  } else if (c == 'U') {
    mouse.release(MOUSE_LEFT);
  } else if (c == 'R') {
    mouse.click(MOUSE_RIGHT);
  } else if (c == 'W') {
    int n = 0;
    if (sscanf(cmd.c_str() + 1, "%d", &n) == 1) mouse.move(0, 0, constrain(n, -127, 127));
  }
  Serial.println("OK");
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(20);
  mouse.begin();
  Serial.println("READY");
}

void loop() {
  bool conn = mouse.isConnected();
  if (conn != lastConn) {
    lastConn = conn;
    Serial.println(conn ? "EVENT connected" : "EVENT disconnected");
  }
  while (Serial.available()) {
    char ch = (char)Serial.read();
    if (ch == '\n') {
      line.trim();
      handle(line);
      line = "";
    } else if (ch != '\r' && line.length() < 64) {
      line += ch;
    }
  }
}
