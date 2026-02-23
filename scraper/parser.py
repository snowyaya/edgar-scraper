# HTML → ParsedPage (content extraction, section splitting)
"""
Extracts structured content from raw SEC filing HTML into a ParsedPage
dataclass for the transformer to enrich.

Content root is found via layered fallback: div#document >> div.formContent
>> div#main-content >> main >> article >> div#content >> body, requiring 200+
characters before accepting a candidate. Boilerplate is stripped, then the
remaining content is split into sections at heading boundaries.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional
import warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning, Tag

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from scraper.crawler import CrawlResult

logger = logging.getLogger(__name__)


# minimum characters for a section's body to be worth keeping
MIN_SECTION_CHARS = 50

# boilerplate elements to remove before content extraction
BOILERPLATE_SELECTORS = [
    # layout chrome
    "header", "footer", "nav", "aside",
    # EDGAR-specific navigation and chrome
    "#header", "#footer", ".banner", ".nav-bar",
    ".formGrouping",        # EDGAR form chrome
    "[class*='header']",    # anything with 'header' in class
    "[class*='footer']",    # anything with 'footer' in class
    "[class*='navbar']",
    # XBRL inline tags — structured data, not readable text
    "ix\\:header", "ix\\:hidden",
    # table of contents links — redundant once we split into sections
    ".toc", "#toc", "[class*='table-of-contents']",
    # page number artifacts common in scanned → HTML conversions
    ".page-number", "[class*='pagenum']",
    # exhibit lists and signatures are boilerplate in 10-Ks
    # strip their excess whitespace
]

SEC_ITEM_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"item\s*1\.01",  re.I), "item_1_01"),
    (re.compile(r"item\s*1\.02",  re.I), "item_1_02"),
    (re.compile(r"item\s*2\.01",  re.I), "item_2_01"),
    (re.compile(r"item\s*2\.02",  re.I), "item_2_02"),
    (re.compile(r"item\s*2\.05",  re.I), "item_2_05"),
    (re.compile(r"item\s*3\.01",  re.I), "item_3_01"),
    (re.compile(r"item\s*5\.02",  re.I), "item_5_02"),
    (re.compile(r"item\s*5\.03",  re.I), "item_5_03"),
    (re.compile(r"item\s*7\.01",  re.I), "item_7_01"),
    (re.compile(r"item\s*8\.01",  re.I), "item_8_01"),
    (re.compile(r"item\s*9\.01",  re.I), "item_9_01"),
    (re.compile(r"item\s*1[.\s:—]+business", re.I), "item_1"),
    (re.compile(r"item\s*1a[.\s:—]+risk", re.I), "item_1a"),
    (re.compile(r"item\s*1b[.\s:—]+unresolved", re.I), "item_1b"),
    (re.compile(r"item\s*2[.\s:—]+propert", re.I), "item_2"),
    (re.compile(r"item\s*3[.\s:—]+legal", re.I), "item_3"),
    (re.compile(r"item\s*4[.\s:—]+mine", re.I), "item_4"),
    (re.compile(r"item\s*5[.\s:—]+market", re.I), "item_5"),
    (re.compile(r"item\s*6[.\s:—]+selected", re.I), "item_6"),
    (re.compile(r"item\s*7[.\s:—]+management", re.I), "item_7"),
    (re.compile(r"item\s*7a[.\s:—]+quantitative", re.I), "item_7a"),
    (re.compile(r"item\s*8[.\s:—]+financial\s+stat", re.I), "item_8"),
    (re.compile(r"item\s*9[.\s:—]+changes", re.I), "item_9"),
    (re.compile(r"item\s*9a[.\s:—]+controls", re.I), "item_9a"),
    (re.compile(r"item\s*9b[.\s:—]+other", re.I), "item_9b"),
    (re.compile(r"item\s*10[.\s:—]+directors", re.I), "item_10"),
    (re.compile(r"item\s*11[.\s:—]+executive", re.I), "item_11"),
    (re.compile(r"item\s*12[.\s:—]+security", re.I), "item_12"),
    (re.compile(r"item\s*13[.\s:—]+certain", re.I), "item_13"),
    (re.compile(r"item\s*14[.\s:—]+principal", re.I), "item_14"),
    (re.compile(r"item\s*15[.\s:—]+exhibit", re.I), "item_15"),
    # 10-Q specific
    (re.compile(r"item\s*1[.\s:—]+financial\s+stat", re.I), "item_1_10q"),
    (re.compile(r"item\s*2[.\s:—]+management", re.I), "item_2_10q"),
    (re.compile(r"item\s*3[.\s:—]+quantitative", re.I), "item_3_10q"),
    (re.compile(r"item\s*4[.\s:—]+controls", re.I), "item_4_10q"),
]


@dataclass
class ParsedSection:
    """One section of a filing, split at a heading boundary."""
    level: int # heading depth: 1=H1, 2=H2, etc.
    heading: str # cleaned heading text
    body_text: str # cleaned section body text
    position: int # zero-indexed order in document
    sec_item: Optional[str] = None # canonical SEC item tag if detected


@dataclass
class ParsedPage:
    """
    Structured intermediate representation of a scraped filing page.

    Produced by parser.py, consumed by transformer.py.
    Contains cleaned content and structure but no computed signals —
    those are added by the transformer.
    """
    # source info from CrawlResult
    url: str
    http_status: int
    fetched_at: object

    # extracted content
    title: str
    body_text: str # full cleaned text
    headings: list[str] # ordered list of all heading texts
    sections: list[ParsedSection]
    breadcrumbs: list[str]

    # raw counts
    raw_char_count: int
    table_count: int
    code_char_count: int
    link_count: int

    # filing context from CrawlResult
    company: object
    filing: object

    last_modified: Optional[object] = None


def _find_content_root(soup: BeautifulSoup) -> Tag:
    """
    Locate the primary content element using a layered fallback strategy.
    """
    candidates = [
        soup.find("div", id="document"),
        soup.find("div", class_="formContent"),
        soup.find("div", id="main-content"),
        soup.find("main"),
        soup.find("article"),
        soup.find("div", id="content"),
        soup.find("body"),
    ]

    for candidate in candidates:
        if candidate and isinstance(candidate, Tag):
            # require at least 200 characters of text to avoid empty shells
            if len(candidate.get_text(strip=True)) > 200:
                logger.debug(f"Content root: <{candidate.name} id='{candidate.get('id', '')}'>")
                return candidate

    # fallback to return the whole soup as a Tag
    logger.warning("Could not find a content root — using full document body")
    return soup


def _strip_boilerplate(root: Tag) -> None:
    """
    Remove known boilerplate elements from the content root in-place.
    """
    for selector in BOILERPLATE_SELECTORS:
        for element in root.select(selector):
            element.decompose()


def _extract_title(soup: BeautifulSoup, filing_type: str, company_name: str) -> str:
    """
    Extract the document title with fallback construction.
    Priority:
    1. <title> tag
    2. First <h1> in the document
    3. Constructed from filing type + company name
    """
    # title
    title_tag = soup.find("title")
    if title_tag:
        title = _clean_whitespace(title_tag.get_text())
        if title and "EDGAR" not in title.upper() and len(title) > 5:
            return title

    # H1
    h1 = soup.find("h1")
    if h1 and isinstance(h1, Tag):
        title = _clean_whitespace(h1.get_text())
        if title and len(title) > 3:
            return title

    # company name + fileing type
    return f"{company_name} — Form {filing_type}"


def _extract_breadcrumbs(soup: BeautifulSoup) -> list[str]:
    breadcrumb_selectors = [
        ".breadcrumb", ".breadcrumbs", "#breadcrumb",
        "[aria-label='breadcrumb']", ".crumbs",
    ]

    for selector in breadcrumb_selectors:
        element = soup.select_one(selector)
        if element:
            crumbs = [
                _clean_whitespace(a.get_text())
                for a in element.find_all("a")
                if _clean_whitespace(a.get_text())
            ]
            if crumbs:
                return crumbs

    return []


def _detect_sec_item(heading: str) -> Optional[str]:
    for pattern, item_id in SEC_ITEM_PATTERNS:
        if pattern.search(heading):
            return item_id
    return None

def _is_sec_heading(element: Tag) -> tuple[bool, str]:
    """
    Detect SEC item headings that aren't marked up as <h1>-<h4> tags.
    """
    text = _clean_whitespace(element.get_text())
    if not text:
        return False, ""

    # should be a known sec item
    if _detect_sec_item(text) is None:
        return False, ""

    # check 1: bold via <b>/<strong> child tags (traditional HTML filings)
    bold_text = "".join(
        b.get_text() for b in element.find_all(["b", "strong"])
    )
    if len(bold_text) > len(text) * 0.7:
        return True, text

    style = element.get("style", "")
    if re.search(r"font-weight\s*:\s*(bold|[6-9]\d{2})", style, re.I):
        return True, text
    
    # check 2: bold via inline CSS on the element itself or any descendant
    bold_pattern = re.compile(r"font-weight\s*:\s*(bold|[6-9]\d{2})", re.I)
    elements_to_check = [element] + element.find_all(True)
    for el in elements_to_check:
        if bold_pattern.search(el.get("style", "")):
            return True, text

    # check 3: heading CSS classes
    classes = element.get("class", [])
    heading_classes = {"sectionHeading", "itemHeading", "item-heading",
                       "heading", "sHeading", "hd"}
    if any(c in heading_classes for c in classes):
        return True, text

    return False, ""


def _extract_sections(root: Tag) -> list[ParsedSection]:
    """
    Split the content root into sections at heading boundaries.
    Walks the element tree, flushing a new ParsedSection at each explicit
    heading (H1–H4) or detected SEC item heading in <p>/<div>/<span>.
    Sections shorter than MIN_SECTION_CHARS are merged into the previous one.
    """
    sections: list[ParsedSection] = []
    current_heading: Optional[str] = None
    current_level: int = 1
    current_body_parts: list[str] = []
    position = 0

    heading_tags = {"h1", "h2", "h3", "h4"}

    def flush_section() -> None:
        nonlocal position
        if current_heading is None:
            return
        body = _clean_whitespace(" ".join(current_body_parts))

        # merge short fragments into the previous section to avoid noise
        if len(body) < MIN_SECTION_CHARS and sections:
            sections[-1].body_text += " " + body
            return
        sections.append(ParsedSection(
            level=current_level,
            heading=current_heading,
            body_text=body,
            position=position,
            sec_item=_detect_sec_item(current_heading),
        ))
        position += 1

    def collect_text(element: Tag) -> str:
        """Collect text from an element that isn't itself a heading."""
        return _clean_whitespace(element.get_text())

    def walk(node: Tag) -> None:
        nonlocal current_heading, current_level, current_body_parts

        for element in node.children:
            if not isinstance(element, Tag):
                continue

            if element.name in heading_tags:
                flush_section()
                heading_text = _clean_whitespace(element.get_text())
                if heading_text:
                    current_heading = heading_text
                    current_level = int(element.name[1])
                    current_body_parts = []

            elif element.name in {"p", "div", "span"}:
                is_heading, heading_text = _is_sec_heading(element)
                if is_heading:
                    flush_section()
                    current_heading = heading_text
                    current_level = 2
                    current_body_parts = []
                else:
                    # recurse into structural containers; collect text at leaves
                    has_block_children = any(
                        isinstance(c, Tag) and c.name in {"p", "div", "table", "ul", "ol"}
                        for c in element.children
                    )
                    if has_block_children:
                        walk(element)
                    else:
                        text = collect_text(element)
                        if text and len(text) > 2:
                            current_body_parts.append(text)

            elif element.name in {"li", "td", "th"}:
                text = collect_text(element)
                if text and len(text) > 2:
                    current_body_parts.append(text)

            elif element.name in {"table", "ul", "ol"}:
                walk(element)

    walk(root)
    flush_section()
    return sections

def _count_tables(root: Tag) -> int:
    return len(root.find_all("table"))


def _count_code_chars(root: Tag) -> int:
    total = 0
    for tag in root.find_all(["pre", "code"]):
        total += len(tag.get_text())
    return total


def _count_links(root: Tag) -> int:
    return len(root.find_all("a", href=True))


def _clean_whitespace(text: str) -> str:
    """Normalise whitespace, remove control characters, and strip page numbers."""
    if not text:
        return ""

    # NFKC handles ligatures and compatibility characters
    text = unicodedata.normalize("NFKC", text)

    # zero-width and control characters are common in copy-pasted SEC filings
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b\u200c\u200d\ufeff]", "", text)

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # strip purely numeric lines (e.g. "- 47 -", "47")
    lines = text.split("\n")
    lines = [l for l in lines if not re.match(r"^\s*[-–—]?\s*\d+\s*[-–—]?\s*$", l)]
    text = "\n".join(lines)

    return text.strip()


def parse(result: CrawlResult) -> Optional[ParsedPage]:
    """
    Parse a CrawlResult into a structured ParsedPage, or None if the page
    has insufficient content (error pages, redirect stubs, empty documents).
    """
    try:
        soup = BeautifulSoup(result.html, "lxml")
        raw_html_char_count = len(result.html)
    except Exception as e:
        logger.error(f"Failed to parse HTML for {result.url}: {e}")
        return None

    # find and clean the content root
    root = _find_content_root(soup)
    _strip_boilerplate(root)

    # extract title and sections
    title = _extract_title(
        soup=soup,
        filing_type=result.filing.filing_type,
        company_name=result.company.name,
    )

    sections = _extract_sections(root)

    if not sections:
        # fallback for XBRL/inline filings with no heading tags
        full_text = _clean_whitespace(root.get_text())
        if full_text:
            sections = [ParsedSection(
                level=1,
                heading="Full Document",
                body_text=full_text,
                position=0,
                sec_item=None,
            )]
        else:
            return None

    # build full body text
    body_parts = []
    for section in sections:
        body_parts.append(section.heading)
        if section.body_text:
            body_parts.append(section.body_text)
    body_text = _clean_whitespace("\n\n".join(body_parts))

    # reject pages with trivially little content
    if len(body_text) < 200:
        logger.warning(
            f"Insufficient content ({len(body_text)} chars) at {result.url} — skipping"
        )
        return None

    return ParsedPage(
        url=result.url,
        http_status=result.http_status,
        fetched_at=result.fetched_at,
        last_modified=result.last_modified,
        title=title,
        body_text=body_text,
        headings=[s.heading for s in sections],
        sections=sections,
        breadcrumbs=_extract_breadcrumbs(soup),
        raw_char_count=raw_html_char_count,
        table_count=_count_tables(root),
        code_char_count=_count_code_chars(root),
        link_count=_count_links(root),
        company=result.company,
        filing=result.filing,
    )
