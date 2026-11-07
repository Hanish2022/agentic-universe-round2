# Grade report — public_01_dev

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.346 | +1.2% | 0.242 | +1.0% | 0.502 | +0.4% | -1% | 53 (52) |
| nw_kyc | 0.359 | -4.6% | 0.240 | -1.0% | 0.590 | -3.7% | 0% | 14 (21) |
| nw_renewal | 0.422 | +0.5% | 0.260 | -0.7% | 0.558 | +2.0% | 23% | 51 (39) |
| ALL | 0.374 | -0.3% | 0.248 | -0.0% | 0.539 | +0.0% | 8% | 118 (112) |

## Changes applied by the controller

11 applied — beneficial: 2, neutral: 8, harmful: 1

- nw_renewal v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice'] engageΔ=+0.068 didΔ=+0.000 → **beneficial**
- ks_cancel v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice'] engageΔ=-0.002 didΔ=+0.000 → **neutral**
- nw_renewal v3 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- ks_cancel v3 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nw_kyc v2 (controller_approved) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nw_renewal v4 (controller_approved) dims=['welcome_message'] engageΔ=+0.076 didΔ=+0.000 → **beneficial**
- ks_cancel v4 (controller_approved) dims=['welcome_message'] engageΔ=+0.008 didΔ=+0.000 → **neutral**
- ks_cancel v5 (controller_approved) dims=['welcome_message'] engageΔ=-0.008 didΔ=+0.000 → **neutral**
- nw_renewal v5 (controller_approved) dims=['voice'] engageΔ=-0.001 didΔ=+0.000 → **neutral**
- nw_renewal v6 (controller_approved) dims=['welcome_message'] engageΔ=-0.040 didΔ=+0.000 → **harmful**
- ks_cancel v6 (controller_approved) dims=['welcome_message'] engageΔ=+0.008 didΔ=+0.000 → **neutral**

## Governance

```
{
  "approval_requests": 11,
  "decisions": {
    "approved": 9,
    "rejected": 2,
    "expired": 0
  },
  "rejection_reasons": {
    "approver declined (judgement call)": 2
  },
  "applied_via_approval": 9,
  "auto_applied": 2,
  "auto_apply_rejected": 0,
  "apply_conflicts": 0,
  "lapsed": 0,
  "peak_requests_per_24h": {
    "nw_renewal": 2,
    "nw_kyc": 2,
    "ks_cancel": 2
  }
}
```

## Incidents

```
[]
```

## Decaying variants — share of in-population calls still on the variant, by day after onset

```
{
  "nw_renewal:welcome_message=W3": {
    "3": 0.925,
    "4": 0.614,
    "5": 0.611,
    "6": 0.614,
    "7": 0.623
  }
}
```

Credits used: 0 · validation runs: 0 · LLM fix calls: 0