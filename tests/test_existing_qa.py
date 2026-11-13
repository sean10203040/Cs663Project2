"""Offline contract, failure, and held-out evaluation checks. No model calls."""
import base64
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from backend.app import create_app
from backend import qa
from model_dev.prepare_existing_qa import assert_held_out, extract_template, load_sft
from model_dev.evaluate_existing_qa import summarize, user_contents


class ExistingQATests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        prefix = "Fixture instructions. Return answer and answerable.\nQuestion: "
        self.template = {"prefix": prefix, "suffix": "", "prompt_version": qa.PROMPT_VERSION,
                         "prompt_sha256": qa.prompt_digest(prefix, "")}
        self.prompt_path = Path(self.temp.name)/"prompt.json"
        self.prompt_path.write_text(json.dumps(self.template), encoding="utf-8")
        self.env = patch.dict(os.environ, {"LABELLENS_APP_TOKEN": "test-"+"x"*32,
            "LABELLENS_QA_PROMPT_FILE": str(self.prompt_path),
            "GOOGLE_CLOUD_PROJECT": qa.PROJECT, "LABELLENS_QA_TUNED_MODEL": qa.TUNED_MODEL,
            "LABELLENS_QA_BASE_MODEL": qa.BASE_MODEL, "LABELLENS_QA_BASE_LOCATION": "global"})
        self.env.start()
        self.addCleanup(self.env.stop)
        data = io.BytesIO()
        Image.new("RGB", (2, 2)).save(data, "JPEG")
        self.payload = {"scan_id": "fixture", "model_variant": "tuned",
                        "question": "What brand is visible?", "image_jpeg_base64": base64.b64encode(data.getvalue()).decode()}
        self.headers = {"Authorization": "Bearer test-"+"x"*32}

    def post(self, generate, payload=None, headers=None):
        with TestClient(create_app(generate_qa=generate)) as client:
            return client.post("/v1/answer", json=payload or self.payload,
                               headers=self.headers if headers is None else headers)

    def test_single_image_prompt_region_and_answer(self):
        calls = []
        def generated(model, location, image, prompt):
            calls.append((model, location, image, prompt))
            return '{"answer":"deer park","answerable":true}'
        response = self.post(generated)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["qa"]["answer"], "deer park")
        self.assertIsNone(response.json()["guidance"])
        self.assertEqual(calls[0][0:2], (qa.TUNED_MODEL, "us"))
        self.assertEqual(calls[0][3], self.template["prefix"]+self.payload["question"])
        self.assertTrue(calls[0][2].startswith(b"\xff\xd8"))
        self.assertNotIn("confidence", response.json())
        base = self.post(generated, {**self.payload, "model_variant": "base"})
        self.assertEqual(base.status_code, 200)
        self.assertEqual(calls[1][0:2], (qa.BASE_MODEL, "global"))
        self.assertEqual(calls[0][2:], calls[1][2:])

    def test_unanswerable_has_guidance(self):
        response = self.post(lambda *args: '{"answer":"unanswerable","answerable":false}')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["qa"]["answerable"])
        self.assertIn("reduce glare", response.json()["guidance"])

    def test_invalid_outputs_are_errors_not_answers(self):
        for text in ['not json', '{"answer":"deer park","answerable":"true"}',
                     '{"answer":"unanswerable","answerable":true}',
                     '{"answer":"deer park","answerable":false}',
                     '{"answer":"deer park","answerable":true,"confidence":0.99}']:
            with self.subTest(text=text):
                self.assertEqual(self.post(lambda *args: text).status_code, 502)

    def test_authorization_and_input_validation_prevent_calls(self):
        def forbidden(*args):
            self.fail("Must not call Gemini for invalid requests")
        self.assertEqual(self.post(forbidden, headers={}).status_code, 401)
        for payload in [{**self.payload, "question": "  "},
                        {**self.payload, "image_jpeg_base64": "not an image"},
                        {**self.payload, "ocr_text": "unexpected extra input"}]:
            self.assertEqual(self.post(forbidden, payload).status_code, 422)
        with patch.dict(os.environ, {"LABELLENS_QA_TUNED_MODEL": ""}):
            self.assertEqual(self.post(forbidden).status_code, 503)
        with patch.dict(os.environ, {"LABELLENS_QA_PROMPT_FILE": ""}):
            self.assertEqual(self.post(forbidden).status_code, 503)

    def test_cloud_failures_have_stable_guidance(self):
        class CapacityError(Exception):
            code = 429
        for error, status in [(TimeoutError("private"), 504), (CapacityError("private"), 429)]:
            def failed(*args):
                raise error
            response = self.post(failed)
            self.assertEqual(response.status_code, status)
            self.assertNotIn("private", response.text)

    def test_original_sft_reference_is_excluded(self):
        original = {"contents": [
            {"role": "user", "parts": [{"fileData": {"mimeType": "image/jpeg", "fileUri": "gs://fixture/test.jpg"}},
                {"text": self.template["prefix"]+"What brand is visible?"}]},
            {"role": "model", "parts": [{"text": '{"answer":"secret-reference","answerable":true}'}]}]}
        path = Path(self.temp.name)/"test.jsonl"
        path.write_text(json.dumps(original)+"\n", encoding="utf-8")
        row = load_sft(path)[0]
        content = user_contents(row)
        self.assertEqual(len(content), 1)
        self.assertEqual(content[0].role, "user")
        self.assertNotIn("secret-reference", content[0].model_dump_json())
        template = extract_template([row])
        self.assertEqual(template["prefix"], self.template["prefix"])
        with self.assertRaises(ValueError):
            assert_held_out([row], [], [row])

    def test_failures_remain_in_accuracy_denominator(self):
        target = {"answer": "deer park", "answerable": True}
        rows = [{"target": target, "prediction": target, "elapsed_ms": 10},
                {"target": target, "prediction": None, "elapsed_ms": 10},
                {"target": {"answer": "unanswerable", "answerable": False},
                 "prediction": target, "elapsed_ms": 10}]
        stats = summarize(rows)
        self.assertEqual(stats["normalized_exact_accuracy"], 1/3)
        self.assertEqual(stats["answerability_accuracy"], 1/3)
        self.assertEqual(stats["errors"], 1)
        self.assertEqual(stats["token_f1_on_answerable"], .5)
        self.assertEqual(stats["false_answer_rate_when_unanswerable"], 1)

    def test_sdk_generation_configuration_without_network(self):
        from google.genai import types
        # The installed SDK accepts aliases present in the original SFT file.
        content = types.Content.model_validate({"role": "user", "parts": [
            {"fileData": {"fileUri": "gs://fixture/example.jpg", "mimeType": "image/jpeg"}}]})
        self.assertEqual(content.parts[0].file_data.file_uri, "gs://fixture/example.jpg")
        captured = {}
        class FakeClient:
            def __init__(self, **kwargs):
                captured.update(kwargs)
                self.models = self
            def generate_content(self, **kwargs):
                captured.update(kwargs)
                return type("Response", (), {"text": '{"answer":"x","answerable":true}'})()
            def close(self):
                captured["closed"] = True
        with patch("google.genai.Client", FakeClient):
            qa.generate_answer(qa.PROJECT, qa.TUNED_MODEL, "us", [content])
        self.assertEqual(captured["config"].thinking_config.thinking_level.value, "MINIMAL")
        self.assertEqual(captured["http_options"].retry_options.attempts, 1)
        self.assertTrue(captured["closed"])


if __name__ == "__main__":
    unittest.main()
