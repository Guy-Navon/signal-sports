"""Profile-independent evidence of a current, consequential development.

This does not assign importance or a feed tier. It describes the event so an
explicit push rule can distinguish completion/imminent agreement from ordinary
negotiations, rejected destinations and retrospective interviews.
"""
import re

from app.taxonomy.entities import ENTITIES


_CONCRETE_STEP = (
    r"(?<![א-ת])(?:הגיש|הגישה|הגישו|סוכם|סוכמה|סיכמו|סיכם|סיכמה|הוכרע|הכריע|הכריעה|"
    r"החליט|החליטה|החליטו|אושר|אושרה|אישר|אישרה|אישרו|נחתם|נחתמה|נמכר|נמכרה|"
    r"נרכש|נרכשה|רכש|רכשה|רכשו|השלים|השלימה|השלימו)(?![א-ת])"
    r"|\b(?:filed|agreed|approved|sold|bought|completed)\b"
)


def _with_linked_people(subjects: list, entity_ids: list, title: str) -> list:
    """Add a team as a subject when a coach/executive linked to it is named in the title."""
    out = list(subjects)
    for person in ENTITIES.values():
        if person.kind not in ("coach", "executive") or person.team_id not in entity_ids:
            continue
        if person.team_id not in out and any(a.lower() in title for a in person.aliases):
            out.append(person.team_id)
    return out


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
    elif event_type == "club_governance":
        # #229: push only on a concrete step taken (filed, agreed, decided, approved,
        # sold, bought) — not on statements, reactions or previews of a decision.
        if re.search(_CONCRETE_STEP, title):
            development = "concrete_step"
        # The story's subject may be named through a person linked to the club
        # ("דיץ הגיש בקשה … במכבי"): the club alias itself is often only the bare
        # family name, which never resolves.
        subjects = _with_linked_people(subjects, entity_ids, title)
    elif event_type == "injury":
        if any(word in title for word in ("נפצע", "קרע", "ייעדר", "injured", "out for")):
            development = "current_injury"
    else:
        # This policy narrows the noisy transfer/injury rules only. Other
        # event types still face their own semantic and override contracts.
        return {"development": "other_event", "subject_entity_ids": subjects}
    return {"development": development, "subject_entity_ids": subjects}
