import csv
import logging
import os

import requests

from config import (
    ADZUNA_APP_ID,
    ADZUNA_APP_KEY,
    ADZUNA_COUNTRY_CODE,
    DEFAULT_FALLBACK_CSV,
    JOB_LOCATION_QUERY,
    JOB_ROLE_QUERY,
    MAX_ADZUNA_PAGES,
    RESULTS_PER_PAGE,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def _normalize_job(job: dict, source: str = "adzuna") -> dict:
    company = job.get("company", "")
    location = job.get("location", "")
    return {
        "source": source,
        "job_id": str(job.get("id") or job.get("job_id") or "").strip(),
        "title": (job.get("title") or "").strip(),
        "company": (company.get("display_name", "") if isinstance(company, dict) else company or "").strip(),
        "location": (location.get("display_name", "") if isinstance(location, dict) else location or "").strip(),
        "description": (job.get("description") or "").strip(),
        "url": (job.get("redirect_url") or job.get("url") or job.get("link") or "").strip(),
    }


def load_jobs_from_csv(csv_path: str = DEFAULT_FALLBACK_CSV) -> list:
    """Load jobs from a CSV file when the live API is unavailable."""
    if not csv_path or not os.path.exists(csv_path):
        return []

    jobs = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            jobs.append(
                _normalize_job(
                    {
                        "job_id": row.get("job_id", ""),
                        "title": row.get("title", ""),
                        "company": row.get("company", ""),
                        "location": row.get("location", ""),
                        "description": row.get("description", ""),
                        "url": row.get("url", "") or row.get("link", ""),
                    },
                    source=row.get("source", "csv"),
                )
            )

    logging.info("Loaded %s jobs from CSV fallback: %s.", len(jobs), csv_path)
    return jobs


def fetch_adzuna_jobs(
    app_id=ADZUNA_APP_ID,
    app_key=ADZUNA_APP_KEY,
    what=JOB_ROLE_QUERY,
    where=JOB_LOCATION_QUERY,
    max_pages=MAX_ADZUNA_PAGES,
    country_code=ADZUNA_COUNTRY_CODE,
    fallback_csv=DEFAULT_FALLBACK_CSV,
):
    """Fetch job postings from Adzuna API and return normalized job dictionaries."""
    jobs = []
    if not app_id or not app_key:
        logging.warning("Adzuna credentials are missing. Falling back to CSV jobs if available.")
        return load_jobs_from_csv(fallback_csv)

    base_url = f"https://api.adzuna.com/v1/api/jobs/{country_code}/search"

    for page in range(1, max_pages + 1):
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": RESULTS_PER_PAGE,
            "what": what,
        }
        if where:
            params["where"] = where

        try:
            response = requests.get(f"{base_url}/{page}", params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            for job in data.get("results", []):
                jobs.append(_normalize_job(job))

            if not data.get("results"):
                break

        except requests.RequestException as error:
            logging.error("Adzuna request failed on page %s: %s", page, error)
            break

    if jobs:
        logging.info("Fetched %s jobs from Adzuna.", len(jobs))
        return jobs

    logging.warning("No jobs fetched from Adzuna. Falling back to CSV jobs if available.")
    return load_jobs_from_csv(fallback_csv)


def normalize_location(location: str) -> str:
    return (location or "").strip().lower()


def filter_jobs_by_location(jobs: list, preferred_locations: list) -> list:
    """Keep only jobs whose location matches the preferred location list."""
    preferred = [location.lower() for location in preferred_locations]
    filtered = []

    for job in jobs:
        normalized = normalize_location(job.get("location", ""))
        if any(pref in normalized for pref in preferred):
            filtered.append(job)

    logging.info("Filtered jobs by location: %s remain after location filter.", len(filtered))
    return filtered
