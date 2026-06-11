"""Live Wire event bus: in-memory ring buffer of real-time call events.

Fed by the step11 agent's debug-event webhook and its tool handlers; drained
by the public /api/live-events SSE for the workshop Live Wire panel.
Thread-safe, version-counted (same convention as call_store/function_health).
"""
import json
import threading
import time


def _summarize(event_type, data):
    if isinstance(data, dict):
        bits = []
        for k in ("content", "text", "step", "function", "name", "city",
                  "latency", "result", "error"):
            v = data.get(k)
            if isinstance(v, (str, int, float)) and str(v).strip():
                bits.append(f"{k}={str(v)[:60]}")
            if len(bits) >= 3:
                break
        if bits:
            return f"{event_type} · " + " · ".join(bits)
    return str(event_type)


class LiveEventBus:
    def __init__(self, cap=500):
        self._cap = cap
        self._events = []
        self._lock = threading.Lock()
        self._seq = 0

    @property
    def version(self):
        return self._seq

    def emit(self, source, event_type, data):
        try:
            json.dumps(data)
        except (TypeError, ValueError):
            data = None
        with self._lock:
            self._seq += 1
            self._events.append({
                "seq": self._seq, "ts": time.time(), "source": source,
                "type": str(event_type), "summary": _summarize(event_type, data),
                "data": data,
            })
            if len(self._events) > self._cap:
                self._events = self._events[-self._cap:]

    def since(self, seq):
        with self._lock:
            return [e for e in self._events if e["seq"] > seq]


BUS = LiveEventBus()
