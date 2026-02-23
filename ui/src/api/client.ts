/**
 * api/client.ts
 * Typed fetch wrappers for all API endpoints.
 * Centralising API calls here means route changes only need one edit.
 */

import axios from 'axios'

// Base URL — empty string means same origin (Nginx proxies /api → FastAPI)
// In development, Vite proxies /api → localhost:8000
export const apiClient = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000,
})

// ── Types (mirrors api/models.py) ──────────────────────────────────────────

export interface Company {
  cik: string
  name: string
  tickers?: string[]
  sic_code?: string
  sic_description?: string
}

export interface DocumentSection {
  id: number
  level: number
  heading: string
  body_text?: string
  position: number
  word_count?: number
  char_count?: number
  sec_item?: string
}

export interface DocumentSummary {
  id: string
  url: string
  accession_number?: string
  filing_type?: string
  filing_date?: string
  period_of_report?: string
  fiscal_year?: number
  title?: string
  word_count?: number
  char_count?: number
  reading_time_minutes?: number
  language?: string
  content_type?: string
  quality_score?: number
  has_tables?: boolean
  table_count?: number
  tags?: string[]
  fetched_at: string
  company?: Company
}

export interface DocumentDetail extends DocumentSummary {
  body_text: string
  headings?: string[]
  breadcrumbs?: string[]
  code_ratio?: number
  link_count?: number
  depth_in_site?: number
  schema_version: number
  last_modified?: string
  http_status?: number
  canonical_url?: string
  sections: DocumentSection[]
}

export interface PaginatedDocuments {
  total: number
  limit: number
  offset: number
  items: DocumentSummary[]
}

export interface RunSummary {
  run_id: string
  started_at: string
  finished_at?: string
  status: string
  filing_types?: string[]
  pages_crawled: number
  pages_saved: number
  pages_skipped: number
  pages_errored: number
}

export interface RunDetail extends RunSummary {
  start_ciks?: string[]
  max_filings?: number
  config?: Record<string, unknown>
  error_summary?: string
}

export interface RunCreate {
  tickers?: string[]
  ciks?: string[]
  filing_types: string[]
  max_filings: number
  date_from?: string
  date_to?: string
}

export interface RunCreateResponse {
  run_id: string
  status: string
  message: string
}

export interface CrawlError {
  id: number
  url: string
  error_type?: string
  http_status?: number
  message?: string
  occurred_at: string
}

export interface PaginatedErrors {
  total: number
  limit: number
  offset: number
  items: CrawlError[]
}

export interface OverviewStats {
  total_documents: number
  total_companies: number
  total_runs: number
  avg_quality_score?: number
  avg_word_count?: number
  total_words?: number
  last_crawled_at?: string
}

export interface FilingTypeStats {
  filing_type: string
  document_count: number
  avg_quality_score?: number
  avg_word_count?: number
}

export interface LanguageStats {
  language: string
  document_count: number
  percentage: number
}

export interface QualityBucket {
  bucket_start: number
  bucket_end: number
  count: number
}

export interface TimelinePoint {
  date: string
  documents_saved: number
  companies: number
}

export interface TopCompany {
  cik: string
  name: string
  tickers?: string[]
  document_count: number
  avg_quality_score?: number
  total_words?: number
  filing_types: string[]
}

export interface ReadingTimeDistribution {
  bucket_label: string
  count: number
}

// ── Documents ──────────────────────────────────────────────────────────────

export interface DocumentFilters {
  limit?: number
  offset?: number
  company_cik?: string
  filing_type?: string
  fiscal_year?: number
  language?: string
  content_type?: string
  quality_min?: number
  quality_max?: number
  search?: string
  sort?: string
  order?: 'asc' | 'desc'
}

export const documentsApi = {
  list: (filters: DocumentFilters = {}) =>
    apiClient.get<PaginatedDocuments>('/documents', { params: filters }).then(r => r.data),

  get: (id: string) =>
    apiClient.get<DocumentDetail>(`/documents/${id}`).then(r => r.data),

  getSections: (id: string, params?: { sec_item?: string; min_words?: number }) =>
    apiClient.get<DocumentSection[]>(`/documents/${id}/sections`, { params }).then(r => r.data),
}

// ── Runs ───────────────────────────────────────────────────────────────────

export const runsApi = {
  list: (params?: { limit?: number; offset?: number; status?: string }) =>
    apiClient.get<RunSummary[]>('/runs', { params }).then(r => r.data),

  get: (runId: string) =>
    apiClient.get<RunDetail>(`/runs/${runId}`).then(r => r.data),

  create: (body: RunCreate) =>
    apiClient.post<RunCreateResponse>('/runs', body).then(r => r.data),

  getErrors: (runId: string, params?: { limit?: number; offset?: number }) =>
    apiClient.get<PaginatedErrors>(`/runs/${runId}/errors`, { params }).then(r => r.data),
}

// ── Analytics ──────────────────────────────────────────────────────────────

export const analyticsApi = {
  overview: () =>
    apiClient.get<OverviewStats>('/analytics/overview').then(r => r.data),

  filingTypes: () =>
    apiClient.get<FilingTypeStats[]>('/analytics/filing-types').then(r => r.data),

  languages: () =>
    apiClient.get<LanguageStats[]>('/analytics/languages').then(r => r.data),

  qualityHistogram: (buckets = 10) =>
    apiClient.get<QualityBucket[]>('/analytics/quality-histogram', { params: { buckets } }).then(r => r.data),

  timeline: (days = 30) =>
    apiClient.get<TimelinePoint[]>('/analytics/timeline', { params: { days } }).then(r => r.data),

  topCompanies: (limit = 10) =>
    apiClient.get<TopCompany[]>('/analytics/top-companies', { params: { limit } }).then(r => r.data),

  readingTime: () =>
    apiClient.get<ReadingTimeDistribution[]>('/analytics/reading-time').then(r => r.data),
}
