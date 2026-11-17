"""Submit or inspect an ACTUAL Gemini tuning job; never trains YOLO."""
import argparse
import json
from pathlib import Path


def main():
    from google import genai
    from google.genai import types
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",required=True);p.add_argument("--location",default="us")
    p.add_argument("--base-model",default="gemini-3.5-flash")
    p.add_argument("--train-uri");p.add_argument("--validation-uri");p.add_argument("--job")
    p.add_argument("--epochs",type=int,default=1);p.add_argument("--output",type=Path,default=Path("gemini_tuning_job.json"))
    p.add_argument("--display-name",default="LabelLens-product-evidence-v3")
    p.add_argument("--adapter-size",type=int,default=4)
    p.add_argument("--learning-rate-multiplier",type=float,default=1.0)
    p.add_argument("--export-intermediate-checkpoints",action="store_true",help="Retain epoch checkpoints for validation comparison")
    a=p.parse_args()
    if not a.job and a.output.exists():
        p.error("Job record already exists; inspect that job with --job instead of submitting a duplicate")
    if not a.job and (a.epochs<1 or a.adapter_size not in (1,2,4,8,16)):
        p.error("Use positive epochs and a supported adapter size")
    if not a.job and a.base_model.startswith("gemini-3") and a.location not in ("us","eu"):
        p.error("Gemini 3 tuning requires the us or eu multi-region location")
    options={"api_version":"v1","timeout":60000,"retry_options":types.HttpRetryOptions(attempts=1)}
    if a.location in ("us","eu"):options["base_url"]=f"https://aiplatform.{a.location}.rep.googleapis.com"
    client=genai.Client(vertexai=True,project=a.project,location=a.location,http_options=types.HttpOptions(**options))
    try:
        if a.job:
            job=client.tunings.get(name=a.job)
        else:
            if not a.train_uri or not a.validation_uri or not all(u.startswith("gs://") for u in [a.train_uri,a.validation_uri]):
                p.error("Provide reviewed training and validation gs:// JSONL URIs, or --job to inspect a previous run")
            job=client.tunings.tune(base_model=a.base_model,training_dataset=types.TuningDataset(gcs_uri=a.train_uri),
                config=types.CreateTuningJobConfig(tuned_model_display_name=a.display_name,
                    epoch_count=a.epochs,adapter_size={1:"ADAPTER_SIZE_ONE",2:"ADAPTER_SIZE_TWO",4:"ADAPTER_SIZE_FOUR",8:"ADAPTER_SIZE_EIGHT",16:"ADAPTER_SIZE_SIXTEEN"}[a.adapter_size],learning_rate_multiplier=a.learning_rate_multiplier,
                    export_last_checkpoint_only=not a.export_intermediate_checkpoints,validation_dataset=types.TuningValidationDataset(gcs_uri=a.validation_uri)))
        data=job.model_dump(mode="json",exclude_none=True)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(data,indent=2),encoding="utf-8")
        print(json.dumps(data,indent=2));print("Use the completed job's tuned_model.endpoint in LABELLENS_TUNED_MODEL.")
    finally:client.close()


if __name__=="__main__":main()
