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
        "Dr. Alexa Torontow": 1,
    },
    "injections": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 1,
    },
    "botanical": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 1,
    },
    "clinical_nutrition": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 1,
    },
    "lifestyle_coaching": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 1,
    },
    "functional_testing": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 2,
    },
    "orthopedic_injections": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 3,
        "Dr. Alexa Torontow": 3,
    },
    "ozone_therapy": {
        "Dr. Ali Nurani": 1,
        "Dr. Marisa Hucal": 3,
        "Dr. Alexa Torontow": 3,
    },
    "acupuncture_nd": {
        "Dr. Ali Nurani": 3,
        "Dr. Marisa Hucal": 1,
        "Dr. Alexa Torontow": 2,
    },
    "bio_regulatory": {
        "Dr. Ali Nurani": 3,
        "Dr. Marisa Hucal": 3,
        "Dr. Alexa Torontow": 1,
    },
    "aesthetic_medicine": {
        "Dr. Ali Nurani": 3,
        "Dr. Marisa Hucal": 2,
        "Dr. Alexa Torontow": 2,
    },
    "environmental_medicine": {
        "Dr. Ali Nurani": 2,
        "Dr. Marisa Hucal": 3,
        "Dr. Alexa Torontow": 2,
    },
    "chelation": {
        "Dr. Ali Nurani": 3,
        "Dr. Marisa Hucal": 3,
        "Dr. Alexa Torontow": 3,
    },
    "homeopathy": {
        "Dr. Ali Nurani": 3,
        "Dr. Marisa Hucal": 3,
        "Dr. Alexa Torontow": 3,
    },
    "physical_medicine": {
        "Dr. Ali Nurani": 3,
        "Dr. Marisa Hucal": 3,
        "Dr. Alexa Torontow": 3,
    },
    "craniosacral": {
        "Dr. Ali Nurani": 3,
        "Dr. Marisa Hucal": 3,
        "Dr. Alexa Torontow": 3,
    },
    "laser_therapy": {
        "Dr. Ali Nurani": 3,
        "Dr. Marisa Hucal": 3,
        "Dr. Alexa Torontow": 3,
    },
    # Health-concern-adjacent modalities (prenatal/postpartum)
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
    # injections (vitamin/B12/lipotropic shots)
    "b12 injection": "injections", "b12 shot": "injections",
    "vitamin injection": "injections", "vitamin shot": "injections",
    "lipotropic": "injections", "vitamin d injection": "injections",
    "intramuscular injection": "injections",
    # orthopedic_injections (prolotherapy, TPI, neural therapy)
    "prolotherapy": "orthopedic_injections", "prolo": "orthopedic_injections",
    "trigger point injection": "orthopedic_injections",
    "neural therapy": "orthopedic_injections",
    "proloneural": "orthopedic_injections",
    "regenerative injection": "orthopedic_injections",
    # ozone_therapy
    "ozone": "ozone_therapy", "ozone therapy": "ozone_therapy",
    "mah": "ozone_therapy", "insufflation": "ozone_therapy",
    # botanical
    "botanical": "botanical", "herbal": "botanical", "herb": "botanical",
    "tincture": "botanical",
    # clinical_nutrition
    "nutrition": "clinical_nutrition", "nutritional": "clinical_nutrition",
    "dietetics": "clinical_nutrition", "supplementation": "clinical_nutrition",
    "metabolic balance": "clinical_nutrition",
    # lifestyle_coaching
    "lifestyle coaching": "lifestyle_coaching", "health coaching": "lifestyle_coaching",
    "sleep hygiene": "lifestyle_coaching", "exercise prescription": "lifestyle_coaching",
    # acupuncture_nd
    "acupuncture": "acupuncture_nd", "tcm": "acupuncture_nd",
    "traditional chinese": "acupuncture_nd",
    # functional_testing
    "functional test": "functional_testing", "functional lab": "functional_testing",
    "dutch": "functional_testing", "hormone test": "functional_testing",
    "gi-360": "functional_testing", "gi 360": "functional_testing",
    "gi-map": "functional_testing", "gi map": "functional_testing",
    "gut test": "functional_testing", "sibo test": "functional_testing",
    "sibo breath": "functional_testing",
    "food sensitivity test": "functional_testing",
    "food allergy test": "functional_testing",
    # bio_regulatory
    "bio-regulatory": "bio_regulatory", "bioregulatory": "bio_regulatory",
    "bio regulatory": "bio_regulatory",
    # aesthetic_medicine
    "microneedling": "aesthetic_medicine", "cosmetic acupuncture": "aesthetic_medicine",
    "naturopathic facial": "aesthetic_medicine",
    # environmental_medicine
    "mold": "environmental_medicine", "mycotox": "environmental_medicine",
    "toxic load": "environmental_medicine", "gpl-tox": "environmental_medicine",
    "heavy metal": "environmental_medicine", "mold detox": "environmental_medicine",
    # chelation
    "chelation": "chelation",
    # homeopathy
    "homeopathy": "homeopathy", "homeopathic": "homeopathy",
    # physical_medicine
    "hydrotherapy": "physical_medicine",
    "naturopathic manipulation": "physical_medicine",
    # craniosacral
    "craniosacral": "craniosacral",
    # laser_therapy
    "laser therapy": "laser_therapy", "cold laser": "laser_therapy",
    "low-level laser": "laser_therapy", "lllt": "laser_therapy",
    # prenatal / postpartum
    "prenatal": "prenatal", "pregnancy": "prenatal", "pregnant": "prenatal",
    "postpartum": "postpartum",
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
        "iv_therapy", "injections", "orthopedic_injections", "ozone_therapy",
        "acupuncture_nd", "functional_testing", "bio_regulatory",
        "aesthetic_medicine", "environmental_medicine", "prenatal", "postpartum",
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
    lines.append("IMPORTANT: Do NOT recommend a practitioner immediately when a patient first mentions a health concern. First, ask 1-2 clarifying questions to better understand their situation (e.g. 'Can you tell me a bit more about what you're experiencing?' or 'How long have you been dealing with this?'). Only after you have a clearer picture, recommend the Tier 1 practitioner(s) for the relevant concern or modality. Tier 1 means it is their primary clinical focus. Do NOT recommend a Tier 2 or Tier 3 practitioner over a Tier 1 practitioner, even if a Tier 2/3 practitioner's bio mentions that topic. The tier rankings above are the definitive authority on practitioner-specialty fit.")
    return "\n".join(lines)
