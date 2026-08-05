"""Coder agent: turns one accepted strategist proposal into an actual code
change, written to submissions/candidate/main.py for A/B testing.
"""
from __future__ import annotations

import re
from pathlib import Path

from agents.llm_client import call
from agents.strategist import Proposal

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPT_TEMPLATE = (REPO_ROOT / "prompts" / "coder.md").read_text()
BASELINE_PATH = REPO_ROOT / "submissions" / "baseline" / "main.py"
CANDIDATE_PATH = REPO_ROOT / "submissions" / "candidate" / "main.py"

CODE_BLOCK_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def extract_code(response: str) -> str:
    match = CODE_BLOCK_RE.search(response)
    if not match:
        raise ValueError("coder response did not contain a python code block")
    return match.group(1).rstrip() + "\n"


def run_coder(proposal: Proposal, baseline_src: str | None = None) -> str:
    baseline_src = baseline_src if baseline_src is not None else BASELINE_PATH.read_text()
    prompt = PROMPT_TEMPLATE.replace("{{ proposal_md }}", proposal.body).replace(
        "{{ baseline_src }}", baseline_src
    )
    response = call(prompt, role="coder")
    code = extract_code(response)
    CANDIDATE_PATH.write_text(code)
    return code


if __name__ == "__main__":
    from agents.strategist import run_strategist

    proposals = run_strategist()
    if not proposals:
        raise SystemExit("no proposals to implement")
    print(run_coder(proposals[0]))
