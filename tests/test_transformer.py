from __future__ import annotations

from scraper.parser import (
    ParsedPage,
    _clean_whitespace,
    _detect_sec_item,
    _extract_sections,
    _extract_title,
    _count_tables,
    _count_links,
    parse,
)
from bs4 import BeautifulSoup


class TestCleanWhitespace:
    def test_collapses_multiple_spaces(self):
        assert _clean_whitespace("hello   world") == "hello world"

    def test_collapses_tabs(self):
        assert _clean_whitespace("hello\t\tworld") == "hello world"

    def test_strips_leading_trailing(self):
        assert _clean_whitespace("  hello  ") == "hello"

    def test_collapses_excessive_newlines(self):
        result = _clean_whitespace("para one\n\n\n\n\npara two")
        assert "\n\n\n" not in result

    def test_removes_page_numbers(self):
        text = "Some text\n- 47 -\nMore text"
        result = _clean_whitespace(text)
        assert "47" not in result or "- 47 -" not in result

    def test_handles_empty_string(self):
        assert _clean_whitespace("") == ""

    def test_normalises_unicode(self):
        # NFKC normalisation: ligature fi → fi
        result = _clean_whitespace("\ufb01nancial")
        assert result == "financial"

    def test_removes_zero_width_chars(self):
        result = _clean_whitespace("hello\u200bworld")
        assert "\u200b" not in result


class TestDetectSecItem:
    def test_detects_item_1a_risk_factors(self):
        assert _detect_sec_item("Item 1A. Risk Factors") == "item_1a"

    def test_detects_item_7_mda(self):
        result = _detect_sec_item("Item 7. Management's Discussion and Analysis")
        assert result == "item_7"

    def test_detects_item_8_financial_statements(self):
        result = _detect_sec_item("Item 8. Financial Statements and Supplementary Data")
        assert result == "item_8"

    def test_detects_item_9a_controls(self):
        result = _detect_sec_item("Item 9A. Controls and Procedures")
        assert result == "item_9a"

    def test_detects_item_1_business(self):
        result = _detect_sec_item("ITEM 1. BUSINESS")
        assert result == "item_1"

    def test_detects_with_em_dash_separator(self):
        result = _detect_sec_item("Item 1A — Risk Factors")
        assert result == "item_1a"

    def test_case_insensitive(self):
        assert _detect_sec_item("item 1a. risk factors") == "item_1a"
        assert _detect_sec_item("ITEM 1A. RISK FACTORS") == "item_1a"

    def test_returns_none_for_unknown(self):
        assert _detect_sec_item("Quarterly Financial Summary") is None

    def test_returns_none_for_empty(self):
        assert _detect_sec_item("") is None

    def test_detects_item_2_properties(self):
        assert _detect_sec_item("Item 2. Properties") == "item_2"


class TestExtractTitle:
    def test_extracts_from_title_tag(self):
        soup = BeautifulSoup(
            "<html><head><title>Apple Inc. Annual Report</title></head><body></body></html>",
            "lxml"
        )
        result = _extract_title(soup, "10-K", "Apple Inc.")
        assert "Apple" in result

    def test_falls_back_to_h1(self):
        soup = BeautifulSoup(
            "<html><head><title>SEC EDGAR</title></head><body><h1>Apple 10-K Filing</h1></body></html>",
            "lxml"
        )
        result = _extract_title(soup, "10-K", "Apple Inc.")
        assert "Apple" in result

    def test_constructs_title_when_no_useful_tags(self):
        soup = BeautifulSoup(
            "<html><head><title>SEC EDGAR</title></head><body></body></html>",
            "lxml"
        )
        result = _extract_title(soup, "10-K", "Apple Inc.")
        assert "10-K" in result
        assert "Apple" in result

    def test_skips_generic_edgar_title(self):
        soup = BeautifulSoup(
            "<html><head><title>EDGAR Filing Viewer</title></head>"
            "<body><h1>Apple Inc. Form 10-K</h1></body></html>",
            "lxml"
        )
        result = _extract_title(soup, "10-K", "Apple Inc.")
        # should not use the EDGAR title, fall back to h1
        assert "Apple" in result


class TestCounters:
    def test_counts_tables(self):
        soup = BeautifulSoup(
            "<div><table><tr><td>A</td></tr></table><table><tr><td>B</td></tr></table></div>",
            "lxml"
        )
        root = soup.find("div")
        assert _count_tables(root) == 2

    def test_counts_zero_tables(self):
        soup = BeautifulSoup("<div><p>No tables here</p></div>", "lxml")
        root = soup.find("div")
        assert _count_tables(root) == 0

    def test_counts_links(self):
        soup = BeautifulSoup(
            '<div><a href="/a">A</a><a href="/b">B</a><a href="/c">C</a></div>',
            "lxml"
        )
        root = soup.find("div")
        assert _count_links(root) == 3



class TestParse:
    def test_parse_10k_returns_parsed_page(self, crawl_result_10k):
        result = parse(crawl_result_10k)
        assert result is not None
        assert isinstance(result, ParsedPage)

    def test_parse_10k_extracts_title(self, crawl_result_10k):
        result = parse(crawl_result_10k)
        assert result is not None
        assert result.title
        assert len(result.title) > 3

    def test_parse_10k_has_sections(self, crawl_result_10k):
        result = parse(crawl_result_10k)
        assert result is not None
        assert len(result.sections) > 0

    def test_parse_10k_detects_risk_factors(self, crawl_result_10k):
        result = parse(crawl_result_10k)
        assert result is not None
        sec_items = [s.sec_item for s in result.sections if s.sec_item]
        assert "item_1a" in sec_items

    def test_parse_10k_detects_mda(self, crawl_result_10k):
        result = parse(crawl_result_10k)
        assert result is not None
        sec_items = [s.sec_item for s in result.sections if s.sec_item]
        assert "item_7" in sec_items

    def test_parse_10k_strips_boilerplate(self, crawl_result_10k):
        result = parse(crawl_result_10k)
        assert result is not None
        # footer text should not appear in body
        assert "Copyright Apple Inc." not in result.body_text
        assert "EDGAR Filing System" not in result.body_text

    def test_parse_10k_has_body_text(self, crawl_result_10k):
        result = parse(crawl_result_10k)
        assert result is not None
        assert len(result.body_text) > 500

    def test_parse_10k_counts_tables(self, crawl_result_10k):
        result = parse(crawl_result_10k)
        assert result is not None
        assert result.table_count >= 1

    def test_parse_10k_headings_are_ordered(self, crawl_result_10k):
        result = parse(crawl_result_10k)
        assert result is not None
        assert len(result.headings) > 0
        # headings list should match section headings in order
        section_headings = [s.heading for s in result.sections]
        assert result.headings == section_headings

    def test_parse_8k_returns_parsed_page(self, crawl_result_8k):
        result = parse(crawl_result_8k)
        assert result is not None

    def test_parse_8k_has_sections(self, crawl_result_8k):
        result = parse(crawl_result_8k)
        assert result is not None
        assert len(result.sections) > 0

    def test_parse_empty_returns_none(self, crawl_result_empty):
        """Pages with < 200 chars of content should be rejected."""
        result = parse(crawl_result_empty)
        assert result is None

    def test_section_positions_are_sequential(self, crawl_result_10k):
        result = parse(crawl_result_10k)
        assert result is not None
        positions = [s.position for s in result.sections]
        assert positions == list(range(len(positions)))

    def test_url_passed_through(self, crawl_result_10k):
        result = parse(crawl_result_10k)
        assert result is not None
        assert result.url == crawl_result_10k.url
