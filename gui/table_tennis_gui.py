#!/usr/bin/env python3
"""Desktop GUI for the Arduino/Wokwi table-tennis game."""
import argparse
import queue
import threading
import time
import tkinter as tk

try:
    import serial
    import serial.threaded
except ImportError as exc:
    raise SystemExit("Install the dependency first: python -m pip install pyserial") from exc


class SerialReader(threading.Thread):
    def __init__(self, port, baud, output):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.output = output
        self.stop_event = threading.Event()
        self.connection = None
        self.write_lock = threading.Lock()

    def run(self):
        try:
            if self.port.startswith("rfc2217://"):
                self.connection = serial.serial_for_url(self.port, baudrate=self.baud, timeout=0.1)
            else:
                self.connection = serial.Serial(self.port, self.baud, timeout=0.1)
            self.output.put(("status", f"Connected to {self.port}"))
            while not self.stop_event.is_set():
                raw = self.connection.readline()
                if raw:
                    self.output.put(("line", raw.decode("utf-8", errors="replace").strip()))
        except Exception as exc:
            self.output.put(("status", f"Connection error: {exc}"))
        finally:
            if self.connection is not None:
                self.connection.close()

    def stop(self):
        self.stop_event.set()
        if self.connection is not None:
            self.connection.close()

    def send_line(self, line):
        if self.connection is None or not self.connection.is_open:
            return
        try:
            with self.write_lock:
                self.connection.write((line + "\n").encode("ascii"))
        except Exception:
            pass


class TableTennisGUI(tk.Tk):
    WIDTH = 1000
    HEIGHT = 650

    def __init__(self, port):
        super().__init__()
        self.title("Arduino Table Tennis")
        self.geometry("1080x760")
        self.configure(bg="#101b2d")
        self.events = queue.Queue()
        self.reader = None
        self.ball_x = 50.0
        self.ball_target = 50.0
        self.score = [0, 0]
        self.server = 1
        self.winner = None
        self.message = "Waiting for the Arduino..."
        self.last_shot = [0.0, 0.0]
        self.power = [0.0, 0.0]
        self.racket_offset = [0.0, 0.0]
        self.racket_target = [0.0, 0.0]
        self.racket_pulse_until = [0.0, 0.0]
        self.ball_in_hitting_zone = [False, False]
        self.keyboard_enabled = tk.BooleanVar(value=True)
        self.keys_down = set()
        self.sensor_keys = {"a": 0, "d": 1, "Left": 2, "Right": 3}
        self.port_var = tk.StringVar(value=port)
        self.status_var = tk.StringVar(value="Disconnected")
        self.message_var = tk.StringVar(value=self.message)
        self.score_var = tk.StringVar(value="0   :   0")
        self.server_var = tk.StringVar(value="Serve: P1")
        self._build_ui()
        self.bind("<KeyPress>", self._on_key_press)
        self.bind("<KeyRelease>", self._on_key_release)
        self.canvas.bind("<Button-1>", lambda _event: self.focus_set())
        self.focus_set()
        self.after(30, self._poll_events)
        self.after(30, self._animate)
        self.after(80, self._keyboard_keepalive)

    def _build_ui(self):
        top = tk.Frame(self, bg="#101b2d")
        top.pack(fill="x", padx=18, pady=(14, 8))
        tk.Label(top, text="ARDUINO TABLE TENNIS", fg="#80ed99", bg="#101b2d", font=("Segoe UI", 20, "bold")).pack(side="left")
        tk.Label(top, textvariable=self.status_var, fg="#b8c7dd", bg="#101b2d", font=("Segoe UI", 10)).pack(side="right")

        controls = tk.Frame(self, bg="#16243b")
        controls.pack(fill="x", padx=18, pady=6)
        tk.Label(controls, text="Serial port:", fg="white", bg="#16243b").pack(side="left", padx=(12, 5), pady=10)
        tk.Entry(controls, textvariable=self.port_var, width=28).pack(side="left", pady=10)
        tk.Button(controls, text="Connect", command=self.connect, bg="#80ed99", activebackground="#57cc99").pack(side="left", padx=10)
        tk.Checkbutton(controls, text="Keyboard sensor mode", variable=self.keyboard_enabled,
                       fg="white", bg="#16243b", selectcolor="#263b5a",
                       activebackground="#16243b", activeforeground="white").pack(side="left", padx=10)
        tk.Label(controls, text="A/D = P1 left/right   ←/→ = P2 left/right",
                 fg="#b8c7dd", bg="#16243b").pack(side="left", padx=10)

        self.canvas = tk.Canvas(self, width=self.WIDTH, height=self.HEIGHT, bg="#132238", highlightthickness=0)
        self.canvas.pack(padx=18, pady=8, fill="both", expand=True)

        info = tk.Frame(self, bg="#101b2d")
        info.pack(fill="x", padx=18, pady=(4, 12))
        tk.Label(info, textvariable=self.score_var, fg="white", bg="#101b2d", font=("Segoe UI", 24, "bold")).pack(side="left", padx=12)
        tk.Label(info, textvariable=self.server_var, fg="#ffd166", bg="#101b2d", font=("Segoe UI", 12, "bold")).pack(side="left", padx=18)
        tk.Label(info, textvariable=self.message_var, fg="#b8c7dd", bg="#101b2d", font=("Segoe UI", 12)).pack(side="right", padx=12)

    def connect(self):
        if self.reader:
            self.reader.stop()
        self.reader = SerialReader(self.port_var.get().strip(), 115200, self.events)
        self.reader.start()

    def _send_keyboard_sensor(self, sensor_index, speed):
        if self.reader:
            self.reader.send_line(f"KEY,{sensor_index},{speed:.1f}")

    def _on_key_press(self, event):
        if not self.keyboard_enabled.get() or event.keysym not in self.sensor_keys:
            return
        key = event.keysym
        sensor_index = self.sensor_keys[key]
        self.keys_down.add(key)
        self._send_keyboard_sensor(sensor_index, 85.0)
        player = 0 if sensor_index < 2 else 1
        self.racket_target[player] = -34.0 if sensor_index % 2 == 0 else 34.0

    def _on_key_release(self, event):
        if event.keysym not in self.sensor_keys:
            return
        key = event.keysym
        self.keys_down.discard(key)
        self._send_keyboard_sensor(self.sensor_keys[key], 0.0)
        player = 0 if self.sensor_keys[key] < 2 else 1
        player_keys = ("a", "d") if player == 0 else ("Left", "Right")
        if not any(k in self.keys_down for k in player_keys):
            self.racket_target[player] = 0.0

    def _pulse_racket(self, player, offset):
        """Animate a racket after an actual sensor or keyboard swing."""
        self.racket_target[player] = offset
        self.racket_pulse_until[player] = time.time() + 0.38

    def _update_hitting_zone_state(self, position):
        p1_zone = position <= 15.0
        p2_zone = position >= 85.0
        self.ball_in_hitting_zone = [p1_zone, p2_zone]

    def _keyboard_keepalive(self):
        if self.keyboard_enabled.get():
            for key in self.keys_down:
                self._send_keyboard_sensor(self.sensor_keys[key], 85.0)
        self.after(80, self._keyboard_keepalive)

    def _poll_events(self):
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                self.status_var.set(value)
            else:
                self._handle_line(value)
        self.after(30, self._poll_events)

    def _handle_line(self, line):
        fields = line.split(",")
        if not fields:
            return
        if fields[0] == "BALL" and len(fields) >= 2:
            try:
                self.ball_target = max(0.0, min(100.0, float(fields[1])))
                self._update_hitting_zone_state(self.ball_target)
            except ValueError:
                pass
        elif fields[0] == "SCORE" and len(fields) >= 5:
            try:
                self.score = [int(fields[1]), int(fields[2])]
                self.server = int(fields[4])
                self.score_var.set(f"{self.score[0]}   :   {self.score[1]}")
                self.server_var.set(f"Serve: P{self.server}")
            except ValueError:
                pass
        elif fields[0] == "SHOT" and len(fields) >= 5:
            try:
                player = int(fields[1]) - 1
                self.power[player] = max(0.0, min(130.0, float(fields[2])))
                self.last_shot[player] = time.time()
                direction = float(fields[3]) if len(fields) >= 4 else 0.0
                self._pulse_racket(player, -34.0 if direction > 0 else 34.0)
            except ValueError:
                pass
        elif fields[0] == "MSG" and len(fields) >= 2:
            self.message = ",".join(fields[1:])
            self.message_var.set(self.message)
        elif fields[0] == "WINNER" and len(fields) >= 2:
            self.winner = fields[1]
            self.message_var.set(f"PLAYER {self.winner} WINS!")

    def _animate(self):
        self.ball_x += (self.ball_target - self.ball_x) * 0.16
        for player in range(2):
            if time.time() >= self.racket_pulse_until[player] and not self._player_key_is_down(player):
                self.racket_target[player] = 0.0
            self.racket_offset[player] += (self.racket_target[player] - self.racket_offset[player]) * 0.25
        self._draw()
        self.after(30, self._animate)

    def _player_key_is_down(self, player):
        keys = ("a", "d") if player == 0 else ("Left", "Right")
        return any(key in self.keys_down for key in keys)

    def _draw(self):
        c = self.canvas
        c.delete("all")
        w = max(c.winfo_width(), self.WIDTH)
        h = max(c.winfo_height(), self.HEIGHT)
        left, right = 80, w - 80
        top, bottom = 130, h - 100
        c.create_text(w / 2, 28, text="TABLE TENNIS", fill="#80ed99", font=("Segoe UI", 24, "bold"))
        c.create_text(w / 2, 62, text="Use Wokwi sliders or keyboard: A/D for P1, Left/Right for P2", fill="#b8c7dd", font=("Segoe UI", 11))
        c.create_rectangle(left, top, right, bottom, fill="#198754", outline="#d8f3dc", width=4)
        mid = (left + right) / 2
        c.create_line(mid, top, mid, bottom, fill="#d8f3dc", width=3)
        c.create_line(left, top, right, top, fill="#d8f3dc", width=4)
        c.create_line(left, bottom, right, bottom, fill="#d8f3dc", width=4)
        c.create_line(mid, top - 14, mid, bottom + 14, fill="#f6bd60", width=5)
        c.create_text(left + 20, bottom + 26, text="P1", fill="#80ed99", font=("Segoe UI", 14, "bold"), anchor="w")
        c.create_text(right - 20, bottom + 26, text="P2", fill="#80ed99", font=("Segoe UI", 14, "bold"), anchor="e")

        # Hitting-zone guides.
        c.create_rectangle(left, top, left + (right - left) * .15, bottom, outline="#ffd166", dash=(5, 3), width=2)
        c.create_rectangle(right - (right - left) * .15, top, right, bottom, outline="#ffd166", dash=(5, 3), width=2)

        for player, x in enumerate((left + 22, right - 22)):
            d = self.last_shot[player]
            center_y = (top + bottom) / 2 + self.racket_offset[player]
            bar_color = "#f1faee" if time.time() - d >= 0.6 else "#fff3b0"
            c.create_line(x, center_y - 46, x, center_y + 46, fill=bar_color, width=9)
            c.create_text(x, center_y + 62, text="racket", fill="#d8f3dc", font=("Segoe UI", 9))

        bx = left + (right - left) * self.ball_x / 100.0
        by = (top + bottom) / 2
        c.create_oval(bx - 11, by - 11, bx + 11, by + 11, fill="#ffd166", outline="white", width=2)

        # Power bars.
        bar_y = h - 45
        for i, x in enumerate((left, right - 220)):
            label = f"P{i+1} power"
            c.create_text(x, bar_y - 8, text=label, fill="#d8f3dc", anchor="w", font=("Segoe UI", 10, "bold"))
            c.create_rectangle(x + 78, bar_y - 16, x + 220, bar_y, fill="#263b5a", outline="")
            fill_w = 142 * min(self.power[i] / 130.0, 1.0)
            c.create_rectangle(x + 78, bar_y - 16, x + 78 + fill_w, bar_y, fill="#ff6b6b" if i == 0 else "#4dabf7", outline="")
            c.create_text(x + 230, bar_y - 8, text=f"{self.power[i]:.0f} cm/s", fill="#b8c7dd", anchor="w", font=("Segoe UI", 9))

    def destroy(self):
        if self.reader:
            self.reader.stop()
        super().destroy()


def main():
    parser = argparse.ArgumentParser(description="Arduino/Wokwi table tennis GUI")
    parser.add_argument("--port", default="rfc2217://localhost:4000", help="serial device or RFC2217 URL")
    args = parser.parse_args()
    app = TableTennisGUI(args.port)
    app.mainloop()


if __name__ == "__main__":
    main()
