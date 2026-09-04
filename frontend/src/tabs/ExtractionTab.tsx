import { useEffect, useRef, useState } from 'react'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import StopIcon from '@mui/icons-material/Stop'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'

import { runNerStream } from '../api/client'
import DocumentPanel from '../components/DocumentPanel'
import ResultPanel from '../components/ResultPanel'
import RunLog from '../components/RunLog'
import TemplatePanel, { NEW_TEMPLATE } from '../components/TemplatePanel'
import type { LogEntry, ModelSelection, NerResult, UploadResponse } from '../types'

interface Props {
  selection: ModelSelection
  localOcr?: { provider: string; model: string } | null
  document: UploadResponse | null
  onDocument: (doc: UploadResponse | null) => void
  pastedText: string
  onPastedText: (text: string) => void
  templates: Record<string, string>
  onTemplates: (templates: Record<string, string>) => void
}

export default function ExtractionTab({
  selection,
  localOcr = null,
  document,
  onDocument,
  pastedText,
  onPastedText,
  templates,
  onTemplates,
}: Props) {
  const [selected, setSelected] = useState('')
  const [definition, setDefinition] = useState('')
  const [log, setLog] = useState<LogEntry[]>([])
  const [result, setResult] = useState<NerResult | null>(null)
  const [error, setError] = useState('')
  const [controller, setController] = useState<AbortController | null>(null)

  // Results are tied to one document. When a different one is loaded - here or
  // from another tab, since the document is shared - drop the stale run.
  const lastDocument = useRef<string | null>(null)
  useEffect(() => {
    const id = document?.document.id ?? null
    if (id !== lastDocument.current) {
      lastDocument.current = id
      setResult(null)
      setLog([])
      setError('')
    }
  }, [document])

  const hasSource = Boolean(document?.document.id || pastedText.trim())
  const canRun = hasSource && definition.trim().length > 0 && !controller

  const run = () => {
    setLog([])
    setResult(null)
    setError('')
    const abort = runNerStream(
      {
        document_id: document?.document.id,
        text: document ? undefined : pastedText,
        template_definition: definition,
        template_name: selected && selected !== NEW_TEMPLATE ? selected : undefined,
        provider: selection.provider,
        model: selection.model,
        temperature: selection.temperature,
      },
      {
        onLog: (entry) => setLog((prev) => [...prev, entry]),
        onResult: (value) => {
          setResult(value)
          setController(null)
        },
        onError: (message) => {
          setError(message)
          setController(null)
        },
      },
    )
    setController(abort)
  }

  const stop = () => {
    controller?.abort()
    setController(null)
  }

  return (
    <Box
      sx={{
        display: 'grid',
        gap: 2,
        alignItems: 'start',
        gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 2fr) minmax(320px, 1fr)' },
      }}
    >
      <Stack spacing={2} sx={{ minWidth: 0 }}>
        <DocumentPanel
          document={document}
          onDocument={onDocument}
          pastedText={pastedText}
          onPastedText={onPastedText}
          localOcr={localOcr}
        />

        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="subtitle2" gutterBottom>
            2. Run extraction
          </Typography>
          <Typography variant="caption" color="text.secondary">
            The template is sent as the field list, prefixed with the standard
            "extract the following fields ... return as json" instruction.
          </Typography>
          <Stack direction="row" spacing={1} sx={{ mt: 1.5 }} alignItems="center">
            <Button
              variant="contained"
              startIcon={<PlayArrowIcon />}
              disabled={!canRun}
              onClick={run}
            >
              Recognize entities
            </Button>
            {controller && (
              <Button color="inherit" startIcon={<StopIcon />} onClick={stop}>
                Stop
              </Button>
            )}
            {!hasSource && (
              <Typography variant="caption" color="text.secondary">
                Upload a document or paste text first.
              </Typography>
            )}
            {hasSource && !definition.trim() && (
              <Typography variant="caption" color="text.secondary">
                Pick or write a template.
              </Typography>
            )}
          </Stack>
        </Paper>

        {error && <Alert severity="error">{error}</Alert>}
        <RunLog entries={log} running={Boolean(controller)} />
        {result && <ResultPanel result={result} />}
      </Stack>

      <TemplatePanel
        templates={templates}
        onTemplates={onTemplates}
        selected={selected}
        onSelected={setSelected}
        definition={definition}
        onDefinition={setDefinition}
      />
    </Box>
  )
}
