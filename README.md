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
8. Press and release `A` for P1's left sensor, `D` for P1's right sensor, `Left Arrow` for P2's left sensor, or `Right Arrow` for P2's right sensor. A quick tap simulates fast hand movement; holding longer simulates slower movement. The swing is sent on release.
9. Click **Serve** in the webpage or press **Space** to serve for the active player. The physical serve buttons in Wokwi also work. Serving during a rally or after game over is ignored. The button inputs use `INPUT_PULLUP`, so each button connects its Arduino pin to GND.

The webpage also has four virtual ultrasonic distance sliders in the player sidebars, each ranging from 2 to 400 cm. Drag toward a smaller distance to simulate an approaching hand; faster changes produce more power (speed is distance change divided by elapsed time, capped at 250 cm/s). Moving toward a larger distance prepares the next swing without generating power. A stationary slider stops generating movement after 150 ms. These controls emulate sensor movement through the serial bridge; they do not change the Wokwi component sliders themselves.

After updating the firmware, rebuild with PlatformIO and restart Wokwi so it loads the new HEX file. The web Serve button and Space send `SERVE` over serial, using the same serving-player and rally checks as the board buttons.

The Django bridge connects to the Wokwi RFC2217 port at `rfc2217://localhost:4000`. Set the `WOKWI_SERIAL_URL` environment variable if you use another serial URL.

## Swing and game logs

While the Django server is connected to the updated firmware, complete event snapshots are appended to:

- `logs/swings.log`: readable blocks with timestamps, player, state, score, server, ball position, sensor values, power, direction, and calculated flight time for shots.
- `logs/swings.jsonl`: the same records as one JSON object per line for analysis.

The folder and files are created automatically on the first event. Each file rotates at 5 MB and retains five backups. Timestamps are UTC with an explicit offset; each server bridge session has an identifier and numbered records. Files are appended across server restarts.

Event types:

| Event | Meaning |
|---|---|
| `SWING` | A player's combined sensor power crosses from below 5 cm/s to at least 5 cm/s. One continuous hold/movement is one swing; return below the threshold to start another. Attempts are logged even outside the hitting zone. State is `READY`, `OUT_OF_ZONE`, `COOLDOWN`, `WAITING_SERVE`, or `GAME_OVER`. |
| `SHOT` | The Arduino accepts a hit attempt in the hitting zone; state is `IN`, `NET`, `LONG`, `WIDE`, or `MISS`. A sustained swing can generate a later shot, so these are distinct event types. |
| `POINT` | A point has been awarded. This snapshot contains the updated score and any match winner. |
| `SERVE` | A serve was accepted and the rally started. |

Every record includes both players' left/right **physical sensor distances in cm** and **effective speeds in cm/s** at the board. GUI input overrides speeds, so physical distances do not represent the GUI sliders or a keyboard hold. `input_source` distinguishes `GUI` overrides from `ULTRASONIC` readings. Power is the player's mean effective speed; direction is right speed minus left speed (negative aims right, positive aims left). `SHOT` contains the score at the instant of the hit; a following `POINT` contains the resulting score. Calculated flight time is not an observed travel duration.

Rebuild/restart Wokwi after this firmware update and restart Django to enable logging. Events are saved while the serial bridge is connected; the Uno does not retain events that occurred while disconnected.

## Serial event protocol

Detailed log records use this CSV format alongside the existing GUI messages:

```text
EVENT,type,board_ms,player,state,ball,p1_score,p2_score,server,winner,source,d0,d1,d2,d3,v0,v1,v2,v3,power,direction,flight_time
```

Sensor order is P1-left, P1-right, P2-left, P2-right. Player 0 denotes a match-level point record. Winner 0 means no match winner.

## GUI serial messages

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

The dashed rectangles at both ends are the 15% hitting zones. They only decide whether a sensor swing is allowed to hit the ball. The racket bar moves after an actual sensor swing produces a `SHOT` message, or when a keyboard key is released to swing.

## Keyboard sensor mapping

| Key | Virtual sensor | Arduino sensor index |
|---|---|---|
| `A` | P1 left | 0 |
| `D` | P1 right | 1 |
| `Left Arrow` | P2 left | 2 |
| `Right Arrow` | P2 right | 3 |

Each key represents a fixed 6 cm virtual hand movement. The page measures the duration from keydown to keyup, then computes `speed = min(250, 6 / duration_seconds)` with a 20 ms minimum duration for numerical stability. A quick press-and-release produces a fast swing; a long hold produces a slow swing. Each key has its own timer; auto-repeat does not reset it. No keyboard movement is sent while holding, because the completed movement duration is only known on release.

On release, the page sends a 200 ms movement pulse, refreshing it every 80 ms before resetting it to zero. The pulse is a delivery window for the completed swing, not extra movement time in the velocity calculation. Power bars display the pulse and then the last actual shot. Losing focus cancels unfinished presses and active pulses without firing a swing. Slider controls still work independently.

| Press duration | Sensor speed | Power with the other sensor idle |
|---|---|---|
| 100 ms | 60 cm/s | 30 cm/s |
| 150 ms | 40 cm/s | 20 cm/s |
| 300 ms | 20 cm/s | 10 cm/s |
| 600 ms | 10 cm/s | 5 cm/s |

The Arduino computes physical sensor speed from `(previous_distance - current_distance) / elapsed_seconds`, keeping only approaching speeds above 5 cm/s and capping them at 250 cm/s. It uses effective speeds from either physical sensors or GUI input to compute player power as `(left_speed + right_speed) / 2` and direction as `right_speed - left_speed`. For an IN shot, try a **100–150 ms tap of A for P1 or Right Arrow for P2**, releasing while the ball is in the hitting zone. Faster taps can be WIDE because their direction magnitude exceeds 60 cm/s; longer holds can be NET or too slow to register. Pressing both keys equally gives neutral direction, which is not an IN shot. Existing firmware thresholds, scoring, and event logging apply to the released swing.
