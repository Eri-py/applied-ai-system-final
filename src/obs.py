"""Run logging: one JSONL file per run, plus an optional live trace on stderr.

Every decision the system makes is recorded as one JSON object on one line: the guardrail
verdict, what retrieval returned, which backend parsed the request, every tool call with its
arguments, every critic verdict, every repair, and the final confidence. The format is JSONL
rather than prose because the evaluation harness reads these files back and asserts on them --
a log you can only read with your eyes is not evidence.

Design notes:

- The logger never raises. An observability layer that can break the run it observes is worse
  than no observability layer, so disk errors degrade to "logging off" with one warning.
- Timing is recorded per event (`t_ms`, milliseconds since the run started) so a slow step is
  visible without a profiler.
- `trace=True` mirrors events to stderr for `--verbose`, keeping stdout clean for the actual
  playlist so the CLI stays pipeable.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


def new_run_id() -> str:
    """A short, sortable run id: timestamp plus four random characters."""
    return f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:4]}"


@dataclass
class RunLogger:
    """Collects the events of a single run and writes them as JSONL.

    Events are kept in memory as well as written, because the CLI prints a summary from them
    and the evaluation harness inspects them without re-reading the file.
    """

    run_id: str = field(default_factory=new_run_id)
    log_dir: Optional[Path] = None
    trace: bool = False
    enabled: bool = True
    events: List[Dict[str, Any]] = field(default_factory=list)
    _handle: Any = field(default=None, repr=False)
    _start: float = field(default_factory=time.perf_counter, repr=False)
    _warned: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        if not self.enabled:
            return
        directory = Path(self.log_dir) if self.log_dir else DEFAULT_LOG_DIR
        try:
            directory.mkdir(parents=True, exist_ok=True)
            self.path = directory / f"run-{self.run_id}.jsonl"
            self._handle = self.path.open("w", encoding="utf-8")
        except OSError as error:
            # A read-only or full disk must not take the playlist down with it.
            self.enabled = False
            self.path = None
            print(f"[warn] run logging disabled: {error}", file=sys.stderr)

    @property
    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)

    def event(self, kind: str, **payload: Any) -> Dict[str, Any]:
        """Records one event. Returns it, so callers can log and return in one expression."""
        record = {
            "run_id": self.run_id,
            "seq": len(self.events),
            "t_ms": self.elapsed_ms,
            "kind": kind,
            **payload,
        }
        self.events.append(record)

        if self.trace:
            detail = {k: v for k, v in payload.items() if k not in ("prose", "notes_text")}
            print(f"  [{record['t_ms']:>5}ms] {kind}: {_compact(detail)}", file=sys.stderr)

        if self.enabled and self._handle is not None:
            try:
                self._handle.write(json.dumps(record, default=str) + "\n")
                self._handle.flush()
            except (OSError, ValueError) as error:
                if not self._warned:
                    print(f"[warn] run logging stopped: {error}", file=sys.stderr)
                    self._warned = True
        return record

    def error(self, where: str, exc: BaseException) -> Dict[str, Any]:
        """Records a caught exception with its type, for the reliability summary."""
        return self.event(
            "error",
            where=where,
            error_type=type(exc).__name__,
            error=str(exc)[:400],
        )

    def by_kind(self, kind: str) -> List[Dict[str, Any]]:
        """All recorded events of one kind, for assertions and summaries."""
        return [event for event in self.events if event["kind"] == kind]

    def close(self) -> Optional[Path]:
        """Closes the file and returns its path, or None if logging was off."""
        if self._handle is not None:
            try:
                self._handle.close()
            except OSError:
                pass
            self._handle = None
        return getattr(self, "path", None)

    def __enter__(self) -> "RunLogger":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


def _compact(payload: Dict[str, Any], limit: int = 160) -> str:
    """One-line rendering of an event payload for the live trace."""
    try:
        text = json.dumps(payload, default=str, sort_keys=True)
    except (TypeError, ValueError):
        text = str(payload)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def logging_enabled() -> bool:
    """Run logging is on unless `VIBEFINDER_NO_LOG` is set, so tests can switch it off."""
    return os.environ.get("VIBEFINDER_NO_LOG", "").strip() not in ("1", "true", "yes")
