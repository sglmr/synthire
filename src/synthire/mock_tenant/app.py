"""A local FastAPI stand-in for a Workday tenant.

Exposes:
  - GET  /ccx/api/v1/tenant/search_workers   -- RaaS-style REST report
  - POST /ccx/service/tenant/Staffing/v45.0  -- SOAP endpoint dispatching
                                                 Get_Workers and Hire_Employee
                                                 by sniffing the request body,
                                                 the same way Workday's single
                                                 SOAP endpoint dispatches on
                                                 the wrapped element name.

No authentication -- this is a local dev/demo fixture, not a real tenant.
"""

import logging

from fastapi import FastAPI, Request, Response

from .. import workday_xml
from ..config import RAAS_SEARCH_PATH, SOAP_STAFFING_PATH, configure_logging
from .state import TenantState

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Synthire Mock Workday Tenant")
state = TenantState()


@app.get(RAAS_SEARCH_PATH)
def search_workers(name: str = ""):
    results = state.search_raw(name)
    logger.info("RaaS search_workers(name=%r) -> %d result(s)", name, len(results))
    return {"workers": results}


@app.post(SOAP_STAFFING_PATH)
async def staffing_soap(request: Request):
    body = (await request.body()).decode("utf-8")

    if "Get_Workers_Request" in body:
        logger.info("SOAP request dispatched: Get_Workers")
        return _handle_get_workers(body)
    if "Hire_Employee_Request" in body:
        logger.info("SOAP request dispatched: Hire_Employee")
        return _handle_hire_employee(body)

    logger.warning("Unrecognized SOAP request body (no known request element found)")
    return Response(status_code=400, content="Unrecognized SOAP request")


def _handle_get_workers(body: str) -> Response:
    employee_ids = workday_xml.parse_get_workers_request_xml(body)
    workers = state.get_workers(employee_ids)
    logger.info("Get_Workers(employee_ids=%s) -> %d worker(s)", employee_ids, len(workers))
    xml = workday_xml.build_get_workers_response_xml(workers)
    return Response(content=xml, media_type="text/xml")


def _handle_hire_employee(body: str) -> Response:
    proposal = workday_xml.parse_hire_employee_request_xml(body)
    result = state.hire(proposal)
    xml = workday_xml.build_hire_employee_event_response_xml(result)
    status_code = 200 if result.success else 422
    return Response(content=xml, media_type="text/xml", status_code=status_code)
