"""Authenticated image+OCR gateway. No credentials or model keys are sent to Android."""
import base64
import binascii
import hmac
import hashlib
import io
import json
import os
from pathlib import Path
import time
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from PIL import Image
from pydantic import Field

from .contracts import PROMPT_VERSION, StrictModel, make_prompt, parse_reading
from . import qa
from .product_tools import agreement, rescan_steps


class ParseRequest(StrictModel):
    scan_id: str = Field(min_length=1, max_length=100)
    model_variant: Literal["base", "tuned"] = "base"
    crop_jpeg_base64: str = Field(min_length=4, max_length=8_000_000)
    context_jpeg_base64: str | None = Field(default=None, max_length=8_000_000)
    ocr_text: str = Field(max_length=30_000)


class AnswerRequest(StrictModel):
    scan_id: str = Field(min_length=1, max_length=100)
    model_variant: Literal["base", "tuned"] = "tuned"
    image_jpeg_base64: str = Field(min_length=4, max_length=8_000_000)
    question: str = Field(min_length=1, max_length=1000, pattern=r"\S")


def require_app_token(authorization):
    token = os.environ.get("LABELLENS_APP_TOKEN", "")
    if len(token) < 24:
        raise HTTPException(503, "Backend authentication is not configured")
    if not authorization or not hmac.compare_digest(authorization, "Bearer " + token):
        raise HTTPException(401, "Invalid application token")


def checked_jpeg(encoded: str) -> bytes:
    try:
        data = base64.b64decode(encoded, validate=True)
        if len(data) > 6_000_000:
            raise ValueError("Image too large")
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "JPEG" or image.width * image.height > 32_000_000:
                raise ValueError("Expected a bounded JPEG image")
            image.verify()
        return data
    except (ValueError, binascii.Error, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "Invalid JPEG image") from exc


def calibration_for(model: str, reported_confidence: str):
    """Only expose empirical rates from a matching, reviewed validation report."""
    path = os.environ.get("LABELLENS_CALIBRATION_FILE")
    if not path:
        return None
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        if report["model"] != model or report["prompt_version"] != PROMPT_VERSION or report["split"] != "validation":
            return None
        bucket = report["buckets"].get(reported_confidence)
        if not bucket or bucket["count"] < 30:
            return None
        return {"validation_examples": bucket["count"], "empirical_all_field_accuracy": bucket["all_field_accuracy"],
                "method": "categorical validation bucket; not a guarantee on an individual scan"}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def create_app(generate=None, generate_qa=None):
    app = FastAPI(title="LabelLens Gemini gateway", version="0.5.0")

    def product_model_settings():
        base = os.environ.get("LABELLENS_BASE_MODEL", qa.BASE_MODEL)
        tuned = os.environ.get("LABELLENS_TUNED_MODEL", "")
        qa_model = os.environ.get("LABELLENS_QA_TUNED_MODEL", "")
        available = bool(tuned and tuned.startswith("projects/") and "/endpoints/" in tuned and tuned != qa_model and tuned != base)
        return base, tuned, available

    @app.get("/health")
    def health():
        try:
            qa.load_prompt(os.environ.get("LABELLENS_QA_PROMPT_FILE", ""))
            prompt_ready = True
        except (OSError, ValueError, TypeError, KeyError):
            prompt_ready = False
        return {"service": "LabelLens", "prompt_version": PROMPT_VERSION,
                "base_configured": bool(os.environ.get("GOOGLE_CLOUD_PROJECT") and os.environ.get("LABELLENS_APP_TOKEN")),
                "tuned_configured": product_model_settings()[2],
                "qa_prompt_configured": prompt_ready,
                "qa_tuned_configured": bool(os.environ.get("LABELLENS_QA_TUNED_MODEL")),
                "note": "Health does not verify credentials, model access or completed tuning"}

    @app.post("/v1/answer")
    def answer(request: AnswerRequest, authorization: str | None = Header(default=None)):
        require_app_token(authorization)
        model = (os.environ.get("LABELLENS_QA_TUNED_MODEL", "") if request.model_variant == "tuned"
                 else os.environ.get("LABELLENS_QA_BASE_MODEL", qa.BASE_MODEL))
        if not model:
            raise HTTPException(503, "QA tuned endpoint is not configured; no base-model substitution was made")
        if request.model_variant == "tuned" and not model.startswith("projects/"):
            raise HTTPException(503, "Configure the full QA tuned endpoint resource name")
        image = checked_jpeg(request.image_jpeg_base64)
        try:
            template = qa.load_prompt(os.environ.get("LABELLENS_QA_PROMPT_FILE", ""))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise HTTPException(503, "QA training prompt is not configured. Run model_dev.prepare_existing_qa and set LABELLENS_QA_PROMPT_FILE.") from exc
        prompt = qa.make_prompt(template, request.question)
        location = qa.serving_location(model, os.environ.get("LABELLENS_QA_BASE_LOCATION", "global"))
        started = time.perf_counter()
        try:
            if generate_qa is not None:  # Offline contract tests only.
                text = generate_qa(model, location, image, prompt)
            else:
                project = os.environ.get("GOOGLE_CLOUD_PROJECT")
                if not project:
                    raise HTTPException(503, "Google Cloud project is not configured")
                from google.genai import types
                contents = [types.Content(role="user", parts=[
                    types.Part.from_bytes(data=image, mime_type="image/jpeg"),
                    types.Part.from_text(text=prompt)])]
                text = qa.generate_answer(project, model, location, contents)
        except HTTPException:
            raise
        except Exception as exc:
            status, detail = qa.failure_status(exc)
            raise HTTPException(status, detail) from exc
        try:
            result = qa.parse_answer(text)
        except (ValueError, TypeError) as exc:
            raise HTTPException(502, "Gemini returned an invalid answer. Local OCR is still available; try another photo.") from exc
        return {"scan_id": request.scan_id, "question": request.question.strip(),
                "model": model, "model_variant": request.model_variant, "model_location": location,
                "prompt_version": qa.PROMPT_VERSION, "prompt_sha256": template["prompt_sha256"],
                "input_mode": "single_image_question", "qa": result.model_dump(),
                "guidance": None if result.answerable else qa.RESCAN_GUIDANCE,
                "backend_ms": round((time.perf_counter()-started)*1000, 2)}

    @app.post("/v1/parse")
    def parse(request: ParseRequest, authorization: str | None = Header(default=None)):
        require_app_token(authorization)
        model = os.environ.get("LABELLENS_TUNED_MODEL", "") if request.model_variant == "tuned" else os.environ.get("LABELLENS_BASE_MODEL", qa.BASE_MODEL)
        if not model:
            raise HTTPException(503, "Fine-tuned Gemini is not configured; no base-model substitution was made")
        if request.model_variant == "tuned" and not product_model_settings()[2]:
            raise HTTPException(503, "Configure a separate product-extraction tuned endpoint; the QA model is not compatible")
        crop = checked_jpeg(request.crop_jpeg_base64)
        context = checked_jpeg(request.context_jpeg_base64) if request.context_jpeg_base64 else None
        started = time.perf_counter()
        try:
            if generate is not None:  # Test injection only; production always calls Gemini.
                text = generate(model, request.model_variant, crop, context, make_prompt(request.ocr_text))
            else:
                project = os.environ.get("GOOGLE_CLOUD_PROJECT")
                if not project:
                    raise HTTPException(503, "Google Cloud project is not configured")
                from google import genai
                from google.genai import types
                client = genai.Client(vertexai=True, project=project,
                    location=qa.serving_location(model, os.environ.get("GOOGLE_CLOUD_LOCATION", "global")),
                    http_options=types.HttpOptions(api_version="v1", timeout=25_000,
                        retry_options=types.HttpRetryOptions(attempts=1)))
                parts = [types.Part.from_bytes(data=crop, mime_type="image/jpeg")]
                if context is not None:
                    parts.append(types.Part.from_bytes(data=context, mime_type="image/jpeg"))
                parts.append(types.Part.from_text(text=make_prompt(request.ocr_text)))
                # Tuned tasks use the same prompt/schema as training. Google notes
                # controlled response schemas may reduce tuned-model quality.
                config = {"temperature": 0, "max_output_tokens": 1600}
                family = os.environ.get("LABELLENS_BASE_MODEL", qa.BASE_MODEL)
                if "gemini-2.5" in family:
                    config["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
                elif "gemini-3" in family:
                    config["thinking_config"] = types.ThinkingConfig(thinking_level="MINIMAL")
                # Same generation settings for the paired product-details comparison.
                config["response_mime_type"] = "application/json"
                try:
                    response = client.models.generate_content(model=model,
                        contents=[types.Content(role="user", parts=parts)],
                        config=types.GenerateContentConfig(**config))
                    text = response.text or ""
                finally:
                    client.close()
            reading = parse_reading(text, request.ocr_text)
        except HTTPException:
            raise
        except (ValueError, TypeError) as exc:
            raise HTTPException(502, "Gemini returned invalid or unsupported structured evidence; rescan or review the image") from exc
        except Exception as exc:
            status, detail = qa.failure_status(exc)
            raise HTTPException(status, detail) from exc
        return {"scan_id": request.scan_id, "model": model, "model_variant": request.model_variant,
                "prompt_version": PROMPT_VERSION, "reading": reading.model_dump(),
                "calibration": calibration_for(model, reading.confidence),
                "rescan_steps": rescan_steps(reading),
                "backend_ms": round((time.perf_counter()-started)*1000, 2),
                "confidence_note": "Reported certainty; only the separate calibration field contains validation measurements"}

    @app.post("/v1/compare")
    def compare_products(request: ParseRequest, authorization: str | None = Header(default=None)):
        require_app_token(authorization)
        base, tuned, available = product_model_settings()
        if not available:
            return {"scan_id": request.scan_id, "available": False, "inference_requests": 0,
                    "reason": "A product-extraction fine-tuned model is not configured yet. The existing question-answer model is a different task. Base product details remain available.",
                    "base_model": base, "tuned_model": None}
        crop = checked_jpeg(request.crop_jpeg_base64)
        context = checked_jpeg(request.context_jpeg_base64) if request.context_jpeg_base64 else b""
        # Snapshot the exact multimodal input before either model is called.
        prompt = make_prompt(request.ocr_text)
        digest = hashlib.sha256(json.dumps({"crop_sha256": hashlib.sha256(crop).hexdigest(),
            "context_sha256": hashlib.sha256(context).hexdigest(), "prompt": prompt}, sort_keys=True).encode()).hexdigest()
        result = {"scan_id": request.scan_id, "available": True, "input_sha256": digest,
                  "prompt_version": PROMPT_VERSION, "inference_requests": 2,
                  "scope": "Same images, OCR, prompt and generation settings; no reference answers sent. Agreement is not accuracy."}
        for variant in ("base", "tuned"):
            try:
                response = parse(request.model_copy(update={"model_variant": variant}), authorization)
                result[variant] = {"status": "ok", "response": response}
            except HTTPException as exc:
                result[variant] = {"status": "error", "error": {"status": exc.status_code, "detail": exc.detail}}
        if all(result[v]["status"] == "ok" for v in ("base", "tuned")):
            from .contracts import ProductReading
            result["agreement"] = agreement(*[ProductReading.model_validate(result[v]["response"]["reading"]) for v in ("base", "tuned")])
        return result

    return app


app = create_app()
