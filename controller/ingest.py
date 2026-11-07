"""C1 — event ingestion: backlog-safe, idempotent, restartable.

- Chunks are processed in order; the last processed chunk number is the
  checkpoint in the store's meta table, so a restart resumes exactly where
  the previous process stopped (and the simulator keeps the world waiting).
- Idempotent: leads and calls are keyed by lead_id / event_id with
  INSERT OR IGNORE — re-ingesting a chunk after a crash changes nothing.
- Two passes per chunk (leads first, then calls) so a call's cohort can be
  resolved from its lead row even when both arrive in the same chunk.
- The controller learns only what the HTTP API returns. Chunk payloads are
  the API's own event stream, fetched via GET /events/chunks/{n}.
"""
import json
from datetime import datetime


class Ingestor:
    def __init__(self, client, store, epoch, on_config_changed=None):
        self.c, self.s = client, store
        self.epoch = epoch  # datetime of sim minute 0
        self.on_config_changed = on_config_changed
        self.cohortsets = {}  # wid -> CohortSet (once built)

    def minute_of(self, ts: str) -> int:
        return int((datetime.fromisoformat(ts) - self.epoch).total_seconds() // 60)

    def _cohort_for(self, lead_id, features=None):
        row = self.s.db.execute(
            "SELECT cohort_id, workflow_id FROM leads WHERE lead_id=?", (lead_id,)).fetchone()
        if row:
            return row[0]
        return "default"

    def ingest_chunk(self, n: int, kind: str, leads_only: bool = False):
        """Returns the number of NEW rows inserted (leads + calls)."""
        text = self.c.chunk_text(n)
        events = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))
        inserted = 0
        # pass 1: leads (campaigns and other types need no storage)
        local_cohorts = {}
        for ev in events:
            if ev["type"] == "lead":
                cs = self.cohortsets.get(ev["workflow_id"])
                cohort = cs.assign(ev["features"]) if cs else "default"
                local_cohorts[ev["lead_id"]] = cohort
                inserted += self.s.add_lead(ev, cohort, kind == "history")
        self.s.commit()
        if leads_only:
            return inserted
        # pass 2: calls + world events
        for ev in events:
            t = ev["type"]
            if t == "call":
                cohort = local_cohorts.get(ev["lead_id"]) or self._cohort_for(ev["lead_id"])
                inserted += self.s.add_call(ev, cohort, self.minute_of(ev["ts"]))
            elif t == "config_changed" and self.on_config_changed:
                self.on_config_changed(ev, self.minute_of(ev["ts"]))
        self.s.commit()
        return inserted
