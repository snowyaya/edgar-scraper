#!/usr/bin/env python3
"""
Loads the JSONL output and prints a structured report covering:
  - Corpus size and volume
  - Filing type distribution
  - Language distribution
  - Quality score statistics and histogram
  - Company coverage
  - Reading time distribution
  - SEC item (section) coverage
  - Top/bottom documents by quality
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median, stdev
from typing import Optional


try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import print as rprint
    RICH = True
    console = Console()
except ImportError:
    RICH = False
    console = None


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_jsonl(path: Path, filing_type: Optional[str] = None) -> list[dict]:
    if not path.exists():
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        print("Run the scraper first: python -m scraper.main --tickers AAPL --output output/edgar.jsonl",
              file=sys.stderr)
        sys.exit(1)

    docs = []
    errors = 0

    with open(path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
                if filing_type and doc.get("filing_type") != filing_type:
                    continue
                docs.append(doc)
            except json.JSONDecodeError as e:
                errors += 1
                print(f"WARNING: Invalid JSON on line {line_num}: {e}", file=sys.stderr)

    if errors:
        print(f"WARNING: Skipped {errors} invalid lines", file=sys.stderr)

    return docs


# ---------------------------------------------------------------------------
# Calculate statistics
# ---------------------------------------------------------------------------

def compute_stats(docs: list[dict]) -> dict:
    """
    Calculate corpus statistics from a list of document dicts.
    Returns a nested dict for JSON export or display.
    """
    if not docs:
        return {"error": "No documents found"}

    word_counts = [d.get("word_count", 0) or 0 for d in docs]
    quality_scores = [d.get("quality_score", 0) or 0 for d in docs]
    reading_times = [d.get("reading_time_minutes", 0) or 0 for d in docs]
    char_counts = [d.get("char_count", 0) or 0 for d in docs]

    filing_types = Counter(d.get("filing_type", "unknown") for d in docs)

    languages = Counter(d.get("language", "unknown") for d in docs)

    content_types = Counter(d.get("content_type", "other") for d in docs)

    company_doc_counts: dict[str, int] = Counter()
    company_names: dict[str, str] = {}
    for doc in docs:
        company = doc.get("company") or {}
        cik = company.get("cik", "unknown")
        company_doc_counts[cik] += 1
        company_names[cik] = company.get("name", "Unknown")

    fiscal_years = Counter(
        d.get("fiscal_year") for d in docs if d.get("fiscal_year")
    )

    quality_buckets: dict[str, int] = defaultdict(int)
    for score in quality_scores:
        bucket_idx = min(int(score * 10), 9)
        label = f"{bucket_idx / 10:.1f}–{(bucket_idx + 1) / 10:.1f}"
        quality_buckets[label] += 1

    reading_time_buckets: dict[str, int] = defaultdict(int)
    for rt in reading_times:
        if rt < 15:
            reading_time_buckets["< 15 min"] += 1
        elif rt < 30:
            reading_time_buckets["15–30 min"] += 1
        elif rt < 60:
            reading_time_buckets["30–60 min"] += 1
        elif rt < 120:
            reading_time_buckets["1–2 hours"] += 1
        elif rt < 240:
            reading_time_buckets["2–4 hours"] += 1
        else:
            reading_time_buckets["4+ hours"] += 1

    sec_item_counts: Counter = Counter()
    for doc in docs:
        for section in doc.get("sections", []):
            item = section.get("sec_item")
            if item:
                sec_item_counts[item] += 1

    tag_counts: Counter = Counter()
    for doc in docs:
        for tag in doc.get("tags", []):
            tag_counts[tag] += 1

    # Sort documents by quality score for top/bottom examples
    sorted_by_quality = sorted(docs, key=lambda d: d.get("quality_score") or 0, reverse=True)
    top_docs = [
        {
            "title": d.get("title", "")[:60],
            "company": (d.get("company") or {}).get("name", ""),
            "filing_type": d.get("filing_type"),
            "quality_score": d.get("quality_score"),
            "word_count": d.get("word_count"),
        }
        for d in sorted_by_quality[:5]
    ]
    bottom_docs = [
        {
            "title": d.get("title", "")[:60],
            "company": (d.get("company") or {}).get("name", ""),
            "filing_type": d.get("filing_type"),
            "quality_score": d.get("quality_score"),
            "word_count": d.get("word_count"),
        }
        for d in sorted_by_quality[-5:]
    ]

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "corpus": {
            "total_documents": len(docs),
            "total_companies": len(company_doc_counts),
            "total_words": sum(word_counts),
            "total_chars": sum(char_counts),
        },
        "word_count": {
            "min": min(word_counts),
            "max": max(word_counts),
            "mean": round(mean(word_counts), 1),
            "median": round(median(word_counts), 1),
            "stdev": round(stdev(word_counts), 1) if len(word_counts) > 1 else 0,
        },
        "quality_score": {
            "min": round(min(quality_scores), 4),
            "max": round(max(quality_scores), 4),
            "mean": round(mean(quality_scores), 4),
            "median": round(median(quality_scores), 4),
            "stdev": round(stdev(quality_scores), 4) if len(quality_scores) > 1 else 0,
            "pct_above_0_7": round(
                sum(1 for s in quality_scores if s >= 0.7) / len(quality_scores) * 100, 1
            ),
            "pct_above_0_8": round(
                sum(1 for s in quality_scores if s >= 0.8) / len(quality_scores) * 100, 1
            ),
            "histogram": dict(sorted(quality_buckets.items())),
        },
        "reading_time": {
            "mean_minutes": round(mean(reading_times), 1),
            "median_minutes": round(median(reading_times), 1),
            "distribution": dict(reading_time_buckets),
        },
        "filing_types": dict(filing_types.most_common()),
        "content_types": dict(content_types.most_common()),
        "languages": dict(languages.most_common()),
        "fiscal_years": dict(sorted(fiscal_years.items(), reverse=True)),
        "top_companies": [
            {"cik": cik, "name": company_names[cik], "document_count": count}
            for cik, count in company_doc_counts.most_common(10)
        ],
        "sec_item_coverage": dict(sec_item_counts.most_common(15)),
        "top_tags": dict(tag_counts.most_common(15)),
        "top_docs_by_quality": top_docs,
        "bottom_docs_by_quality": bottom_docs,
    }


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _bar(value: int, max_value: int, width: int = 30) -> str:
    """Render an ASCII progress bar."""
    if max_value == 0:
        return " " * width
    filled = round((value / max_value) * width)
    return "█" * filled + "░" * (width - filled)


def print_report_plain(stats: dict) -> None:
    """Print a plain-text report (fallback when rich is not installed)."""
    sep = "─" * 60

    print(f"\n{'═' * 60}")
    print("  SEC EDGAR CORPUS ANALYTICS")
    print(f"  Generated: {stats['generated_at']}")
    print(f"{'═' * 60}\n")

    # Overview
    c = stats["corpus"]
    print("CORPUS OVERVIEW")
    print(sep)
    print(f"  Total documents : {c['total_documents']:>10,}")
    print(f"  Total companies : {c['total_companies']:>10,}")
    print(f"  Total words     : {c['total_words']:>10,}")
    print(f"  Total chars     : {c['total_chars']:>10,}")
    print()

    # Word counts
    w = stats["word_count"]
    print("WORD COUNT")
    print(sep)
    print(f"  Min    : {w['min']:>10,}")
    print(f"  Max    : {w['max']:>10,}")
    print(f"  Mean   : {w['mean']:>10,.1f}")
    print(f"  Median : {w['median']:>10,.1f}")
    print()

    # Quality score
    q = stats["quality_score"]
    print("QUALITY SCORE")
    print(sep)
    print(f"  Min    : {q['min']:.4f}")
    print(f"  Max    : {q['max']:.4f}")
    print(f"  Mean   : {q['mean']:.4f}")
    print(f"  Median : {q['median']:.4f}")
    print(f"  ≥ 0.70 : {q['pct_above_0_7']}%")
    print(f"  ≥ 0.80 : {q['pct_above_0_8']}%")
    print()

    # Quality histogram
    print("  Quality Histogram:")
    hist = stats["quality_score"]["histogram"]
    max_count = max(hist.values()) if hist else 1
    for bucket, count in sorted(hist.items()):
        bar = _bar(count, max_count, 25)
        print(f"    {bucket}  {bar}  {count:,}")
    print()

    # Filing types
    print("FILING TYPES")
    print(sep)
    ft = stats["filing_types"]
    max_ft = max(ft.values()) if ft else 1
    for ftype, count in ft.items():
        bar = _bar(count, max_ft, 25)
        print(f"  {ftype:<10}  {bar}  {count:,}")
    print()

    # Languages
    print("LANGUAGES")
    print(sep)
    langs = stats["languages"]
    total = sum(langs.values())
    for lang, count in langs.items():
        pct = count / total * 100
        print(f"  {lang:<8}  {count:>6,}  ({pct:.1f}%)")
    print()

    # Fiscal years
    print("FISCAL YEARS")
    print(sep)
    fy = stats["fiscal_years"]
    max_fy = max(fy.values()) if fy else 1
    for year, count in sorted(fy.items(), reverse=True)[:10]:
        bar = _bar(count, max_fy, 25)
        print(f"  {year}  {bar}  {count:,}")
    print()

    # Top companies
    print("TOP COMPANIES BY DOCUMENT COUNT")
    print(sep)
    for i, co in enumerate(stats["top_companies"], 1):
        print(f"  {i:>2}. {co['name']:<40} {co['document_count']:>4} docs")
    print()

    # SEC item coverage
    print("SEC ITEM COVERAGE (sections detected)")
    print(sep)
    for item, count in stats["sec_item_coverage"].items():
        print(f"  {item:<15}  {count:>6,}")
    print()

    # Top/bottom quality
    print("TOP 5 DOCUMENTS BY QUALITY")
    print(sep)
    for doc in stats["top_docs_by_quality"]:
        print(f"  [{doc['quality_score']:.2f}] {doc['company']:<25} {doc['filing_type']:<8} {doc['title'][:40]}")
    print()

    print("BOTTOM 5 DOCUMENTS BY QUALITY")
    print(sep)
    for doc in stats["bottom_docs_by_quality"]:
        print(f"  [{doc['quality_score']:.2f}] {doc['company']:<25} {doc['filing_type']:<8} {doc['title'][:40]}")
    print()


def print_report_rich(stats: dict) -> None:
    """Print a rich formatted report."""
    c = stats["corpus"]

    console.print()
    console.print(Panel.fit(
        f"[bold gold1]SEC EDGAR Corpus Analytics[/bold gold1]\n"
        f"[dim]{stats['generated_at']}[/dim]",
        border_style="dim",
    ))
    console.print()

    # Overview table
    overview = Table(title="Corpus Overview", show_header=False, box=None, padding=(0, 2))
    overview.add_column(style="dim")
    overview.add_column(style="bold white", justify="right")
    overview.add_row("Total Documents",  f"{c['total_documents']:,}")
    overview.add_row("Total Companies",  f"{c['total_companies']:,}")
    overview.add_row("Total Words",      f"{c['total_words']:,}")
    overview.add_row("Total Characters", f"{c['total_chars']:,}")
    console.print(overview)
    console.print()

    # Quality + word counts
    q = stats["quality_score"]
    w = stats["word_count"]

    qual_table = Table(title="Quality Score", show_header=False, box=None, padding=(0, 2))
    qual_table.add_column(style="dim")
    qual_table.add_column(style="green", justify="right")
    qual_table.add_row("Min",    f"{q['min']:.4f}")
    qual_table.add_row("Max",    f"{q['max']:.4f}")
    qual_table.add_row("Mean",   f"{q['mean']:.4f}")
    qual_table.add_row("Median", f"{q['median']:.4f}")
    qual_table.add_row("≥ 0.70", f"[bold]{q['pct_above_0_7']}%[/bold]")
    qual_table.add_row("≥ 0.80", f"[bold]{q['pct_above_0_8']}%[/bold]")
    console.print(qual_table)
    console.print()

    # Filing types
    ft_table = Table(title="Filing Type Distribution", padding=(0, 2))
    ft_table.add_column("Type", style="cyan bold", no_wrap=True)
    ft_table.add_column("Count", justify="right", style="white")
    ft_table.add_column("Bar", style="gold1")
    ft = stats["filing_types"]
    max_ft = max(ft.values()) if ft else 1
    for ftype, count in ft.items():
        ft_table.add_row(ftype, f"{count:,}", _bar(count, max_ft, 20))
    console.print(ft_table)
    console.print()

    # Languages
    lang_table = Table(title="Language Distribution", padding=(0, 2))
    lang_table.add_column("Language", style="cyan")
    lang_table.add_column("Count", justify="right")
    lang_table.add_column("Pct", justify="right", style="dim")
    total = sum(stats["languages"].values())
    for lang, count in stats["languages"].items():
        lang_table.add_row(lang, f"{count:,}", f"{count/total*100:.1f}%")
    console.print(lang_table)
    console.print()

    # Top companies
    co_table = Table(title="Top Companies", padding=(0, 2))
    co_table.add_column("#", style="dim", width=3)
    co_table.add_column("Company", style="white")
    co_table.add_column("CIK", style="dim")
    co_table.add_column("Docs", justify="right", style="gold1")
    for i, co in enumerate(stats["top_companies"], 1):
        co_table.add_row(str(i), co["name"], co["cik"], f"{co['document_count']:,}")
    console.print(co_table)
    console.print()

    # SEC item coverage
    sec_table = Table(title="SEC Item Coverage (sections detected)", padding=(0, 2))
    sec_table.add_column("Item", style="cyan")
    sec_table.add_column("Count", justify="right", style="white")
    for item, count in stats["sec_item_coverage"].items():
        sec_table.add_row(item, f"{count:,}")
    console.print(sec_table)
    console.print()

    # Top docs by quality
    top_table = Table(title="Top 5 Documents by Quality", padding=(0, 2))
    top_table.add_column("Score", style="green bold", width=6)
    top_table.add_column("Company", style="white", width=25)
    top_table.add_column("Type", style="cyan", width=8)
    top_table.add_column("Words", justify="right", style="dim")
    top_table.add_column("Title", style="dim")
    for doc in stats["top_docs_by_quality"]:
        top_table.add_row(
            f"{doc['quality_score']:.2f}",
            doc["company"][:24],
            doc["filing_type"] or "",
            f"{doc['word_count']:,}" if doc["word_count"] else "—",
            doc["title"][:45],
        )
    console.print(top_table)
    console.print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python analytics/stats.py",
        description="SEC EDGAR corpus analytics — loads JSONL output and prints statistics.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("output/edgar.jsonl"),
        metavar="PATH",
        help="Path to the JSONL corpus file (default: output/edgar.jsonl)",
    )
    parser.add_argument(
        "--filing-type",
        type=str,
        default=None,
        metavar="TYPE",
        help="Only analyse documents of this filing type (e.g. 10-K)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of formatted report",
    )
    args = parser.parse_args()

    print(f"Loading corpus from {args.input}...", file=sys.stderr)
    docs = load_jsonl(args.input, filing_type=args.filing_type)
    print(f"Loaded {len(docs):,} documents.", file=sys.stderr)

    stats = compute_stats(docs)

    if args.json:
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    elif RICH:
        print_report_rich(stats)
    else:
        print_report_plain(stats)


if __name__ == "__main__":
    main()
