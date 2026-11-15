# Roadmap Addendum — Evidence, Safety, Multilingual Access, and Clinical Matching

**Status:** Future requirements, not implemented features. Read with plan.md, database_schema.md, and antigravity_handoff.md.

## Product aims

1. **Herb descriptions:** concise, understandable, cited descriptions covering identity, common names, plant part, traditional context, and scientifically supported findings. Keep traditional claims separate from modern research.
2. **Hindi and English first:** Hindi and English are primary user-facing languages. Preserve Sanskrit, Devanagari, transliteration, and exact source wording, but do not make Sanskrit the only discoverable language. Store translation origin and review status.
3. **Scientific backing:** important claims require traceable evidence appropriate to the claim: pharmacopoeias and government/academic sources for identity/monographs; taxonomy registries for taxonomy; primary research/systematic reviews for research; recognized regulatory/pharmacovigilance sources for safety.
4. **Multiple-source corroboration:** attach independent sources to existing and future claims. Preserve disagreements. Do not count mirrors, derivative databases, or citations of the same study as independent corroboration.
5. **Common side effects:** capture reported adverse effects and safety observations with exact herb/preparation, route, population, exposure context, evidence type, severity/frequency wording, and source when available. No report found does not mean safe.
6. **Medical-history considerations:** much later, support cautious screening of relevant declared factors such as allergies, medicines, pregnancy/breastfeeding, age group, chronic conditions, and procedures. This is not a diagnosis or recommendation engine. Require privacy and clinical review.
7. **Preparation/form:** record source-documented forms such as whole/solid material, powder/churna, decoction/kashaya, infusion, juice/swarasa, paste/kalka, extract, oil, tablet/capsule, or compound preparations. Capture plant part, preparation method, vehicle/adjuvant, route, dose, and duration only if explicitly documented.
8. **Multiple-symptom matching:** retrieve closest supported terminology concepts using explainable ranking. Show matched/unmatched symptoms, alternatives, evidence, and uncertainty. Abstain when weak or ambiguous. Never diagnose or recommend a herb.

## Non-negotiable rules

- Preserve original source wording and normalized interpretation separately.
- Every claim must be traceable to source record, URL, section/page, retrieval date, license, and evidence metadata where available.
- Distinguish traditional text, pharmacopoeial statements, in-vitro, animal, observational human, clinical trial, systematic review, and regulatory evidence.
- Never describe laboratory/animal findings as proven human efficacy.
- Never equate Ayurvedic indications to modern diseases by string similarity alone.
- A missing adverse-event record means unknown/not reported in collected sources, not no side effects.
- Machine translations remain unverified until reviewed.
- Never invent dose, duration, route, preparation, contraindication, interaction, side-effect frequency, or efficacy.
- User medical history is sensitive. Do not store it in the shared herb knowledge database. Minimize collection; require explicit consent, retention/deletion policy, and privacy/security review before any history feature.
- No feature may diagnose, prescribe, or advise stopping/changing prescribed medicines.

## Dependency-ordered stages and gates

### Stage A — Stabilize current engineering
- Verify current branch, open PRs, and PR-specific CI.
- Complete GUI stylesheet integration only after its own checks pass.
- Run offline test suite and document current schema accurately.
- Preserve CLI/database/web boundaries.
**Gate:** clean CI, reproducible setup, documented active schema, no known migration regression.

### Stage B — Provenance and reproducible ingestion
- Operationally integrate sources, source_records, and source_claims into DRAVYA ingestion.
- Link names, attributes, Dosha, indications, and future safety/preparation claims to source claims.
- Define claim granularity, correction/supersession history, raw source artifact/cache, scrape runs, parse errors, idempotency, and partial-failure behavior.
- Record source license and redistribution decision.
**Gate:** every imported claim is traceable; re-ingestion is idempotent; source updates and failures cannot silently erase valid/manual data.

### Stage C — Normalized domain model and multilingual identity
- Implement normalized concepts for plant parts, Rasa/Guna/Virya/Vipaka, Karma, Dosha effects, indications/conditions, preparations, and controlled vocabularies.
- Every claim-bearing row references a source claim.
- Hindi and English become first-class labels/descriptions; Sanskrit and original scripts remain preserved.
- Track source-authored, human-reviewed, and machine-unverified translations.
**Gate:** schema, migrations, repositories, importers, tests, and documentation agree; legacy migration is safe.

### Stage D — Multi-source scientific evidence
- Complete feasibility/licensing review before each source adapter.
- Add claim/evidence records with publication type, authors/organization, year, DOI/URL, page/section, study type, species/population, plant part, preparation, route, exposure, outcome, and limitations where available.
- Identify duplicate/derivative sources and shared underlying studies.
- Preserve conflicting claims and adjudication status.
**Gate:** representative dataset has auditable independent corroboration and visible disagreement; license checks pass.

### Stage E — Herb descriptions and preparation forms
- Compose descriptions from validated, cited fields.
- Separate identity, traditional use, preclinical research, clinical findings, and safety.
- Record documented forms and preparation details; never infer missing vehicles, routes, doses, or durations.
- Review Hindi and English.
**Gate:** every factual detail is traceable; unknown values remain unknown; translation review status is visible.

### Stage F — Side-effect and safety evidence
- Model adverse events, adverse reactions, contraindications, precautions, interactions, allergy, toxicity, and insufficient safety data separately.
- Capture formulation, plant part, route, exposure, population, event, severity/frequency wording, causality assessment, and source when available.
- Prioritize recognized pharmacovigilance/regulatory sources and peer-reviewed research.
- Distinguish reported event from proven causality.
**Gate:** safety statements are contextualized and reviewed; no false reassurance.

### Stage G — Medical-history caution layer (later)
- Complete privacy threat model, data flow, consent, retention/deletion, and security design.
- Keep user history separate from shared herb database; minimize optional factors.
- Compare only with documented cautions/interactions.
- Return cautious prompts to consult a clinician/pharmacist, never “safe for you.”
- Never diagnose, prescribe, or advise medication changes.
**Gate:** privacy/security and clinical safety approval. If unmet, do not ship.

### Stage H — Multi-symptom terminology matching (not diagnosis)
- Build reviewed Hindi/English symptom concepts and explicit crosswalks.
- Preserve original wording and show normalized concepts.
- Rank candidates using documented, evaluated signals.
- Show matched/unmatched symptoms, alternatives, evidence, and mapping status.
- Abstain on low-confidence, ambiguous, contradictory, or out-of-scope inputs.
- Add urgent-symptom escalation behavior.
- Do not recommend herbs or diagnose.
**Gate:** reviewed multilingual evaluation set, measured performance/abstention, domain review, and safe UX.

### Stage I — Public release and maintenance
- Complete public query API and CLI.
- Publish versioned database releases with provenance, license, attribution, and quality reports.
- Maintain adapters, migrations, corrections, translation review, and safety updates.

## Proposed domain additions (not implemented)

| Concept | Purpose |
|---|---|
| herb_descriptions | Localized cited descriptions and review status |
| herb_preparations | Form, plant part, preparation method, route, vehicle, source claim |
| adverse_effects | Controlled adverse-effect concepts and localized labels |
| herb_safety_claims | Herb/preparation/population-specific safety assertions |
| evidence_records | Bibliographic and study metadata |
| claim_evidence | Link claims to evidence records |
| localized_terms | Hindi/English/Sanskrit labels, script, preferred status, review provenance |
| symptom_concepts | Controlled symptom terminology and synonyms |
| condition_crosswalks | Explicit terminology mappings and review status |

These are conceptual entities, not instructions to implement tables immediately. Review database_schema.md and migration strategy first. User medical history must not be stored in the shared herb knowledge database.

## Release acceptance checklist

- [ ] Claims are traceable; unsupported/manual claims are clearly labelled.
- [ ] Source independence and conflicts are assessed.
- [ ] Hindi and English core content exists or is clearly marked unavailable.
- [ ] Translation origin/review status is visible.
- [ ] Preparation and route are source-backed; missing values remain unknown.
- [ ] Side-effect and interaction content includes context and limitations.
- [ ] No report found is never rendered as safe/no side effects.
- [ ] Medical-history feature has privacy and clinical approval.
- [ ] Multi-symptom matching shows coverage, uncertainty, alternatives, and abstains.
- [ ] No screen diagnoses, prescribes, or advises medication changes.
- [ ] Tests cover conflicting sources, missing evidence, low confidence, and multilingual edge cases.
- [ ] Source license and attribution checks pass.
