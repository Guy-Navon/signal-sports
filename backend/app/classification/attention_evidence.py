"""Profile-independent evidence of a current, consequential development.

This does not assign importance or a feed tier. It describes the event so an
explicit push rule can distinguish completion/imminent agreement from ordinary
negotiations, rejected destinations and retrospective interviews.
"""
import re

from app.taxonomy.entities import ENTITIES


def attention_evidence(title: str, subtitle: str, event_type: str, entity_ids: list[str]) -> dict:
    title, subtitle = title.lower(), (subtitle or "").lower()
    # A transaction involving an ex-club or rejected destination is not a new
    # development FOR that club. Keep the fact and its normal feed eligibility.
    retrospective = any(marker in title for marker in (
        "האמינו שיגיע", "פוספס", "דחה את", "התקדם מ", "יכולתי", "אם לא הפציעה",
        "would have", "used to", "rejected", "missed out",
    ))
    subjects = []
    for eid in entity_ids:
        entity = ENTITIES.get(eid)
        if entity is None:
            continue
        if any(alias.lower() in title for alias in entity.aliases):
            subjects.append(eid)
    if retrospective:
        return {"development": "retrospective_or_rejected", "subject_entity_ids": []}

    development = "routine_or_uncertain"
    if event_type in {"signing", "negotiation", "major_signing"}:
        if re.search(r"(?<![א-ת])(?:חתם|חתמה|חתמו|סיכם|סיכמה|סיכמו|הציגה|הציג)(?![א-ת])", title) or re.search(r"\b(signed|agreed|announced)\b", title):
            development = "agreement_or_completion"
        elif "פרטים קטנים" in subtitle and "הארכת חוזה" in subtitle:
            development = "imminent_renewal"
    elif event_type == "injury":
        if any(word in title for word in ("נפצע", "קרע", "ייעדר", "injured", "out for")):
            development = "current_injury"
    else:
        # This policy narrows the noisy transfer/injury rules only. Other
        # event types still face their own semantic and override contracts.
        return {"development": "other_event", "subject_entity_ids": subjects}
    return {"development": development, "subject_entity_ids": subjects}
