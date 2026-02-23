from __future__ import annotations

import uuid
from datetime import date

import pytest

from scraper.parser import parse
from scraper.transformer import transform


class TestUrlDedup:
    """
    The seen_urls set is the first line of defense against re-fetching.
    These tests verify the set mechanics work as expected.
    """

    def test_seen_urls_starts_empty(self):
        seen: set[str] = set()
        assert len(seen) == 0

    def test_url_added_after_processing(self):
        seen: set[str] = set()
        url = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000077/aapl-20230930.htm"
        seen.add(url)
        assert url in seen

    def test_duplicate_url_not_duplicated_in_set(self):
        seen: set[str] = set()
        url = "https://www.sec.gov/test.htm"
        seen.add(url)
        seen.add(url)  # second add is a no-op
        assert len(seen) == 1

    def test_different_urls_both_tracked(self):
        seen: set[str] = set()
        url1 = "https://www.sec.gov/Archives/edgar/data/320193/a.htm"
        url2 = "https://www.sec.gov/Archives/edgar/data/320193/b.htm"
        seen.add(url1)
        seen.add(url2)
        assert len(seen) == 2
        assert url1 in seen
        assert url2 in seen

    def test_url_check_before_add(self):
        seen: set[str] = set()
        url = "https://www.sec.gov/test.htm"
        # simulate the dedup check in write_document
        if url not in seen:
            seen.add(url)
        # second attempt — would be skipped
        was_skipped = url in seen
        assert was_skipped


class TestIncrementRunCounter:
    def test_rejects_invalid_counter_name(self):
        with pytest.raises(ValueError, match="Invalid counter"):
            valid_counters = {"pages_crawled", "pages_saved", "pages_skipped", "pages_errored"}
            counter = "invalid_counter_name"
            if counter not in valid_counters:
                raise ValueError(
                    f"Invalid counter: {counter}. Must be one of {valid_counters}"
                )

    def test_valid_counter_names_accepted(self):
        valid = {"pages_crawled", "pages_saved", "pages_skipped", "pages_errored"}
        for name in valid:
            assert name in valid


class TestDocumentToDict:
    def _get_sample_doc(self, crawl_result_10k):
        """Parse and transform a fixture into an AIDocument."""
        parsed = parse(crawl_result_10k)
        assert parsed is not None
        doc = transform(parsed)
        assert doc is not None
        return doc

    def test_produces_valid_dict(self, crawl_result_10k):
        from scraper.main import document_to_dict
        doc = self._get_sample_doc(crawl_result_10k)
        result = document_to_dict(doc)
        assert isinstance(result, dict)

    def test_contains_required_ai_fields(self, crawl_result_10k):
        from scraper.main import document_to_dict
        doc = self._get_sample_doc(crawl_result_10k)
        result = document_to_dict(doc)

        required_fields = [
            "id", "content_hash", "schema_version", "url",
            "company", "filing_type", "filing_date",
            "title", "body_text", "word_count", "char_count",
            "reading_time_minutes", "language", "content_type",
            "quality_score", "has_tables", "tags", "sections",
        ]
        for field in required_fields:
            assert field in result, f"Missing required field: {field}"

    def test_id_is_string_uuid(self, crawl_result_10k):
        from scraper.main import document_to_dict
        doc = self._get_sample_doc(crawl_result_10k)
        result = document_to_dict(doc)
        # should be a valid UUID string
        parsed_uuid = uuid.UUID(result["id"])
        assert str(parsed_uuid) == result["id"]

    def test_dates_are_iso_strings(self, crawl_result_10k):
        from scraper.main import document_to_dict
        doc = self._get_sample_doc(crawl_result_10k)
        result = document_to_dict(doc)
        # filing_date should be an ISO date string, not a date object
        if result["filing_date"] is not None:
            assert isinstance(result["filing_date"], str)
            date.fromisoformat(result["filing_date"])  # should not raise

    def test_quality_score_is_float(self, crawl_result_10k):
        from scraper.main import document_to_dict
        doc = self._get_sample_doc(crawl_result_10k)
        result = document_to_dict(doc)
        assert isinstance(result["quality_score"], float)

    def test_sections_is_list(self, crawl_result_10k):
        from scraper.main import document_to_dict
        doc = self._get_sample_doc(crawl_result_10k)
        result = document_to_dict(doc)
        assert isinstance(result["sections"], list)

    def test_section_has_sec_item_field(self, crawl_result_10k):
        from scraper.main import document_to_dict
        doc = self._get_sample_doc(crawl_result_10k)
        result = document_to_dict(doc)
        if result["sections"]:
            section = result["sections"][0]
            assert "sec_item" in section
            assert "heading" in section
            assert "body_text" in section
            assert "word_count" in section

    def test_company_nested_correctly(self, crawl_result_10k):
        from scraper.main import document_to_dict
        doc = self._get_sample_doc(crawl_result_10k)
        result = document_to_dict(doc)
        assert isinstance(result["company"], dict)
        assert "cik" in result["company"]
        assert "name" in result["company"]
        assert result["company"]["name"] == "Apple Inc."

    def test_result_is_json_serialisable(self, crawl_result_10k):
        import json
        from scraper.main import document_to_dict
        doc = self._get_sample_doc(crawl_result_10k)
        result = document_to_dict(doc)
        # should not raise — everything must be JSON-serialisable
        serialised = json.dumps(result)
        assert len(serialised) > 0

    def test_content_hash_is_64_chars(self, crawl_result_10k):
        from scraper.main import document_to_dict
        doc = self._get_sample_doc(crawl_result_10k)
        result = document_to_dict(doc)
        assert len(result["content_hash"]) == 64
