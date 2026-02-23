# BFS queue, HTTP fetching, rate limiting, retry
"""
Async crawler for SEC EDGAR.

Unlike a generic web crawler that follows HTML links, this crawler uses
the structured data.sec.gov JSON API as its primary navigation source.
This is more reliable than link-following because EDGAR's API provides
a clean, paginated index of every filing — no need to parse navigation HTML.

Crawl flow:
1. Resolve ticker → CIK via EDGAR company search API
2. Fetch company metadata from data.sec.gov/submissions/CIK{id}.json
3. Filter filings by type (10-K, 10-Q, 8-K, etc.) and date range
4. For each filing: fetch the filing index page, identify the primary document
5. Yield (company_metadata, filing_metadata, document_html) to the pipeline

Concurrency:
An asyncio.Semaphore limits concurrent HTTP requests to MAX_CONCURRENT_REQUESTS
(default: 5). A per-request delay of CRAWL_DELAY_SECONDS (default: 0.5s)
provides additional politeness on top of the semaphore.

SEC fair-use guideline: no more than 10 requests/second.
This project defaults stay well within that at ~2 requests/second peak.
"""

from __future__ import annotations

import asyncio
import logging
import re
from itertools import zip_longest
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import AsyncIterator, Optional
from urllib.parse import urljoin, urlparse

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from scraper.config import settings

logger = logging.getLogger(__name__)

EDGAR_BASE_URL = "https://www.sec.gov"
EDGAR_DATA_URL = "https://data.sec.gov"

# company submissions endpoint >> returns metadata + full filing history
SUBMISSIONS_URL = f"{EDGAR_DATA_URL}/submissions/CIK{{cik}}.json"

# company ticker >> CIK lookup
TICKER_SEARCH_URL = f"{EDGAR_DATA_URL}/submissions/lookup/ticker/{{ticker}}.json"

# filing index page
FILING_INDEX_URL = f"{EDGAR_BASE_URL}/cgi-bin/browse-edgar?action=getcompany&CIK={{cik}}&type={{filing_type}}&dateb=&owner=include&count=40&search_text="

# archives base (filing documents live here)
ARCHIVES_BASE = f"{EDGAR_BASE_URL}/Archives/edgar/data"

SUPPORTED_FILING_TYPES = {
    "10-K": "annual_report",
    "10-Q": "quarterly_report",
    "8-K": "current_report",
    "DEF 14A": "proxy_statement",
    "20-F": "annual_report_fpi for foreign private issuers", 
    "6-K": "current_report_fpi for foreign private issuers",
}

# extensions this project skip (binary, structured data, or non-content files)
SKIP_EXTENSIONS = {".xsd", ".xml", ".xbrl", ".zip", ".pdf", ".gif",
                   ".jpg", ".jpeg", ".png", ".css", ".js", ".json"}


@dataclass
class CompanyMeta:
    cik: str
    name: str
    tickers: list[str] = field(default_factory=list)
    exchanges: list[str] = field(default_factory=list)
    sic_code: Optional[str] = None
    sic_description: Optional[str] = None
    state_of_inc: Optional[str] = None
    fiscal_year_end: Optional[str] = None
    entity_type: Optional[str] = None


@dataclass
class FilingMeta:
    accession_number: str # e.g. "0000320193-23-000077"
    filing_type: str # e.g. "10-K"
    filing_date: date
    period_of_report: Optional[date]
    primary_document: Optional[str] # filename of the main document
    primary_doc_url: Optional[str] # full URL to fetch


@dataclass
class CrawlResult:
    company: CompanyMeta
    filing: FilingMeta
    url: str
    html: str
    http_status: int
    fetched_at: datetime
    last_modified: Optional[datetime] = None


def build_http_client() -> httpx.AsyncClient:
    """
    Build a configured httpx async client.
    """
    return httpx.AsyncClient(
        headers={
            "User-Agent": settings.sec_user_agent,
            "Accept-Encoding": "gzip, deflate",
        },
        timeout=httpx.Timeout(
            connect=10.0, # connection timeout
            read=settings.request_timeout_seconds, # read timeout
            write=10.0, # write timeout
            pool=5.0, # pool timeout
        ),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )



# Retry decorator for transient network errors
def _make_retry_decorator():
    """
    3 attempts.
    Retries on network errors and 5xx responses via httpx.HTTPStatusError.
    Does NOT retry 4xx because those are permanent failures.
    """
    return retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )

with_retry = _make_retry_decorator()

async def resolve_cik(identifier: str, client: httpx.AsyncClient) -> str:
    """
    Resolve a ticker symbol or raw CIK string to a zero-padded 10-digit CIK.
    identifier: ticker symbol (e.g. "AAPL") or raw CIK (e.g. "320193")
    Returns Zero-padded 10-digit CIK string
    """
    if identifier.isdigit():
        return identifier.zfill(10)

    ticker = identifier.upper()
    response = await client.get("https://www.sec.gov/files/company_tickers.json")
    response.raise_for_status()
    data = response.json()

    for entry in data.values():
        if entry["ticker"] == ticker:
            return str(entry["cik_str"]).zfill(10)

    raise ValueError(f"Ticker '{ticker}' not found in SEC EDGAR")


async def fetch_company_meta(cik: str, client: httpx.AsyncClient) -> CompanyMeta:
    url = SUBMISSIONS_URL.format(cik=cik)
    logger.info(f"Fetching company metadata for CIK {cik}")

    response = await client.get(url)
    response.raise_for_status()
    data = response.json()

    tickers = data.get("tickers", [])
    exchanges = data.get("exchanges", [])

    return CompanyMeta(
        cik=cik,
        name=data.get("name", ""),
        tickers=tickers if isinstance(tickers, list) else [tickers],
        exchanges=exchanges if isinstance(exchanges, list) else [exchanges],
        sic_code=str(data.get("sic", "")) or None,
        sic_description=data.get("sicDescription") or None,
        state_of_inc=data.get("stateOfIncorporation") or None,
        fiscal_year_end=data.get("fiscalYearEnd") or None,
        entity_type=data.get("entityType") or None,
    )


def extract_filings(
    submissions_data: dict,
    filing_types: list[str],
    max_filings: int,
    cik: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[FilingMeta]:
    """
    The submissions API returns filings as a columnar dict:
        {
          "accessionNumber": ["0000320193-23-000077", ...],
          "form": ["10-K", ...],
          "filingDate": ["2023-11-03", ...],
          ...
        }

    Zip these columns into rows and filter by type and date.

    submissions_data: Raw JSON from data.sec.gov/submissions/CIK*.json
    filing_types: e.g. ["10-K", "10-Q"]
    max_filings: total cap across all types
    date_from: only include filings on or after this date
    date_to: only include filings on or before this date

    Returns a list of FilingMeta, most recent first, up to max_filings
    """
    recent = submissions_data.get("filings", {}).get("recent", {})
    if not recent:
        logger.warning("No recent filings found in submissions data")
        return []

    # zip columnar arrays into rows
    accessions = recent.get("accessionNumber", [])
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    periods = recent.get("reportDate", recent.get("periodOfReport", []))
    cik_clean = cik.lstrip("0") or "0" 
    primary_docs = recent.get("primaryDocument", [])         # ← use company CIK, not accession prefix
    filings: list[FilingMeta] = []

    for i, (accession, form, filing_date_str, period_str, primary_doc) in enumerate(
        zip_longest(accessions, forms, filing_dates, periods, primary_docs, fillvalue="")
    ):
        # match filing type
        if form not in filing_types:
            continue

        # parse dates
        try:
            filing_date = date.fromisoformat(filing_date_str)
        except (ValueError, TypeError):
            logger.warning(f"Could not parse filing date '{filing_date_str}', skipping")
            continue

        # apply date range filters
        if date_from and filing_date < date_from:
            continue
        if date_to and filing_date > date_to:
            continue

        period_of_report: Optional[date] = None
        if period_str:
            try:
                period_of_report = date.fromisoformat(period_str)
            except (ValueError, TypeError):
                pass

        # build the URL to the primary document
        accession_normalised = accession.replace("-", "")
        accession_formatted = f"{accession_normalised[:10]}-{accession_normalised[10:12]}-{accession_normalised[12:]}"
        cik_clean = cik.lstrip("0") or "0" # company CIK
        primary_doc_url: Optional[str] = None
        if primary_doc:
            primary_doc_url = (
                f"{ARCHIVES_BASE}/{cik_clean}/"
                f"{accession_normalised}/{primary_doc}"
            )

        filings.append(FilingMeta(
            accession_number=accession_formatted,
            filing_type=form,
            filing_date=filing_date,
            period_of_report=period_of_report,
            primary_document=primary_doc,
            primary_doc_url=primary_doc_url,
        ))

        if len(filings) >= max_filings:
            break

    # check for foreign private issuer forms
    all_forms = set(forms)
    fpi_forms = all_forms & {"20-F", "6-K", "40-F"}
    if fpi_forms:
        logger.warning(
            f"No '{filing_types}' filings found for CIK {cik}. "
            f"This may be a foreign private issuer — found these form types instead: {fpi_forms}. "
            f"Try --filing-types {' '.join(fpi_forms)}"
        )

    logger.info(f"Found {len(filings)} filings matching filters")
    return filings


@with_retry
async def fetch_document(
    url: str,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
) -> tuple[str, int, Optional[datetime]]:
    """
    url: Full URL of the document to fetch
    client: Shared httpx async client
    semaphore: Shared concurrency limiter

    Returns a tuple of (html_text, http_status, last_modified_datetime)

    Raises:
        httpx.HTTPStatusError: on 4xx/5xx after retries exhausted
        httpx.TransportError: on network failure after retries exhausted
    """
    async with semaphore:
        logger.debug(f"Fetching {url}")
        response = await client.get(url)

        # raise immediately on 4xx and won't retry
        # raise on 5xx and will retry
        response.raise_for_status()

        # parse Last-Modified header if present
        last_modified: Optional[datetime] = None
        lm_header = response.headers.get("last-modified")
        if lm_header:
            try:
                last_modified = datetime.strptime(lm_header, "%a, %d %b %Y %H:%M:%S %Z")
            except ValueError:
                pass

        html = response.text
        status = response.status_code

        # politeness delay after each successful request
        await asyncio.sleep(settings.crawl_delay_seconds)

        return html, status, last_modified


def is_valid_document_url(url: str) -> bool:
    """
    Check if a URL points to a content document worth fetching.
    """
    parsed = urlparse(url)

    # must be on sec.gov
    if "sec.gov" not in parsed.netloc:
        return False

    path = parsed.path.lower()

    # skip by extension
    if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
        return False

    # skip navigation pages
    skip_paths = [
        "/cgi-bin/browse-edgar",
        "/cgi-bin/viewer",
        "/cgi-bin/viewer.cgi",
        "/cgi-bin/browse-edgar?action=getcompany",
    ]
    if any(path.startswith(sp) for sp in skip_paths):
        return False

    return True


def normalise_url(url: str, base_url: str) -> str:
    """Resolve relative URLs against a base and strip fragments."""
    resolved = urljoin(base_url, url)
    # strip URL fragment (#section-anchor) — same page, different anchor
    return resolved.split("#")[0]


# Crawler
class EDGARCrawler:
    """
    Orchestrates the full crawl pipeline for one or more companies.
    """

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
        # track seen URLs within a run to avoid re-fetching
        self._seen_urls: set[str] = set()

    async def __aenter__(self) -> "EDGARCrawler":
        self._client = build_http_client()
        return self

    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("EDGARCrawler must be used as an async context manager")
        return self._client

    async def crawl(
        self,
        identifiers: list[str],
        filing_types: list[str],
        max_filings: int = 10,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> AsyncIterator[CrawlResult]:
        """
        Async generator that yields CrawlResult for each successfully
        fetched document across all companies and filing types.

        Errors are logged and skipped — a single bad URL never stops the run.

        identifiers: List of tickers (e.g. ["AAPL"]) or CIKs (e.g. ["0000320193"])
        filing_types: SEC form types to include (e.g. ["10-K", "10-Q"])
        max_filings: Max filings per company (not total)
        date_from: Earliest filing date to include
        date_to: Latest filing date to include

        It yields CrawlResult for each successfully fetched document
        """
        # validate filing types
        unknown_types = set(filing_types) - set(SUPPORTED_FILING_TYPES)
        if unknown_types:
            logger.warning(
                f"Unsupported filing types will be skipped: {unknown_types}. "
                f"Supported: {list(SUPPORTED_FILING_TYPES)}"
            )
            filing_types = [ft for ft in filing_types if ft in SUPPORTED_FILING_TYPES]

        for identifier in identifiers:
            async for result in self._crawl_company(
                identifier=identifier,
                filing_types=filing_types,
                max_filings=max_filings,
                date_from=date_from,
                date_to=date_to,
            ):
                yield result

    async def _crawl_company(
        self,
        identifier: str,
        filing_types: list[str],
        max_filings: int,
        date_from: Optional[date],
        date_to: Optional[date],
    ) -> AsyncIterator[CrawlResult]:
        # step 1: resolve identifier >> CIK
        try:
            cik = await resolve_cik(identifier, self.client)
        except (ValueError, httpx.HTTPError) as e:
            logger.error(f"Could not resolve '{identifier}' to a CIK: {e}")
            return

        # step 2: fetch company metadata and filing list
        try:
            response = await self.client.get(SUBMISSIONS_URL.format(cik=cik))
            response.raise_for_status()
            submissions_data = response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch submissions for CIK {cik}: {e}")
            return

        company = CompanyMeta(
            cik=cik,
            name=submissions_data.get("name", ""),
            tickers=submissions_data.get("tickers", []),
            exchanges=submissions_data.get("exchanges", []),
            sic_code=str(submissions_data.get("sic", "")) or None,
            sic_description=submissions_data.get("sicDescription") or None,
            state_of_inc=submissions_data.get("stateOfIncorporation") or None,
            fiscal_year_end=submissions_data.get("fiscalYearEnd") or None,
            entity_type=submissions_data.get("entityType") or None,
        )
        logger.info(f"Crawling {company.name} (CIK: {cik})")

        # step 3: filter filings
        filings = extract_filings(
            submissions_data=submissions_data,
            filing_types=filing_types,
            max_filings=max_filings,
            cik=cik,
            date_from=date_from,
            date_to=date_to,
        )

        if not filings:
            logger.warning(f"No matching filings found for {company.name}")
            return

        # step 4: fetch each filing document concurrently
        tasks = [
            self._fetch_filing(company=company, filing=filing)
            for filing in filings
            if filing.primary_doc_url # skip if no doc url
        ]

        # yield result
        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result is not None:
                yield result

    async def _fetch_filing(
        self,
        company: CompanyMeta,
        filing: FilingMeta,
    ) -> Optional[CrawlResult]:
        """
        Fetch one filing document. 
        Returns None on any error (logged but not raised).
        """
        url = filing.primary_doc_url
        if not url:
            return None

        # skip if the url was already fetched in this run
        if url in self._seen_urls:
            logger.debug(f"Skipping already-seen URL: {url}")
            return None

        if not is_valid_document_url(url):
            logger.debug(f"Skipping non-content URL: {url}")
            return None

        self._seen_urls.add(url)

        try:
            html, status, last_modified = await fetch_document(
                url=url,
                client=self.client,
                semaphore=self._semaphore,
            )

            logger.info(
                f"✓ Fetched {filing.filing_type} for {company.name} "
                f"({filing.period_of_report}) — {len(html):,} chars"
            )

            return CrawlResult(
                company=company,
                filing=filing,
                url=url,
                html=html,
                http_status=status,
                fetched_at=datetime.utcnow(),
                last_modified=last_modified,
            )

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP {e.response.status_code} fetching {url} "
                f"({company.name} {filing.filing_type}): {e}"
            )
            return None

        except (httpx.TransportError, httpx.TimeoutException) as e:
            logger.error(f"Network error fetching {url}: {e}")
            return None

        except Exception as e:
            logger.exception(f"Unexpected error fetching {url}: {e}")
            return None
