"""Data shapes shared between the mock tenant and the MCP server.

These are deliberately a small, flat subset of what a real Workday Worker or
Hire_Employee payload can carry -- see workday_xml.py for which schema fields
each one maps to and why the rest were left out.
"""

from dataclasses import dataclass, field


@dataclass
class WorkerCandidate:
    """One row from the RaaS worker-search report -- enough to disambiguate by name."""

    employee_id: str
    first_name: str
    last_name: str
    job_profile: str
    country: str

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


@dataclass
class WorkerTemplate:
    """The subset of a Get_Workers response used to clone a new hire from."""

    employee_id: str
    first_name: str
    last_name: str
    email: str
    country: str
    job_profile: str
    job_family: str
    supervisory_org: str


@dataclass
class HireProposal:
    """The simplified, human-reviewable payload that becomes a Hire_Employee_Request."""

    first_name: str
    last_name: str
    email: str
    country: str
    job_profile: str
    supervisory_org: str
    hire_date: str
    employee_id: str | None = None
    position_id: str | None = None


@dataclass
class HireResult:
    """What the mock tenant hands back after a Hire_Employee call."""

    success: bool
    employee_id: str | None = None
    wid: str | None = None
    exceptions: list[str] = field(default_factory=list)
