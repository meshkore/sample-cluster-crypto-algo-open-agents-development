"""THE MIND - a local language model, used for the one job it is actually better at.

    *"It is likely that we would also need to access a Qwen model running on this same machine
    to make decisions about whether we are interested in being subscribed to a channel or not;
    what implication the price of cereal has for, say, the restaurant industry on a country's
    coast."*

That is exactly the right job for it, and it is worth being precise about why. A language model
is bad at arithmetic under uncertainty and excellent at the question *"could these two things
plausibly be connected at all?"* - which is a question about the world, not about this dataset,
and which no amount of correlation can answer because you cannot correlate a channel you never
thought to subscribe to.

So the division of labour is fixed and it is the same one the rest of this laboratory runs on:

    THE MODEL PROPOSES. THE RECORD DISPOSES.

A proposal from here is a hypothesis with a trial subscription attached. It survives only if
`entity.review` measures a relationship over the following month. Nothing an LLM says ever
becomes a coefficient, an effect size, or a fact in this system, and nothing it says is
believed because it sounded confident.

WHAT RUNS WHERE. The machine has a GPU and Ollama is the assumed host. Everything here degrades
to `None` when nothing is listening on the port, because a simulation that stops when a side
car is down is a simulation nobody can leave running.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

HOST = os.environ.get("MWMODEL_LLM_HOST", "http://127.0.0.1:11434")
MODEL = os.environ.get("MWMODEL_LLM", "qwen2.5:7b")
TIMEOUT = float(os.environ.get("MWMODEL_LLM_TIMEOUT", "25"))

_available: bool | None = None


def available() -> bool:
    """Whether a local model is actually answering. Cached, and never raises."""
    global _available
    if _available is None:
        try:
            with urllib.request.urlopen(f"{HOST}/api/tags", timeout=3) as r:
                _available = r.status == 200
        except Exception:
            _available = False
    return bool(_available)


def ask(prompt: str, system: str = "", json_mode: bool = True) -> str | None:
    """One completion, or None. No retries, no streaming, no state."""
    if not available():
        return None
    body = {"model": MODEL, "prompt": prompt, "stream": False,
            "options": {"temperature": 0.2, "num_predict": 400}}
    if system:
        body["system"] = system
    if json_mode:
        body["format"] = "json"
    try:
        req = urllib.request.Request(
            f"{HOST}/api/generate", data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8")).get("response")
    except Exception:
        return None


SYSTEM = (
    "You advise an agent-based simulation of the world economy on which data channels one "
    "entity should listen to. You are NOT being asked to predict anything, estimate any "
    "number, or say how strong a relationship is - only whether a causal link could plausibly "
    "exist at all, in the direction channel -> this entity. Be inclusive about mechanism and "
    "strict about direction. Answer with JSON only: {\"channels\": [...], \"why\": {...}}."
)


def propose_channels(who: str, description: str, candidates: list[str],
                     limit: int = 6) -> list[str]:
    """Ask which of these channels could plausibly move this entity. Returns a subset.

    The return is always a SUBSET of `candidates` - the model is never allowed to invent a
    topic name, both because a hallucinated channel would silently never fire and because the
    set of things that exist in this world is a fact about the code, not a matter of opinion.
    """
    if not candidates or not available():
        return []
    prompt = (f"Entity: {who}\nWhat it is: {description}\n\n"
              f"Available channels:\n" + "\n".join(f"- {c}" for c in sorted(candidates)) +
              f"\n\nWhich at most {limit} of these could plausibly influence this entity? "
              "Use only channel names from the list above.")
    raw = ask(prompt, SYSTEM)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    got = data.get("channels") or []
    allowed = set(candidates)
    return [c for c in got if isinstance(c, str) and c in allowed][:limit]
