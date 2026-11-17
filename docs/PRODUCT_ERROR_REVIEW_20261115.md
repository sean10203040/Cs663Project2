# Product extraction error review — November 15, 2026

The current 50.3% product-name exact-match score mixes genuine extraction errors,
differences in naming/translation, and references that need a visibility check.
The next step should be consistent field definitions and a reviewed training-data
revision, followed by targeted training examples. Another epoch alone would not
address several of the problems found here.

## Scope and method

This is an **assistant visual triage**, not independently verified human ground
truth. All 155 validation crops from 18 recorded product groups were inspected in
34 contact sheets, with selected regions enlarged. Saved reference, actual OCR,
base prediction and tuned prediction were joined by example ID. Paired input
hashes, references and crop hashes were checked before review.

The detailed classifications concern the **new product-extraction fine-tune**.
Base predictions were inspected as paired context; they have not received a
separate exhaustive semantic adjudication. Strictly matching predictions were
visually screened, but this is not a complete reannotation of all matching fields.
Ambiguous lettering, partial labels and policy-dependent fields remain open.

No new model inference or training was performed. The dataset, predictions,
prompt, scoring and deployed app/backend were not changed. Final-test and stress
sets were not opened or evaluated. Original scores remain in the
[paired validation report](PRODUCT_VALIDATION_20261115.md).

## Findings

There are 151 valid tuned responses and four rejected responses. Among the valid
responses, 211 individual fields disagree with the frozen references:

| Provisional category | Field disagreements | Meaning |
|---|---:|---|
| Wording or field scope | 82 | Translation, qualifier, product line, or which words belong in a field differs |
| Formatting | 51 | Quantity/date/text identity is unchanged; punctuation, spacing, heading inclusion or order differs |
| Apparent model error | 44 | Wrong role, wrong number, missed information, or an unsupported assertion under the intended task |
| Reference needs review | 22 | Reference visibility, content, or annotation policy needs independent checking |
| Uncertain | 12 | Image/evidence is insufficient to adjudicate confidently |

These are **field counts, not image counts or a new accuracy score**. A photo can
contain several categories. Wording/scope does not automatically mean the model
is right: omitting a flavor, strength or other important qualifier can affect
usefulness. The model-error category is also provisional; some errors reflect
requirements that the current prompt does not define explicitly enough.

Product name alone has 78 exact matches, 73 field disagreements and four rejected
responses. Of the 73 disagreements, 57 concern wording/scope, nine are apparent
extraction/role errors, six require reference review and one is uncertain. This
does **not** justify adding those 57 cases to the accuracy numerator.

## Concrete examples and implications

| Case | Frozen reference → tuned output | Observation |
|---|---|---|
| Cream cheese, `fg_060383008390_rgb_20190116_130351` | Cream Cheese → cream cheese / fromage à la crème | Both languages are visibly printed; English-only exact matching rejects the longer result |
| Earth's Own, `fg_626027700015_rgb_20181004_202248` | Earth’s Own → Earth's Own; 1.89 L → 1.89L | Typographic apostrophe and unit-spacing differences; not evidence of failed visual recognition or corrupt Unicode |
| Cheese slices, `fg_060383061357_rgb_20190713_132221` | 230 g → 250 g | A genuine numerical transcription error; the photo shows 230 g |
| Butter, `fg_066096123450_rgb_20190113_224620` | size null → 10 g | A nutrition serving amount is being used as package size |
| Move Free, `H003` | size null → 1 Tablet | Serving size is being used as package count; ingredient blend is also returned as product name |
| Smokies, `fg_060383081317_rgb_20190430_201115` | brand null → ORIGINALES | A French product descriptor is being used as brand |
| Tea carton, `K084` | name null → Tart cranberries and sweet apples blend in this vibrant tea | Promotional copy is being used as product name; manufacturer is substituted for consumer brand |
| Tata salt, `K113` | size null → 1 kg | NET QUANTITY 1 kg is visible: reference should be independently checked |
| Minoxidil, `H121` | brand null → BEAUELI | Front logo is visible upside down: reference should be independently checked |
| Date field, `H004` | EXP 07/2028 → 07/2028 | Date value matches; the heading is omitted. Future output should retain date type separately |

Eleven disagreements specifically use a serving amount, dosing directions or
servings per container as size. Other cases derive a total quantity from the
serving table rather than transcribing a net-quantity label. Twenty-four size
disagreements concern formatting; additional cases concern multipack detail.
Do not erase those distinctions with a rule that strips all numbers or accepts
any substring.

Brand decisions also lack a consistent scope: examples include PC versus
President's Choice versus Free From, Lactantia versus Lactantia My Country, and
Tata versus Tata Salt. Manufacturer/distributor names are a separate issue:
Kraft Heinz, Loblaws, Reckitt, Indian Nectar and Madhu Jayanti must not silently
substitute for a consumer-facing brand under the intended product-card task.

Seventeen of the 24 date disagreements preserve the date components but omit a
heading or reorder components. A date value and its type (best-before, use-by,
expiration) should be retained distinctly; accepting a matching date value must
not erase type differences or validate a lot code.

## Four rejected responses

All four tuned failures are unsupported **OCR-source quotes**, rather than
missing required JSON keys:

| Case | Claimed OCR quote | Actual OCR fragment |
|---|---|---|
| `fg_626027700015_rgb_20181103_195136` | earth's own | earthisown / eartha |
| `fg_060383061357_rgb_20180914_113859` | no name | no namee |
| `fg_060383061357_rgb_20190224_185207` | no name | no names |
| `fg_060383855772_rgb_20190117_113153` | 500g | 5009 |

The model sometimes reads the image correctly, but claims that its corrected
transcription came verbatim from OCR. Training should explicitly teach that a
corrected reading uses `source: image`; an OCR quote must preserve the supplied
text. Do not remove evidence validation just to increase the pass rate. The raw
rejected cheese response for February 24 also says 250 g instead of the visible
230 g, so correcting its evidence source alone would not make the answer correct.

## What the paired improvement means

The tuned model gained 14 product-name exact matches and lost one relative to
base, for a net gain of 13 (65 → 78). Five of the 14 gained matches came from
base responses that failed the full contract. The single product-name regression
is `K022`: base retained A2/A2 Raw Milk; tuned shortened it to Raw Milk. The A2/A2
qualifier is visible. This supports retaining important qualifiers in the target
definition, not rewarding arbitrarily shorter names.

Two base-only all-field exact cases also illustrate different causes: the tuned
sausage answer added Free From to the brand, while a rear yogurt view acquired
an unverified 6 x 93 mL quantity. Ninety paired valid responses return identical
normalized values for all four fields. These observations help explain the modest
all-field improvement; they do not establish statistical significance.

## Priorities before the next paid run

1. **Define the fields.** Product name should include visible identity and important
   variant qualifiers; pick an explicit language policy. Brand should mean the
   visible consumer brand, with product line and manufacturer handled separately.
   Size should mean directly supported package net quantity/count, not nutrition
   serving size or daily directions. Define multipack representation. Preserve
   printed date value and date type without inventing missing components.
2. **Review the training pool against those definitions.** Apply fixes to a new
   versioned training derivative, preserving original images and noisy OCR. Add
   examples that contrast net weight with serving amounts, brand with ingredient
   or distributor text, and visible facts with unreadable/turned-away views. Keep
   all validation product families and their other views out of training.
3. **Resolve the flagged validation cases independently.** The 22 reference-review
   and 12 uncertain field decisions are a queue for a teammate to check, not an
   automatic patch. If a revised reference set or scoring policy is adopted,
   publish it as a separate version and rescore both saved models identically.
   Keep the original strict results alongside it. Do not turn validation photos
   or answers into training examples.
4. **Add supplemental scoring before selecting the next experiment.** Keep exact
   matching; add explicitly defined unit/typography normalization and human-checked
   identity/qualifier judgments. Report net quantities separately from count,
   and date transcription separately from date type. A revised scoring rule is
   a measurement change, not a model improvement.
5. **Then run a controlled training comparison.** Use reviewed training examples,
   the same held-out validation groups and frozen per-experiment prompts/settings.
   More epochs or more data are hypotheses to test, not a promised jump to a
   particular accuracy. Leave the final-test set untouched until selection ends.

The current prompt says `size` and `brand`, but does not explicitly distinguish
net quantity from serving information or consumer brand from corporate owner.
Aligning the instructions, training targets and evaluation policy is necessary
before interpreting those failures as something more training alone will solve.

## Review artifacts

- Case-by-case annotations and frozen source hashes:
  `model_dev/product_error_review_20261115.json` (155 cases).
- Offline photo gallery with reference/base/tuned values, field observations and
  actual OCR: `.tools/error_review_20261115/review.html` (local, Git ignored).
- Contact sheets, selected enlargements and local preparation scripts are under
  `.tools/`; source dataset images remain in the existing ignored run folder.

The gallery can be filtered by example ID, product group or category. Clicking a
photo opens the source crop. Nothing in these artifacts is a training upload,
reference correction, final-test result, or replacement for human adjudication.
