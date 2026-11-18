# Stage C.2 Work Package 1 (WP-1): Canonical Concept Catalog Coverage Report

**Date:** 2026-11-19  
**Status:** Complete & Verified  
**Schema Version:** Stage C / Migration 3 (`semantic_dravyaguna`)  
**Companion Artifacts:**
- Module: [`stage_c_review/concept_catalog.py`](file:///e:/PythonProject/NITT-PSP-Project/stage_c_review/concept_catalog.py)
- Test Suite: [`stage_c_review/test_wp1_concept_catalog.py`](file:///e:/PythonProject/NITT-PSP-Project/stage_c_review/test_wp1_concept_catalog.py)
- Architecture Record: [`stage_c_review/ADR_STAGE_C2_ARCHITECTURE.md`](file:///e:/PythonProject/NITT-PSP-Project/stage_c_review/ADR_STAGE_C2_ARCHITECTURE.md)

---

## 1. Executive Summary

Work Package 1 (WP-1: Canonical Concept Catalog) delivers the foundational standardized ontology dataset, namespace validation module, and multilingual resolution engine for Stage C.2.

All implementations strictly adhere to:
- The 11 accepted Stage C concept domains and uppercase prefix namespaces per ADR Decision 1.B.
- The Single-Preferred-Label Application Invariant per ADR Decision 9.2 (at most one `is_preferred = 1` row per `(concept_id, language_code, script_code)`).
- Decoupled concept lifecycle (`active`, `provisional`) and label verification (`unreviewed`) per ADR Decision 2.
- The two curator-adjudicated taxonomy resolutions:
  1. **Dosha Effects:** Strictly 2 active directional effect concepts (`EFFECT_DECREASE` and `EFFECT_INCREASE`); compound balance expressions decompose in future backfill/ingestion work packages (WP-3/WP-4).
  2. **Virya Scope & Ashta-Virya:** 2 active consensus potencies (`VIRYA_USHNA`, `VIRYA_SHITA`), 7 provisional extended Ashta-Virya potency tokens (`VIRYA_SNIGDHA`, `VIRYA_RUKSHA`, `VIRYA_GURU`, `VIRYA_LAGHU`, `VIRYA_TIKSHNA`, `VIRYA_MRIDU`, `VIRYA_MANDA`), and 9 active corresponding *Gurvadi Guna* attributes under `guna`.

---

## 2. Catalog Metrics & Summary Tables

### 2.1 Domain Distribution

| Domain | Namespace Prefix | Active Concepts | Provisional Concepts | Total Concepts | Preferred Labels | Synonym Labels | Total Labels | Citations |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `rasa` | `RASA_` | 6 | 0 | 6 | 24 | 3 | 27 | 6 |
| `guna` | `GUNA_` | 30 | 0 | 30 | 120 | 19 | 139 | 30 |
| `virya` | `VIRYA_` | 2 | 7 | 9 | 36 | 6 | 42 | 9 |
| `vipaka` | `VIPAKA_` | 3 | 0 | 3 | 12 | 1 | 13 | 3 |
| `dosha` | `DOSHA_` | 3 | 0 | 3 | 12 | 4 | 16 | 3 |
| `dosha_effect` | `EFFECT_` | 2 | 0 | 2 | 8 | 2 | 10 | 2 |
| `prabhava` | `PRABHAVA_` | 6 | 0 | 6 | 24 | 4 | 28 | 6 |
| `karma` | `KARMA_` | 22 | 0 | 22 | 88 | 14 | 102 | 22 |
| `plant_part` | `PART_` | 16 | 0 | 16 | 64 | 17 | 81 | 16 |
| `preparation_form` | `PREP_` | 15 | 0 | 15 | 60 | 18 | 78 | 15 |
| `indication` | `IND_` | 24 | 0 | 24 | 96 | 17 | 113 | 24 |
| **Total** | — | **129** | **7** | **136** | **544** | **105** | **649** | **136** |

### 2.2 Label Representation by Language and Script

| Language | Script Code | Script Name | Preferred Labels | Variant / Synonym Labels | Total Labels |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `sa` (Sanskrit) | `Latn` | Latin (IAST Transliteration) | 136 | 98 | 234 |
| `sa` (Sanskrit) | `Deva` | Devanagari (Classical Script) | 136 | 7 | 143 |
| `hi` (Hindi) | `Deva` | Devanagari (Standard Hindi) | 136 | 0 | 136 |
| `en` (English) | `Latn` | Latin (Scholarly English) | 136 | 0 | 136 |
| **Total** | — | — | **544** | **105** | **649** |

---

## 3. Complete Inventory of Seeded Concepts

### 3.1 Rasa (6 Concepts — Active)
| Concept Code | English Preferred | Hindi Preferred | Sanskrit Deva Preferred | Sanskrit IAST Preferred | Authoritative Citation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `RASA_MADHURA` | Sweet | मधुर | मधुर | Madhura | *Caraka Saṃhitā, Sūtrasthāna 26.42* |
| `RASA_AMLA` | Sour | अम्ल | अम्ल | Amla | *Caraka Saṃhitā, Sūtrasthāna 26.43* |
| `RASA_LAVANA` | Salty | नमकीन (लवण) | लवण | Lavaṇa | *Caraka Saṃhitā, Sūtrasthāna 26.44* |
| `RASA_KATU` | Pungent | कटु (तीखा) | कटु | Kaṭu | *Caraka Saṃhitā, Sūtrasthāna 26.45* |
| `RASA_TIKTA` | Bitter | तिक्त (कड़वा) | तिक्त | Tikta | *Caraka Saṃhitā, Sūtrasthāna 26.46* |
| `RASA_KASHAYA` | Astringent | कषाय (कसैला) | कषाय | Kaṣāya | *Caraka Saṃhitā, Sūtrasthāna 26.47* |

### 3.2 Guna (30 Concepts — Active)
#### 20 Gurvadi Gunas
| Concept Code | English Preferred | Hindi Preferred | Sanskrit Deva Preferred | Sanskrit IAST Preferred | Authoritative Citation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GUNA_GURU` | Heavy | गुरु (भारी) | गुरु | Guru | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |
| `GUNA_LAGHU` | Light | लघु (हल्का) | लघु | Laghu | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |
| `GUNA_SHITA` | Cold | शीत (ठंडा) | शीत | Śīta | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |
| `GUNA_USHNA` | Hot | उष्ण (गर्म) | उष्ण | Uṣṇa | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |
| `GUNA_SNIGDHA` | Unctuous | स्निग्ध (चिकना) | स्निग्ध | Snigdha | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |
| `GUNA_RUKSHA` | Dry | रूक्ष (रूखा) | रूक्ष | Rūkṣa | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |
| `GUNA_MANDA` | Dull / Slow | मन्द (धीमा) | मन्द | Manda | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |
| `GUNA_TIKSHNA` | Sharp / Penetrating | तीक्ष्ण (तीव्र) | तीक्ष्ण | Tīkṣṇa | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |
| `GUNA_STHIRA` | Stable / Static | स्थिर | स्थिर | Sthira | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |
| `GUNA_SARA` | Mobile / Fluid | सर (गतिशील) | सर | Sara | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |
| `GUNA_MRIDU` | Soft | मृदु (कोमल) | मृदु | Mṛdu | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |
| `GUNA_KATHINA` | Hard | कठिन (कठोर) | कठिन | Kaṭhina | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |
| `GUNA_VISHADA` | Clear / Non-slimy | विशद (स्वच्छ) | विशद | Viśada | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |
| `GUNA_PICCHILA` | Slimy / Mucilaginous | पिच्छिल (लुआबदार) | पिच्छिल | Picchila | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |
| `GUNA_SHLAKSHNA` | Smooth | श्लक्ष्ण (चिकना) | श्लक्ष्ण | Ślakṣṇa | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |
| `GUNA_KHARA` | Rough | खर (खुरदरा) | खर | Khara | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |
| `GUNA_SUKSHMA` | Subtle / Minute | सूक्ष्म (महीन) | सूक्ष्म | Sūkṣma | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |
| `GUNA_STHULA` | Gross / Dense | स्थूल (मोटा) | स्थूल | Sthūla | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |
| `GUNA_SANDRA` | Solid / Dense | सान्द्र (गाढ़ा) | सान्द्र | Sāndra | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |
| `GUNA_DRAVA` | Liquid / Fluid | द्रव (तरल) | द्रव | Drava | *Caraka Saṃhitā, Sūtrasthāna 26.29-30* |

#### 10 Paradi Gunas
| Concept Code | English Preferred | Hindi Preferred | Sanskrit Deva Preferred | Sanskrit IAST Preferred | Authoritative Citation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GUNA_PARA` | Superior / Primary | पर (श्रेष्ठ) | पर | Para | *Caraka Saṃhitā, Sūtrasthāna 26.29-31* |
| `GUNA_APARA` | Inferior / Secondary | अपर (गौण) | अपर | Apara | *Caraka Saṃhitā, Sūtrasthāna 26.29-31* |
| `GUNA_YUKTI` | Rational Application | युक्ति (तर्कसंगत योजना) | युक्ति | Yukti | *Caraka Saṃhitā, Sūtrasthāna 26.29-31* |
| `GUNA_SAMKHYA` | Number / Enumeration | संख्या (गणना) | संख्या | Saṃkhyā | *Caraka Saṃhitā, Sūtrasthāna 26.29-31* |
| `GUNA_SAMYOGA` | Combination / Conjunction | संयोग (मिलन) | संयोग | Saṃyoga | *Caraka Saṃhitā, Sūtrasthāna 26.29-31* |
| `GUNA_VIBHAGA` | Division / Disjunction | विभाग (विभाजन) | विभाग | Vibhāga | *Caraka Saṃhitā, Sūtrasthāna 26.29-31* |
| `GUNA_PRITHAKTVA` | Separateness / Distinction | पृथक्त्व (भिन्नता) | पृथक्त्व | Pṛthaktva | *Caraka Saṃhitā, Sūtrasthāna 26.29-31* |
| `GUNA_PARIMANA` | Measure / Dimension | परिमाण (माप) | परिमाण | Parimāṇa | *Caraka Saṃhitā, Sūtrasthāna 26.29-31* |
| `GUNA_SAMSKARA` | Processing / Transformation | संस्कार (प्रक्रिया) | संस्कार | Saṃskāra | *Caraka Saṃhitā, Sūtrasthāna 26.29-31* |
| `GUNA_ABHYASA` | Habituation / Practice | अभ्यास (निरंतर प्रयोग) | अभ्यास | Abhyāsa | *Caraka Saṃhitā, Sūtrasthāna 26.29-31* |

### 3.3 Virya (9 Concepts: 2 Active Consensus + 7 Provisional Ashta-Virya)
| Concept Code | Status | English Preferred | Hindi Preferred | Sanskrit Deva Preferred | Sanskrit IAST Preferred | Authoritative Citation |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `VIRYA_USHNA` | `active` | Hot Potency | उष्ण वीर्य (गर्म प्रभाव) | उष्ण | Uṣṇa | *Caraka Saṃhitā, Sūtrasthāna 26.65* |
| `VIRYA_SHITA` | `active` | Cold Potency | शीत वीर्य (ठंडा प्रभाव) | शीत | Śīta | *Caraka Saṃhitā, Sūtrasthāna 26.65* |
| `VIRYA_SNIGDHA` | `provisional` | Unctuous Potency | स्निग्ध वीर्य | स्निग्ध | Snigdha | *Suśruta Saṃhitā, Sūtrasthāna 40.5* |
| `VIRYA_RUKSHA` | `provisional` | Dry Potency | रूक्ष वीर्य | रूक्ष | Rūkṣa | *Suśruta Saṃhitā, Sūtrasthāna 40.5* |
| `VIRYA_GURU` | `provisional` | Heavy Potency | गुरु वीर्य | गुरु | Guru | *Suśruta Saṃhitā, Sūtrasthāna 40.5* |
| `VIRYA_LAGHU` | `provisional` | Light Potency | लघु वीर्य | लघु | Laghu | *Suśruta Saṃhitā, Sūtrasthāna 40.5* |
| `VIRYA_TIKSHNA` | `provisional` | Sharp Potency | तीक्ष्ण वीर्य | तीक्ष्ण | Tīkṣṇa | *Suśruta Saṃhitā, Sūtrasthāna 40.5* |
| `VIRYA_MRIDU` | `provisional` | Soft Potency | मृदु वीर्य | मृदु | Mṛdu | *Suśruta Saṃhitā, Sūtrasthāna 40.5* |
| `VIRYA_MANDA` | `provisional` | Dull Potency | मन्द वीर्य | मन्द | Manda | *Aṣṭāṅga Hṛdaya / Nighaṇṭu commentaries* |

### 3.4 Vipaka (3 Concepts — Active)
| Concept Code | English Preferred | Hindi Preferred | Sanskrit Deva Preferred | Sanskrit IAST Preferred | Authoritative Citation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `VIPAKA_MADHURA` | Sweet Post-Digestive Effect | मधुर विपाक | मधुर | Madhura | *Caraka Saṃhitā, Sūtrasthāna 26.57* |
| `VIPAKA_AMLA` | Sour Post-Digestive Effect | अम्ल विपाक | अम्ल | Amla | *Caraka Saṃhitā, Sūtrasthāna 26.58* |
| `VIPAKA_KATU` | Pungent Post-Digestive Effect | कटु विपाक | कटु | Kaṭu | *Caraka Saṃhitā, Sūtrasthāna 26.59* |

### 3.5 Dosha (3 Concepts — Active)
| Concept Code | English Preferred | Hindi Preferred | Sanskrit Deva Preferred | Sanskrit IAST Preferred | Authoritative Citation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `DOSHA_VATA` | Vata Dosha | वात दोष | वात | Vāta | *Caraka Saṃhitā, Sūtrasthāna 1.57* |
| `DOSHA_PITTA` | Pitta Dosha | पित्त दोष | पित्त | Pitta | *Caraka Saṃhitā, Sūtrasthāna 1.57* |
| `DOSHA_KAPHA` | Kapha Dosha | कफ दोष | कफ | Kapha | *Caraka Saṃhitā, Sūtrasthāna 1.57* |

### 3.6 Dosha Effect (2 Concepts — Active Directional Effects)
| Concept Code | English Preferred | Hindi Preferred | Sanskrit Deva Preferred | Sanskrit IAST Preferred | Authoritative Citation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `EFFECT_DECREASE` | Pacifies / Decreases | शामक (शांत करने वाला) | शमन / हर | Śamana / Hara | *Caraka Saṃhitā, Sūtrasthāna 1.62* |
| `EFFECT_INCREASE` | Aggravates / Increases | प्रकोपक (बढ़ाने वाला) | प्रकोपक / वर्धक | Prakopaka / Vardhaka | *Caraka Saṃhitā, Sūtrasthāna 1.62* |

### 3.7 Prabhava (6 Concepts — Active Core Set)
| Concept Code | English Preferred | Hindi Preferred | Sanskrit Deva Preferred | Sanskrit IAST Preferred | Authoritative Citation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `PRABHAVA_VISHAGHNA` | Antitoxic / Anti-poisonous Action | विषघ्न (विषनाशक) | विषघ्न | Viṣaghna | *Caraka Saṃhitā, Sūtrasthāna 26.70* |
| `PRABHAVA_MEDHYA` | Intellect-Promoting / Nootropic | मेध्य (बुद्धिवर्धक) | मेध्य | Medhya | *Caraka Saṃhitā, Cikitsāsthāna 1.3* |
| `PRABHAVA_HRIDYA` | Cardioprotective / Cardiac Tonic | हृद्य (हृदय पोषक) | हृद्य | Hṛdya | *Caraka Saṃhitā, Sūtrasthāna 4.10* |
| `PRABHAVA_RASAYANA` | Rejuvenative Action | रसायन (कायाकल्प) | रसायन | Rasāyana | *Caraka Saṃhitā, Cikitsāsthāna 1.1* |
| `PRABHAVA_VAMAKA` | Emetic Action | वामक (वमनकारी) | वामक | Vāmaka | *Caraka Saṃhitā, Kalpasthāna 1.5* |
| `PRABHAVA_VIRECHAKA` | Purgative Action | विरेचक (दस्तावर) | विरेचक | Virecaka | *Caraka Saṃhitā, Kalpasthāna 1.6* |

### 3.8 Karma (22 Concepts — Active Classical Actions)
| Concept Code | English Preferred | Hindi Preferred | Sanskrit Deva Preferred | Sanskrit IAST Preferred | Authoritative Citation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `KARMA_DEEPANA` | Appetizer / Digestive Stimulant | दीपन (अग्निदीपक) | दीपन | Dīpana | *Śārṅgadhara Saṃhitā, Pūrva Khaṇḍa 4.1* |
| `KARMA_PACHANA` | Digestant / Ama Metabolizer | पाचन (आमपाचक) | पाचन | Pācana | *Śārṅgadhara Saṃhitā, Pūrva Khaṇḍa 4.1* |
| `KARMA_ANULOMANA` | Carminative / Peristalsis Normalizer | अनुलोमन (वात अनुलोमक) | अनुलोमन | Anulomana | *Śārṅgadhara Saṃhitā, Pūrva Khaṇḍa 4.4* |
| `KARMA_GRAHI` | Bowel Binder / Fluid Absorber | ग्राही (मल संग्राहक) | ग्राही | Grāhī | *Śārṅgadhara Saṃhitā, Pūrva Khaṇḍa 4.8* |
| `KARMA_STAMBHANA` | Astringent / Hemostatic | स्तम्भन (रोकने वाला) | स्तम्भन | Stambhana | *Śārṅgadhara Saṃhitā, Pūrva Khaṇḍa 4.9* |
| `KARMA_RECHANA` | Purgative / Evacuant | रेचन (दस्त कराने वाला) | रेचन | Recana | *Śārṅgadhara Saṃhitā, Pūrva Khaṇḍa 4.7* |
| `KARMA_BHEDANA` | Drastic Purgative / Fecal Mass Breaker | भेदन (मल भेदक) | भेदन | Bhedana | *Śārṅgadhara Saṃhitā, Pūrva Khaṇḍa 4.6* |
| `KARMA_RASAYANA` | Rejuvenative / Vitality Enhancer | रसायन कर्म | रसायन | Rasāyana | *Caraka Saṃhitā, Cikitsāsthāna 1.1* |
| `KARMA_VAJIKARANA` | Aphrodisiac / Virility Enhancer | वाजीकरण (वीर्यवर्धक) | वाजीकरण | Vājīkaraṇa | *Caraka Saṃhitā, Cikitsāsthāna 2.1* |
| `KARMA_BALYA` | Strength Promoter / Tonic | बल्य (बलवर्धक) | बल्य | Balya | *Caraka Saṃhitā, Sūtrasthāna 4.7* |
| `KARMA_BRIMHANA` | Nourishing / Body Mass Promoter | बृंहण (पुष्टिकारक) | बृंहण | Bṛṃhaṇa | *Caraka Saṃhitā, Sūtrasthāna 22.10* |
| `KARMA_LANGHANA` | Lightening / Depleting | लङ्घन (लघुताकारक) | लङ्घन | Laṅghana | *Caraka Saṃhitā, Sūtrasthāna 22.9* |
| `KARMA_LEKHANA` | Scraping / Lipid-Reducing | लेखन (मेदनाशक) | लेखन | Lekhana | *Śārṅgadhara Saṃhitā, Pūrva Khaṇḍa 4.11* |
| `KARMA_CHEDANA` | Expectorant / Dosha Detachment | छेदन (कफ विदारक) | छेदन | Chedana | *Śārṅgadhara Saṃhitā, Pūrva Khaṇḍa 4.10* |
| `KARMA_SHOTHAHARA` | Anti-inflammatory / Edema-Reducing | शोथहर (सूजन नाशक) | शोथहर | Śothahara | *Caraka Saṃhitā, Sūtrasthāna 4.16* |
| `KARMA_JVARAGHNA` | Antipyretic / Febrifuge | ज्वरघ्न (बुखार नाशक) | ज्वरघ्न | Jvaraghna | *Caraka Saṃhitā, Sūtrasthāna 4.39* |
| `KARMA_KASAHARA` | Antitussive / Cough-Relieving | कासहर (खांसी नाशक) | कासहर | Kāsahara | *Caraka Saṃhitā, Sūtrasthāna 4.36* |
| `KARMA_KRIMIGHNA` | Anthelmintic / Anti-parasitic | कृमिघ्न (कीड़े मारने वाला) | कृमिघ्न | Kṛmighna | *Caraka Saṃhitā, Sūtrasthāna 4.15* |
| `KARMA_KUSHTHAGHNA` | Dermatological Therapeutic | कुष्ठघ्न (त्वचारोग नाशक) | कुष्ठघ्न | Kuṣṭhaghna | *Caraka Saṃhitā, Sūtrasthāna 4.13* |
| `KARMA_VEDANASTHAPANA` | Analgesic / Pain-Relieving | वेदनास्थापन (दर्द निवारक) | वेदनास्थापन | Vedanāsthāpana | *Caraka Saṃhitā, Sūtrasthāna 4.47* |
| `KARMA_SANDHANIYA` | Healing / Tissue Union Promoter | सन्धानीय (जोड़ने वाला) | सन्धानीय | Sandhānīya | *Caraka Saṃhitā, Sūtrasthāna 4.5* |
| `KARMA_VRANAROPANA` | Wound-Healing / Vulnerary | व्रणरोपण (घाव भरने वाला) | व्रणरोपण | Vraṇaropaṇa | *Suśruta Saṃhitā, Sūtrasthāna 37.15* |

### 3.9 Plant Part (16 Concepts — Active per API Part 1)
| Concept Code | English Preferred | Hindi Preferred | Sanskrit Deva Preferred | Sanskrit IAST Preferred | Authoritative Citation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `PART_ROOT` | Root | जड़ (मूल) | मूल | Mūla | *API Part 1 Monograph* |
| `PART_RHIZOME` | Rhizome | प्रकन्द | प्रकन्द | Prakanda | *API Part 1 Monograph* |
| `PART_STEM` | Stem | तना (काण्ड) | काण्ड | Kāṇḍa | *API Part 1 Monograph* |
| `PART_STEM_BARK` | Stem Bark | छाल (काण्ड-त्वक) | काण्ड-त्वक् | Kāṇḍa-Tvak | *API Part 1 Monograph* |
| `PART_ROOT_BARK` | Root Bark | मूल छाल | मूल-त्वक् | Mūla-Tvak | *API Part 1 Monograph* |
| `PART_HEARTWOOD` | Heartwood | सारकाष्ठ (सार) | सार | Sāra | *API Part 1 Monograph* |
| `PART_LEAF` | Leaf | पत्ती (पत्र) | पत्र | Patra | *API Part 1 Monograph* |
| `PART_FLOWER` | Flower | फूल (पुष्प) | पुष्प | Puṣpa | *API Part 1 Monograph* |
| `PART_FRUIT` | Fruit | फल | फल | Phala | *API Part 1 Monograph* |
| `PART_SEED` | Seed | बीज | बीज | Bīja | *API Part 1 Monograph* |
| `PART_WHOLE_PLANT` | Whole Plant | पंचांग (संपूर्ण पौधा) | पञ्चाङ्ग | Pañcāṅga | *API Part 1 Monograph* |
| `PART_EXUDATE_RESIN` | Exudate / Resin | निर्यास (गोंद / राल) | निर्यास | Niryāsa | *API Part 1 Monograph* |
| `PART_LATEX` | Latex | क्षीर (दूध) | क्षीर | Kṣīra | *API Part 1 Monograph* |
| `PART_BULB` | Bulb | शल्क-कन्द (गांठ) | शल्क-कन्द | Śalka-Kanda | *API Part 1 Monograph* |
| `PART_FRUIT_RIND` | Fruit Rind / Pericarp | फल छिलका | फल-त्वक् | Phala-Tvak | *API Part 1 Monograph* |
| `PART_ARIL` | Aril / Mace | जावित्री | जातीपत्री | Jātīpatrī | *API Part 1 Monograph* |

### 3.10 Preparation Form (15 Concepts — Active per AFI / Sharngadhara)
| Concept Code | English Preferred | Hindi Preferred | Sanskrit Deva Preferred | Sanskrit IAST Preferred | Authoritative Citation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `PREP_SWARASA` | Fresh Expressed Juice | स्वरस (ताजा रस) | स्वरस | Svarasa | *Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 1.1* |
| `PREP_KALKA` | Herbal Paste / Bolus | कल्क (पेस्ट) | कल्क | Kalka | *Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 5.1* |
| `PREP_KWATHA` | Decoction | क्वाथ (काढ़ा) | क्वाथ | Kvātha | *Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 2.1* |
| `PREP_HIMA` | Cold Infusion | हिम (शीत कषाय) | हिम | Hima | *Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 3.1* |
| `PREP_PHANTA` | Hot Infusion | फाण्ट (उष्ण कषाय) | फाण्ट | Phāṇṭa | *Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 4.1* |
| `PREP_CHURNA` | Fine Pulverized Powder | चूर्ण (पाउडर) | चूर्ण | Cūrṇa | *Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 6.1* |
| `PREP_VATI` | Tablet / Pill | वटी (गोली) | वटी | Vaṭī | *Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 7.1* |
| `PREP_AVALEHA` | Herbal Jam / Confection | अवलेह (पेस्ट) | अवलेह | Avaleha | *Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 8.1* |
| `PREP_GHRITA` | Medicated Clarified Butter | घृत (सिद्ध घी) | घृत | Ghṛta | *Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 9.1* |
| `PREP_TAILA` | Medicated Oil | तैल (सिद्ध तेल) | तैल | Taila | *Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 9.1* |
| `PREP_ASAVA` | Naturally Fermented Infusion | आसव (किण्वित आसव) | आसव | Āsava | *Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 10.1* |
| `PREP_ARISHTA` | Naturally Fermented Decoction | अरिष्ट (किण्वित क्वाथ) | अरिष्ट | Ariṣṭa | *Śārṅgadhara Saṃhitā, Madhyama Khaṇḍa 10.1* |
| `PREP_BHASMA` | Calcinated Ash Preparation | भस्म (शोधित राख) | भस्म | Bhasma | *Rasataraṅgiṇī / AFI Part 1* |
| `PREP_LEPA` | Medicated External Poultice | लेप (बाह्य लेप) | लेप | Lepa | *Śārṅgadhara Saṃhitā, Uttara Khaṇḍa 11.1* |
| `PREP_GUGGULU` | Guggulu Compound Formulation | गुग्गुलु कल्प | गुग्गुलु | Guggulu | *Ayurvedic Formulary of India (AFI) Part 1* |

### 3.11 Indication (24 Concepts — Active Clinical Conditions)
| Concept Code | English Preferred | Hindi Preferred | Sanskrit Deva Preferred | Sanskrit IAST Preferred | Authoritative Citation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `IND_JVARA` | Fever / Pyrexia | ज्वर (बुखार) | ज्वर | Jvara | *Caraka Saṃhitā, Nidānasthāna 1* |
| `IND_KASA` | Cough / Bronchitis | कास (खांसी) | कास | Kāsa | *Caraka Saṃhitā, Cikitsāsthāna 18* |
| `IND_SHWASA` | Dyspnea / Asthma | श्वास (दमा) | श्वास | Śvāsa | *Caraka Saṃhitā, Cikitsāsthāna 17* |
| `IND_PRAMEHA` | Urinary Disorders / Diabetes | प्रमेह (मधुमेह आदि) | प्रमेह | Prameha | *Caraka Saṃhitā, Nidānasthāna 4* |
| `IND_ARSHA` | Hemorrhoids / Piles | अर्श (बवासीर) | अर्श | Arśas | *Caraka Saṃhitā, Cikitsāsthāna 14* |
| `IND_ATISARA` | Diarrhea | अतिसार (दस्त) | अतिसार | Atisāra | *Caraka Saṃhitā, Cikitsāsthāna 19* |
| `IND_GRAHANI` | Malabsorption / IBS | ग्रहणी (संग्रहणी) | ग्रहणी | Grahaṇī | *Caraka Saṃhitā, Cikitsāsthāna 15* |
| `IND_KAMALA` | Jaundice / Hepatitis | कामला (पीलिया) | कामला | Kāmalā | *Caraka Saṃhitā, Cikitsāsthāna 16* |
| `IND_PANDU` | Anemia | पाण्डु (रक्तअल्पता) | पाण्डु | Pāṇḍu | *Caraka Saṃhitā, Cikitsāsthāna 16* |
| `IND_KUSHTHA` | Dermatological Disorders | कुष्ठ (त्वचा रोग) | कुष्ठ | Kuṣṭha | *Caraka Saṃhitā, Cikitsāsthāna 7* |
| `IND_SHOTHA` | Edema / Inflammation | शोथ (सूजन) | शोथ | Śotha | *Caraka Saṃhitā, Cikitsāsthāna 12* |
| `IND_AMAVATA` | Rheumatoid Arthritis | आमवात (गठिया) | आमवात | Āmavāta | *Mādhava Nidāna 25* |
| `IND_VATARAKTA` | Gout / Hyperuricemia | वातरक्त (गठिया विकार) | वातरक्त | Vātarakta | *Caraka Saṃhitā, Cikitsāsthāna 29* |
| `IND_AMLAPITTA` | Hyperacidity / Acid Peptic Disorder | अम्लपित्त (एसिडिटी) | अम्लपित्त | Amlapitta | *Mādhava Nidāna 51* |
| `IND_KRIMI` | Helminthiasis / Worm Infestation | कृमि रोग (पेट के कीड़े) | कृमि | Kṛmi | *Caraka Saṃhitā, Vimānasthāna 7* |
| `IND_MUTRAKRICCHRA` | Dysuria / Painful Micturition | मूत्रकृच्छ्र (पेशाब में जलन) | मूत्रकृच्छ्र | Mūtrakṛcchra | *Caraka Saṃhitā, Cikitsāsthāna 26* |
| `IND_ASHMARI` | Urinary Calculi / Stones | अश्मरी (पथरी) | अश्मरी | Aśmarī | *Suśruta Saṃhitā, Nidānasthāna 3* |
| `IND_VRANA` | Ulcer / Wound | व्रण (घाव / अल्सर) | व्रण | Vraṇa | *Suśruta Saṃhitā, Sūtrasthāna 21* |
| `IND_DAHA` | Burning Sensation | दाह (जलन) | दाह | Dāha | *Caraka Saṃhitā, Cikitsāsthāna 24* |
| `IND_CHARDI` | Vomiting / Emesis | छर्दि (उल्टी) | छर्दि | Chardi | *Caraka Saṃhitā, Cikitsāsthāna 20* |
| `IND_TRISHNA` | Polydipsia / Excessive Thirst | तृष्णा (अत्यधिक प्यास) | तृष्णा | Tṛṣṇā | *Caraka Saṃhitā, Cikitsāsthāna 22* |
| `IND_HRIDROGA` | Cardiac Disorders | हृद्रोग (हृदय रोग) | हृद्रोग | Hṛdroga | *Caraka Saṃhitā, Cikitsāsthāna 26* |
| `IND_UNMADA` | Psychosis / Mental Disorders | उन्माद (मानसिक विकार) | उन्माद | Unmāda | *Caraka Saṃhitā, Nidānasthāna 7* |
| `IND_APASMARA` | Epilepsy / Convulsive Disorder | अपस्मार (मिर्गी) | अपस्मार | Apasmāra | *Caraka Saṃhitā, Nidānasthāna 8* |

---

## 4. Adjudicated Taxonomy Policies & Open Candidate Deferrals

### 4.1 Adjudicated Dosha Effects Policy
- Strictly **2 active canonical directional effect concepts** are seeded in `dosha_effect`:
  - `EFFECT_DECREASE`: *Shamana* / *Kshaya* / *Hara*
  - `EFFECT_INCREASE`: *Vardhaka* / *Kopana* / *Vriddhi*
- **Compound Decomposition:** Compound statements in CCRAS or Nighantu texts such as *Tridoshahara* or "balances all three doshas" are rejected from creating a third `EFFECT_BALANCE` concept. In Stage C.2 ingestion/backfill pipelines (WP-3/WP-4), such phrases decompose into 3 discrete `EFFECT_DECREASE` assertions (`DOSHA_VATA`, `DOSHA_PITTA`, `DOSHA_KAPHA`).

### 4.2 Adjudicated Virya Policy
- The **2 primary consensus potencies** (*Dvividha Virya*) are seeded with `status = 'active'`:
  - `VIRYA_USHNA` (Hot potency)
  - `VIRYA_SHITA` (Cold potency)
- The **7 extended *Ashta-Virya* potencies** are seeded under `concept_domain = 'virya'` with `status = 'provisional'`:
  - `VIRYA_SNIGDHA`, `VIRYA_RUKSHA`, `VIRYA_GURU`, `VIRYA_LAGHU`, `VIRYA_TIKSHNA`, `VIRYA_MRIDU` (citing *Suśruta Saṃhitā, Sūtrasthāna 40.5*), and `VIRYA_MANDA` (citing *Aṣṭāṅga Hṛdaya / Nighaṇṭu commentaries*).
  - Being `provisional`, they remain cataloged for cross-treatise concordance while quarantined from default binary Virya reconciliation queries and default public profile views per ADR Decision 2.C & 3.D.
- The corresponding 9 Gunas (`GUNA_SNIGDHA`, `GUNA_RUKSHA`, `GUNA_GURU`, `GUNA_LAGHU`, `GUNA_TIKSHNA`, `GUNA_MRIDU`, `GUNA_MANDA`, `GUNA_SHITA`, `GUNA_USHNA`) remain independently active in `guna`.

### 4.3 Candidate Concepts Deferred to WP-4 Discovery
- Specialized therapeutic actions (*Karma*) beyond the 22 core actions (e.g. specialized ophthalmic actions like *Chakshushya*, hair growth promoters like *Keshya*, galactagogues like *Stanyajanana*) are cataloged as discovery candidates to be seeded during WP-4 backfill.
- Specific clinical sub-indications beyond the 24 primary conditions (e.g. *Shvitra* vitiligo, *Pradara* menorrhagia) will be mapped dynamically during WP-4 CCRAS DRAVYA backfill.
