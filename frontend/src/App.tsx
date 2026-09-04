import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import DarkModeIcon from '@mui/icons-material/DarkMode'
import LightModeIcon from '@mui/icons-material/LightMode'
import AppBar from '@mui/material/AppBar'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Container from '@mui/material/Container'
import CssBaseline from '@mui/material/CssBaseline'
import IconButton from '@mui/material/IconButton'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import Toolbar from '@mui/material/Toolbar'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { ThemeProvider } from '@mui/material/styles'
import type { PaletteMode } from '@mui/material'

import { listProviders, listSummaryTypes, listTemplates } from './api/client'
import ModelBar from './components/ModelBar'
import ExtractionTab from './tabs/ExtractionTab'
import SummarizationTab from './tabs/SummarizationTab'
import VisionTab from './tabs/VisionTab'
import { buildTheme } from './theme'
import type {
  ModelSelection,
  ProviderInfo,
  SummaryType,
  UploadResponse,
} from './types'

const THEME_KEY = 'ner-studio-theme'
const VISION_TAB = 2

function TabPanel({ active, children }: { active: boolean; children: ReactNode }) {
  return (
    <Box role="tabpanel" hidden={!active} sx={{ display: active ? 'block' : 'none' }}>
      {children}
    </Box>
  )
}

export default function App() {
  const [mode, setMode] = useState<PaletteMode>(
    () => (localStorage.getItem(THEME_KEY) as PaletteMode) || 'light',
  )
  const theme = useMemo(() => buildTheme(mode), [mode])

  const [tab, setTab] = useState(0)
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [summaryTypes, setSummaryTypes] = useState<SummaryType[]>([])
  const [templates, setTemplates] = useState<Record<string, string>>({})
  // One selection per tab: the vision tab can only use image-capable models,
  // so it keeps its own choice rather than inheriting the text tabs'.
  const [selections, setSelections] = useState<ModelSelection[]>([
    { provider: 'bedrock', model: '', temperature: 0.2 },
    { provider: 'bedrock', model: '', temperature: 0.7 },
    { provider: 'bedrock', model: '', temperature: 0.2 },
  ])
  const selection = selections[tab]
  const setSelection = useCallback(
    (next: ModelSelection) =>
      setSelections((current) => current.map((s, i) => (i === tab ? next : s))),
    [tab],
  )
  const [document, setDocument] = useState<UploadResponse | null>(null)
  const [pastedText, setPastedText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const loadProviders = useCallback(
    async (refresh = false) => {
      setLoading(true)
      try {
        const list = await listProviders(refresh)
        setProviders(list)
        setSelections((current) =>
          current.map((sel, index) => {
            const preferred =
              list.find((p) => p.id === sel.provider && p.configured) ??
              list.find((p) => p.configured) ??
              list[0]
            if (!preferred) return sel
            // Tab 2 is the vision tab; it may only pick image-capable models.
            const usable =
              index === VISION_TAB
                ? preferred.models.filter((m) => m.supports_images)
                : preferred.models
            const keep = preferred.id === sel.provider && usable.some((m) => m.id === sel.model)
            const fallback =
              usable.find((m) => m.id === preferred.default_model) ?? usable[0]
            return {
              ...sel,
              provider: preferred.id,
              model: keep ? sel.model : (fallback?.id ?? ''),
            }
          }),
        )
        setError('')
      } catch (e) {
        setError(`Cannot reach the backend: ${(e as Error).message}`)
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  useEffect(() => {
    void loadProviders()
    listSummaryTypes().then(setSummaryTypes).catch(() => undefined)
    listTemplates().then(setTemplates).catch(() => undefined)
  }, [loadProviders])

  useEffect(() => localStorage.setItem(THEME_KEY, mode), [mode])

  // A configured local provider doubles as an OCR engine on the document panel.
  const localProvider = providers.find((p) => p.id === 'local' && p.configured)
  const localOcr = localProvider
    ? { provider: localProvider.id, model: localProvider.default_model }
    : null

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AppBar position="sticky">
        <Toolbar sx={{ gap: 2 }}>
          <Box>
            <Typography variant="h6" component="h1" lineHeight={1.2}>
              NER Studio
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Textract OCR - LangGraph - Bedrock / Anthropic / OpenAI / Gemini
            </Typography>
          </Box>
          <Box flex={1} />
          <Tooltip title={mode === 'dark' ? 'Light mode' : 'Dark mode'}>
            <IconButton onClick={() => setMode(mode === 'dark' ? 'light' : 'dark')}>
              {mode === 'dark' ? <LightModeIcon /> : <DarkModeIcon />}
            </IconButton>
          </Tooltip>
        </Toolbar>
      </AppBar>

      <Container maxWidth="xl" sx={{ py: 3 }}>
        <Stack spacing={2}>
          {error && <Alert severity="error">{error}</Alert>}

          <ModelBar
            providers={providers}
            value={selection}
            onChange={setSelection}
            onRefresh={() => void loadProviders(true)}
            loading={loading}
            imagesOnly={tab === VISION_TAB}
          />

          <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <Tabs value={tab} onChange={(_, value) => setTab(value)}>
              <Tab label="Entity extraction" />
              <Tab label="Summarization" />
              <Tab label="Vision (no OCR)" />
            </Tabs>
          </Box>

          {/* Every tab stays mounted; only the active one is shown. Switching
              tabs therefore keeps each tab's run and results intact, so two
              approaches can be compared side by side. */}
          <TabPanel active={tab === 0}>
            <ExtractionTab
              selection={selection}
              localOcr={localOcr}
              document={document}
              onDocument={setDocument}
              pastedText={pastedText}
              onPastedText={setPastedText}
              templates={templates}
              onTemplates={setTemplates}
            />
          </TabPanel>
          <TabPanel active={tab === 1}>
            <SummarizationTab
              selection={selection}
              localOcr={localOcr}
              summaryTypes={summaryTypes}
              document={document}
              onDocument={setDocument}
              pastedText={pastedText}
              onPastedText={setPastedText}
            />
          </TabPanel>
          <TabPanel active={tab === 2}>
            <VisionTab selection={selection} templates={templates} />
          </TabPanel>
        </Stack>
      </Container>
    </ThemeProvider>
  )
}
