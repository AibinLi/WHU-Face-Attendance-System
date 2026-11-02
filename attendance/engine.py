"""Local SCRFD + ArcFace ONNX inference. No remote recognition service."""
from pathlib import Path
import os
import threading
import cv2
import numpy as np
from PIL import Image, ImageOps
from .matching import unit

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
                      [41.5493, 92.3655], [70.7299, 92.2041]], dtype=np.float32)


def read_image(path):
    with Image.open(path) as image:
        if image.width * image.height > 80_000_000:
            raise ValueError('图片超过 8000 万像素，请先缩小。')
        rgb = np.asarray(ImageOps.exif_transpose(image).convert('RGB'))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def nms(boxes, scores, threshold=0.4):
    if not len(boxes):
        return []
    x1, y1, x2, y2 = np.asarray(boxes).T
    area = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
    order = np.argsort(-np.asarray(scores))
    keep = []
    while len(order):
        i = int(order[0]); keep.append(i)
        remaining = order[1:]
        inter = np.maximum(0, np.minimum(x2[i], x2[remaining]) - np.maximum(x1[i], x1[remaining])) * np.maximum(0, np.minimum(y2[i], y2[remaining]) - np.maximum(y1[i], y1[remaining]))
        iou = inter / np.maximum(area[i] + area[remaining] - inter, 1e-9)
        # IoM also removes nested duplicate detections from full-frame/tile passes.
        iom = inter / np.maximum(np.minimum(area[i], area[remaining]), 1e-9)
        order = remaining[(iou < threshold) & (iom < 0.75)]
    return keep


class Engine:
    def __init__(self):
        self.detector = self.recognizer = None
        self.quality_recognizer = None
        self.model_id = 'arcface-adaface-fusion-v1'
        self.provider = '未加载'
        self.lock = threading.RLock()

    def load(self):
        if self.detector is not None:
            return
        import onnxruntime as ort
        files = [ROOT / 'models/scrfd_10g.onnx', ROOT / 'models/arcface_r100.onnx', ROOT / 'models/adaface_ir101.onnx']
        if any(not p.exists() or p.stat().st_size < 1_000_000 for p in files):
            raise RuntimeError('缺少模型权重，请运行 tools/download_models.py。')
        # Load CUDA DLLs from project-local nvidia pip packages, when installed.
        import site
        self._dll_dirs = []
        dll_paths = []
        for base in site.getsitepackages():
            for directory in Path(base).glob('nvidia/*/bin'):
                dll_paths.append(str(directory))
                if hasattr(os, 'add_dll_directory'):
                    self._dll_dirs.append(os.add_dll_directory(str(directory)))
        # cuDNN loads component libraries itself via LoadLibrary, which uses PATH.
        os.environ['PATH'] = os.pathsep.join(dll_paths + [os.environ.get('PATH', '')])
        if os.name == 'nt':
            import ctypes
            # ORT 1.19 predates preload_dlls; explicitly load dependencies in order.
            self._dlls = []
            for name in ('cudart64_12.dll', 'cublasLt64_12.dll', 'cublas64_12.dll', 'cufft64_11.dll', 'cudnn64_9.dll'):
                for base in site.getsitepackages():
                    found = list((Path(base) / 'nvidia').glob('*/bin/' + name))
                    if found:
                        try:
                            self._dlls.append(ctypes.WinDLL(str(found[0])))
                        except OSError:
                            pass
                        break
        options = ort.SessionOptions()
        options.intra_op_num_threads = min(6, os.cpu_count() or 4)
        options.log_severity_level = 3
        providers = ['CPUExecutionProvider']
        if os.environ.get('ATTENDANCE_CPU') != '1' and 'CUDAExecutionProvider' in ort.get_available_providers():
            providers.insert(0, ('CUDAExecutionProvider', {'gpu_mem_limit': 3 * 1024**3,
                                                        'cudnn_conv_algo_search': 'HEURISTIC'}))
        self.detector = ort.InferenceSession(str(files[0]), options, providers=providers)
        self.recognizer = ort.InferenceSession(str(files[1]), options, providers=providers)
        self.quality_recognizer = ort.InferenceSession(str(files[2]), options, providers=providers)
        self.provider = self.recognizer.get_providers()[0]

    def _detect(self, image, size=640, threshold=0.45):
        h, w = image.shape[:2]
        ratio = min(size / w, size / h)
        rw, rh = max(1, round(w * ratio)), max(1, round(h * ratio))
        canvas = np.zeros((size, size, 3), np.uint8)
        canvas[:rh, :rw] = cv2.resize(image, (rw, rh))
        blob = cv2.dnn.blobFromImage(canvas, 1 / 128., (size, size), (127.5, 127.5, 127.5), swapRB=True)
        outputs = self.detector.run(None, {self.detector.get_inputs()[0].name: blob})
        levels = len(outputs) // 3
        strides = [8, 16, 32] if levels == 3 else [8, 16, 32, 64, 128]
        boxes, scores, landmarks = [], [], []
        for idx, stride in enumerate(strides):
            confidence = outputs[idx].reshape(-1)
            distance = outputs[idx + levels].reshape(-1, 4) * stride
            points = outputs[idx + 2 * levels].reshape(-1, 10) * stride
            grid = np.stack(np.mgrid[:size // stride, :size // stride][::-1], axis=-1).reshape(-1, 2) * stride
            anchors = len(confidence) // len(grid)
            grid = np.repeat(grid, anchors, axis=0)
            positive = np.where(confidence >= threshold)[0]
            c, d = grid[positive], distance[positive]
            b = np.stack([c[:, 0] - d[:, 0], c[:, 1] - d[:, 1],
                          c[:, 0] + d[:, 2], c[:, 1] + d[:, 3]], axis=1) / ratio
            p = (points[positive].reshape(-1, 5, 2) + c[:, None, :]) / ratio
            valid = (b[:, 2] > 0) & (b[:, 3] > 0) & (b[:, 0] < w) & (b[:, 1] < h)
            boxes.extend(b[valid]); scores.extend(confidence[positive][valid]); landmarks.extend(p[valid])
        keep = nms(boxes, scores)
        return [(np.asarray(boxes[i]), float(scores[i]), np.asarray(landmarks[i])) for i in keep]

    def extract(self, image, tiled=True):
        with self.lock:
            self.load()
            h, w = image.shape[:2]
            detections = self._detect(image)
            if tiled and max(w, h) > 1000:
                tile, step = 960, 720
                def starts(length):
                    return sorted(set(list(range(0, max(length - tile, 0), step)) + [max(length - tile, 0)]))
                for y in starts(h):
                    for x in starts(w):
                        for box, score, kps in self._detect(image[y:y + tile, x:x + tile]):
                            detections.append((box + [x, y, x, y], score, kps + [x, y]))
            indices = nms([d[0] for d in detections], [d[1] for d in detections])
            selected = sorted([detections[i] for i in indices], key=lambda d: (int(d[0][1] // 120), d[0][0]))
            faces = []
            for box, score, kps in selected:
                box = np.clip(box, [0, 0, 0, 0], [w, h, w, h])
                if min(box[2] - box[0], box[3] - box[1]) < 10:
                    continue
                # Deterministic least-squares similarity transform; no random RANSAC.
                from skimage.transform import SimilarityTransform
                transform = SimilarityTransform()
                if not transform.estimate(kps, REFERENCE):
                    continue
                aligned = cv2.warpAffine(image, transform.params[:2].astype(np.float32), (112, 112), borderValue=0)
                model_embeddings = []
                for recognizer in (self.recognizer, self.quality_recognizer):
                    embeddings = []
                    for sample in (aligned, cv2.flip(aligned, 1)):
                        blob = cv2.dnn.blobFromImage(sample, 1 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
                        embedding = recognizer.run(None, {recognizer.get_inputs()[0].name: blob})[0].reshape(-1)
                        embeddings.append(unit(embedding))
                    model_embeddings.append(unit(np.mean(embeddings, axis=0)))
                # Equal-weight late fusion: dot product equals mean of two cosine scores.
                embedding = unit(np.concatenate(model_embeddings))
                sharpness = float(cv2.Laplacian(cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
                face_size = min(box[2] - box[0], box[3] - box[1])
                quality = float(np.clip(face_size / 100, 0, 1) * 0.55 + np.clip(sharpness / 300, 0, 1) * 0.45)
                faces.append(dict(bbox=box.round(2).tolist(), landmarks=kps.round(2).tolist(),
                                  detection_score=round(score, 4), quality=round(quality, 4),
                                  face_size=round(float(face_size), 1), sharpness=round(sharpness, 1),
                                  embedding=embedding.tolist(), aligned=aligned))
            return faces
