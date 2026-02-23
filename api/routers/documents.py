"""
Documents API endpoints for browsing and retrieving scraped filings.

GET /api/documents              — paginated list with 8+ filter dimensions
GET /api/documents/{id}         — full document detail including sections
GET /api/documents/{id}/sections — sections only (RAG chunking endpoint)
GET /api/export                 — stream filtered corpus as JSONL
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import Float, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from api.db import get_db
from api.models import (
    CompanyInDocument,
    DocumentDetail,
    DocumentSectionSchema,
    DocumentSummary,
    PaginatedDocuments,
)
from scraper.db import Company, Document, DocumentSection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])


# ---------------------------------------------------------------------------
# Shared filter builder
# ---------------------------------------------------------------------------

def _apply_document_filters(
    stmt,
    company_cik: str | None,
    filing_type: str | None,
    fiscal_year: int | None,
    language: str | None,
    content_type: str | None,
    quality_min: float | None,
    quality_max: float | None,
    search: str | None,
    tags: list[str] | None,
):
    """
    All document filters are applied to a SQLAlchemy select statement.
    """
    if company_cik:
        stmt = stmt.join(Company, Document.company_id == Company.id).where(
            Company.cik == company_cik
        )

    if filing_type:
        stmt = stmt.where(Document.filing_type == filing_type)

    if fiscal_year:
        stmt = stmt.where(Document.fiscal_year == fiscal_year)

    if language:
        stmt = stmt.where(Document.language == language)

    if content_type:
        stmt = stmt.where(Document.content_type == content_type)

    if quality_min is not None:
        stmt = stmt.where(Document.quality_score >= quality_min)

    if quality_max is not None:
        stmt = stmt.where(Document.quality_score <= quality_max)

    if search:
        # use GIN index on documents(title + body_text) for full-text search        
        ts_query = func.plainto_tsquery("english", search)
        ts_vector = func.to_tsvector(
            "english",
            func.coalesce(Document.title, "") + " " + func.coalesce(Document.body_text, ""),
        )
        stmt = stmt.where(ts_vector.op("@@")(ts_query))

    if tags:
        # match documents that contain ALL specified tags (AND logic)
        for tag in tags:
            stmt = stmt.where(Document.tags.contains([tag]))

    return stmt


SORT_COLUMNS = {
    "quality_score": Document.quality_score,
    "word_count": Document.word_count,
    "fetched_at": Document.fetched_at,
    "filing_date": Document.filing_date,
    "reading_time_minutes": Document.reading_time_minutes,
}


# ---------------------------------------------------------------------------
# List documents
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedDocuments)
async def list_documents(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),

    # Filters
    company_cik: str | None = Query(default=None, description="Filter by company CIK"),
    filing_type: str | None = Query(default=None, description="e.g. '10-K', '10-Q', '8-K'"),
    fiscal_year: int | None = Query(default=None, description="e.g. 2023"),
    language: str | None = Query(default=None, description="ISO 639-1 code, e.g. 'en'"),
    content_type: str | None = Query(default=None, description="e.g. 'annual_report'"),
    quality_min: float | None = Query(default=None, ge=0.0, le=1.0),
    quality_max: float | None = Query(default=None, ge=0.0, le=1.0),
    search: str | None = Query(default=None, description="Full-text search across title + body"),
    tags: list[str] | None = Query(default=None, description="Filter by tags (AND logic)"),
    
    # Sorting
    sort: str = Query(default="fetched_at", description="Sort field"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedDocuments:
    """
    Paginated document listing with filtering and sorting.
    """
    # count query for total results (before pagination)
    count_stmt = select(func.count()).select_from(Document)
    count_stmt = _apply_document_filters(
        count_stmt, company_cik, filing_type, fiscal_year,
        language, content_type, quality_min, quality_max, search, tags,
    )
    total = await db.scalar(count_stmt) or 0

    # data query with filters, sorting, and pagination
    stmt = select(Document).options(joinedload(Document.company))
    stmt = _apply_document_filters(
        stmt, company_cik, filing_type, fiscal_year,
        language, content_type, quality_min, quality_max, search, tags,
    )

    # sort
    sort_col = SORT_COLUMNS.get(sort, Document.fetched_at)
    if order == "desc":
        stmt = stmt.order_by(sort_col.desc().nulls_last())
    else:
        stmt = stmt.order_by(sort_col.asc().nulls_last())

    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    documents = result.scalars().unique().all()

    items = []
    for doc in documents:
        summary = DocumentSummary.model_validate(doc)
        if doc.company:
            summary.company = CompanyInDocument.model_validate(doc.company)
        items.append(summary)

    return PaginatedDocuments(total=total, limit=limit, offset=offset, items=items)


# ---------------------------------------------------------------------------
# Document detail
# ---------------------------------------------------------------------------

@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DocumentDetail:
    """
    Full document detail including body_text and all sections.
    """
    result = await db.execute(
        select(Document)
        .options(
            joinedload(Document.company),
            selectinload(Document.sections),
        )
        .where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()

    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")

    detail = DocumentDetail.model_validate(doc)
    if doc.company:
        detail.company = CompanyInDocument.model_validate(doc.company)
    detail.sections = [DocumentSectionSchema.model_validate(s) for s in doc.sections]

    return detail


# ---------------------------------------------------------------------------
# Sections only (RAG endpoint)
# ---------------------------------------------------------------------------

@router.get("/{document_id}/sections", response_model=list[DocumentSectionSchema])
async def get_document_sections(
    document_id: UUID,
    sec_item: str | None = Query(
        default=None,
        description="Filter by SEC item (e.g. 'item_1a', 'item_7')",
    ),
    min_words: int | None = Query(
        default=None,
        description="Only return sections with at least this many words",
    ),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentSectionSchema]:
    """
    Return sections for a document — the primary RAG chunking endpoint.
    """
    doc_exists = await db.execute(
        select(Document.id).where(Document.id == document_id)
    )
    if doc_exists.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")

    stmt = (
        select(DocumentSection)
        .where(DocumentSection.document_id == document_id)
        .order_by(DocumentSection.position)
    )

    if sec_item:
        stmt = stmt.where(DocumentSection.sec_item == sec_item)

    if min_words:
        stmt = stmt.where(DocumentSection.word_count >= min_words)

    result = await db.execute(stmt)
    sections = result.scalars().all()

    return [DocumentSectionSchema.model_validate(s) for s in sections]


# ---------------------------------------------------------------------------
# JSONL export (streaming)
# ---------------------------------------------------------------------------

async def _stream_jsonl(
    db: AsyncSession,
    company_cik: str | None,
    filing_type: str | None,
    fiscal_year: int | None,
    language: str | None,
    content_type: str | None,
    quality_min: float | None,
) -> AsyncGenerator[str, None]:
    """
    Async generator that streams documents as JSONL lines.
    """
    stmt = select(Document).options(joinedload(Document.company))
    stmt = _apply_document_filters(
        stmt, company_cik, filing_type, fiscal_year,
        language, content_type, quality_min, None, None, None,
    )
    stmt = stmt.order_by(Document.fetched_at.desc())

    result = await db.stream(stmt)

    async for partition in result.partitions(50):
        for row in partition:
            doc = row[0]
            record = {
                "id": str(doc.id),
                "content_hash": doc.content_hash,
                "schema_version": doc.schema_version,
                "url": doc.url,
                "accession_number": doc.accession_number,
                "company": {
                    "cik": doc.company.cik if doc.company else None,
                    "name": doc.company.name if doc.company else None,
                    "tickers": doc.company.tickers if doc.company else [],
                    "sic_code": doc.company.sic_code if doc.company else None,
                } if doc.company else None,
                "filing_type": doc.filing_type,
                "filing_date": doc.filing_date.isoformat() if doc.filing_date else None,
                "period_of_report": doc.period_of_report.isoformat() if doc.period_of_report else None,
                "fiscal_year": doc.fiscal_year,
                "fetched_at": doc.fetched_at.isoformat(),
                "title": doc.title,
                "body_text": doc.body_text,
                "word_count": doc.word_count,
                "char_count": doc.char_count,
                "reading_time_minutes": float(doc.reading_time_minutes) if doc.reading_time_minutes else None,
                "language": doc.language,
                "content_type": doc.content_type,
                "quality_score": float(doc.quality_score) if doc.quality_score else None,
                "has_tables": doc.has_tables,
                "tags": doc.tags,
                "headings": doc.headings,
            }
            yield json.dumps(record, ensure_ascii=False) + "\n"


export_router = APIRouter(prefix="/api/export", tags=["export"])


@export_router.get("")
async def export_jsonl(
    company_cik: str | None = Query(default=None),
    filing_type: str | None = Query(default=None),
    fiscal_year: int | None = Query(default=None),
    language: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    quality_min: float | None = Query(default=None, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Stream the full corpus (or a filtered subset) as newline-delimited JSON.
    """
    return StreamingResponse(
        _stream_jsonl(
            db=db,
            company_cik=company_cik,
            filing_type=filing_type,
            fiscal_year=fiscal_year,
            language=language,
            content_type=content_type,
            quality_min=quality_min,
        ),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": "attachment; filename=edgar_corpus.jsonl",
            "X-Content-Type-Options": "nosniff",
        },
    )
