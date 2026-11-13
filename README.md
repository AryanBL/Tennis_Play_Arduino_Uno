# Arduino Uno Table Tennis

This project implements the two-player ultrasonic table-tennis assignment for Arduino Uno and Wokwi. It includes the board firmware, a wide breadboard layout, and a Django web GUI served on port 5000.

## Files

- `diagram.json`: Wokwi circuit with an Arduino Uno, two wide breadboards, four HC-SR04 sensors, two serve buttons, and a buzzer.
- `src/main.ino`: game logic, interrupt-driven serve buttons, ultrasonic pulse measurements, scoring, sounds, and serial protocol.
- `web/`: Django project and web GUI. It draws the table, net, animated racket bars, ball animation, power bars, messages, score, and next server.
- `platformio.ini`: PlatformIO configuration for an Arduino Uno.
- `wokwi.toml`: Wokwi VS Code configuration. The simulated serial bridge is TCP port 4000.

## Run in Wokwi for VS Code

1. Install VS Code, PlatformIO, and the Wokwi for VS Code extension.
2. Open this folder in VS Code.
3. Build the project with PlatformIO. The resulting HEX file is placed in `.pio/build/uno/firmware.hex`.
4. Start the Wokwi simulation. Keep the Wokwi tab visible while playing.
5. In a second terminal, install the web GUI dependencies and run the Django server:

   ```bash
   python -m pip install -r requirements.txt
   python web/manage.py runserver 5000
   ```

6. Open [http://localhost:5000](http://localhost:5000) in your browser.
7. When the page connects to Wokwi, drag each HC-SR04 distance slider quickly to simulate a hand swing. The sensor order is P1-left, P1-right, P2-left, P2-right.
8. Hold `A` for P1's left sensor, `D` for P1's right sensor, `Left Arrow` for P2's left sensor, or `Right Arrow` for P2's right sensor. The webpage sends virtual sensor speeds to the Arduino over the serial connection.
9. Press the active player's serve button in the Wokwi diagram. The button inputs use `INPUT_PULLUP`, so each button connects its Arduino pin to GND.

The Django bridge connects to the Wokwi RFC2217 port at `rfc2217://localhost:4000`. Set the `WOKWI_SERIAL_URL` environment variable if you use another serial URL.

## Serial messages

The firmware sends newline-delimited messages:

- `BALL,x` - ball position from 0 to 100 table percent.
- `SHOT,player,P,D,result,T` - player, power, direction, result (`IN`, `NET`, `LONG`, `WIDE`, or `MISS`), and travel time.
- `SCORE,p1,p2,SERVE,next_player` - current score and next server.
- `MSG,text` - display message.
- `WINNER,player` - final winner.

## Hardware mapping

| Item | Arduino Uno pin |
|---|---|
| P1 left HC-SR04 TRIG/ECHO | D4 / D5 |
| P1 right HC-SR04 TRIG/ECHO | D6 / D7 |
| P2 left HC-SR04 TRIG/ECHO | D8 / D9 |
| P2 right HC-SR04 TRIG/ECHO | D10 / D11 |
| P1 serve button | D2 to GND, interrupt FALLING |
| P2 serve button | D3 to GND, interrupt FALLING |
| Buzzer | D12 to buzzer positive, buzzer negative to GND |
| All sensor VCC | 5V |
| All sensor GND | GND |

The breadboard rails are linked to the Arduino 5V and GND pins. Every sensor has its own separated row area and its wires are routed in parallel lanes, so components and wires do not need to overlap.

The dashed rectangles at both ends are the 15% hitting zones. They only decide whether a sensor swing is allowed to hit the ball. The racket bar moves after an actual sensor swing produces a `SHOT` message, or while a keyboard sensor key is held.

## Keyboard sensor mapping

| Key | Virtual sensor | Arduino sensor index |
|---|---|---|
| `A` | P1 left | 0 |
| `D` | P1 right | 1 |
| `Left Arrow` | P2 left | 2 |
| `Right Arrow` | P2 right | 3 |

The webpage sends messages such as `KEY,0,85` while a key is held and `KEY,0,0` when it is released. The Arduino uses these values in the same power and direction calculation as the physical HC-SR04 readings.
