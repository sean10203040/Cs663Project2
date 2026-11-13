"""Contract for the existing image-question LabelLens model, separate from extraction."""
import hashlib
import json
from pathlib import Path
import re

from pydantic import Field, StrictBool, model_validator

from .contracts import StrictModel

PROJECT = "spatial-thinker-512218-b0"
BASE_MODEL = "gemini-3.5-flash"
TUNED_MODEL = "projects/1056598944825/locations/us/endpoints/1423735616574586880"
PROMPT_VERSION = "labellens-existing-qa-v1"
RESCAN_GUIDANCE = "I could not answer from this image. Move closer, reduce glare, uncover the label, and try again."


class Answer(StrictModel):
    answer: str = Field(min_length=1, max_length=4000)
    answerable: StrictBool

    @model_validator(mode="after")
    def consistent_answerability(self):
        if not self.answer.strip():
            raise ValueError("Empty answer")
        unknown = self.answer.strip().casefold() == "unanswerable"
        if unknown == self.answerable:
            raise ValueError("Answer and answerable disagree")
        return self


def parse_answer(text: str) -> Answer:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return Answer.model_validate(json.loads(text))


def prompt_digest(prefix: str, suffix: str) -> str:
    return hashlib.sha256(json.dumps([prefix, suffix], ensure_ascii=False).encode("utf-8")).hexdigest()


def load_prompt(path: str) -> dict:
    """Fail closed until the full training prompt has been extracted, not guessed."""
    if not path:
        raise ValueError("Configure LABELLENS_QA_PROMPT_FILE using model_dev.prepare_existing_qa")
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if data.get("prompt_version") != PROMPT_VERSION:
        raise ValueError("Unexpected QA prompt version")
    if not isinstance(data.get("prefix"), str) or not data["prefix"].strip() or not isinstance(data.get("suffix"), str):
        raise ValueError("Invalid QA prompt template")
    if data.get("prompt_sha256") != prompt_digest(data["prefix"], data["suffix"]):
        raise ValueError("QA prompt checksum does not match")
    return data


def make_prompt(template: dict, question: str) -> str:
    if not question.strip():
        raise ValueError("Question is required")
    return template["prefix"] + question.strip() + template["suffix"]


def serving_location(model: str, base_location: str = "global") -> str:
    match = re.fullmatch(r"projects/[^/]+/locations/([^/]+)/endpoints/[^/]+", model)
    if match:
        return match.group(1)
    return base_location


def generate_answer(project: str, model: str, location: str, contents) -> str:
    from google import genai
    from google.genai import types
    client = genai.Client(vertexai=True, project=project, location=location,
        http_options=types.HttpOptions(api_version="v1", timeout=25_000,
            retry_options=types.HttpRetryOptions(attempts=1)))
    try:
        # Identical generation settings for base and tuned. No extra OCR/context,
        # response_schema, system prompt, or Google Search absent from training.
        response = client.models.generate_content(model=model, contents=contents,
            config=types.GenerateContentConfig(temperature=0, max_output_tokens=2048,
                thinking_config=types.ThinkingConfig(thinking_level="MINIMAL")))
        return response.text or ""
    finally:
        client.close()


def failure_status(error: Exception) -> tuple[int, str]:
    """Stable client guidance; never send raw cloud errors/credentials to Android."""
    import httpx
    if isinstance(error, (TimeoutError, httpx.TimeoutException)) or getattr(error, "code", None) == 504:
        return 504, "Gemini timed out. Local OCR is still available; try again."
    code = getattr(error, "code", None)
    if code == 429:
        return 429, "Gemini quota or capacity is temporarily unavailable. Use local OCR and retry later."
    if code in (401, 403):
        return 503, "The backend cannot access Gemini. Check its Google credentials and model permissions."
    if code == 404:
        return 503, "Gemini model was not found. Check the endpoint name and serving region."
    return 502, "Gemini could not complete this request. Use local OCR or try another photo."
