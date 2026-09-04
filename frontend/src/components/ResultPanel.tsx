import { useMemo, useState } from 'react'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import DownloadIcon from '@mui/icons-material/Download'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Tabs from '@mui/material/Tabs'
import Typography from '@mui/material/Typography'

import { monoFont } from '../theme'
import UsageChips from './UsageChips'
import type { NerResult } from '../types'

type Row = { path: string; value: string }

function flatten(value: unknown, prefix = '', rows: Row[] = []): Row[] {
  if (value === null || value === undefined) {
    rows.push({ path: prefix, value: '-' })
  } else if (Array.isArray(value)) {
    if (!value.length) rows.push({ path: prefix, value: '[]' })
    value.forEach((item, i) => flatten(item, `${prefix}[${i}]`, rows))
  } else if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
    if (!entries.length) rows.push({ path: prefix, value: '{}' })
    entries.forEach(([key, child]) =>
      flatten(child, prefix ? `${prefix}.${key}` : key, rows),
    )
  } else {
    rows.push({ path: prefix, value: String(value) })
  }
  return rows
}

function download(name: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  URL.revokeObjectURL(url)
}

export default function ResultPanel({ result }: { result: NerResult }) {
  const [tab, setTab] = useState(0)
  const json = useMemo(
    () => (result.data != null ? JSON.stringify(result.data, null, 2) : ''),
    [result.data],
  )
  const rows = useMemo(() => (result.data != null ? flatten(result.data) : []), [result.data])

  return (
    <Paper variant="outlined">
      <Stack
        direction="row"
        spacing={1}
        useFlexGap
        flexWrap="wrap"
        alignItems="center"
        sx={{ p: 2, pb: 1 }}
      >
        <Typography variant="subtitle2" sx={{ mr: 1 }}>
          Extracted entities
        </Typography>
        <Chip size="small" variant="outlined" label={result.model} />
        <Chip size="small" variant="outlined" label={`${result.chunks} chunk(s)`} />
        <Chip size="small" variant="outlined" label={`${(result.elapsed_ms / 1000).toFixed(1)}s`} />
        <UsageChips usage={result.usage} />
        <Box flex={1} />
        <Button
          size="small"
          startIcon={<ContentCopyIcon />}
          onClick={() => void navigator.clipboard.writeText(json || result.raw)}
        >
          Copy
        </Button>
        <Button
          size="small"
          startIcon={<DownloadIcon />}
          disabled={!json}
          onClick={() => download('extraction.json', json)}
        >
          JSON
        </Button>
      </Stack>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ px: 1, borderBottom: 1, borderColor: 'divider' }}>
        <Tab label="Fields" />
        <Tab label="JSON" />
        <Tab label="Raw response" />
      </Tabs>

      <Box sx={{ maxHeight: 460, overflow: 'auto' }}>
        {tab === 0 &&
          (rows.length ? (
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: '45%' }}>Field</TableCell>
                  <TableCell>Value</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((row, i) => (
                  <TableRow key={`${row.path}-${i}`} hover>
                    <TableCell sx={{ fontFamily: monoFont, fontSize: 12, color: 'text.secondary' }}>
                      {row.path}
                    </TableCell>
                    <TableCell sx={{ fontSize: 13 }}>{row.value}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
              The model did not return parseable JSON. See the raw response tab.
            </Typography>
          ))}
        {tab === 1 && (
          <Box sx={{ p: 2, fontFamily: monoFont, fontSize: 12.5, whiteSpace: 'pre-wrap' }}>
            {json || '-'}
          </Box>
        )}
        {tab === 2 && (
          <Box sx={{ p: 2, fontFamily: monoFont, fontSize: 12.5, whiteSpace: 'pre-wrap' }}>
            {result.raw || '-'}
          </Box>
        )}
      </Box>
    </Paper>
  )
}
