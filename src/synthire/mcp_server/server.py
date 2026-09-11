"""MCP server exposing Workday test-hire tools backed by the mock tenant.

Tool flow (see Agents.md for the full human-in-the-loop script):
  1. search_workers          -- find template worker(s) by name, disambiguate with the user
  2. get_worker_template      -- fetch the confirmed template's cloneable fields
  3. generate_synthetic_identity -- produce a fresh name/email so the new hire
     isn't a literal duplicate of the template (agent then proposes the full
     hire and gets user sign-off in chat -- no tool needed for that step)
  4. synthesize_test_hire     -- submit the user-approved payload to the tenant
"""

import logging
from datetime import date

from faker import Faker
from mcp.server.mcpserver import MCPServer

from ..config import configure_logging
from ..models import HireProposal
from .client import WorkdayClient

configure_logging()
logger = logging.getLogger(__name__)

mcp = MCPServer("Synthire")
_client = WorkdayClient()

_LOCALE_BY_COUNTRY = {
    "USA": "en_US",
    "GBR": "en_GB",
    "AUS": "en_AU",
    "CAN": "en_CA",
    "DEU": "de_DE",
    "FRA": "fr_FR",
    "JPN": "ja_JP",
    "BRA": "pt_BR",
    "IND": "en_IN",
    "MEX": "es_MX",
}


@mcp.tool()
def search_workers(name: str) -> list[dict]:
    """Search the Workday worker population by name to find a template worker.

    Returns candidate matches (employee_id, name, job_profile, country) for the
    user to disambiguate between if more than one comes back.
    """
    logger.info("Tool call: search_workers(name=%r)", name)
    candidates = _client.search_workers(name)
    logger.info("search_workers -> %d candidate(s)", len(candidates))
    return [
        {
            "employee_id": c.employee_id,
            "full_name": c.full_name,
            "job_profile": c.job_profile,
            "country": c.country,
        }
        for c in candidates
    ]


@mcp.tool()
def get_worker_template(employee_id: str) -> dict:
    """Fetch the confirmed template worker's cloneable fields via Get_Workers.

    Call this only after the user has confirmed exactly which worker (by
    employee_id) to use as the template -- it returns the job profile,
    supervisory org, and country that a new hire will be cloned from.
    """
    logger.info("Tool call: get_worker_template(employee_id=%r)", employee_id)
    worker = _client.get_worker(employee_id)
    if worker is None:
        logger.warning("get_worker_template: no worker found for employee_id=%r", employee_id)
        return {"error": f"No worker found with employee_id {employee_id}"}
    return {
        "employee_id": worker.employee_id,
        "first_name": worker.first_name,
        "last_name": worker.last_name,
        "email": worker.email,
        "country": worker.country,
        "job_profile": worker.job_profile,
        "job_family": worker.job_family,
        "supervisory_org": worker.supervisory_org,
    }


@mcp.tool()
def generate_synthetic_identity(country: str) -> dict:
    """Generate a fresh synthetic first name, last name, and email.

    Use this to give the new hire its own identity instead of literally
    duplicating the template worker's name. `country` should be an
    ISO 3166-1 alpha-3 code (e.g. "USA", "GBR", "JPN") -- it's used to pick a
    locale-appropriate name where supported, falling back to en_US otherwise.
    """
    logger.info("Tool call: generate_synthetic_identity(country=%r)", country)
    locale = _LOCALE_BY_COUNTRY.get(country.upper(), "en_US")
    faker = Faker(locale)
    first_name = faker.first_name()
    last_name = faker.last_name()
    email = f"{first_name}.{last_name}@fakecorp.com".lower()
    logger.info("generate_synthetic_identity -> %s %s (locale=%s)", first_name, last_name, locale)
    return {"first_name": first_name, "last_name": last_name, "email": email}


@mcp.tool()
def synthesize_test_hire(
    first_name: str,
    last_name: str,
    email: str,
    country: str,
    job_profile: str,
    supervisory_org: str,
    hire_date: str | None = None,
    employee_id: str | None = None,
    position_id: str | None = None,
) -> dict:
    """Submit the user-approved hire payload to the tenant via Hire_Employee.

    Only call this after the user has explicitly confirmed the proposed
    fields -- this is the one tool in this server that actually mutates the
    tenant. `country` is an ISO 3166-1 alpha-3 code; `hire_date` defaults to
    today (ISO format) if omitted. `employee_id` is optional -- leave it out
    to let the tenant auto-assign one.
    """
    proposal = HireProposal(
        first_name=first_name,
        last_name=last_name,
        email=email,
        country=country,
        job_profile=job_profile,
        supervisory_org=supervisory_org,
        hire_date=hire_date or date.today().isoformat(),
        employee_id=employee_id,
        position_id=position_id,
    )
    logger.info("Tool call: synthesize_test_hire(%s %s, job_profile=%r, supervisory_org=%r)", first_name, last_name, job_profile, supervisory_org)
    result = _client.hire_employee(proposal)
    if result.success:
        logger.info("synthesize_test_hire succeeded: employee_id=%s wid=%s", result.employee_id, result.wid)
    else:
        logger.warning("synthesize_test_hire rejected: %s", "; ".join(result.exceptions))
    return {
        "success": result.success,
        "employee_id": result.employee_id,
        "wid": result.wid,
        "exceptions": result.exceptions,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
