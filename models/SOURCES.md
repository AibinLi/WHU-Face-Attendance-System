# 预训练权重来源

所有身份识别均在本地推理；镜像仅用于下载公开权重，不上传班级照片。

| 本地文件 | 来源与版本 | 方法 |
| --- | --- | --- |
| scrfd_10g.onnx | [Immich antelopev2](https://huggingface.co/immich-app/antelopev2)，revision `51ca7e153bccebdbae224779e23c9c243e2fec85`，`detection/model.onnx` | InsightFace SCRFD-10G |
| arcface_r100.onnx | 同上，`recognition/model.onnx` | ArcFace R100 / Glint360K |
| adaface_ir101.safetensors | [作者 CVLFace 模型](https://huggingface.co/minchul/cvlface_adaface_ir101_webface12m)，revision `54f602a0737bd1ee4a4e7e9fd089a485f397fefd` | AdaFace IR101 / WebFace12M |
| adaface_ir101.onnx | 由以上 safetensors 与同 revision 的 `models/iresnet/model.py` 导出，opset 13 | 本地转换，无再训练 |

原始 AdaFace 架构保存在 `docs/adaface_architecture.py`，转换脚本为 `tools/export_adaface.py`。只去除用于 CLI FLOPs 统计的 fvcore 导入；模型结构、参数名和前向计算保留。权重键移除 `model.net.` 前缀后严格加载。RGB 输入按官方配置归一化到 [-1,1]。

文件的 SHA256 与大小记录在 `manifest.json`，可用于核验完整性。导出的 ONNX 与 PyTorch 数值一致性由 `tools/check_export.py` 检查。

InsightFace 代码与预训练模型的许可不同；公开预训练模型按上游说明仅限非商业研究使用。CVLFace 作者要求遵守原论文及训练数据许可。此项目按课程研究演示用途使用，分发或商用前应查阅以下上游原始条款，不能将其当作不受限制的商业权重。

- [InsightFace 许可说明](https://github.com/deepinsight/insightface/tree/master/python-package#license)
- [CVLFace 官方仓库](https://github.com/mk-minchul/CVLface)
- [AdaFace 官方模型卡](https://huggingface.co/minchul/cvlface_adaface_ir101_webface12m)
- [SCRFD 论文](https://arxiv.org/abs/2105.04714)
- [ArcFace 论文](https://arxiv.org/abs/1801.07698)
- [AdaFace 论文](https://arxiv.org/abs/2204.00964)

ArcFace、AdaFace 是已有预训练模型；本项目的分块、融合、模板聚合和约束匹配是工程实现，不能在答辩中表述为从六张照片训练了上述深度模型。
