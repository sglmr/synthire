# SyntHire: Workday Test Data Synthesizer (MCP)

Chat: _"Hire a new worker with the same job as Liz Erd."_ SyntHire searches Workday for the template worker, confirms the match with you, clones the job/org context, generates a fresh synthetic identity, and submits a real Workday `Hire_Employee` API call. All with you approving the exact details before anything is sent.

## Why this project exists

I build and test Workday integrations for a living, and entering test data transactions by hand is one of the more boring and repetetive parts o the job. Hiring a single worker means assembling several interdependent fields (Supervisory Organization, Job Profile, legal name, contact info) and approval steps that are more than tedious. This project automates that specific pain point, and doubled as a way to learn about the [Model Context Protocol](https://modelcontextprotocol.io) hands-on rather than just read about it.

### What this demonstrates

- **MCP server design**, not just API wrapping: four small, single-purpose tools (`search_workers`, `get_worker_template`, `generate_synthetic_identity`, `synthesize_test_hire`) instead of one do-everything tool, so the orchestrating agent (and a human) can inspect and intervene between each step.
- **Human-in-the-loop safety design for a mutating action.** The agent is explicitly instructed (see [Agents.md](Agents.md)) to disambiguate the template worker and get sign-off on the exact hire payload _before_ the one tool that actually writes data. This mirrors how you'd actually want an agent to behave against a real Workday tenant.
- **Building a safe environment to demo an inherently risky workflow.** "Let an LLM hire people in Workday" isn't something you point at a production or even a real sandbox tenant on day one. A FastAPI mock tenant makes the whole flow demoable with real XML API calls and testable without compromising real HR data (nor my career).
- **Realistic API mocking**, not a JSON toy stand-in. The mock tenant speaks actual Workday SOAP envelopes (`urn:com.workday/bsvc` namespace, `v45.0`-style versioning, `Applicant_Data` / `Legal_Name_Data` / `Organization_Reference` element names) built with `xml.etree.ElementTree`, and a single SOAP endpoint that dispatches on the wrapped request element the same way Workday's real endpoint does.
- **Workday domain knowledge.** Workday API's define dozens of optional sections for (benefits, national IDs, military service...). Rather than guess at what's "required," a smalls cript walked the raw XSD to find real `minOccurs="1"` constraints, and separately mined the `wd:Validation` annotations embedded in the WSDL for business-rule requirements the schema itself doesn't enforce (e.g. _"The Hire Date is required"_, _"A legal name is required when adding an applicant"_).

## Architecture

Two independent local processes talking real (simplified) Workday SOAP + RaaS-style REST over HTTP — no Workday authentication involved, by design, since this is a local prototype, not a path to a live tenant:

```
Claude Desktop (or any MCP client)
        │  stdio (MCP)
        ▼
  MCP Server  (src/synthire/mcp_server/)
        │  HTTP (RaaS REST + SOAP/XML)
        ▼
  Mock FastAPI Tenant (src/synthire/mock_tenant/)
        │
        ▼
  devdata/worker_list.csv  (seed data)
```

1. **MCP Server** (`src/synthire/mcp_server/`) — built with the official `mcp` SDK (`MCPServer`, the current v2.x API). Exposes four tools to an MCP client:
   - `search_workers(name)` — find template worker candidates
   - `get_worker_template(employee_id)` — fetch the confirmed template's cloneable fields via Workday's `Get_Workers` API
   - `generate_synthetic_identity(country)` — `Faker`-generated name/email, locale-matched to the template's country
   - `synthesize_test_hire(...)` — submits the user-approved payload via Workday's `Hire_Employee` API
2. **Mock Tenant** (`src/synthire/mock_tenant/`) — a FastAPI app standing in for a Workday tenant.
   - `GET /ccx/api/v1/tenant/search_workers?name=...` — RaaS-style report backed by `devdata/worker_list.csv`
   - `POST /ccx/service/tenant/Staffing/v45.0` — one SOAP endpoint dispatching `Get_Workers` and `Hire_Employee` by sniffing the request body for the wrapped element name
   - In-memory state (`state.py`) seeded from the CSV; a successful hire is validated Workday-style and immediately visible to a follow-up `Get_Workers` call; a failed one comes back with real-sounding `Exceptions_Data` messages

Shared modules (`workday_xml.py`, `models.py`, `config.py`) keep SOAP envelope building/parsing and field definitions in one place, so the mock tenant and the MCP client can never drift out of agreement on the wire format.

### Why only required fields?

Implementing exactly the schema-required + business-rule-required subset — legal name, one contact method, a Supervisory Organization, a Hire Date, and a Job Profile — keeps the prototype's surface area small without faking the shape of the real integration. Every element name and namespace in the generated XML is authentic Workday. What's been trimmed is the volume of optional data, not fidelity. This sets up a solid base for extending in the future..

### Logging

Processes log through Python's standard `logging` module, configured once in `config.configure_logging()` with a consistent `HH:MM:SS [logger.name] LEVEL: message` format. Logs deliberately go to **stderr**, not stdout: the MCP server talks to its client over stdio, and stdout is reserved for the JSON-RPC protocol stream — writing logs there would corrupt the connection.

- The mock tenant (`mock_tenant/app.py`, `mock_tenant/state.py`) logs every RaaS search, every SOAP dispatch, and every hire attempt — including _why_ a hire was rejected (the same validation messages returned to the caller).
- The MCP server (`mcp_server/server.py`) logs every tool call's key inputs and outcome, so a debugging session can see exactly what the agent decided to call and with what arguments, independent of what the chat transcript shows.

This is enough to debug a single run; it doesn't persist anywhere. See [Ideas for Future Development](#ideas-for-future-development) for a durable audit trail.

## Prerequisites

- Python 3.13+
- `uv` package manager
- Claude Desktop (or another MCP client)

## Quickstart

1. **Install dependencies:**

   ```bash
   uv sync
   ```

2. **Start the mock Workday tenant** (in one terminal):

   ```bash
   uv run synthire-mock
   ```

3. **Point an MCP client at the server.** For Claude Desktop, add to `claude_desktop_config.json`:

   ```json
   {
     "mcpServers": {
       "synthire": {
         "command": "uv",
         "args": [
           "run",
           "--directory",
           "/absolute/path/to/synthire",
           "synthire-mcp"
         ]
       }
     }
   }
   ```

   Or run it standalone for debugging:

   ```bash
   uv run synthire-mcp
   ```

4. **Chat:** "I want to hire a new worker with the same job as Scott Peterson." (See `devdata/worker_list.csv` for other names in the seed data.)

## Project Layout

```
devdata/                   # WSDLs, sample SOAP payloads, and the worker CSV fixture
src/synthire/
  config.py                # shared namespace/version/paths + logging setup
  models.py                # WorkerCandidate, WorkerTemplate, HireProposal, HireResult
  workday_xml.py           # build/parse Get_Workers + Hire_Employee SOAP envelopes
  csv_store.py             # loads devdata/worker_list.csv
  mock_tenant/
    app.py                 # FastAPI app (RaaS search + SOAP dispatch)
    state.py                # in-memory tenant state + hire validation
  mcp_server/
    client.py              # WorkdayClient (HTTP calls to the mock tenant)
    server.py              # MCP tool definitions
```

## Ideas for Future Development

The near-term punch list (tests, error handling, config cleanup) lives in [plan.md](plan.md#6-future-work). These are the bigger, longer-term directions this could grow in:

**Testing & reliability**

- An automated test suite (`pytest`) for `workday_xml` build/parse round-trips and `TenantState` validation — everything so far has been verified by hand.
- CI (GitHub Actions) running lint + tests on push once that suite exists.

**Observability**

- A durable audit trail of every synthetic hire attempted (not just logged to stderr) — a small append-only store (SQLite or a JSONL file) recording who/what/when for each `Hire_Employee` call, surviving a mock-tenant restart. Today's logging (see above) is enough to debug one run, but there's no record once the process exits, and no way to answer "what test data has this tool ever created" after the fact — which matters once synthetic workers need to be tracked and cleaned up in a shared sandbox.
- Structured (JSON) log output as an option, so logs could feed a real log aggregator once this points at anything other than a local mock.

**Real Workday connectivity**

- OAuth 2.0 / Integration System User (ISU) authentication, so the MCP server can talk to an actual Workday tenant instead of only the mock — the biggest step from "prototype" to "usable tool."
- Support for multiple test environments (e.g. different sandbox tenants per team or per release), with the MCP server selecting or being told which tenant to target rather than hardcoding one base URL.
- Once real connectivity exists: guardrails specific to that risk — e.g. refusing to run against anything that doesn't look like a sandbox/non-prod tenant URL, and a hard cap on hires per session.
- Tagging synthetic workers distinctly (a naming convention or custom ID field) so test data stays identifiable and easy to clean up in a shared real sandbox, rather than blending in with real employees.
- A companion "terminate" tool to clean up synthetic workers after a test run — `Staffing.wsdl` already defines `Terminate_Employee`, so this would follow the same pattern as `Hire_Employee`.

**More flexible input**

- Accepting criteria beyond a template worker's name — e.g. _"I need an Australian Sales worker"_ — by adding a filtered search tool (country, job family, job profile, manager flag) alongside the name-based `search_workers`, so the agent can pick or synthesize a template from criteria instead of requiring a specific person to clone.
- Batch generation — _"hire 5 test workers across different countries"_ — for teams that need a population of test data rather than one worker at a time.
- Extending beyond `Hire_Employee` to other Staffing business processes already defined in the WSDL (`Edit_Position`, `Change_Job`, contingent worker hires), generalizing this from a hire-only tool into a broader test-data operations server.

**Fidelity & scope**

- Progressively adding optional `Hire_Employee` sections (compensation package, position time type, employee type) as deliberate, individually-justified extensions rather than all at once — each one earning its place the same way the current required-field set did.
- A "dry run" mode that shows the exact generated SOAP envelope before submission, for advanced users who want to inspect the wire format directly.
- Persisting mock tenant state (SQLite instead of in-memory) so longer demo sessions or repeated test runs survive a restart.

---

See [plan.md](plan.md) for a full breakdown of work completed and what's still open, and [Agents.md](Agents.md) for the exact human-in-the-loop instructions the agent follows.
