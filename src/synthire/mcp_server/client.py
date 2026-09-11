"""HTTP client the MCP server uses to talk to the mock (or, someday, a real) tenant."""

import httpx

from .. import workday_xml
from ..config import MOCK_TENANT_BASE_URL, RAAS_SEARCH_PATH, SOAP_STAFFING_PATH
from ..models import HireProposal, HireResult, WorkerCandidate, WorkerTemplate


class WorkdayClient:
    def __init__(self, base_url: str = MOCK_TENANT_BASE_URL) -> None:
        self._base_url = base_url

    def search_workers(self, name: str) -> list[WorkerCandidate]:
        response = httpx.get(f"{self._base_url}{RAAS_SEARCH_PATH}", params={"name": name})
        response.raise_for_status()
        rows = response.json()["workers"]
        return [
            WorkerCandidate(
                employee_id=row["Employee_ID"],
                first_name=row["First_Name"],
                last_name=row["Last_Name"],
                job_profile=row["Job_Profile"],
                country=row["Country"],
            )
            for row in rows
        ]

    def get_worker(self, employee_id: str) -> WorkerTemplate | None:
        request_xml = workday_xml.build_get_workers_request_xml([employee_id])
        response = httpx.post(
            f"{self._base_url}{SOAP_STAFFING_PATH}",
            content=request_xml,
            headers={"Content-Type": "text/xml"},
        )
        response.raise_for_status()
        workers = workday_xml.parse_get_workers_response_xml(response.text)
        return workers[0] if workers else None

    def hire_employee(self, proposal: HireProposal) -> HireResult:
        request_xml = workday_xml.build_hire_employee_request_xml(proposal)
        response = httpx.post(
            f"{self._base_url}{SOAP_STAFFING_PATH}",
            content=request_xml,
            headers={"Content-Type": "text/xml"},
        )
        return workday_xml.parse_hire_employee_event_response_xml(response.text)
