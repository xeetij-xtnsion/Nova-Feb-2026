"""Tier-based practitioner matching for health concerns and modalities.

Dr. Ali collected tier rankings (1=primary focus, 2=competent, 3=limited)
from all three NDs. Lorena (TCM/RMT) is excluded from tier matching.
"""

from typing import Dict, List, Optional, Set

# ── The three NDs in the tier system ─────────────────────────────────
TIER_PRACTITIONERS: Set[str] = {
    "Dr. Ali Nurani",
    "Dr. Marisa Hucal",
    "Dr. Alexa Torontow",
}

# ── Health concern tiers ─────────────────────────────────────────────
# Each category maps practitioner → tier (1 = primary focus)
HEALTH_CONCERN_TIERS: Dict[str, Dict[str, int]] = {
    "digestive": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 2,
    },
    "fertility": {
        "Dr. Ali Nurani": 3,
        "Dr. Marisa Hucal": 2,
        "Dr. Alexa Torontow": 1,
    },
    "hormonal": {
        "Dr. Ali Nurani": 2,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 1,
    },
    "autoimmune": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 3,
        "Dr. Alexa Torontow": 3,
    },
    "cancer": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 3,
        "Dr. Alexa Torontow": 3,
    },
    "weight": {
        "Dr. Ali Nurani": 2,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 3,
    },
    "pain": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 3,
        "Dr. Alexa Torontow": 3,
    },
    "mental_health": {
        "Dr. Ali Nurani": 2,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 2,
    },
    "immune": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 2,
        "Dr. Alexa Torontow": 3,
    },
    "skin": {
        "Dr. Ali Nurani": 2,
        "Dr. Marisa Hucal": 2,
        "Dr. Alexa Torontow": 2,
    },
}

# ── Modality tiers ───────────────────────────────────────────────────
MODALITY_TIERS: Dict[str, Dict[str, int]] = {
    "iv_therapy": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 3,
    },
    "injections": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 3,
    },
    "prolotherapy": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 3,
        "Dr. Alexa Torontow": 3,
    },
    "ozone_therapy": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 3,
        "Dr. Alexa Torontow": 3,
    },
    "botanical": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 1,
    },
    "nutrition": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 1,
    },
    "acupuncture_nd": {
        "Dr. Ali Nurani": 3,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 3,
    },
    "chelation": {
        "Dr. Ali Nurani": 2,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 3,
    },
    "functional_testing": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 1,
    },
    "hormone_testing": {
        "Dr. Ali Nurani": 2,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 1,
    },
    "food_sensitivity_testing": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 2,
    },
    "gut_testing": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 2,
    },
    "prenatal": {
        "Dr. Ali Nurani": 3,
        "Dr. Marisa Hucal": 2,
        "Dr. Alexa Torontow": 1,
    },
    "postpartum": {
        "Dr. Ali Nurani": 3,
        "Dr. Marisa Hucal": 2,
        "Dr. Alexa Torontow": 1,
    },
    "metabolic_balance": {
        "Dr. Ali Nurani": 3,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 3,
    },
    "mold_toxin_testing": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 2,
        "Dr. Alexa Torontow": 3,
    },
}

# ── Keyword → category mappings ─────────────────────────────────────
CONCERN_KEYWORDS: Dict[str, str] = {
    # digestive
    "digest": "digestive", "digestion": "digestive", "digestive": "digestive",
    "gut": "digestive", "bloat": "digestive", "bloating": "digestive",
    "ibs": "digestive", "stomach": "digestive", "nausea": "digestive",
    "constipat": "digestive", "sibo": "digestive", "intestin": "digestive",
    # fertility
    "fertil": "fertility", "fertility": "fertility", "conceiv": "fertility",
    "infertil": "fertility", "ivf": "fertility", "iui": "fertility",
    "trying to conceive": "fertility", "get pregnant": "fertility",
    # hormonal
    "hormone": "hormonal", "hormonal": "hormonal", "thyroid": "hormonal",
    "menopaus": "hormonal", "period": "hormonal", "pcos": "hormonal",
    "endocrine": "hormonal",
    # autoimmune
    "autoimmune": "autoimmune", "lupus": "autoimmune",
    "rheumatoid": "autoimmune", "celiac": "autoimmune",
    "hashimoto": "autoimmune", "graves": "autoimmune",
    "crohn": "autoimmune", "colitis": "autoimmune",
    "scleroderma": "autoimmune", "sjogren": "autoimmune",
    "fibromyalgia": "autoimmune", "multiple sclerosis": "autoimmune",
    # cancer
    "cancer": "cancer", "oncology": "cancer", "tumor": "cancer",
    "tumour": "cancer", "chemo": "cancer", "chemotherapy": "cancer",
    "radiation": "cancer", "carcinoma": "cancer", "lymphoma": "cancer",
    # weight
    "weight": "weight", "diet": "weight", "obesity": "weight",
    "lose weight": "weight", "gain weight": "weight",
    # pain
    "pain": "pain", "joint": "pain", "ligament": "pain",
    "tendon": "pain", "knee": "pain", "shoulder": "pain",
    "sprain": "pain", "musculoskeletal": "pain",
    # mental_health
    "stress": "mental_health", "anxiety": "mental_health",
    "anxious": "mental_health", "depression": "mental_health",
    "depressed": "mental_health", "insomnia": "mental_health",
    "sleep": "mental_health", "burnout": "mental_health",
    # immune
    "immune": "immune", "immunity": "immune", "wellness": "immune",
    "flu": "immune",
    # skin
    "skin": "skin", "acne": "skin", "eczema": "skin",
    "psoriasis": "skin", "rash": "skin",
}

MODALITY_KEYWORDS: Dict[str, str] = {
    # iv_therapy
    "iv therapy": "iv_therapy", "iv drip": "iv_therapy",
    "iv nutrient": "iv_therapy", "intravenous": "iv_therapy",
    "iv infusion": "iv_therapy",
    # injections
    "injection": "injections", "intramuscular": "injections",
    "vitamin injection": "injections", "b12 injection": "injections",
    "trigger point": "injections",
    # prolotherapy
    "prolotherapy": "prolotherapy", "prolo": "prolotherapy",
    "regenerative injection": "prolotherapy",
    # ozone_therapy
    "ozone": "ozone_therapy", "ozone therapy": "ozone_therapy",
    # botanical
    "botanical": "botanical", "herbal": "botanical", "herb": "botanical",
    # nutrition
    "nutrition": "nutrition", "nutritional": "nutrition",
    # acupuncture_nd
    "acupuncture": "acupuncture_nd",
    # chelation
    "chelation": "chelation",
    # functional_testing
    "functional test": "functional_testing",
    # hormone_testing
    "dutch": "hormone_testing", "hormone test": "hormone_testing",
    # food_sensitivity_testing
    "food sensitivity": "food_sensitivity_testing",
    "food allergy": "food_sensitivity_testing",
    "food intolerance": "food_sensitivity_testing",
    # gut_testing
    "gi-360": "gut_testing", "gi 360": "gut_testing",
    "gut test": "gut_testing", "sibo test": "gut_testing",
    "sibo breath": "gut_testing",
    # prenatal
    "prenatal": "prenatal", "pregnancy": "prenatal", "pregnant": "prenatal",
    # postpartum
    "postpartum": "postpartum",
    # metabolic_balance
    "metabolic balance": "metabolic_balance",
    # mold_toxin_testing
    "mold": "mold_toxin_testing", "mycotox": "mold_toxin_testing",
    "toxin": "mold_toxin_testing", "gpl-tox": "mold_toxin_testing",
}


def detect_concerns(message: str) -> List[str]:
    """Detect health concern categories from a patient message."""
    msg = message.lower()
    found: Set[str] = set()
    # Check multi-word keywords first, then single-word
    for keyword, category in sorted(CONCERN_KEYWORDS.items(), key=lambda x: -len(x[0])):
        if keyword in msg:
            found.add(category)
    return list(found)


def detect_modalities(message: str) -> List[str]:
    """Detect modality categories from a patient message."""
    msg = message.lower()
    found: Set[str] = set()
    for keyword, category in sorted(MODALITY_KEYWORDS.items(), key=lambda x: -len(x[0])):
        if keyword in msg:
            found.add(category)
    return list(found)


def match_practitioners(
    message: str,
    eligible: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """Rank practitioners by tier match for a patient message.

    Returns list of {"name", "tier", "match_type"} sorted best-first.
    If *eligible* is provided, only those practitioners are considered.

    Algorithm:
    1. Check modality match first (specific treatment request).
    2. If single Tier 1 for modality → done.
    3. If multiple Tier 1 for modality → use concern as tiebreaker.
    4. If no modality match → use concerns directly.
    5. Tie-break: alphabetical (placeholder until Jane App availability).
    """
    pool = TIER_PRACTITIONERS
    if eligible is not None:
        pool = pool & set(eligible)
    if not pool:
        return []

    modalities = detect_modalities(message)
    concerns = detect_concerns(message)

    if not modalities and not concerns:
        return []

    def _best_from_tiers(
        categories: List[str], tier_data: Dict[str, Dict[str, int]], match_type: str
    ) -> List[Dict[str, str]]:
        """Score practitioners across categories — lowest total tier wins."""
        scores: Dict[str, int] = {}
        for cat in categories:
            tiers = tier_data.get(cat, {})
            for name in pool:
                scores[name] = scores.get(name, 0) + tiers.get(name, 99)
        if not scores:
            return []
        min_score = min(scores.values())
        ranked = sorted(scores.items(), key=lambda x: (x[1], x[0]))
        return [
            {"name": name, "tier": score, "match_type": match_type}
            for name, score in ranked
        ]

    # Step 1: modality match
    if modalities:
        modality_results = _best_from_tiers(modalities, MODALITY_TIERS, "modality")
        if modality_results:
            # If single Tier 1 winner, done
            tier1 = [r for r in modality_results if r["tier"] == modality_results[0]["tier"]]
            if len(tier1) == 1:
                return modality_results
            # Multiple tied on modality — use concerns as tiebreaker
            if concerns:
                concern_scores: Dict[str, int] = {}
                for cat in concerns:
                    tiers = HEALTH_CONCERN_TIERS.get(cat, {})
                    for name in pool:
                        concern_scores[name] = concern_scores.get(name, 0) + tiers.get(name, 99)
                # Re-sort tied leaders by concern score, then alphabetical
                combined = []
                for r in modality_results:
                    combined.append({
                        "name": r["name"],
                        "tier": r["tier"],
                        "match_type": "modality+concern",
                        "_concern_score": concern_scores.get(r["name"], 99),
                    })
                combined.sort(key=lambda x: (x["tier"], x["_concern_score"], x["name"]))
                return [
                    {"name": c["name"], "tier": c["tier"], "match_type": c["match_type"]}
                    for c in combined
                ]
            return modality_results

    # Step 2: concern-only match
    if concerns:
        return _best_from_tiers(concerns, HEALTH_CONCERN_TIERS, "concern")

    return []


def get_best_practitioner(
    message: str,
    eligible: Optional[List[str]] = None,
) -> Optional[str]:
    """Return the single best-matched practitioner name, or None."""
    results = match_practitioners(message, eligible)
    return results[0]["name"] if results else None


def get_tier_summary() -> str:
    """Return a text block summarizing practitioner specialties for the LLM."""
    lines = [
        "",
        "PRACTITIONER SPECIALTIES (Tier 1 = primary focus, Tier 2 = competent, Tier 3 = limited):",
        "",
        "Health Concerns:",
    ]
    for category, tiers in HEALTH_CONCERN_TIERS.items():
        t1 = [n.split()[-1] for n, t in tiers.items() if t == 1]
        t2 = [n.split()[-1] for n, t in tiers.items() if t == 2]
        label = category.replace("_", " ").title()
        parts = []
        if t1:
            parts.append(f"Tier 1: {', '.join(sorted(t1))}")
        if t2:
            parts.append(f"Tier 2: {', '.join(sorted(t2))}")
        lines.append(f"  {label}: {' | '.join(parts)}")

    lines.append("")
    lines.append("Key Modalities:")
    highlight_modalities = [
        "iv_therapy", "injections", "prolotherapy", "ozone_therapy",
        "acupuncture_nd", "chelation", "prenatal", "postpartum",
        "metabolic_balance", "mold_toxin_testing",
    ]
    for mod in highlight_modalities:
        tiers = MODALITY_TIERS.get(mod, {})
        t1 = [n.split()[-1] for n, t in tiers.items() if t == 1]
        t2 = [n.split()[-1] for n, t in tiers.items() if t == 2]
        label = mod.replace("_", " ").title()
        parts = []
        if t1:
            parts.append(f"Tier 1: {', '.join(sorted(t1))}")
        if t2:
            parts.append(f"Tier 2: {', '.join(sorted(t2))}")
        lines.append(f"  {label}: {' | '.join(parts)}")

    lines.append("")
    lines.append("IMPORTANT: When a patient asks which doctor to see or who you recommend, ALWAYS recommend the Tier 1 practitioner(s) for the relevant concern or modality FIRST. Tier 1 means it is their primary clinical focus. Do NOT recommend a Tier 2 or Tier 3 practitioner over a Tier 1 practitioner, even if a Tier 2/3 practitioner's bio mentions that topic. The tier rankings above are the definitive authority on practitioner-specialty fit.")
    return "\n".join(lines)
