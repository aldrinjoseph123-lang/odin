"""The older plain-text report versions (before the rollout report, 30 Sep
2026): a line starting with "# " is a heading, "- " a list item, anything
else a paragraph. Saved versions are still shown through the rollout report.
"""


def render_blocks(body):
    """Plain text -> [(kind, text)] for the template: 'h', 'li', 'p'."""
    blocks = []
    for line in (body or "").splitlines():
        if line.startswith("# "):
            blocks.append(("h", line[2:].strip()))
        elif line.startswith("- "):
            blocks.append(("li", line[2:]))
        elif line.strip():
            blocks.append(("p", line))
    return blocks
