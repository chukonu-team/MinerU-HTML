from abc import ABC, abstractmethod
from typing import override

from vllm import LLM, SamplingParams
import asyncio
from vllm import AsyncLLMEngine, AsyncEngineArgs
import uuid

class InferenceBackend(ABC):
    @abstractmethod
    def generate(self, prompt_list: list[str], gen_config: SamplingParams = None) -> list[str]:
        pass

    @abstractmethod
    def get_tokenizer(self):
        pass

    @abstractmethod
    def stop(self):
        pass
    
    @abstractmethod
    async def generateAsync(self, prompt_list: list[str], gen_config: SamplingParams = None) -> list[str]:
        pass



class VLLMInferenceBackend(InferenceBackend):
    def __init__(self, model_path:str, tensor_parallel_size:int):
        self.gen_config = SamplingParams(
            top_k=1, top_p=0.95, temperature=0, max_tokens=8 * 1024
        )
        # self._llm = LLM(model=model_path, tensor_parallel_size=tensor_parallel_size)
        # self._llm = LLM(model=model_path, tensor_parallel_size=tensor_parallel_size, kv_cache_dtype="fp8_e5m2", disable_log_stats=False, max_num_seqs=64, gpu_memory_utilization=0.9)
        self._llm = LLM(model=model_path, tensor_parallel_size=tensor_parallel_size, disable_log_stats=False
        # , log_level="INFO"
        , gpu_memory_utilization=0.9)

    @override
    def generate(self, prompt_list: list[str], gen_config: SamplingParams = None) -> list[str]:
        # if gen_config is None:
        if False:
            response = self._llm.generate(prompt_list, sampling_params=self.gen_config)
        else:
            response = self._llm.generate(prompt_list, gen_config)
        return response

    @override
    def get_tokenizer(self):
        return self._llm.get_tokenizer()

    @override
    def stop(self):
        # return self._llm.llm_engine.engine_core.stop()
        pass
    
    @override
    async def generateAsync(self, prompt_list: list[str], gen_config: SamplingParams = None) -> list[str]:
        pass


class VLLMInferenceBackendAsync(InferenceBackend):
    def __init__(self, model_path:str, tensor_parallel_size:int):
        self.gen_config = SamplingParams(
            top_k=1, top_p=0.95, temperature=0, max_tokens=8 * 1024
        )
        
        # self._llm = LLM(model=model_path, tensor_parallel_size=tensor_parallel_size, disable_log_stats=True
        # # , log_level="INFO"
        # , gpu_memory_utilization=0.9)

        engine_args = AsyncEngineArgs(
            model=model_path,
            tensor_parallel_size=tensor_parallel_size,
            # gpu_memory_utilization=GPU_UTIL,
            trust_remote_code=True,
            # quantization="awq",  # 量化降低显存占用，可选
            # max_num_batched_tokens=16384,  # 核心！调大这个值，vLLM能调度更多请求并行
            enable_chunked_prefill=True,   # 开启分块预填充，长prompt也不会阻塞
        )
        self.async_engine = AsyncLLMEngine.from_engine_args(engine_args)

    @override
    def generate(self, prompt_list: list[str], gen_config: SamplingParams = None) -> list[str]:
        raw_results = asyncio.run(self.generateAsync(prompt_list,self.gen_config))
        return raw_results

    @override
    def get_tokenizer(self):
        return None

    @override
    def stop(self):
        # return self._llm.llm_engine.engine_core.stop()
        pass
    
    @override
    async def generateAsync(self, prompt_list: list[str], gen_config: SamplingParams = None) -> list[str]:
        final_results = []
        for idx, prompt in enumerate(prompt_list):
            req_id = str(uuid.uuid4())[:8]
            output = await self.infer_single_request(prompt, req_id, gen_config)
            final_results.append(output)
        return final_results

    async def infer_single_request(self, prompt: str, req_id: str, gen_config: SamplingParams = None):
        async for output in self.async_engine.generate(prompt, gen_config, req_id):
             final_output = output
        return final_output
