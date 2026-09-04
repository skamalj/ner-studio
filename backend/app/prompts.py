"""Prompts carried over from the original Flask/OpenAI implementation.

The wording is deliberately preserved: these are the prompts the original
`summarization/summarise.py` and `ner/app.py` shipped with, so results stay
comparable across the rewrite.
"""
from __future__ import annotations

# System prompt used for every map/reduce summarization call.
SUMMARIZER_SYSTEM_PROMPT = """
You are an intelligent summarizer. Do not truncate input for any reason when creating summaries, use complete text input.
Adhere to the context provided strictly.
Do not add any information in the summary which is not in the original text.
Documents are being provided to you in parts, so it is ok to provide part summary only.
These will eventually be merged and put together to create one simgle summarty.
""".strip()

# System prompt for entity extraction. The original reused the summarizer
# system prompt; extraction gets its own so JSON-only output is enforceable.
EXTRACTOR_SYSTEM_PROMPT = """
You are a precise information extraction engine.
Adhere to the provided text strictly. Never invent values that are not supported by the text.
When a field cannot be found in the text, return null for it rather than guessing.
Documents may be provided to you in parts, so it is ok to extract from the part you were given.
These parts will eventually be merged into a single result.
Respond with a single valid JSON object and nothing else. Do not wrap it in markdown fences.
""".strip()

# Prefix the original /ner route prepended to every template definition.
ENTITY_PROMPT_PREFIX = (
    "Please extract the following fields from the provided text. "
    "Return extracted fields as json\n\n"
)

# Summary styles offered by the original UI dropdown, verbatim.
SUMMARY_TYPES: dict[str, str] = {
    "concise": "Please provide a concise summary of the given text: {text}",
    "succinct": (
        "Could you give me a succinct summary of the provided text. Clearly highlight "
        "which policy is this and what is the cord product. Provide the summary as if "
        "you are going to start with sales pitch: {text}"
    ),
    "comprehensive": "I'd like a comprehensive and very descriptive summary of the given text: {text}",
    "elaborate": (
        "Can you provide an elaborate summary,broken into muultiple paragraphs, of this "
        "product. Exclude any legal or disclaimer content from this summary.: {text}"
    ),
    "detailed": "Please share a detailed summary of the given text: {text}",
    "policy_seller": (
        "You are an agent who sells health insurance policy to customers without hiding "
        "core details.  Understand the given text and elaborate in paragraphs as a person "
        "explaining to prospective customers: {text}"
    ),
    "points": (
        "Present the summary of following text as a series\n"
        "        of bullet points or a list of key takeaways,\n"
        "        which can be more concise and easier to read. "
        "Points must be separated by newline: {text}"
    ),
    "overview": "Provide 2 line overview Of this product: {text}",
    "in-depth": (
        "Could you provide an in-depth summary of the text: {text}? "
        "Please ensure to include all key points and supporting details."
    ),
}

# Labels for the UI dropdown, in the order the original page listed them.
SUMMARY_TYPE_LABELS: list[tuple[str, str]] = [
    ("concise", "Concise"),
    ("succinct", "Succinct"),
    ("overview", "Overview"),
    ("comprehensive", "Comprehensive"),
    ("elaborate", "Elaborate"),
    ("detailed", "Detailed"),
    ("points", "Bullet Points"),
    ("in-depth", "In-depth"),
    ("policy_seller", "Sales Agent"),
]


def summary_prompt(summary_type: str, text: str) -> str:
    template = SUMMARY_TYPES.get(summary_type)
    if template is None:
        raise ValueError(f"Unknown summary type: {summary_type}")
    return template.format(text=text)


def entity_prompt(template_definition: str) -> str:
    """Compose the extraction instruction the /ner route used to build."""
    return f"{ENTITY_PROMPT_PREFIX}{template_definition.strip()}\n\n"


def extraction_prompt(instruction: str, text: str) -> str:
    return f"{instruction}\n{text}"


# Reduce step: merge partial JSON extractions from several chunks.
MERGE_EXTRACTIONS_PROMPT = """
Several partial JSON extractions were produced from consecutive parts of one document.
Merge them into a single JSON object that follows the field list below.

Rules:
- Prefer a concrete value over null. If two parts disagree, keep the value with more supporting detail.
- Concatenate list-valued fields (such as itemized details) in document order, without duplicates.
- Do not invent values that appear in none of the parts.
- Respond with a single valid JSON object and nothing else.

Requested fields:
{instruction}

Partial extractions:
{partials}
""".strip()

# Reduce step for summaries. The original re-ran the same summary prompt over
# the joined partial summaries; that behaviour is preserved in the graph.
