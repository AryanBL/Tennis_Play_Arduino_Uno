"""Persistent board-event records: readable text and machine-readable JSONL."""
import json
import logging
import math
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_DIR = Path(__file__).resolve().parents[2] / "logs"


def parse_event(line):
    fields = line.split(",")
    if len(fields) != 22 or fields[0] != "EVENT":
        raise ValueError("Invalid event snapshot")
    kind, result, source = fields[1], fields[4], fields[10]
    player = int(fields[3])
    if kind not in {"SWING", "SHOT", "SERVE", "POINT"} or player not in range(3):
        raise ValueError("Invalid event type or player")
    values = [float(fields[i]) for i in [5, *range(11, 22)]]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Non-finite event measurement")
    distances = [float(value) for value in fields[11:15]]
    speeds = [float(value) for value in fields[15:19]]
    score = [int(fields[6]), int(fields[7])]
    return {
        "event": kind, "board_ms": int(fields[2]), "player": player or None,
        "state": result, "input_source": source,
        "ball_percent": float(fields[5]), "score": {"p1": score[0], "p2": score[1]},
        "server": int(fields[8]), "winner": int(fields[9]) or None,
        "sensors": {
            f"p{p + 1}": {
                side: {"physical_distance_cm": distances[p * 2 + i],
                       "effective_speed_cm_s": speeds[p * 2 + i]}
                for i, side in enumerate(("left", "right"))
            } for p in range(2)
        },
        "power_cm_s": float(fields[19]) if player else None,
        "direction_cm_s": float(fields[20]) if player else None,
        "flight_time_s": float(fields[21]) if kind == "SHOT" else None,
    }


class EventLog:
    def __init__(self, directory=LOG_DIR):
        self.directory = Path(directory)
        self.session = uuid.uuid4().hex[:12]
        self.sequence = 0
        self.writers = None

    def _open(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        self.writers = []
        for name in ("swings.log", "swings.jsonl"):
            logger = logging.Logger(f"tennis.{self.session}.{name}")
            handler = RotatingFileHandler(self.directory / name, maxBytes=5_000_000,
                                          backupCount=5, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)
            self.writers.append(logger)

    def write(self, event):
        if self.writers is None:
            self._open()
        self.sequence += 1
        record = {"timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                  "session": self.session, "sequence": self.sequence, **event}
        player = f"P{record['player']}" if record["player"] else "-"
        lines = ["=" * 76,
                 f"{record['timestamp_utc']} | {record['event']} #{self.sequence} | Player: {player}",
                 f"Session: {self.session} | Board: {record['board_ms']} ms | Source: {record['input_source']}",
                 f"State: {record['state']} | Ball: {record['ball_percent']:.2f}%",
                 f"Score: P1 {record['score']['p1']} : {record['score']['p2']} P2 | Server: P{record['server']} | Winner: {record['winner'] or '-'}"]
        for p, sensors in record["sensors"].items():
            lines.append(f"{p.upper()} sensors (physical cm / effective cm/s): " + " | ".join(
                f"{side}: {sample['physical_distance_cm']:.2f} / {sample['effective_speed_cm_s']:.2f}"
                for side, sample in sensors.items()))
        if record["power_cm_s"] is not None:
            direction = record["direction_cm_s"]
            aim = "right" if direction < 0 else "left" if direction > 0 else "neutral"
            lines.append(f"Power: {record['power_cm_s']:.2f} cm/s | Direction (R-L): {direction:+.2f} cm/s ({aim})")
        if record["flight_time_s"] is not None:
            lines.append(f"Calculated flight time: {record['flight_time_s']:.2f} s")
        self.writers[0].info("\n".join(lines))
        self.writers[1].info(json.dumps(record, allow_nan=False))

    def close(self):
        for writer in self.writers or []:
            for handler in writer.handlers:
                handler.close()
        self.writers = None
