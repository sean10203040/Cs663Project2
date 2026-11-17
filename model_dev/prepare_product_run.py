"""Stage the November dataset's compact train/validation inputs without touching final tests."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import io
import zipfile
from PIL import Image
from backend.contracts import INSTRUCTION, PROMPT_VERSION, make_prompt, parse_reading


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def stage_archive(archive, destination):
    """Extract only the approved compact training and validation inputs."""
    if destination.exists() and any(destination.iterdir()):raise ValueError("Archive staging folder must be new or empty")
    destination=destination.resolve();destination.mkdir(parents=True,exist_ok=True)
    metadata_names=["manifests/train_compact_400.jsonl","manifests/validation.jsonl",
        "gemini_requests/train_compact_400.jsonl","gemini_requests/validation.jsonl","START_HERE.md"]
    with zipfile.ZipFile(archive) as outer:
        metadata=next(n for n in outer.namelist() if n.endswith("/00_LabelLens_Manifests_and_Schema.zip"))
        with zipfile.ZipFile(io.BytesIO(outer.read(metadata))) as inner:
            for name in metadata_names:
                path=destination/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(inner.read(name))
        wanted={r["image"] for split in ("train_compact_400","validation") for r in read_rows(destination/"manifests"/(split+".jsonl"))}
        for name in wanted:
            path=(destination/name).resolve()
            if not path.is_relative_to(destination) or not name.startswith(("images/train/","images/validation/")):
                raise ValueError("Unsafe or unexpected image path")
        found=set()
        for name in outer.namelist():
            if not name.endswith(".zip") or name==metadata or "held_out" in name:continue
            with zipfile.ZipFile(io.BytesIO(outer.read(name))) as inner:
                for image in set(inner.namelist())&wanted:
                    path=destination/image;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(inner.read(image));found.add(image)
        if found!=wanted:raise ValueError("Archive is missing selected training or validation images")
    return len(found)


def prepare(source, output, gcs_prefix, patches_path):
    if not gcs_prefix.startswith("gs://") or len(gcs_prefix.split("/"))<4:
        raise ValueError("Use a dedicated Cloud Storage bucket/prefix for this run")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty output folder to preserve earlier datasets and results")
    patches=read_rows(patches_path) if patches_path.suffix==".jsonl" else json.loads(patches_path.read_text(encoding="utf-8"))
    edits={(p["split"],p["id"]):p for p in patches}
    if len(edits)!=len(patches):raise ValueError("Duplicate review decisions")
    groups={};image_splits={};examples=[];change_log=[];applied=set();prepared={}
    source=source.resolve()
    for split,file in (("train","train_compact_400"),("validation","validation")):
        data=read_rows(source/"manifests"/(file+".jsonl"))
        requests=read_rows(source/"gemini_requests"/(file+".jsonl"))
        if len(data)!=len(requests):raise ValueError("Request/manifest counts disagree")
        result=[]
        for row,request in zip(data,requests):
            row=copy.deepcopy(row);request=copy.deepcopy(request)
            group=row.get("product_family")
            if not group:raise ValueError("Missing product family")
            if group in groups and groups[group]!=split:raise ValueError("Product family leaks between splits")
            groups[group]=split
            crop=(source/row["image"]).resolve()
            if not crop.is_relative_to(source) or not crop.is_file():raise ValueError("Invalid image path")
            digest=hashlib.sha256(crop.read_bytes()).hexdigest()
            if digest!=row["image_sha256"]:raise ValueError("Image hash mismatch")
            if digest in image_splits and image_splits[digest]!=split:raise ValueError("Image leaks between splits")
            image_splits[digest]=split
            user=request["contents"][0];model=request["contents"][1]
            if user["role"]!="user" or model["role"]!="model":raise ValueError("Wrong training roles")
            original_prompt="".join(p["text"] for p in user["parts"] if "text" in p)
            if original_prompt!=make_prompt(row["ml_kit_ocr"]):raise ValueError("Training prompt does not match app prompt")
            if json.loads(model["parts"][0]["text"])!=row["target"]:raise ValueError("Original target differs from manifest")
            review_key=(file,row["id"])
            if review_key in edits:
                patch=edits[review_key]
                if patch["image"]!=row["image"]:raise ValueError("Review refers to a different image")
                for field,support in patch["fields"].items():
                    if field not in row["target"]["evidence"]:raise ValueError("Review adds unexpected field")
                    before=copy.deepcopy(row["target"]["evidence"][field])
                    row["target"]["evidence"][field]=support
                    change_log.append({"split":split,"id":row["id"],"image_sha256":digest,"field":field,
                                       "before":before,"after":support,"review_method":patch["review_method"]})
                applied.add(review_key)
            row["target"]=parse_reading(json.dumps(row["target"]),row["ml_kit_ocr"]).model_dump()
            with Image.open(crop) as image:
                mime={"JPEG":"image/jpeg","PNG":"image/png"}.get(image.format)
            if mime is None:raise ValueError("Unsupported image format")
            images=[p for p in user["parts"] if "fileData" in p]
            if len(images)!=1:raise ValueError("This experiment requires one crop per request")
            name=digest+crop.suffix.lower()
            images[0]["fileData"]={"mimeType":mime,"fileUri":gcs_prefix.rstrip("/")+"/images/"+name}
            model["parts"]=[{"text":json.dumps(row["target"],ensure_ascii=False)}]
            request["generationConfig"]={"mediaResolution":"MEDIA_RESOLUTION_HIGH"}
            result.append(request)
            examples.append({"example_id":row["id"],"product_group":group,"split":split,"condition":row.get("condition"),
                "crop":"images/"+name,"context":None,"ocr_text":row["ml_kit_ocr"],"reviewed":True,
                "target":row["target"],"review_provenance":row.get("review"),"source":row.get("source"),
                "source_photo_sha256":row.get("source_photo_sha256")})
        prepared[split]=result
    if applied!=set(edits):raise ValueError("Some review decisions were not applied")
    (output/"images").mkdir(parents=True)
    for row in examples:
        original=next(p for p in (source/"images"/("train" if row["split"]=="train" else "validation")).glob(Path(row["crop"]).name))
        shutil.copyfile(original,output/row["crop"])
    for split,data in prepared.items():
        (output/(split+".jsonl")).write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in data),encoding="utf-8")
    (output/"examples.jsonl").write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in examples),encoding="utf-8")
    (output/"evidence_changes.json").write_text(json.dumps(change_log,ensure_ascii=False,indent=2),encoding="utf-8")
    manifest={"prompt_version":PROMPT_VERSION,"instruction_sha256":hashlib.sha256(INSTRUCTION.encode()).hexdigest(),
        "base_model":"gemini-3.5-flash","input_policy":"one exact crop + original ML Kit OCR; no full photo",
        "media_resolution":"MEDIA_RESOLUTION_HIGH","counts":{k:len(v) for k,v in prepared.items()},
        "families":{k:len({r["product_group"] for r in examples if r["split"]==k}) for k in prepared},
        "evidence_source_changes":len(change_log),"reviewed_rows_changed":len(applied),"gcs_prefix":gcs_prefix,
        "files":{k+".jsonl":hashlib.sha256((output/(k+".jsonl")).read_bytes()).hexdigest() for k in prepared},
        "final_test_policy":"Held-out and OCR stress sets were not staged, uploaded, or evaluated",
        "label_review_limit":"Original annotation provenance retained. Assistant visual review corrected flagged evidence sources; the entire label set was not independently reannotated."}
    (output/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return manifest


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--archive",type=Path,help="Optionally stage compact train/validation inputs from the original nested ZIP into --source")
    p.add_argument("--gcs-prefix",required=True)
    p.add_argument("--patches",type=Path,default=Path("model_dev/evidence_review_20261113.json"))
    a=p.parse_args()
    if a.archive:print("Staged train/validation images:",stage_archive(a.archive,a.source))
    print(json.dumps(prepare(a.source,a.output,a.gcs_prefix,a.patches),indent=2))
