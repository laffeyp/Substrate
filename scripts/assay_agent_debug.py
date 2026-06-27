"""Trace the container agent on ONE instance (verbose) to see its actions + final diff. Env-gated."""

import sys

from datasets import load_dataset

from substrate.assay.swebench_agent import solve_in_container
from substrate.reference._models import OllamaResponder

IID = sys.argv[1] if len(sys.argv) > 1 else "astropy__astropy-12907"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "qwen3-coder:480b-cloud"


def main() -> None:
    inst = next(x for x in load_dataset("princeton-nlp/SWE-bench_Lite", split="test") if x["instance_id"] == IID)
    patch = solve_in_container(inst, OllamaResponder(MODEL, max_tokens=2048), max_steps=8, verbose=True)
    print(f"\n=== final patch: {len(patch)}b ===", flush=True)
    if patch:
        print(patch[:800], flush=True)


if __name__ == "__main__":
    main()
