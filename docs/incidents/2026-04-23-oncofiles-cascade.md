# Incident postmortem — 2026-04-23 oncofiles cascade

**Status**: resolved · **Severity**: P0 · **User-facing duration**: ~13 min
api downtime · **Filed as**: #431

## TL;DR

Peter's oncofiles deploy failure (unrelated commit, migration 062) cascaded
into oncoteam going down for ~13 minutes. Oncoteam's own code was healthy
throughout — it just couldn't get past Railway's healthcheck window because
its HTTP startup awaited oncofiles-dependent I/O synchronously before
binding the port. Root cause is architectural: oncoteam and oncofiles are
peer services, but oncoteam had a hidden hard dependency during boot.

## Timeline (UTC)

| Time | Event |
|------|-------|
| 20:05:xx | Peter pushes oncofiles commit `7d8b8d9` (`feat(#476) backfill_orphan_prompt_logs`, migration 062). Deploy fails — migration 062's 19,707 UPDATEs in one transaction. `oncofiles.com` → 502. |
| 20:06:58 | Claude Code pushes oncoteam commit `7585de0` (docs-only: DR runbook for #397). |
| 20:07:xx | Railway auto-deploys oncoteam. Build succeeds. Container starts. |
| 20:07:xx–20:13:xx | Oncoteam container enters startup path: `_run_http` awaits `load_approved_phones()` → `oncofiles_client.get_agent_state()` → MCP session establishment hangs (oncofiles unreachable) → timeout + retry + circuit breaker dance → ~20-40s blocking. Port not bound. Railway healthcheck probes find no listener. After `restartPolicyMaxRetries=5` with the same cascade, Railway sets `status=FAILED`, `deploymentStopped=true`. |
| 20:13:51 | UptimeRobot alert: `oncoteam-production.up.railway.app/health` is down (HTTP 502). |
| 20:13–20:19 | Claude Code diagnoses: pulls Railway logs, identifies MCP timeout in startup path, confirms oncofiles is also 502. Files recovery commit. |
| 20:19:52 | Redeploy of same commit triggered. Fails with same pattern (cause still oncofiles-down). |
| 20:24:34 | Claude Code pushes oncoteam commit `b083479` (fix: decouple startup I/O to `asyncio.create_task` with 8s `wait_for` timeout). |
| 20:28:xx | Deploy `b083479` succeeds. `api.oncoteam.cloud/health` → 200 while `oncofiles.com/health` → 502. Architectural principle verified. |
| 20:40:xx | Commit `fa0d17e` ships regression tests + dashboard banner copy for full-outage state. |
| later | Step 5 ships (agent skip on outage), Step 6 this doc, Step 7 chaos drill. |

## Root cause

`server.py` → `main()` → `_run_http()` contained:

```python
# BEFORE (problematic)
async def _run_http():
    start_scheduler()
    try:
        await load_approved_phones()      # <-- blocks on oncofiles MCP
    except Exception as e:
        logging.warning(...)
    try:
        await load_patient_tokens()       # <-- blocks on oncofiles MCP
    except Exception as e:
        logging.warning(...)
    await mcp.run_async(...)              # port bind — only reached after both awaits
```

The `try/except` looked defensive — "we log + continue if these fail" —
but critically, both `load_*` calls await `oncofiles_client.get_agent_state()`,
which attempts an MCP session via `fastmcp`. When oncofiles is unreachable,
the session establishment doesn't raise promptly; it goes through:

1. `_get_client()` → `await client.__aenter__()` → `self._connect()` → hangs
2. Internal oncofiles_client retry machinery (20s per-call timeout, circuit
   breaker, semaphore wait, RSS backoff checks) — each attempt eats time
3. Eventually raises `TimeoutError`, `try/except` catches it, moves on

Total time: 20-40 seconds just for the first `load_approved_phones()` call.
Railway's `healthcheckTimeout=60` was not hit, but `restartPolicyMaxRetries=5`
with rapid restart cycles DID burn through tries as the proxy layer marked
the unbinded port as unresponsive.

## Why the existing circuit breaker didn't save us

The `oncofiles_client._circuit_state` breaker trips after N consecutive
failures and blocks further calls for a cooldown. That design is correct
for runtime, but:

1. At **startup**, breaker state is empty (`_circuit_state = {}`). It can't
   short-circuit the first call.
2. Even after the first call fails and trips the breaker, the SECOND call
   (`load_patient_tokens`) hits a freshly-opened breaker and short-circuits
   immediately — but the first call already ate 20-40s.
3. Per CLAUDE.md post-#424: the local breaker only trips on upstream-open
   signals (`"Circuit breaker open"` / `"Database briefly unavailable"`).
   A hard 502 / TCP timeout doesn't match those strings, so the breaker
   DIDN'T trip at all on the initial oncofiles outage — it would retry
   every call within the attempt budget.

## Remediation (shipped in #431)

### Step 1 — decouple startup I/O (commit `b083479`)

```python
# AFTER
async def _run_http():
    start_scheduler()

    async def _safe_bg(coro, label):
        try:
            await asyncio.wait_for(coro, timeout=8.0)
        except TimeoutError:
            logging.warning("%s timed out at startup — proceeding", label)
        except Exception as e:
            logging.warning("%s failed at startup: %s", label, e)

    asyncio.create_task(_safe_bg(load_approved_phones(), "load_approved_phones"))
    asyncio.create_task(_safe_bg(load_patient_tokens(), "load_patient_tokens"))

    await mcp.run_async(...)              # port bind — immediate
```

Port now binds within a few hundred ms of `_run_http` entering, regardless
of oncofiles state. Lazy-load retry path (the `_approved_phones_loaded`
flag + per-request `load_approved_phones()` call in `api_whatsapp_status`)
handles recovery: first live request after oncofiles comes back will
populate the state.

### Step 2 — startup coupling audit (verified none remain)

Grep of `server.py` + `scheduler.py` + `autonomous_tasks.py` for
module-level `oncofiles_client.*` calls + `next_run_time=now()` immediate
triggers returned empty. The two `load_*` paths were the only startup
couplings.

### Step 3 — regression tests (`tests/test_startup_resilience.py`)

4 tests pin:
- `load_approved_phones` / `load_patient_tokens` swallow TimeoutError
- `_safe_bg` wrapper bounds hang time to its timeout
- `get_scheduler_status` doesn't touch oncofiles (critical for `/health`)

### Step 4 — dashboard banner shows full-outage state (commit `fa0d17e`)

`useCircuitBreakerStatus.degraded` now fires when the readiness proxy
itself errors (not just when the upstream breaker is open). New
`outageKind` computed (`'unreachable' | 'half_open' | 'breaker_open'`)
routes `ApiErrorBanner` to accurate copy per state. New EN+SK locale
string:

- EN: *"Data service is offline — oncoteam is up, but oncofiles is unreachable. Cached views still render; new data will resume when the service recovers."*

Pre-fix: zero banner during full oncofiles outage. Users saw broken
cards with no explanation.

### Step 5 — agent skip during outage

`run_autonomous_task` now checks `oncofiles_client.get_circuit_breaker_status()`
before any Claude API call. If breaker is open, returns
`{"skipped": true, "reason": "oncofiles_unavailable", "cost": 0.0}`
immediately. Saves Claude budget + avoids agent-run log noise during
outage windows. `keepalive_ping` is exempt because it bypasses
`run_autonomous_task` entirely (it's the canary that detects recovery).

### Step 6 — this document

### Step 7 — chaos drill CI

GitHub Actions workflow that boots oncoteam against a deliberately-
offline oncofiles fixture and asserts `/health` → 200 within 10 seconds.
Regression gate for any future refactor that would accidentally re-
introduce a startup coupling.

## Lessons learned

1. **"Try/except around an await is not the same as non-blocking."** An
   await that eventually raises is still an await that blocks. To truly
   not-block, you need `asyncio.create_task` + `asyncio.wait_for` for
   bounded failure.

2. **Hidden dependencies in startup paths are the worst class of coupling.**
   Oncoteam's runtime code already had circuit-breaker-aware calls to
   oncofiles (#424). But two innocent-looking `await load_*` lines at
   startup bypassed the entire safety net. Audit startup paths with
   particular paranoia.

3. **Reliability invariants deserve explicit tests.** The regression tests
   in Step 3 will catch any future refactor that accidentally reintroduces
   a startup-time blocking call on oncofiles. Without that, the same bug
   could re-land in 6 months.

4. **Peer services shouldn't cascade.** The failure of one Railway project
   should not be able to take down another Railway project in the same
   workspace. If it can, the design has a hidden dependency. That's true
   even when "it's just startup" — Railway's 5-retry policy can burn
   through your patience faster than any graceful-degradation strategy.

5. **Surface outages prominently.** Silently-broken cards teach users to
   distrust the dashboard. Explicit "Data service is offline" copy teaches
   them to wait out the recovery. The cost of hiding bad news is always
   higher than the cost of being honest about it.

## Prevention going forward

- **Invariant added to CLAUDE.md**: "oncoteam MUST boot independently of
  oncofiles. `/health` MUST return 200 within 10 seconds of process
  start, regardless of oncofiles state."
- **CI chaos drill** (Step 7): mocks oncofiles 502 and asserts the
  invariant. Fails the CI if any future commit violates it.
- **Dashboard banner** never silently hides full-outage state again.

## Incidentally surfaced

- Oncofiles migration 062 (the trigger for Peter's deploy failure) has a
  single-transaction 19,707-UPDATE design that crashed oncofiles' Turso
  replica under load. That's tracked separately on oncofiles' repo —
  not an oncoteam concern.
- `/api/oncofiles-readiness` proxy returns 502 when upstream is down.
  Frontend composable didn't handle that path. Fixed in Step 4.

## References

- #431 — incident issue + full plan
- #424 — circuit breaker contract (prior work this incident revealed to be incomplete)
- commit `b083479` — Step 1 fix
- commit `fa0d17e` — Steps 2-4 fix
- Railway project: oncoteam-prod-backups (separate, unrelated — #397)
