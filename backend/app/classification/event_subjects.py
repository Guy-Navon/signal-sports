"""Conservative title evidence for the participants in a relocation report.

Entity presence is broader than participation: 'the team of X' identifies a
franchise through X, without asserting that X is moving. These facts are
profile-independent and never add entities the resolver did not establish.
"""

import re

from app.taxonomy.entities import ENTITIES


def relocation_subject_ids(title: str, entity_ids: list[str]) -> list[str]:
    subjects = []
    for eid in entity_ids:
        entity = ENTITIES.get(eid)
        if entity is None or entity.kind != "player":
            continue
        # Full names only: an ambiguous short mention is not enough for an
        # interruption. Longest first also avoids treating a surname as a
        # second occurrence outside the preceding possessive.
        aliases = sorted((a for a in entity.aliases if " " in a), key=len, reverse=True)
        for alias in aliases:
            for match in re.finditer(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", title, re.I):
                prefix = title[:match.start()].rstrip()
                if re.search(r"(?:\bשל|\bof)\s*$", prefix, re.I):
                    continue
                subjects.append(eid)
                break
            if eid in subjects:
                break
    return subjects
