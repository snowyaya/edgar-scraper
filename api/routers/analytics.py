"""
Analytics API endpoints for corpus insights and dashboard metrics.

- GET /api/analytics/overview
- GET /api/analytics/filing-types
- GET /api/analytics/languages
- GET /api/analytics/quality-histogram
- GET /api/analytics/timeline
- GET /api/analytics/top-companies
- GET /api/analytics/reading-time
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Integer, Numeric, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import get_db
from api.models import (
    FilingTypeStats,
    LanguageStats,
    OverviewStats,
    QualityBucket,
    ReadingTimeDistribution,
    TimelinePoint,
    TopCompany,
)
from scraper.db import Company, CrawlRun, Document


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["analytics"])

@router.get("/overview", response_model=OverviewStats)
async def get_overview(
    db: AsyncSession = Depends(get_db),
) -> OverviewStats:
    """
    Corpus statistics for the dashboard overview cards.
    Returns totals and averages across the entire document collection.
    """
    doc_stats = await db.execute(
        select(
            func.count(Document.id).label("total_documents"),
            func.avg(cast(Document.quality_score, Numeric)).label("avg_quality"),
            func.avg(cast(Document.word_count, Numeric)).label("avg_words"),
            func.sum(Document.word_count).label("total_words"),
            func.max(Document.fetched_at).label("last_crawled_at"),
        )
    )
    doc_row = doc_stats.one()

    total_companies = await db.scalar(
        select(func.count(Company.id))
    ) or 0

    total_runs = await db.scalar(
        select(func.count(CrawlRun.id))
    ) or 0

    return OverviewStats(
        total_documents=doc_row.total_documents or 0,
        total_companies=total_companies,
        total_runs=total_runs,
        avg_quality_score=round(float(doc_row.avg_quality), 4) if doc_row.avg_quality else None,
        avg_word_count=round(float(doc_row.avg_words), 1) if doc_row.avg_words else None,
        total_words=int(doc_row.total_words) if doc_row.total_words else None,
        last_crawled_at=doc_row.last_crawled_at,
    )


@router.get("/filing-types", response_model=list[FilingTypeStats])
async def get_filing_type_stats(
    db: AsyncSession = Depends(get_db),
) -> list[FilingTypeStats]:
    """
    Document count and quality metrics grouped by filing type.
    """
    result = await db.execute(
        select(
            Document.filing_type,
            func.count(Document.id).label("document_count"),
            func.avg(cast(Document.quality_score, Numeric)).label("avg_quality"),
            func.avg(cast(Document.word_count, Numeric)).label("avg_words"),
        )
        .where(Document.filing_type.isnot(None))
        .group_by(Document.filing_type)
        .order_by(func.count(Document.id).desc())
    )

    return [
        FilingTypeStats(
            filing_type=row.filing_type,
            document_count=row.document_count,
            avg_quality_score=round(float(row.avg_quality), 4) if row.avg_quality else None,
            avg_word_count=round(float(row.avg_words), 1) if row.avg_words else None,
        )
        for row in result.all()
    ]


@router.get("/languages", response_model=list[LanguageStats])
async def get_language_stats(
    db: AsyncSession = Depends(get_db),
) -> list[LanguageStats]:
    """
    Document count by detected language with percentage.
    """
    # Get total count for percentage calculation
    total = await db.scalar(select(func.count(Document.id))) or 1

    result = await db.execute(
        select(
            Document.language,
            func.count(Document.id).label("document_count"),
        )
        .where(Document.language.isnot(None))
        .group_by(Document.language)
        .order_by(func.count(Document.id).desc())
    )

    return [
        LanguageStats(
            language=row.language,
            document_count=row.document_count,
            percentage=round((row.document_count / total) * 100, 2),
        )
        for row in result.all()
    ]


@router.get("/quality-histogram", response_model=list[QualityBucket])
async def get_quality_histogram(
    buckets: int = Query(default=10, ge=2, le=20),
    db: AsyncSession = Depends(get_db),
) -> list[QualityBucket]:
    """
    Quality score (10 equal-width buckets from 0.0 to 1.0) distribution as a histogram.
    """
    bucket_size = 1.0 / buckets

    result = await db.execute(
        select(
            # Bucket index: floor(quality_score / bucket_size)
            func.floor(
                cast(Document.quality_score, Numeric) / bucket_size
            ).label("bucket"),
            func.count(Document.id).label("count"),
        )
        .where(Document.quality_score.isnot(None))
        .group_by(text("bucket"))
        .order_by(text("bucket"))
    )

    rows = result.all()

    # Build all buckets (including empty ones for a complete hisigram)
    bucket_counts: dict[int, int] = {row.bucket: row.count for row in rows}

    return [
        QualityBucket(
            bucket_start=round(i * bucket_size, 2),
            bucket_end=round(min((i + 1) * bucket_size, 1.0), 2),
            count=bucket_counts.get(i, 0),
        )
        for i in range(buckets)
    ]


@router.get("/timeline", response_model=list[TimelinePoint])
async def get_timeline(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> list[TimelinePoint]:
    """
    Documents saved per day for the last N days.
    """
    since = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(
            func.date_trunc("day", Document.fetched_at).label("day"),
            func.count(Document.id).label("documents_saved"),
            func.count(func.distinct(Document.company_id)).label("companies"),
        )
        .where(Document.fetched_at >= since)
        .group_by(text("day"))
        .order_by(text("day"))
    )

    return [
        TimelinePoint(
            date=row.day.date(),
            documents_saved=row.documents_saved,
            companies=row.companies,
        )
        for row in result.all()
    ]


@router.get("/top-companies", response_model=list[TopCompany])
async def get_top_companies(
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[TopCompany]:
    """
    Companies ranked by document count, with quality and word metrics.
    """
    result = await db.execute(
        select(
            Company.cik,
            Company.name,
            Company.tickers,
            func.count(Document.id).label("document_count"),
            func.avg(cast(Document.quality_score, Numeric)).label("avg_quality"),
            func.sum(Document.word_count).label("total_words"),
            func.array_agg(func.distinct(Document.filing_type)).label("filing_types"),
        )
        .join(Document, Document.company_id == Company.id)
        .group_by(Company.id, Company.cik, Company.name, Company.tickers)
        .order_by(func.count(Document.id).desc())
        .limit(limit)
    )

    return [
        TopCompany(
            cik=row.cik,
            name=row.name,
            tickers=row.tickers or [],
            document_count=row.document_count,
            avg_quality_score=round(float(row.avg_quality), 4) if row.avg_quality else None,
            total_words=int(row.total_words) if row.total_words else None,
            filing_types=[ft for ft in (row.filing_types or []) if ft],
        )
        for row in result.all()
    ]


@router.get("/reading-time", response_model=list[ReadingTimeDistribution])
async def get_reading_time_distribution(
    db: AsyncSession = Depends(get_db),
) -> list[ReadingTimeDistribution]:
    """
    Reading time distribution across the corpus.
    """
    buckets = [
        ("< 15 min",   0,    15),
        ("15–30 min",  15,   30),
        ("30–60 min",  30,   60),
        ("1–2 hours",  60,   120),
        ("2–4 hours",  120,  240),
        ("4+ hours",   240,  999999),
    ]

    results = []
    for label, min_mins, max_mins in buckets:
        count = await db.scalar(
            select(func.count(Document.id))
            .where(Document.reading_time_minutes.isnot(None))
            .where(cast(Document.reading_time_minutes, Numeric) >= min_mins)
            .where(cast(Document.reading_time_minutes, Numeric) < max_mins)
        ) or 0

        results.append(ReadingTimeDistribution(bucket_label=label, count=count))

    return results
