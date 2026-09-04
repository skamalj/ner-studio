import { useEffect, useRef, useState } from 'react'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import StopIcon from '@mui/icons-material/Stop'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'

import { runSummarizeStream } from '../api/client'
import DocumentPanel from '../components/DocumentPanel'
import RunLog from '../components/RunLog'
import UsageChips from '../components/UsageChips'
import type {
  LogEntry,
  ModelSelection,
  SummaryResult,
  SummaryType,
  UploadResponse,
} from '../types'

interface Props {
  selection: ModelSelection
  localOcr?: { provider: string; model: string } | null
  summaryTypes: SummaryType[]
  document: UploadResponse | null
  onDocument: (doc: UploadResponse | null) => void
  pastedText: string
  onPastedText: (text: string) => void
}

export default function SummarizationTab({
  selection,
  localOcr = null,
  summaryTypes,
  document,
  onDocument,
  pastedText,
  onPastedText,
}: Props) {
  const [summaryType, setSummaryType] = useState('concise')
  const [log, setLog] = useState<LogEntry[]>([])
  const [result, setResult] = useState<SummaryResult | null>(null)
  const [error, setError] = useState('')
  const [controller, setController] = useState<AbortController | null>(null)

  // A newly loaded document invalidates the summary on screen.
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

  const run = () => {
    setLog([])
    setResult(null)
    setError('')
    const abort = runSummarizeStream(
      {
        document_id: document?.document.id,
        text: document ? undefined : pastedText,
        summary_type: summaryType,
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
            2. Summarize
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems="center">
            <TextField
              select
              size="small"
              label="Summary type"
              value={summaryType}
              onChange={(e) => setSummaryType(e.target.value)}
              sx={{ minWidth: 220 }}
            >
              {summaryTypes.map((type) => (
                <MenuItem key={type.id} value={type.id}>
                  {type.label}
                </MenuItem>
              ))}
            </TextField>
            <Button
              variant="contained"
              startIcon={<PlayArrowIcon />}
              disabled={!hasSource || Boolean(controller)}
              onClick={run}
            >
              Summarize
            </Button>
            {controller && (
              <Button
                color="inherit"
                startIcon={<StopIcon />}
                onClick={() => {
                  controller.abort()
                  setController(null)
                }}
              >
                Stop
              </Button>
            )}
          </Stack>
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
            Long documents are split, summarized in parallel, then summarized again until
            the result fits a single call.
          </Typography>
        </Paper>

        {error && <Alert severity="error">{error}</Alert>}
        <RunLog entries={log} running={Boolean(controller)} />

        {result && (
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center" mb={1.5}>
              <Typography variant="subtitle2" sx={{ mr: 1 }}>
                Summary
              </Typography>
              <Chip size="small" variant="outlined" label={result.model} />
              <Chip size="small" variant="outlined" label={`${result.passes} pass(es)`} />
              <Chip
                size="small"
                variant="outlined"
                label={`${(result.elapsed_ms / 1000).toFixed(1)}s`}
              />
              <UsageChips usage={result.usage} />
              <Box flex={1} />
              <Button
                size="small"
                startIcon={<ContentCopyIcon />}
                onClick={() => void navigator.clipboard.writeText(result.summary)}
              >
                Copy
              </Button>
            </Stack>
            <Typography
              variant="body2"
              sx={{ whiteSpace: 'pre-wrap', maxHeight: 460, overflow: 'auto' }}
            >
              {result.summary}
            </Typography>
          </Paper>
        )}
      </Stack>

      <Paper variant="outlined" sx={{ p: 2, position: 'sticky', top: 16 }}>
        <Typography variant="subtitle2" gutterBottom>
          Summary styles
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Each style is a fixed prompt carried over from the original app - the same
          wording, now run against whichever provider you pick above.
        </Typography>
        <Stack spacing={0.75} sx={{ mt: 1.5 }}>
          {summaryTypes.map((type) => (
            <Chip
              key={type.id}
              label={type.label}
              size="small"
              variant={type.id === summaryType ? 'filled' : 'outlined'}
              color={type.id === summaryType ? 'primary' : 'default'}
              onClick={() => setSummaryType(type.id)}
              sx={{ justifyContent: 'flex-start' }}
            />
          ))}
        </Stack>
      </Paper>
    </Box>
  )
}
