"""One authenticated product-details request through the deployed backend; no training."""
import argparse
import base64
import io
import json
from pathlib import Path
import time
import uuid
import httpx
from PIL import Image, ImageOps
from backend.contracts import PROMPT_VERSION, parse_reading


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--ocr-text", default="", help="Actual OCR only; empty is valid for this image-only smoke test")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check-comparison-unconfigured", action="store_true",
                        help="Check comparison availability without running model inference")
    args = parser.parse_args()
    url = args.url.rstrip("/")
    if not url.startswith("https://"): parser.error("Use an HTTPS service URL")
    with Image.open(args.image) as original:
        image = ImageOps.exif_transpose(original).convert("RGB"); image.thumbnail((2048, 2048))
        data = io.BytesIO(); image.save(data, "JPEG", quality=95)
    payload = {"scan_id": "details-smoke-" + uuid.uuid4().hex, "model_variant": "base",
               "crop_jpeg_base64": base64.b64encode(data.getvalue()).decode(), "ocr_text": args.ocr_text}
    token = args.token_file.read_text(encoding="utf-8").strip()
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        denied = client.post(url + "/v1/parse", json=payload)
        assert denied.status_code == 401, f"Expected 401, got {denied.status_code}"
        started = time.perf_counter()
        response = client.post(url + "/v1/parse", json=payload, headers={"Authorization": "Bearer " + token})
        body = response.json()
        report = {"url": url, "unauthenticated_status": denied.status_code,
                  "status": response.status_code, "elapsed_ms": round((time.perf_counter()-started)*1000, 2),
                  "ocr_text": args.ocr_text, "response": body,
                  "scope": "One-image extraction smoke test, not an accuracy evaluation or Android UI test"}
        if args.check_comparison_unconfigured:
            comparison = client.post(url + "/v1/compare", json=payload, headers={"Authorization": "Bearer " + token})
            report["comparison_status"] = comparison.status_code
            report["comparison"] = comparison.json()
            assert comparison.status_code == 200, report["comparison"]
            assert report["comparison"]["available"] is False and report["comparison"]["inference_requests"] == 0
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        response.raise_for_status()
        assert body["scan_id"] == payload["scan_id"] and body["model_variant"] == "base"
        assert body["prompt_version"] == PROMPT_VERSION
        parse_reading(json.dumps(body["reading"]), args.ocr_text)
        assert isinstance(body["rescan_steps"], list)
        print(json.dumps(report, indent=2))


if __name__ == "__main__": main()
