/*
  Arduino Uno two-player table-tennis game.
  Wokwi wiring is in diagram.json. The PC GUI consumes the simple serial protocol
  documented in README.md.
*/
#include <Arduino.h>
#include <stdio.h>

// Ultrasonic sensors: P1 left/right, then P2 left/right.
const uint8_t TRIG_PINS[4] = {4, 6, 8, 10};
const uint8_t ECHO_PINS[4] = {5, 7, 9, 11};
const uint8_t SERVE_P1_PIN = 2;
const uint8_t SERVE_P2_PIN = 3;
const uint8_t BUZZER_PIN = 12;

volatile bool serveP1Event = false;
volatile bool serveP2Event = false;
volatile uint32_t lastP1ButtonUs = 0;
volatile uint32_t lastP2ButtonUs = 0;

// Ball position: 0 = P1 end, 100 = P2 end. P1 serves toward the right.
float ballX = 50.0f;
float ballV = 0.0f;            // table-percent per second
uint32_t lastBallMs = 0;
uint32_t lastShotMs = 0;
uint32_t lastTelemetryMs = 0;
uint32_t lastSensorMs = 0;

float distanceCm[4] = {80, 80, 80, 80};
float previousDistanceCm[4] = {80, 80, 80, 80};
uint32_t previousDistanceMs = 0;
float speedCmS[4] = {0, 0, 0, 0};
float keyboardSpeedCmS[4] = {0, 0, 0, 0};
uint32_t keyboardOverrideUntil = 0;

uint8_t scoreP1 = 0;
uint8_t scoreP2 = 0;
uint8_t servingPlayer = 1;
bool rallyStarted = false;
bool gameOver = false;
uint8_t winner = 0;
bool swingActive[2] = {false, false};

const uint32_t SHOT_COOLDOWN_MS = 450;
const uint32_t BUTTON_DEBOUNCE_US = 220000UL;
const float MIN_HAND_SPEED = 5.0f;

// Complete board snapshot, separate from the compact GUI protocol.
void logGameEvent(const char* kind, uint8_t player, const char* state, float flightTime = 0) {
  Serial.print(F("EVENT,")); Serial.print(kind);
  Serial.print(','); Serial.print(millis());
  Serial.print(','); Serial.print(player);
  Serial.print(','); Serial.print(state);
  Serial.print(','); Serial.print(ballX, 2);
  Serial.print(','); Serial.print(scoreP1);
  Serial.print(','); Serial.print(scoreP2);
  Serial.print(','); Serial.print(servingPlayer);
  Serial.print(','); Serial.print(winner);
  Serial.print(','); Serial.print(millis() < keyboardOverrideUntil ? F("GUI") : F("ULTRASONIC"));
  for (uint8_t i = 0; i < 4; i++) { Serial.print(','); Serial.print(distanceCm[i], 2); }
  for (uint8_t i = 0; i < 4; i++) { Serial.print(','); Serial.print(speedCmS[i], 2); }
  uint8_t left = player == 2 ? 2 : 0;
  Serial.print(','); Serial.print(player ? (speedCmS[left] + speedCmS[left + 1]) / 2.0f : 0, 2);
  Serial.print(','); Serial.print(player ? speedCmS[left + 1] - speedCmS[left] : 0, 2);
  Serial.print(','); Serial.println(flightTime, 2);
}

void detectSwings() {
  for (uint8_t p = 0; p < 2; p++) {
    float power = (speedCmS[p * 2] + speedCmS[p * 2 + 1]) / 2.0f;
    bool active = power >= MIN_HAND_SPEED;
    if (active && !swingActive[p]) {
      bool inZone = p == 0 ? ballX <= 15.0f : ballX >= 85.0f;
      const char* state = gameOver ? "GAME_OVER" : !rallyStarted ? "WAITING_SERVE" :
        !inZone ? "OUT_OF_ZONE" : millis() - lastShotMs < SHOT_COOLDOWN_MS ? "COOLDOWN" : "READY";
      logGameEvent("SWING", p + 1, state);
    }
    swingActive[p] = active;
  }
}

void onServeP1() {
  uint32_t now = micros();
  if ((uint32_t)(now - lastP1ButtonUs) > BUTTON_DEBOUNCE_US) {
    serveP1Event = true;
    lastP1ButtonUs = now;
  }
}

void onServeP2() {
  uint32_t now = micros();
  if ((uint32_t)(now - lastP2ButtonUs) > BUTTON_DEBOUNCE_US) {
    serveP2Event = true;
    lastP2ButtonUs = now;
  }
}

void sendScore() {
  Serial.print("SCORE,");
  Serial.print(scoreP1);
  Serial.print(',');
  Serial.print(scoreP2);
  Serial.print(",SERVE,");
  Serial.println(servingPlayer);
}

void sendBall() {
  Serial.print("BALL,");
  Serial.println(ballX, 2);
}

void message(const __FlashStringHelper* text) {
  Serial.print("MSG,");
  Serial.println(text);
}

void message(const char* text) {
  Serial.print("MSG,");
  Serial.println(text);
}

void beep(uint16_t frequency, uint16_t durationMs) {
  tone(BUZZER_PIN, frequency, durationMs);
}

void resetRallyForServe(uint8_t player) {
  servingPlayer = player;
  rallyStarted = true;
  gameOver = false;
  winner = 0;
  ballX = (player == 1) ? 12.0f : 88.0f;
  // A serve travels toward the opponent.
  ballV = (player == 1) ? 35.0f : -35.0f;
  lastBallMs = millis();
  lastShotMs = millis();
  message(player == 1 ? F("P1 SERVES") : F("P2 SERVES"));
  beep(880, 90);
  sendScore();
  sendBall();
  logGameEvent("SERVE", player, "RALLY_STARTED");
}

void registerPoint(uint8_t pointWinner, const char* reason) {
  if (gameOver) return;
  if (pointWinner == 1) scoreP1++;
  else scoreP2++;
  message(reason);
  beep(660, 280);
  delay(20);
  beep(pointWinner == 1 ? 880 : 1040, 180);

  if ((scoreP1 >= 11 || scoreP2 >= 11) && abs((int)scoreP1 - (int)scoreP2) >= 2) {
    gameOver = true;
    winner = pointWinner;
    Serial.print("WINNER,");
    Serial.println(winner);
    message(winner == 1 ? F("P1 WINS") : F("P2 WINS"));
    sendScore();
    logGameEvent("POINT", 0, reason);
    return;
  }

  // The serve changes every two points; after 10-10 it changes every point.
  uint8_t total = scoreP1 + scoreP2;
  if (total >= 20 || (total % 2 == 0 && total > 0)) {
    servingPlayer = (servingPlayer == 1) ? 2 : 1;
  }
  sendScore();
  rallyStarted = false;
  ballX = (servingPlayer == 1) ? 12.0f : 88.0f;
  ballV = 0;
  sendBall();
  logGameEvent("POINT", 0, reason);
}

float measureOne(uint8_t index) {
  digitalWrite(TRIG_PINS[index], LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PINS[index], HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PINS[index], LOW);
  unsigned long duration = pulseIn(ECHO_PINS[index], HIGH, 25000UL);
  if (duration == 0) return distanceCm[index];
  float cm = duration * 0.0343f / 2.0f;
  if (cm < 2.0f) cm = 2.0f;
  if (cm > 400.0f) cm = 400.0f;
  return cm;
}

void sampleSensors() {
  uint32_t now = millis();
  if (now - lastSensorMs < 45) return;
  lastSensorMs = now;
  for (uint8_t i = 0; i < 4; i++) {
    distanceCm[i] = measureOne(i);
  }
  uint32_t dtMs = now - previousDistanceMs;
  if (dtMs >= 20 && dtMs <= 1000) {
    float dt = dtMs / 1000.0f;
    for (uint8_t i = 0; i < 4; i++) {
      // Positive speed means the hand moved toward the sensor.
      float toward = (previousDistanceCm[i] - distanceCm[i]) / dt;
      speedCmS[i] = (toward > MIN_HAND_SPEED) ? toward : 0.0f;
      if (speedCmS[i] > 250.0f) speedCmS[i] = 250.0f;
    }
  }
  for (uint8_t i = 0; i < 4; i++) previousDistanceCm[i] = distanceCm[i];
  previousDistanceMs = now;
  if (now < keyboardOverrideUntil) {
    for (uint8_t i = 0; i < 4; i++) speedCmS[i] = keyboardSpeedCmS[i];
  }
}

// The GUI can emulate the four sensor speeds from the laptop keyboard.
// Message format: KEY,<sensor index 0..3>,<speed in cm/s>
void readKeyboardCommands() {
  while (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    if (command == "SERVE") {
      // Use the same active-player and rally guards as the physical buttons.
      if (servingPlayer == 1) serveP1Event = true;
      else serveP2Event = true;
      continue;
    }
    // Uno's default scanf does not support %f. Parse the speed explicitly.
    if (command.startsWith("KEY,") && command.length() > 6 && command.charAt(5) == ',' && command.charAt(4) >= '0' && command.charAt(4) <= '3') {
      uint8_t sensorIndex = command.charAt(4) - '0';
      float speed = command.substring(6).toFloat();
      keyboardSpeedCmS[sensorIndex] = constrain(speed, 0.0f, 250.0f);
      keyboardOverrideUntil = millis() + 300;
      for (uint8_t i = 0; i < 4; i++) speedCmS[i] = keyboardSpeedCmS[i];
    }
  }
}

void sendShot(uint8_t player, float power, float direction, const char* result, float flightTime) {
  Serial.print("SHOT,");
  Serial.print(player);
  Serial.print(',');
  Serial.print(power, 1);
  Serial.print(',');
  Serial.print(direction, 1);
  Serial.print(',');
  Serial.print(result);
  Serial.print(',');
  Serial.println(flightTime, 2);
}

void evaluateShot(uint8_t player) {
  uint32_t now = millis();
  if (!rallyStarted || gameOver || now - lastShotMs < SHOT_COOLDOWN_MS) return;
  bool inZone = (player == 1) ? (ballX <= 15.0f) : (ballX >= 85.0f);
  if (!inZone) return;

  uint8_t left = (player == 1) ? 0 : 2;
  uint8_t right = left + 1;
  float vL = speedCmS[left];
  float vR = speedCmS[right];
  float power = (vL + vR) / 2.0f;
  float direction = vR - vL;

  // Reaching the hitting zone does not count as a shot by itself. Wait until
  // at least one of this player's sensors detects a real hand movement.
  if (power < MIN_HAND_SPEED) return;

  const char* result = "IN";
  float flightTime = 60.0f / max(power, 1.0f);

  if (power < 20.0f) result = "NET";
  else if (power > 120.0f) result = "LONG";
  else if (fabs(direction) > 60.0f) result = "WIDE";
  else if (power < MIN_HAND_SPEED) result = "MISS";

  // The shot must travel toward the other end: negative direction = right,
  // positive direction = left, matching vR - vL.
  if (strcmp(result, "IN") == 0) {
    bool towardOpponent = (player == 1) ? (direction < 0.0f) : (direction > 0.0f);
    if (!towardOpponent) result = "WIDE";
  }

  sendShot(player, power, direction, result, flightTime);
  logGameEvent("SHOT", player, result, flightTime);
  lastShotMs = now;
  beep(1200, 65);

  if (strcmp(result, "IN") != 0) {
    registerPoint(player == 1 ? 2 : 1, result);
    return;
  }

  ballV = (player == 1) ? (100.0f / max(flightTime, 0.4f)) : -(100.0f / max(flightTime, 0.4f));
  message(F("IN"));
}

void updateBall() {
  if (!rallyStarted || gameOver || ballV == 0.0f) return;
  uint32_t now = millis();
  float dt = (now - lastBallMs) / 1000.0f;
  if (dt <= 0.0f || dt > 0.5f) {
    lastBallMs = now;
    return;
  }
  lastBallMs = now;
  ballX += ballV * dt;
  if (ballX <= 0.0f) {
    ballX = 0.0f;
    registerPoint(2, "MISS");
  } else if (ballX >= 100.0f) {
    ballX = 100.0f;
    registerPoint(1, "MISS");
  }
}

void handleServeEvents() {
  bool p1 = false;
  bool p2 = false;
  noInterrupts();
  p1 = serveP1Event;
  p2 = serveP2Event;
  serveP1Event = false;
  serveP2Event = false;
  interrupts();
  if (gameOver || rallyStarted) return;
  if (p1 && servingPlayer == 1) resetRallyForServe(1);
  else if (p2 && servingPlayer == 2) resetRallyForServe(2);
}

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(20);
  for (uint8_t i = 0; i < 4; i++) {
    pinMode(TRIG_PINS[i], OUTPUT);
    pinMode(ECHO_PINS[i], INPUT);
    digitalWrite(TRIG_PINS[i], LOW);
  }
  pinMode(SERVE_P1_PIN, INPUT_PULLUP);
  pinMode(SERVE_P2_PIN, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);
  attachInterrupt(digitalPinToInterrupt(SERVE_P1_PIN), onServeP1, FALLING);
  attachInterrupt(digitalPinToInterrupt(SERVE_P2_PIN), onServeP2, FALLING);
  previousDistanceMs = millis();
  lastBallMs = millis();
  Serial.println(F("READY,115200"));
  sendScore();
  sendBall();
  message(F("PRESS THE SERVING PLAYER BUTTON"));
}

void loop() {
  readKeyboardCommands();
  handleServeEvents();
  sampleSensors();
  detectSwings();
  evaluateShot(1);
  evaluateShot(2);
  updateBall();
  if (millis() - lastTelemetryMs >= 45) {
    lastTelemetryMs = millis();
    sendBall();
  }
}
