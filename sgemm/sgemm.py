import torch
import time 
from torch.utils.cpp_extension import load
from functools import partial
from typing import Optional

torch.set_grad_enabled(False)

# Load the CUDA kernel as a python module
lib = load(name='sgemm_lib', 
           sources=['sgemm.cu', 'sgemm_async.cu'], 
           extra_cuda_cflags=[
               "-O3",
                "-U__CUDA_NO_HALF_OPERATORS__",
                "-U__CUDA_NO_HALF_CONVERSIONS__",
                "-U__CUDA_NO_HALF2_OPERATORS__",
                "-U__CUDA_NO_BFLOAT16_CONVERSIONS__",
                "--expt-relaxed-constexpr",
                "--expt-extended-lambda",
                "--use_fast_math"
            ], 
           extra_cflags=['-std=c++17'])


def run_benchmark(perf_func: callable, 
                  a: torch.Tensor, b: torch.Tensor,
                  tag: str, out: Optional[torch.Tensor] = None, 
                  warmup: int = 10, iters: int = 100,
                  show_all: bool = False):
    if out is not None: 
        out.fill_(0)      
    if out is not None:
        for i in range(warmup):
            perf_func(a, b, out)
    else:
        for i in range(warmup):
            _ = perf_func(a, b) 
    
    torch.cuda.synchronize()
    start = time.time()
    # iters
    if out is not None:
        for i in range(iters):
            perf_func(a, b, out)
    else:
        for i in range(iters):
            out = perf_func(a, b) 
    torch.cuda.synchronize()
    end = time.time()
    total_time = (end - start) * 1000 # ms
    mean_time = total_time / iters
    out_info = f"out_{tag}"
    out_val = out.flatten().detach().cpu().numpy().tolist()[:3]
    out_val = [round(v, 8) for v in out_val]
    out_val = [f"{v:<12}" for v in out_val]
    print(f"{out_info:>32}: {out_val}, time:{mean_time:.6f}ms")
    if show_all: print(out)
    return out.clone(), mean_time


Ms = [2048, 4096]
Ns = [2048, 4096]
Ks = [1024, 2048]
MNKs = [(M, N, K) for M in Ms for N in Ns for K in Ks]
for (M, N, K) in MNKs:
    print("-" * 110)
    print(" " * 45 + f"M={M}, N={N}, K={K}")
    a = torch.randn((M, K)).cuda().float().contiguous() 
    b = torch.randn((K, N)).cuda().float().contiguous() 
    c = torch.randn((M, N)).cuda().float().contiguous() 
    run_benchmark(lib.sgemm_naive_f32,                     
                  a, b, "f32", c)
    run_benchmark(lib.sgemm_sliced_k_f32,                  
                  a, b, "f32(sk)", c)
    run_benchmark(lib.sgemm_t_8x8_sliced_k_f32x4,          
                  a, b, "f32x4(t8x8sk)", c)
    run_benchmark(lib.sgemm_t_8x8_sliced_k_f32x4_bcf,      
                  a, b, "f32x4(t8x8bcf)", c)
    run_benchmark(lib.sgemm_t_8x8_sliced_k_f32x4_bcf_offset,      
                  a, b, "f32x4(t8x8bcf+offset)", c)
    run_benchmark(lib.sgemm_t_8x8_sliced_k_f32x4_bcf_dbuf, 
                  a, b, "f32x4(t8x8dbuf)", c)
    run_benchmark(lib.sgemm_t_8x8_sliced_k_f32x4_bcf_dbuf_offset, 
                  a, b, "f32x4(t8x8dbuf+offset)", c)
    print("-" * 52 + "Async" + "-" * 53)
    run_benchmark(lib.sgemm_t_8x8_sliced_k_f32x4_bcf_dbuf_async, 
                  a, b, "f32x4(t8x8dbuf+async)",  c)
    run_benchmark(partial(torch.matmul, out=c),            
                  a, b, "f32_th")
    print("-" * 110)
