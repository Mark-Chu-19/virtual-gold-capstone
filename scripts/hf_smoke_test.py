"""Sandbox smoke test for HFTransformersModel (TODO B12 acceptance).

Loads a model (4-bit by default), runs one generate call, and reports text,
per-token logprobs, hidden-state shape, tokens/s and peak GPU memory. Also
compares each stored hidden state against a full forward pass to show which
token position it actually corresponds to (last vs one before last).

Needs a CUDA GPU and `pip install -e ".[hf]"`; not runnable on the laptop
dev setup. Usage:
    python scripts/hf_smoke_test.py --model meta-llama/Llama-3.1-8B-Instruct
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import torch  # noqa: E402

from harness.hf_local_model import HFTransformersModel  # noqa: E402
from harness.types import Query  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt", default="Question: What is 17 * 3?\nAnswer:")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--hidden-layer", type=int, default=-1)
    parser.add_argument("--no-4bit", action="store_true")
    args = parser.parse_args()

    load_start = time.perf_counter()
    model = HFTransformersModel(
        args.model,
        load_in_4bit=not args.no_4bit,
        max_new_tokens=args.max_new_tokens,
        hidden_layer=args.hidden_layer,
    )
    print(f"load time: {time.perf_counter() - load_start:.1f}s")

    torch.cuda.reset_peak_memory_stats()
    query = Query(id="smoke", prompt=args.prompt, gold=None)
    gen_start = time.perf_counter()
    samples = model.generate(query, n=args.k, temperature=args.temperature)
    elapsed = time.perf_counter() - gen_start

    total_tokens = sum(len(s.token_logprobs) for s in samples)
    print(f"generated {len(samples)} samples, {total_tokens} tokens in {elapsed:.2f}s "
          f"({total_tokens / elapsed:.1f} tokens/s across the batch)")
    print(f"peak GPU memory: {torch.cuda.max_memory_allocated() / 2**30:.2f} GiB")

    for i, sample in enumerate(samples):
        assert sample.token_logprobs, f"sample {i} has no logprobs"
        assert sample.hidden_state is not None, f"sample {i} has no hidden state"
        print(f"[{i}] {sample.text!r}  logprobs={len(sample.token_logprobs)}  "
              f"hidden_state={tuple(sample.hidden_state.shape)}")

    check_hidden_state_position(model, args.prompt, samples[0], args.hidden_layer)


def check_hidden_state_position(model: HFTransformersModel, prompt: str, sample, layer: int) -> None:
    """Heuristic: re-tokenize prompt + sample text, run one forward pass, and
    see which of the last two positions the stored hidden state matches."""
    tokenizer, hf_model = model._tokenizer, model._model
    ids = tokenizer(prompt + sample.text, return_tensors="pt").to(hf_model.device)
    with torch.no_grad():
        states = hf_model(**ids, output_hidden_states=True).hidden_states[layer][0].float().cpu()
    stored = sample.hidden_state
    for label, position in (("last token", -1), ("one before last", -2)):
        cos = torch.nn.functional.cosine_similarity(stored, states[position], dim=0).item()
        print(f"hidden-state match vs {label}: cosine={cos:.4f}")
    print("Higher cosine indicates the position the stored state corresponds to "
          "(4-bit noise and re-tokenization make this approximate).")


if __name__ == "__main__":
    main()
