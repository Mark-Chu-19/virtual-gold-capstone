"""HF transformers local model: returns text, per-token logprobs and a
hidden state for every sample (todo/TODO.md A1, design doc §2 footnote).

torch/transformers are imported lazily so the rest of the harness (and its
tests) runs on laptops without a GPU stack. Install with `pip install -e ".[hf]"`.
"""

from __future__ import annotations

from harness.types import Query, Sample


class HFTransformersModel:
    def __init__(
        self,
        model_id: str,
        load_in_4bit: bool = True,
        max_new_tokens: int = 256,
        hidden_layer: int = -1,
    ):
        """`hidden_layer` picks which layer's hidden state is stored for a
        Semantic Entropy Probe; which layer to use is still an open research
        question (todo/TODO.md F29), so it stays configurable."""
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(model_id)
        if self._tokenizer.pad_token_id is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token
        quantization = (
            BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16)
            if load_in_4bit
            else None
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            model_id, quantization_config=quantization, device_map="auto"
        )
        self._model.eval()
        self._max_new_tokens = max_new_tokens
        self._hidden_layer = hidden_layer

    def generate(self, query: Query, n: int, temperature: float) -> list[Sample]:
        torch = self._torch
        inputs = self._tokenizer(query.prompt, return_tensors="pt").to(self._model.device)
        prompt_len = inputs["input_ids"].shape[1]

        with torch.no_grad():
            out = self._model.generate(
                **inputs,
                do_sample=True,
                temperature=temperature,
                num_return_sequences=n,
                max_new_tokens=self._max_new_tokens,
                pad_token_id=self._tokenizer.pad_token_id,
                output_scores=True,
                output_hidden_states=True,
                return_dict_in_generate=True,
            )
            transition_scores = self._model.compute_transition_scores(
                out.sequences, out.scores, normalize_logits=True
            )

        generated = out.sequences[:, prompt_len:]
        eos = self._tokenizer.eos_token_id
        samples: list[Sample] = []
        for i in range(n):
            tokens = generated[i]
            length = int(tokens.shape[0])
            if eos is not None:
                eos_positions = (tokens == eos).nonzero()
                if len(eos_positions) > 0:
                    length = int(eos_positions[0].item())
            length = max(length, 1)
            text = self._tokenizer.decode(tokens[:length], skip_special_tokens=True)
            logprobs = [float(x) for x in transition_scores[i, :length].cpu()]
            # hidden_states[step][layer]: step 0 covers the prompt (take its
            # last position), later steps hold one new token each.
            step = length - 1
            layer_states = out.hidden_states[step][self._hidden_layer]
            hidden = layer_states[i, -1, :].float().cpu()
            samples.append(Sample(text=text, token_logprobs=logprobs, hidden_state=hidden))
        return samples
