# Judge0 versus go-judge campaign: a100-engine-ab

Status: **complete**

Source commit: `c0ae1d00c7663f3a54cd4b4da517f7d670bc9260`

Fixed profile: 8 runner workers, 4 app workers, 6 runner CPUs, 8 GiB.
Both profiles use fresh Python state per case. Grouping and HTTP reuse
are disabled.

| Workload | Status | Comparison |
| --- | --- | --- |
| Ransom Note | complete | [comparison](../a100-engine-ab-ransom-note-try01/comparison.md) |
| Number of Islands | complete | [comparison](../a100-engine-ab-number-of-islands-try01/comparison.md) |
| Minimum Cost for Tickets | complete | [comparison](../a100-engine-ab-minimum-cost-for-tickets-try01/comparison.md) |
