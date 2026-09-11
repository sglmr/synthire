# Synthire — Project Plan

A record of what's been decided and built so far, and what's still open. See [README.md](README.md) for the architecture/why, and [Agents.md](Agents.md) for the agent's operating instructions.

## 1. Requirements

- [x] **Core use case:** chat "hire a new worker with the same data as [existing worker]" → MCP tools search Workday, disambiguate the template with the user, fetch its full data, propose a new-hire payload, let the user tweak it, and submit it — only after explicit confirmation.
- [x] **Purpose:** (a) a real tool for Workday integration test-data entry, (b) a hands-on way to learn MCP server design, (c) a portfolio piece for a job interview.
- [x] **Scope decisions locked in during design:**
  - Mock the Workday tenant entirely — no live tenant, no authentication.
  - Use real SOAP/XML for the mock (not a JSON-simplified stand-in), so the wire format stays authentic.
  - `Hire_Employee` should only use the fields that are actually schema-required or business-rule-required for a from-scratch hire — not the full set of optional fields Workday supports.
  - Python, managed with `uv`.
  - Project structured as a proper `src/synthire` package (not flat scripts) — "make it portfolio-worthy."
  - Supervisory Organization (required by `Hire_Employee`, absent from the original `worker_list.csv`) is supplied by adding a `Supervisory_Org` column to the CSV, rather than deriving it at runtime or hardcoding a single value.

## 2. Research

- [x] Read `devdata/worker_list.csv`, `Get_Workers_Request.xml`/`Response.xml`, `Hire_Employee_Request.xml`, `Hire_Employee_Event_Response.xml` to see the existing fixtures.
- [x] Discovered the sample XML files are raw WSDL-generated skeletons — nearly every element is commented `<!--Optional:-->`, which made them useless on their own as a signal of what's actually required.
- [x] Wrote a one-off script to parse `devdata/Staffing.wsdl` as XML and walk the `xsd:complexType` tree from `Hire_Employee_RequestType` down, reporting each element's real `minOccurs`/`maxOccurs`.
- [x] Found that `Hire_Employee_Data` requires choosing exactly one of 5 ways to identify the hire (`Applicant_Reference`, `Former_Worker_Reference`, `Student_Reference`, `Academic_Affiliate_Reference`, or `Applicant_Data`) — confirmed `Applicant_Data` (a brand-new pre-hire) is the right branch for this project, since it's always creating new synthetic people rather than converting an existing record.
- [x] Mined the `wd:Validation`/`wd:Validation_Message` annotations embedded in the WSDL to find business-rule-required fields the XSD itself doesn't enforce: Hire Date, legal name, ≥1 contact method, and a Supervisory Organization (or a derivable one via Position Reference, which this prototype doesn't use).
- [x] Confirmed via the WSDL that `Get_Workers` lives alongside `Hire_Employee` in `Staffing.wsdl`, and identified the real element names for a worker record (`Worker_Data` → `Personal_Data`, `Employment_Data` → `Position_Data`, `Organization_Data`) to keep the mock's simplified response schema-authentic.

## 3. Build

- [x] `devdata/worker_list.csv` — added `Supervisory_Org` column, one org per `Job_Family` (Finance Division, Sales Division, Engineering Division, Human Resources Division, Marketing Division, IT Division).
- [x] `src/synthire/config.py` — shared namespace (`urn:com.workday/bsvc`), version (`v45.0`), file paths, mock tenant URL/ports.
- [x] `src/synthire/models.py` — `WorkerCandidate`, `WorkerTemplate`, `HireProposal`, `HireResult` dataclasses shared by both sides of the wire.
- [x] `src/synthire/workday_xml.py` — builders/parsers for `Get_Workers_Request`/`Response` and `Hire_Employee_Request`/`Event_Response`, using real Workday element/namespace conventions restricted to the required-field subset.
- [x] `src/synthire/csv_store.py` — loads the worker CSV.
- [x] `src/synthire/mock_tenant/state.py` — in-memory tenant state seeded from the CSV; validates and executes hires; returns Workday-style `Exceptions_Data` messages on failure.
- [x] `src/synthire/mock_tenant/app.py` — FastAPI app: RaaS-style `search_workers` REST endpoint, and one SOAP endpoint that dispatches `Get_Workers`/`Hire_Employee` by sniffing the request body.
- [x] `src/synthire/mcp_server/client.py` — `WorkdayClient`, the HTTP client the MCP server uses to call the mock tenant.
- [x] `src/synthire/mcp_server/server.py` — the MCP server itself (`mcp` SDK, `MCPServer`), exposing `search_workers`, `get_worker_template`, `generate_synthetic_identity`, `synthesize_test_hire`.
- [x] `src/synthire/__init__.py` — `run_mock_tenant()` / `run_mcp_server()` entry points.
- [x] `pyproject.toml` — added `fastapi`, `uvicorn`, `httpx`, `faker`, `mcp[cli]` dependencies; registered `synthire-mock` and `synthire-mcp` console scripts.
- [x] Removed the original root-level `mock_tenant.py` prototype (superseded by the package).
- [x] Rewrote `README.md` and `Agents.md` to describe the actual, current architecture and decisions rather than the original aspirational draft.
- [x] Added `README.md`'s "Ideas for Future Development" section (testing, real Workday connectivity, more flexible input, fidelity/scope).
- [x] Added structured logging: `config.configure_logging()` (stderr-only, so it can't corrupt the MCP server's stdio protocol stream), hire attempt/outcome logging in `mock_tenant/state.py`, SOAP dispatch logging in `mock_tenant/app.py`, and per-tool-call logging in `mcp_server/server.py`. Documented in `README.md`'s "Logging" section and cross-referenced from `Agents.md` as a debugging resource.

## 4. Test

Everything below was verified manually this session (no automated test suite yet — see Future Work):

- [x] `GET /ccx/api/v1/tenant/search_workers?name=...` returns the expected CSV rows as JSON.
- [x] `WorkdayClient.get_worker(employee_id)` round-trips a real `Get_Workers_Request`/`Response` SOAP exchange and parses back a correct `WorkerTemplate`.
- [x] `WorkdayClient.hire_employee(proposal)` round-trips a `Hire_Employee_Request`/`Event_Response` exchange and returns a correct `HireResult` with a generated `employee_id` and `wid`.
- [x] Chained lookup confirmed: a freshly hired worker's `employee_id` can immediately be fetched back via `Get_Workers`.
- [x] Validation failure path confirmed: missing name/email/org, an unrecognized supervisory org, and an invalid hire-date string all produce the expected `exceptions` list instead of a crash.
- [x] All four MCP tool functions (`search_workers`, `get_worker_template`, `generate_synthetic_identity`, `synthesize_test_hire`) called directly and confirmed to produce correct output against the running mock tenant.
- [x] Confirmed the `synthire-mock` and `synthire-mcp` console scripts start cleanly after `uv sync`.
- [x] Visually inspected generated `Get_Workers_Response` and `Hire_Employee_Request` XML for authentic Workday structure/naming.
- [x] Confirmed log output lands on **stderr** for both processes (verified by redirecting stdout/stderr separately) and never on stdout — critical for the MCP server, since stdout carries the JSON-RPC protocol stream.
- [x] Confirmed log content: RaaS searches, SOAP dispatch, hire attempts (including rejection reasons), and every MCP tool call's inputs/outcome all show up with the expected `HH:MM:SS [logger.name] LEVEL: message` format.

## 5. Deploy / Run

There's no "deploy" target — this is a local prototype meant to run on a developer's machine and be pointed to by an MCP client:

- [x] `uv sync` installs dependencies.
- [x] `uv run synthire-mock` starts the mock tenant on `localhost:8000`.
- [x] `uv run synthire-mcp` starts the MCP server (stdio transport) for a client to connect to.
- [x] README documents the `claude_desktop_config.json` entry to register it with Claude Desktop.

## 6. Future Work

Things worth doing next, roughly in the order I'd tackle them:

- [ ] **Run it for real.** Everything above was verified by calling the Python functions directly — the actual chat-driven flow through Claude Desktop (or another MCP client) hasn't been exercised yet. This is the most important next step: watch the agent actually search, disambiguate, propose, and confirm in a live conversation, and see where its phrasing or judgment needs tightening in `Agents.md`.
- [ ] **Add an automated test suite** (`pytest`): round-trip tests for every `workday_xml` builder/parser pair, and validation-path tests for `TenantState.hire()`. Currently all verification lives in this session's ad hoc scripts, not in the repo.
- [ ] **Add a durable audit trail** of every synthetic hire attempted (not just logged to stderr) — a small append-only store (SQLite or JSONL) recording who/what/when for each `Hire_Employee` call, surviving a mock-tenant restart. Today's logging is enough to debug one run, but there's no record once the process exits and no way to answer "what test data has this tool ever created" after the fact. See `README.md`'s "Observability" section.
- [ ] **Add a "John Doe"-style well-known demo worker** to `worker_list.csv` — the original example query ("same data as John Doe") doesn't actually match anyone in the fixture; worth either adding one or updating the example to a real name like Scott Peterson.
- [ ] **Harden network error handling** between the MCP server and the mock tenant — `WorkdayClient` currently lets raw `httpx` exceptions propagate if the mock tenant isn't running.
- [ ] **Make the mock tenant URL configurable** (env var or config file) instead of hardcoded to `localhost:8000`, for running multiple instances or pointing at a deployed mock later.
- [ ] **Consider CI** (GitHub Actions) once a test suite exists — lint + test on push.
- [ ] **Extend `Hire_Employee` fidelity** as a deliberate follow-on, not scope creep: compensation package, position time type, employee type (contractor vs. employee), or national ID — each as its own incremental addition to `workday_xml.py`, keeping the "why is this field here" reasoning intact.
- [ ] **Document the in-memory-only limitation** more visibly if this gets demoed live: restarting `synthire-mock` forgets every hire made during the session, which is intentional but worth calling out to an audience mid-demo.
- [ ] **Decide on a git history strategy.** Nothing in this session has been committed yet — worth an initial commit (or a small number of logical commits) before this goes anywhere public, since a single giant commit undersells the design work documented above.
