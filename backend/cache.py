"""
转换结果缓存模块
基于文件哈希的简单缓存机制
"""

import os
import json
import hashlib
import time
from pathlib import Path
from typing import Optional, Dict, Any
from config import settings


class ConversionCache:
    """PDF/Word转换结果缓存"""

    def __init__(self, cache_dir: str = None, expiry_seconds: int = None):
        self.cache_dir = Path(cache_dir or settings.CACHE_DIR)
        self.expiry_seconds = expiry_seconds or settings.CACHE_EXPIRY_SECONDS
        self.enabled = settings.ENABLE_CACHE

        # 确保缓存目录存在
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_hash(self, file_path: str) -> str:
        """计算文件的MD5哈希"""
        hash_md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _get_cache_key(self, file_path: str, pages: list = None, translate: bool = False) -> str:
        """生成缓存键"""
        file_hash = self._get_file_hash(file_path)
        pages_str = f"_p{'-'.join(map(str, sorted(pages)))}" if pages else ""
        translate_str = "_tr" if translate else ""
        return f"{file_hash}{pages_str}{translate_str}"

    def _get_cache_path(self, cache_key: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{cache_key}.json"

    def get(self, file_path: str, pages: list = None, translate: bool = False) -> Optional[Dict[str, Any]]:
        """
        获取缓存的转换结果

        Args:
            file_path: 源文件路径
            pages: 页码列表
            translate: 是否翻译

        Returns:
            缓存结果或None（无缓存或已过期）
        """
        if not self.enabled:
            return None

        cache_key = self._get_cache_key(file_path, pages, translate)
        cache_path = self._get_cache_path(cache_key)

        if not cache_path.exists():
            return None

        # 检查是否过期
        mtime = cache_path.stat().st_mtime
        if time.time() - mtime > self.expiry_seconds:
            # 过期，删除
            try:
                cache_path.unlink()
            except:
                pass
            return None

        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def set(self, file_path: str, pages: list, translate: bool, result: Dict[str, Any]) -> bool:
        """
        保存转换结果到缓存

        Args:
            file_path: 源文件路径
            pages: 页码列表
            translate: 是否翻译
            result: 转换结果

        Returns:
            是否保存成功
        """
        if not self.enabled:
            return False

        cache_key = self._get_cache_key(file_path, pages, translate)
        cache_path = self._get_cache_path(cache_key)

        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def clear(self, file_path: str = None) -> int:
        """
        清除缓存

        Args:
            file_path: 如果提供，只清除该文件的缓存；否则清除所有

        Returns:
            清除的缓存数量
        """
        if not self.enabled:
            return 0

        count = 0
        if file_path:
            cache_key = self._get_cache_key(file_path)
            cache_path = self._get_cache_path(cache_key)
            if cache_path.exists():
                try:
                    cache_path.unlink()
                    count = 1
                except:
                    pass
        else:
            # 清除所有过期缓存
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    mtime = cache_file.stat().st_mtime
                    if time.time() - mtime > self.expiry_seconds:
                        cache_file.unlink()
                        count += 1
                except:
                    pass

        return count

    def get_cache_info(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        if not self.enabled:
            return {'enabled': False}

        cache_files = list(self.cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in cache_files)

        expired = 0
        for cache_file in cache_files:
            try:
                if time.time() - cache_file.stat().st_mtime > self.expiry_seconds:
                    expired += 1
            except:
                pass

        return {
            'enabled': True,
            'count': len(cache_files),
            'total_size_bytes': total_size,
            'expired': expired,
            'cache_dir': str(self.cache_dir)
        }


# 全局缓存实例
_cache: Optional[ConversionCache] = None


def get_cache() -> ConversionCache:
    """获取全局缓存实例"""
    global _cache
    if _cache is None:
        _cache = ConversionCache()
    return _cache