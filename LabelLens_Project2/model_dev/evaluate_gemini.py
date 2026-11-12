"""Compare base and tuned Gemini on identical reviewed held-out image+OCR inputs."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import time
from backend.contracts import PROMPT_VERSION, make_prompt, parse_reading
from model_dev.export_sft import load_reviewed


def values(reading):
    return {"product_name":reading["product_name"],"brand":reading["brand"],
            "size":reading["key_attributes"]["size"],"best_by":reading["key_attributes"]["best_by"]}


def normalized(value):
    return None if value is None else " ".join(value.casefold().split())


def summarize(rows):
    fields={k:{"correct":0,"tp":0,"fp":0,"fn":0} for k in ["product_name","brand","size","best_by"]}
    buckets=defaultdict(lambda:{"count":0,"correct":0});all_correct=valid=unknown=hallucinated=0
    for row in rows:
        expected=values(row["target"]);predicted=values(row["prediction"]) if row.get("prediction") else {k:None for k in fields}
        ok=bool(row.get("prediction"));valid+=ok;exact=ok
        for key,counts in fields.items():
            e,p=normalized(expected[key]),normalized(predicted[key]);same=ok and e==p;counts["correct"]+=same;exact=exact and same
            counts["tp"]+=same and e is not None;counts["fp"]+=p is not None and not same;counts["fn"]+=e is not None and not same
        all_correct+=exact
        if expected["product_name"] is None:
            unknown+=1;hallucinated+=predicted["product_name"] is not None
        if ok:
            b=buckets[row["prediction"]["confidence"]];b["count"]+=1;b["correct"]+=exact
    for counts in fields.values():
        counts["accuracy"]=counts["correct"]/len(rows) if rows else None
        counts["precision"]=counts["tp"]/(counts["tp"]+counts["fp"]) if counts["tp"]+counts["fp"] else None
        counts["recall"]=counts["tp"]/(counts["tp"]+counts["fn"]) if counts["tp"]+counts["fn"] else None
    return {"examples":len(rows),"valid_response_rate":valid/len(rows) if rows else None,
        "all_field_accuracy":all_correct/len(rows) if rows else None,"fields":fields,
        "unknown_product_examples":unknown,"false_identification_rate_when_unknown":hallucinated/unknown if unknown else None,
        "buckets":{k:{"count":b["count"],"all_field_accuracy":b["correct"]/b["count"]} for k,b in buckets.items()}}


def main():
    from google import genai
    from google.genai import types
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--records",type=Path,required=True)
    p.add_argument("--project",required=True);p.add_argument("--location",default="us-central1")
    p.add_argument("--base-model",required=True);p.add_argument("--tuned-model",required=True)
    p.add_argument("--split",choices=["validation","test"],default="test");p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();records=[r for r in load_reviewed(a.records) if r["split"]==a.split]
    if not records:raise ValueError("No reviewed held-out examples in selected split")
    if a.output.exists() and any(a.output.iterdir()):raise ValueError("Choose a new output folder")
    a.output.mkdir(parents=True,exist_ok=True)
    client=genai.Client(vertexai=True,project=a.project,location=a.location,http_options=types.HttpOptions(api_version="v1",timeout=25000))
    report={}
    try:
        for variant,model in [("base",a.base_model),("tuned",a.tuned_model)]:
            rows=[]
            for r in records:
                started=time.perf_counter();row={"example_id":r["example_id"],"product_group":r["product_group"],"condition":r.get("condition"),"target":r["target"],"model":model}
                try:
                    parts=[types.Part.from_bytes(data=(a.records.parent/r[k]).read_bytes(),mime_type="image/jpeg") for k in ["crop","context"]]
                    parts.append(types.Part.from_text(text=make_prompt(r["ocr_text"])))
                    config={"temperature":0,"max_output_tokens":1600}
                    if "gemini-2.5" in a.base_model:config["thinking_config"]=types.ThinkingConfig(thinking_budget=0)
                    if variant=="base":config["response_mime_type"]="application/json"
                    response=client.models.generate_content(model=model,contents=[types.Content(role="user",parts=parts)],config=types.GenerateContentConfig(**config))
                    row["prediction"]=parse_reading(response.text or "",r["ocr_text"]).model_dump()
                except Exception as error:row["error"]=str(error);row["prediction"]=None
                row["elapsed_ms"]=(time.perf_counter()-started)*1000;rows.append(row)
                with (a.output/(variant+"_predictions.jsonl")).open("a",encoding="utf-8") as stream:stream.write(json.dumps(row,ensure_ascii=False)+"\n")
            stats=summarize(rows);stats.update({"model":model,"prompt_version":PROMPT_VERSION,"split":a.split})
            stats["by_condition"]={c:summarize([r for r in rows if (r.get("condition") or "unspecified")==c]) for c in sorted({r.get("condition") or "unspecified" for r in rows})}
            report[variant]=stats
            if a.split=="validation":(a.output/(variant+"_calibration.json")).write_text(json.dumps(stats,indent=2),encoding="utf-8")
    finally:client.close()
    (a.output/"comparison.json").write_text(json.dumps(report,indent=2),encoding="utf-8");print(json.dumps(report,indent=2))


if __name__=="__main__":main()
