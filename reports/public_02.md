# Grade report — public_02_incidents

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.209 | -14.2% | 0.159 | -12.7% | 0.476 | +0.9% | 2% | 69 (310) |
| nw_kyc | 0.381 | -0.8% | 0.250 | +1.1% | 0.582 | -2.9% | -20% | 27 (38) |
| nw_renewal | 0.421 | -2.2% | 0.260 | -1.1% | 0.541 | -1.2% | -5% | 55 (58) |
| ALL | 0.316 | -5.8% | 0.212 | -5.0% | 0.528 | -0.4% | -4% | 151 (406) |

## Changes applied by the controller

20 applied — beneficial: 7, harmful: 4, neutral: 9

- nw_renewal v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice'] engageΔ=+0.041 didΔ=+0.000 → **beneficial**
- nw_kyc v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice'] engageΔ=-0.019 didΔ=+0.000 → **harmful**
- ks_cancel v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice'] engageΔ=+0.023 didΔ=+0.000 → **beneficial**
- nw_renewal v3 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- ks_cancel v3 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nw_kyc v3 (controller_approved) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nw_renewal v4 (controller_approved) dims=['welcome_message'] engageΔ=+0.111 didΔ=+0.000 → **beneficial**
- ks_cancel v4 (controller_approved) dims=['prompt_version'] engageΔ=+0.031 didΔ=+0.000 → **beneficial**
- ks_cancel v5 (controller_approved) dims=['voice'] engageΔ=-0.007 didΔ=+0.000 → **neutral**
- ks_cancel v6 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.383 → **beneficial**
- nw_kyc v4 (controller_approved) dims=['welcome_message'] engageΔ=+0.010 didΔ=+0.000 → **beneficial**
- nw_renewal v5 (controller_approved) dims=['voice'] engageΔ=+0.003 didΔ=+0.000 → **neutral**
- nw_renewal v6 (controller_approved) dims=['welcome_message'] engageΔ=-0.006 didΔ=+0.000 → **neutral**
- nw_kyc v5 (controller_approved) dims=['welcome_message'] engageΔ=-0.010 didΔ=+0.000 → **harmful**
- ks_cancel v8 (controller_approved) dims=['prompt_version'] engageΔ=-0.051 didΔ=+0.000 → **harmful**
- ks_cancel v9 (controller_approved) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- ks_cancel v10 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=-0.465 → **harmful**
- nw_kyc v6 (controller_approved) dims=['welcome_message'] engageΔ=+0.010 didΔ=+0.000 → **neutral**
- nw_renewal v8 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=-0.005 → **neutral**
- nw_renewal v9 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.028 → **beneficial**

## Governance

```
{
  "approval_requests": 17,
  "decisions": {
    "approved": 17,
    "expired": 0
  },
  "rejection_reasons": {},
  "applied_via_approval": 16,
  "auto_applied": 4,
  "auto_apply_rejected": 0,
  "apply_conflicts": 1,
  "lapsed": 0,
  "peak_requests_per_24h": {
    "nw_renewal": 2,
    "nw_kyc": 2,
    "ks_cancel": 3
  }
}
```

## Incidents

```
[
  {
    "type": "did_flagged",
    "workflow": "ks_cancel",
    "at": "D2 10:00",
    "flagged_did_share_by_day": {
      "2": 0.4,
      "3": 0.094,
      "4": 0.104,
      "5": 0.807,
      "6": 0.905,
      "7": 0.901,
      "8": 0.905,
      "9": 0.907
    }
  },
  {
    "type": "supervisor_edit",
    "workflow": "ks_cancel",
    "at": "D3 11:30",
    "mttr_minutes": 450,
    "fixed_by": "controller_approved"
  },
  {
    "type": "supervisor_edit",
    "workflow": "nw_renewal",
    "at": "D5 15:00"
  }
]
```

## Decaying variants — share of in-population calls still on the variant, by day after onset

```
{
  "nw_renewal:welcome_message=W3": {
    "2": 1.0,
    "3": 0.793,
    "4": 0.616,
    "5": 0.623,
    "6": 0.627,
    "7": 0.617,
    "8": 0.623,
    "9": 0.629
  }
}
```

Credits used: 36 · validation runs: 6 · LLM fix calls: 2