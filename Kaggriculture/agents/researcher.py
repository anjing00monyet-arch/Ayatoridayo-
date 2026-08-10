"""Researcher agent: consolidates manually-collected notes from public
Notebooks/Discussion/past solutions (dropped as markdown files into
docs/research/) into a single summary the strategist can draw on.

This step is intentionally human-in-the-loop for note collection -- there is
no scraper here. Paste findings from Kaggle Notebooks/Discussion into
docs/research/*.md yourself, then run this to consolidate them.
"""
from __future__ import annotations

from pathlib import Path

from agents.llm_client import call

REPO_ROOT = Path(__file__).resolve().parent.parent
RESEARCH_DIR = REPO_ROOT / "docs" / "research"
PROMPT_TEMPLATE = (REPO_ROOT / "prompts" / "researcher.md").read_text()
OUTPUT_PATH = REPO_ROOT / "reports" / "research_summary.md"


def collect_notes() -> str:
    notes = sorted(RESEARCH_DIR.glob("*.md"))
    if not notes:
        return "(docs/research/ にメモがまだありません)"
    return "\n\n---\n\n".join(f"### {p.name}\n\n{p.read_text()}" for p in notes)


def run_researcher() -> str:
    notes = collect_notes()
    prompt = PROMPT_TEMPLATE.replace("{{ notes }}", notes)
    summary = call(prompt, role="researcher")
    OUTPUT_PATH.write_text(summary)
    return summary


if __name__ == "__main__":
    print(run_researcher())
