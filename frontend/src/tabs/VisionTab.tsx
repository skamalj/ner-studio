import { useRef, useState } from 'react'
import CloudUploadIcon from '@mui/icons-material/CloudUpload'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import StopIcon from '@mui/icons-material/Stop'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Divider from '@mui/material/Divider'
import LinearProgress from '@mui/material/LinearProgress'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'

import { runVisionStream, uploadDocument } from '../api/client'
import ResultPanel from '../components/ResultPanel'
import RunLog from '../components/RunLog'
import { monoFont } from '../theme'
import type { LogEntry, ModelSelection, NerResult, UploadResponse } from '../types'

const ACCEPT = '.png,.jpg,.jpeg,.webp,.gif'

/** Same instruction the text pipeline prepends, pointed at an image. */
const IMAGE_PROMPT_PREFIX =
  'Please extract the following fields from the provided image. ' +
  'Return extracted fields as json\n\n'

const DEFAULT_PROMPT =
  'Read this document and return everything on it as JSON. ' +
  'Preserve the wording of labels as they appear.'

interface Props {
  selection: ModelSelection
  templates: Record<string, string>
}

export default function VisionTab({ selection, templates }: Props) {
  const [document, setDocument] = useState<UploadResponse | null>(null)
  const [preview, setPreview] = useState('')
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT)
  const [templateName, setTemplateName] = useState('')
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [log, setLog] = useState<LogEntry[]>([])
  const [result, setResult] = useState<NerResult | null>(null)
  const [error, setError] = useState('')
  const [controller, setController] = useState<AbortController | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const upload = async (file: File) => {
    setUploading(true)
    setError('')
    setResult(null)
    setLog([])
    try {
      // "raw" stores the bytes and skips Textract entirely.
      const uploaded = await uploadDocument(file, 'raw')
      setDocument(uploaded)
      setPreview(URL.createObjectURL(file))
    } catch (e) {
      setError((e as Error).message)
      setDocument(null)
    } finally {
      setUploading(false)
    }
  }

  const pickTemplate = (name: string) => {
    setTemplateName(name)
    if (templates[name]) setPrompt(IMAGE_PROMPT_PREFIX + templates[name].trim())
  }

  const run = () => {
    if (!document) return
    setLog([])
    setResult(null)
    setError('')
    const abort = runVisionStream(
      {
        document_id: document.document.id,
        prompt,
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
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="subtitle2" gutterBottom>
            1. Image
          </Typography>
          <Typography variant="caption" color="text.secondary">
            No OCR runs on this tab. The image is sent to the model as-is, so the model
            does its own reading - this needs a vision-capable model.
          </Typography>

          <Box
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragging(false)
              const file = e.dataTransfer.files?.[0]
              if (file) void upload(file)
            }}
            onClick={() => inputRef.current?.click()}
            sx={{
              mt: 1.5,
              p: 3,
              textAlign: 'center',
              cursor: 'pointer',
              borderRadius: 2,
              border: '1.5px dashed',
              borderColor: dragging ? 'primary.main' : 'divider',
              bgcolor: dragging ? 'action.hover' : 'transparent',
            }}
          >
            <CloudUploadIcon color={dragging ? 'primary' : 'disabled'} />
            <Typography variant="body2" sx={{ mt: 0.5 }}>
              Drop an image here, or click to browse
            </Typography>
            <Typography variant="caption" color="text.secondary">
              PNG, JPG, WEBP or GIF
            </Typography>
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT}
              hidden
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) void upload(file)
                e.target.value = ''
              }}
            />
          </Box>

          {uploading && <LinearProgress sx={{ mt: 1.5, borderRadius: 1 }} />}

          {document && (
            <Stack direction="row" spacing={2} sx={{ mt: 2 }} alignItems="flex-start">
              {preview && (
                <Box
                  component="img"
                  src={preview}
                  alt={document.document.filename}
                  sx={{
                    width: 140,
                    maxHeight: 200,
                    objectFit: 'contain',
                    borderRadius: 1,
                    border: 1,
                    borderColor: 'divider',
                    bgcolor: 'background.paper',
                  }}
                />
              )}
              <Stack spacing={1} alignItems="flex-start">
                <Chip size="small" label={document.document.filename} />
                <Chip
                  size="small"
                  variant="outlined"
                  label={`${(document.document.size / 1024).toFixed(0)} KB - no OCR`}
                />
                <Button
                  size="small"
                  color="inherit"
                  startIcon={<DeleteOutlineIcon />}
                  onClick={() => {
                    setDocument(null)
                    setPreview('')
                  }}
                >
                  Clear
                </Button>
              </Stack>
            </Stack>
          )}
        </Paper>

        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="subtitle2" gutterBottom>
            2. Prompt
          </Typography>
          <TextField
            fullWidth
            multiline
            minRows={5}
            maxRows={16}
            size="small"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            sx={{ mt: 0.5, '& textarea': { fontFamily: monoFont, fontSize: 12.5 } }}
          />
          <Stack direction="row" spacing={1} sx={{ mt: 1.5 }} alignItems="center">
            <Button
              variant="contained"
              startIcon={<PlayArrowIcon />}
              disabled={!document || !prompt.trim() || Boolean(controller)}
              onClick={run}
            >
              Send image to model
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
            {!document && (
              <Typography variant="caption" color="text.secondary">
                Upload an image first.
              </Typography>
            )}
          </Stack>
        </Paper>

        {error && <Alert severity="error">{error}</Alert>}
        <RunLog entries={log} running={Boolean(controller)} />
        {result && <ResultPanel result={result} />}
      </Stack>

      <Paper variant="outlined" sx={{ p: 2, position: 'sticky', top: 16 }}>
        <Typography variant="subtitle2" gutterBottom>
          Start from a template
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Loads a saved field list into the prompt, so the same template can be compared
          against the Textract pipeline on the extraction tab.
        </Typography>
        <TextField
          select
          fullWidth
          size="small"
          label="Template"
          value={templateName}
          onChange={(e) => pickTemplate(e.target.value)}
          sx={{ mt: 2 }}
        >
          {Object.keys(templates).map((name) => (
            <MenuItem key={name} value={name}>
              {name}
            </MenuItem>
          ))}
        </TextField>
        <Button
          size="small"
          sx={{ mt: 1 }}
          onClick={() => {
            setPrompt(DEFAULT_PROMPT)
            setTemplateName('')
          }}
        >
          Reset prompt
        </Button>

        <Divider sx={{ my: 2 }} />
        <Typography variant="caption" color="text.secondary">
          Not every model accepts images. If the one you picked does not, the run fails
          with the provider's own message - switch to a vision model and try again.
        </Typography>
      </Paper>
    </Box>
  )
}
