import json
import tempfile
from pathlib import Path
from unittest import TestCase

from .event_log import EventLog, parse_event
from .serial_bridge import SerialBridge


def snapshot(kind="SWING", result="OUT_OF_ZONE", score="0,0"):
    return f"EVENT,{kind},1234,1,{result},50.00,{score},1,0,GUI,80,90,100,110,60,0,0,0,30,-60,2.00"


class SwingLoggingTests(TestCase):
    def test_full_sensor_snapshot_and_units(self):
        event = parse_event(snapshot())
        self.assertEqual(event["sensors"]["p1"]["left"],
                         {"physical_distance_cm": 80, "effective_speed_cm_s": 60})
        self.assertEqual(event["sensors"]["p2"]["right"]["physical_distance_cm"], 110)
        self.assertEqual(event["power_cm_s"], 30)
        self.assertEqual(event["direction_cm_s"], -60)
        self.assertEqual(event["state"], "OUT_OF_ZONE")
        self.assertIsNone(event["flight_time_s"])

    def test_rejects_incomplete_and_nonfinite_records(self):
        for line in ("EVENT,SHOT", snapshot().replace(",80,", ",nan,"),
                     snapshot().replace(",1,OUT_OF_ZONE", ",9,OUT_OF_ZONE")):
            with self.subTest(line=line), self.assertRaises(ValueError):
                parse_event(line)

    def test_bridge_persists_attempt_shot_and_final_score(self):
        with tempfile.TemporaryDirectory() as directory:
            bridge = SerialBridge()
            bridge.event_log = EventLog(directory)
            try:
                bridge._handle_line(snapshot())
                bridge._handle_line("SHOT,1,30,-60,IN,2.00")
                bridge._handle_line(snapshot("SHOT", "IN"))
                bridge._handle_line("SCORE,0,1,SERVE,1")
                bridge._handle_line(snapshot("POINT", "MISS", "0,1"))
                records = [json.loads(line) for line in (Path(directory) / "swings.jsonl").read_text().splitlines()]
                self.assertEqual([r["event"] for r in records], ["SWING", "SHOT", "POINT"])
                self.assertEqual(records[-1]["score"], {"p1": 0, "p2": 1})
                self.assertEqual(records[1]["flight_time_s"], 2)
                self.assertEqual([r["sequence"] for r in records], [1, 2, 3])
                self.assertTrue(records[0]["timestamp_utc"].endswith("+00:00"))
                self.assertEqual(bridge.snapshot()["racket_event"], 1)
                text = (Path(directory) / "swings.log").read_text(encoding="utf-8")
                for expected in ("P1 sensors", "P2 sensors", "OUT_OF_ZONE", "Score: P1 0 : 1 P2", "Direction (R-L): -60.00"):
                    self.assertIn(expected, text)
                # New processes append, rather than overwriting previous games.
                bridge.event_log.close()
                bridge.event_log = EventLog(directory)
                bridge._handle_line(snapshot("SERVE", "RALLY_STARTED"))
                self.assertEqual(len((Path(directory) / "swings.jsonl").read_text().splitlines()), 4)
            finally:
                bridge.event_log.close()

    def test_bad_event_does_not_prevent_next_valid_event(self):
        with tempfile.TemporaryDirectory() as directory:
            bridge = SerialBridge()
            bridge.event_log = EventLog(directory)
            try:
                with self.assertLogs("game.serial_bridge", level="WARNING"):
                    bridge._handle_line("EVENT,SHOT,broken")
                bridge._handle_line(snapshot())
                self.assertEqual(bridge.event_log.sequence, 1)
            finally:
                bridge.event_log.close()
