"""Build and parse the (simplified) Workday SOAP payloads used by this project.

Only three message shapes are handled, and each one only carries the fields
identified as schema-required or business-rule-required in Staffing.wsdl for
a from-scratch employee hire (see devdata/Staffing.wsdl,
Hire_Employee_Business_Process_DataType):

- Get_Workers_Response   (mock tenant -> MCP server)
- Hire_Employee_Request  (MCP server -> mock tenant)
- Hire_Employee_Event_Response (mock tenant -> MCP server)

Real Workday responses carry dozens of optional sections (compensation,
benefits, national IDs, ...). This module intentionally only round-trips the
fields this prototype needs, using authentic Workday element and namespace
names so the wire format still reads like the real thing.
"""

from xml.etree import ElementTree as ET

from .config import COUNTRY_ID_TYPE, EMAIL_USAGE_TYPE_ID, WD_NAMESPACE, WD_VERSION
from .models import HireProposal, HireResult, WorkerTemplate

NS = {"bsvc": WD_NAMESPACE}
ET.register_namespace("bsvc", WD_NAMESPACE)


def _tag(name: str) -> str:
    return f"{{{WD_NAMESPACE}}}{name}"


def _sub(parent: ET.Element, name: str, text: str | None = None) -> ET.Element:
    el = ET.SubElement(parent, _tag(name))
    if text is not None:
        el.text = text
    return el


def _reference(parent: ET.Element, name: str, id_type: str, id_value: str, descriptor: str | None = None) -> ET.Element:
    return _reference_multi(parent, name, [(id_type, id_value)], descriptor=descriptor)


def _reference_multi(
    parent: ET.Element, name: str, ids: list[tuple[str, str]], descriptor: str | None = None
) -> ET.Element:
    ref = ET.SubElement(parent, _tag(name))
    if descriptor:
        ref.set(f"{{{WD_NAMESPACE}}}Descriptor", descriptor)
    for id_type, id_value in ids:
        id_el = ET.SubElement(ref, _tag("ID"))
        id_el.set(f"{{{WD_NAMESPACE}}}type", id_type)
        id_el.text = id_value
    return ref


def _find_text(el: ET.Element | None, path: str) -> str | None:
    if el is None:
        return None
    found = el.find(path, NS)
    return found.text if found is not None else None


def _find_id(el: ET.Element | None, ref_path: str, id_type: str) -> str | None:
    """Find `bsvc:ID[@bsvc:type=id_type]` under the reference at ref_path."""
    if el is None:
        return None
    ref = el.find(ref_path, NS)
    if ref is None:
        return None
    for id_el in ref.findall(f"{{{WD_NAMESPACE}}}ID"):
        if id_el.get(f"{{{WD_NAMESPACE}}}type") == id_type:
            return id_el.text
    return None


def _to_xml_string(root: ET.Element) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


# --------------------------------------------------------------------------
# Get_Workers_Request / Get_Workers_Response
# --------------------------------------------------------------------------


def build_get_workers_request_xml(employee_ids: list[str]) -> str:
    root = ET.Element(_tag("Get_Workers_Request"))
    root.set(f"{{{WD_NAMESPACE}}}version", WD_VERSION)
    request_references = _sub(root, "Request_References")
    for employee_id in employee_ids:
        _reference(request_references, "Worker_Reference", "Employee_ID", employee_id)
    return _to_xml_string(root)


def parse_get_workers_request_xml(xml_str: str) -> list[str]:
    root = ET.fromstring(xml_str)
    employee_ids = []
    for ref in root.findall(".//bsvc:Request_References/bsvc:Worker_Reference", NS):
        for id_el in ref.findall(f"{{{WD_NAMESPACE}}}ID"):
            if id_el.get(f"{{{WD_NAMESPACE}}}type") == "Employee_ID":
                employee_ids.append(id_el.text)
    return employee_ids


def build_get_workers_response_xml(workers: list[WorkerTemplate]) -> str:
    root = ET.Element(_tag("Get_Workers_Response"))
    root.set(f"{{{WD_NAMESPACE}}}version", WD_VERSION)
    response_data = _sub(root, "Response_Data")

    for worker in workers:
        worker_el = _sub(response_data, "Worker")
        _reference(
            worker_el,
            "Worker_Reference",
            "Employee_ID",
            worker.employee_id,
            descriptor=f"{worker.first_name} {worker.last_name}",
        )

        worker_data = _sub(worker_el, "Worker_Data")

        personal_data = _sub(worker_data, "Personal_Data")
        name_data = _sub(personal_data, "Name_Data")
        legal_name_data = _sub(name_data, "Legal_Name_Data")
        name_detail = _sub(legal_name_data, "Name_Detail_Data")
        _reference(name_detail, "Country_Reference", COUNTRY_ID_TYPE, worker.country)
        _sub(name_detail, "First_Name", worker.first_name)
        _sub(name_detail, "Last_Name", worker.last_name)

        contact_data = _sub(personal_data, "Contact_Data")
        email_data = _sub(contact_data, "Email_Address_Data")
        _sub(email_data, "Email_Address", worker.email)

        employment_data = _sub(worker_data, "Employment_Data")
        position_data = _sub(employment_data, "Position_Data")
        _reference(position_data, "Job_Profile_Reference", "Job_Profile_ID", worker.job_profile, descriptor=worker.job_profile)
        _sub(position_data, "Job_Family", worker.job_family)

        organization_data = _sub(worker_data, "Organization_Data")
        _reference(
            organization_data,
            "Supervisory_Organization_Reference",
            "Organization_Reference_ID",
            worker.supervisory_org,
            descriptor=worker.supervisory_org,
        )

    return _to_xml_string(root)


def parse_get_workers_response_xml(xml_str: str) -> list[WorkerTemplate]:
    root = ET.fromstring(xml_str)
    workers = []
    for worker_el in root.findall(".//bsvc:Worker", NS):
        employee_id = _find_id(worker_el, "bsvc:Worker_Reference", "Employee_ID")
        worker_data = worker_el.find("bsvc:Worker_Data", NS)
        name_detail = worker_data.find(".//bsvc:Legal_Name_Data/bsvc:Name_Detail_Data", NS)

        workers.append(
            WorkerTemplate(
                employee_id=employee_id or "",
                first_name=_find_text(name_detail, "bsvc:First_Name") or "",
                last_name=_find_text(name_detail, "bsvc:Last_Name") or "",
                email=_find_text(worker_data, ".//bsvc:Contact_Data/bsvc:Email_Address_Data/bsvc:Email_Address") or "",
                country=_find_id(name_detail, "bsvc:Country_Reference", COUNTRY_ID_TYPE) or "",
                job_profile=_find_id(worker_data, ".//bsvc:Position_Data/bsvc:Job_Profile_Reference", "Job_Profile_ID") or "",
                job_family=_find_text(worker_data, ".//bsvc:Position_Data/bsvc:Job_Family") or "",
                supervisory_org=_find_id(
                    worker_data, ".//bsvc:Organization_Data/bsvc:Supervisory_Organization_Reference", "Organization_Reference_ID"
                )
                or "",
            )
        )
    return workers


# --------------------------------------------------------------------------
# Hire_Employee_Request
# --------------------------------------------------------------------------


def build_hire_employee_request_xml(proposal: HireProposal) -> str:
    root = ET.Element(_tag("Hire_Employee_Request"))
    root.set(f"{{{WD_NAMESPACE}}}version", WD_VERSION)

    hire_data = _sub(root, "Hire_Employee_Data")

    applicant_data = _sub(hire_data, "Applicant_Data")
    personal_data = _sub(applicant_data, "Personal_Data")
    name_data = _sub(personal_data, "Name_Data")
    legal_name_data = _sub(name_data, "Legal_Name_Data")
    name_detail = _sub(legal_name_data, "Name_Detail_Data")
    _reference(name_detail, "Country_Reference", COUNTRY_ID_TYPE, proposal.country)
    _sub(name_detail, "First_Name", proposal.first_name)
    _sub(name_detail, "Last_Name", proposal.last_name)

    contact_data = _sub(personal_data, "Contact_Data")
    email_data = _sub(contact_data, "Email_Address_Data")
    _sub(email_data, "Email_Address", proposal.email)
    usage_data = _sub(email_data, "Usage_Data")
    type_data = _sub(usage_data, "Type_Data")
    _reference(type_data, "Type_Reference", "Communication_Usage_Type_ID", EMAIL_USAGE_TYPE_ID)

    _reference(hire_data, "Organization_Reference", "Organization_Reference_ID", proposal.supervisory_org)

    _sub(hire_data, "Hire_Date", proposal.hire_date)

    event_data = _sub(hire_data, "Hire_Employee_Event_Data")
    if proposal.employee_id:
        _sub(event_data, "Employee_ID", proposal.employee_id)
    if proposal.position_id:
        _sub(event_data, "Position_ID", proposal.position_id)
    position_details = _sub(event_data, "Position_Details")
    _reference(position_details, "Job_Profile_Reference", "Job_Profile_ID", proposal.job_profile)

    return _to_xml_string(root)


def parse_hire_employee_request_xml(xml_str: str) -> HireProposal:
    root = ET.fromstring(xml_str)
    name_detail = root.find(".//bsvc:Applicant_Data/bsvc:Personal_Data//bsvc:Name_Detail_Data", NS)
    email = root.find(".//bsvc:Applicant_Data/bsvc:Personal_Data//bsvc:Email_Address_Data/bsvc:Email_Address", NS)
    event_data = root.find(".//bsvc:Hire_Employee_Event_Data", NS)

    return HireProposal(
        first_name=_find_text(name_detail, "bsvc:First_Name") or "",
        last_name=_find_text(name_detail, "bsvc:Last_Name") or "",
        email=email.text if email is not None else "",
        country=_find_id(name_detail, "bsvc:Country_Reference", COUNTRY_ID_TYPE) or "",
        job_profile=_find_id(event_data, "bsvc:Position_Details/bsvc:Job_Profile_Reference", "Job_Profile_ID") or "",
        supervisory_org=_find_id(root, ".//bsvc:Hire_Employee_Data/bsvc:Organization_Reference", "Organization_Reference_ID") or "",
        hire_date=_find_text(root, ".//bsvc:Hire_Employee_Data/bsvc:Hire_Date") or "",
        employee_id=_find_text(event_data, "bsvc:Employee_ID"),
        position_id=_find_text(event_data, "bsvc:Position_ID"),
    )


# --------------------------------------------------------------------------
# Hire_Employee_Event_Response
# --------------------------------------------------------------------------


def build_hire_employee_event_response_xml(result: HireResult) -> str:
    root = ET.Element(_tag("Hire_Employee_Event_Response"))
    root.set(f"{{{WD_NAMESPACE}}}version", WD_VERSION)

    if result.success:
        _reference_multi(
            root,
            "Employee_Reference",
            [("Employee_ID", result.employee_id or ""), ("WID", result.wid or "")],
        )

    if result.exceptions:
        exceptions_response = _sub(root, "Exceptions_Response_Data")
        exceptions_data = _sub(exceptions_response, "Exceptions_Data")
        for message in result.exceptions:
            exception_data = _sub(exceptions_data, "Exception_Data")
            _sub(exception_data, "Classification", "Error")
            _sub(exception_data, "Message", message)

    return _to_xml_string(root)


def parse_hire_employee_event_response_xml(xml_str: str) -> HireResult:
    root = ET.fromstring(xml_str)
    exceptions = [
        text
        for text in (
            _find_text(exc, "bsvc:Message") for exc in root.findall(".//bsvc:Exceptions_Data/bsvc:Exception_Data", NS)
        )
        if text
    ]

    employee_id = None
    wid = None
    for ref in root.findall("bsvc:Employee_Reference", NS):
        for id_el in ref.findall(f"{{{WD_NAMESPACE}}}ID"):
            id_type = id_el.get(f"{{{WD_NAMESPACE}}}type")
            if id_type == "Employee_ID":
                employee_id = id_el.text
            elif id_type == "WID":
                wid = id_el.text

    return HireResult(
        success=not exceptions and employee_id is not None,
        employee_id=employee_id,
        wid=wid,
        exceptions=exceptions,
    )
