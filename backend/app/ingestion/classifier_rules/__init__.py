"""Rule families of the deterministic keyword classifier (audit L8).

``app.ingestion.classifier`` owns ``classify()`` and re-exports every name defined here,
so existing imports from the classifier keep working. Modules, in dependency order:

- ``matching``  keyword-match helpers and source defaults
- ``sport``     sport detection and sport-context disambiguation
- ``league``    legacy league display field (keywords + membership inference)
- ``entities``  taxonomy entity resolution and post-merge entity enrichment
- ``events``    event-type proposals routed through event_evidence validation
- ``scoring``   importance, confidence and tags
"""
