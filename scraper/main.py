from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from scraper.config import settings
from scraper.crawler import EDGARCrawler, SUPPORTED_FILING_TYPES
from scraper.parser import parse
from scraper.transformer import transform
from scraper import writer

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Quiet down noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("charset_normalizer").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# CLI entry point to orchestrate the full crawl pipeline
def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scraper.main",
        description="SEC EDGAR AI Scraping Pipeline — crawls, parses, enriches, and stores filings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
            Examples:
            # Single company, last 5 annual reports
            python -m scraper.main --tickers AAPL --filing-types 10-K --max-filings 5

            # Multiple companies, multiple types
            python -m scraper.main --tickers AAPL AMZN MSFT --filing-types 10-K 10-Q --max-filings 20

            # Using CIKs directly
            python -m scraper.main --ciks 0000320193 0001018724 --filing-types 10-K

            # With date range and JSONL export
            python -m scraper.main --tickers AAPL --date-from 2020-01-01 --output output/edgar.jsonl
        """,
    )

    company_group = parser.add_mutually_exclusive_group(required=True)
    company_group.add_argument(
        "--tickers",
        nargs="+",
        metavar="TICKER",
        help="One or more ticker symbols (e.g. AAPL AMZN MSFT)",
    )
    company_group.add_argument(
        "--ciks",
        nargs="+",
        metavar="CIK",
        help="One or more SEC CIK numbers (e.g. 0000320193)",
    )

    parser.add_argument(
        "--run-id",
        default=None,
        metavar="UUID",
        help="Pre-created run ID to resume (used when triggered via API)",
    )

    parser.add_argument(
        "--filing-types",
        nargs="+",
        default=["10-K", "10-Q", "8-K"],
        choices=list(SUPPORTED_FILING_TYPES.keys()),
        metavar="TYPE",
        help=f"Filing types to collect. Choices: {list(SUPPORTED_FILING_TYPES.keys())}. Default: 10-K, 10-Q, 8-K",
    )

    parser.add_argument(
        "--max-filings",
        type=int,
        default=10,
        metavar="N",
        help="Maximum filings to fetch per company (default: 10)",
    )

    parser.add_argument(
        "--date-from",
        type=date.fromisoformat,
        default=None,
        metavar="YYYY-MM-DD",
        help="Only include filings on or after this date",
    )
    parser.add_argument(
        "--date-to",
        type=date.fromisoformat,
        default=None,
        metavar="YYYY-MM-DD",
        help="Only include filings on or before this date",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="PATH",
        help="Also write output as JSONL to this path (e.g. output/edgar.jsonl)",
    )

    parser.add_argument(
        "--log-level",
        default=settings.log_level,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help=f"Log verbosity (default: {settings.log_level})",
    )

    return parser


def document_to_dict(doc) -> dict:
    return {
        "id": str(doc.id),
        "content_hash": doc.content_hash,
        "schema_version": doc.schema_version,
        "url": doc.url,
        "accession_number": doc.accession_number,
        "company": {
            "cik": doc.company.cik,
            "name": doc.company.name,
            "tickers": doc.company.tickers,
            "sic_code": doc.company.sic_code,
            "sic_description": doc.company.sic_description,
        },
        "filing_type": doc.filing_type,
        "filing_date": doc.filing_date.isoformat() if doc.filing_date else None,
        "period_of_report": doc.period_of_report.isoformat() if doc.period_of_report else None,
        "fiscal_year": doc.fiscal_year,
        "fetched_at": doc.fetched_at.isoformat(),
        "title": doc.title,
        "body_text": doc.body_text,
        "headings": doc.headings,
        "sections": [
            {
                "level": s.level,
                "heading": s.heading,
                "body_text": s.body_text,
                "position": s.position,
                "word_count": s.word_count,
                "sec_item": s.sec_item,
            }
            for s in doc.sections
        ],
        "word_count": doc.word_count,
        "char_count": doc.char_count,
        "reading_time_minutes": float(doc.reading_time_minutes),
        "language": doc.language,
        "content_type": doc.content_type,
        "quality_score": float(doc.quality_score),
        "has_tables": doc.has_tables,
        "table_count": doc.table_count,
        "tags": doc.tags,
    }


async def run_pipeline(
    identifiers: list[str],
    filing_types: list[str],
    max_filings: int,
    date_from: Optional[date],
    date_to: Optional[date],
    output_path: Optional[Path],
    run_id: Optional[str] = None,
) -> None:
    """
    The full crawl pipeline: crawler → parser → transformer → writer
    """
    if run_id is None:
        # CLI path: create the run record here as before
        run_id = await writer.create_run(
            ciks=identifiers,
            filing_types=filing_types,
            max_filings=max_filings,
            config={
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
                "output_path": str(output_path) if output_path else None,
                "triggered_via": "cli",
            },
        )
    
    logger.info(f"Started run {run_id}")

    # load existing URLs for in-memory dedup
    seen_urls = await writer.load_seen_urls()

    # prepare optional JSONL output file
    jsonl_file = None
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        jsonl_file = open(output_path, "a", encoding="utf-8")
        logger.info(f"Writing JSONL to {output_path}")

    saved = 0
    skipped = 0
    errored = 0

    try:
        async with EDGARCrawler() as crawler:
            async for crawl_result in crawler.crawl(
                identifiers=identifiers,
                filing_types=filing_types,
                max_filings=max_filings,
                date_from=date_from,
                date_to=date_to,
            ):
                # stage 1: parse HTML >> ParsedPage
                try:
                    parsed = parse(crawl_result)
                except Exception as e:
                    await writer.log_error(
                        run_id=run_id,
                        url=crawl_result.url,
                        error_type="parse_error",
                        message=str(e),
                        exc=e,
                    )
                    errored += 1
                    continue

                if parsed is None:
                    await writer.log_error(
                        run_id=run_id,
                        url=crawl_result.url,
                        error_type="empty_content",
                        message="Parser returned None — insufficient content",
                    )
                    skipped += 1
                    continue

                # stage 2: transform ParsedPage >> AIDocument
                try:
                    doc = transform(parsed)
                except Exception as e:
                    await writer.log_error(
                        run_id=run_id,
                        url=crawl_result.url,
                        error_type="transform_error",
                        message=str(e),
                        exc=e,
                    )
                    errored += 1
                    continue

                if doc is None:
                    skipped += 1
                    continue

                # stage 3: write to PostgreSQL
                try:
                    was_saved = await writer.write_document(
                        doc=doc,
                        run_id=run_id,
                        seen_urls=seen_urls,
                    )
                    if was_saved:
                        saved += 1
                        # stage 4 (optional): write to JSONL
                        if jsonl_file:
                            jsonl_file.write(json.dumps(document_to_dict(doc)) + "\n")
                            jsonl_file.flush()
                    else:
                        skipped += 1

                except Exception as e:
                    await writer.log_error(
                        run_id=run_id,
                        url=crawl_result.url,
                        error_type="write_error",
                        message=str(e),
                        exc=e,
                    )
                    errored += 1
                    continue

        # determine final run status
        if errored == 0:
            status = "completed"
        elif saved > 0:
            status = "partial"
        else:
            status = "failed"

        await writer.finish_run(run_id=run_id, status=status)

    except Exception as e:
        logger.exception(f"Fatal error in pipeline: {e}")
        await writer.finish_run(
            run_id=run_id,
            status="failed",
            error_summary=str(e),
        )
        raise

    finally:
        if jsonl_file:
            jsonl_file.close()

    # summary
    logger.info(
        f"\n{'='*50}\n"
        f"Run {run_id} complete\n"
        f"  Saved:   {saved}\n"
        f"  Skipped: {skipped}\n"
        f"  Errored: {errored}\n"
        f"  Status:  {status}\n"
        f"{'='*50}"
    )


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    setup_logging(args.log_level)

    identifiers = args.tickers or args.ciks

    logger.info(
        f"SEC EDGAR Scraper starting\n"
        f"  Companies:    {identifiers}\n"
        f"  Filing types: {args.filing_types}\n"
        f"  Max filings:  {args.max_filings} per company\n"
        f"  Date range:   {args.date_from} → {args.date_to or 'now'}\n"
    )

    asyncio.run(
        run_pipeline(
            identifiers=identifiers,
            filing_types=args.filing_types,
            max_filings=args.max_filings,
            date_from=args.date_from,
            date_to=args.date_to,
            output_path=args.output,
            run_id=args.run_id,
        )
    )


if __name__ == "__main__":
    main()
