"""Deterministic answer templates (he/en). Numbers come only from tool facts."""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List


def _date(iso, lang):
    """Display date only (the time part garbles right-to-left text)."""
    y, m, d = str(iso)[:10].split("-")
    return "%s.%s.%s" % (d, m, y) if lang == "he" else "%s-%s-%s" % (y, m, d)


def usd(s: str) -> str:
    return "${:,.2f}".format(Decimal(s))


def _positions(val: Dict) -> str:
    return "; ".join("%s %s" % (p["asset"], usd(p["valueUsd"])) for p in val["positions"])


T = {
 "denied": {"en": "Access denied: this customer is not available in your scope.",
            "he": "הגישה נדחתה: הלקוח אינו זמין בהיקף ההרשאות שלך."},
 "refusal": {"en": "I can't give buy/sell recommendations or personal investment advice. "
                   "Please refer the client to a licensed investment adviser.",
             "he": "אני לא יכול לתת המלצות קנייה או מכירה או ייעוץ השקעות אישי. "
                   "יש להפנות את הלקוח ליועץ השקעות מורשה."},
 "missing_price": {"en": "Cannot value the portfolio: no price available for {assets}. No figures are shown.",
                   "he": "לא ניתן להעריך את התיק: חסר מחיר עבור {assets}. לא מוצגים נתונים."},
 "data_unavailable": {"en": "The required data is currently unavailable. No answer is given.",
                      "he": "הנתונים הנדרשים אינם זמינים כעת. לא ניתנת תשובה."},
 "no_source": {"en": "The required policy source was not found (or was quarantined as unsafe). No answer is given.",
               "he": "מקור המידע הנדרש לא נמצא (או הוצא מהשימוש כלא בטוח). לא ניתנת תשובה."},
 "unsupported": {"en": "I can answer questions about portfolio value, exposure versus policy, management fees "
                       "and the market review. I can't answer this from the available sources.",
                 "he": "אני יכול לענות על שאלות בנושא שווי התיק, חשיפה מול המדיניות, דמי ניהול וסקירת השוק. "
                       "אין לי מקור מתאים לשאלה זו."},
 "profile": {"en": "The exposure limit in the policy is defined for the medium risk profile only.",
             "he": "מגבלת החשיפה במדיניות מוגדרת רק לפרופיל סיכון בינוני."},
}


def msg(key: str, lang: str, **kw) -> str:
    return T[key][lang].format(**kw)


def value_text(val: Dict, lang: str) -> str:
    if lang == "he":
        return ("שווי התיק הדיגיטלי של {c} הוא {t} לפי מחירים לדוגמה ({p}). החזקות נכון ל-{a}; "
                "למחירים אין חותמת זמן, ולכן אין זה מידע בזמן אמת.").format(
            c=val["customerId"], t=usd(val["totalUsd"]), p=_positions(val), a=_date(val["holdingsAsOf"], "he"))
    return ("The digital portfolio of {c} is worth {t} at the sample prices ({p}). Holdings as of {a}; "
            "the prices carry no timestamp, so this is not live data.").format(
        c=val["customerId"], t=usd(val["totalUsd"]), p=_positions(val), a=_date(val["holdingsAsOf"], "en"))


def exposure_text(chk: Dict, lang: str) -> str:
    if lang == "he":
        rel = "מעל" if chk["breach"] else "מתחת ל"
        return ("{a} היא הפוזיציה הגדולה ביותר שאינה מטבע יציב: {p}% מהתיק, {r}מגבלת {l}% לנכס בודד "
                "בפרופיל סיכון בינוני. {x}").format(
            a=chk["asset"], p=chk["exposurePct"], r=rel + (" " if chk["breach"] else ""), l=chk["limitPct"],
            x="יש חריגה." if chk["breach"] else "אין חריגה.")
    return ("{a} is the largest non-stablecoin position at {p}% of the portfolio, {r} the {l}% single-asset "
            "limit for the medium risk profile. {x}").format(
        a=chk["asset"], p=chk["exposurePct"], r="above" if chk["breach"] else "below", l=chk["limitPct"],
        x="This is a breach." if chk["breach"] else "No breach.")


def fee_text(fee: Dict, total: str, lang: str) -> str:
    if lang == "he":
        return ("אומדן דמי הניהול לרבעון הקרוב: {f} (0.8% בשנה / 4 על שווי התמונה הנוכחית {t}). זהו אומדן בלבד "
                "בהנחת שווי קבוע; שיטת החיוב בפועל לא צוינה, ואין זו חשבונית עתידית מובטחת.").format(
            f=usd(fee["estimateUsd"]), t=usd(total))
    return ("Estimated quarterly management fee: {f} (0.8% per year / 4 on the current snapshot value {t}). "
            "This is an estimate assuming constant value; the actual billing convention is unspecified and "
            "it is not a guaranteed future bill.").format(f=usd(fee["estimateUsd"]), t=usd(total))


def market_text(quotes: List[str], lang: str) -> str:
    head = "קטע מסקירת השוק:" if lang == "he" else "Market review excerpt (as written in the source, not a forecast or recommendation):"
    return head + " " + " ".join("«%s»" % q for q in quotes)
