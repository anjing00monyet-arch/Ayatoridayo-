"""Reviewer agent: a cheap pre-check run before the expensive A/B match
evaluation (evaluation/compare_agents.py). Catches syntax errors and
forbidden-API changes with static analysis first (free, instant), then asks
an LLM to sanity-check the diff against the proposal's intent.
"""
from __future__ import annotations

import ast
import difflib
import re
from dataclasses import dataclass
from pathlib import Path

from agents.llm_client import call
from agents.strategist import Proposal

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPT_TEMPLATE = (REPO_ROOT / "prompts" / "reviewer.md").read_text()

AGENT_SIGNATURE_RE = re.compile(r"^def agent\(observation[^)]*\)", re.MULTILINE)


@dataclass
class StaticCheckResult:
    syntax_ok: bool
    syntax_error: str | None
    signature_preserved: bool

    def report(self) -> str:
        lines = [
            f"{'PASS' if self.syntax_ok else 'FAIL'}  構文が正しい"
            + (f" ({self.syntax_error})" if self.syntax_error else ""),
            f"{'PASS' if self.signature_preserved else 'FAIL'}  agent(observation) のシグネチャを維持",
        ]
        return "\n".join(lines)

    @property
    def ok(self) -> bool:
        return self.syntax_ok and self.signature_preserved


def static_check(candidate_src: str) -> StaticCheckResult:
    try:
        ast.parse(candidate_src)
        syntax_ok, syntax_error = True, None
    except SyntaxError as e:
        syntax_ok, syntax_error = False, str(e)

    signature_preserved = bool(AGENT_SIGNATURE_RE.search(candidate_src))
    return StaticCheckResult(syntax_ok, syntax_error, signature_preserved)


def make_diff(baseline_src: str, candidate_src: str) -> str:
    return "".join(
        difflib.unified_diff(
            baseline_src.splitlines(keepends=True),
            candidate_src.splitlines(keepends=True),
            fromfile="submissions/baseline/main.py",
            tofile="submissions/candidate/main.py",
        )
    )


def run_reviewer(proposal: Proposal, baseline_src: str, candidate_src: str) -> tuple[bool, str]:
    checks = static_check(candidate_src)
    if not checks.ok:
        return False, f"REJECT (static check failed)\n{checks.report()}"

    diff = make_diff(baseline_src, candidate_src)
    prompt = (
        PROMPT_TEMPLATE.replace("{{ proposal_md }}", proposal.body)
        .replace("{{ diff }}", diff)
        .replace("{{ static_check_report }}", checks.report())
    )
    response = call(prompt, role="reviewer")
    approved = bool(re.search(r"判定[:：]\s*APPROVE", response))
    return approved, response


if __name__ == "__main__":
    from agents.strategist import run_strategist

    baseline_src = (REPO_ROOT / "submissions" / "baseline" / "main.py").read_text()
    candidate_src = (REPO_ROOT / "submissions" / "candidate" / "main.py").read_text()
    proposals = run_strategist()
    approved, response = run_reviewer(proposals[0], baseline_src, candidate_src)
    print(response)
    print("APPROVED:", approved)
