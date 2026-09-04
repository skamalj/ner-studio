# NER Studio

A rebuild of the NER / summarization halves of
[`skamalj/cgpt_python`](https://github.com/skamalj/cgpt_python): same flow, new stack.

**Create a template → upload a document or image → OCR → LLM → JSON entities.**

Three routes to the same answer, switchable in the UI and comparable side by side:

| Route | Path |
| --- | --- |
| Textract → LLM | AWS OCR, then extraction against your template |
| Local OCR → LLM | an OCR model on your own machine, then the same extraction |
| Image → VLM | no OCR at all; the image goes straight to a vision model |

| | Original | This build |
| --- | --- | --- |
| Frontend | Vue 2 + BootstrapVue, single `index.html` | React 18 + TypeScript + MUI (Vite) |
| Backend | Flask, `/ner` calling its own `/summarize` over HTTP | FastAPI + LangGraph pipelines |
| Models | OpenAI GPT-4, hard-coded | Bedrock, Anthropic, OpenAI, Gemini, or any local OpenAI-compatible server - picked per run |
| OCR | Manual, out of band | Textract, a local OCR model, or skipped entirely - chosen per upload |
| Chunking | Equal character slices | Token-aware, boundary-respecting |
| Templates | Flat `.txt` files | Flat `.txt` files (unchanged, drop-in) |

The prompts are carried over verbatim - the summarizer system prompt, all nine summary
styles, and the `"Please extract the following fields ... Return extracted fields as json"`
prefix that wraps every template. The seven original templates ship in `backend/templates/`.

---

## Layout

```
backend/
  app/
    main.py            FastAPI app + CORS
    config.py          settings (.env), AWS profile propagation
    prompts.py         prompts carried over from the original app
    providers.py       chat-model factory, per-provider status and setup hints
    store.py           flat-file template store
    schemas.py         request/response models
    graphs/
      extraction.py    prepare -> extract_chunk* (parallel) -> merge
      summarization.py split -> summarize_chunk* -> collect -> loop | end
      vision.py        look (image straight to a vision model, no OCR)
      common.py        shared state, model invocation, usage accounting
    services/
      ocr.py           OCR engine dispatch (Textract | local model | none)
      textract.py      synchronous Textract (text, or forms + tables)
      catalog.py       the curated Bedrock model catalogue
      pricing.py       AWS Price List lookup, used where the catalogue has no figure
      chunking.py      token-aware splitting
      documents.py     uploaded-document store
      jsonparse.py     JSON recovery from model output
    routers/           meta, templates, documents, analysis
  model_catalog.json   Bedrock model ids, prices and the vision flag
  pricing.json         manual price overrides
  templates/           itr, itr2, itr_extractor, policy, reciept, reciept2, wage
  tests/
frontend/
  src/
    App.tsx            shell, tabs, per-tab model selection + shared document state
    api/client.ts      REST + SSE client
    components/        ModelBar, DocumentPanel, TemplatePanel, RunLog, ResultPanel,
                       UsageChips
    tabs/              ExtractionTab, SummarizationTab, VisionTab
```

## The pipelines

**Extraction** (`app/graphs/extraction.py`)

```
prepare ──┬─> extract_chunk (chunk 1) ──┐
          ├─> extract_chunk (chunk 2) ──┼─> merge ─> END
          └─> extract_chunk (chunk n) ──┘
```

`prepare` normalizes the OCR text and splits it to fit the token budget. Chunks are
extracted in parallel via LangGraph `Send`. One chunk returns as-is; several are
reconciled by a merge call that prefers concrete values and concatenates list fields.

**Vision** (`app/graphs/vision.py`)

```
look -> END
```

A third path that skips OCR entirely: the image is base64'd into the message and sent to
a vision model with a prompt. One node, because a page is one image and there is nothing
to chunk. Uploads for this flow use `mode=raw`, which stores the bytes without calling
Textract. Not every model accepts images - a text-only model returns the provider's own
error ("This model doesn't support the image content block that you provided").

**Summarization** (`app/graphs/summarization.py`)

```
split ──> summarize_chunk* ──> collect ──> split (another pass)
                                       └──> END
```

The original recursion is preserved: while the text does not fit one call it is chunked,
summarized in parallel, joined and summarized again - ending with a single final pass.
Capped at 4 passes.

Both graphs stream their node progress to the UI over SSE, so the pipeline panel fills in
as the run happens.

**Token accounting.** Every model call reports `usage_metadata`, which is summed across the
graph by a reducer on the state. The UI shows it at two levels: per step in the pipeline log
(`valid JSON - 12968 in / 446 out`) and as run totals next to the result
(`23,132 in`, `1,349 out`, `3 calls`). Providers that return no usage metadata show
"tokens not reported" instead of a misleading zero. The totals are also on every API
response as `usage.input_tokens`, `usage.output_tokens` and `usage.calls`.

### Tab state

All three tabs stay mounted; only the active one is displayed. Switching tabs keeps each
tab's run, prompt and results intact, so the OCR path and the vision path can be compared
without re-running either. A run is cleared only when a new document is loaded - including
one loaded from another tab, since the document is shared - so what is on screen always
belongs to the document on screen.

## Choosing an OCR engine

The document panel's **OCR engine** selector decides how a page becomes text before
the extraction LLM sees it:

| Engine | What runs | Cost | Notes |
| --- | --- | --- | --- |
| `forms_tables` | Textract `AnalyzeDocument` (FORMS + TABLES) | per page | Key/values and tables flattened into the text |
| `text` | Textract `DetectDocumentText` | per page | Raw lines only |
| `local_ocr` | An OCR model on the local OpenAI-compatible server | free | Needs `LOCAL_BASE_URL`; no page limit |

`local_ocr` sends the image to the local model with the bare prompt `Text Recognition:`
at temperature 0.02 (`OCR_PROMPT` / `OCR_TEMPERATURE`), and deliberately sends **no system
prompt** - OCR models are trained on a bare instruction and extra framing degrades them.

Measured on the same receipt, GLM-OCR (0.9B, llama.cpp on an Intel Arc iGPU) against
Textract:

| | Textract | GLM-OCR |
| --- | --- | --- |
| Line items | `Flat White` / `x2` / `7.00` on three lines | `Flat White  x2  7.00` on one |
| Tokens into the LLM | 506 | 318 |
| Extraction score | 10/10 | 9/10 |

GLM-OCR keeps the line structure Textract splits apart, which is why it costs fewer tokens
downstream. It is not a strict upgrade: on a degraded scan it misread a store number that
Textract read correctly, so it trades OCR-style errors for model-style ones.

## OCR path vs vision path

The extraction tab OCRs first, the vision tab does not, and which wins depends on the
document. Measured on the same receipt image, same prompt, `ap-south-1`:

| Path | Model | Latency | Tokens | Fields found |
| --- | --- | --- | --- | --- |
| Textract + LLM | nova-pro | 1.5s | 506 in / 241 out | 10/10 |
| Vision | qwen3-vl-235b | 11.2s | 339 in / 242 out | 10/10 |
| Vision | nova-2-lite | 1.6s | 420 in / 223 out | 9/10 |
| Vision | nova-pro | 2.2s | 1363 in / 239 out | 9/10 |
| Vision | nova-lite | 1.4s | 1363 in / 163 out | 9/10 |

On a *clean* image the OCR path is as accurate and cheaper. The vision path earns its
keep on messy scans: on a real photographed receipt, Textract read `Fry` as `Γ.y` and the
LLM faithfully extracted the garbage, while the vision model read the word correctly.
OCR errors are unrecoverable downstream - the model never sees the pixels.

## The model catalogue

`backend/model_catalog.json` is the source of truth for which Bedrock models the app
offers. It exists because two things cannot be discovered from AWS:

* **Image support.** No Bedrock API reports whether a model accepts image input, so the
  catalogue's `vision` flag is the only way to know. The vision tab offers only models
  where it is true; before this, picking a text model there failed at run time with
  *"This model doesn't support the image content block that you provided"*.
* **The callable id.** Availability in ap-south-1 is three-state. `route: in_region` means
  call the bare id; `geo_apac` / `geo_in` require the `apac.*` / `in.*` profile; `global`
  requires `global.*`. The catalogue's **`invoke_id` is what goes on the wire** - `base_id`
  is informational and calling it for a non-in-region model returns a ValidationException.

Loaded by `app/services/catalog.py`. Embedding, video and speech models in the file are
deliberately not loaded - they are not callable through the Converse path. Where the
catalogue has no price, the AWS Price List API is used as a fallback; `pricing.json` still
overrides everything.

Each model carries its residency (`India` / `APAC` / `Worldwide`) and any caveats -
`gated`, `legacy`, `price unconfirmed` - which the UI shows beside the model. Every Claude
model except Sonnet 4 is global-routed from Mumbai, so the model field shows a
**leaves India** chip when one is selected.

### Per-tab model lists

The model selector is per tab, not global:

| Tab | Models offered | Default |
| --- | --- | --- |
| Entity extraction | all 54 | `qwen.qwen3-235b-a22b-2507-v1:0` |
| Summarization | all 54 | same |
| Vision (no OCR) | the 29 with `vision: true` | `google.gemma-3-4b-it` (cheapest) |

Each tab remembers its own model, so GLM-OCR can stay selected on Vision while Bedrock
runs the extraction tab.

## Model prices

The model dropdown lists every model **cheapest output price first**, with the price
beside the id (`$1.04 /M out - $0.26 in`, USD per million tokens); models with no known
price sort last and read `price n/a` rather than showing a guess.

Bedrock prices come from the **AWS Price List API** for the configured region, so they are
real and current. That API identifies a model by a `usagetype` string rather than a model
id, and names the same model two ways (`qwen.qwen3-32b-mantle-output-tokens-standard` and
`Qwen3-32B-output-tokens`), so `app/services/pricing.py` normalizes both to a comparable
key. It reads only plain on-demand rows - batch, flex and priority are separate products,
and some of those rows carry a misleading `inferenceType`, so the usage-type suffix is what
decides. In ap-south-1 this prices 43 of 71 catalog models; the rest (Claude, GPT-5.6) have
no standard on-demand rows there because they bill through AWS Marketplace.

The other providers publish no pricing API. Their prices live in `backend/pricing.json`,
keyed `provider/model-id`, which also overrides any Bedrock price:

```json
{ "anthropic/claude-sonnet-5": { "input_per_1m": 2.0, "output_per_1m": 10.0 } }
```

The shipped Anthropic figures are first-party API rates. Bedrock and Vertex are
partner-operated and priced separately, so those numbers are deliberately not reused for
`bedrock/*` ids.

## Setup

### Backend

```bash
cd backend
uv sync
cp .env.example .env   # then edit
uv run uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

`.env` keys:

| Key | Purpose |
| --- | --- |
| `AWS_PROFILE`, `AWS_REGION` | Textract + Bedrock. An `aws sso login` session works - the profile name is exported to boto3's credential chain. |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` | enable those providers |
| `LOCAL_BASE_URL` | any OpenAI-compatible server (llama.cpp, vLLM, Ollama). Enables the "Local" provider; its models are read from `/v1/models`. e.g. `http://127.0.0.1:8085/v1` |
| `LOCAL_SUPPORTS_IMAGES` | whether the local server's model accepts images (default true - the usual local model here is an OCR VLM) |
| `DEFAULT_PROVIDER`, `DEFAULT_MODEL`, `DEFAULT_TEMPERATURE` | what a run uses when the request names nothing. Ships as Bedrock + `qwen.qwen3-235b-a22b-2507-v1:0`; `qwen.qwen3-32b-v1:0` is the faster, cheaper sibling. |
| `CHUNK_TOKEN_LIMIT` | per-call token budget (default 10000, matching the original) |
| `CORS_ORIGINS` | comma-separated allowed origins |

Every provider carries a `setup_hint` naming exactly what to set - shown on a help icon
beside it in the provider list, and spelled out in amber under the model field whenever the
selected provider is not ready. The hints live in `providers.setup_hint()`, server-side,
because that is where the configuration is read.

A provider with no credentials shows as *Not configured* in the UI; nothing fails at
startup. The local provider is checked differently: having `LOCAL_BASE_URL` set is not
enough, so if nothing answers `/v1/models` it shows **Not responding** and offers no
models, rather than claiming Ready and failing at upload time. The probe uses a 3-second
timeout with no retries, so a dead server does not stall the model list. Model ids are discovered live from each provider's list API and fall back to a
static list, and the model field accepts any id you type.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite serves on 5173 and proxies `/api` to `http://127.0.0.1:8010`
(override with `VITE_API_TARGET`).

### Tests

```bash
cd backend
uv run --group dev pytest tests -q
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | liveness + effective settings |
| GET | `/api/models?refresh=` | providers, configured flag, model ids |
| GET | `/api/summary-types` | the nine summary styles |
| GET | `/api/templates` | `{name: definition}` - same shape as the original |
| GET | `/api/templates/{name}` | one template |
| POST | `/api/templates` | create or overwrite |
| DELETE | `/api/templates/{name}` | delete |
| POST | `/api/documents` | multipart upload; runs Textract; returns text + document id |
| GET | `/api/documents` | recent uploads |
| GET | `/api/documents/{id}/text` | stored OCR text |
| POST | `/api/ner` | extraction, returns the finished result |
| POST | `/api/ner/stream` | extraction, SSE: `log` events then `result` |
| POST | `/api/vision` | image + prompt straight to a vision model, no OCR |
| POST | `/api/vision/stream` | the same, SSE |
| POST | `/api/summarize` | summarization |
| POST | `/api/summarize/stream` | summarization, SSE |

Interactive docs at `http://127.0.0.1:8010/docs`.

## OCR notes

Only the **synchronous** Textract APIs are used, so no S3 bucket is needed:

* `DetectDocumentText` - raw text.
* `AnalyzeDocument` with FORMS + TABLES - also flattens key/value pairs and tables into
  the text sent to the model, which measurably helps on receipts and forms.

That means JPEG, PNG, single-page PDF and single-page TIFF, up to 10 MB. Multi-page PDFs
are rejected with a clear message. `.txt`, `.md`, `.csv` and `.json` uploads skip Textract
and are used as-is.
