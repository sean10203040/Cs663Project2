"""Explicit live gateway smoke test; makes one tuned-model inference request."""
import argparse
import base64
import io
import json
from pathlib import Path
import time
import uuid

import httpx
from PIL import Image, ImageOps

from backend import qa


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    token = args.token_file.read_text(encoding="utf-8").strip()
    with Image.open(args.image) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((2048, 2048))
        stream = io.BytesIO()
        image.save(stream, "JPEG", quality=95)
    payload = {"scan_id": "gateway-smoke-" + uuid.uuid4().hex,
               "model_variant": "tuned", "question": args.question.strip(),
               "image_jpeg_base64": base64.b64encode(stream.getvalue()).decode("ascii")}
    url = args.url.rstrip("/")
    if not url.startswith("https://"):
        parser.error("Use the deployed HTTPS service URL")
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        health = client.get(url + "/health")
        health.raise_for_status()
        assert health.json()["qa_prompt_configured"] and health.json()["qa_tuned_configured"], health.text
        denied = client.post(url + "/v1/answer", json=payload)
        assert denied.status_code == 401, f"Expected application authentication, got {denied.status_code}"
        started = time.perf_counter()
        response = client.post(url + "/v1/answer", json=payload,
                               headers={"Authorization": "Bearer " + token})
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        result = {"url": url, "health": health.json(), "unauthenticated_status": denied.status_code,
                  "authenticated_status": response.status_code, "round_trip_ms": elapsed,
                  "response": response.json()}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        response.raise_for_status()
        body = response.json()
        assert body["scan_id"] == payload["scan_id"]
        assert body["model_variant"] == "tuned" and body["model"] == qa.TUNED_MODEL
        assert body["question"] == args.question.strip()
        qa.Answer.model_validate(body["qa"])
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
