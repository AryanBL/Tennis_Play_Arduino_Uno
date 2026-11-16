import copy
import logging
import os
import threading
import time

import serial

from .event_log import EventLog, parse_event


class SerialBridge:
    """Small background bridge between Django and the Wokwi RFC2217 port."""

    def __init__(self):
        self.url = os.environ.get("WOKWI_SERIAL_URL", "rfc2217://localhost:4000")
        self.connection = None
        self.thread = None
        self.stop_event = threading.Event()
        self.lock = threading.RLock()
        self.write_lock = threading.Lock()
        self.event_log = EventLog()
        self.state = {
            "connected": False,
            "status": "Waiting for the Wokwi serial bridge",
            "ball": 50.0,
            "score": [0, 0],
            "server": 1,
            "message": "Start Wokwi, then press Connect",
            "winner": None,
            "power": [0.0, 0.0],
            "racket_event": 0,
            "racket_player": 0,
            "racket_offset": 0,
        }

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():
                return
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._run, name="wokwi-serial", daemon=True)
            self.thread.start()

    def _run(self):
        while not self.stop_event.is_set():
            if self.connection is None:
                try:
                    connection = serial.serial_for_url(self.url, baudrate=115200, timeout=0.1)
                    with self.lock:
                        self.connection = connection
                        self.state["connected"] = True
                        self.state["status"] = f"Connected to {self.url}"
                        self.state["message"] = "Connected"
                except Exception as exc:
                    with self.lock:
                        self.state["connected"] = False
                        self.state["status"] = f"Waiting for Wokwi: {exc}"
                    time.sleep(2.0)
                    continue

            try:
                raw = self.connection.readline()
                if raw:
                    self._handle_line(raw.decode("utf-8", errors="replace").strip())
            except Exception as exc:
                with self.lock:
                    self.state["connected"] = False
                    self.state["status"] = f"Serial disconnected: {exc}"
                    connection = self.connection
                    self.connection = None
                try:
                    connection.close()
                except Exception:
                    pass
                time.sleep(1.0)

    def _handle_line(self, line):
        fields = line.split(",")
        if not fields:
            return
        with self.lock:
            if fields[0] == "EVENT":
                try:
                    event = parse_event(line)
                except (ValueError, IndexError):
                    logging.getLogger(__name__).warning("Ignored malformed board event: %s", line)
                    return
                try:
                    self.event_log.write(event)
                except OSError:
                    logging.getLogger(__name__).exception("Could not write game event log")
            elif fields[0] == "BALL" and len(fields) >= 2:
                try:
                    self.state["ball"] = max(0.0, min(100.0, float(fields[1])))
                except ValueError:
                    pass
            elif fields[0] == "SCORE" and len(fields) >= 5:
                try:
                    self.state["score"] = [int(fields[1]), int(fields[2])]
                    self.state["server"] = int(fields[4])
                except ValueError:
                    pass
            elif fields[0] == "SHOT" and len(fields) >= 5:
                try:
                    player = int(fields[1]) - 1
                    direction = float(fields[3])
                    self.state["power"][player] = max(0.0, min(130.0, float(fields[2])))
                    self.state["racket_event"] += 1
                    self.state["racket_player"] = player
                    self.state["racket_offset"] = -34 if direction > 0 else 34
                except (ValueError, IndexError):
                    pass
            elif fields[0] == "MSG" and len(fields) >= 2:
                self.state["message"] = ",".join(fields[1:])
            elif fields[0] == "WINNER" and len(fields) >= 2:
                self.state["winner"] = fields[1]
                self.state["message"] = f"PLAYER {fields[1]} WINS!"

    def send_keyboard(self, sensor_index, speed):
        return self._send_command(f"KEY,{int(sensor_index)},{float(speed):.1f}")

    def send_serve(self):
        return self._send_command("SERVE")

    def _send_command(self, command):
        self.start()
        with self.write_lock:
            connection = self.connection
            if connection is None:
                return False
            try:
                connection.write(f"{command}\n".encode("ascii"))
                return True
            except Exception as exc:
                with self.lock:
                    self.state["connected"] = False
                    self.state["status"] = f"Serial write failed: {exc}"
                return False

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.state)


bridge = SerialBridge()
