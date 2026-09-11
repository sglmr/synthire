"""Loads devdata/worker_list.csv, standing in for a Workday RaaS report."""

import csv

from .config import WORKER_CSV_PATH


def load_workers_csv() -> list[dict[str, str]]:
    with open(WORKER_CSV_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
