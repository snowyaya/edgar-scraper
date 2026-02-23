"""
Persists AIDocument objects to PostgreSQL with full idempotency.

Two-level dedup:
1. URL-level (in-memory, per-run): skip already-seen URLs before fetching
2. Content-level (DB, cross-run): INSERT ... ON CONFLICT (content_hash) DO NOTHING

Companies are upserted by CIK before document insertion to satisfy the FK constraint.
All write operations increment CrawlRun progress counters atomically.
"""

from __future__ import annotations

import logging
import traceback
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.crawler import CompanyMeta
from scraper.db import AsyncSessionFactory, Company, CrawlError, CrawlRun, Document, DocumentSection
from scraper.transformer import AIDocument, AIDocumentSection

logger = logging.getLogger(__name__)


async def create_run(
    ciks: list[str],
    filing_types: list[str],
    max_filings: int,
    config: Optional[dict] = None,
) -> uuid.UUID:
    async with AsyncSessionFactory() as session:
        run = CrawlRun(
            status="running",
            start_ciks=ciks,
            filing_types=filing_types,
            max_filings=max_filings,
            config=config or {},
        )
        session.add(run)
        await session.flush() # get run_id without committing
        run_id = run.run_id
        await session.commit()

    logger.info(f"Created crawl run {run_id}")
    return run_id


async def finish_run(
    run_id: uuid.UUID,
    status: str,
    error_summary: Optional[str] = None,
) -> None:
    async with AsyncSessionFactory() as session:
        await session.execute(
            update(CrawlRun)
            .where(CrawlRun.run_id == run_id)
            .values(
                status=status,
                finished_at=datetime.utcnow(),
                error_summary=error_summary,
            )
        )
        await session.commit()

    logger.info(f"Finished run {run_id} with status '{status}'")


async def increment_run_counter(run_id: uuid.UUID, counter: str) -> None:
    """Atomically increment a CrawlRun progress counter via raw SQL to avoid read-modify-write races."""
    valid_counters = {"pages_crawled", "pages_saved", "pages_skipped", "pages_errored"}
    if counter not in valid_counters:
        raise ValueError(f"Invalid counter: {counter}. Must be one of {valid_counters}")

    async with AsyncSessionFactory() as session:
        await session.execute(
            text(f"UPDATE crawl_runs SET {counter} = {counter} + 1 WHERE run_id = :run_id"),
            {"run_id": run_id},
        )
        await session.commit()


async def load_seen_urls() -> set[str]:
    async with AsyncSessionFactory() as session:
        result = await session.execute(select(Document.url))
        urls = {row[0] for row in result.fetchall()}

    logger.info(f"Loaded {len(urls):,} existing URLs for dedup")
    return urls


async def upsert_company(company: CompanyMeta, session: AsyncSession) -> int:
    """Upsert company by CIK, updating mutable fields (name, tickers) if changed. Returns PK id."""
    stmt = pg_insert(Company).values(
        cik=company.cik,
        name=company.name,
        tickers=company.tickers or [],
        exchanges=company.exchanges or [],
        sic_code=company.sic_code,
        sic_description=company.sic_description,
        state_of_inc=company.state_of_inc,
        fiscal_year_end=company.fiscal_year_end,
        entity_type=company.entity_type,
    ).on_conflict_do_update(
        index_elements=["cik"],
        set_={
            "name": company.name,
            "tickers": company.tickers or [],
            "exchanges": company.exchanges or [],
            "sic_description": company.sic_description,
            "updated_at": datetime.utcnow(),
        },
    ).returning(Company.id)

    result = await session.execute(stmt)
    company_id: int = result.scalar_one()
    return company_id


async def write_document(
    doc: AIDocument,
    run_id: uuid.UUID,
    seen_urls: set[str],
) -> bool:
    """
    Persist a single AIDocument and its sections in one transaction.
    Returns True if inserted, False if skipped (duplicate URL or content hash).
    """
    # URL-level dedup check (in-memory, avoids a DB round-trip)
    if doc.url in seen_urls:
        logger.debug(f"Skipping already-seen URL: {doc.url}")
        await increment_run_counter(run_id, "pages_skipped")
        return False

    async with AsyncSessionFactory() as session:
        async with session.begin():
            # step 1: upsert company and get its FK id
            company_id = await upsert_company(doc.company, session)

            # step 2: insert document with ON CONFLICT DO NOTHING (content_hash)
            doc_stmt = pg_insert(Document).values(
                id=doc.id,
                content_hash=doc.content_hash,
                run_id=run_id,
                company_id=company_id,
                url=doc.url,
                canonical_url=doc.canonical_url,
                accession_number=doc.accession_number,
                http_status=doc.http_status,
                fetched_at=doc.fetched_at,
                last_modified=doc.last_modified,
                filing_type=doc.filing_type,
                filing_date=doc.filing_date,
                period_of_report=doc.period_of_report,
                fiscal_year=doc.fiscal_year,
                title=doc.title,
                body_text=doc.body_text,
                headings=doc.headings,
                breadcrumbs=doc.breadcrumbs,
                word_count=doc.word_count,
                char_count=doc.char_count,
                reading_time_minutes=doc.reading_time_minutes,
                language=doc.language,
                content_type=doc.content_type,
                code_ratio=doc.code_ratio,
                has_tables=doc.has_tables,
                table_count=doc.table_count,
                link_count=doc.link_count,
                quality_score=doc.quality_score,
                tags=doc.tags,
                depth_in_site=doc.depth_in_site,
                schema_version=doc.schema_version,
            ).on_conflict_do_nothing(
                index_elements=["content_hash"]
            ).returning(Document.id)

            result = await session.execute(doc_stmt)
            inserted_id = result.scalar_one_or_none()

            if inserted_id is None:
                # content hash conflict — duplicate document, silently skip
                logger.debug(
                    f"Duplicate content hash for {doc.url} — skipping sections"
                )
                seen_urls.add(doc.url)
                await increment_run_counter(run_id, "pages_skipped")
                return False

            # step 3: bulk insert all sections
            if doc.sections:
                sections_data = [
                    {
                        "document_id": inserted_id,
                        "level": s.level,
                        "heading": s.heading,
                        "body_text": s.body_text,
                        "position": s.position,
                        "word_count": s.word_count,
                        "char_count": s.char_count,
                        "sec_item": s.sec_item,
                    }
                    for s in doc.sections
                ]
                await session.execute(
                    pg_insert(DocumentSection),
                    sections_data,
                )

    # update dedup cache and run counters
    seen_urls.add(doc.url)
    await increment_run_counter(run_id, "pages_saved")
    await increment_run_counter(run_id, "pages_crawled")

    logger.info(
        f"✓ Saved {doc.filing_type} — {doc.company.name} "
        f"({doc.period_of_report}) | {doc.word_count:,} words | "
        f"quality={doc.quality_score:.2f} | {len(doc.sections)} sections"
    )
    return True


async def log_error(
    run_id: uuid.UUID,
    url: str,
    error_type: str,
    message: str,
    http_status: Optional[int] = None,
    exc: Optional[Exception] = None,
) -> None:
    """Write a per-page error to crawl_errors and increment pages_errored. Never raises."""

    stack_trace = traceback.format_exc() if exc else None

    async with AsyncSessionFactory() as session:
        error = CrawlError(
            run_id=run_id,
            url=url,
            error_type=error_type,
            http_status=http_status,
            message=message,
            stack_trace=stack_trace,
        )
        session.add(error)
        await session.commit()

    await increment_run_counter(run_id, "pages_errored")
    logger.error(f"[{error_type}] {url}: {message}")
