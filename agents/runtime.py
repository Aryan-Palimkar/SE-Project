"""Lazily loaded model runtime shared by the agent nodes.

One base model is loaded on first use and each LoRA adapter is attached to it, so several
adapters fit on a small GPU. Nodes only see a `Backend`, so tests can use MockBackend.
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass, field

from core.backends import Backend


@dataclass
class AdapterSpec:
    """A named LoRA adapter directory, or None for the plain base model.

    `task` enables JSON-schema constrained decoding for that adapter.
    """
    name: str
    path: str | None = None
    max_new_tokens: int = 768
    task: str | None = None


class ModelHub:
    """Holds one base model and its adapters, loaded on first use."""

    def __init__(self, model_id: str, adapters: dict[str, AdapterSpec] | None = None,
                 load_in_4bit: bool = True, device_map: str | dict | None = None):
        self.model_id = model_id
        self.adapters = dict(adapters or {})
        self.load_in_4bit = load_in_4bit
        self.device_map = device_map
        self._model = None
        self._tokenizer = None
        self._attached: set[str] = set()
        self._active: str | None = None
        self._constraints: dict[str, object] = {}


    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _load_base(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        cuda = torch.cuda.is_available()
        dtype = (torch.bfloat16 if cuda and torch.cuda.is_bf16_supported() else
                 torch.float16 if cuda else torch.float32)
        quant = (BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=dtype,
                                    bnb_4bit_use_double_quant=True) if self.load_in_4bit and cuda else None)
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_id, padding_side="left")
        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token
        device_map = self.device_map if self.device_map is not None else ({"": 0} if cuda else None)
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_id, quantization_config=quant, torch_dtype=dtype, device_map=device_map)
        self._model.eval()

    def _attach(self, name: str) -> None:
        """Attach an adapter to the shared base model (first one wraps it in a PeftModel)."""
        from peft import PeftModel

        spec = self.adapters[name]
        if spec.path is None or name in self._attached:
            return
        if not self._attached:
            self._model = PeftModel.from_pretrained(self._model, spec.path, adapter_name=name)
        else:
            self._model.load_adapter(spec.path, adapter_name=name)
        self._attached.add(name)

    def ensure(self, name: str | None = None) -> None:
        if self._model is None:
            self._load_base()
        if name and self.adapters.get(name) and self.adapters[name].path:
            self._attach(name)

    def unload(self) -> None:
        """Drop the model and free the GPU. The next generate() reloads it."""
        self._model = self._tokenizer = None
        self._attached.clear()
        self._active = None
        try:
            import gc

            import torch
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    @contextlib.contextmanager
    def paused(self):
        """Free the model for the duration of the block (for handing the GPU to something else)."""
        self.unload()
        try:
            yield self
        finally:
            pass


    def _constraint(self, task: str | None):
        """The constrained-decoding function for a task, built once the tokenizer exists."""
        if not task:
            return None
        if task not in self._constraints:
            try:
                from train.constrained import prefix_allowed_tokens_fn

                self._constraints[task] = prefix_allowed_tokens_fn(task, self._tokenizer)
            except ImportError:                          # no enforcer installed: decode unconstrained
                self._constraints[task] = None
        return self._constraints[task]

    def generate(self, adapter: str | None, system: str, user: str, max_new_tokens: int | None = None) -> str:
        import torch

        self.ensure(adapter)
        spec = self.adapters.get(adapter or "", None)
        limit = max_new_tokens or (spec.max_new_tokens if spec else 512)
        use_adapter = bool(spec and spec.path)
        if use_adapter and self._active != adapter:
            self._model.set_adapter(adapter)
            self._active = adapter
        prompt = self._tokenizer.apply_chat_template(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            tokenize=False, add_generation_prompt=True)
        enc = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)
        ctx = contextlib.nullcontext() if use_adapter else _no_adapter(self._model, self._attached)
        with torch.no_grad(), ctx:
            out = self._model.generate(**enc, max_new_tokens=limit, do_sample=False,
                                       prefix_allowed_tokens_fn=self._constraint(spec.task if spec else None),
                                       pad_token_id=self._tokenizer.pad_token_id)
        return self._tokenizer.decode(out[0, enc["input_ids"].shape[1]:], skip_special_tokens=True).strip()

    def backend(self, adapter: str | None = None, max_new_tokens: int | None = None) -> Backend:
        return HubBackend(self, adapter, max_new_tokens)


def _no_adapter(model, attached: set[str]):
    """Run the base model even though adapters are attached (zero-shot comparisons)."""
    return model.disable_adapter() if attached else contextlib.nullcontext()


@dataclass
class HubBackend(Backend):
    """A `Backend` view of one adapter on the hub; nodes hold this and nothing else."""
    hub: ModelHub
    adapter: str | None = None
    max_new_tokens: int | None = None
    name: str = field(init=False, default="")

    def __post_init__(self):
        self.name = f"{self.hub.model_id}+{self.adapter}" if self.adapter else self.hub.model_id

    def complete(self, system: str, user: str) -> str:
        return self.hub.generate(self.adapter, system, user, self.max_new_tokens)

    def complete_batch(self, requests):
        return [self.complete(s, u) for s, u in requests]
