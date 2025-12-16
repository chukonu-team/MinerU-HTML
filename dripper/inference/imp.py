from abc import ABC, abstractmethod
from typing import override

from vllm import LLM, SamplingParams


class InferenceBackend(ABC):
    @abstractmethod
    def generate(self, prompt_list: list[str]) -> list[str]:
        pass


class VLLMInferenceBackend(InferenceBackend):
    def __init__(self, model_path:str, tensor_parallel_size:int):
        self.gen_config = SamplingParams(
            top_k=1, top_p=0.95, temperature=0, max_tokens=8 * 1024
        )
        self._llm = LLM(model=model_path, tensor_parallel_size=tensor_parallel_size)

    @override
    def generate(self, prompt_list: list[str]) -> list[str]:
        response = self._llm.generate(prompt_list, sampling_params=self.gen_config)
        return response
