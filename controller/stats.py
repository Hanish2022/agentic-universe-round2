"""Deterministic statistics for winner selection (constraint 4).

No LLM ever decides a winner. Every decision in the system reduces to the
two-proportion z-test below with a Bonferroni correction across the family of
comparisons made in the same round, plus a minimum-sample rule and a minimum
practical effect. Same inputs -> same answer, always.
"""
import math

# Decision constants. Picked once, written down, applied everywhere.
ALPHA = 0.05            # family-wise error rate per experiment round
MIN_EFFECT = 0.02       # a winner must beat control by >= 2 points to matter
MIN_ARM_SAMPLE = 300    # min observations per arm before any test is run


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def two_prop_ztest(k1: int, n1: int, k2: int, n2: int):
    """Two-sided z-test for p1 != p2. Returns (p_value, p1 - p2)."""
    if n1 == 0 or n2 == 0:
        return 1.0, 0.0
    p1, p2 = k1 / n1, k2 / n2
    p_pool = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0, p1 - p2
    z = (p1 - p2) / se
    return 2 * (1 - _norm_cdf(abs(z))), p1 - p2


def decide_winner(arms, n_comparisons: int):
    """arms: list of dicts {name, k, n} where arm[0] is the control.

    Returns the winning arm dict or None. A challenger wins only if it beats
    control by >= MIN_EFFECT with p < ALPHA / n_comparisons (Bonferroni) and
    every arm has >= MIN_ARM_SAMPLE observations. If several challengers pass,
    the one with the largest effect wins — deterministic tie-break by name.
    """
    if len(arms) < 2:
        return None
    control = arms[0]
    if any(a["n"] < MIN_ARM_SAMPLE for a in arms):
        return None
    threshold = ALPHA / max(1, n_comparisons)
    best = None
    for ch in arms[1:]:
        p, diff = two_prop_ztest(ch["k"], ch["n"], control["k"], control["n"])
        if p < threshold and diff >= MIN_EFFECT:
            if best is None or diff > best[1] or (diff == best[1] and ch["name"] < best[0]["name"]):
                best = (ch, diff)
    return best[0] if best else None


def rate(k: int, n: int):
    return (k / n) if n else None
