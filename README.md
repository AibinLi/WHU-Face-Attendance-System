# 见齐：本地人脸考勤系统

这是一个**完全本地运行**的班级合照考勤系统：先上传班级合照自动建立人员底库，再上传考勤照片进行识别，最后导出 CSV/JSON。照片、人脸特征和考勤记录只保存在运行机器上，不调用第三方人脸识别 API。

## 功能

- 上传底库照片，自动检测人脸并生成候选人员编号。
- 在网页中合并、拆分、排除误检、重命名人员和更换头像。
- 上传现场合照或个人照片，按人员去重并标记出席、缺席和待确认。
- 对低置信度结果人工确认，结束场次后下载 CSV/JSON。
- 自动保存数据库和操作记录，支持界面备份。

## 环境要求

- Windows x64、Linux 或 macOS
- Python 3.10–3.12（推荐 3.11）
- 至少 8 GB 内存；模型文件约 700 MB
- NVIDIA 显卡可选；没有显卡时使用 CPU

## 安装与启动

在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tools/download_models.py
.\.venv\Scripts\python.exe launch.py
```

然后打开 <http://127.0.0.1:8765>。Windows 用户也可以双击 `启动考勤系统.bat`。

### NVIDIA GPU

安装匹配的 NVIDIA 驱动后执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-gpu.txt
```

项目会自动优先使用 CUDA；强制 CPU 可设置 `ATTENDANCE_CPU=1`。下载脚本会校验 SHA256，也支持 `--endpoint` 指定镜像。

## 第一次使用：建立底库

1. 进入“班级底库”，上传包含清晰正脸的班级照片（JPG、PNG、WEBP，一次最多 20 张）。建议每个人至少出现在两张不同角度的照片中。
2. 点击“生成/重建人员编号”，等待处理完成。
3. 检查人脸框和头像：合并同一人的重复编号，拆分误合并的人脸，排除误检，并按需要重命名。
4. 填写实际人数并确认底库。只有确认后才能创建正式考勤场次。

照片不需要按姓名命名；系统先生成编号，确认后可在页面中改成姓名或学号。底库确认前可以反复上传和修正。

## 进行考勤

1. 点击“新建考勤”，输入场次名称。
2. 上传现场合照或个人照片，可分批上传；建议使用清晰原图，并让相邻区域有重叠。
3. 检查检测框和低置信度候选；无法自动确定时选择正确编号，或标记为不计入。
4. 确认没有待处理人脸后结束场次。
5. 在场次页面下载 CSV/JSON。已结束场次使用创建时的底库快照，之后修改底库不会改变历史结果。

## 配置与目录

| 路径 | 用途 |
| --- | --- |
| `server.py` | Flask 本地 API 与任务队列 |
| `launch.py` | 检查端口、预热模型并打开浏览器 |
| `attendance/engine.py` | SCRFD 检测、对齐和 ONNX 特征提取 |
| `attendance/matching.py` | 相似度计算、聚类和全局分配 |
| `attendance/service.py` | 底库、考勤、人工修正和快照 |
| `attendance/store.py` | 原子写入、备份和恢复 |
| `static/` | 无外网依赖的网页界面 |
| `models/` | 模型清单；权重由下载脚本获取 |
| `data/` | 运行时图片、特征、数据库和备份 |

默认数据目录是项目下的 `data/`，可用环境变量 `ATTENDANCE_DATA` 改到其他磁盘；端口可用 `PORT` 修改。服务默认只监听本机地址，不适合直接暴露到公网。

## 模型与许可

`tools/download_models.py` 会下载 SCRFD、ArcFace 和 AdaFace 权重；来源、版本、SHA256 和上游许可见 [`models/SOURCES.md`](models/SOURCES.md)。预训练权重按上游条款主要用于研究/课程演示，发布或商用前请自行确认许可。模型不随 Git 仓库提交，避免仓库过大。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

测试验证业务流程和匹配逻辑；真正处理图片前仍需下载模型并人工核对底库。请不要把 `data/` 中的照片、特征或数据库提交到 GitHub。

## 注意事项

这是照片识别考勤工具，不提供可靠活体检测，不能用于防照片代签。遮挡严重、脸部过小或光线不足时应补拍或人工确认。请获得被拍摄者授权，并遵守当地隐私和生物特征信息法规。
