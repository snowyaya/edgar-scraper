"""
API response schemas, separate from the SQLAlchemy models in scraper/db.py.
This separation lets the API shape evolve independently of the DB schema,
excludes internal fields (stack traces, raw HTML), and enables automatic
OpenAPI documentation via FastAPI.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

class APIModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,   # read from SQLAlchemy objects
        populate_by_name=True,  # allow field population by alias or name
    )


class CompanyInDocument(APIModel):
    """Minimal company info embedded in document responses int GET /api/documents)"""
    cik: str
    name: str
    tickers: Optional[list[str]] = None
    sic_code: Optional[str] = None
    sic_description: Optional[str] = None


class CompanySummary(APIModel):
    """Company listing item in GET /api/companies"""
    id: int
    cik: str
    name: str
    tickers: Optional[list[str]] = None
    exchanges: Optional[list[str]] = None
    sic_code: Optional[str] = None
    sic_description: Optional[str] = None
    state_of_inc: Optional[str] = None
    fiscal_year_end: Optional[str] = None
    first_seen_at: datetime


class CompanyDetail(CompanySummary):
    entity_type: Optional[str] = None
    document_count: int = 0
    filing_types: list[str] = Field(default_factory=list)


class DocumentSectionSchema(APIModel):
    id: int
    level: int
    heading: str
    body_text: Optional[str] = None
    position: int
    word_count: Optional[int] = None
    char_count: Optional[int] = None
    sec_item: Optional[str] = None


class DocumentSummary(APIModel):
    """
    A lightweight document shape for list responses.
    body_text and sections are only in DocumentDetail.
    """
    id: UUID
    url: str
    accession_number: Optional[str] = None
    filing_type: Optional[str] = None
    filing_date: Optional[date] = None
    period_of_report: Optional[date] = None
    fiscal_year: Optional[int] = None
    title: Optional[str] = None
    word_count: Optional[int] = None
    char_count: Optional[int] = None
    reading_time_minutes: Optional[float] = None
    language: Optional[str] = None
    content_type: Optional[str] = None
    quality_score: Optional[float] = None
    has_tables: Optional[bool] = None
    table_count: Optional[int] = None
    tags: Optional[list[str]] = None
    fetched_at: datetime
    company: Optional[CompanyInDocument] = None


class DocumentDetail(DocumentSummary):
    body_text: str
    headings: Optional[list[str]] = None
    breadcrumbs: Optional[list[str]] = None
    code_ratio: Optional[float] = None
    link_count: Optional[int] = None
    depth_in_site: Optional[int] = None
    schema_version: int = 1
    last_modified: Optional[datetime] = None
    http_status: Optional[int] = None
    canonical_url: Optional[str] = None
    sections: list[DocumentSectionSchema] = Field(default_factory=list)


class PaginatedDocuments(APIModel):
    """Standard paginated response for document lists."""
    total: int
    limit: int
    offset: int
    items: list[DocumentSummary]


class RunSummary(APIModel):
    run_id: UUID
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str
    filing_types: Optional[list[str]] = None
    pages_crawled: int
    pages_saved: int
    pages_skipped: int
    pages_errored: int


class RunDetail(RunSummary):
    start_ciks: Optional[list[str]] = None
    max_filings: Optional[int] = None
    config: Optional[dict] = None
    error_summary: Optional[str] = None


class RunCreate(BaseModel):
    tickers: Optional[list[str]] = Field(
        default=None,
        description="Ticker symbols to scrape (e.g. ['AAPL', 'AMZN'])",
    )
    ciks: Optional[list[str]] = Field(
        default=None,
        description="SEC CIK numbers to scrape (e.g. ['0000320193'])",
    )
    filing_types: list[str] = Field(
        default=["10-K"],
        description="SEC form types to collect",
    )
    max_filings: int = Field(
        default=10,
        ge=1,
        le=1000,
        description="Max filings per company",
    )
    date_from: Optional[date] = Field(
        default=None,
        description="Only include filings on or after this date",
    )
    date_to: Optional[date] = Field(
        default=None,
        description="Only include filings on or before this date",
    )


class RunCreateResponse(APIModel):
    run_id: UUID
    status: str
    message: str


class CrawlErrorSchema(APIModel):
    id: int
    url: str
    error_type: Optional[str] = None
    http_status: Optional[int] = None
    message: Optional[str] = None
    occurred_at: datetime


class PaginatedErrors(APIModel):
    total: int
    limit: int
    offset: int
    items: list[CrawlErrorSchema]


class OverviewStats(APIModel):
    total_documents: int
    total_companies: int
    total_runs: int
    avg_quality_score: Optional[float] = None
    avg_word_count: Optional[float] = None
    total_words: Optional[int] = None
    last_crawled_at: Optional[datetime] = None


class FilingTypeStats(APIModel):
    filing_type: str
    document_count: int
    avg_quality_score: Optional[float] = None
    avg_word_count: Optional[float] = None


class LanguageStats(APIModel):
    language: str
    document_count: int
    percentage: float


class QualityBucket(APIModel):
    bucket_start: float   # e.g. 0.7
    bucket_end: float     # e.g. 0.8
    count: int


class TimelinePoint(APIModel):
    date: date
    documents_saved: int
    companies: int


class TopCompany(APIModel):
    cik: str
    name: str
    tickers: Optional[list[str]] = None
    document_count: int
    avg_quality_score: Optional[float] = None
    total_words: Optional[int] = None
    filing_types: list[str] = Field(default_factory=list)


class ReadingTimeDistribution(APIModel):
    bucket_label: str
    count: int


class ExportParams(BaseModel):
    filing_type: Optional[str] = None
    language: Optional[str] = None
    quality_min: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    company_cik: Optional[str] = None
    fiscal_year: Optional[int] = None
