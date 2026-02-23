"""Initial schema — all five tables and indexes.

Revision ID: 001
Revises:
Create Date: 2026-02-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # crawl_runs
    op.create_table(
        "crawl_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), server_default="running", nullable=False),
        sa.Column("start_ciks", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("filing_types", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("max_filings", sa.Integer(), nullable=True),
        sa.Column("config", postgresql.JSONB(), nullable=True),
        sa.Column("pages_crawled", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pages_saved", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pages_skipped", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pages_errored", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )

    # companies
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cik", sa.String(10), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("tickers", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("exchanges", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("sic_code", sa.String(4), nullable=True),
        sa.Column("sic_description", sa.Text(), nullable=True),
        sa.Column("state_of_inc", sa.String(2), nullable=True),
        sa.Column("fiscal_year_end", sa.String(4), nullable=True),
        sa.Column("entity_type", sa.Text(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cik"),
    )
    op.create_index("idx_companies_cik", "companies", ["cik"])
    op.create_index("idx_companies_sic", "companies", ["sic_code"])
    op.create_index(
        "idx_companies_tickers",
        "companies",
        ["tickers"],
        postgresql_using="gin",
    )

    # documents
    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("accession_number", sa.String(25), nullable=True),
        sa.Column("http_status", sa.SmallInteger(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_modified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filing_type", sa.String(20), nullable=True),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("period_of_report", sa.Date(), nullable=True),
        sa.Column("fiscal_year", sa.SmallInteger(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("headings", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("breadcrumbs", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("char_count", sa.Integer(), nullable=True),
        sa.Column("reading_time_minutes", sa.Numeric(7, 2), nullable=True),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("content_type", sa.String(30), nullable=True),
        sa.Column("code_ratio", sa.Numeric(5, 4), nullable=True),
        sa.Column("has_tables", sa.Boolean(), nullable=True),
        sa.Column("table_count", sa.Integer(), nullable=True),
        sa.Column("link_count", sa.Integer(), nullable=True),
        sa.Column("quality_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("depth_in_site", sa.SmallInteger(), nullable=True),
        sa.Column("schema_version", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["crawl_runs.run_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_hash"),
        sa.UniqueConstraint("url"),
    )

    # core lookup indexes
    op.create_index("idx_documents_url", "documents", ["url"], unique=True)
    op.create_index("idx_documents_hash", "documents", ["content_hash"], unique=True)
    op.create_index("idx_documents_run_id", "documents", ["run_id"])
    op.create_index("idx_documents_company", "documents", ["company_id"])

    # filtering indexes
    op.create_index("idx_documents_filing_type", "documents", ["filing_type"])
    op.create_index("idx_documents_filing_date", "documents", ["filing_date"])
    op.create_index("idx_documents_period", "documents", ["period_of_report"])
    op.create_index("idx_documents_quality", "documents", ["quality_score"])
    op.create_index("idx_documents_language", "documents", ["language"])
    op.create_index("idx_documents_content_type", "documents", ["content_type"])

    # full-text search index
    op.create_index(
        "idx_documents_fts",
        "documents",
        [sa.text("to_tsvector('english', coalesce(title, '') || ' ' || coalesce(body_text, ''))")],
        postgresql_using="gin",
    )

    # array containment: WHERE 'risk-factors' = ANY(tags)
    op.create_index(
        "idx_documents_tags",
        "documents",
        ["tags"],
        postgresql_using="gin",
    )

    # document_sections
    op.create_table(
        "document_sections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("heading", sa.Text(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("char_count", sa.Integer(), nullable=True),
        sa.Column("sec_item", sa.String(20), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_sections_document",
        "document_sections",
        ["document_id", "position"],
    )
    op.create_index(
        "idx_sections_sec_item",
        "document_sections",
        ["sec_item"],
        postgresql_where=sa.text("sec_item IS NOT NULL"),
    )
    op.create_index(
        "idx_sections_fts",
        "document_sections",
        [sa.text("to_tsvector('english', coalesce(heading, '') || ' ' || coalesce(body_text, ''))")],
        postgresql_using="gin",
    )

    # crawl_errors
    op.create_table(
        "crawl_errors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("error_type", sa.String(30), nullable=True),
        sa.Column("http_status", sa.SmallInteger(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("stack_trace", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["crawl_runs.run_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_errors_run_id", "crawl_errors", ["run_id"])
    op.create_index("idx_errors_type", "crawl_errors", ["error_type"])


def downgrade() -> None:
    op.drop_table("crawl_errors")
    op.drop_table("document_sections")
    op.drop_table("documents")
    op.drop_table("companies")
    op.drop_table("crawl_runs")
