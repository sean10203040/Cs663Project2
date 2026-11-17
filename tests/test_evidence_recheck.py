import base64
import copy
import hashlib
import io
import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from backend.app import create_app
from backend.evidence_recheck import read_with_recheck
from backend.product_policy_v4 import INSTRUCTION, make_prompt


class EvidenceRecheckTests(unittest.TestCase):
    def setUp(self):
        self.good = {"product_name": "Milk", "brand": "Example",
                     "key_attributes": {"size": "1 L", "best_by": None},
                     "confidence": "high", "guidance": None,
                     "evidence": {"product_name": {"source": "ocr", "quote": "Milk"},
                                  "brand": {"source": "ocr", "quote": "Example"},
                                  "size": {"source": "ocr", "quote": "1 L"}}}
        self.ocr = "Example Milkk 1 L"

    def test_valid_response_needs_no_extra_call(self):
        def forbidden(prompt):
            self.fail("Valid evidence should not incur another model call")
        result, info = read_with_recheck(json.dumps(self.good), "Example Milk 1 L", "original", forbidden)
        self.assertEqual(self.good, result.model_dump())
        self.assertFalse(info["recheck_attempted"])

    def test_image_recheck_repairs_only_flagged_fields(self):
        prompts = []
        repaired = copy.deepcopy(self.good)
        repaired["evidence"]["product_name"]["source"] = "image"
        repaired["brand"] = "Unrequested change"
        repaired["evidence"]["brand"] = {"source": "image", "quote": "Unrequested change"}
        def generate(prompt):
            prompts.append(prompt)
            return json.dumps(repaired)
        result, info = read_with_recheck(json.dumps(self.good), self.ocr, "ORIGINAL IMAGE PROMPT", generate)
        self.assertEqual(len(prompts), 1)
        self.assertIn("ORIGINAL IMAGE PROMPT", prompts[0])
        self.assertIn('"fields_to_recheck": ["product_name"]', prompts[0])
        self.assertEqual(result.brand, "Example")
        self.assertEqual(result.evidence["product_name"].source, "image")
        self.assertEqual(info["removed_fields"], [])

    def test_still_unsupported_quote_becomes_unknown_not_automatically_image(self):
        result, info = read_with_recheck(json.dumps(self.good), self.ocr, "original", lambda p: json.dumps(self.good))
        self.assertIsNone(result.product_name)
        self.assertNotIn("product_name", result.evidence)
        self.assertEqual(result.brand, "Example")
        self.assertEqual(result.key_attributes.size, "1 L")
        self.assertIn("product name", result.guidance)
        self.assertEqual(info["removed_fields"], ["product_name"])

    def test_failed_recheck_preserves_supported_details(self):
        def fail(prompt):
            raise TimeoutError("Fixture timeout")
        result, info = read_with_recheck(json.dumps(self.good), self.ocr, "original", fail)
        self.assertEqual(result.brand, "Example")
        self.assertIsNone(result.product_name)
        self.assertEqual(info["recheck_error_type"], "TimeoutError")

    def test_all_unknown_result_has_low_confidence_and_guidance(self):
        result, info = read_with_recheck(json.dumps(self.good), "unreadable", "original", lambda p: json.dumps(self.good))
        self.assertIsNone(result.product_name)
        self.assertIsNone(result.brand)
        self.assertIsNone(result.key_attributes.size)
        self.assertEqual(result.confidence, "low")
        self.assertTrue(result.guidance)
        self.assertEqual(set(info["removed_fields"]), {"product_name", "brand", "size"})

    def test_malformed_schema_is_not_retried(self):
        def forbidden(prompt):
            self.fail("Malformed schemas must not be silently repaired")
        with self.assertRaises(ValueError):
            read_with_recheck('{"brand":"invented"}', self.ocr, "original", forbidden)

    def test_serving_v4_instruction_matches_frozen_evaluated_instruction(self):
        self.assertEqual(hashlib.sha256(INSTRUCTION.encode()).hexdigest(),
                         "cc071334fdb0ed6fb98e6229d2f8dd6f3db9963f3892333cf154652e36643793")

    def test_route_uses_same_images_for_recheck_and_reports_actual_call_count(self):
        stream = io.BytesIO()
        Image.new("RGB", (10, 10), "white").save(stream, "JPEG")
        image = base64.b64encode(stream.getvalue()).decode()
        token = "fixture-" + "x" * 32
        calls = []
        fixed = copy.deepcopy(self.good)
        fixed["evidence"]["product_name"]["source"] = "image"
        def generate(*args):
            calls.append(args)
            return json.dumps(self.good if len(calls) % 2 else fixed)
        env = {"GOOGLE_CLOUD_PROJECT": "fixture", "LABELLENS_APP_TOKEN": token,
               "LABELLENS_BASE_MODEL": "gemini-3.5-flash",
               "LABELLENS_TUNED_MODEL": "projects/fixture/locations/us/endpoints/product",
               "LABELLENS_QA_TUNED_MODEL": "projects/fixture/locations/us/endpoints/qa",
               "LABELLENS_PRODUCT_POLICY": "v4", "LABELLENS_EVIDENCE_RECHECK": "true"}
        with patch.dict(os.environ, env), TestClient(create_app(generate=generate)) as client:
            response = client.post("/v1/compare", headers={"Authorization": "Bearer " + token},
                                   json={"scan_id": "fixture", "crop_jpeg_base64": image,
                                         "context_jpeg_base64": image, "ocr_text": self.ocr})
            health = client.get("/health").json()
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(len(calls), 4)
        self.assertEqual(data["inference_requests"], 4)
        self.assertEqual(calls[0][2:4], calls[1][2:4])
        self.assertEqual(calls[0][2:], calls[2][2:])
        self.assertEqual(calls[0][4], make_prompt(self.ocr))
        self.assertEqual(data["tuned"]["response"]["model"], env["LABELLENS_TUNED_MODEL"])
        self.assertEqual(health["prompt_version"], "labellens-evidence-v4-candidate")
        self.assertEqual(health["product_processing_version"], "targeted-evidence-recheck-v1")


if __name__ == "__main__":
    unittest.main()
