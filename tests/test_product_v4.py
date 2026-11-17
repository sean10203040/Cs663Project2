import io
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from backend.contracts import PROMPT_VERSION as LIVE_VERSION, make_prompt as live_prompt
from model_dev.prepare_product_v4 import canonical_sha, prepare, read_rows, sha
from model_dev.product_policy_v4 import INSTRUCTION, PROMPT_VERSION, make_prompt, select_policy


class ProductV4Tests(unittest.TestCase):
    def fixture(self, root):
        records = []
        for split, color in (("train", "white"), ("validation", "blue")):
            stream = io.BytesIO()
            Image.new("RGB", (8, 8), color).save(stream, format="PNG")
            blob = stream.getvalue()
            crop = "images/" + sha(blob) + ".png"
            (root / "images").mkdir(exist_ok=True)
            (root / crop).write_bytes(blob)
            records.append({"example_id": split, "product_group": split + "-family", "split": split,
                "crop": crop, "context": None, "ocr_text": "Brand milk NOISY 1009", "reviewed": True,
                "target": {"product_name": "Milk", "brand": "Brand", "key_attributes": {"size": None, "best_by": None},
                    "confidence": "high", "guidance": None, "evidence": {
                        "product_name": {"source": "ocr", "quote": "milk"},
                        "brand": {"source": "ocr", "quote": "Brand"}}}})
        source = root / "examples.jsonl"
        source.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        row = records[0]
        audit = {"source_examples_sha256": sha(source.read_bytes()), "policy_version": PROMPT_VERSION,
            "instruction_sha256": sha(INSTRUCTION.encode()), "decisions": [{
                "example_id": "train", "status": "revise", "notes": ["Fixture visual decision"],
                "source_row_sha256": canonical_sha(row), "image_sha256": Path(row["crop"]).stem,
                "fields": {"size": {"before": None, "before_evidence": None, "value": "100 g",
                    "source": "image", "quote": "NET WT 100g", "reason": "Fixture visual correction"}}}]}
        audit_path = root / "audit.json"
        self.write_audit(audit_path, audit)
        return source, audit_path, audit, records

    def write_audit(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_candidate_preserves_ocr_images_and_excludes_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, audit_path, audit, records = self.fixture(root)
            before = source.read_bytes()
            output = root / "new"
            result = prepare(source, audit_path, output, "gs://fixture/candidate")
            rows = read_rows(output / "examples.jsonl")
            self.assertEqual([r["example_id"] for r in rows], ["train"])
            self.assertEqual(rows[0]["ocr_text"], records[0]["ocr_text"])
            self.assertEqual(rows[0]["target"]["key_attributes"]["size"], "100 g")
            self.assertFalse(rows[0]["candidate_review"]["independently_human_verified"])
            self.assertEqual((output / rows[0]["crop"]).read_bytes(), (root / rows[0]["crop"]).read_bytes())
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(result["counts"]["candidate_train"], 1)
            self.assertFalse((output / "validation.jsonl").exists())
            request = read_rows(output / "train.jsonl")[0]
            self.assertEqual(request["contents"][0]["parts"][1]["text"], make_prompt(records[0]["ocr_text"]))
            self.assertEqual(request["contents"][0]["parts"][0]["fileData"]["mimeType"], "image/png")
            change = json.loads((output / "changes.json").read_text())[0]
            self.assertIsNone(change["before"]["key_attributes"]["size"])
            self.assertEqual(change["after"]["key_attributes"]["size"], "100 g")
            self.assertEqual(result["files"]["train.jsonl"], sha((output / "train.jsonl").read_bytes()))

    def test_changed_source_and_image_rejected_before_output(self):
        for damage in ("source", "image"):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source, audit_path, audit, records = self.fixture(root)
                if damage == "source":
                    source.write_bytes(source.read_bytes() + b"\n")
                else:
                    (root / records[0]["crop"]).write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "changed|hash mismatch"):
                    prepare(source, audit_path, root / "new", "gs://fixture/candidate")
                self.assertFalse((root / "new").exists())

    def test_review_cannot_promote_validation_or_leave_pending(self):
        for damage in ("validation", "pending", "wrong_before", "wrong_policy"):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source, audit_path, audit, records = self.fixture(root)
                if damage == "validation":
                    audit["decisions"][0]["example_id"] = "validation"
                elif damage == "pending":
                    audit["decisions"][0]["status"] = "pending"
                elif damage == "wrong_before":
                    audit["decisions"][0]["fields"]["size"]["before"] = "wrong"
                else:
                    audit["instruction_sha256"] = "changed policy"
                self.write_audit(audit_path, audit)
                with self.assertRaises(ValueError):
                    prepare(source, audit_path, root / "new", "gs://fixture/candidate")
                self.assertFalse((root / "new").exists())

    def test_hold_is_excluded_and_false_ocr_quote_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, audit_path, audit, records = self.fixture(root)
            audit["decisions"][0]["status"] = "hold"
            self.write_audit(audit_path, audit)
            with self.assertRaisesRegex(ValueError, "No candidate"):
                prepare(source, audit_path, root / "new", "gs://fixture/candidate")
            audit["decisions"][0]["status"] = "revise"
            audit["decisions"][0]["fields"]["size"]["source"] = "ocr"
            self.write_audit(audit_path, audit)
            with self.assertRaisesRegex(ValueError, "not supplied"):
                prepare(source, audit_path, root / "new", "gs://fixture/candidate")

    def test_hold_is_not_exported_alongside_accepted_training_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, audit_path, audit, records = self.fixture(root)
            held = json.loads(json.dumps(records[0]))
            held["example_id"] = "held-train"
            records.append(held)
            source.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
            audit["source_examples_sha256"] = sha(source.read_bytes())
            audit["decisions"].append({"example_id": "held-train", "status": "hold",
                "notes": ["Unclear print"], "fields": {}, "source_row_sha256": canonical_sha(held),
                "image_sha256": Path(held["crop"]).stem})
            self.write_audit(audit_path, audit)
            output = root / "new"
            result = prepare(source, audit_path, output, "gs://fixture/candidate")
            self.assertEqual([r["example_id"] for r in read_rows(output / "examples.jsonl")], ["train"])
            self.assertEqual(result["counts"]["held_for_review"], 1)
            self.assertEqual(json.loads((output / "held_for_review.json").read_text())[0]["example_id"], "held-train")

    def test_same_photo_across_splits_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, audit_path, audit, records = self.fixture(root)
            for row in records:
                row["source_photo_sha256"] = "same-original-photo"
            source.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
            audit["source_examples_sha256"] = sha(source.read_bytes())
            audit["decisions"][0]["source_row_sha256"] = canonical_sha(records[0])
            self.write_audit(audit_path, audit)
            with self.assertRaisesRegex(ValueError, "Source photo leaks"):
                prepare(source, audit_path, root / "new", "gs://fixture/candidate")

    def test_policy_selection_keeps_live_v3_unchanged(self):
        self.assertEqual(LIVE_VERSION, "labellens-evidence-v3")
        self.assertEqual(select_policy("v3"), (LIVE_VERSION, live_prompt))
        self.assertEqual(select_policy("v4"), (PROMPT_VERSION, make_prompt))
        self.assertNotEqual(make_prompt("text"), live_prompt("text"))
        with self.assertRaises(ValueError):
            select_policy("unknown")
