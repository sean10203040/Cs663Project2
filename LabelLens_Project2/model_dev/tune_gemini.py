"""Submit or inspect an ACTUAL Gemini tuning job; never trains YOLO."""
import argparse
import json
from pathlib import Path


def main():
    from google import genai
    from google.genai import types
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",required=True);p.add_argument("--location",default="us-central1")
    p.add_argument("--base-model",default="gemini-2.5-flash")
    p.add_argument("--train-uri");p.add_argument("--validation-uri");p.add_argument("--job")
    p.add_argument("--epochs",type=int,default=1);p.add_argument("--output",type=Path,default=Path("gemini_tuning_job.json"))
    a=p.parse_args()
    client=genai.Client(vertexai=True,project=a.project,location=a.location,http_options=types.HttpOptions(api_version="v1"))
    try:
        if a.job:
            job=client.tunings.get(name=a.job)
        else:
            if not a.train_uri or not a.validation_uri or not all(u.startswith("gs://") for u in [a.train_uri,a.validation_uri]):
                p.error("Provide reviewed training and validation gs:// JSONL URIs, or --job to inspect a previous run")
            job=client.tunings.tune(base_model=a.base_model,training_dataset=types.TuningDataset(gcs_uri=a.train_uri),
                config=types.CreateTuningJobConfig(tuned_model_display_name="LabelLens-product-evidence",
                    epoch_count=a.epochs,validation_dataset=types.TuningDataset(gcs_uri=a.validation_uri)))
        data=job.model_dump(mode="json",exclude_none=True)
        a.output.write_text(json.dumps(data,indent=2),encoding="utf-8")
        print(json.dumps(data,indent=2));print("Use the completed job's tuned_model.endpoint in LABELLENS_TUNED_MODEL.")
    finally:client.close()


if __name__=="__main__":main()
