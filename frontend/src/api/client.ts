import type {
  NerResult,
  OcrMode,
  ProviderInfo,
  SummaryResult,
  SummaryType,
  UploadResponse,
} from '../types'

const BASE = '/api'

async function unwrap<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (body?.detail) {
        message =
          typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      }
    } catch {
      /* non-JSON error body */
    }
    throw new Error(message)
  }
  return (await response.json()) as T
}

async function getJson<T>(path: string): Promise<T> {
  return unwrap<T>(await fetch(`${BASE}${path}`))
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  return unwrap<T>(
    await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  )
}

export const listProviders = (refresh = false) =>
  getJson<ProviderInfo[]>(`/models${refresh ? '?refresh=true' : ''}`)

export const listSummaryTypes = () => getJson<SummaryType[]>('/summary-types')

export const listTemplates = () => getJson<Record<string, string>>('/templates')

export const saveTemplate = (name: string, definition: string) =>
  postJson<{ message: string; name: string; templates: Record<string, string> }>(
    '/templates',
    { name, definition },
  )

export async function deleteTemplate(name: string) {
  return unwrap<{ message: string; templates: Record<string, string> }>(
    await fetch(`${BASE}/templates/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  )
}

export async function uploadDocument(
  file: File,
  mode: OcrMode,
  ocr?: { provider: string; model: string },
) {
  const form = new FormData()
  form.append('file', file)
  form.append('mode', mode)
  if (ocr) {
    form.append('ocr_provider', ocr.provider)
    form.append('ocr_model', ocr.model)
  }
  return unwrap<UploadResponse>(
    await fetch(`${BASE}/documents`, { method: 'POST', body: form }),
  )
}

export interface StreamHandlers<T> {
  onLog?: (entry: { node: string; message: string; detail?: string }) => void
  onResult?: (result: T) => void
  onError?: (message: string) => void
}

/**
 * POST a run request and consume the server-sent event stream it returns.
 * Returns an AbortController so a running job can be cancelled.
 */
function streamRun<T>(
  path: string,
  body: unknown,
  handlers: StreamHandlers<T>,
): AbortController {
  const controller = new AbortController()

  void (async () => {
    try {
      const response = await fetch(`${BASE}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
      if (!response.ok || !response.body) {
        await unwrap(response) // throws with the server's message
        return
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        let split: number
        while ((split = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, split)
          buffer = buffer.slice(split + 2)

          let event = 'message'
          const dataLines: string[] = []
          for (const line of frame.split('\n')) {
            if (line.startsWith('event:')) event = line.slice(6).trim()
            else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
          }
          if (!dataLines.length) continue
          const payload = JSON.parse(dataLines.join('\n'))

          if (event === 'log') handlers.onLog?.(payload)
          else if (event === 'result') handlers.onResult?.(payload as T)
          else if (event === 'error') handlers.onError?.(payload.message ?? 'Run failed')
        }
      }
    } catch (error) {
      if ((error as Error).name === 'AbortError') return
      handlers.onError?.((error as Error).message)
    }
  })()

  return controller
}

export interface NerRequest {
  document_id?: string
  text?: string
  template_name?: string
  template_definition?: string
  provider: string
  model: string
  temperature: number
}

export interface SummarizeRequest {
  document_id?: string
  text?: string
  summary_type: string
  provider: string
  model: string
  temperature: number
}

export const runNerStream = (body: NerRequest, handlers: StreamHandlers<NerResult>) =>
  streamRun<NerResult>('/ner/stream', body, handlers)

export interface VisionRequest {
  document_id: string
  prompt: string
  provider: string
  model: string
  temperature: number
}

export const runVisionStream = (body: VisionRequest, handlers: StreamHandlers<NerResult>) =>
  streamRun<NerResult>('/vision/stream', body, handlers)

export const runSummarizeStream = (
  body: SummarizeRequest,
  handlers: StreamHandlers<SummaryResult>,
) => streamRun<SummaryResult>('/summarize/stream', body, handlers)
