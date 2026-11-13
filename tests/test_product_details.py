"""Product extraction contracts and input wiring; no model inference."""
import base64
import io
import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from backend.app import create_app
from backend.contracts import parse_reading


class ProductDetailsTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "GOOGLE_CLOUD_PROJECT": "fixture-project", "LABELLENS_APP_TOKEN": "fixture-" + "x" * 32,
            "LABELLENS_BASE_MODEL": "gemini-3.5-flash", "GOOGLE_CLOUD_LOCATION": "global",
            "LABELLENS_TUNED_MODEL": "",
            "LABELLENS_QA_TUNED_MODEL": "projects/fixture/locations/us/endpoints/qa-only",
        })
        self.environment.start(); self.addCleanup(self.environment.stop)
        stream = io.BytesIO(); Image.new("RGB", (12, 12), "white").save(stream, "JPEG")
        self.jpeg = base64.b64encode(stream.getvalue()).decode()
        self.payload = {"scan_id": "product-fixture", "crop_jpeg_base64": self.jpeg,
                        "context_jpeg_base64": self.jpeg, "ocr_text": "POCARI SWEAT 500 ml"}
        self.headers = {"Authorization": "Bearer fixture-" + "x" * 32}
        self.reading = {"product_name": "POCARI SWEAT", "brand": None,
                        "key_attributes": {"size": "500 ml", "best_by": None},
                        "confidence": "medium", "guidance": "Turn the bottle to show the date.",
                        "evidence": {"product_name": {"source": "ocr", "quote": "POCARI SWEAT"},
                                     "size": {"source": "ocr", "quote": "500 ml"}}}

    def post(self, generator, payload=None, headers=None):
        with TestClient(create_app(generate=generator)) as client:
            return client.post("/v1/parse", json=payload or self.payload,
                               headers=self.headers if headers is None else headers)

    def test_default_is_base_and_missing_values_remain_null(self):
        calls = []
        def generate(*args):
            calls.append(args); return json.dumps(self.reading)
        response = self.post(generate)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["model_variant"], "base")
        self.assertEqual(data["model"], "gemini-3.5-flash")
        self.assertIsNone(data["reading"]["brand"])
        self.assertIsNone(data["reading"]["key_attributes"]["best_by"])
        self.assertIsNone(data["calibration"])
        model, variant, crop, context, prompt = calls[0]
        self.assertTrue(crop.startswith(b"\xff\xd8")); self.assertEqual(crop, context)
        self.assertIn(self.payload["ocr_text"], prompt)

    def test_missing_matching_tuned_model_does_not_use_qa_endpoint(self):
        def forbidden(*args): self.fail("Existing QA endpoint must not be substituted")
        response = self.post(forbidden, {**self.payload, "model_variant": "tuned"})
        self.assertEqual(response.status_code, 503)

    def test_absent_or_unreadable_fields_need_guidance_not_fabricated_values(self):
        empty = {"product_name": None, "brand": None, "key_attributes": {"size": None, "best_by": None},
                 "confidence": "low", "guidance": "Move closer and reduce glare.", "evidence": {}}
        response = self.post(lambda *args: json.dumps(empty))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["reading"]["product_name"])
        for change in ({"guidance": None}, {"confidence": "high"}):
            self.assertEqual(self.post(lambda *args: json.dumps({**empty, **change})).status_code, 502)

    def test_invalid_or_unsupported_fields_are_not_shown_as_results(self):
        bad = [
            {**self.reading, "brand": "invented brand"},
            {**self.reading, "evidence": {**self.reading["evidence"], "brand": {"source": "image", "quote": "brand"}}},
            {**self.reading, "product_name": 123},
            {**self.reading, "key_attributes": {"size": "500 ml", "best_by": "2027"}},
            {**self.reading, "evidence": {**self.reading["evidence"], "product_name": {"source": "ocr", "quote": "not in supplied text"}}},
        ]
        for reading in bad:
            with self.subTest(reading=reading):
                self.assertEqual(self.post(lambda *args: json.dumps(reading)).status_code, 502)

    def test_auth_and_invalid_images_prevent_inference(self):
        def forbidden(*args): self.fail("Invalid requests must not invoke Gemini")
        self.assertEqual(self.post(forbidden, headers={}).status_code, 401)
        self.assertEqual(self.post(forbidden, {**self.payload, "context_jpeg_base64": "invalid"}).status_code, 422)

    def test_real_sdk_request_wiring_without_network(self):
        captured = {}
        class FakeClient:
            def __init__(inner, **kwargs): captured.update(kwargs); inner.models = inner
            def generate_content(inner, **kwargs):
                captured.update(kwargs)
                return type("Result", (), {"text": json.dumps(self.reading)})()
            def close(inner): captured["closed"] = True
        with patch("google.genai.Client", FakeClient), TestClient(create_app()) as client:
            response = client.post("/v1/parse", json=self.payload, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(captured["model"], "gemini-3.5-flash")
        self.assertEqual(captured["location"], "global")
        self.assertEqual(len(captured["contents"][0].parts), 3)
        config = captured["config"]
        self.assertEqual(config.thinking_config.thinking_level.value, "MINIMAL")
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertTrue(captured["closed"])

    def test_rescan_steps_address_only_missing_fields(self):
        response = self.post(lambda *args: json.dumps(self.reading)).json()
        self.assertEqual([step["fields"] for step in response["rescan_steps"]], [["brand"], ["best_by"]])
        self.assertIn("lot code", response["rescan_steps"][1]["instruction"])

    def test_unconfigured_or_qa_only_comparison_does_not_infer(self):
        def forbidden(*args): self.fail("Comparison must not substitute another task")
        for model in ("", os.environ["LABELLENS_QA_TUNED_MODEL"]):
            with patch.dict(os.environ, {"LABELLENS_TUNED_MODEL": model}), TestClient(create_app(generate=forbidden)) as client:
                result = client.post("/v1/compare", json=self.payload, headers=self.headers)
                self.assertEqual(result.status_code, 200)
                self.assertFalse(result.json()["available"])
                self.assertEqual(result.json()["inference_requests"], 0)
                self.assertEqual(client.post("/v1/compare", json=self.payload).status_code, 401)

    def test_comparison_uses_identical_inputs_and_preserves_partial_failures(self):
        calls = []
        def generate(*args):
            calls.append(args)
            if args[1] == "tuned":
                return json.dumps({**self.reading, "brand": "Unsupported"})
            return json.dumps(self.reading)
        with patch.dict(os.environ, {"LABELLENS_TUNED_MODEL": "projects/fixture/locations/us/endpoints/product"}), TestClient(create_app(generate=generate)) as client:
            result = client.post("/v1/compare", json=self.payload, headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][2:], calls[1][2:])
        self.assertEqual(result.json()["base"]["status"], "ok")
        self.assertEqual(result.json()["tuned"]["error"]["status"], 502)
        self.assertNotIn("agreement", result.json())
        self.assertEqual(len(result.json()["input_sha256"]), 64)

    def test_agreement_is_labeled_not_accuracy_and_counts_shared_nulls(self):
        with patch.dict(os.environ, {"LABELLENS_TUNED_MODEL": "projects/fixture/locations/us/endpoints/product"}), TestClient(create_app(generate=lambda *args: json.dumps(self.reading))) as client:
            result = client.post("/v1/compare", json=self.payload, headers=self.headers).json()
        self.assertEqual(result["agreement"]["equal_fields"], 4)
        self.assertIn("shared missing", result["agreement"]["note"])


if __name__ == "__main__": unittest.main()
