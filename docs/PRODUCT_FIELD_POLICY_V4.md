# Product-field policy v4 — candidate, November 15, 2026

This policy guides a new training derivative after the November 15 error review.
It does not change the deployed evidence-v3 prompt, its model, original labels,
or frozen validation scores. All facts must be supported by the selected image
and actual OCR for that example; another view of the same product is not evidence
that a fact is readable in this view.

## Product name

Use the visible product identity and important printed variant qualifiers, in
natural reading order. Include product kind, flavor, strength, percentage,
unsalted/no-sugar/lactose-free or similar variant wording when readable and part
of the identity. Do not replace the name with ingredients, nutrition text,
directions, a website, an advertising sentence, or a corporate name.

Prefer the printed English name when it is readable. If English is absent or
unreadable, transcribe one readable printed language; do not translate or infer
missing words. Do not concatenate duplicate English/French names. Preserve
accents and meaningful punctuation. Do not repeat the separately extracted brand
unless it is an inseparable part of a printed product/line name. Do not add
generic product categories based on appearance or prior brand knowledge.
An explicit identification in descriptive copy can support the product type
(for example, "this delicious bacon" supports Bacon); an ingredient list alone
does not establish the product's name.

## Brand

Use the readable consumer-facing brand for the selected product, once, in its
printed form. Prefer English if duplicate language versions are printed. A
clearly printed abbreviation/logo can be transcribed as printed; do not expand
it from outside knowledge. Keep the parent brand distinct from the product line
where the label makes that distinction clear. A distributor, manufacturer or
corporate owner in an address block is not automatically the consumer brand.
Ingredient names and product descriptors are not brands. If only a website or
ambiguous owner attribution is readable, return null rather than guessing.

## Package size

`key_attributes.size` means **directly printed net package quantity or package
count**. It does not mean amount per serving, daily directions, number of servings,
concentration, calories, or a promotional equivalence. Never derive package
quantity by multiplying servings by serving size.

For a multipack, preserve the readable count and per-unit quantity, plus total
net quantity if explicitly printed and readable. Do not calculate or convert
units. Keep all printed numbers exact. Use one space between a number and a unit
(`230 g`, `1.89 L`, `30 mL`); use `x` between count and per-unit quantity. Do not
include a redundant `NET WT`/`NET QUANTITY` heading in the value, but retain it in
image evidence when readable. Never convert 230 g to 250 g, remove a decimal, or
accept a quantity merely because a substring agrees with the target.

## Printed date

The existing `best_by` schema also carries printed expiry/use-by dates. Preserve
the visible heading and date when both are readable, e.g. `EXP 07/2028` or
`BEST BEFORE AUG-2022`. If only a date value is readable, retain it only when its
best-by/use-by/expiry role is supported in that input. Do not use manufacture
dates, batch/lot codes, recycle codes, or general shelf-life instructions.

Preserve printed date ambiguity and missing components; do not invent a year,
translate month codes, reorder date components, or calculate a date. A future
schema can separate date type and date value; this candidate retains the current
app-compatible schema. No freshness or safety judgment is implied.

## Evidence, missing fields and confidence

Each non-null field needs a supporting quote. For `source: ocr`, copy the actual
OCR text exactly, including wrong letters or digits; a quote must be present in
the supplied OCR. When the picture corrects the OCR, transcribe the readable print
and use `source: image`. Do not silently relabel uncertain evidence as image.
Image evidence must support both the value and its field role.

For unreadable/absent/ambiguous fields return null and omit that evidence key.
Do not fill a field from other photos, product-family identity, familiar package
colors or a reference answer. Keep original noisy OCR unchanged. If name and
brand are both unavailable, provide one specific request for a clearer label
view. Missing optional size/date alone does not lower confidence in readable
identity. Confidence is subjective; it is not measured accuracy.

## Review and evaluation rules

- A visually confirmed correction is recorded with original/new targets and an
  explanation. Ambiguous rows are held out of the candidate, not assigned invented
  answers. Assistant review is identified explicitly; it is not human adjudication.
- Training contains only originally assigned training examples. Validation and
  final-test families, photos and labels must never become training examples.
- Existing reference sets and strict scores stay frozen. Any future revised
  validation labels or supplemental normalization require their own version and
  identical treatment of both models. Never report a scoring-policy change as a
  model improvement.
- Future base/tuned comparisons must use identical v4 instructions and inputs.
  The old v3 scores remain a separate experiment. Deploy a v4 prompt only with
  a model evaluated for that prompt; keep the old model connection available.
