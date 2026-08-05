"""Shared LLM-calling seam for the five agent roles (researcher, analyst,
strategist, coder, reviewer).

Two modes, chosen automatically:

- **API mode**: if `ANTHROPIC_API_KEY` is set and the `anthropic` package is
  installed, prompts are sent directly to the Claude API and the loop can run
  unattended (e.g. from a scheduled job).
- **Manual mode** (the safer default recommended for the first version of
  this environment): the prompt is written to `reports/pending_prompts/` and
  `call()` raises `PendingManualReview` so `run_improvement_loop.py` stops
  and tells you which file to feed into a Claude Code session by hand. Paste
  the model's reply back with `write_reply()` and re-run the loop.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PENDING_DIR = REPO_ROOT / "reports" / "pending_prompts"


class PendingManualReview(Exception):
    """Raised in manual mode: the prompt is waiting for a human/Claude Code
    session to answer it."""

    def __init__(self, prompt_path: Path, reply_path: Path):
        self.prompt_path = prompt_path
        self.reply_path = reply_path
        super().__init__(
            f"No ANTHROPIC_API_KEY set -- prompt written to {prompt_path}.\n"
            f"Run it through Claude Code, then save the reply to {reply_path} "
            f"and re-run the loop."
        )


def call(prompt: str, role: str, model: str = "claude-sonnet-5") -> str:
    """Sends `prompt` to the LLM and returns the text reply.

    `role` is a short slug (e.g. "analyst", "strategist") used to name the
    pending-prompt file in manual mode.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        import anthropic  # imported lazily so manual mode has no hard dependency

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    prompt_path = PENDING_DIR / f"{role}_prompt.md"
    reply_path = PENDING_DIR / f"{role}_reply.md"
    prompt_path.write_text(prompt)

    if reply_path.exists():
        reply = reply_path.read_text()
        reply_path.unlink()  # consume so stale replies can't be reused silently
        return reply

    raise PendingManualReview(prompt_path, reply_path)
