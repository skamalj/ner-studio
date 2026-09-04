import { useState } from 'react'
import AddIcon from '@mui/icons-material/Add'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import SaveIcon from '@mui/icons-material/Save'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Divider from '@mui/material/Divider'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'

import { deleteTemplate, saveTemplate } from '../api/client'
import { monoFont } from '../theme'

export const NEW_TEMPLATE = '__new__'

interface Props {
  templates: Record<string, string>
  onTemplates: (templates: Record<string, string>) => void
  selected: string
  onSelected: (name: string) => void
  definition: string
  onDefinition: (definition: string) => void
}

export default function TemplatePanel({
  templates,
  onTemplates,
  selected,
  onSelected,
  definition,
  onDefinition,
}: Props) {
  const [newName, setNewName] = useState('')
  const [status, setStatus] = useState<{ kind: 'success' | 'error'; text: string } | null>(
    null,
  )
  const [busy, setBusy] = useState(false)

  const isNew = selected === NEW_TEMPLATE
  const nameToSave = isNew ? newName.trim() : selected

  const pick = (name: string) => {
    onSelected(name)
    if (name === NEW_TEMPLATE) {
      onDefinition('')
      setNewName('')
    } else {
      onDefinition(templates[name] ?? '')
    }
    setStatus(null)
  }

  const save = async () => {
    setBusy(true)
    setStatus(null)
    try {
      const result = await saveTemplate(nameToSave, definition)
      onTemplates(result.templates)
      onSelected(result.name)
      setNewName('')
      setStatus({ kind: 'success', text: result.message })
    } catch (e) {
      setStatus({ kind: 'error', text: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    setBusy(true)
    setStatus(null)
    try {
      const result = await deleteTemplate(selected)
      onTemplates(result.templates)
      onSelected('')
      onDefinition('')
      setStatus({ kind: 'success', text: result.message })
    } catch (e) {
      setStatus({ kind: 'error', text: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Paper variant="outlined" sx={{ p: 2, position: 'sticky', top: 16 }}>
      <Typography variant="subtitle2" gutterBottom>
        Template
      </Typography>
      <Typography variant="caption" color="text.secondary">
        The field list sent to the model. Pick one, edit it, or create a new one.
      </Typography>

      <TextField
        select
        fullWidth
        size="small"
        label="Template name"
        value={selected}
        onChange={(e) => pick(e.target.value)}
        sx={{ mt: 2 }}
      >
        {Object.keys(templates).map((name) => (
          <MenuItem key={name} value={name}>
            {name}
          </MenuItem>
        ))}
        <Divider />
        <MenuItem value={NEW_TEMPLATE}>
          <AddIcon fontSize="small" sx={{ mr: 1 }} /> New template...
        </MenuItem>
      </TextField>

      {isNew && (
        <TextField
          fullWidth
          size="small"
          label="New template name"
          placeholder="e.g. invoice"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          sx={{ mt: 1.5 }}
        />
      )}

      <TextField
        fullWidth
        multiline
        minRows={10}
        maxRows={22}
        size="small"
        label="Template definition"
        placeholder={'Extract the following fields:\nName\nTotal Income\nPAN'}
        value={definition}
        onChange={(e) => onDefinition(e.target.value)}
        sx={{ mt: 1.5, '& textarea': { fontFamily: monoFont, fontSize: 12.5 } }}
      />

      <Stack direction="row" spacing={1} sx={{ mt: 1.5 }}>
        <Button
          variant="contained"
          size="small"
          startIcon={<SaveIcon />}
          disabled={busy || !nameToSave || !definition.trim()}
          onClick={() => void save()}
        >
          Save template
        </Button>
        <Box flex={1} />
        <Button
          size="small"
          color="error"
          startIcon={<DeleteOutlineIcon />}
          disabled={busy || isNew || !selected}
          onClick={() => void remove()}
        >
          Delete
        </Button>
      </Stack>

      {status && (
        <Alert severity={status.kind} sx={{ mt: 1.5 }} onClose={() => setStatus(null)}>
          {status.text}
        </Alert>
      )}
    </Paper>
  )
}
