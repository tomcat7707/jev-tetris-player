import json
import os
import statistics
import threading
import time
from datetime import datetime, timezone


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def compact_board(board):
    """20x10 board를 사람이/AI가 읽기 쉬운 문자열 배열로 축약한다."""
    return ["".join(cell if cell is not None else "." for cell in row) for row in board]


def compact_candidate(move):
    if not move:
        return None
    keys = (
        "id",
        "rot",
        "rot_label",
        "col",
        "drop_y",
        "landing_height",
        "contact_edges",
        "overhangs",
        "delta_holes",
        "total_holes_after",
        "col_transitions",
        "cumulative_wells",
        "lines_cleared",
        "max_height",
    )
    return {key: move.get(key) for key in keys}


class ExperimentLogger:
    """
    한 실행 세션을 JSONL 이벤트 로그 + summary JSON으로 기록한다.

    JSONL은 사람이 직접 읽을 수 있고, ChatGPT/Agent가 나중에
    piece 단위로 원인을 재구성하기에도 적합하다.
    """

    def __init__(self, log_dir="logs", session_config=None):
        os.makedirs(log_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_id = f"jev_tetris_{stamp}_{os.getpid()}"
        self.log_path = os.path.join(log_dir, f"{self.session_id}.jsonl")
        self.summary_path = os.path.join(log_dir, f"{self.session_id}_summary.json")

        self._lock = threading.Lock()
        self._start = time.perf_counter()
        self._closed = False

        self.counters = {
            "pieces_spawned": 0,
            "jev_requests": 0,
            "jev_responses": 0,
            "jev_applied": 0,
            "jev_late": 0,
            "jev_errors": 0,
            "deadline_fallbacks": 0,
            "landings": 0,
            "target_misses": 0,
            "line_clear_events": 0,
            "lines_cleared": 0,
            "game_overs": 0,
            "resets": 0,
        }
        self.latencies_ms = []

        self.event(
            "session_start",
            session_id=self.session_id,
            config=session_config or {},
        )

    def event(self, event_type, **data):
        if self._closed:
            return

        record = {
            "ts_utc": _utc_now_iso(),
            "elapsed_ms": int((time.perf_counter() - self._start) * 1000),
            "event": event_type,
            **data,
        }

        with self._lock:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                f.write("\n")

    def count(self, key, amount=1):
        if key in self.counters:
            self.counters[key] += amount

    def add_latency(self, latency_ms):
        if latency_ms is None:
            return
        try:
            value = int(latency_ms)
        except (TypeError, ValueError):
            return
        if value >= 0:
            self.latencies_ms.append(value)

    def summary(self, final_state=None):
        lat = sorted(self.latencies_ms)

        def percentile(p):
            if not lat:
                return None
            if len(lat) == 1:
                return lat[0]
            index = (len(lat) - 1) * p
            lo = int(index)
            hi = min(lo + 1, len(lat) - 1)
            frac = index - lo
            return round(lat[lo] * (1 - frac) + lat[hi] * frac, 1)

        latency_stats = {
            "samples": len(lat),
            "min_ms": min(lat) if lat else None,
            "mean_ms": round(statistics.mean(lat), 1) if lat else None,
            "median_ms": round(statistics.median(lat), 1) if lat else None,
            "p90_ms": percentile(0.90),
            "p95_ms": percentile(0.95),
            "max_ms": max(lat) if lat else None,
        }

        result = {
            "session_id": self.session_id,
            "created_utc": _utc_now_iso(),
            "duration_ms": int((time.perf_counter() - self._start) * 1000),
            "counters": dict(self.counters),
            "jev_latency": latency_stats,
            "final_state": final_state or {},
            "jsonl_log": self.log_path,
        }
        return result

    def close(self, final_state=None):
        if self._closed:
            return

        summary = self.summary(final_state)
        self.event("session_end", summary=summary)

        with self._lock:
            with open(self.summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)

        self._closed = True
