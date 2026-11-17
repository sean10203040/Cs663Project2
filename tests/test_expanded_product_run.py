import copy
import json
from pathlib import Path
import tempfile
import unittest

from model_dev.prepare_expanded_product_run import prepare
from model_dev.prepare_product_v4 import canonical_sha, read_rows, sha
from model_dev.product_policy_v4 import INSTRUCTION, PROMPT_VERSION


class ExpandedProductRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "images").mkdir()
        crops = []
        for blob in (b"training image fixture", b"validation image fixture"):
            crop = "images/" + sha(blob) + ".jpg"
            (self.root / crop).write_bytes(blob)
            crops.append(crop)
        target = {"product_name": None, "brand": None,
                  "key_attributes": {"size": None, "best_by": None},
                  "confidence": "low", "guidance": "Show the complete front label.", "evidence": {}}
        self.rows = [{"example_id": str(i), "product_group": "group-" + str(i),
                      "split": "train", "crop": crops[0], "context": None,
                      "ocr_text": "", "target": copy.deepcopy(target)} for i in range(400)]
        self.rows.append({**copy.deepcopy(self.rows[0]), "example_id": "validation",
                          "split": "validation", "product_group": "validation", "crop": crops[1]})
        self.source = self.root / "source.jsonl"
        self.previous = self.root / "previous.jsonl"
        self.source.write_text("".join(json.dumps(r) + "\n" for r in self.rows), encoding="utf-8")
        self.previous.write_text("".join(json.dumps(r) + "\n" for r in self.rows[:287]), encoding="utf-8")
        self.audit = {"source_examples_sha256": sha(self.source.read_bytes()),
                      "previous_examples_sha256": sha(self.previous.read_bytes()),
                      "previous_gcs_prefix": "gs://bucket/frozen", "policy_version": PROMPT_VERSION,
                      "instruction_sha256": sha(INSTRUCTION.encode()), "entries": []}
        for row in self.rows[287:400]:
            self.audit["entries"].append({"example_id": row["example_id"], "number": int(row["example_id"]),
                                          "source_row_sha256": canonical_sha(row),
                                          "image_sha256": Path(crops[0]).stem, "note": "Visual review fixture.",
                                          "disposition": "exclude" if row["example_id"] == "399" else "include",
                                          "target": copy.deepcopy(target)})
        self.audit_path = self.root / "audit.json"
        self.output = self.root / "output"

    def run_prepare(self, prefix="gs://bucket/future"):
        self.audit_path.write_text(json.dumps(self.audit), encoding="utf-8")
        return prepare(self.source, self.previous, self.audit_path, self.output, prefix)

    def test_preserves_previous_rows_and_excludes_validation_and_unresolved_case(self):
        result = self.run_prepare()
        rows = read_rows(self.output / "examples.jsonl")
        self.assertEqual(399, result["counts"]["candidate_train"])
        self.assertEqual(self.rows[:287], rows[:287])
        self.assertTrue(all(r["split"] == "train" for r in rows))
        self.assertNotIn("399", {r["example_id"] for r in rows})
        self.assertFalse(result["cloud_calls_made"])
        requests = read_rows(self.output / "train.jsonl")
        self.assertTrue(all(r["contents"][0]["parts"][0]["fileData"]["fileUri"].startswith("gs://bucket/future/") for r in requests))
        with self.assertRaisesRegex(ValueError, "existing revisions"):
            self.run_prepare()

    def test_rejects_incomplete_review_before_writing(self):
        self.audit["entries"].pop()
        with self.assertRaisesRegex(ValueError, "every held"):
            self.run_prepare()
        self.assertFalse(self.output.exists())

    def test_rejects_wrong_image_binding(self):
        self.audit["entries"][0]["image_sha256"] = "wrong image"
        with self.assertRaisesRegex(ValueError, "original row/image"):
            self.run_prepare()
        self.assertFalse(self.output.exists())

    def test_rejects_reuse_of_running_cloud_prefix(self):
        with self.assertRaisesRegex(ValueError, "distinct planned"):
            self.run_prepare("gs://bucket/frozen/")
        self.assertFalse(self.output.exists())

    def test_rejects_family_leakage(self):
        self.rows[-1]["product_group"] = self.rows[0]["product_group"]
        self.source.write_text("".join(json.dumps(r) + "\n" for r in self.rows), encoding="utf-8")
        self.audit["source_examples_sha256"] = sha(self.source.read_bytes())
        with self.assertRaisesRegex(ValueError, "leakage"):
            self.run_prepare()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
