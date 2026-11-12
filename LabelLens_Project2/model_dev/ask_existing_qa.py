"""One real base/tuned image-question request; does not train or deploy anything."""
import argparse
import io
import json
from pathlib import Path

from PIL import Image, ImageOps
from backend import qa


def main():
    from google.genai import types
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--image", type=Path, required=True)
    p.add_argument("--question", required=True)
    p.add_argument("--prompt", default="backend/qa_prompt.json")
    p.add_argument("--project", default=qa.PROJECT)
    p.add_argument("--variant", choices=["base", "tuned"], default="tuned")
    p.add_argument("--base-model", default=qa.BASE_MODEL)
    p.add_argument("--base-location", default="global")
    p.add_argument("--tuned-model", default=qa.TUNED_MODEL)
    a = p.parse_args()
    template = qa.load_prompt(a.prompt)
    with Image.open(a.image) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((2048, 2048))
        stream = io.BytesIO()
        image.save(stream, "JPEG", quality=95)
    model = a.tuned_model if a.variant == "tuned" else a.base_model
    location = qa.serving_location(model, a.base_location)
    contents = [types.Content(role="user", parts=[
        types.Part.from_bytes(data=stream.getvalue(), mime_type="image/jpeg"),
        types.Part.from_text(text=qa.make_prompt(template, a.question))])]
    result = qa.parse_answer(qa.generate_answer(a.project, model, location, contents))
    print(json.dumps({"model": model, "location": location, "question": a.question,
        "qa": result.model_dump(), "guidance": None if result.answerable else qa.RESCAN_GUIDANCE},
        ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
