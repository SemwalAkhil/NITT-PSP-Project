# Clinical, Safety, Evidence, and Multilingual Data Requirements

**Status:** Future-stage requirements. This document does not provide clinical advice and does not claim these features are implemented.

## 1. Intended and prohibited use

Herbal Almanac is a research and educational reference. It may display sourced information about herbs, traditional uses, research, preparations, and reported safety concerns.

It must not diagnose, recommend herbs as treatment for an individual, prescribe dose/duration/route, replace a clinician/pharmacist, advise stopping/changing prescribed medicine, or imply that absence of adverse-effect reports proves safety. Traditional use, in-vitro work, and animal studies are not proof of human efficacy. Display a visible research-information disclaimer.

## 2. Evidence categories

| Category | What it supports | What it does not prove by itself |
|---|---|---|
| Classical/traditional text | Historical/traditional use | Modern clinical efficacy or safety |
| Government/pharmacopoeial monograph | Official identity/quality statements within scope | Universal effectiveness |
| In-vitro/preclinical | Laboratory mechanism/activity | Human benefit |
| Animal study | Findings in studied model | Human dose/effect |
| Observational human study | Association in studied population | Causation |
| Clinical trial | Findings for study design/population/intervention | Generalization to all products |
| Systematic review/meta-analysis | Synthesis of included studies | Certainty beyond included evidence |
| Regulatory/pharmacovigilance | Safety signal or reported event | Automatic proof of causality |

For each evidence item capture available title, authors/organization, date, journal/book/monograph, DOI/PMID/registry ID/URL, volume/page/section, evidence type, population/species, sample size, botanical identity, plant part, preparation/extract, route/exposure, comparator/outcome, limitations, funding/conflicts, retrieval date, and license. Missing metadata remains unknown.

### Independent corroboration

Multiple sources must be independent. Identify mirrors, derivative databases, and citations to the same underlying study. Store each source claim separately; preserve conflicts; do not use majority vote. Select sources appropriate to each claim type and show evidence scope/limitations.

## 3. Herb description requirements

A description should be composed from validated, cited components:
1. Preferred Hindi and English names.
2. Ayurvedic/Sanskrit name and original-script form.
3. Verified botanical name, family, and taxonomic status.
4. Common/vernacular names and language/region where known.
5. Documented plant parts.
6. Neutral botanical identity description.
7. Traditional properties/uses labelled as traditional.
8. Modern research summary separated by evidence category.
9. Documented preparations/forms.
10. Reported safety concerns and evidence gaps.
11. Sources for each factual section.

Do not blend traditional claims and modern science into one uncited paragraph.

## 4. Hindi and English localization

Hindi and English are primary interface languages. Preserve Sanskrit and source wording.

Store exact text, language code, script code, term type, source/evidence, translation origin (source-authored/human/machine), verification status (unreviewed/reviewed/disputed/rejected), reviewer/date, and preferred display flag.

Rules:
- Translation and transliteration are different data.
- Do not replace original Sanskrit or source wording.
- Do not treat English as canonical for every vernacular term.
- Machine-generated values remain unverified until reviewed.
- Search should support Hindi, English, Sanskrit, synonyms, and transliteration variants where practical.
- If no reliable translation exists, label it unavailable/unverified.

## 5. Preparation and form-of-use data

Suggested vocabulary: whole/solid material, powder/churna, decoction/kashaya, infusion, juice/swarasa, paste/kalka, extract, oil/ghrita, tablet/capsule, compound formulation, other source-described liquid/preparation, unknown/not stated.

For each preparation claim capture available herb/taxon, plant part, exact source term, normalized form, method, solvent/vehicle/adjuvant, route, dose/units, frequency/duration, population/indication, evidence category, source claim, and review status.

Never infer that powder is mixed with honey, milk, water, ghee, or anything else unless a source explicitly says so. Do not convert traditional units without a documented conversion and uncertainty. Keep formulation identity distinct from plant species.

## 6. Side effects and safety

Separate:
- Reported adverse event.
- Adverse reaction with assessed causality.
- Contraindication.
- Precaution/warning.
- Herb-drug or herb-herb interaction.
- Allergy/hypersensitivity.
- Toxicity/overdose/misidentification risk.
- Special-population caution.
- Insufficient safety data.

For each assertion capture available exact herb/product, formulation, plant part, route, exposure/dose, duration, population, event/concern, exact source wording, severity/seriousness, frequency wording, causality, outcome, source type, evidence reference, date, jurisdiction, and review status.

Do not normalize frequency unless mapping is documented. Display careful states: “reported in cited source(s),” “potential interaction reported,” “no report found in sources reviewed,” “insufficient safety data,” or “evidence conflicting.” Never show “no side effects” or “completely safe.”

## 7. Medical-history considerations — later stage only

Not part of the current MVP. Potential user-declared factors may include allergies, current medicines/supplements, pregnancy/breastfeeding, age group, chronic conditions, and planned procedures—but only where evidence establishes relevance.

Before implementation:
1. Privacy threat model and data-flow diagram.
2. Minimize data and explain each field.
3. Explicit informed consent.
4. Keep health data separate from shared herb/reference database.
5. No persistent storage by default; define retention, deletion, export, access control, and encryption before storage.
6. No third-party processing without explicit consent and reviewed legal/data basis.
7. Clinical/pharmacist review of matching rules and wording.
8. Test false negatives and false reassurance.

Only show cautious source-backed prompts such as “a potential interaction is documented; discuss this with your pharmacist.” Never say “safe for you,” diagnose, select a herb, or change medication instructions. If evidence is insufficient, say the system cannot assess it.

## 8. Multiple-symptom matching — terminology retrieval, not diagnosis

- Accept Hindi and English free text; optional Sanskrit/Ayurvedic terms.
- Preserve exact user wording; normalize spelling, transliteration, and reviewed synonyms separately.
- Clarify ambiguous terms.
- Detect urgent/red-flag language and route to urgent-care guidance rather than herb search.
- Retrieve reviewed symptom concepts and explicit crosswalks.
- Analyze each symptom before ranking combined candidates.
- Show matched, unmatched, and ambiguous symptoms.
- Use documented ranking signals (exact term, reviewed synonym, hierarchy, semantic retrieval) evaluated on a reviewed dataset.
- No uncalibrated diagnostic probability.
- Do not infer disease from symptom clusters or string similarity.
- Output ranked terminology candidates, explanation, source/target terms, mapping type, evidence, review status, alternatives, and abstention where uncertain.
- No automatic herb recommendation or treatment plan.

Evaluation must include Hindi/English, ambiguous, misspelled, multi-symptom, negated, and out-of-scope cases. Measure precision, recall, top-k accuracy, abstention quality, and language-specific errors. Obtain domain/clinical review before release.

## 9. Data quality measures

Track authoritative identity coverage, Hindi/English coverage and review, source-backed properties, reviewed condition mappings, preparation detail coverage, safety evidence coverage (including unknown/insufficient), single vs multiple independent sources, unresolved conflicts, stale evidence, license status, and translation/normalization exceptions. Never improve completeness by guessing.

## 10. Acceptance checklist

- [ ] Original source text/language/script retained.
- [ ] Hindi and English labels available or clearly unavailable.
- [ ] Traditional, preclinical, clinical, and regulatory evidence separated.
- [ ] Every claim traceable to source/evidence.
- [ ] Source independence and conflicts assessed.
- [ ] Herb descriptions use cited, reviewed fields.
- [ ] Preparation/route/vehicle/dose/duration never inferred.
- [ ] Safety claims include formulation/population context.
- [ ] Missing safety data means unknown, not safe.
- [ ] Medical-history feature gated by privacy and clinical review.
- [ ] Multi-symptom matching explains and abstains.
- [ ] No diagnosis, prescribing, or medication-change advice.
