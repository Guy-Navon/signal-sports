"""Story-identifying named anchors (#136).

THE MISSING SEMANTIC PRIMITIVE. The v1 matcher has no way to say "these two articles are about
the same named subject", and the rarity model it uses instead is exactly backwards:

    מדר   — the token that NAMES the story's subject — df=13 → NOT discriminative
    יאללה — an interjection ("yalla")               — df=2  → discriminative
    דולר  — "dollar"                                 — df=5  → discriminative
    פרק   — "chapter"                                — df=3  → discriminative

An anchor is a NAMED MENTION: a person or club that a story can be *about*. It is not a rare
token, and rarity is not evidence of it.

    Rare is not the same as story-identifying.
    Names are a strong identity signal — but shared identity without shared event semantics
    must NOT merge. A player appears in his farewell, his signing, his shirt number and his
    next fixture. A shared anchor is NECESSARY, never SUFFICIENT.

DELIBERATELY NOT A TAXONOMY. An anchor exists to match stories inside a candidate window; it
does not need to be globally canonical, and it must NOT require taxonomy resolution to exist —
the taxonomy resolves **zero** Israeli players (3/257 corpus articles carry any player entity:
LeBron and Deni). Registering the four names by hand would fit this corpus and fail the next.
When the taxonomy *does* know the entity we reuse its id; otherwise we carry the surface form.

Since #141/#126 this module is LIVE: `generate_candidates` feeds the ingestion-time
enrichment stage, whose validated output `match_pair` reads as tier-N subject evidence
(docs/CLUSTERING.md §7.7). The legacy `generate_anchor_candidates`/`shared_anchors`
surface remains diagnostic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from app.clustering.anchor_contract import AnchorCandidate
from app.clustering.anchor_normalization import transliteration_skeleton as _skeleton
from app.clustering.tokens import is_generic, normalize

# ── The vocabulary a name is NOT ─────────────────────────────────────────────
# A name is defined by POSITIVE evidence (see `extract_anchors`), but a token drawn from the
# domain's action vocabulary can never be one. These are the words that fooled the rarity
# model — every one of them is "rare" and identifies nothing.
_ACTION_VERBS = frozenset("""
חתם חתמה חתמו סיכם סיכמה סיכמו האריך האריכה הצטרף הצטרפה עוזב עוזבת עזב עזבה
נפרד נפרדה נפרדו מתרחק מתרחקת ישחק תשחק שיחק ששיחק שיחקה יגיע תגיע הגיע הגיעה
פוצץ פוצצו הציגה הציג הכריז הודיע דיווח נחשף פורסם צפוי צפויה יחתום תחתום
מנהל מנהלים סגר סגרה סגרו קיבל קיבלה ניצח ניצחה הפסיד הפסידה פותח פותחת לפתוח
מאיים מאיימים בוחן שיבחן לקח מתחזקת ירדו נעדר נבחר זכה זכתה
""".split())

_CONTRACT_MONEY = frozenset("""
חוזה חוזהו שכר שכרו שנים שנתיים לשנתיים לשלוש לשנה נוספות נוספת עונה עונות
מיליון מיליוני אלף דולר יורו שקל שקלים סעיף יציאה תנאיו הארכת מו מגעים
בשיחות שיחות במו הצעה מועמד מועמדים
""".split())

_NUMBER_WORDS = frozenset("""
אחד אחת שני שתי שניים שלוש שלושה ארבע ארבעה חמש חמישה שש שישה שבע שבעה
שמונה תשע עשר עשרה ראשון ראשונה שנייה שלישי
""".split())

# Everything above, plus the shared generic list, plus prefixed forms.
_NON_NAME_VOCAB = _ACTION_VERBS | _CONTRACT_MONEY | _NUMBER_WORDS

_HEB_PREFIXES = "בהלמכשו"


def _known_competition_tokens() -> frozenset[str]:
    """Competition vocabulary, from the taxonomy — not a hand-written list.

    A competition is a KNOWN ENTITY KIND, and it is never what a story is about: every
    EuroLeague story shares "יורוליג", exactly as every Maccabi story shares the team. Letting
    a competition act as a person-anchor merged Bryant's extension with Otooru's.
    """
    out: set[str] = set()
    try:
        from app.classification.facts import _COMPETITION_KEYWORDS
        for kws in _COMPETITION_KEYWORDS.values():
            for kw in kws:
                for w in str(kw).split():
                    if len(w) > 2:
                        out.add(w)
    except Exception:
        pass
    return frozenset(out)


_COMPETITIONS = _known_competition_tokens()


def _is_vocabulary(token: str) -> bool:
    """True when a token is known domain vocabulary and therefore CANNOT be a name."""
    if is_generic(token):
        return True
    if token in _NON_NAME_VOCAB:
        return True
    if token in _COMPETITIONS:
        return True
    # A single attached prefix letter never turns a verb into a name: "בשיחות" -> "שיחות".
    if len(token) > 2 and token[0] in _HEB_PREFIXES and token[1:] in _NON_NAME_VOCAB:
        return True
    return False


# ── Role markers ─────────────────────────────────────────────────────────────
# Where determinable. A role-holder or an opponent is NOT what a story is ABOUT.
_ROLE_TITLES = frozenset("""
מאמן מאמנת המאמן הרכש הבעלים בעלים נשיא המנהל מנהל סוכן הסוכן קפטן שופט השופט
""".split())
# "הקבוצה של איטודיס" — a possessive marks the coach as a ROLE-HOLDER of the club, not the
# subject of the story. This is the exact construction that bridged three unrelated articles.
_POSSESSIVE = frozenset({"של"})
_OPPONENT_MARKERS = frozenset({"מול", "נגד", "יריבה", "יריבת"})
_WORD = re.compile("[֐-׿׳״'\"-]+")


@dataclass(frozen=True)
class Anchor:
    """One named mention. The contract #137 will normalize and #124 will evaluate.

    Stable by design: #137 adds `normalized` variants (transliteration) WITHOUT changing this
    shape, and taxonomy growth only ever fills in `entity_id` — never invalidates an anchor.
    """

    raw: str                      # the mention exactly as it appeared
    normalized: str               # normalized surface form (#137 will fold spelling variants)
    anchor_type: str              # "person" | "club" | "unknown" — only when confidently known
    entity_id: Optional[str]      # canonical taxonomy id, when available. None is NORMAL.
    source: str                   # "title" | "subtitle" — WHERE the evidence lives
    confidence: str               # "canonical" | "strong" | "weak"
    evidence: str                 # WHY this is an anchor — must be explainable in a trace
    role: str                     # "subject"|"opponent"|"quoted"|"role_holder"|"incidental"|"unknown"

    def key(self) -> str:
        """Identity for matching. Canonical id wins; otherwise the normalized surface."""
        return self.entity_id or f"name:{self.normalized}"

    def keys(self) -> frozenset[str]:
        """All forms this anchor may match on.

        Hebrew glues prepositions onto names — sport5 writes "נפרדה מהנקינס" where ynet writes
        "מזאק הנקינס". So a prefix-stripped form is an ADDITIONAL key, never a REPLACEMENT.

        That distinction is not cosmetic. Stripping in place corrupts real names whose first
        letter merely happens to be a prefix letter: הנקינס→נקינס, מכבי→כבי, ברצלונה→רצלונה,
        כריס→ריס. A spurious stripped form is harmless as an EXTRA key (it can only ever match
        an identically-spurious form); as a replacement it destroys the name.
        """
        if self.entity_id:
            return frozenset({self.entity_id})
        out = {f"name:{self.normalized}"}
        for part in self.normalized.split():
            out.add(f"name:{part}")
            if len(part) > 3 and part[0] in _HEB_PREFIXES:
                out.add(f"name:{part[1:]}")
        return frozenset(out)

    def is_story_identifying(self) -> bool:
        """A role-holder or an opponent is not what the story is ABOUT.

        This is what kills `adv_coach_as_bridge`: Itoudis appears in three unrelated Hapoel
        articles as the club's COACH ("הקבוצה של איטודיס"), never as the subject.
        """
        return self.role in ("subject", "quoted", "unknown")


def _tokens_with_positions(text: str) -> list[str]:
    return [w for w in _WORD.findall(normalize(text)) if len(w) > 1]


def _candidate_forms(token: str) -> tuple[str, ...]:
    """The token, PLUS its prefix-stripped form — never instead of it.

    Hebrew glues prepositions onto names ("נפרדה מזאק"), so the stripped form must be
    reachable. But stripping in place is destructive: the first letter of הנקינס, מכבי,
    ברצלונה and כריס is *also* a prefix letter. Both forms, always.
    """
    if len(token) > 3 and token[0] in _HEB_PREFIXES:
        return (token, token[1:])
    return (token,)


def _is_vocabulary_any_form(token: str) -> bool:
    """Vocabulary if ANY candidate form is vocabulary — 'בשיחות' is 'שיחות'."""
    return any(_is_vocabulary(f) for f in _candidate_forms(token))


def _resolve(text: str):
    """Taxonomy resolution. Returns canonical entities — usually EMPTY for these articles."""
    try:
        from app.taxonomy.resolver import resolve_entities
        return resolve_entities(text).resolved
    except Exception:
        return []


def build_name_lexicon(articles) -> frozenset[str]:
    """Name forms corroborated by BIGRAM evidence anywhere in the candidate population.

    THE PROBLEM THIS SOLVES. sport5 writes "מכבי ת\"א נפרדה מהנקינס" — Hankins appears as a
    LONE token with no bigram partner, so the article yields NO anchor at all and the hardest
    Hankins card can never join. Within-article corroboration cannot fix that; the name simply
    is not introduced there.

    THE FIX, and note it mirrors #135 exactly: corroborate against the CANDIDATE POPULATION.
    ynet introduces him properly ("נפרדה מזאק הנקינס"), so the window knows "הנקינס" is a name.
    sport5's bare mention is then recognisable. Names are established by the same population
    that establishes evidence frequency — one idea, applied twice.

    This is NOT a global lexicon and NOT a taxonomy. It lives and dies with the window.
    """
    lex: set[str] = set()
    for a in articles:
        for text in (getattr(a, "title", "") or "", getattr(a, "subtitle", "") or ""):
            words = _tokens_with_positions(text)
            for i in range(len(words) - 1):
                w1, w2 = words[i], words[i + 1]
                if _is_vocabulary_any_form(w1) or _is_vocabulary_any_form(w2):
                    continue
                if len(w1) < 2 or len(w2) < 2:
                    continue
                for w in (w1, w2):
                    for f in _candidate_forms(w):
                        lex.add(f)
                    # #137 at the GENERATION stage: the population also establishes a
                    # name's transliteration SKELETON, so a variant spelling of an
                    # established name ("סטרונסקי" when the window knows "סטורנסקי")
                    # is recognisable as a corroborated lone mention. Namespaced so a
                    # skeleton can only ever match a skeleton lookup — never a raw
                    # surface form. The candidate still faces full validation.
                    lex.add(f"translit:{_skeleton(w)}")
    return frozenset(lex)


def generate_candidates(
    title: str,
    subtitle: str = "",
    lexicon: frozenset[str] | None = None,
    article_id: str = "",
    candidate_set_id: str = "",
) -> tuple[AnchorCandidate, ...]:
    """HIGH-RECALL generation, emitting the FULL structured record (#141 interface correction).

    Every candidate carries the grammatical context that was true where it was found — token
    offsets, left/right context, the positional pattern, the inferred role, and the exact rule
    that produced it. The validator must never have to reconstruct that from a bare string.

    Position is destroyed by isolation: hand a validator "איטודיס" and the fact that it sat in
    "הקבוצה של איטודיס" — a possessive marking a ROLE-HOLDER — is simply gone.
    """
    out: list[AnchorCandidate] = []
    seen: set[tuple[str, str, int]] = set()
    ctx = 3

    for text, src in ((title, "title"), (subtitle, "subtitle")):
        if not text:
            continue
        words = _tokens_with_positions(text)

        for ent in _resolve(text):
            kind = getattr(ent, "kind", "unknown")
            out.append(AnchorCandidate(
                raw=getattr(ent, "display_he", ent.id), normalized=ent.id,
                source=src, token_start=-1, token_end=-1,
                left_context=(), right_context=(),
                pattern="taxonomy_match",
                role="role_holder" if kind == "coach" else "unknown",
                entity_id=ent.id, taxonomy_kind=kind, population_corroborated=False,
                generation_rule="canonical_taxonomy", confidence="canonical",
                article_id=article_id, candidate_set_id=candidate_set_id,
                anchor_type="person" if kind in ("player", "coach") else "club",
            ))

        bigram_names: set[str] = set()
        for i in range(len(words) - 1):
            w1, w2 = words[i], words[i + 1]
            if _is_vocabulary_any_form(w1) or _is_vocabulary_any_form(w2):
                continue
            if len(w1) < 2 or len(w2) < 2:
                continue
            bigram_names.add(w1)
            bigram_names.add(w2)
            key = (f"{w1} {w2}", src, i)
            if key in seen:
                continue
            seen.add(key)
            out.append(AnchorCandidate(
                raw=f"{w1} {w2}", normalized=f"{w1} {w2}", source=src,
                token_start=i, token_end=i + 2,
                left_context=tuple(words[max(0, i - ctx):i]),
                right_context=tuple(words[i + 2:i + 2 + ctx]),
                pattern="two_adjacent_non_vocabulary_tokens",
                role=_infer_role(words, i, text),
                entity_id=None, taxonomy_kind=None, population_corroborated=False,
                generation_rule="name_bigram", confidence="strong",
                article_id=article_id, candidate_set_id=candidate_set_id,
                anchor_type="person",
            ))

        corroborated = set(bigram_names) | set(lexicon or ())
        for i, w in enumerate(words):
            if _is_vocabulary_any_form(w):
                continue
            surface_hit = any(f in corroborated for f in _candidate_forms(w))
            skeleton_hit = (
                f"translit:{_skeleton(w)}" in corroborated
            )
            if not (surface_hit or skeleton_hit):
                continue
            key = (w, src, i)
            if key in seen:
                continue
            seen.add(key)
            out.append(AnchorCandidate(
                raw=w, normalized=w, source=src, token_start=i, token_end=i + 1,
                left_context=tuple(words[max(0, i - ctx):i]),
                right_context=tuple(words[i + 1:i + 1 + ctx]),
                pattern="lone_mention_known_to_population",
                role=_infer_role(words, i, text),
                entity_id=None, taxonomy_kind=None,
                population_corroborated=bool(lexicon and any(
                    f in lexicon for f in _candidate_forms(w))),
                generation_rule="corroborated_single", confidence="weak",
                article_id=article_id, candidate_set_id=candidate_set_id,
                anchor_type="person",
            ))
    return tuple(out)


def generate_anchor_candidates(
    title: str, subtitle: str = "", lexicon: frozenset[str] | None = None
) -> tuple[Anchor, ...]:
    """Extract named anchors from an article, with layered evidence.

    Layer 1 — CANONICAL. The taxonomy resolved it. Highest confidence, and it carries a
              `kind`, so a coach becomes `role_holder` for free.
    Layer 2 — NAME BIGRAM. Two adjacent tokens, NEITHER of which is domain vocabulary.
              Every real name in the corpus forms one: 'ים מדר', 'זאק הנקינס', 'דן אוטורו',
              'תומאש סטורנסקי', 'טימוקו דיארה', 'אלייז'ה בראיינט'. None of the fooling tokens
              do — 'מיליון דולר' pairs with a NUMBER, 'פותח פרק' with a VERB, 'חוזה לשלוש'
              with CONTRACT vocabulary.
    Layer 3 — CORROBORATED SINGLE MENTION. A lone token the CANDIDATE POPULATION established
              as a name (see `build_name_lexicon`). This is what lets sport5's bare
              "נפרדה מהנקינס" join — ynet introduced him properly, so the window knows the
              name. Weak confidence; never promoted on its own.
    """
    anchors: list[Anchor] = []
    seen: set[tuple[str, str]] = set()

    for text, src in ((title, "title"), (subtitle, "subtitle")):
        if not text:
            continue

        # ── Layer 1: canonical ────────────────────────────────────────────────
        for ent in _resolve(text):
            kind = getattr(ent, "kind", "unknown")
            role = "role_holder" if kind == "coach" else "unknown"
            a = Anchor(
                raw=getattr(ent, "display_he", ent.id), normalized=ent.id,
                anchor_type="person" if kind in ("player", "coach") else "club",
                entity_id=ent.id, source=src, confidence="canonical",
                evidence=f"taxonomy:{kind}", role=role,
            )
            if (a.key(), src) not in seen:
                seen.add((a.key(), src))
                anchors.append(a)

        words = _tokens_with_positions(text)
        bigram_names: set[str] = set()

        # ── Layer 2: name bigrams ─────────────────────────────────────────────
        for i in range(len(words) - 1):
            w1, w2 = words[i], words[i + 1]
            if _is_vocabulary_any_form(w1) or _is_vocabulary_any_form(w2):
                continue
            if len(w1) < 2 or len(w2) < 2:
                continue

            role = _infer_role(words, i, text)
            # Surface forms are preserved VERBATIM. Prefix variants are added by Anchor.keys().
            bigram_names.add(w1)
            bigram_names.add(w2)
            a = Anchor(
                raw=f"{w1} {w2}", normalized=f"{w1} {w2}", anchor_type="person",
                entity_id=None, source=src, confidence="strong",
                evidence="name_bigram: two adjacent non-vocabulary tokens", role=role,
            )
            if (a.key(), src) not in seen:
                seen.add((a.key(), src))
                anchors.append(a)

        # ── Layer 3: corroborated single mentions ─────────────────────────────
        corroborated = set(bigram_names)
        if lexicon:
            corroborated |= set(lexicon)
        for idx, w in enumerate(words):
            if _is_vocabulary_any_form(w):
                continue
            if any(f in corroborated for f in _candidate_forms(w)):
                # Role inference applies HERE TOO. Skipping it was a real defect: "הקבוצה של
                # איטודיס" never forms a bigram (של is vocabulary), so the coach arrived via
                # Layer 3 with role="unknown" and counted as story-identifying — which is
                # precisely how he bridged three unrelated Hapoel articles.
                a = Anchor(
                    raw=w, normalized=w, anchor_type="person", entity_id=None, source=src,
                    confidence="weak",
                    evidence="corroborated_single: the candidate population knows this name",
                    role=_infer_role(words, idx, text),
                )
                if (a.key(), src) not in seen:
                    seen.add((a.key(), src))
                    anchors.append(a)

    return tuple(anchors)


def _infer_role(words: list[str], i: int, text: str) -> str:
    """Role of the mention at position i, WHERE DETERMINABLE. Defaults to 'unknown'.

    We never guess a confident role. 'unknown' still counts as story-identifying; only a
    POSITIVELY identified role-holder or opponent is excluded.
    """
    prev = words[i - 1] if i > 0 else ""
    prev2 = words[i - 2] if i > 1 else ""

    # "הקבוצה של איטודיס" — possessive: the coach OWNS the club, he is not the story.
    if prev in _POSSESSIVE:
        return "role_holder"
    # "המאמן דימיטריס איטודיס" — an explicit role title.
    if prev in _ROLE_TITLES or prev2 in _ROLE_TITLES:
        return "role_holder"
    # "מול X" / "נגד X" — the opponent is not the subject.
    if prev in _OPPONENT_MARKERS:
        return "opponent"
    return "unknown"


# ── THE VALIDATION BOUNDARY ──────────────────────────────────────────────────
# A CANDIDATE SPAN IS NOT AN ANCHOR.
#
# `generate_anchor_candidates` deliberately favours RECALL: it will happily propose
# "נשאר אדום" ("stayed red"), because the bigram rule's premise — "two adjacent
# non-vocabulary tokens is a name" — holds only to the extent that the vocabulary is COMPLETE,
# and Hebrew is not a closed vocabulary. Ordinary verbs, nouns and adjectives satisfy it.
#
# So a candidate may NEVER become clustering evidence on its own. It must first be VALIDATED as
# name-like by a resource that actually knows Hebrew. That validator does not exist yet
# (tracked separately); until it does, this stage ABSTAINS on everything it cannot prove.
#
# Abstention beats incorrect clustering. Passing candidates straight through would make the
# frozen corpus go green while leaving the abstraction broken — the fixture would pass and the
# product would not.

VALIDATION_ABSTAINED = "no_validator: only canonical taxonomy anchors are proven name-like"


def validate_anchors(candidates: tuple[Anchor, ...]) -> tuple[Anchor, ...]:
    """The precision half. May ABSTAIN, and currently abstains on almost everything.

    Today the ONLY thing that proves a span is name-like is a canonical taxonomy match. Every
    heuristic candidate — bigram or corroborated single — is UNVALIDATED and must not reach
    merge evidence, no matter how confident the generator felt.

    This is why `אדום` (red), `שיא` (record) and `הכל` (everything) cannot over-merge any more:
    not because they were added to a stoplist (that would fit this corpus and fail the next),
    but because NOTHING heuristic is trusted until a real validator says so.
    """
    return tuple(c for c in candidates if c.confidence == "canonical")


def shared_anchors(a: tuple[Anchor, ...], b: tuple[Anchor, ...]) -> tuple[str, ...]:
    """Story-identifying anchors shared by two articles — VALIDATED ANCHORS ONLY.

    Role-holders and opponents are excluded — a coach shared by two articles about DIFFERENT
    players is not evidence they are the same story.
    """
    a = validate_anchors(a)
    b = validate_anchors(b)
    ka: set[str] = set()
    for x in a:
        if x.is_story_identifying():
            ka |= x.keys()
    kb: set[str] = set()
    for y in b:
        if y.is_story_identifying():
            kb |= y.keys()
    return tuple(sorted(ka & kb))


def shared_anchor_candidates(
    a: tuple[Anchor, ...], b: tuple[Anchor, ...]
) -> tuple[str, ...]:
    """UNVALIDATED overlap. DIAGNOSTICS ONLY — never merge evidence.

    Exists so #124 can measure what a validator would have to work with, and so the Hebrew
    anchor-validation issue has a recall ceiling to aim at. Calling this from the matcher
    would defeat the entire validation boundary.
    """
    ka: set[str] = set()
    for x in a:
        if x.is_story_identifying():
            ka |= x.keys()
    kb: set[str] = set()
    for y in b:
        if y.is_story_identifying():
            kb |= y.keys()
    return tuple(sorted(ka & kb))
