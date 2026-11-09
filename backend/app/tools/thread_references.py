"""Parse an explicit public identifier, not natural-language topic matching."""

import re

REFERENCE = re.compile(r"(?<![\w/-])V-([0-9]+)(?![\w-])", re.IGNORECASE)


class ThreadReferenceError(ValueError):
    pass


def reference_ids(message: str) -> list[int]:
    result = []
    for match in REFERENCE.finditer(message):
        digits = match[1]
        if len(digits) > 19 or not 0 < int(digits) <= 9223372036854775807:
            raise ThreadReferenceError("Ungültige Vorhaben-Kennung. Verwende zum Beispiel V-42.")
        tid = int(digits)
        if tid not in result:
            result.append(tid)
    if len(result) > 10:
        raise ThreadReferenceError("Bitte höchstens zehn Vorhaben je Nachricht referenzieren.")
    return result
