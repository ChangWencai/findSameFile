"""
相似文件检测器

使用感知哈希算法检测近似相似的图片和视频文件。
"""
import os
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Callable, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum

if TYPE_CHECKING:
    import imagehash

try:
    from PIL import Image
    import imagehash
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    imagehash = None  # type: ignore

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

from logger import get_logger
from file_scanner import FileInfo


class SimilarityMethod(Enum):
    """相似度计算方法"""
    AVERAGE_HASH = "average_hash"
    PERCEPTUAL_HASH = "perceptual_hash"
    DIFFERENCE_HASH = "difference_hash"
    WAVELET_HASH = "wavelet_hash"


@dataclass
class SimilarFile:
    """相似文件信息"""
    file_path: str
    similarity: float  # 0-100, 越高越相似
    hash_value: str


@dataclass
class SimilarGroup:
    """相似文件组"""
    reference_file: str
    similar_files: List[SimilarFile]
    method: SimilarityMethod


class SimilarityDetector:
    """相似文件检测器"""

    # 图片扩展名
    IMAGE_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.ico'
    }

    # 视频扩展名
    VIDEO_EXTENSIONS = {
        '.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v', '.mpg', '.mpeg'
    }

    def __init__(self):
        self.log = get_logger()
        self.method = SimilarityMethod.PERCEPTUAL_HASH
        self.threshold = 80  # 默认相似度阈值 80%

    def set_method(self, method: SimilarityMethod):
        """设置相似度计算方法"""
        self.method = method

    def set_threshold(self, threshold: int):
        """
        设置相似度阈值

        Args:
            threshold: 0-100, 相似度百分比
        """
        self.threshold = max(0, min(100, threshold))

    def calculate_image_hash(self, image_path: str) -> Optional['ImageHash']:
        """
        计算图片的感知哈希值

        Args:
            image_path: 图片文件路径

        Returns:
            哈希值对象，失败返回 None
        """
        if not HAS_PILLOW:
            self.log.error("Pillow 库未安装，无法计算图片哈希")
            return None

        try:
            with Image.open(image_path) as img:
                # 转换为 RGB 模式（处理 RGBA 等格式）
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                # 根据方法计算不同的哈希
                if self.method == SimilarityMethod.AVERAGE_HASH:
                    return imagehash.average_hash(img, hash_size=8)
                elif self.method == SimilarityMethod.PERCEPTUAL_HASH:
                    return imagehash.phash(img, hash_size=8)
                elif self.method == SimilarityMethod.DIFFERENCE_HASH:
                    return imagehash.dhash(img, hash_size=8)
                elif self.method == SimilarityMethod.WAVELET_HASH:
                    return imagehash.whash(img, hash_size=8)
                else:
                    return imagehash.phash(img, hash_size=8)
        except Exception as e:
            self.log.warning(f"计算图片哈希失败 {image_path}: {e}")
            return None

    def calculate_video_keyframe_hash(self, video_path: str,
                                      progress_callback: Optional[Callable[[int, int], None]] = None) -> Optional[str]:
        """
        提取视频关键帧并计算哈希值

        Args:
            video_path: 视频文件路径
            progress_callback: 进度回调

        Returns:
            哈希值字符串，失败返回 None
        """
        if not HAS_OPENCV:
            self.log.error("OpenCV 库未安装，无法提取视频关键帧")
            return None

        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None

            # 获取视频信息
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames == 0:
                cap.release()
                return None

            # 提取关键帧（均匀分布在视频中）
            num_samples = min(5, total_frames)  # 最多提取5帧
            frame_indices = [int(i * total_frames / num_samples) for i in range(num_samples)]

            hashes = []
            for i, frame_idx in enumerate(frame_indices):
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()

                if ret:
                    # 调整大小以加快哈希计算
                    frame = cv2.resize(frame, (64, 64))
                    # 转换为 PIL Image
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(frame_rgb)

                    # 计算哈希
                    if self.method == SimilarityMethod.AVERAGE_HASH:
                        h = imagehash.average_hash(img, hash_size=8)
                    elif self.method == SimilarityMethod.PERCEPTUAL_HASH:
                        h = imagehash.phash(img, hash_size=8)
                    elif self.method == SimilarityMethod.DIFFERENCE_HASH:
                        h = imagehash.dhash(img, hash_size=8)
                    elif self.method == SimilarityMethod.WAVELET_HASH:
                        h = imagehash.whash(img, hash_size=8)
                    else:
                        h = imagehash.phash(img, hash_size=8)

                    hashes.append(str(h))

                if progress_callback:
                    progress_callback(i + 1, num_samples)

            cap.release()

            # 组合所有关键帧的哈希
            return ','.join(hashes) if hashes else None

        except Exception as e:
            self.log.warning(f"提取视频关键帧哈希失败 {video_path}: {e}")
            return None

    def calculate_similarity(self, hash1: str, hash2: str) -> float:
        """
        计算两个哈希值之间的相似度

        Args:
            hash1: 第一个哈希值（可能包含多个用逗号分隔的哈希）
            hash2: 第二个哈希值

        Returns:
            相似度百分比 (0-100)
        """
        # 处理视频多关键帧哈希
        hashes1 = hash1.split(',')
        hashes2 = hash2.split(',')

        # 如果帧数不同，只比较前 min(n, m) 帧
        num_frames = min(len(hashes1), len(hashes2))

        if num_frames == 0:
            return 0.0

        total_similarity = 0.0
        for i in range(num_frames):
            # 计算汉明距离
            h1 = imagehash.hex_to_hash(hashes1[i])
            h2 = imagehash.hex_to_hash(hashes2[i])
            distance = h1 - h2

            # 转换为相似度百分比 (64 是 8x8 哈希的最大距离)
            max_distance = 64
            similarity = max(0, (max_distance - distance) / max_distance * 100)
            total_similarity += similarity

        # 计算平均相似度
        return total_similarity / num_frames

    def find_similar_images(self, files: List[FileInfo],
                           progress_callback: Optional[Callable[[int, int], None]] = None) -> List[SimilarGroup]:
        """
        在图片文件中查找相似的文件

        Args:
            files: 文件信息列表
            progress_callback: 进度回调 (current, total)

        Returns:
            相似文件组列表
        """
        if not HAS_PILLOW:
            self.log.error("请安装 Pillow 和 imagehash 库以使用相似图片检测功能")
            return []

        # 筛选图片文件
        image_files = [f for f in files if Path(f.path).suffix.lower() in self.IMAGE_EXTENSIONS]

        if len(image_files) < 2:
            return []

        # 计算所有图片的哈希
        hash_dict: Dict[str, str] = {}
        total = len(image_files)

        for i, file_info in enumerate(image_files):
            hash_obj = self.calculate_image_hash(file_info.path)
            if hash_obj:
                hash_dict[file_info.path] = str(hash_obj)

            if progress_callback:
                progress_callback(i + 1, total)

        # 查找相似的图片
        return self._find_similar_files(hash_dict)

    def find_similar_videos(self, files: List[FileInfo],
                           progress_callback: Optional[Callable[[int, int], None]] = None) -> List[SimilarGroup]:
        """
        在视频文件中查找相似的文件

        Args:
            files: 文件信息列表
            progress_callback: 进度回调 (current, total)

        Returns:
            相似文件组列表
        """
        if not HAS_PILLOW or not HAS_OPENCV:
            self.log.error("请安装 Pillow、imagehash 和 opencv-python 库以使用相似视频检测功能")
            return []

        # 筛选视频文件
        video_files = [f for f in files if Path(f.path).suffix.lower() in self.VIDEO_EXTENSIONS]

        if len(video_files) < 2:
            return []

        # 计算所有视频的哈希
        hash_dict: Dict[str, str] = {}
        total = len(video_files)

        for i, file_info in enumerate(video_files):
            hash_value = self.calculate_video_keyframe_hash(file_info.path)
            if hash_value:
                hash_dict[file_info.path] = hash_value

            if progress_callback:
                progress_callback(i + 1, total)

        # 查找相似的视频
        return self._find_similar_files(hash_dict)

    def find_similar_files(self, files: List[FileInfo],
                          progress_callback: Optional[Callable[[int, int], None]] = None) -> Tuple[List[SimilarGroup], List[SimilarGroup]]:
        """
        同时查找相似的图片和视频文件

        Args:
            files: 文件信息列表
            progress_callback: 进度回调 (current, total)

        Returns:
            (相似图片组, 相似视频组)
        """
        # 分离图片和视频
        image_files = [f for f in files if Path(f.path).suffix.lower() in self.IMAGE_EXTENSIONS]
        video_files = [f for f in files if Path(f.path).suffix.lower() in self.VIDEO_EXTENSIONS]

        # 查找相似的图片
        similar_images = self.find_similar_images(image_files, progress_callback)

        # 查找相似的视频
        similar_videos = self.find_similar_videos(video_files, progress_callback)

        return similar_images, similar_videos

    def _find_similar_files(self, hash_dict: Dict[str, str]) -> List[SimilarGroup]:
        """
        根据哈希字典查找相似的文件

        Args:
            hash_dict: 文件路径到哈希值的映射

        Returns:
            相似文件组列表
        """
        if len(hash_dict) < 2:
            return []

        similar_groups = []
        processed = set()

        for file1 in hash_dict:
            if file1 in processed:
                continue

            similar_files = []
            hash1 = hash_dict[file1]

            for file2 in hash_dict:
                if file1 == file2 or file2 in processed:
                    continue

                hash2 = hash_dict[file2]
                similarity = self.calculate_similarity(hash1, hash2)

                if similarity >= self.threshold:
                    similar_files.append(SimilarFile(
                        file_path=file2,
                        similarity=similarity,
                        hash_value=hash2
                    ))

            # 如果找到相似的文件，创建一个组
            if similar_files:
                similar_files.sort(key=lambda x: x.similarity, reverse=True)
                group = SimilarGroup(
                    reference_file=file1,
                    similar_files=similar_files,
                    method=self.method
                )
                similar_groups.append(group)

                # 标记所有相似文件为已处理
                processed.add(file1)
                for sf in similar_files:
                    processed.add(sf.file_path)

        return similar_groups

    def is_image_file(self, file_path: str) -> bool:
        """判断是否为图片文件"""
        return Path(file_path).suffix.lower() in self.IMAGE_EXTENSIONS

    def is_video_file(self, file_path: str) -> bool:
        """判断是否为视频文件"""
        return Path(file_path).suffix.lower() in self.VIDEO_EXTENSIONS
