"""Shared constants for the mock Workday tenant and the MCP server.

Keeping these in one place means both sides of the wire (the mock tenant that
answers SOAP calls, and the MCP server that makes them) agree on the same
namespace, version, and reference-ID conventions without duplicating them.
"""

import logging
from pathlib import Path

WD_NAMESPACE = "urn:com.workday/bsvc"
WD_VERSION = "v45.0"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEVDATA_DIR = REPO_ROOT / "devdata"
WORKER_CSV_PATH = DEVDATA_DIR / "worker_list.csv"

MOCK_TENANT_HOST = "127.0.0.1"
MOCK_TENANT_PORT = 8000
MOCK_TENANT_BASE_URL = f"http://{MOCK_TENANT_HOST}:{MOCK_TENANT_PORT}"

RAAS_SEARCH_PATH = "/ccx/api/v1/tenant/search_workers"
SOAP_STAFFING_PATH = "/ccx/service/tenant/Staffing/v45.0"

EMAIL_USAGE_TYPE_ID = "WORK"
COUNTRY_ID_TYPE = "ISO_3166-1_Alpha-3_Code"


def configure_logging(level: int = logging.INFO) -> None:
    """Set up a consistent log format for both the mock tenant and the MCP server.

    Deliberately relies on logging's default stderr stream: the MCP server
    talks to its client over stdio, so anything written to stdout would
    corrupt the JSON-RPC protocol stream. stderr is safe for both processes.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
