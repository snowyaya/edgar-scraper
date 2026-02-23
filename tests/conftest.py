from __future__ import annotations
from datetime import date, datetime
import pytest
from scraper.crawler import CompanyMeta, CrawlResult, FilingMeta


@pytest.fixture
def apple_company() -> CompanyMeta:
    return CompanyMeta(
        cik="0000320193",
        name="Apple Inc.",
        tickers=["AAPL"],
        exchanges=["Nasdaq"],
        sic_code="3571",
        sic_description="Electronic Computers",
        state_of_inc="CA",
        fiscal_year_end="0930",
        entity_type="Operating",
    )


@pytest.fixture
def filing_10k() -> FilingMeta:
    return FilingMeta(
        accession_number="0000320193-23-000077",
        filing_type="10-K",
        filing_date=date(2023, 11, 3),
        period_of_report=date(2023, 9, 30),
        primary_document="aapl-20230930.htm",
        primary_doc_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000077/aapl-20230930.htm",
    )


@pytest.fixture
def filing_8k() -> FilingMeta:
    return FilingMeta(
        accession_number="0000320193-23-000099",
        filing_type="8-K",
        filing_date=date(2023, 11, 2),
        period_of_report=date(2023, 11, 2),
        primary_document="aapl-20231102.htm",
        primary_doc_url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000099/aapl-20231102.htm",
    )


# Full 10-K HTML with proper item structure, boilerplate, tables, and
# enough body text to pass the min_content_words threshold.
APPLE_10K_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Apple Inc. Annual Report on Form 10-K</title>
</head>
<body>
  <!-- Navigation boilerplate — should be stripped -->
  <nav id="nav">
    <a href="/">EDGAR Home</a>
    <a href="/cgi-bin/browse-edgar">Search</a>
    <a href="/login">Login</a>
  </nav>

  <!-- Cover page boilerplate -->
  <div id="cover-page">
    <p>UNITED STATES SECURITIES AND EXCHANGE COMMISSION</p>
    <p>Washington, D.C. 20549</p>
    <p>FORM 10-K</p>
    <p>ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d)</p>
  </div>

  <!-- Main document body -->
  <div id="document">

    <h1>Apple Inc.</h1>
    <p>Form 10-K for the fiscal year ended September 30, 2023</p>

    <h2>Item 1. Business</h2>
    <p>Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets,
    wearables, and accessories worldwide. The Company also sells a variety of related services.
    Apple was incorporated in California in 1977. The Company's fiscal year is the 52 or 53-week
    period that ends on the last Saturday of September. The Company's products and services include
    iPhone, Mac, iPad, AirPods, Apple TV, Apple Watch, Beats products, and HomePod. The Company
    operates retail and online stores and a direct sales force, as well as third-party cellular
    network carriers, wholesalers, retailers, and resellers.</p>

    <h2>Item 1A. Risk Factors</h2>
    <p>The following risk factors and other information included in this Annual Report on Form 10-K
    should be carefully considered. The risks and uncertainties described below are not the only ones
    the Company faces. Additional risks and uncertainties not presently known to the Company or that
    the Company currently deems immaterial may also affect the Company's business operations.</p>
    <p>Global and regional economic conditions could materially adversely affect the Company.
    The Company's operations and performance depend significantly on global and regional economic
    conditions. Adverse macroeconomic conditions, including slow growth or recession, high
    unemployment, inflation, tighter credit, and currency fluctuations could adversely affect
    demand for the Company's products and services.</p>
    <p>The Company's success depends largely on its ability to attract and retain key personnel.
    Much of the Company's future success depends on the continued availability and service of key
    personnel, including its CEO and other members of senior management. The loss of any such
    personnel could negatively affect the Company's operations and financial condition.</p>

    <h2>Item 2. Properties</h2>
    <p>The Company's headquarters are located in Cupertino, California. As of September 30, 2023,
    the Company owned or leased facilities and land for corporate functions, R&amp;D, data centers,
    and retail and other operations. The Company believes its existing facilities and equipment are
    well maintained and in good operating condition. The Company has invested in Apple Park, its
    modern campus in Cupertino, California.</p>

    <h2>Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations</h2>
    <p>The following discussion should be read in conjunction with the consolidated financial
    statements and accompanying notes included in Part II, Item 8 of this Form 10-K. This section
    contains forward-looking statements that involve risks and uncertainties.</p>
    <p>For fiscal 2023, the Company reported net sales of $383.3 billion compared to $394.3 billion
    in fiscal 2022, a decrease of 3%. The decrease in net sales reflected lower iPhone, Mac, and
    iPad net sales, partially offset by higher Services net sales. Products net sales decreased 6%
    compared to fiscal 2022. Services net sales increased 9% compared to fiscal 2022.</p>
    <p>Gross margin was 44.1% for fiscal 2023, compared to 43.3% for fiscal 2022. The increase in
    gross margin percentage was driven primarily by cost savings and a favorable mix shift toward
    Services, partially offset by the weakness in foreign currencies relative to the U.S. dollar.</p>

    <h2>Item 8. Financial Statements and Supplementary Data</h2>
    <p>The following consolidated financial statements of Apple Inc. and its subsidiaries are
    included in this Annual Report on Form 10-K.</p>

    <table>
      <caption>Consolidated Statements of Operations (in millions)</caption>
      <thead>
        <tr>
          <th>Fiscal Year</th>
          <th>2023</th>
          <th>2022</th>
          <th>2021</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>Net sales: Products</td><td>$298,085</td><td>$316,199</td><td>$297,392</td></tr>
        <tr><td>Net sales: Services</td><td>$85,200</td><td>$78,129</td><td>$68,425</td></tr>
        <tr><td>Total net sales</td><td>$383,285</td><td>$394,328</td><td>$365,817</td></tr>
        <tr><td>Cost of sales</td><td>$214,137</td><td>$223,546</td><td>$212,981</td></tr>
        <tr><td>Gross margin</td><td>$169,148</td><td>$170,782</td><td>$152,836</td></tr>
        <tr><td>Net income</td><td>$96,995</td><td>$99,803</td><td>$94,680</td></tr>
      </tbody>
    </table>

    <table>
      <caption>Consolidated Balance Sheets (in millions)</caption>
      <thead>
        <tr><th>As of</th><th>Sep 30, 2023</th><th>Sep 24, 2022</th></tr>
      </thead>
      <tbody>
        <tr><td>Cash and equivalents</td><td>$29,965</td><td>$23,646</td></tr>
        <tr><td>Total current assets</td><td>$143,566</td><td>$135,405</td></tr>
        <tr><td>Total assets</td><td>$352,583</td><td>$352,755</td></tr>
        <tr><td>Total liabilities</td><td>$290,437</td><td>$302,083</td></tr>
      </tbody>
    </table>

    <h2>Item 9A. Controls and Procedures</h2>
    <p>Evaluation of Disclosure Controls and Procedures. Based on an evaluation under the
    supervision and with the participation of the Company's management, the Company's principal
    executive officer and principal financial officer have concluded that the Company's disclosure
    controls and procedures were effective as of September 30, 2023.</p>

  </div>

  <!-- Footer boilerplate — should be stripped -->
  <footer id="footer">
    <p>Copyright Apple Inc. All rights reserved.</p>
    <p>EDGAR Filing System</p>
    <p>- 47 -</p>
  </footer>
</body>
</html>"""


# 8-K current report — shorter, event-driven, no Item 1A/7 structure
APPLE_8K_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Apple Inc. Form 8-K Current Report</title>
</head>
<body>
  <nav><a href="/">EDGAR</a></nav>

  <div id="document">
    <h1>Apple Inc.</h1>
    <p>Current Report on Form 8-K dated November 2, 2023</p>

    <h2>Item 2.02. Results of Operations and Financial Condition</h2>
    <p>On November 2, 2023, Apple Inc. issued a press release regarding its financial results
    for the fourth fiscal quarter and fiscal year ended September 30, 2023. A copy of Apple's
    press release is attached hereto as Exhibit 99.1 and incorporated herein by reference.</p>
    <p>The information in this Current Report on Form 8-K, including Exhibit 99.1 attached hereto,
    is furnished and shall not be deemed filed for purposes of Section 18 of the Securities
    Exchange Act of 1934, as amended. Apple reported fourth quarter revenue of $89.5 billion,
    up 1 percent year over year. The Board of Directors has also declared a cash dividend of
    $0.24 per share of the Company's common stock.</p>

    <h2>Item 9.01. Financial Statements and Exhibits</h2>
    <p>Exhibit 99.1 — Press release issued by Apple Inc. on November 2, 2023 regarding its
    financial results for the fourth fiscal quarter and fiscal year ended September 30, 2023.</p>
  </div>

  <footer><p>Copyright Apple Inc.</p></footer>
</body>
</html>"""


# Deliberately thin — should be rejected by the parser's min content threshold
EMPTY_PAGE_HTML = """<!DOCTYPE html>
<html>
<head><title>SEC EDGAR</title></head>
<body>
  <nav><a href="/">Home</a></nav>
  <div id="document"><p>No content.</p></div>
</body>
</html>"""


@pytest.fixture
def crawl_result_10k(apple_company, filing_10k) -> CrawlResult:
    """Realistic Apple 10-K crawl result with full section structure."""
    return CrawlResult(
        company=apple_company,
        filing=filing_10k,
        url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000077/aapl-20230930.htm",
        html=APPLE_10K_HTML,
        http_status=200,
        fetched_at=datetime(2024, 1, 15, 10, 30, 0),
        last_modified=datetime(2023, 11, 3, 0, 0, 0),
    )


@pytest.fixture
def crawl_result_8k(apple_company, filing_8k) -> CrawlResult:
    """Apple 8-K current report — shorter event-driven filing."""
    return CrawlResult(
        company=apple_company,
        filing=filing_8k,
        url="https://www.sec.gov/Archives/edgar/data/320193/000032019323000099/aapl-20231102.htm",
        html=APPLE_8K_HTML,
        http_status=200,
        fetched_at=datetime(2024, 1, 15, 10, 31, 0),
        last_modified=None,
    )


@pytest.fixture
def crawl_result_empty(apple_company, filing_10k) -> CrawlResult:
    """Near-empty page that should be rejected by the parser."""
    return CrawlResult(
        company=apple_company,
        filing=filing_10k,
        url="https://www.sec.gov/Archives/edgar/data/320193/empty.htm",
        html=EMPTY_PAGE_HTML,
        http_status=200,
        fetched_at=datetime(2024, 1, 15, 10, 32, 0),
        last_modified=None,
    )
