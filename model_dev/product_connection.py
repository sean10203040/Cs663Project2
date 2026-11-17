"""Prepare non-secret backend settings only for the completed, validated product run."""
import argparse
import hashlib
import json
from pathlib import Path
from backend.contracts import INSTRUCTION, PROMPT_VERSION


def connection(run):
    job=json.loads((run/"tuning_job.json").read_text(encoding="utf-8"))
    manifest=json.loads((run/"dataset/manifest.json").read_text(encoding="utf-8"))
    if job.get("state")!="JOB_STATE_SUCCEEDED":raise ValueError("Training has not succeeded; no model connection was prepared")
    endpoint=job.get("tuned_model",{}).get("endpoint","")
    if not endpoint.startswith("projects/") or "/endpoints/" not in endpoint:raise ValueError("No actual serving endpoint was returned")
    spec=job["supervised_tuning_spec"];prefix=manifest["gcs_prefix"].rstrip("/")
    if spec.get("training_dataset_uri")!=prefix+"/train.jsonl" or spec.get("validation_dataset_uri")!=prefix+"/validation.jsonl":
        raise ValueError("Job is for a different dataset")
    if job.get("base_model")!=manifest["base_model"] or manifest["prompt_version"]!=PROMPT_VERSION or manifest["instruction_sha256"]!=hashlib.sha256(INSTRUCTION.encode()).hexdigest():
        raise ValueError("Training/app model or prompt mismatch")
    stats=json.loads((run/"validation/comparison.json").read_text(encoding="utf-8"))
    paired=json.loads((run/"validation/paired_comparison.json").read_text(encoding="utf-8"))
    n=manifest["counts"]["validation"]
    if paired["examples"]!=n or any(stats[v]["examples"]!=n for v in ("base","tuned")):raise ValueError("Paired validation is incomplete")
    if stats["base"]["model"]!=manifest["base_model"] or stats["tuned"]["model"]!=endpoint:
        raise ValueError("Validation evaluated a different model")
    result={"LABELLENS_BASE_MODEL":manifest["base_model"],"LABELLENS_TUNED_MODEL":endpoint,"GOOGLE_CLOUD_LOCATION":"global"}
    (run/"product_backend_settings.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run",type=Path,required=True)
    a=p.parse_args();print(json.dumps(connection(a.run),indent=2))
