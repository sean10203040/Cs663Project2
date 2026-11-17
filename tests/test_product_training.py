import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import io
import zipfile
import contextlib
from unittest.mock import patch
from PIL import Image
from backend.contracts import make_prompt
from model_dev.prepare_product_run import prepare, stage_archive


class ProductTrainingTests(unittest.TestCase):
    def fixture(self, root):
        (root/"manifests").mkdir(parents=True);(root/"gemini_requests").mkdir()
        patches=[]
        for split,file,color,brand,ocr in [("train","train_compact_400","white","Silk","Original Almond SILKY SMOOTH"),
                                           ("validation","validation","blue","Example","Original Almond Example")]:
            folder=root/"images"/split;folder.mkdir(parents=True)
            source=folder/"temporary.png";Image.new("RGB",(8,8),color).save(source)
            digest=hashlib.sha256(source.read_bytes()).hexdigest();image=folder/(digest+".png");source.rename(image)
            target={"product_name":"Original Almond","brand":brand,"key_attributes":{"size":None,"best_by":None},
                "confidence":"medium","guidance":None,"evidence":{"product_name":{"source":"ocr","quote":"Original Almond"},"brand":{"source":"ocr","quote":brand}}}
            row={"id":split+"-one","product_family":split+"-family","image":str(image.relative_to(root)).replace("\\","/"),
                "image_sha256":digest,"ml_kit_ocr":ocr,"target":target,"review":"team reference"}
            request={"contents":[{"role":"user","parts":[{"fileData":{"mimeType":"image/png","fileUri":"gs://old-bucket/image.png"}},
                {"text":make_prompt(ocr)}]},{"role":"model","parts":[{"text":json.dumps(target)}]}]}
            (root/"manifests"/(file+".jsonl")).write_text(json.dumps(row)+"\n")
            (root/"gemini_requests"/(file+".jsonl")).write_text(json.dumps(request)+"\n")
            if split=="train":patches.append({"split":file,"id":row["id"],"image":row["image"],
                "fields":{"brand":{"source":"image","quote":"Silk"}},"review_method":"visual review"})
        # Final test format is deliberately invalid; preparation must never read it.
        (root/"manifests/held_out.jsonl").write_text("not training data")
        patch_path=root/"patches.json";patch_path.write_text(json.dumps(patches))
        return patch_path

    def test_review_patch_preserves_raw_ocr_and_remaps_only_train_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/"source";source.mkdir();patches=self.fixture(source)
            result=prepare(source,root/"ready","gs://fixture-bucket/isolated-run",patches)
            self.assertEqual(result["counts"],{"train":1,"validation":1})
            self.assertEqual(result["evidence_source_changes"],1)
            request=json.loads((root/"ready/train.jsonl").read_text())
            self.assertIn('SILKY SMOOTH',request["contents"][0]["parts"][1]["text"])
            self.assertTrue(request["contents"][0]["parts"][0]["fileData"]["fileUri"].startswith("gs://fixture-bucket/isolated-run/images/"))
            self.assertEqual(request["contents"][0]["parts"][0]["fileData"]["mimeType"],"image/png")
            target=json.loads(request["contents"][1]["parts"][0]["text"])
            self.assertEqual(target["brand"],"Silk")
            self.assertEqual(target["evidence"]["brand"]["source"],"image")
            self.assertFalse((root/"ready/held_out.jsonl").exists())
            original=json.loads((source/"manifests/train_compact_400.jsonl").read_text())
            self.assertEqual(original["target"]["evidence"]["brand"]["source"],"ocr")

    def test_changed_input_or_unused_patch_prevents_preparation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/"source";source.mkdir();patches=self.fixture(source)
            path=source/"gemini_requests/train_compact_400.jsonl";request=json.loads(path.read_text())
            request["contents"][0]["parts"][1]["text"]="different prompt"
            path.write_text(json.dumps(request))
            with self.assertRaisesRegex(ValueError,"prompt does not match"):
                prepare(source,root/"ready","gs://fixture-bucket/run",patches)

    def test_nested_archive_staging_excludes_final_test_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/"source";source.mkdir();self.fixture(source)
            (source/"START_HERE.md").write_text("Fixture")
            metadata=io.BytesIO();images=io.BytesIO();held=io.BytesIO()
            with zipfile.ZipFile(metadata,"w") as z:
                for folder in ("manifests","gemini_requests"):
                    for path in (source/folder).glob("*.jsonl"):z.writestr(str(path.relative_to(source)).replace("\\","/"),path.read_bytes())
                z.writestr("START_HERE.md","Fixture")
            with zipfile.ZipFile(images,"w") as z:
                for path in (source/"images").rglob("*.png"):z.writestr(str(path.relative_to(source)).replace("\\","/"),path.read_bytes())
            with zipfile.ZipFile(held,"w") as z:z.writestr("images/held_out/private-final.png",b"not for training")
            archive=root/"release.zip"
            with zipfile.ZipFile(archive,"w") as z:
                z.writestr("release/00_LabelLens_Manifests_and_Schema.zip",metadata.getvalue())
                z.writestr("release/LabelLens_Images_train_01.zip",images.getvalue())
                z.writestr("release/LabelLens_Images_held_out_01.zip",held.getvalue())
            self.assertEqual(stage_archive(archive,root/"staged"),2)
            self.assertFalse((root/"staged/images/held_out").exists())
            self.assertFalse((root/"staged/manifests/held_out.jsonl").exists())

    def test_existing_job_record_blocks_another_submission_before_client_creation(self):
        from model_dev.tune_gemini import main
        with tempfile.TemporaryDirectory() as directory:
            record=Path(directory)/"job.json";record.write_text('{"name":"existing job"}')
            with patch("sys.argv",["tune","--project","fixture","--location","us","--output",str(record)]),patch("google.genai.Client") as client,contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):main()
                client.assert_not_called()

    def test_paired_report_keeps_failures_and_rejects_changed_inputs(self):
        from model_dev.report_product_run import paired
        target={"product_name":"Milk","brand":None,"key_attributes":{"size":None,"best_by":None}}
        base=[{"example_id":"one","product_group":"family","input_sha256":"same-input","target":target,"prediction":None}]
        tuned=[{**base[0],"prediction":target}]
        result=paired(base,tuned)
        self.assertEqual(result["tuned_only_all_fields_correct"],1)
        self.assertEqual(result["all_field_delta_percentage_points"],100)
        with self.assertRaisesRegex(ValueError,"different inputs"):
            paired(base,[{**tuned[0],"input_sha256":"different-input"}])
