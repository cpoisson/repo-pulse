"""Issue triage: type (bug/enhancement/question) and theme (config taxonomy).

Every candidate implements `Classifier.predict_proba(texts) -> {"type": [[p...]], "theme": [[p...]]}`
(rows aligned with cfg.issue_types / cfg.themes order). Selection happens in bakeoff.py, on data.
"""
from __future__ import annotations

import re


def issue_text(item: dict, body_chars: int = 600) -> str:
    body = re.sub(r"<!--.*?-->", " ", item.get("body") or "", flags=re.S)
    body = re.sub(r"```.*?```", " [code] ", body, flags=re.S)
    body = re.sub(r"\s+", " ", body).strip()
    return f"{item['title'].strip()}. {body[:body_chars]}"
