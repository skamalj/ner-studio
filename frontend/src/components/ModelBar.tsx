import HelpOutlineIcon from '@mui/icons-material/HelpOutline'
import RefreshIcon from '@mui/icons-material/Refresh'
import Autocomplete from '@mui/material/Autocomplete'
import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import IconButton from '@mui/material/IconButton'
import ListItemText from '@mui/material/ListItemText'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Slider from '@mui/material/Slider'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'

import { monoFont } from '../theme'
import type {
  ModelOption,
  ModelSelection,
  ProviderId,
  ProviderInfo,
  ProviderStatus,
} from '../types'

interface Props {
  providers: ProviderInfo[]
  value: ModelSelection
  onChange: (next: ModelSelection) => void
  onRefresh: () => void
  loading?: boolean
  /** When true, only models that accept image input are offered. */
  imagesOnly?: boolean
}

/** Cents matter at these magnitudes, so keep two decimals. */
const usd = (price: number) => `$${price.toFixed(2)}`

const STATUS: Record<ProviderStatus, { label: string; color: string }> = {
  ready: { label: 'Ready', color: 'success.main' },
  not_configured: { label: 'Not configured', color: 'text.disabled' },
  // Configured, but nothing is listening - e.g. llama-server not started.
  unreachable: { label: 'Not responding', color: 'warning.main' },
}

export default function ModelBar({
  providers,
  value,
  onChange,
  onRefresh,
  loading = false,
  imagesOnly = false,
}: Props) {
  const active = providers.find((p) => p.id === value.provider)
  const all = active?.models ?? []
  // The vision flow can only use models that accept image input; offering the
  // rest just produces a provider error at run time.
  const options = imagesOnly ? all.filter((m) => m.supports_images) : all
  const selected = options.find((m) => m.id === value.model)

  const selectProvider = (provider: ProviderId) => {
    const info = providers.find((p) => p.id === provider)
    const usable = imagesOnly
      ? (info?.models ?? []).filter((m) => m.supports_images)
      : (info?.models ?? [])
    const preferred = usable.find((m) => m.id === info?.default_model) ?? usable[0]
    onChange({ ...value, provider, model: preferred?.id ?? '' })
  }

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        display: 'grid',
        gap: 2,
        alignItems: 'center',
        gridTemplateColumns: { xs: '1fr', md: '220px minmax(0, 1fr) 220px' },
      }}
    >
      <TextField
        select
        size="small"
        label="Provider"
        value={providers.length ? value.provider : ''}
        disabled={!providers.length}
        onChange={(e) => selectProvider(e.target.value as ProviderId)}
      >
        {providers.map((p) => (
          <MenuItem key={p.id} value={p.id}>
            <ListItemText
              primary={p.label}
              secondary={STATUS[p.status]?.label ?? 'Unknown'}
              slotProps={{
                primary: { fontSize: 14 },
                secondary: {
                  fontSize: 11,
                  color: STATUS[p.status]?.color ?? 'text.disabled',
                },
              }}
            />
            {p.setup_hint && (
              <Tooltip title={p.setup_hint}>
                <HelpOutlineIcon
                  sx={{ fontSize: 15, ml: 1, color: 'text.disabled', flexShrink: 0 }}
                />
              </Tooltip>
            )}
          </MenuItem>
        ))}
      </TextField>

      <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
        <Autocomplete<ModelOption, false, false, true>
          freeSolo
          fullWidth
          size="small"
          options={options}
          value={selected ?? null}
          inputValue={value.model}
          onInputChange={(_, model) => onChange({ ...value, model })}
          getOptionLabel={(option) => (typeof option === 'string' ? option : option.id)}
          isOptionEqualToValue={(option, current) => option.id === current.id}
          renderOption={(props, option) => {
            const { key, ...rest } = props as typeof props & { key: string }
            return (
              <Box
                component="li"
                key={key}
                {...rest}
                sx={{ display: 'flex', gap: 1, alignItems: 'baseline' }}
              >
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Box sx={{ fontFamily: monoFont, fontSize: 12.5 }}>{option.id}</Box>
                  <Box sx={{ fontSize: 11, color: 'text.secondary' }}>
                    {[
                      option.label,
                      option.residency && `runs in ${option.residency}`,
                      ...option.flags,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </Box>
                </Box>
                {option.output_per_1m != null ? (
                  <Box sx={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                    <Box component="span" sx={{ fontWeight: 600 }}>
                      {usd(option.output_per_1m)}
                    </Box>
                    <Box component="span" sx={{ color: 'text.secondary' }}>
                      {' /M out'}
                      {option.input_per_1m != null ? ` · ${usd(option.input_per_1m)} in` : ''}
                    </Box>
                  </Box>
                ) : (
                  <Tooltip
                    title={
                      value.provider === 'bedrock'
                        ? 'No on-demand rate for this model in the region price list - these bill through AWS Marketplace. Add one in backend/pricing.json if you know it.'
                        : 'No price listed. Add one in backend/pricing.json.'
                    }
                  >
                    <Box sx={{ fontSize: 12, color: 'text.disabled', whiteSpace: 'nowrap' }}>
                      price n/a
                    </Box>
                  </Tooltip>
                )}
              </Box>
            )
          }}
          renderInput={(params) => (
            <TextField
              {...params}
              label="Model"
              FormHelperTextProps={
                active && active.status !== 'ready'
                  ? { sx: { color: 'warning.main' } }
                  : undefined
              }
              helperText={
                active && active.status !== 'ready'
                  ? active.setup_hint
                  : imagesOnly
                    ? `${options.length} image-capable models - type to override`
                    : active?.note || `${options.length} models - type to override`
              }
              slotProps={{
                input: {
                  ...params.InputProps,
                  endAdornment: (
                    <>
                      {selected?.flags?.length ? (
                        <Tooltip title={selected.note || selected.flags.join(', ')}>
                          <Chip
                            size="small"
                            color="warning"
                            variant="outlined"
                            label={selected.flags[0]}
                            sx={{ mr: 0.5 }}
                          />
                        </Tooltip>
                      ) : null}
                      {selected?.residency === 'Worldwide' && (
                        <Tooltip title="Global routing - inference may run outside India">
                          <Chip
                            size="small"
                            variant="outlined"
                            label="leaves India"
                            sx={{ mr: 0.5 }}
                          />
                        </Tooltip>
                      )}
                      {selected?.output_per_1m != null && (
                        <Tooltip
                          title={
                            selected.input_per_1m != null
                              ? `${usd(selected.input_per_1m)} per million input tokens, ${usd(selected.output_per_1m)} per million output tokens`
                              : `${usd(selected.output_per_1m)} per million output tokens`
                          }
                        >
                          <Chip
                            size="small"
                            label={`${usd(selected.output_per_1m)} /M out`}
                            sx={{ mr: 0.5 }}
                          />
                        </Tooltip>
                      )}
                      {params.InputProps.endAdornment}
                    </>
                  ),
                },
              }}
            />
          )}
        />
        <Tooltip title="Re-query provider model lists and prices">
          <span>
            <IconButton onClick={onRefresh} disabled={loading} sx={{ mt: 0.25 }}>
              {loading ? <CircularProgress size={20} /> : <RefreshIcon />}
            </IconButton>
          </span>
        </Tooltip>
      </Box>

      <Box>
        <Typography variant="caption" color="text.secondary">
          Temperature
        </Typography>
        <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center' }}>
          <Slider
            size="small"
            min={0}
            max={1}
            step={0.1}
            value={value.temperature}
            onChange={(_, temperature) =>
              onChange({ ...value, temperature: temperature as number })
            }
          />
          <Chip label={value.temperature.toFixed(1)} size="small" />
        </Box>
      </Box>
    </Paper>
  )
}
