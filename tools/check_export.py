"""Numerically verify AdaFace conversion on deterministic inputs."""
from pathlib import Path
import types
import onnx
import onnxruntime as ort
import numpy as np
import torch
from safetensors.torch import load_file

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'docs/adaface_architecture.py').read_text('utf8').replace('from fvcore.nn import flop_count','')
module=types.ModuleType('checked_adaface')
exec(compile(source,'reviewed_cvlface_iresnet.py','exec'),module.__dict__)
model=module.IR_101((112,112))
model.load_state_dict({k.removeprefix('model.net.'):v for k,v in load_file(str(ROOT/'models/adaface_ir101.safetensors')).items()},strict=True)
model.eval();torch.set_num_threads(4)
runtime=ort.InferenceSession(str(ROOT/'models/adaface_ir101.onnx'),providers=['CPUExecutionProvider'])
rng=np.random.default_rng(2026)
for _ in range(3):
    x=rng.uniform(-1,1,(1,3,112,112)).astype(np.float32)
    with torch.inference_mode():expected=model(torch.from_numpy(x)).numpy()
    actual=runtime.run(None,{'input':x})[0]
    cosine=float(np.sum(expected*actual)/(np.linalg.norm(expected)*np.linalg.norm(actual)))
    error=float(np.max(np.abs(expected-actual)))
    print('cosine',cosine,'max_abs_error',error)
    assert cosine>0.99999 and error<0.001
print('ONNX conversion verified on 3 deterministic inputs.')
