"""Strategist agent: reads the analyst's report and current baseline source,
and produces one or more improvement proposals as structured design docs
(root cause -> change target -> logic -> acceptance criteria -> forbidden
changes) -- *before* any code gets written. This is the "design review"
step that catches "looks better but is actually worse" ideas early.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from agents.llm_client import call

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPT_TEMPLATE = (REPO_ROOT / "prompts" / "strategist.md").read_text()
ANALYSIS_PATH = REPO_ROOT / "reports" / "latest_analysis.md"
BASELINE_PATH = REPO_ROOT / "submissions" / "baseline" / "main.py"

PROPOSAL_HEADER_RE = re.compile(r"^##\s*改善案[:：]", re.MULTILINE)


@dataclass
class Proposal:
    title: str
    body: str  # full "## 改善案: ..." section, passed on to the coder agent as-is


def run_strategist(analysis_md: str | None = None, baseline_src: str | None = None) -> list[Proposal]:
    analysis_md = analysis_md if analysis_md is not None else ANALYSIS_PATH.read_text()
    baseline_src = baseline_src if baseline_src is not None else BASELINE_PATH.read_text()

    prompt = PROMPT_TEMPLATE.replace("{{ analysis_md }}", analysis_md).replace(
        "{{ baseline_src }}", baseline_src
    )
    response = call(prompt, role="strategist")
    return parse_proposals(response)


def parse_proposals(response: str) -> list[Proposal]:
    starts = [m.start() for m in PROPOSAL_HEADER_RE.finditer(response)]
    if not starts:
        return [Proposal(title="(untitled)", body=response.strip())] if response.strip() else []

    sections = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(response)
        section = response[start:end].strip()
        title_line = section.splitlines()[0]
        title = title_line.split(":", 1)[-1].split("：", 1)[-1].strip()
        sections.append(Proposal(title=title, body=section))
    return sections


if __name__ == "__main__":
    for proposal in run_strategist():
        print(f"=== {proposal.title} ===")
        print(proposal.body)
        print()
