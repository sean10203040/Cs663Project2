"""Score real Android P1/P2/P3 scan exports against reviewed manual text.

No OCR engine, Gemini inference, model training, or final-test selection is run.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import html
import json
import math
from pathlib import Path, PurePosixPath
import statistics
import unicodedata
import zipfile

PATHS = ("P1", "P2", "P3")
CONDITIONS = ("clean", "curved", "crumpled", "damaged", "occluded", "optical_noise")
NORMALIZATION = "Unicode NFC, casefold, collapse whitespace; preserve digits, accents and punctuation"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalize(text):
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def distance(reference, hypothesis):
    previous = list(range(len(hypothesis) + 1))
    for i, left in enumerate(reference, 1):
        current = [i]
        for j, right in enumerate(hypothesis, 1):
            current.append(min(previous[j] + 1, current[j-1] + 1, previous[j-1] + (left != right)))
        previous = current
    return previous[-1]


def metrics(reference, hypothesis):
    ref, hyp = normalize(reference), normalize(hypothesis)
    words, predicted = ref.split(), hyp.split()
    ce, we = distance(ref, hyp), distance(words, predicted)
    return {"character_edits": ce, "reference_characters": len(ref),
            "word_edits": we, "reference_words": len(words),
            "cer": ce / len(ref) if ref else None,
            "wer": we / len(words) if words else None,
            "word_accuracy": 1 - we / len(words) if words else None,
            "exact": ref == hyp, "unexpected_text_on_blank_reference": not ref and bool(hyp)}


class Export:
    def __init__(self, path):
        self.path = path.resolve()
        self.archive = zipfile.ZipFile(path) if path.suffix.lower() == ".zip" else None
        if self.archive:
            names = self.archive.namelist()
            if len(names) != len(set(names)) or any(not self.safe(n.rstrip("/")) for n in names):
                self.close()
                raise ValueError("Unsafe or duplicate archive path: " + str(path))
            candidates = [n for n in names if PurePosixPath(n).name == "scan.json"]
            if len(candidates) != 1:
                self.close()
                raise ValueError("Each ZIP must contain exactly one scan.json")
            self.prefix = str(PurePosixPath(candidates[0]).parent)
        else:
            self.prefix = "."
        try:
            self.raw = self.read("scan.json", 2_000_000)
            self.record = json.loads(self.raw)
        except Exception:
            self.close()
            raise

    @staticmethod
    def safe(name):
        p = PurePosixPath(name)
        return bool(name) and not p.is_absolute() and ".." not in p.parts and "\\" not in name and ":" not in name

    def read(self, name, maximum=200_000_000):
        if not self.safe(name):
            raise ValueError("Unsafe asset path")
        if self.archive:
            info = self.archive.getinfo(str(PurePosixPath(self.prefix) / name))
            if info.file_size > maximum:
                raise ValueError("Oversized export member")
            return self.archive.read(info)
        target = (self.path.parent / name).resolve()
        if not target.is_relative_to(self.path.parent) or target.stat().st_size > maximum:
            raise ValueError("Invalid asset path or size")
        return target.read_bytes()

    def close(self):
        if self.archive:
            self.archive.close()


def discover(inputs):
    found = set()
    for supplied in inputs:
        p = Path(supplied)
        if not p.exists():
            raise ValueError("Input does not exist: " + str(p))
        if p.is_dir():
            found.update(x.resolve() for x in p.rglob("scan.json"))
            found.update(x.resolve() for x in p.rglob("*.zip"))
        elif p.name == "scan.json" or p.suffix.lower() == ".zip":
            found.add(p.resolve())
        else:
            raise ValueError("Provide scan export ZIPs, scan.json, or a folder of exports")
    return sorted(found)


def export_identity(export):
    source_hash = digest(export.read("source.png"))
    assets = {s["image"] for s in export.record.get("paths", {}).values() if s.get("image")}
    image_hashes = tuple((name, digest(export.read(name))) for name in sorted(assets))
    return digest(export.raw), source_hash, image_hashes


def source_point(stage, point):
    x, y = point
    geometry = stage["geometry"]
    method = geometry["method"]
    if method == "cylinder":
        theta, radius = geometry["theta_half_radians"], geometry["radius_pixels"]
        width, output = geometry["source_width"], geometry["output_width"]
        if output <= 1:
            raise ValueError("Invalid cylinder mapping")
        x = (width - 1) / 2 + radius * math.sin(-theta + 2 * theta * x / (output - 1))
    elif method in ("identity", "homography"):
        m = geometry["output_to_crop"]
        if len(m) != 9:
            raise ValueError("Expected a 3x3 output-to-crop matrix")
        denominator = m[6] * x + m[7] * y + m[8]
        if abs(denominator) < 1e-12:
            raise ValueError("Unprojectable OCR word")
        x, y = (m[0]*x + m[1]*y + m[2])/denominator, (m[3]*x + m[4]*y + m[5])/denominator
    else:
        raise ValueError("Unknown geometry mapping: " + method)
    origin = stage["crop_origin"]
    if len(origin) != 2 or not all(math.isfinite(v) for v in (x, y, *origin)):
        raise ValueError("Invalid mapped coordinates")
    return x + origin[0], y + origin[1]


def predicted_text(stage, mode, region=None):
    if stage["status"] == "no_detection":
        return ""
    if stage["status"] not in ("read", "no_text") or not isinstance(stage.get("text"), str):
        raise ValueError("Unknown or incomplete OCR stage")
    if mode == "selected-label":
        return stage["text"]
    selected = []
    for word in stage["words"]:
        polygon = word["polygon"]
        if len(polygon) < 3 or any(len(p) != 2 for p in polygon):
            raise ValueError("OCR word has no usable polygon")
        mapped = [source_point(stage, p) for p in polygon]
        x = sum(p[0] for p in mapped) / len(mapped)
        y = sum(p[1] for p in mapped) / len(mapped)
        if region[0] <= x <= region[2] and region[1] <= y <= region[3]:
            selected.append(word["text"])
    return " ".join(selected)


def summarize(rows):
    result = {}
    for path in PATHS:
        parts = [r["paths"][path] for r in rows]
        chars = sum(p["reference_characters"] for p in parts)
        words = sum(p["reference_words"] for p in parts)
        ce, we = sum(p["character_edits"] for p in parts), sum(p["word_edits"] for p in parts)
        timings = [p["ocr_ms"] for p in parts if p["ocr_ms"] is not None and p["status"] != "no_detection"]
        result[path] = {"scans": len(rows), "character_edits": ce, "reference_characters": chars,
                        "word_edits": we, "reference_words": words,
                        "cer": ce/chars if chars else None, "wer": we/words if words else None,
                        "word_accuracy": 1-we/words if words else None,
                        "exact_scans": sum(p["exact"] for p in parts),
                        "no_detection": sum(p["status"] == "no_detection" for p in parts),
                        "no_text": sum(p["status"] == "no_text" for p in parts),
                        "unexpected_text_on_blank_reference": sum(p["unexpected_text_on_blank_reference"] for p in parts),
                        "median_ocr_ms": statistics.median(timings) if timings else None}
    return result


def score(inputs, output, split="validation", mode="selected-label", annotations=None):
    if output.exists():
        raise ValueError("Choose a new output folder to preserve prior benchmark reports")
    overrides = {}
    if annotations:
        entries = [json.loads(l) for l in annotations.read_text(encoding="utf-8").splitlines() if l.strip()]
        overrides = {r["scan_id"]: r for r in entries}
        if len(overrides) != len(entries):
            raise ValueError("Duplicate annotation IDs")
    paths = discover(inputs)
    if not paths:
        raise ValueError("No real Android scan exports found. Capture and export P1/P2/P3 comparisons first.")
    seen, source_splits, group_splits = {}, {}, {}
    rows, unscored, signatures = [], [], set()
    matched_annotations = set()
    for path in paths:
        export = Export(path)
        try:
            record = export.record
            scan_id = record["scan_id"]
            identity = export_identity(export)
            binding, source_hash, _ = identity
            if scan_id in seen:
                if seen[scan_id] != identity:
                    raise ValueError("Conflicting exports for scan: " + scan_id)
                continue
            seen[scan_id] = identity
            group, assigned = record.get("product_group"), record.get("split")
            for mapping, key in ((group_splits, group), (source_splits, source_hash)):
                if key:
                    if key in mapping and mapping[key] != assigned:
                        raise ValueError("Product family or image occurs in different splits")
                    mapping[key] = assigned
            annotation = overrides.get(scan_id)
            if annotation:
                matched_annotations.add(scan_id)
                if annotation["scan_record_sha256"] != binding or annotation["source_sha256"] != source_hash:
                    raise ValueError("Annotation refers to a different scan/image")
            reference = annotation if annotation is not None else record
            reason = None
            if assigned != split:
                reason = "different_split"
            elif not record.get("comparison_run") or set(record.get("paths", {})) != set(PATHS):
                reason = "not_a_complete_three_path_comparison"
            elif reference.get("reference_reviewed") is not True or not isinstance(reference.get("reference_text"), str):
                reason = "manual_reference_not_reviewed"
            elif not group:
                reason = "product_group_missing"
            elif record.get("condition") not in CONDITIONS:
                reason = "unknown_capture_condition"
            region = reference.get("reference_region_xyxy")
            if reason is None and mode == "manual-roi":
                width, height = record["resolution_policy"]["width"], record["resolution_policy"]["height"]
                if (not isinstance(region, list) or len(region) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in region)
                        or not 0 <= region[0] < region[2] <= width or not 0 <= region[1] < region[3] <= height):
                    reason = "manual_reference_region_missing_or_invalid"
            if reason:
                unscored.append({"scan_id": scan_id, "reason": reason, "input": str(path)})
                continue
            signature = {k: record.get(k) for k in ("processing_version", "contrast", "crop_policy", "model_sha256")}
            if not signature["model_sha256"]:
                raise ValueError("Comparison lacks detector provenance")
            signature["ocr_engines"] = sorted({s["engine"] for s in record["paths"].values() if s["status"] != "no_detection"})
            signatures.add(json.dumps(signature, sort_keys=True))
            measured = {}
            for name in PATHS:
                stage = record["paths"][name]
                asset_hash = None
                if stage["status"] != "no_detection":
                    asset_hash = digest(export.read(stage["image"]))
                text = predicted_text(stage, mode, region)
                measured[name] = {**metrics(reference["reference_text"], text), "text": text,
                                  "status": stage["status"], "ocr_ms": stage.get("ocr_ms"),
                                  "image_sha256": asset_hash, "geometry": stage.get("geometry"), "geometry_ms": stage.get("geometry_ms")}
            rows.append({"scan_id": scan_id, "product_group": group, "condition": record["condition"],
                         "split": assigned, "input": str(path), "scan_record_sha256": binding,
                         "source_sha256": source_hash, "reference_text": reference["reference_text"],
                         "reference_region_xyxy": region if mode == "manual-roi" else None,
                         "paths": measured, "detection_ms": record.get("detection_ms")})
        finally:
            export.close()
    if set(overrides) - matched_annotations:
        raise ValueError("Annotations include foreign or missing scan IDs")
    if len(signatures) > 1:
        raise ValueError("Mixed detector, OCR, contrast, crop, or processing settings. Score each configuration separately.")
    if not rows:
        raise ValueError("No eligible comparisons: " + json.dumps(dict(Counter(r["reason"] for r in unscored))))
    duplicate_sources = Counter(r["source_sha256"] for r in rows)
    if any(n > 1 for n in duplicate_sources.values()):
        raise ValueError("Repeated source image in the measured cohort; keep one scan per image/configuration")
    report = {"benchmark": "labellens-ocr-three-path-v1", "split": split, "scope": mode,
              "normalization": NORMALIZATION, "configuration": json.loads(next(iter(signatures))),
              "scored_scans": len(rows), "product_groups": len({r["product_group"] for r in rows}),
              "condition_coverage": {c: sum(r["condition"] == c for r in rows) for c in CONDITIONS},
              "overall": summarize(rows),
              "by_condition": {c: summarize([r for r in rows if r["condition"] == c]) for c in CONDITIONS},
              "unscored": unscored, "cloud_requests": 0,
              "paired_cer_outcomes": {a+"_vs_"+b: {"lower_error": sum(r["paths"][a]["character_edits"] < r["paths"][b]["character_edits"] for r in rows),
                                                           "higher_error": sum(r["paths"][a]["character_edits"] > r["paths"][b]["character_edits"] for r in rows),
                                                           "tied": sum(r["paths"][a]["character_edits"] == r["paths"][b]["character_edits"] for r in rows)} for a,b in (("P2","P1"),("P3","P2"))}}
    output.mkdir(parents=True)
    (output/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output/"per_scan.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in rows), encoding="utf-8")
    write_report(report, output/"report.md")
    write_html(report, rows, output/"report.html")
    return report


def write_report(report, path):
    fmt = lambda value: "N/A" if value is None else f"{value*100:.1f}%"
    lines = ["# OCR P1/P2/P3 benchmark", "", f"{report['scored_scans']} real exported scans from {report['product_groups']} product groups; split: {report['split']}; scope: {report['scope']}.", "",
             "| Path | CER (lower is better) | Word accuracy (1 − WER) | Exact scans | Detection failures | Median OCR time (ms) |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, result in report["overall"].items():
        lines.append(f"| {name} | {fmt(result['cer'])} | {fmt(result['word_accuracy'])} | {result['exact_scans']} | {result['no_detection']} | {result['median_ocr_ms']} |")
    lines += ["", "CER and WER use pooled edit counts divided by pooled reference lengths. Word accuracy means 1 − WER; insertions count, so this can be negative. CER can exceed 100%. Empty reviewed references have no per-image denominator; unexpected text is retained as insertions and counted separately.", "",
              "## Capture conditions", "", "| Condition | Scans | P1 CER | P2 CER | P3 CER |", "| --- | ---: | ---: | ---: | ---: |"]
    for c, count in report["condition_coverage"].items():
        lines.append(f"| {c} | {count} | " + " | ".join(fmt(report["by_condition"][c][p]["cer"]) for p in PATHS) + " |")
    lines += ["", "## Interpretation", "",
              "- Every scored scan contributes to every path. No detection and no-text outcomes remain in the denominator; missing paths or unchecked references are listed separately as unscored exports.",
              "- selected-label scope measures end-to-end label reading: use the same complete, manually transcribed target-label text for every path. Extra background text counts as insertions. It does not isolate OCR recognition quality from localization.",
              "- manual-roi scope uses a human-defined source-image rectangle independent of the detector. OCR word centroids are mapped back through the recorded homography or cylindrical transform and crop origin. The same target region is applied to all paths. The detector-generated evaluation_region_xyxy is never used as ground truth.",
              "- OCR times exclude detection, geometry, camera handling, cloud calls and speech. Comparison runs execute all paths, so their total time is not a standalone P1, P2 or P3 capture-to-speech measurement.",
              "- P3 fallback/identity geometry is retained in each per-scan record; do not describe a fallback as successful unwarping. No cloud requests, training, or inferred/manual-label replacement is performed.",
              "- Keep final-test products separate while changing settings. This report checks split separation among supplied exports; it cannot certify that user-entered product IDs correspond to the original training manifest.", "",
              "## Paired outcomes", "", "```json", json.dumps(report["paired_cer_outcomes"], indent=2), "```", "",
              "## Unscored exports", "", "```json", json.dumps(report["unscored"], indent=2), "```", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_html(report, rows, path):
    escape = lambda value: html.escape(str(value))
    percent = lambda value: "N/A" if value is None else f"{value*100:.1f}%"
    summary = "".join("<tr><th>"+name+"</th><td>"+percent(s["cer"])+"</td><td>"+percent(s["word_accuracy"])+"</td><td>"+str(s["no_detection"])+"</td></tr>" for name,s in report["overall"].items())
    cases = []
    for row in rows:
        sections = "<section><h3>Manual reference</h3><pre>"+escape(row["reference_text"])+"</pre></section>"
        for name in PATHS:
            s = row["paths"][name]
            sections += "<section><h3>"+name+" · CER "+percent(s["cer"])+"</h3><p>"+escape(s["status"])+"</p><pre>"+escape(s["text"])+"</pre>"
            if name == "P3":
                sections += "<p>Geometry: "+escape((s["geometry"] or {}).get("status", "unrecorded"))+"</p>"
            sections += "</section>"
        cases.append("<article><h2>"+escape(row["scan_id"])+"</h2><p>"+escape(row["product_group"])+" · "+escape(row["condition"])+"</p><div class=paths>"+sections+"</div></article>")
    page = """<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width"><title>LabelLens OCR benchmark</title><style>body{font:16px system-ui;background:#f4f6f8;color:#20334d;max-width:1400px;margin:auto;padding:24px}table{border-collapse:collapse;background:white}th,td{padding:12px 22px;border:1px solid #ced6e1}article{background:white;border:1px solid #ced6e1;border-radius:12px;padding:20px;margin:24px 0}.paths{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:15px/1.5 system-ui}input{font:inherit;padding:10px;width:min(600px,90%)}@media(max-width:850px){.paths{grid-template-columns:1fr}}</style><h1>LabelLens: OCR pipeline benchmark</h1>"""
    page += "<p>"+str(report["scored_scans"])+" real scans · "+str(report["product_groups"])+" product groups · "+escape(report["split"])+" · "+escape(report["scope"])+"</p>"
    page += "<table><tr><th>Path</th><th>CER ↓</th><th>Word accuracy (1 − WER) ↑</th><th>No detection</th></tr>"+summary+"</table>"
    page += "<p>Same reviewed reference and paired scans for all paths. Detection failures count as empty output. Missing conditions are not evidence of success. OCR timings are not capture-to-speech latency. See report.md for the protocol and limitations.</p><input id=filter aria-label='Filter scans' placeholder='Find a product, condition or failure'>"
    page += "".join(cases)+"""<script>document.getElementById('filter').addEventListener('input',e=>{const q=e.target.value.toLowerCase();document.querySelectorAll('article').forEach(a=>a.hidden=!a.textContent.toLowerCase().includes(q))})</script></html>"""
    path.write_text(page, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, help="Optional hash-bound manual reference JSONL")
    parser.add_argument("--split", choices=("development", "validation", "test"), default="validation")
    parser.add_argument("--scope", choices=("selected-label", "manual-roi"), default="selected-label")
    parser.add_argument("--confirm-final-test", action="store_true")
    parser.add_argument("--prepare-annotations", action="store_true", help="Create unchecked, hash-bound manual-reference templates; do not score")
    args = parser.parse_args()
    if args.split == "test" and not args.confirm_final_test:
        parser.error("Freeze the evaluation protocol before using --confirm-final-test")
    try:
        if args.prepare_annotations:
            prepare_annotations(args.input, args.output)
            return
        result = score(args.input, args.output, args.split, args.scope, args.annotations)
    except (ValueError, KeyError, OSError, zipfile.BadZipFile) as error:
        parser.exit(1, "Benchmark not scored: " + str(error) + "\n")
    print(json.dumps({"scored_scans": result["scored_scans"], "condition_coverage": result["condition_coverage"],
                      "overall": result["overall"]}, indent=2))


def prepare_annotations(inputs, output):
    if output.exists():
        raise ValueError("Choose a new annotation folder; existing labels are never overwritten")
    paths = discover(inputs)
    if not paths:
        raise ValueError("No scan exports found")
    entries, seen = [], {}
    for path in paths:
        export = Export(path)
        try:
            record = export.record
            key = record["scan_id"]
            identity = export_identity(export)
            binding, source_hash, _ = identity
            if key in seen:
                if seen[key] != identity:
                    raise ValueError("Conflicting exports for scan: " + key)
                continue
            seen[key] = identity
            entries.append({"scan_id": key, "scan_record_sha256": binding,
                            "source_sha256": source_hash,
                            "input": str(path), "reference_text": "", "reference_reviewed": False,
                            "reference_region_xyxy": None,
                            "instruction": "Transcribe the target label from the photo, independently of OCR. For manual-roi scope, enter an independent rectangle in source.png pixels; do not copy evaluation_region_xyxy."})
        finally:
            export.close()
    output.mkdir(parents=True)
    (output/"annotations.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False)+"\n" for r in entries), encoding="utf-8")
    print(json.dumps({"templates": len(entries), "reviewed": 0, "scores_computed": False}))


if __name__ == "__main__":
    main()
