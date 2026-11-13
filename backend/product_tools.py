"""Field-specific guidance and comparison summaries; agreement is not accuracy."""
import re


def field_values(reading):
    return {"product_name": reading.product_name, "brand": reading.brand,
            "size": reading.key_attributes.size, "best_by": reading.key_attributes.best_by}


def rescan_steps(reading):
    fields = field_values(reading)
    steps = []
    missing_front = [key for key in ("product_name", "brand") if fields[key] is None]
    if missing_front:
        steps.append({"fields": missing_front,
                      "instruction": "Photograph the front label straight on, with the full product name and brand in focus. Move the light or package if glare covers the letters."})
    if fields["size"] is None:
        steps.append({"fields": ["size"],
                      "instruction": "Show the printed size or net weight, often near the bottom of the front label or on the back. Include the units."})
    if fields["best_by"] is None:
        steps.append({"fields": ["best_by"],
                      "instruction": "Look for a printed best-by date on the cap, base, seam, or back. Photograph the date together with its heading; a lot code alone is not a best-by date."})
    return steps


def normalized(value):
    return None if value is None else re.sub(r"\s+", " ", value.casefold()).strip()


def agreement(base, tuned):
    a, b = field_values(base), field_values(tuned)
    fields = {key: normalized(a[key]) == normalized(b[key]) for key in a}
    return {"fields_equal": fields, "equal_fields": sum(fields.values()), "total_fields": len(fields),
            "note": "Agreement only, including shared missing values. Correctness requires a human-reviewed reference."}
