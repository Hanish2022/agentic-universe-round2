C13 CRASH-RECOVERY TEST — public_01, runs/dev04, 2026-11-07
Controller started via ./run.sh http://127.0.0.1:8703 (shipped build).
At sim_minute 5040 (day 3.5): 5 proposals applied, 2 PENDING approvals in flight, 174896 calls ingested.
kill -9 sent to the controller process. Simulator left running.
Controller restarted via ./run.sh with the same state DB.
Result: run completed unaided. Pending approvals were picked up and applied (9 applied total).
Duplicate audit on the final store: duplicate proposal_id = 0, duplicate (workflow,version) applied = 0, duplicate call event_id = 0.
Restart log contained 0 errors/tracebacks. Final grade: reports/public_01.md (8% overall headroom).
