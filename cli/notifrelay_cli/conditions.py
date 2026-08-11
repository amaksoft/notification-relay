"""
Convenience Condition-tree builder for the common case (package +
optional channel/title/text), so most CLI users never need to hand-write
JSON. See docs/RULE_SCHEMA.md for the full schema; `device rule add-json`
is the escape hatch for anything this can't express (arbitrary OR/NOT
nesting, multiple packages, etc).
"""


def build_simple_condition(
    package: str | None = None,
    channel: str | None = None,
    title_contains: str | None = None,
    text_contains: str | None = None,
) -> dict:
    leaves = []
    if package:
        leaves.append({"type": "NOTIFICATION_PACKAGE_NAME", "stringValue": package})
    if channel:
        leaves.append({"type": "NOTIFICATION_CHANNEL_ID", "stringValue": channel})
    if title_contains:
        leaves.append({"type": "NOTIFICATION_TITLE", "stringValue": title_contains})
    if text_contains:
        leaves.append({"type": "NOTIFICATION_TEXT", "stringValue": text_contains})

    if not leaves:
        raise SystemExit("At least one of --package/--channel/--title-contains/--text-contains is required.")
    if len(leaves) == 1:
        return leaves[0]
    return {"type": "AND", "conditions": leaves}
