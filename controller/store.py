"""SQLite audit store (C12) and all controller state.

Why SQLite: one file, zero new stateful infrastructure to operate (see
stakeholders/03), transactional, and crash-safe in WAL mode. Every piece of
controller state that must survive a kill lives here — nothing important is
kept only in memory. The store answers the audit question directly:
"why did workflow X change at time T, who approved it, what happened next?"
-> see the decisions + proposals + config_versions tables.
"""
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS leads (
  lead_id TEXT PRIMARY KEY, person_id TEXT, workflow_id TEXT, campaign_id TEXT,
  lang TEXT, city_tier TEXT, age_band TEXT, value_band TEXT, cohort_id TEXT,
  from_history INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_leads_person ON leads(person_id);
CREATE INDEX IF NOT EXISTS idx_leads_wf ON leads(workflow_id);

-- One row per call event. event_id is the idempotency key (C1): re-ingesting
-- a chunk after a crash is a no-op thanks to INSERT OR IGNORE.
CREATE TABLE IF NOT EXISTS calls (
  event_id INTEGER PRIMARY KEY, sim_minute INTEGER, ts TEXT,
  workflow_id TEXT, campaign_id TEXT, lead_id TEXT, person_id TEXT,
  cohort_id TEXT, config_version INTEGER,
  welcome TEXT, voice TEXT, caller_id TEXT, prompt_version TEXT,
  connected INTEGER, engaged INTEGER, disposition TEXT,
  hallucination INTEGER, hour INTEGER
);
CREATE INDEX IF NOT EXISTS idx_calls_wf ON calls(workflow_id, sim_minute);
CREATE INDEX IF NOT EXISTS idx_calls_variant ON calls(workflow_id, cohort_id, voice);
CREATE INDEX IF NOT EXISTS idx_calls_caller ON calls(workflow_id, caller_id, sim_minute);

-- The audit trail (C12). One row per thing the controller noticed or did.
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, sim_minute INTEGER, ts TEXT,
  workflow_id TEXT, kind TEXT, summary TEXT, detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_dec_wf ON decisions(workflow_id, sim_minute);

-- Governance state (C9). proposal_id is OUR deterministic idempotency key:
-- the same decision rebuilt after a crash produces the same proposal_id, so
-- the simulator's duplicate_proposal_id 409 tells us it already went in.
CREATE TABLE IF NOT EXISTS proposals (
  proposal_id TEXT PRIMARY KEY, workflow_id TEXT, approval_id TEXT,
  base_version INTEGER, kind TEXT, status TEXT,
  proposed_config TEXT, change_summary TEXT, impact_score REAL,
  affected_leads INTEGER, created_minute INTEGER, decided_minute INTEGER,
  applied_minute INTEGER, reasons TEXT
);
CREATE INDEX IF NOT EXISTS idx_prop_wf ON proposals(workflow_id, status);

CREATE TABLE IF NOT EXISTS experiments (
  id INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT, cohort_id TEXT,
  dim TEXT, control TEXT, arms TEXT, status TEXT,
  started_minute INTEGER, decided_minute INTEGER, winner TEXT,
  pre_config TEXT, note TEXT
);
CREATE INDEX IF NOT EXISTS idx_exp_wf ON experiments(workflow_id, status);

-- Snapshot of every config version we observe (ours, supervisor's, baseline).
CREATE TABLE IF NOT EXISTS config_versions (
  workflow_id TEXT, version INTEGER, actor TEXT, sim_minute INTEGER,
  config TEXT, PRIMARY KEY (workflow_id, version)
);

CREATE TABLE IF NOT EXISTS incidents (
  id INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT, kind TEXT,
  detected_minute INTEGER, detail TEXT, status TEXT, resolved_minute INTEGER
);

-- Loop self-metrics (C14): one row per controller iteration.
CREATE TABLE IF NOT EXISTS metrics (
  sim_minute INTEGER, wall_ts TEXT, events_ingested INTEGER,
  ingest_lag_min REAL, credits_remaining REAL, decisions INTEGER
);
"""


class Store:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)
        self.db.commit()

    # -- meta ---------------------------------------------------------------
    def get_meta(self, key, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_meta(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, str(value)))
        self.db.commit()

    # -- audit ---------------------------------------------------------------
    def log_decision(self, minute, ts, wid, kind, summary, detail=None):
        self.db.execute(
            "INSERT INTO decisions (sim_minute, ts, workflow_id, kind, summary, detail)"
            " VALUES (?,?,?,?,?,?)",
            (minute, ts, wid, kind, summary, json.dumps(detail or {})))
        self.db.commit()

    # -- ingestion -----------------------------------------------------------
    def add_lead(self, ev, cohort_id, from_history):
        cur = self.db.execute(
            "INSERT OR IGNORE INTO leads VALUES (?,?,?,?,?,?,?,?,?,?)",
            (ev["lead_id"], ev.get("person_id"), ev["workflow_id"], ev["campaign_id"],
             ev["features"].get("lang"), ev["features"].get("city_tier"),
             ev["features"].get("age_band"), ev["features"].get("value_band"),
             cohort_id, 1 if from_history else 0))
        return cur.rowcount

    def add_call(self, ev, cohort_id, sim_minute):
        qa = ev.get("qa") or {}
        cur = self.db.execute(
            "INSERT OR IGNORE INTO calls VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ev["event_id"], sim_minute, ev.get("ts"), ev["workflow_id"], ev["campaign_id"],
             ev["lead_id"], ev.get("person_id"), cohort_id, ev.get("config_version"),
             ev["variant"].get("welcome_message"), ev["variant"].get("voice"),
             ev["variant"].get("caller_id"), ev["variant"].get("prompt_version"),
             1 if ev.get("connected") else 0, 1 if ev.get("engaged") else 0,
             ev.get("disposition"), 1 if qa.get("hallucination_flag") else 0,
             int(ev["ts"][11:13]) if ev.get("ts") else None))
        return cur.rowcount

    def commit(self):
        self.db.commit()

    # -- aggregate queries (the only way stats are ever computed) ------------
    def variant_stats(self, wid, dim, since_minute=0, until_minute=None, cohort_id=None):
        """Per-variant aggregates for a dimension over a sim-minute window.
        Returns {variant: {dials, connected, engaged}}."""
        col = {"welcome_message": "welcome", "voice": "voice",
               "caller_id": "caller_id", "prompt_version": "prompt_version"}[dim]
        q = (f"SELECT {col}, COUNT(*), SUM(connected), SUM(engaged) FROM calls"
             " WHERE workflow_id=? AND sim_minute>=?")
        args = [wid, since_minute]
        if until_minute is not None:
            q += " AND sim_minute<?"
            args.append(until_minute)
        if cohort_id:
            q += " AND cohort_id=?"
            args.append(cohort_id)
        q += f" GROUP BY {col}"
        out = {}
        for variant, dials, conn, eng in self.db.execute(q, args):
            if variant is not None:
                out[variant] = {"dials": dials, "connected": conn or 0, "engaged": eng or 0}
        return out

    def kpi(self, wid, since_minute=0, until_minute=None, cohort_id=None):
        q = ("SELECT COUNT(*), SUM(connected), SUM(engaged) FROM calls"
             " WHERE workflow_id=? AND sim_minute>=?")
        args = [wid, since_minute]
        if until_minute is not None:
            q += " AND sim_minute<?"
            args.append(until_minute)
        if cohort_id:
            q += " AND cohort_id=?"
            args.append(cohort_id)
        dials, conn, eng = self.db.execute(q, args).fetchone()
        return {"dials": dials or 0, "connected": conn or 0, "engaged": eng or 0}

    def hallucination_stats(self, wid, since_minute=0, prompt_version=None):
        q = ("SELECT COUNT(*), SUM(hallucination) FROM calls WHERE workflow_id=?"
             " AND connected=1 AND sim_minute>=?")
        args = [wid, since_minute]
        if prompt_version:
            q += " AND prompt_version=?"
            args.append(prompt_version)
        n, h = self.db.execute(q, args).fetchone()
        return {"connected": n or 0, "flagged": h or 0}

    def hour_stats(self, wid, cohort_id=None):
        q = ("SELECT hour, COUNT(*), SUM(connected) FROM calls WHERE workflow_id=?")
        args = [wid]
        if cohort_id:
            q += " AND cohort_id=?"
            args.append(cohort_id)
        q += " GROUP BY hour"
        return {h: {"dials": d, "connected": c or 0}
                for h, d, c in self.db.execute(q, args) if h is not None}

    def lead_cells(self, wid):
        """(age_band, lang) -> lead count, history + live, for cohort design."""
        rows = self.db.execute(
            "SELECT age_band, lang, COUNT(*) FROM leads WHERE workflow_id=? GROUP BY 1,2",
            (wid,)).fetchall()
        return {(a, l): n for a, l, n in rows}

    def cohort_lead_count(self, wid, cohort_id):
        row = self.db.execute(
            "SELECT COUNT(*) FROM leads WHERE workflow_id=? AND cohort_id=?",
            (wid, cohort_id)).fetchone()
        return row[0]
