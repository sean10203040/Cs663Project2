"""Package portable source only; exclude credentials, datasets, SDKs and build outputs."""
import ast
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT


def main():
    sources = []
    for path in [*(ROOT/"app").rglob("*"), *(ROOT/"gradle").rglob("*")]:
        if not path.is_file():
            continue
        parts = path.relative_to(ANDROID).parts
        if any(part in {"build", ".gradle", ".idea", ".git"} for part in parts):
            continue
        if path.name == "local.properties" or path.suffix in {".jks", ".keystore"}:
            continue
        sources.append(path)
    for folder in ("backend", "model_dev"):
        sources.extend((ROOT/folder).glob("*.py"))
    sources += [ROOT/name for name in [
        "settings.gradle", "build.gradle", "gradle.properties", "gradlew", "gradlew.bat",
        "GEMINI_SETUP.md", "README.md", "Dockerfile", ".dockerignore", ".gcloudignore", ".gitignore",
        "backend/requirements.txt", "backend/Dockerfile", "backend/.env.example",
        "backend/.env.existing-qa.example", "backend/.env.product-extraction.example",
        "model_dev/reviewed_example_format.json", "docs/PRODUCT_EXTRACTION_FUTURE.md",
        "docs/CLOUD_STATUS_20261111.md", "backend/qa_prompt.json", "scripts/package_existing_qa.py"]]
    sources.extend((ROOT/"tests").glob("*.py"))
    sources.extend((ROOT/"docs").glob("*.md"))
    for path in sources:
        if path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    xmls = list((ANDROID/"app/src").rglob("*.xml"))
    for path in xmls:
        ET.parse(path)
    layout = (ANDROID/"app/src/main/res/layout/activity_main.xml").read_text(encoding="utf-8")
    activity = (ANDROID/"app/src/main/java/edu/cs663/labellens/project2/MainActivity.java").read_text(encoding="utf-8")
    declared = set(re.findall(r'@\+id/(\w+)', layout))
    used = set(re.findall(r'R\.id\.(\w+)', activity))
    if used - declared:
        raise ValueError(f"Activity refers to missing layout IDs: {used-declared}")
    gateway = (ANDROID/"app/src/main/java/edu/cs663/labellens/project2/pipeline/GeminiGateway.java").read_text(encoding="utf-8")
    if '"/v1/answer"' not in gateway or '"/v1/parse"' not in gateway:
        raise ValueError("Unexpected Android route")
    output = ROOT/"dist/LabelLensProject2_Source.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(sources)):
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP verification failed")
        names = archive.namelist()
        for name in names:
            if any(p in {".env", ".venv", ".tools", "__pycache__", "local.properties"}
                   for p in Path(name).parts):
                raise ValueError(f"Unexpected private/generated file: {name}")
    report = {"archive": str(output), "files": len(names), "bytes": output.stat().st_size,
              "python_syntax": "passed", "android_xml_files_parsed": len(xmls),
              "activity_layout_ids": "passed", "zip_crc": "passed",
              "android_build_or_runtime": "not run", "live_cloud_inference": "not run",
              "full_training_prompt": "verified QA prompt included; datasets excluded"}
    (ROOT/"dist/Existing_Gemini_Package_Checks.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
