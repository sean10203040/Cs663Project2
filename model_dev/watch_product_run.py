"""Watch an existing tuning job. Never submits a job or invokes a model."""
import argparse
import json
from pathlib import Path
import time
import os
import google.auth
from google.auth import exceptions as auth_errors
from google.auth.transport.requests import Request
import httpx
from google import genai
from google.genai import types, errors as genai_errors
from backend.product_tools import api_base_url


def watch(path, project, interval=30):
    os.environ.setdefault("GOOGLE_CLOUD_QUOTA_PROJECT",project)
    saved=json.loads(path.read_text(encoding="utf-8"))
    name=saved["name"];location=name.split("/locations/",1)[1].split("/",1)[0]
    options={"api_version":"v1","timeout":25000,"retry_options":types.HttpRetryOptions(attempts=1)}
    if api_base_url(location):options["base_url"]=api_base_url(location)
    credentials,_=google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"],quota_project_id=project)
    transport=Request()
    def bounded_request(*args,**kwargs):
        kwargs["timeout"]=20
        return transport(*args,**kwargs)
    last=None
    with genai.Client(vertexai=True,project=project,location=location,credentials=credentials,http_options=types.HttpOptions(**options)) as client:
        while True:
            try:
                if not credentials.valid:credentials.refresh(bounded_request)
                job=client.tunings.get(name=name)
            except auth_errors.RefreshError:
                print("Monitoring needs a fresh Google sign-in. Run gcloud auth application-default login, then restart this monitor. The cloud job is unchanged.",flush=True)
                return {"monitor_error":"authentication"}
            except (auth_errors.TransportError,httpx.TransportError,ConnectionError,TimeoutError) as error:
                print(f"Connection interrupted ({type(error).__name__}). Retrying the status check in {interval} seconds. The cloud job is unchanged.",flush=True)
                time.sleep(interval);continue
            except genai_errors.APIError as error:
                code=getattr(error,"code",0) or 0
                if code in (408,429) or code>=500:
                    print(f"Google status service returned HTTP {code}; retrying in {interval} seconds. The cloud job is unchanged.",flush=True)
                    time.sleep(interval);continue
                print(f"Status check stopped with HTTP {code}. Check sign-in and project access. The cloud job is unchanged.",flush=True)
                return {"monitor_error":f"HTTP {code}"}
            data=job.model_dump(mode="json",exclude_none=True)
            temporary=path.with_name(path.name+f".{os.getpid()}.tmp")
            temporary.write_text(json.dumps(data,indent=2),encoding="utf-8");temporary.replace(path)
            signature=(data.get("state"),json.dumps(data.get("tuned_model"),sort_keys=True))
            if signature!=last:
                print(json.dumps({k:data.get(k) for k in ["name","tuned_model_display_name","state","start_time","end_time","error","tuned_model"]}),flush=True)
                last=signature
            if data.get("state") in ("JOB_STATE_SUCCEEDED","JOB_STATE_FAILED","JOB_STATE_CANCELLED","JOB_STATE_EXPIRED"):
                return data
            time.sleep(interval)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--job-file",type=Path,required=True)
    p.add_argument("--project",required=True);p.add_argument("--interval",type=int,default=30)
    a=p.parse_args()
    if not 10<=a.interval<=60:p.error("Use a polling interval from 10 to 60 seconds")
    try:
        result=watch(a.job_file,a.project,a.interval)
        if result.get("state")!="JOB_STATE_SUCCEEDED":raise SystemExit(1)
    except KeyboardInterrupt:
        print("Stopped monitoring. Google Cloud training is unchanged.")
