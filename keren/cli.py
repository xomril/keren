from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict

from .access import DEFAULT_OPERATOR
from .app import answer
from .env import load_env
from .model import AnthropicModel, FakeModel

EXIT = {"ok": 0, "refused": 0, "denied": 3, "error": 4}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="keren", description="Portfolio assistant prototype (internal demo)")
    ap.add_argument("customer_id")
    ap.add_argument("question")
    ap.add_argument("--operator", default=DEFAULT_OPERATOR, help="demo operator identity (NOT real auth)")
    ap.add_argument("--live", action="store_true",
                    help="use the real Anthropic API (paid; needs ANTHROPIC_API_KEY). Default: offline fake model")
    ap.add_argument("--json", action="store_true", help="print the full result as JSON")
    a = ap.parse_args(argv)
    if a.live:
        load_env()  # reads .env next to the project; real env vars win
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY is not set (put it in .env, see .env.example).", file=sys.stderr)
            return 2
    model = AnthropicModel() if a.live else FakeModel()
    if not a.live:
        print("[offline: fake model, no API call]", file=sys.stderr)
    res = answer(a.operator, a.customer_id, a.question, model)
    if a.json:
        print(json.dumps(asdict(res), ensure_ascii=False, indent=2))
    else:
        print(res.text)
        if res.sources:
            print("Sources: " + ", ".join(res.sources))
        for n in res.notes:
            print("note: " + n, file=sys.stderr)
    return EXIT[res.status]
