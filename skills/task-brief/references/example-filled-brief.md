# Filled brief example

Illustrative example, not a real backlog item. It shows the expected level of detail:
enough context to start, numbered requirements, acceptance criteria a reviewer can run,
and a baseline for the negative check (AC2).

---

# TASK-007 - Cut hanging proxy health checks with a timeout and one retry

| Field | Value |
| --- | --- |
| Project | Proxy pool |
| Requester | lead@example.com |
| Assignee | dev-2@example.com |
| Leader | lead@example.com |
| Reviewer | dev-1@example.com |
| Start | TBD |
| Status | Todo |
| Priority | P2 |
| Estimate | 0.5 |
| Due | 2026-10-30 |
| Created | 2026-10-16 |
| Depends on | none |
| Issue | none |

## Goal

A proxy that accepts the TCP connection but never answers is taken out of the pool within
one check cycle instead of blocking the check loop.

## Context

- `src/proxy/health.py:42` sends one request per check with no timeout, so a silent proxy
  keeps the check pending indefinitely.
- `src/proxy/pool.py:88` keeps handing out the proxy until a check reports it as failed.
- The 2026-10-10 run stalled for 40 minutes with four proxies in this state.
- Baseline for AC2: `grep -n "requests.get(" src/proxy/health.py` returns line 42 today,
  with no `timeout=` argument.

## Scope

In scope:

- Request timeout and one retry inside the health check.

Out of scope:

- Pool rotation policy, gateway routing, proxy provider integration.

## Requirements

- R1: The health check request uses a 5 second timeout.
- R2: One retry is attempted after a 2 second backoff when the first attempt times out.
- R3: A failed check logs one warning line with the proxy id and the elapsed time.
- R4: The function keeps its current name, arguments and return type.

## Deliverables

- `src/proxy/health.py` - updated
- A pull request; its link goes under `## Evidence`

## Acceptance criteria

- [ ] AC1: A request to a deliberately silent endpoint returns a failure in 5 to 12
      seconds - command and output pasted.
- [ ] AC2: `grep -n "requests.get(" src/proxy/health.py` - expected every match carries
      `timeout=`; the baseline in Context shows the check matches today.
- [ ] AC3: A run against a dead proxy removes it from the pool within one check cycle and
      writes the warning line - log excerpt pasted.

## Risks and notes

- Retrying doubles the requests sent to a failing proxy; keep the backoff and do not raise
  the retry count without measuring.

## References

- `src/proxy/health.py:42`
- `src/proxy/pool.py:88`

## Open questions

- None.

## Evidence

- None yet.

## Review log

None yet. Entries are appended by the task-review skill and never rewritten.
