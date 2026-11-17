"""Write a paired validation report only after both models have complete matching inputs."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import random
from model_dev.evaluate_gemini import normalized, values


def exact(row):
    if not row.get("prediction"):return False
    expected,predicted=values(row["target"]),values(row["prediction"])
    return all(normalized(expected[k])==normalized(predicted[k]) for k in expected)


def paired(base,tuned):
    a={r["example_id"]:r for r in base};b={r["example_id"]:r for r in tuned}
    if len(a)!=len(base) or len(b)!=len(tuned) or set(a)!=set(b):raise ValueError("Incomplete or duplicate paired examples")
    wins=losses=ties=0;groups=defaultdict(list)
    validity_recoveries=validity_regressions=both_valid_wins=both_valid_losses=0
    for key,x in a.items():
        y=b[key]
        if not x.get("input_sha256") or x.get("input_sha256")!=y.get("input_sha256") or x["target"]!=y["target"] or x["product_group"]!=y["product_group"]:
            raise ValueError("Paired models were evaluated on different inputs/references")
        delta=int(exact(y))-int(exact(x));groups[x["product_group"]].append(delta)
        wins+=delta>0;losses+=delta<0;ties+=delta==0
        xv,yv=bool(x.get("prediction")),bool(y.get("prediction"))
        validity_recoveries+=not xv and yv;validity_regressions+=xv and not yv
        both_valid_wins+=xv and yv and delta>0;both_valid_losses+=xv and yv and delta<0
    # Resample whole recorded product groups, rather than treating multiple views
    # of one package as independent observations.
    rng=random.Random(20261113);families=list(groups);samples=[]
    for _ in range(5000):
        selected=[groups[rng.choice(families)] for _ in families]
        samples.append(sum(sum(g) for g in selected)/sum(len(g) for g in selected))
    samples.sort()
    return {"examples":len(a),"families":len(groups),"tuned_only_all_fields_correct":wins,
        "base_only_all_fields_correct":losses,"same_all_field_outcome":ties,
        "all_field_delta_percentage_points":100*(wins-losses)/len(a),
        "invalid_base_to_valid_tuned":validity_recoveries,"valid_base_to_invalid_tuned":validity_regressions,
        "both_valid_tuned_only_exact":both_valid_wins,"both_valid_base_only_exact":both_valid_losses,
        "descriptive_group_bootstrap_95_percent_interval_pp":[100*samples[125],100*samples[4874]]}


def report(run,output):
    stats=json.loads((run/"validation/comparison.json").read_text(encoding="utf-8"))
    rows={v:[json.loads(line) for line in (run/"validation"/(v+"_predictions.jsonl")).read_text(encoding="utf-8").splitlines() if line.strip()] for v in ("base","tuned")}
    manifest=json.loads((run/"dataset/manifest.json").read_text(encoding="utf-8"))
    if any(len(data)!=manifest["counts"]["validation"] for data in rows.values()):raise ValueError("Validation split is incomplete")
    comparison=paired(rows["base"],rows["tuned"])
    (run/"validation/paired_comparison.json").write_text(json.dumps(comparison,indent=2),encoding="utf-8")
    percent=lambda x:f"{100*x:.1f}%"
    base,tuned=stats["base"],stats["tuned"]
    lines=["# Product extraction: base versus tuned validation", "",
        "One approved training epoch on 400 examples. Validation contains 155 examples from 18 recorded product families. Final-test cases were not invoked.","",
        "Both models received the same crop bytes, actual OCR, evidence-v3 prompt and generation settings. Reference answers were used only for scoring. Input hashes and references were verified to match.","",
        "| Metric | Base Gemini | Product-extraction fine-tune |", "|---|---:|---:|"]
    for label,key in [("Valid complete response","valid_response_rate"),("All four fields exact","all_field_accuracy")]:
        lines.append(f"| {label} | {percent(base[key])} | {percent(tuned[key])} |")
    for field in ("product_name","brand","size","best_by"):
        lines.append(f"| {field} exact | {percent(base['fields'][field]['accuracy'])} | {percent(tuned['fields'][field]['accuracy'])} |")
    lines.append(f"| Values returned on absent reference fields | {percent(base['unsupported_value_rate_on_absent_fields'])} | {percent(tuned['unsupported_value_rate_on_absent_fields'])} |")
    lines.append(f"| Median cloud response | {base['latency_median_ms']/1000:.2f} s | {tuned['latency_median_ms']/1000:.2f} s |")
    lines.extend(["",f"Paired all-field outcomes: tuned-only correct on {comparison['tuned_only_all_fields_correct']} cases; base-only correct on {comparison['base_only_all_fields_correct']}; tied on {comparison['same_all_field_outcome']}.","",
        f"Format/evidence compliance: {comparison['invalid_base_to_valid_tuned']} base failures became valid tuned responses; {comparison['valid_base_to_invalid_tuned']} valid base responses became tuned failures. Among cases valid for both models, tuned-only exact on all four fields: {comparison['both_valid_tuned_only_exact']}; base-only exact: {comparison['both_valid_base_only_exact']}.","",
        f"All-field exact-match difference: {comparison['all_field_delta_percentage_points']:+.1f} percentage points. Descriptive 95% group-bootstrap interval: {comparison['descriptive_group_bootstrap_95_percent_interval_pp'][0]:+.1f} to {comparison['descriptive_group_bootstrap_95_percent_interval_pp'][1]:+.1f} points, resampling recorded product families.","",
        "## Interpretation limits","",
        "- Exact matching normalizes case/whitespace only. Extra bilingual text, equivalent units and alternate wording can be correct to a person while failing this metric.",
        "- Complete-response failures remain in every accuracy denominator. Improvements in JSON/evidence compliance are useful but do not by themselves prove better visual recognition.",
        "- A value disagreeing with a null reference is not a proven hallucination until the image/reference has been independently checked. Some archived reference policies need adjudication.",
        "- This is validation, not an untouched final-test result or phone accessibility study. Multiple views share product families; the descriptive interval is not a guarantee of real-world performance.",
        "- Cloud timings exclude phone capture, OCR, backend transport and speech. Reported confidence is subjective, not calibrated accuracy.",
        "- Base serving uses the global route; the tuned endpoint's serving location is taken from its resource name. Latency compares these deployments and does not isolate the effect of training from network/region differences.",
        "- The existing question-answer fine-tune is a separate model and was not replaced by this experiment.","",
        "Raw predictions/errors, exact input fingerprints, provenance, per-field precision/recall and paired outcomes are retained locally in the run's validation folder.",""])
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps(comparison,indent=2))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();report(a.run,a.output)
