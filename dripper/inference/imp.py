from abc import ABC, abstractmethod
from typing import override

from vllm import LLM, SamplingParams
import torch

class InferenceBackend(ABC):
    @abstractmethod
    def generate(self, prompt_list: list[str]) -> list[str]:
        pass


class VLLMInferenceBackend(InferenceBackend):
    def __init__(self, model_path:str, tensor_parallel_size:int):
        self.gen_config = SamplingParams(
            top_k=1, top_p=0.95, temperature=0, max_tokens=8 * 1024
        )
        # self.gen_config = SamplingParams(
        #     temperature=0.7,
        #     max_tokens=1024,  # 单次生成 1K token，充分利用批量
        #     top_p=0.95
        # )
        
        self._llm = LLM(model=model_path,
                tensor_parallel_size=tensor_parallel_size,
                disable_log_stats=False,
                gpu_memory_utilization=0.85,
                max_num_batched_tokens=8192,
                enable_prefix_caching=True,
                max_num_seqs=32,
                kv_cache_dtype="fp8_e5m2"
            )

        
        # self._llm = LLM(model=model_path, tensor_parallel_size=tensor_parallel_size, disable_log_stats=False)
        # self._llm = LLM(model=model_path, tensor_parallel_size=tensor_parallel_size, disable_log_stats=False, gpu_memory_utilization=0.7)
        # RTX 4090 24G 高吞吐配置
        # self._llm = LLM(
        #     # 基础路径（保持你的原有配置）
        #     model="/home/ubuntu/cenjing/models", tensor_parallel_size=tensor_parallel_size, 
        #     # tokenizer="/home/ubuntu/cenjing/models",
        #     # served_model_name="/home/ubuntu/cenjing/models",
            
        #     # ===================== 显存核心优化（必配）=====================
        #     # 量化：4bit GPTQ 是 24G 显存跑超长序列的关键（需模型已量化）
        #     # quantization="gptq",
        #     # 显存利用率：24G 超长序列建议 0.75（预留 6G 应对峰值）
        #     gpu_memory_utilization=0.75,
        #     # KV Cache 降精度：用 fp8 进一步压缩缓存占用
        #     # kv_cache_dtype="fp8_e5m2",
        #     # 最大序列长度（保持你的需求）
        #     # max_seq_len=40960,
            
        #     # ===================== 并发/吞吐优化 =====================
        #     # 批处理 token 数：24G 下取 2048（平衡吞吐和显存）
        #     # max_num_batched_tokens=2048,
        #     # 最大并发序列数：24G 下取 6（比 4 多 2 个提升吞吐，比 8 少 2 个保稳定）
        #     # max_num_seqs=6,
        #     # 分块预填充：适配超长序列，提升 prefill 阶段吞吐
        #     enable_chunked_prefill=True,
        #     # chunked_prefill_size=1024,
        #     enforce_eager=False  # 禁用 Eager 模式，强制编译加速
        #     # 禁用前缀缓存（超长序列下收益低，还占显存）
        #     # enable_prefix_caching=False
        # )
        
        self._llm = LLM(
            # 模型路径（替换为你的实际路径）
            model=model_path,
            # ===================== 核心必选参数（无兼容问题）=====================
            tensor_parallel_size=1,  # 单卡部署（必选）
            disable_log_stats=False, 
            dtype=torch.bfloat16,     # RTX 4090 最优精度（必选）
            trust_remote_code=True,   # Qwen3 必须开启（必选）
            seed=42,                  # 固定种子（可选，增加稳定性）
            # ===================== 性能优化（仅保留无兼容问题的参数）=====================
            # 并发配置（核心提升吞吐量，无兼容问题）
            max_num_batched_tokens=4096,  # 从 8192 下调，降低显存压力
            max_num_seqs=16,              # 从 32 下调，优先保证加载成功
            # 显存优化（核心，无兼容问题）
            gpu_memory_utilization=0.85,  # 适度降低，避免 dripper 显存溢出
            kv_cache_dtype="fp8_e5m2",    # fp8 KV Cache 是核心优化（无兼容问题）
            quantization=None            # 0.6B 模型无需量化
            # max_seq_len=32768            # 适配 Qwen3-0.6B 原生上下文
        )
        

    @override
    def generate(self, prompt_list: list[str]) -> list[str]:
        # self._llm.start_profile()
        response = self._llm.generate(prompt_list, sampling_params=self.gen_config)
        # self._llm.stop_profile()
        # metrics = self._llm.get_metrics()
        # print(f"VLLM generation metrics: {metrics}")
        return response
