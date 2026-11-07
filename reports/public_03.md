# Grade report — public_03_load

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| arav_cancel_2 | 0.370 | +8.6% | 0.246 | +0.5% | 0.531 | +6.6% | 45% | 419 (383) |
| arav_kyc_1 | 0.386 | +7.6% | 0.215 | -0.0% | 0.636 | +6.1% | 34% | 343 (349) |
| arav_renewal_0 | 0.440 | +8.9% | 0.263 | +0.0% | 0.594 | +8.4% | 47% | 434 (458) |
| kest_cancel_2 | 0.368 | +8.6% | 0.246 | +0.6% | 0.536 | +7.7% | 57% | 422 (388) |
| kest_kyc_1 | 0.393 | +10.7% | 0.217 | +1.5% | 0.642 | +7.6% | 42% | 368 (309) |
| kest_renewal_0 | 0.440 | +9.7% | 0.264 | +0.5% | 0.596 | +9.1% | 53% | 427 (430) |
| nort_cancel_2 | 0.353 | +4.0% | 0.243 | -0.1% | 0.518 | +4.2% | 26% | 400 (389) |
| nort_kyc_1 | 0.382 | +7.8% | 0.215 | +0.6% | 0.632 | +5.9% | 38% | 361 (346) |
| nort_renewal_0 | 0.441 | +10.0% | 0.265 | +0.6% | 0.594 | +9.0% | 48% | 429 (431) |
| tide_cancel_2 | 0.369 | +8.6% | 0.246 | +0.7% | 0.528 | +5.9% | 43% | 391 (406) |
| tide_kyc_1 | 0.380 | +7.0% | 0.214 | +0.2% | 0.631 | +5.7% | 30% | 341 (339) |
| tide_renewal_0 | 0.441 | +9.9% | 0.265 | +0.8% | 0.597 | +9.3% | 52% | 377 (422) |
| ALL | 0.397 | +8.5% | 0.242 | +0.5% | 0.584 | +7.2% | 44% | 4712 (4650) |

## Changes applied by the controller

82 applied — beneficial: 28, neutral: 34, harmful: 20

- nort_renewal_0 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice'] engageΔ=+0.068 didΔ=+0.000 → **beneficial**
- nort_kyc_1 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice'] engageΔ=+0.075 didΔ=+0.000 → **beneficial**
- nort_cancel_2 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice'] engageΔ=-0.002 didΔ=+0.000 → **neutral**
- kest_renewal_0 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice'] engageΔ=+0.068 didΔ=+0.000 → **beneficial**
- kest_kyc_1 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice'] engageΔ=+0.075 didΔ=+0.000 → **beneficial**
- kest_cancel_2 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice'] engageΔ=-0.002 didΔ=+0.000 → **neutral**
- arav_renewal_0 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice'] engageΔ=+0.068 didΔ=+0.000 → **beneficial**
- arav_kyc_1 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice'] engageΔ=+0.075 didΔ=+0.000 → **beneficial**
- arav_cancel_2 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice'] engageΔ=-0.002 didΔ=+0.000 → **neutral**
- tide_renewal_0 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice'] engageΔ=+0.068 didΔ=+0.000 → **beneficial**
- tide_kyc_1 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice'] engageΔ=+0.075 didΔ=+0.000 → **beneficial**
- tide_cancel_2 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice'] engageΔ=-0.002 didΔ=+0.000 → **neutral**
- kest_cancel_2 v3 (controller_approved) dims=['welcome_message'] engageΔ=+0.055 didΔ=+0.000 → **beneficial**
- tide_renewal_0 v3 (controller_approved) dims=['welcome_message'] engageΔ=+0.076 didΔ=+0.000 → **beneficial**
- nort_cancel_2 v3 (controller_approved) dims=['voice'] engageΔ=+0.064 didΔ=+0.000 → **beneficial**
- kest_renewal_0 v3 (controller_approved) dims=['welcome_message'] engageΔ=+0.076 didΔ=+0.000 → **beneficial**
- kest_cancel_2 v4 (controller_approved) dims=['voice'] engageΔ=+0.063 didΔ=+0.000 → **beneficial**
- nort_renewal_0 v3 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nort_cancel_2 v4 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- kest_renewal_0 v4 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- kest_cancel_2 v5 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- arav_renewal_0 v3 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- arav_cancel_2 v3 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_renewal_0 v4 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_cancel_2 v3 (controller_auto) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nort_renewal_0 v4 (controller_approved) dims=['welcome_message'] engageΔ=+0.076 didΔ=+0.000 → **beneficial**
- nort_kyc_1 v3 (controller_approved) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- kest_kyc_1 v3 (controller_approved) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- arav_renewal_0 v4 (controller_approved) dims=['welcome_message'] engageΔ=+0.076 didΔ=+0.000 → **beneficial**
- arav_kyc_1 v3 (controller_approved) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_kyc_1 v3 (controller_approved) dims=['schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_cancel_2 v4 (controller_approved) dims=['voice'] engageΔ=+0.023 didΔ=+0.000 → **beneficial**
- nort_renewal_0 v5 (controller_approved) dims=['voice'] engageΔ=+0.011 didΔ=+0.000 → **beneficial**
- nort_kyc_1 v4 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.069 didΔ=+0.000 → **beneficial**
- kest_kyc_1 v4 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.069 didΔ=+0.000 → **beneficial**
- kest_cancel_2 v6 (controller_approved) dims=['welcome_message'] engageΔ=-0.004 didΔ=+0.000 → **neutral**
- nort_cancel_2 v5 (controller_approved) dims=['voice'] engageΔ=-0.019 didΔ=+0.000 → **harmful**
- arav_cancel_2 v4 (controller_approved) dims=['voice'] engageΔ=+0.063 didΔ=+0.000 → **beneficial**
- kest_renewal_0 v5 (controller_approved) dims=['welcome_message'] engageΔ=-0.015 didΔ=+0.000 → **harmful**
- kest_cancel_2 v7 (controller_approved) dims=['voice'] engageΔ=-0.018 didΔ=+0.000 → **harmful**
- arav_cancel_2 v5 (controller_approved) dims=['welcome_message'] engageΔ=+0.054 didΔ=+0.000 → **beneficial**
- tide_renewal_0 v5 (controller_approved) dims=['welcome_message'] engageΔ=-0.015 didΔ=+0.000 → **harmful**
- tide_cancel_2 v5 (controller_approved) dims=['voice'] engageΔ=+0.040 didΔ=+0.000 → **beneficial**
- kest_renewal_0 v6 (controller_approved) dims=['voice'] engageΔ=+0.010 didΔ=+0.000 → **beneficial**
- arav_kyc_1 v4 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.068 didΔ=+0.000 → **beneficial**
- tide_kyc_1 v4 (controller_approved) dims=['welcome_message'] engageΔ=+0.036 didΔ=+0.000 → **beneficial**
- nort_renewal_0 v6 (controller_approved) dims=['voice'] engageΔ=-0.010 didΔ=+0.000 → **neutral**
- kest_renewal_0 v7 (controller_approved) dims=['voice'] engageΔ=-0.009 didΔ=+0.000 → **neutral**
- arav_renewal_0 v5 (controller_approved) dims=['welcome_message'] engageΔ=-0.015 didΔ=+0.000 → **harmful**
- tide_kyc_1 v5 (controller_approved) dims=['voice'] engageΔ=+0.004 didΔ=+0.000 → **neutral**
- nort_renewal_0 v7 (controller_approved) dims=['welcome_message'] engageΔ=-0.023 didΔ=+0.000 → **harmful**
- tide_cancel_2 v6 (controller_approved) dims=['welcome_message'] engageΔ=+0.055 didΔ=+0.000 → **beneficial**
- nort_kyc_1 v5 (controller_approved) dims=['voice'] engageΔ=-0.023 didΔ=+0.000 → **harmful**
- arav_cancel_2 v6 (controller_approved) dims=['voice'] engageΔ=-0.018 didΔ=+0.000 → **harmful**
- nort_renewal_0 v8 (controller_approved) dims=['welcome_message'] engageΔ=-0.014 didΔ=+0.000 → **harmful**
- nort_kyc_1 v6 (controller_approved) dims=['welcome_message'] engageΔ=-0.017 didΔ=+0.000 → **harmful**
- arav_renewal_0 v6 (controller_approved) dims=['voice'] engageΔ=-0.004 didΔ=+0.000 → **neutral**
- tide_renewal_0 v6 (controller_approved) dims=['voice'] engageΔ=-0.004 didΔ=+0.000 → **neutral**
- arav_kyc_1 v5 (controller_approved) dims=['welcome_message'] engageΔ=-0.017 didΔ=+0.000 → **harmful**
- kest_kyc_1 v5 (controller_approved) dims=['voice'] engageΔ=-0.009 didΔ=+0.000 → **neutral**
- tide_kyc_1 v6 (controller_approved) dims=['voice'] engageΔ=-0.012 didΔ=+0.000 → **harmful**
- nort_renewal_0 v9 (controller_approved) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- kest_renewal_0 v8 (controller_approved) dims=['voice'] engageΔ=+0.013 didΔ=+0.000 → **beneficial**
- nort_kyc_1 v7 (controller_approved) dims=['voice'] engageΔ=-0.009 didΔ=+0.000 → **neutral**
- tide_cancel_2 v7 (controller_approved) dims=['welcome_message'] engageΔ=-0.004 didΔ=+0.000 → **neutral**
- nort_renewal_0 v10 (controller_approved) dims=['voice'] engageΔ=+0.013 didΔ=+0.000 → **beneficial**
- nort_renewal_0 v11 (controller_approved) dims=['welcome_message'] engageΔ=-0.004 didΔ=+0.000 → **neutral**
- nort_kyc_1 v8 (controller_approved) dims=['welcome_message'] engageΔ=-0.015 didΔ=+0.000 → **harmful**
- kest_kyc_1 v6 (controller_approved) dims=['welcome_message'] engageΔ=-0.015 didΔ=+0.000 → **harmful**
- arav_kyc_1 v6 (controller_approved) dims=['welcome_message'] engageΔ=-0.011 didΔ=+0.000 → **harmful**
- tide_kyc_1 v7 (controller_approved) dims=['welcome_message'] engageΔ=-0.015 didΔ=+0.000 → **harmful**
- kest_renewal_0 v9 (controller_approved) dims=['voice'] engageΔ=-0.018 didΔ=+0.000 → **harmful**
- arav_renewal_0 v7 (controller_approved) dims=['welcome_message'] engageΔ=-0.012 didΔ=+0.000 → **harmful**
- arav_kyc_1 v7 (controller_approved) dims=['voice'] engageΔ=-0.009 didΔ=+0.000 → **neutral**
- nort_renewal_0 v12 (controller_approved) dims=['welcome_message'] engageΔ=-0.007 didΔ=+0.000 → **neutral**
- kest_renewal_0 v10 (controller_approved) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_renewal_0 v7 (controller_approved) dims=['welcome_message'] engageΔ=-0.007 didΔ=+0.000 → **neutral**
- nort_renewal_0 v13 (controller_approved) dims=['welcome_message'] engageΔ=-0.002 didΔ=+0.000 → **neutral**
- kest_kyc_1 v7 (controller_approved) dims=['voice'] engageΔ=-0.022 didΔ=+0.000 → **harmful**
- arav_renewal_0 v8 (controller_approved) dims=['welcome_message'] engageΔ=-0.001 didΔ=+0.000 → **neutral**
- arav_kyc_1 v8 (controller_approved) dims=['welcome_message'] engageΔ=-0.015 didΔ=+0.000 → **harmful**
- kest_renewal_0 v11 (controller_approved) dims=['welcome_message'] engageΔ=-0.001 didΔ=+0.000 → **neutral**

## Governance

```
{
  "approval_requests": 90,
  "decisions": {
    "approved": 74,
    "rejected": 6,
    "expired": 4
  },
  "rejection_reasons": {
    "approver declined (judgement call)": 6
  },
  "applied_via_approval": 74,
  "auto_applied": 8,
  "auto_apply_rejected": 0,
  "apply_conflicts": 0,
  "lapsed": 0,
  "peak_requests_per_24h": {
    "nort_renewal_0": 3,
    "nort_kyc_1": 2,
    "nort_cancel_2": 2,
    "kest_renewal_0": 3,
    "kest_kyc_1": 2,
    "kest_cancel_2": 3,
    "arav_renewal_0": 3,
    "arav_kyc_1": 2,
    "arav_cancel_2": 2,
    "tide_renewal_0": 2,
    "tide_kyc_1": 2,
    "tide_cancel_2": 3
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
  "nort_renewal_0:welcome_message=W3": {
    "3": 0.686,
    "4": 0.354
  },
  "kest_renewal_0:welcome_message=W3": {
    "3": 0.854,
    "4": 0.785
  },
  "arav_renewal_0:welcome_message=W3": {
    "3": 0.861,
    "4": 0.559
  },
  "tide_renewal_0:welcome_message=W3": {
    "3": 0.859,
    "4": 0.688
  }
}
```

Credits used: 0 · validation runs: 0 · LLM fix calls: 0