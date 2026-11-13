import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from model_dev.prepare_examples import prepare
from model_dev.export_sft import export, load_reviewed


class ReviewExportTests(unittest.TestCase):
    def fixture(self, root, reviewed=True):
        source=root/"scan"; source.mkdir()
        Image.new("RGB", (40, 40), "white").save(source/"source.png")
        target={"product_name":"POCARI SWEAT","brand":None,"key_attributes":{"size":None,"best_by":None},
                "confidence":"medium","guidance":"Show size and printed date.",
                "evidence":{"product_name":{"source":"image","quote":"POCARI SWEAT"}}}
        record={"scan_id":"example_1","primary_path":"P2","paths":{"P2":{"image":"source.png","text":"WRONG LEGACY OCR"}},
                "primary_ocr_text":"PO CAR SWEAT", "product_details_ocr_text":"PO CAR SWEAT",
                "product_details_crop":"source.png","product_details_context":None,
                "product_details":{"reading":{**target,"product_name":"PO CAR SWEAT"}},
                "semantic":{"reading":{"product_name":"OLD QA DRAFT MUST NOT BE USED"}},
                "product_review":{"reviewed":reviewed,"target":target,"product_group":"pocari-500ml","split":"train","reviewed_epoch_ms":123}}
        (source/"scan.json").write_text(json.dumps(record),encoding="utf-8")
        return record

    def test_corrected_reference_and_actual_input_survive_export(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root=Path(directory); self.fixture(root)
            prepare(root/"scan",root/"prepared")
            path=root/"prepared/examples.jsonl"
            row=json.loads(path.read_text())
            self.assertTrue(row["reviewed"])
            self.assertEqual(row["target"]["product_name"],"POCARI SWEAT")
            self.assertEqual(row["prediction"]["product_name"],"PO CAR SWEAT")
            self.assertEqual(row["ocr_text"],"PO CAR SWEAT")
            self.assertIsNone(row["context"])
            export(path,root/"sft","gs://fixture-bucket/data")
            example=json.loads((root/"sft/train.jsonl").read_text())
            self.assertEqual(len(example["contents"][0]["parts"]),2)
            self.assertIn("PO CAR SWEAT",example["contents"][0]["parts"][-1]["text"])
            self.assertEqual(json.loads(example["contents"][1]["parts"][0]["text"])["product_name"],"POCARI SWEAT")

    def test_model_draft_is_never_automatically_reviewed(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root=Path(directory);self.fixture(root,reviewed=False)
            prepare(root/"scan",root/"prepared")
            row=json.loads((root/"prepared/examples.jsonl").read_text())
            self.assertFalse(row["reviewed"])
            self.assertEqual(row["target"]["product_name"],"PO CAR SWEAT")
            with self.assertRaisesRegex(ValueError,"No reviewed examples"):
                load_reviewed(root/"prepared/examples.jsonl")

    def test_group_leakage_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root=Path(directory);self.fixture(root)
            prepare(root/"scan",root/"prepared")
            path=root/"prepared/examples.jsonl";row=json.loads(path.read_text())
            path.write_text(json.dumps(row)+"\n"+json.dumps({**row,"split":"test"})+"\n")
            with self.assertRaisesRegex(ValueError,"multiple splits"):load_reviewed(path)

    def test_review_keeps_its_input_snapshot_after_another_analysis(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root=Path(directory);record=self.fixture(root)
            record["product_review"].update({"crop":"source.png","context":None,"ocr_text":"PO CAR SWEAT",
                                           "prediction":record["product_details"]["reading"]})
            record["product_details"]["reading"]={**record["product_details"]["reading"],"product_name":"LATER PREDICTION"}
            record["product_details_ocr_text"]="LATER ANALYSIS WITH DIFFERENT INPUT"
            record["product_details_context"]="source.png"
            (root/"scan/scan.json").write_text(json.dumps(record))
            prepare(root/"scan",root/"prepared")
            row=load_reviewed(root/"prepared/examples.jsonl")[0]
            self.assertIsNone(row["context"])
            self.assertEqual(row["ocr_text"],"PO CAR SWEAT")
            self.assertEqual(row["prediction"]["product_name"],"PO CAR SWEAT")

    def test_evaluation_retains_failures_and_reports_unsupported_values(self):
        from model_dev.evaluate_gemini import summarize
        target={"product_name":"Water","brand":None,"key_attributes":{"size":None,"best_by":None},"confidence":"medium"}
        predicted={**target,"brand":"Invented"}
        result=summarize([{"target":target,"prediction":predicted,"elapsed_ms":100},
                          {"target":target,"prediction":None,"elapsed_ms":300}])
        self.assertEqual(result["valid_response_rate"],0.5)
        self.assertEqual(result["all_field_accuracy"],0)
        self.assertEqual(result["fields"]["product_name"]["accuracy"],0.5)
        self.assertEqual(result["unsupported_value_rate_on_absent_fields"],1/6)
        self.assertEqual(result["latency_median_ms"],200)
