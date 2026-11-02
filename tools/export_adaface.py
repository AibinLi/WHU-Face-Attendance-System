"""Export reviewed CVLFace AdaFace architecture to ONNX. CPU export, no remote code loading."""
from pathlib import Path
import sys
import types
import onnx
import torch
from safetensors.torch import load_file

root = Path(__file__).resolve().parents[1]
source = (root / 'docs/adaface_architecture.py').read_text('utf8')
# fvcore is used solely by upstream's optional FLOP-count CLI.
source = source.replace('from fvcore.nn import flop_count', '')
architecture = types.ModuleType('reviewed_cvlface_iresnet')
exec(compile(source, 'reviewed_cvlface_iresnet.py', 'exec'), architecture.__dict__)
torch.set_num_threads(4)
model = architecture.IR_101((112, 112))
weights = load_file(str(root / 'models/adaface_ir101.safetensors'))
model.load_state_dict({k.removeprefix('model.net.'): v for k, v in weights.items()}, strict=True)
model.eval()
torch.onnx.export(model, torch.zeros(1, 3, 112, 112), str(root / 'models/adaface_ir101.onnx'),
                  input_names=['input'], output_names=['embedding'], opset_version=13, dynamo=False)
print('AdaFace exported', flush=True)
