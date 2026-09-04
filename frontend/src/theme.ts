import { createTheme } from '@mui/material/styles'
import type { PaletteMode } from '@mui/material'

const mono = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace"

export const monoFont = mono

export function buildTheme(mode: PaletteMode) {
  const dark = mode === 'dark'
  return createTheme({
    palette: {
      mode,
      primary: { main: dark ? '#8b9dff' : '#3d4ec7' },
      secondary: { main: dark ? '#4fd1c5' : '#0f766e' },
      background: {
        default: dark ? '#0e1117' : '#f6f7fb',
        paper: dark ? '#161b25' : '#ffffff',
      },
      divider: dark ? 'rgba(255,255,255,0.10)' : 'rgba(15,23,42,0.10)',
    },
    shape: { borderRadius: 10 },
    typography: {
      fontFamily: "'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif",
      h6: { fontWeight: 650, letterSpacing: '-0.01em' },
      subtitle2: { fontWeight: 600 },
      button: { textTransform: 'none', fontWeight: 600 },
    },
    components: {
      MuiPaper: {
        styleOverrides: {
          root: { backgroundImage: 'none' },
          outlined: { borderColor: dark ? 'rgba(255,255,255,0.10)' : 'rgba(15,23,42,0.10)' },
        },
      },
      MuiAppBar: {
        defaultProps: { elevation: 0, color: 'inherit' },
        styleOverrides: {
          root: {
            borderBottom: `1px solid ${dark ? 'rgba(255,255,255,0.10)' : 'rgba(15,23,42,0.10)'}`,
            backdropFilter: 'blur(8px)',
          },
        },
      },
      MuiTab: { styleOverrides: { root: { minHeight: 48 } } },
      MuiChip: { styleOverrides: { root: { fontWeight: 500 } } },
      MuiTooltip: { defaultProps: { arrow: true } },
    },
  })
}
