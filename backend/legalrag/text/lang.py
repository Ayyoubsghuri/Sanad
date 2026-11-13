from __future__ import annotations

from . import arabic
from .stopwords import AR, DARIJA, EN, FR

DARIJA_MARKERS = {
    "واش", "كيفاش", "علاش", "فين", "شحال", "باش", "ديال", "ديالي", "ديالو", "بغيت", "كاين", "كاينة", "ماشي", "دابا", "فاش",
    "شنو", "راه", "راني", "غادي", "مزيان", "خدمة", "طرداتني", "طردوني", "حبسوني", "عطاني", "كنت", "ملي",
}


def detect_language(text: str) -> str:
    """Return 'ar', 'darija', 'fr', 'en' or 'unknown'. Rule-based; Darija is routed as Arabic downstream."""
    if not text or not text.strip():
        return "unknown"
    ratio = arabic.arabic_ratio(text)
    toks = arabic.tokens(text)
    if ratio >= 0.5:
        hits = sum(1 for t in toks if t in DARIJA_MARKERS or t in DARIJA)
        if hits >= 1 and hits / max(len(toks), 1) >= 0.06:
            return "darija"
        return "ar"
    fr = sum(1 for t in toks if t in FR)
    en = sum(1 for t in toks if t in EN)
    fr += sum(1 for ch in text if ch in "éèêàçùûôîï")  # accents are a strong French cue
    if fr == en == 0:
        return "unknown"
    return "fr" if fr >= en else "en"
