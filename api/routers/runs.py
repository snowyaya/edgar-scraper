"""
Crawler run management endpoints.

GET  /api/runs
GET  /api/runs/{run_id}
POST /api/runs
GET  /api/runs/{run_id}/errors
"""

from __future__ import annotations

import asyncio
import logging
import sys
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import get_db
from api.models import (
    CrawlErrorSchema,
    PaginatedErrors,
    RunCreate,
    RunCreateResponse,
    RunDetail,
    RunSummary,
)
from scraper.db import CrawlError, CrawlRun

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=list[RunSummary])
async def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None, description="Filter by status"),
    db: AsyncSession = Depends(get_db),
) -> list[RunSummary]:
    """
    List all crawls, sorted by crawled time
    """
    stmt = select(CrawlRun).order_by(CrawlRun.started_at.desc())

    if status:
        stmt = stmt.where(CrawlRun.status == status)

    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    runs = result.scalars().all()

    return [RunSummary.model_validate(run) for run in runs]


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> RunDetail:
    """Full detail for a single crawl run including configuration snapshot."""
    result = await db.execute(
        select(CrawlRun).where(CrawlRun.run_id == run_id)
    )
    run = result.scalar_one_or_none()

    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return RunDetail.model_validate(run)


async def _run_scraper_subprocess(
    run_id: str,
    identifiers: list[str],
    id_type: str,
    filing_types: list[str],
    max_filings: int,
    date_from: str | None,
    date_to: str | None,
) -> None:
    """
    Trigger a new run of the scraper as a subprocess.
    Passing parameters via command-line args.
    """
    logger.info(f"_run_scraper_subprocess called: run_id={run_id}, identifiers={identifiers}, id_type={id_type}")
    try:
        cmd = [
            sys.executable, "-m", "scraper.main",
            "--run-id", run_id,
            f"--{id_type}", *identifiers,
            "--filing-types", *filing_types,
            "--max-filings", str(max_filings),
        ]
        if date_from:
            cmd += ["--date-from", date_from]
        if date_to:
            cmd += ["--date-to", date_to]

        logger.info(f"Launching scraper subprocess: {' '.join(cmd)}")
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await process.communicate()
        if process.returncode != 0:
            logger.error(f"Scraper subprocess failed (exit {process.returncode}):\n{stdout.decode()}")
        else:
            logger.info(f"Scraper subprocess completed successfully")
    except Exception as e:
        logger.exception(f"_run_scraper_subprocess FAILED: {e}")


@router.post("", response_model=RunCreateResponse, status_code=202)
async def create_run(
    body: RunCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> RunCreateResponse:
    """
    Trigger a new crawl run asynchronously.
    Either `tickers` or `ciks` must be provided (not both and not neither).
    """
    # validate exactly one of tickers/ciks must be provided
    if not body.tickers and not body.ciks:
        raise HTTPException(
            status_code=422,
            detail="Provide either 'tickers' or 'ciks' (not both and not neither)",
        )
    if body.tickers and body.ciks:
        raise HTTPException(
            status_code=422,
            detail="Provide either 'tickers' or 'ciks', not both",
        )

    identifiers = body.tickers or body.ciks or []
    id_type = "tickers" if body.tickers else "ciks"

    # create the run record immediately so the client has a run_id to poll
    from scraper.writer import create_run as _create_run
    run_id = await _create_run(
        ciks=identifiers,
        filing_types=body.filing_types,
        max_filings=body.max_filings,
        config={
            "id_type": id_type,
            "date_from": body.date_from.isoformat() if body.date_from else None,
            "date_to": body.date_to.isoformat() if body.date_to else None,
            "triggered_via": "api",
        },
    )

    # schedule the actual crawl as a background task
    background_tasks.add_task(
        _run_scraper_subprocess,
        run_id=str(run_id),
        identifiers=identifiers,
        id_type=id_type,
        filing_types=body.filing_types,
        max_filings=body.max_filings,
        date_from=body.date_from.isoformat() if body.date_from else None,
        date_to=body.date_to.isoformat() if body.date_to else None,
    )

    logger.info(f"Accepted crawl run {run_id} for {identifiers}")

    return RunCreateResponse(
        run_id=run_id,
        status="running",
        message=f"Crawl started for {identifiers}. Poll GET /api/runs/{run_id} for status.",
    )


@router.get("/{run_id}/errors", response_model=PaginatedErrors)
async def list_run_errors(
    run_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    error_type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> PaginatedErrors:
    """Paginated error log for a specific crawl run."""
    # first, verify run exists
    run_exists = await db.execute(
        select(CrawlRun.run_id).where(CrawlRun.run_id == run_id)
    )
    if run_exists.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # count total errors
    error_count_stmt = select(func.count(CrawlError.id)).select_from(CrawlError).where(
        CrawlError.run_id == run_id
    )
    if error_type:
        error_count_stmt = error_count_stmt.where(CrawlError.error_type == error_type)

    total = await db.scalar(error_count_stmt) or 0

    # fetch page and return results
    error_query_stmt = select(CrawlError).where(CrawlError.run_id == run_id).order_by(CrawlError.occurred_at.desc())
    if error_type:
        error_query_stmt = error_query_stmt.where(CrawlError.error_type == error_type)

    error_query_stmt = error_query_stmt.limit(limit).offset(offset)
    result = await db.execute(error_query_stmt)
    errors = result.scalars().all()

    return PaginatedErrors(
        total=total,
        limit=limit,
        offset=offset,
        items=[CrawlErrorSchema.model_validate(e) for e in errors],
    )
