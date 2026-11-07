"""C2 — ONE shared cohort object.

The same CohortSet is used by detection, experiments, call-time optimisation
and the supervisor view, and it is exactly what gets written into the workflow
config (Product memo: no three subtly different definitions of a cohort).

Design (deterministic, from ingested lead features only):
- Candidate segments are (age_band x lang) cells — the two features a voice
  agent's reception plausibly depends on.
- A cell becomes a named cohort only if it holds >= MIN_COHORT_SHARE of the
  workflow's leads. Below that, an experiment arm inside it could never reach
  minimum sample inside a scenario, so the cell stays in `default` rather than
  fragmenting traffic (the cost of more cohorts is slower learning everywhere).
- At most MAX_COHORTS named cohorts, largest first; ties break by cell key so
  the result never depends on dict ordering.
"""
MIN_COHORT_SHARE = 0.05
MAX_COHORTS = 5


def _cohort_id(age_band: str, lang: str) -> str:
    return f"{age_band.replace('+', 'p').replace('-', '_')}_{lang}"


class CohortSet:
    def __init__(self, cells: dict):
        """cells: {(age_band, lang): lead_count} for one workflow."""
        total = sum(cells.values()) or 1
        ranked = sorted(
            ((cell, n) for cell, n in cells.items() if n / total >= MIN_COHORT_SHARE),
            key=lambda kv: (-kv[1], kv[0]))
        self.defs = []  # list of (cohort_id, {"age_band": ab, "lang": lang})
        for (ab, lang), _n in ranked[:MAX_COHORTS]:
            self.defs.append((_cohort_id(ab, lang), {"age_band": ab, "lang": lang}))
        self.ids = [cid for cid, _ in self.defs] + ["default"]

    def assign(self, features: dict) -> str:
        """First-match wins, exactly like the simulator's cohort evaluation."""
        for cid, where in self.defs:
            if (features.get("age_band") == where["age_band"]
                    and features.get("lang") == where["lang"]):
                return cid
        return "default"

    def config_cohorts(self):
        """The `cohorts` array for the workflow config, in evaluation order."""
        return [{"id": cid, "where": {"age_band": [w["age_band"]], "lang": [w["lang"]]}}
                for cid, w in self.defs]
