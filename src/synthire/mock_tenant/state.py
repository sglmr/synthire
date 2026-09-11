"""In-memory state for the mock tenant.

Seeded from devdata/worker_list.csv on startup. Hiring a worker through this
mock doesn't touch the CSV -- new hires just live in memory for the lifetime
of the process, which is enough to demo "hire, then immediately look the new
worker back up via Get_Workers."
"""

import logging
import uuid
from datetime import date

from ..csv_store import load_workers_csv
from ..models import HireProposal, HireResult, WorkerTemplate

logger = logging.getLogger(__name__)

REQUIRED_FIELD_MESSAGES = {
    "first_name": "A legal name is required when adding an applicant.",
    "last_name": "A legal name is required when adding an applicant.",
    "email": "At least one email address, phone number or address is required to create a new applicant.",
    "supervisory_org": "The supervisory organization must be entered or be derivable from the Position Reference.",
    "hire_date": "The Hire Date is required.",
    "job_profile": "A Job Profile is required for the position.",
}


class TenantState:
    def __init__(self) -> None:
        self._workers: dict[str, WorkerTemplate] = {}
        self._raw_rows: dict[str, dict[str, str]] = {}
        self._known_orgs: set[str] = set()
        self._next_employee_number = 1

        for row in load_workers_csv():
            template = WorkerTemplate(
                employee_id=row["Employee_ID"],
                first_name=row["First_Name"],
                last_name=row["Last_Name"],
                email=row["Email_Address"],
                country=row["Country"],
                job_profile=row["Job_Profile"],
                job_family=row["Job_Family"],
                supervisory_org=row["Supervisory_Org"],
            )
            self._workers[template.employee_id] = template
            self._raw_rows[template.employee_id] = row
            self._known_orgs.add(template.supervisory_org)

            number = int(template.employee_id.removeprefix("EMP") or 0)
            self._next_employee_number = max(self._next_employee_number, number + 1)

    def search_raw(self, name: str) -> list[dict[str, str]]:
        if not name:
            return list(self._raw_rows.values())
        needle = name.lower()
        return [row for row in self._raw_rows.values() if needle in f"{row['First_Name']} {row['Last_Name']}".lower()]

    def get_worker(self, employee_id: str) -> WorkerTemplate | None:
        return self._workers.get(employee_id)

    def get_workers(self, employee_ids: list[str]) -> list[WorkerTemplate]:
        return [self._workers[eid] for eid in employee_ids if eid in self._workers]

    def hire(self, proposal: HireProposal) -> HireResult:
        logger.info(
            "Hire_Employee attempt: %s %s -> job_profile=%r supervisory_org=%r hire_date=%s",
            proposal.first_name,
            proposal.last_name,
            proposal.job_profile,
            proposal.supervisory_org,
            proposal.hire_date,
        )
        exceptions = []
        for field_name, message in REQUIRED_FIELD_MESSAGES.items():
            if not getattr(proposal, field_name):
                exceptions.append(message)

        if proposal.supervisory_org and proposal.supervisory_org not in self._known_orgs:
            exceptions.append(f"Proposed supervisory organization ({proposal.supervisory_org}) is not valid.")

        if proposal.hire_date:
            try:
                date.fromisoformat(proposal.hire_date)
            except ValueError:
                exceptions.append(f"Hire Date '{proposal.hire_date}' is not a valid date.")

        if exceptions:
            logger.warning("Hire_Employee rejected for %s %s: %s", proposal.first_name, proposal.last_name, "; ".join(exceptions))
            return HireResult(success=False, exceptions=exceptions)

        employee_id = proposal.employee_id or f"EMP{self._next_employee_number:03d}"
        self._next_employee_number = max(self._next_employee_number, int(employee_id.removeprefix("EMP") or 0) + 1)
        wid = str(uuid.uuid4())

        template = WorkerTemplate(
            employee_id=employee_id,
            first_name=proposal.first_name,
            last_name=proposal.last_name,
            email=proposal.email,
            country=proposal.country,
            job_profile=proposal.job_profile,
            job_family="",
            supervisory_org=proposal.supervisory_org,
        )
        self._workers[employee_id] = template
        self._raw_rows[employee_id] = {
            "Employee_ID": employee_id,
            "First_Name": proposal.first_name,
            "Last_Name": proposal.last_name,
            "Is_Manager": "N",
            "Email_Address": proposal.email,
            "Job_Family": "",
            "Job_Profile": proposal.job_profile,
            "Country": proposal.country,
            "Supervisory_Org": proposal.supervisory_org,
        }

        logger.info("Hire_Employee succeeded: employee_id=%s wid=%s (%s %s)", employee_id, wid, proposal.first_name, proposal.last_name)
        return HireResult(success=True, employee_id=employee_id, wid=wid)
