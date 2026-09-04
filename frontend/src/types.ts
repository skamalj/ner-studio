export type ProviderId = 'bedrock' | 'anthropic' | 'openai' | 'gemini' | 'local'

/** A selectable model: what to send, what it costs, what it accepts. */
export interface ModelOption {
  id: string
  label: string
  input_per_1m: number | null
  output_per_1m: number | null
  /** Only models with this flag may be offered on an image-based tab. */
  supports_images: boolean
  context: number | null
  /** Where inference physically runs: India / APAC / Worldwide. */
  residency: string
  flags: string[]
  note: string
}

export type ProviderStatus = 'ready' | 'not_configured' | 'unreachable'

export interface ProviderInfo {
  id: ProviderId
  label: string
  configured: boolean
  default_model: string
  models: ModelOption[]
  note: string
  status: ProviderStatus
  /** One line on how to configure or revive this provider. */
  setup_hint: string
}

export interface SummaryType {
  id: string
  label: string
}

export interface DocumentInfo {
  id: string
  filename: string
  content_type: string
  size: number
  ocr_source: string
  ocr_mode: string
  pages: number
  line_count: number
  created_at: string
  char_count: number
}

export interface UploadResponse {
  document: DocumentInfo
  text: string
  key_values: Record<string, string>
  tables: string[][][]
  warnings: string[]
}

export interface LogEntry {
  node: string
  message: string
  detail?: string
  ts?: number
}

export interface Usage {
  input_tokens: number
  output_tokens: number
  calls: number
}

export interface NerResult {
  data: unknown
  raw: string
  chunks: number
  instruction: string
  provider: string
  model: string
  elapsed_ms: number
  usage: Usage
  log: LogEntry[]
}

export interface SummaryResult {
  summary: string
  summary_type: string
  chunks: number
  passes: number
  provider: string
  model: string
  elapsed_ms: number
  usage: Usage
  log: LogEntry[]
}

export interface ModelSelection {
  provider: ProviderId
  model: string
  temperature: number
}

/**
 * Which engine turns the page into text.
 * 'text' / 'forms_tables' are Textract; 'local_ocr' is a local OCR model;
 * 'raw' stores the file without OCR - the vision flow sends the image itself.
 */
export type OcrMode = 'text' | 'forms_tables' | 'local_ocr' | 'raw'
