"""Render a local before/after gallery from the frozen source and candidate audit."""
import argparse
import copy
import html
import json
import os
from pathlib import Path

from model_dev.prepare_product_v4 import canonical_sha, read_rows, sha


def render(source, audit_path, output):
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if sha(source.read_bytes()) != audit["source_examples_sha256"]:
        raise ValueError("Source changed since review")
    rows = {r["example_id"]: r for r in read_rows(source) if r["split"] == "train"}
    cards = []
    for decision in audit["decisions"]:
        row = rows[decision["example_id"]]
        if canonical_sha(row) != decision["source_row_sha256"]:
            raise ValueError("Reviewed record changed")
        original = row["target"]
        revised = copy.deepcopy(original)
        for key, patch in decision["fields"].items():
            if key in ("product_name", "brand"):
                revised[key] = patch["value"]
            else:
                revised["key_attributes"][key] = patch["value"]
            if patch["value"] is None:
                revised["evidence"].pop(key, None)
            else:
                revised["evidence"][key] = {"source": patch["source"], "quote": patch["quote"]}
        image = (source.parent / row["crop"]).resolve()
        if sha(image.read_bytes()) != decision["image_sha256"]:
            raise ValueError("Reviewed crop changed")
        image_url = Path(os.path.relpath(image, output.parent.resolve())).as_posix()
        notes = "\n".join(decision["notes"] + [key + ": " + p["reason"] for key, p in decision["fields"].items()])
        status = decision["status"]
        search = html.escape(" ".join((row["example_id"], row["product_group"], notes, json.dumps(original, ensure_ascii=False), json.dumps(revised, ensure_ascii=False))).casefold(), quote=True)
        def panel(title, value):
            return "<div><h3>" + title + "</h3><pre>" + html.escape(json.dumps(value, ensure_ascii=False, indent=2)) + "</pre></div>"
        label = "Proposed candidate target" if status == "revise" else "Unchanged target"
        if status == "hold":
            label = "Excluded; earlier proposals are not training answers"
        cards.append(f'<article data-status="{status}" data-search="{search}"><h2>#{decision["number"]} · {html.escape(row["example_id"])} · {status}</h2>'
            f'<p>{html.escape(row["product_group"])}</p><a href="{html.escape(image_url, quote=True)}" target="_blank" rel="noopener"><img loading="lazy" src="{html.escape(image_url, quote=True)}" alt="Selected source crop for example {decision["number"]}"></a>'
            '<div class="panels">' + panel("Original target", original) + panel(label, revised) + '</div>'
            f'<pre>{html.escape(notes)}</pre><details><summary>Original noisy OCR</summary><pre>{html.escape(row["ocr_text"])}</pre></details></article>')
    document = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LabelLens training review · November 15, 2026</title>
<style>body{font:16px system-ui;margin:0;background:#f0f3f6;color:#152536}header,main{max-width:1250px;margin:auto;padding:20px}header{position:sticky;top:0;background:#fff;border-bottom:2px solid #aab8c8;z-index:1}h1{font-size:24px;margin:0 0 8px}h2{font-size:19px;overflow-wrap:anywhere}h3{font-size:16px}input,select{font:inherit;padding:9px;margin:5px}input{width:min(60%,650px)}article{padding:24px;margin:24px 0;background:white;border-radius:12px;border-left:7px solid #317859}article[data-status=hold]{border-color:#ad6625}article[data-status=revise]{border-color:#246da1}img{display:block;max-width:100%;max-height:750px;margin:15px auto;background:#eee}.panels{display:grid;grid-template-columns:1fr 1fr;gap:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px ui-monospace,monospace;background:#f6f8fa;padding:12px}button{font:inherit}article[hidden]{display:none}@media(max-width:700px){.panels{grid-template-columns:1fr}header{position:static}}</style>
<header><h1>LabelLens · Training review</h1><p>400 training crops · assistant first-pass review · 287 candidates / 113 held. Proposed corrections need independent checking; this is not a new accuracy result.</p><input id="query" aria-label="Search" placeholder="Search ID, family, field or reason"><select id="status" aria-label="Disposition"><option value="">All dispositions</option><option value="revise">93 proposed corrections</option><option value="hold">113 held for review</option><option value="retain">194 unchanged</option></select><span id="count" aria-live="polite"></span></header><main>
""" + "\n".join(cards) + """</main><script>
const cards=[...document.querySelectorAll('article')],query=document.getElementById('query'),status=document.getElementById('status');
function filter(){let visible=0;const q=query.value.toLocaleLowerCase().trim();for(const card of cards){card.hidden=Boolean((status.value&&card.dataset.status!==status.value)||(q&&!card.dataset.search.includes(q)));if(!card.hidden)visible++;}document.getElementById('count').textContent=visible+' / '+cards.length+' examples';}
query.addEventListener('input',filter);status.addEventListener('change',filter);filter();
</script></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    return len(cards)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print("Rendered", render(args.source, args.audit, args.output), "training crops")
