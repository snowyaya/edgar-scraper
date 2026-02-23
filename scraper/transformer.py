"""
Transforms a ParsedPage into a fully enriched AIDocument ready for storage.

Computes all AI-relevant signals: word counts, reading time, language
detection, content type classification, quality score, and tag generation.

Quality score (0.0–1.0)
------------------------
  Component           Weight  Signal
  ──────────────────  ──────  ─────────────────────────────────────────────
  Length adequacy       30%   word_count ≥ 500 → 1.0, scales linearly below
  Language confidence   25%   langdetect probability for detected language
  Content density       25%   body_text chars / raw HTML chars
  Structure richness    20%   min(section_count / 5, 1.0)

Transparent and re-weightable — downstream systems can adjust weights or
replace the score entirely without re-scraping.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from scraper.crawler import CompanyMeta, FilingMeta
from scraper.parser import ParsedPage, ParsedSection

logger = logging.getLogger(__name__)


READING_WPM = 238 # average adult reading speed (words per minute)
MIN_WORDS_FULL_SCORE = 500  # word count threshold for full length score

# maps SEC filing type to content_type vocabulary used in the document schema
FILING_TYPE_TO_CONTENT_TYPE: dict[str, str] = {
    "10-K":    "annual_report",
    "10-Q":    "quarterly_report",
    "8-K":     "current_report",
    "DEF 14A": "proxy_statement",
    "S-1":     "registration_statement",
    "20-F":    "annual_report",   # foreign private issuer equivalent of 10-K
    "6-K":     "current_report",  # foreign private issuer equivalent of 8-K
}

# maps SIC code ranges to sector tags, based on SEC's own SIC groupings
SIC_SECTOR_TAGS: list[tuple[range, str]] = [
    (range(100, 1000),   "agriculture"),
    (range(1000, 1500),  "mining"),
    (range(1500, 1800),  "construction"),
    (range(2000, 4000),  "manufacturing"),
    (range(4000, 5000),  "transportation"),
    (range(5000, 5200),  "wholesale-trade"),
    (range(5200, 6000),  "retail-trade"),
    (range(6000, 6800),  "finance"),
    (range(7000, 8000),  "services"),
    (range(7370, 7380),  "technology"),
    (range(8000, 9000),  "healthcare"),
    (range(9000, 10000), "public-administration"),
]


@dataclass
class AIDocumentSection:
    level: int
    heading: str
    body_text: str
    position: int
    word_count: int
    char_count: int
    sec_item: Optional[str] = None


@dataclass
class AIDocument:
    id: uuid.UUID
    content_hash: str # SHA-256 of body_text (dedup key)

    # provenance
    url: str
    canonical_url: str
    accession_number: Optional[str]
    http_status: int
    fetched_at: datetime
    last_modified: Optional[datetime]

    # filing classification
    filing_type: str
    filing_date: date
    period_of_report: Optional[date]
    fiscal_year: Optional[int]

    # company
    company: CompanyMeta

    # content
    title: str
    body_text: str
    headings: list[str]
    breadcrumbs: list[str]
    sections: list[AIDocumentSection]

    # enrichment signals
    word_count: int
    char_count: int
    reading_time_minutes: float
    language: str
    content_type: str
    code_ratio: float
    has_tables: bool
    table_count: int
    link_count: int
    quality_score: float

    # taxonomy
    tags: list[str]
    depth_in_site: int

    schema_version: int = 1


def _compute_content_hash(body_text: str) -> str:
    """
    SHA-256 of cleaned body text — used as the idempotency key.

    Documents with identical content are silently skipped on re-runs via
    ON CONFLICT DO NOTHING. Hashing body_text (not the URL) handles cases
    where the same filing is accessible at multiple URLs.
    """
    return hashlib.sha256(body_text.encode("utf-8")).hexdigest()


def _detect_language(text: str) -> tuple[str, float]:
    """
    Detect primary language. Returns (language_code, confidence).
    Samples the first 5k chars for speed. Falls back to ("en", 0.0).
    """
    try:
        from langdetect import detect_langs
        results = detect_langs(text[:5000])
        if results:
            best = results[0]
            return best.lang, round(best.prob, 4)
    except Exception as e:
        logger.debug(f"Language detection failed: {e}")

    return "en", 0.0


def _classify_content_type(filing_type: str) -> str:
    """Map SEC filing type to content_type vocabulary. Falls back to 'other'."""
    return FILING_TYPE_TO_CONTENT_TYPE.get(filing_type, "other")


def _compute_code_ratio(code_char_count: int, total_char_count: int) -> float:
    """Fraction of body text inside <pre>/<code> blocks. Near-zero for SEC filings."""
    if total_char_count == 0:
        return 0.0
    return round(min(code_char_count / total_char_count, 1.0), 4)


def _compute_quality_score(
    word_count: int,
    lang_confidence: float,
    raw_char_count: int,
    total_char_count: int,
    section_count: int,
) -> float:
    """
    Composite quality score (0.0–1.0). See module docstring for component weights.
    Raw signals are stored alongside the score so downstream systems can
    re-weight without re-scraping.
    """
    length_score = 1.0 if word_count >= MIN_WORDS_FULL_SCORE else word_count / MIN_WORDS_FULL_SCORE
    lang_score = lang_confidence
    density_score = min(total_char_count / max(raw_char_count, 1), 1.0) if raw_char_count > 0 else 0.0
    structure_score = min(section_count / 5.0, 1.0)  # 5+ sections = full score

    quality = (
        0.30 * length_score
        + 0.25 * lang_score
        + 0.25 * density_score
        + 0.20 * structure_score
    )
    return round(min(quality, 1.0), 4)


def _derive_fiscal_year(period_of_report: Optional[date]) -> Optional[int]:
    """Extract fiscal year from period_of_report (calendar year of period end date)."""
    return period_of_report.year if period_of_report else None


def _compute_depth_in_site(url: str) -> int:
    """Count meaningful path segments as a proxy for document depth in the site."""
    from urllib.parse import urlparse
    path = urlparse(url).path
    return len([s for s in path.split("/") if s])


def _generate_tags(
    filing_type: str,
    sic_code: Optional[str],
    sections: list[AIDocumentSection],
) -> list[str]:
    """
    Generate faceted search tags from structured metadata.

    Derived purely from filing type, SIC code, and detected SEC items —
    no free-text NLP. Tags serve as search dimensions and training data
    categories for downstream AI workflows.
    """
    tags: list[str] = []

    content_type = FILING_TYPE_TO_CONTENT_TYPE.get(filing_type)
    if content_type:
        tags.append(content_type.replace("_", "-"))
    tags.append(filing_type.lower().replace(" ", "-"))

    # SIC-based sector tag
    if sic_code and sic_code.isdigit():
        sic_int = int(sic_code)
        for sic_range, sector_tag in SIC_SECTOR_TAGS:
            if sic_int in sic_range:
                tags.append(sector_tag)
                break

    # SEC item tags derived from detected sections
    sec_items_found = {s.sec_item for s in sections if s.sec_item}
    for item in sec_items_found:
        tags.append(item.replace("_", "-"))

    # semantic content tags for common AI retrieval targets
    if "item_1a" in sec_items_found:
        tags.append("risk-factors")
    if "item_7" in sec_items_found or "item_2_10q" in sec_items_found:
        tags.append("mda")
    if "item_8" in sec_items_found or "item_1_10q" in sec_items_found:
        tags.append("financial-statements")

    # deduplicate while preserving order
    seen: set[str] = set()
    unique_tags: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)

    return unique_tags


def _transform_sections(parsed_sections: list[ParsedSection]) -> list[AIDocumentSection]:
    """Convert ParsedSection list to AIDocumentSection list with word/char counts."""
    result = []
    for s in parsed_sections:
        body = s.body_text or ""
        result.append(AIDocumentSection(
            level=s.level,
            heading=s.heading,
            body_text=body,
            position=s.position,
            word_count=len(body.split()),
            char_count=len(body),
            sec_item=s.sec_item,
        ))
    return result


def transform(page: ParsedPage) -> Optional[AIDocument]:
    """
    Transform a ParsedPage into a fully enriched AIDocument.
    Returns None if the document is below the minimum word count threshold.
    """
    body_text = page.body_text
    word_count = len(body_text.split())
    char_count = len(body_text)

    if word_count < 50:
        logger.warning(f"Document too short ({word_count} words) at {page.url} — skipping")
        return None

    reading_time_minutes = round(word_count / READING_WPM, 2)
    language, lang_confidence = _detect_language(body_text)
    content_type = _classify_content_type(page.filing.filing_type)
    code_ratio = _compute_code_ratio(
        code_char_count=page.code_char_count,
        total_char_count=char_count,
    )
    sections = _transform_sections(page.sections)
    quality_score = _compute_quality_score(
        word_count=word_count,
        lang_confidence=lang_confidence,
        raw_char_count=page.raw_char_count,
        total_char_count=len(page.body_text),
        section_count=len(sections),
    )
    content_hash = _compute_content_hash(body_text)
    tags = _generate_tags(
        filing_type=page.filing.filing_type,
        sic_code=page.company.sic_code,
        sections=sections,
    )
    fiscal_year = _derive_fiscal_year(page.filing.period_of_report)

    logger.info(
        f"Transformed {page.filing.filing_type} for {page.company.name} | "
        f"words={word_count:,} quality={quality_score:.2f} lang={language} "
        f"sections={len(sections)} tags={tags}"
    )

    return AIDocument(
        id=uuid.uuid4(),
        content_hash=content_hash,
        url=page.url,
        canonical_url=page.url,
        accession_number=page.filing.accession_number,
        http_status=page.http_status,
        fetched_at=page.fetched_at,
        last_modified=page.last_modified,
        filing_type=page.filing.filing_type,
        filing_date=page.filing.filing_date,
        period_of_report=page.filing.period_of_report,
        fiscal_year=fiscal_year,
        company=page.company,
        title=page.title,
        body_text=body_text,
        headings=page.headings,
        breadcrumbs=page.breadcrumbs,
        sections=sections,
        word_count=word_count,
        char_count=char_count,
        reading_time_minutes=reading_time_minutes,
        language=language,
        content_type=content_type,
        code_ratio=code_ratio,
        has_tables=page.table_count > 0,
        table_count=page.table_count,
        link_count=page.link_count,
        quality_score=quality_score,
        tags=tags,
        depth_in_site=_compute_depth_in_site(page.url),
    )
