import onnxruntime
import numpy as np
import cv2
import ctypes
import glob
import importlib.util
import logging
import os
import sys
from abc import ABC, abstractmethod
from typing import Any, Tuple, Union, List

logger = logging.getLogger(__name__)
_DLL_DIRECTORY_HANDLES = []
_DLL_PATHS_ADDED = set()
CHRO_GPU_RUNTIME_PATH = os.getenv("CHRO_GPU_RUNTIME_PATH", r"D:\CHRO_GPU_RUNTIME\python_pkgs")


def _build_session_options():
    options = onnxruntime.SessionOptions()
    options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.enable_mem_pattern = True
    options.enable_cpu_mem_arena = True
    options.intra_op_num_threads = _thread_count_from_env("CHRO_ONNX_INTRA_THREADS", 2)
    options.inter_op_num_threads = _thread_count_from_env("CHRO_ONNX_INTER_THREADS", 1)
    options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
    return options


def _thread_count_from_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _preferred_providers():
    available = onnxruntime.get_available_providers()
    requested = os.getenv("CHRO_ONNX_PROVIDERS", "").strip()

    if requested:
        providers = [provider.strip() for provider in requested.split(",") if provider.strip()]
    else:
        providers = [
            "CUDAExecutionProvider",
            "DmlExecutionProvider",
            "CPUExecutionProvider",
        ]

    providers = [provider for provider in providers if provider in available]
    if "CUDAExecutionProvider" in providers and not _cuda_dependencies_available():
        providers = [provider for provider in providers if provider != "CUDAExecutionProvider"]
        if "CPUExecutionProvider" in available and "CPUExecutionProvider" not in providers:
            providers.append("CPUExecutionProvider")

    return providers


def _try_preload_cuda_dlls():
    preload = getattr(onnxruntime, "preload_dlls", None)
    if preload is None:
        return
    if not (_module_available("nvidia") or _module_available("torch")):
        return

    try:
        # Empty directory means: search nvidia site packages first, then the
        # default DLL paths. CHRO_GPU_RUNTIME_PATH is inserted into sys.path
        # before this runs, so the D: drive runtime package is eligible here.
        preload(cuda=True, cudnn=True, msvc=True, directory="")
    except Exception as e:
        logger.debug("ONNX Runtime preload_dlls failed: %s", e)


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _dll_loadable(name: str) -> bool:
    try:
        ctypes.WinDLL(name)
        return True
    except Exception:
        return False


def _add_cuda_dll_directories():
    if sys.platform != "win32" or not hasattr(os, "add_dll_directory"):
        return

    candidates = []
    if CHRO_GPU_RUNTIME_PATH and os.path.isdir(CHRO_GPU_RUNTIME_PATH):
        if CHRO_GPU_RUNTIME_PATH not in sys.path:
            sys.path.insert(0, CHRO_GPU_RUNTIME_PATH)
        candidates.extend(glob.glob(os.path.join(CHRO_GPU_RUNTIME_PATH, "nvidia", "*", "bin")))

    for env_name, value in os.environ.items():
        if env_name.startswith("CUDA_PATH") and value:
            candidates.append(os.path.join(value, "bin"))

    candidates.extend(glob.glob(r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v*\bin"))
    candidates.extend(glob.glob(r"C:\Program Files\NVIDIA\CUDNN\v*\bin"))
    candidates.extend(glob.glob(r"C:\Program Files\NVIDIA\CUDNN\*\bin"))

    for directory in candidates:
        if not directory or not os.path.isdir(directory):
            continue
        normalized = os.path.normcase(os.path.abspath(directory))
        if normalized not in _DLL_PATHS_ADDED:
            os.environ["PATH"] = directory + os.pathsep + os.environ.get("PATH", "")
            _DLL_PATHS_ADDED.add(normalized)
        try:
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(directory))
        except (FileNotFoundError, OSError):
            continue


def _cuda_dependencies_available() -> bool:
    if sys.platform != "win32":
        return True

    _add_cuda_dll_directories()
    _try_preload_cuda_dlls()
    required_dlls = ("cublas64_12.dll", "cublasLt64_12.dll", "cudnn64_9.dll")
    missing = [
        dll_name
        for dll_name in required_dlls
        if not _dll_loadable(dll_name)
    ]
    if missing:
        missing = [
            dll_name
            for dll_name in required_dlls
            if not _dll_loadable(dll_name)
        ]

    if missing:
        logger.warning(
            "检测到 onnxruntime-gpu，但 CUDA provider 依赖缺失或未加入 PATH: %s；本次使用 CPU。"
            "安装/加入 CUDA 12 与 cuDNN 9 后会自动启用 GPU。",
            ", ".join(missing)
        )
        return False

    return True


class BaseONNX(ABC):
    def __init__(self, model_path: str, input_size: Tuple[int, int]):
        """初始化ONNX模型基类

        Args:
            model_path (str): ONNX模型路径
            input_size (tuple): 模型输入尺寸 (width, height)
        """
        session_options = _build_session_options()
        providers = _preferred_providers()
        if not providers:
            providers = ["CPUExecutionProvider"]

        try:
            self.session = onnxruntime.InferenceSession(
                model_path,
                sess_options=session_options,
                providers=providers
            )
        except Exception as e:
            if providers != ["CPUExecutionProvider"]:
                logger.warning("ONNX GPU provider 初始化失败，回退到 CPU: %s", e)
                self.session = onnxruntime.InferenceSession(
                    model_path,
                    sess_options=session_options,
                    providers=["CPUExecutionProvider"]
                )
            else:
                raise

        actual_providers = self.session.get_providers()
        if "CUDAExecutionProvider" in providers and "CUDAExecutionProvider" not in actual_providers:
            logger.warning("ONNX CUDA provider 未实际启用，当前执行后端: %s", actual_providers)
        logger.info("ONNX模型 %s 使用执行后端: %s", os.path.basename(model_path), actual_providers)
        self.input_name = self.session.get_inputs()[0].name
        self.input_size = input_size

    def load_image(self, image: Union[cv2.UMat, str]) -> cv2.UMat:
        """加载图像

        Args:
            image (Union[cv2.UMat, str]): 图像路径或cv2图像对象

        Returns:
            cv2.UMat: 加载的图像
        """
        if isinstance(image, str):
            return cv2.imread(image)
        return image.copy()

    @abstractmethod
    def preprocess_image(self, img_bgr: cv2.UMat, *args, **kwargs) -> np.ndarray:
        """图像预处理抽象方法

        Args:
            img_bgr (cv2.UMat): BGR格式的输入图像
            
        Returns:
            np.ndarray: 预处理后的图像
        """
        pass

    @abstractmethod
    def run_inference(self, image: np.ndarray) -> Any:
        """运行推理的抽象方法

        Args:
            image (np.ndarray): 预处理后的输入图像

        Returns:
            Any: 模型输出结果
        """
        pass

    @abstractmethod
    def pred(self, image: Union[cv2.UMat, str], *args, **kwargs) -> Any:
        """预测的抽象方法

        Args:
            image (Union[cv2.UMat, str]): 输入图像或图像路径

        Returns:
            Any: 预测结果
        """
        pass

    @abstractmethod
    def draw_pred(self, img: cv2.UMat, *args, **kwargs) -> cv2.UMat:
        """绘制预测结果的抽象方法

        Args:
            img (cv2.UMat): 要绘制的图像

        Returns:
            cv2.UMat: 绘制结果后的图像
        """
        pass

    
    def check_images_list(self, images: List[Union[cv2.UMat, str, np.ndarray]]):
        """
        检查图像列表是否有效
        """
        for image in images:
            if not isinstance(image, cv2.UMat) and not isinstance(image, str) and not isinstance(image, np.ndarray):
                raise ValueError("The images must be a list of cv2.UMat or str or np.ndarray.")
 
