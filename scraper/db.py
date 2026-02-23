"""
SQLAlchemy ORM models and async engine/session factory.
Single source of truth for the database schema.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from scraper.config import settings


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all ORM models"""
    pass


def create_engine():
    """Create the async SQLAlchemy engine"""
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True, # validates connections before use, handles DB restarts
        pool_size=10,
        max_overflow=20,
        echo=settings.log_level == "DEBUG", # log SQL only in debug mode
    )


def create_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False, #keeps ORM objects accessible after commit
    )


# Module-level singletons — imported by scraper writer and API routers
engine = create_engine()
AsyncSessionFactory = create_session_factory(engine)


async def get_db_session() -> AsyncSession:
    """FastAPI dependency that yields a DB session per request"""
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        nullable=False,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # enum-like: 'running' | 'completed' | 'failed' | 'partial'
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")

    # configuration snapshot of a run
    start_ciks: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text), nullable=True)
    filing_types: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text), nullable=True)
    max_filings: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # progress counters (updated incrementally during the run)
    pages_crawled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_saved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_errored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # relationships
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="run")
    errors: Mapped[list["CrawlError"]] = relationship("CrawlError", back_populates="run")

    def __repr__(self) -> str:
        return f"<CrawlRun {self.run_id} status={self.status}>"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cik: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    # market identifiers
    tickers: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text), nullable=True)
    exchanges: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text), nullable=True)

    # SEC classification
    sic_code: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    sic_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    state_of_inc: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)

    # fiscal calendar
    fiscal_year_end: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)  # MMDD

    entity_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # relationships
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="company")

    __table_args__ = (
        Index("idx_companies_cik", "cik"),
        Index("idx_companies_sic", "sic_code"),
        # GIN index for array containment queries: WHERE 'AAPL' = ANY(tickers)
        Index("idx_companies_tickers", "tickers", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<Company {self.cik} {self.name}>"


class Document(Base):
    __tablename__ = "documents"

    # identity & dedup
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    # SHA-256 hex digest of cleaned body_text (also the dedup key)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    # provenance
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crawl_runs.run_id"),
        nullable=False,
    )
    company_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("companies.id"),
        nullable=True,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # SEC accession number — e.g. "0000320193-23-000077"
    # uniquely identifies a filing in EDGAR; used to reconstruct URLs
    accession_number: Mapped[Optional[str]] = mapped_column(String(25), nullable=True)

    http_status: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_modified: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # filing type
    filing_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    filing_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # fiscal period of the report
    period_of_report: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    fiscal_year: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)

    # core content
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)

    # ordered array of all headings found in the document
    headings: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text), nullable=True)
    breadcrumbs: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text), nullable=True)

    # AI enrichment signals
    word_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    char_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # estimated reading time in minutes (word_count / 238 wpm)
    reading_time_minutes: Mapped[Optional[float]] = mapped_column(Numeric(7, 2), nullable=True)
    
    # ISO 639-1 language code, e.g. 'en'
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    
    # e.g.: annual_report | quarterly_report | current_report | proxy_statement | filing_index | other
    content_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    
    # fraction of body text
    code_ratio: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    has_tables: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    table_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    link_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # composite quality signal (0.0–1.0)
    quality_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)

    # taxonomy
    tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text), nullable=True)
    depth_in_site: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)

    #schema version (handle migrations gracefully)
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # relationships
    run: Mapped["CrawlRun"] = relationship("CrawlRun", back_populates="documents")
    company: Mapped[Optional["Company"]] = relationship("Company", back_populates="documents")
    sections: Mapped[list["DocumentSection"]] = relationship(
        "DocumentSection",
        back_populates="document",
        cascade="all, delete-orphan", # deleting a document removes its sections
        order_by="DocumentSection.position",
    )

    __table_args__ = (
        # core index
        Index("idx_documents_url", "url", unique=True),
        Index("idx_documents_hash", "content_hash", unique=True),
        Index("idx_documents_run_id", "run_id"),
        Index("idx_documents_company", "company_id"),

        # filtering indexes
        Index("idx_documents_filing_type", "filing_type"),
        Index("idx_documents_filing_date", "filing_date"),
        Index("idx_documents_period", "period_of_report"),
        Index("idx_documents_quality", "quality_score"),
        Index("idx_documents_language", "language"),
        Index("idx_documents_content_type", "content_type"),

        # full-text search
        Index(
            "idx_documents_fts",
            func.to_tsvector(
                "english",
                func.coalesce(text("title"), "")
                + " "
                + func.coalesce(text("body_text"), ""),
            ),
            postgresql_using="gin",
        ),

        # array containment queries: WHERE 'risk-factors' = ANY(tags)
        Index("idx_documents_tags", "tags", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<Document {self.id} {self.filing_type} {self.title[:40] if self.title else ''}>"


class DocumentSection(Base):
    """
    Section-level content breakdown of a document.

    This table is the key to making the corpus RAG-ready.
    Instead of chunking raw text at retrieval time, sections are stored
    as first-class rows, enabling queries like "Give me Item 1A (Risk Factors) from Apple's last 3 10-Ks"
    as a simple SQL join, with no re-chunking required.

    sec_item maps headings to canonical SEC filing sections:
    'item_1'  >>  Business description
    'item_1a' >>  Risk Factors
    'item_7'  >>  MD&A (Management Discussion & Analysis)
    'item_8'  >>  Financial Statements
    'item_9a' >>  Controls and Procedures
    """
    __tablename__ = "document_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    # heading hierarchy depth: 1=H1, 2=H2, 3=H3
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    heading: Mapped[str] = mapped_column(Text, nullable=False)
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # zero-indexed position within the parent document for ordering
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    word_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    char_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # canonical SEC item identifier
    sec_item: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # relationship
    document: Mapped["Document"] = relationship("Document", back_populates="sections")

    __table_args__ = (
        # primary access pattern: all sections for a document, in order
        Index("idx_sections_document", "document_id", "position"),
        # targeted retrieval: WHERE sec_item = 'item_1a'
        Index(
            "idx_sections_sec_item",
            "sec_item",
            postgresql_where=text("sec_item IS NOT NULL"),
        ),
        # section-level full-text search
        Index(
            "idx_sections_fts",
            func.to_tsvector(
                "english",
                func.coalesce(text("heading"), "")
                + " "
                + func.coalesce(text("body_text"), ""),
            ),
            postgresql_using="gin",
        ),
    )

    def __repr__(self) -> str:
        return f"<DocumentSection {self.document_id} pos={self.position} '{self.heading[:40]}'>"


class CrawlError(Base):
    """
    error_type controlled vocabulary:
    'timeout'        >> request exceeded REQUEST_TIMEOUT_SECONDS
    'http_error'     >> 4xx or 5xx response
    'parse_error'    >> HTML parsing or content extraction failed
    'encoding_error' >> could not decode response bytes
    'rate_limited'   >> 429 response (after exhausting retries)
    'empty_content'  >> word_count < MIN_CONTENT_WORDS after extraction
    """
    __tablename__ = "crawl_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crawl_runs.run_id"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    error_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    http_status: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stack_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # relationship
    run: Mapped["CrawlRun"] = relationship("CrawlRun", back_populates="errors")

    __table_args__ = (
        Index("idx_errors_run_id", "run_id"),
        Index("idx_errors_type", "error_type"),
    )

    def __repr__(self) -> str:
        return f"<CrawlError {self.run_id} {self.error_type} {self.url[:60]}>"
