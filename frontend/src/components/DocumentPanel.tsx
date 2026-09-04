import { useRef, useState } from 'react'
import ArticleIcon from '@mui/icons-material/Article'
import CloudUploadIcon from '@mui/icons-material/CloudUpload'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Collapse from '@mui/material/Collapse'
import LinearProgress from '@mui/material/LinearProgress'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'

import { uploadDocument } from '../api/client'
import { monoFont } from '../theme'
import type { OcrMode, UploadResponse } from '../types'

const ACCEPT = '.pdf,.png,.jpg,.jpeg,.tif,.tiff,.txt,.md,.csv,.json'

interface Props {
  document: UploadResponse | null
  onDocument: (doc: UploadResponse | null) => void
  pastedText: string
  onPastedText: (text: string) => void
  /** OCR engines that run a local model, from the configured providers. */
  localOcr?: { provider: string; model: string } | null
}

export default function DocumentPanel({
  document,
  onDocument,
  pastedText,
  onPastedText,
  localOcr = null,
}: Props) {
  const [mode, setMode] = useState<OcrMode>('forms_tables')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)
  const [showText, setShowText] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const upload = async (file: File) => {
    setBusy(true)
    setError('')
    try {
      const result = await uploadDocument(
        file,
        mode,
        mode === 'local_ocr' && localOcr ? localOcr : undefined,
      )
      onDocument(result)
      onPastedText('')
      setShowText(true)
    } catch (e) {
      setError((e as Error).message)
      onDocument(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={1.5}>
        <Typography variant="subtitle2">1. Document</Typography>
        <TextField
          select
          size="small"
          label="OCR engine"
          value={mode}
          onChange={(e) => setMode(e.target.value as OcrMode)}
          sx={{ width: 260 }}
          helperText={
            mode === 'local_ocr'
              ? `Local model - ${localOcr?.model ?? 'none available'}`
              : 'AWS Textract - billed per page'
          }
        >
          <MenuItem value="forms_tables">Textract - forms + tables</MenuItem>
          <MenuItem value="text">Textract - raw text</MenuItem>
          <MenuItem value="local_ocr" disabled={!localOcr}>
            Local OCR model{localOcr ? '' : ' (no local provider configured)'}
          </MenuItem>
        </TextField>
      </Stack>

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
          p: 3,
          textAlign: 'center',
          cursor: 'pointer',
          borderRadius: 2,
          border: '1.5px dashed',
          borderColor: dragging ? 'primary.main' : 'divider',
          bgcolor: dragging ? 'action.hover' : 'transparent',
          transition: 'border-color .15s, background-color .15s',
        }}
      >
        <CloudUploadIcon color={dragging ? 'primary' : 'disabled'} />
        <Typography variant="body2" sx={{ mt: 0.5 }}>
          Drop a document or image here, or click to browse
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {mode === 'local_ocr'
            ? 'Images are read by the local OCR model - no AWS cost, no page limit.'
            : 'PDF (single page), PNG, JPG, TIFF go through AWS Textract. Plain text is used as-is.'}
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

      {busy && <LinearProgress sx={{ mt: 1.5, borderRadius: 1 }} />}
      {error && (
        <Alert severity="error" sx={{ mt: 1.5 }} onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      {document && (
        <Box sx={{ mt: 1.5 }}>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
            <Chip icon={<ArticleIcon />} label={document.document.filename} size="small" />
            <Chip
              label={
                document.document.ocr_mode === 'local_ocr'
                  ? `Local OCR - ${document.document.line_count} lines`
                  : document.document.ocr_source === 'textract'
                    ? `Textract - ${document.document.line_count} lines`
                    : 'Plain text'
              }
              size="small"
              variant="outlined"
              color={document.document.ocr_mode === 'local_ocr' ? 'secondary' : 'default'}
            />
            <Chip
              label={`${document.document.char_count.toLocaleString()} chars`}
              size="small"
              variant="outlined"
            />
            {Object.keys(document.key_values).length > 0 && (
              <Chip
                label={`${Object.keys(document.key_values).length} form fields`}
                size="small"
                variant="outlined"
              />
            )}
            {document.tables.length > 0 && (
              <Chip label={`${document.tables.length} tables`} size="small" variant="outlined" />
            )}
            <Button size="small" onClick={() => setShowText((v) => !v)}>
              {showText ? 'Hide text' : 'Show text'}
            </Button>
            <Button
              size="small"
              color="inherit"
              startIcon={<DeleteOutlineIcon />}
              onClick={() => onDocument(null)}
            >
              Clear
            </Button>
          </Stack>
          {document.warnings.map((w) => (
            <Alert key={w} severity="warning" sx={{ mt: 1 }}>
              {w}
            </Alert>
          ))}
          <Collapse in={showText}>
            <Box
              sx={{
                mt: 1.5,
                p: 1.5,
                maxHeight: 260,
                overflow: 'auto',
                borderRadius: 1,
                bgcolor: 'action.hover',
                fontFamily: monoFont,
                fontSize: 12,
                whiteSpace: 'pre-wrap',
              }}
            >
              {document.text}
            </Box>
          </Collapse>
        </Box>
      )}

      {!document && (
        <TextField
          multiline
          minRows={3}
          maxRows={10}
          fullWidth
          size="small"
          sx={{ mt: 2 }}
          label="...or paste text directly"
          value={pastedText}
          onChange={(e) => onPastedText(e.target.value)}
        />
      )}
    </Paper>
  )
}
