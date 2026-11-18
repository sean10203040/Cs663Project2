import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from model_dev.benchmark_ocr import (Export, digest, distance, metrics, predicted_text,
                                      prepare_annotations, score, source_point)


class OcrBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.counter = 0

    def fixture(self, condition="clean", group="product-one", split="validation"):
        self.counter += 1
        folder = self.root / ("export-" + str(self.counter))
        folder.mkdir()
        image = b"synthetic asset fixture " + str(self.counter).encode()
        for name in ("source.png", "P2_input.png", "P3_input.png"):
            (folder / name).write_bytes(image)
        identity = [1, 0, 0, 0, 1, 0, 0, 0, 1]
        stage = {"status": "read", "text": "POCARI SWEAT", "ocr_ms": 120,
                 "engine": "MLKit-Latin-16.0.1", "image": "source.png",
                 "words": [{"text": "POCARI", "polygon": [[1,1],[9,1],[9,9],[1,9]]}],
                 "geometry": {"method": "identity", "output_to_crop": identity}, "crop_origin": [0, 0]}
        record = {"scan_id": "fixture-" + str(self.counter), "product_group": group,
                  "condition": condition, "split": split, "comparison_run": True,
                  "reference_reviewed": True, "reference_text": "POCARI SWEAT",
                  "processing_version": "fixture", "model_sha256": "a"*64,
                  "contrast": False, "crop_policy": "fixture-fixed-crop",
                  "resolution_policy": {"width": 100, "height": 100},
                  "paths": {name: copy.deepcopy(stage) for name in ("P1", "P2", "P3")}}
        self.write(folder, record)
        return folder, record

    @staticmethod
    def write(folder, record):
        (folder / "scan.json").write_text(json.dumps(record), encoding="utf-8")

    def test_edit_metrics_preserve_missing_letters_and_spaces(self):
        m = metrics("POCARI SWEAT", "PO CAR SWEAT")
        self.assertEqual(m["character_edits"], 2)
        self.assertEqual(m["word_edits"], 2)
        self.assertAlmostEqual(m["cer"], 2/12)
        self.assertEqual(distance("abc", ""), 3)
        self.assertFalse(m["exact"])

    def test_normalization_and_insertion_penalty(self):
        self.assertTrue(metrics(" Café\n500 g ", "CAFÉ 500 g")["exact"])
        m = metrics("one", "one two three four")
        self.assertEqual(m["word_accuracy"], -2)
        self.assertIsNone(metrics("", "unexpected")["cer"])
        self.assertTrue(metrics("", "unexpected")["unexpected_text_on_blank_reference"])

    def test_three_paths_share_cohort_and_detection_failures_count(self):
        folder, r = self.fixture()
        r["paths"]["P2"] = {"status": "no_detection", "text": "", "words": [], "ocr_ms": 0}
        self.write(folder, r)
        report = score([folder], self.root/"report")
        self.assertEqual(report["scored_scans"], 1)
        self.assertEqual(report["overall"]["P2"]["cer"], 1)
        self.assertEqual(report["overall"]["P2"]["no_detection"], 1)
        self.assertIsNone(report["overall"]["P2"]["median_ocr_ms"])
        self.assertEqual(report["overall"]["P1"]["scans"], report["overall"]["P2"]["scans"])
        self.assertEqual(report["condition_coverage"]["curved"], 0)
        self.assertTrue((self.root/"report/report.md").exists())

    def test_zips_supported_and_exact_duplicates_not_double_counted(self):
        folder, record = self.fixture()
        archive = self.root/"scan.zip"
        with zipfile.ZipFile(archive, "w") as z:
            for p in folder.iterdir():
                z.write(p, "nested/"+p.name)
        report = score([folder, archive], self.root/"report")
        self.assertEqual(report["scored_scans"], 1)

    def test_no_exports_or_no_checked_reference_does_not_create_scores(self):
        inbox = self.root/"empty"; inbox.mkdir()
        with self.assertRaisesRegex(ValueError, "No real Android"):
            score([inbox], self.root/"report")
        folder, r = self.fixture(); r["reference_reviewed"] = False; self.write(folder, r)
        with self.assertRaisesRegex(ValueError, "manual_reference_not_reviewed"):
            score([folder], self.root/"report")
        self.assertFalse((self.root/"report").exists())

    def test_missing_path_is_unscored_instead_of_comparing_different_cohorts(self):
        one, _ = self.fixture()
        two, r = self.fixture(group="product-two"); del r["paths"]["P3"]; self.write(two,r)
        report = score([one,two], self.root/"report")
        self.assertEqual(report["scored_scans"], 1)
        self.assertEqual(report["unscored"][0]["reason"], "not_a_complete_three_path_comparison")

    def test_product_split_leakage_and_mixed_processing_rejected(self):
        one, _ = self.fixture()
        two, r = self.fixture(split="train")
        with self.assertRaisesRegex(ValueError, "different splits"):
            score([one,two], self.root/"report")
        r["split"] = "validation"; r["contrast"] = True; self.write(two,r)
        with self.assertRaisesRegex(ValueError, "Mixed detector"):
            score([one,two], self.root/"report")

    def test_geometry_maps_back_before_independent_roi_filtering(self):
        _, r = self.fixture()
        stage = r["paths"]["P3"]
        stage["crop_origin"] = [20, 30]
        stage["geometry"] = {"method":"homography", "output_to_crop":[2,0,0,0,2,0,0,0,1]}
        self.assertEqual(source_point(stage,[5,5]), (30,40))
        self.assertEqual(predicted_text(stage,"manual-roi",[25,35,35,45]), "POCARI")
        self.assertEqual(predicted_text(stage,"manual-roi",[0,0,10,10]), "")
        stage["geometry"] = {"method":"cylinder", "source_width":101,"output_width":101,
                             "theta_half_radians":1,"radius_pixels":50}
        self.assertEqual(source_point(stage,[50,5]), (70,35))

    def test_manual_roi_never_borrows_detector_evaluation_region(self):
        folder, r = self.fixture(); r["evaluation_region_xyxy"] = [0,0,100,100]; self.write(folder,r)
        with self.assertRaisesRegex(ValueError, "manual_reference_region_missing"):
            score([folder], self.root/"report", mode="manual-roi")

    def test_annotation_templates_unreviewed_and_bound_to_record_and_image(self):
        folder, r = self.fixture()
        prepare_annotations([folder], self.root/"labels")
        labels = self.root/"labels/annotations.jsonl"
        row = json.loads(labels.read_text())
        self.assertFalse(row["reference_reviewed"])
        self.assertEqual(row["reference_text"], "")
        row.update(reference_reviewed=True,reference_text="POCARI",reference_region_xyxy=[0,0,10,10])
        labels.write_text(json.dumps(row),encoding="utf-8")
        report = score([folder], self.root/"report",mode="manual-roi",annotations=labels)
        self.assertEqual(report["overall"]["P1"]["cer"],0)
        row["source_sha256"] = "wrong"; labels.write_text(json.dumps(row))
        with self.assertRaisesRegex(ValueError,"different scan/image"):
            score([folder], self.root/"other-report",mode="manual-roi",annotations=labels)

    def test_archive_traversal_and_conflicting_scan_ids_rejected(self):
        archive = self.root/"unsafe.zip"
        with zipfile.ZipFile(archive,"w") as z:z.writestr("../scan.json","{}")
        with self.assertRaisesRegex(ValueError,"Unsafe"):
            Export(archive)
        one, r = self.fixture()
        two, s = self.fixture(); s["scan_id"] = r["scan_id"]; self.write(two,s)
        with self.assertRaisesRegex(ValueError,"Conflicting exports"):
            score([one,two],self.root/"report")


if __name__ == "__main__":
    unittest.main()
