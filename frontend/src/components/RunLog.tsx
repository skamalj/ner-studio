import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked'
import Box from '@mui/material/Box'
import CircularProgress from '@mui/material/CircularProgress'
import Paper from '@mui/material/Paper'
import Typography from '@mui/material/Typography'

import type { LogEntry } from '../types'

const NODE_LABELS: Record<string, string> = {
  prepare: 'Prepare',
  extract_chunk: 'Extract',
  merge: 'Merge',
  split: 'Split',
  summarize_chunk: 'Summarize',
  collect: 'Collect',
}

interface Props {
  entries: LogEntry[]
  running: boolean
}

export default function RunLog({ entries, running }: Props) {
  if (!entries.length && !running) return null
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Typography variant="subtitle2" gutterBottom>
        Pipeline
      </Typography>
      <Box component="ol" sx={{ listStyle: 'none', m: 0, p: 0 }}>
        {entries.map((entry, index) => (
          <Box
            component="li"
            key={`${entry.node}-${index}`}
            sx={{ display: 'flex', gap: 1.25, alignItems: 'flex-start', py: 0.5 }}
          >
            <CheckCircleIcon sx={{ fontSize: 16, mt: '2px', color: 'success.main' }} />
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="body2">
                <Box component="span" sx={{ color: 'text.secondary', mr: 0.75 }}>
                  {NODE_LABELS[entry.node] ?? entry.node}
                </Box>
                {entry.message}
              </Typography>
              {entry.detail && (
                <Typography variant="caption" color="text.secondary">
                  {entry.detail}
                </Typography>
              )}
            </Box>
          </Box>
        ))}
        {running && (
          <Box component="li" sx={{ display: 'flex', gap: 1.25, alignItems: 'center', py: 0.5 }}>
            <CircularProgress size={14} />
            <Typography variant="body2" color="text.secondary">
              Waiting for the model...
            </Typography>
          </Box>
        )}
        {!entries.length && !running && (
          <Box component="li" sx={{ display: 'flex', gap: 1.25, alignItems: 'center' }}>
            <RadioButtonUncheckedIcon sx={{ fontSize: 16, color: 'text.disabled' }} />
            <Typography variant="body2" color="text.secondary">
              Not started
            </Typography>
          </Box>
        )}
      </Box>
    </Paper>
  )
}
