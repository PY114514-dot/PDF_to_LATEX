#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
历史记录管理模块
- 保存转换历史
- 清理旧文件
- 只保留最近20条记录
- 用户偏好学习（术语映射、模板偏好）
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, asdict


@dataclass
class TerminologyMapping:
    """术语映射条目"""
    source: str  # 英文术语
    target: str  # 用户偏好的中文翻译
    confidence: int  # 出现次数（置信度）
    last_updated: str  # 最后更新时间


class UserPreferences:
    """用户偏好数据"""

    def __init__(self):
        # 术语映射：英文 -> 用户偏好中文
        self.terminology: Dict[str, str] = {}
        # 模板偏好：模板名 -> 使用次数
        self.template_usage: Dict[str, int] = defaultdict(int)
        # 模型偏好：模型名 -> 使用次数
        self.model_usage: Dict[str, int] = defaultdict(int)
        # 翻译偏好：是否默认翻译
        self.default_translate: bool = False
        # 质量模式偏好
        self.quality_mode: str = 'standard'
        # 常用页面范围
        self.common_page_ranges: List[str] = []
        # 学习到的常见修复模式
        self.fix_patterns: List[Dict[str, str]] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            'terminology': self.terminology,
            'template_usage': dict(self.template_usage),
            'model_usage': dict(self.model_usage),
            'default_translate': self.default_translate,
            'quality_mode': self.quality_mode,
            'common_page_ranges': self.common_page_ranges,
            'fix_patterns': self.fix_patterns
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserPreferences':
        pref = cls()
        if not data:
            return pref

        pref.terminology = data.get('terminology', {})
        pref.template_usage = defaultdict(int, data.get('template_usage', {}))
        pref.model_usage = defaultdict(int, data.get('model_usage', {}))
        pref.default_translate = data.get('default_translate', False)
        pref.quality_mode = data.get('quality_mode', 'standard')
        pref.common_page_ranges = data.get('common_page_ranges', [])
        pref.fix_patterns = data.get('fix_patterns', [])
        return pref


class HistoryManager:
    def __init__(self, history_file: str = "history.json", max_records: int = 20):
        self.history_file = Path(history_file)
        self.max_records = max_records
        self.history = self._load_history()
    
    def _load_history(self) -> List[Dict[str, Any]]:
        """加载历史记录"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载历史记录失败: {e}")
                return []
        return []
    
    def _save_history(self):
        """保存历史记录"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存历史记录失败: {e}")
    
    def add_record(self, record: Dict[str, Any]):
        """
        添加一条记录
        
        Args:
            record: 包含转换信息的字典
                - filename: 文件名
                - model: 使用的模型
                - translated: 是否翻译
                - pages: 页码范围
                - output_file: 输出文件路径
                - upload_file: 上传文件路径（可选，用于清理）
                - stats: 统计信息
                - timestamp: 时间戳
        """
        # 添加时间戳
        if 'timestamp' not in record:
            record['timestamp'] = datetime.now().isoformat()
        
        # 添加到历史记录开头
        self.history.insert(0, record)
        
        # 只保留最近的记录
        if len(self.history) > self.max_records:
            # 删除超出的记录及其文件
            old_records = self.history[self.max_records:]
            for old_record in old_records:
                self._delete_record_files(old_record)
            
            self.history = self.history[:self.max_records]
        
        self._save_history()
    
    def add_entry(self, entry: Dict[str, Any]):
        """添加记录的别名方法（兼容性）"""
        return self.add_record(entry)
    
    def _delete_record_files(self, record: Dict[str, Any]):
        """删除记录关联的文件"""
        try:
            # 删除输出文件
            if 'output_file' in record:
                output_path = Path(record['output_file'])
                if output_path.exists():
                    output_path.unlink()
                    print(f"已删除旧文件: {output_path}")
            
            # 删除上传文件
            if 'upload_file' in record:
                upload_path = Path(record['upload_file'])
                if upload_path.exists():
                    upload_path.unlink()
                    print(f"已删除旧文件: {upload_path}")
        except Exception as e:
            print(f"删除文件失败: {e}")
    
    def get_history(self, limit: int = None, offset: int = 0) -> List[Dict[str, Any]]:
        """
        获取历史记录
        
        Args:
            limit: 返回的记录数量限制
            offset: 起始偏移
        
        Returns:
            历史记录列表
        """
        start = max(0, offset)
        if limit is None:
            return self.history[start:]
        return self.history[start:start + limit]
    
    def get_record(self, index: int) -> Dict[str, Any]:
        """获取指定索引的记录"""
        if 0 <= index < len(self.history):
            return self.history[index]
        return None

    def delete_record(self, index: int) -> bool:
        """删除指定索引的记录并清理文件"""
        if 0 <= index < len(self.history):
            record = self.history.pop(index)
            self._delete_record_files(record)
            self._save_history()
            return True
        return False
    
    def clear_history(self):
        """清空所有历史记录"""
        for record in self.history:
            self._delete_record_files(record)
        self.history = []
        self._save_history()
    
    def clean_orphan_files(self, upload_dir: Path, output_dir: Path):
        """
        清理孤立文件（不在历史记录中的文件）
        
        Args:
            upload_dir: 上传目录
            output_dir: 输出目录
        """
        # 获取历史记录中的所有文件
        tracked_files = set()
        for record in self.history:
            if 'output_file' in record:
                tracked_files.add(Path(record['output_file']).name)
            if 'upload_file' in record:
                tracked_files.add(Path(record['upload_file']).name)
        
        # 清理上传目录
        if upload_dir.exists():
            for file in upload_dir.iterdir():
                if file.is_file() and file.name not in tracked_files:
                    try:
                        file.unlink()
                        print(f"清理孤立文件: {file}")
                    except Exception as e:
                        print(f"清理文件失败 {file}: {e}")
        
        # 清理输出目录
        if output_dir.exists():
            for file in output_dir.iterdir():
                if file.is_file() and file.name not in tracked_files:
                    try:
                        file.unlink()
                        print(f"清理孤立文件: {file}")
                    except Exception as e:
                        print(f"清理文件失败 {file}: {e}")

# ==================== 用户偏好学习管理器 ====================

class PreferenceLearner:
    """
    用户偏好学习器
    从转换历史中学习用户的术语偏好、模板偏好等
    """

    def __init__(self, preferences_file: str = "user_preferences.json"):
        self.preferences_file = Path(preferences_file)
        self.preferences = self._load_preferences()

    def _load_preferences(self) -> UserPreferences:
        """加载用户偏好"""
        if self.preferences_file.exists():
            try:
                with open(self.preferences_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return UserPreferences.from_dict(data)
            except Exception as e:
                print(f"加载用户偏好失败: {e}")
                return UserPreferences()
        return UserPreferences()

    def _save_preferences(self):
        """保存用户偏好"""
        try:
            with open(self.preferences_file, 'w', encoding='utf-8') as f:
                json.dump(self.preferences.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存用户偏好失败: {e}")

    def learn_from_record(self, record: Dict[str, Any]) -> None:
        """
        从一条转换记录中学习用户偏好

        Args:
            record: 转换记录，包含:
                - model: 使用的模型
                - template: 模板名称
                - translated: 是否翻译
                - quality_mode: 质量模式
                - pages: 页码范围
        """
        if not record:
            return

        # 学习模型偏好
        model = record.get('model')
        if model:
            self.preferences.model_usage[model] += 1

        # 学习模板偏好
        template = record.get('template_name') or record.get('template')
        if template:
            self.preferences.template_usage[template] += 1

        # 学习翻译偏好
        translated = record.get('translated')
        if isinstance(translated, bool):
            # 如果用户多次选择翻译，累计更新
            if translated:
                self.preferences.default_translate = True

        # 学习质量模式偏好
        quality = record.get('quality_mode')
        if quality:
            self.preferences.quality_mode = quality

        # 学习常见页面范围
        pages = record.get('pages')
        if pages and pages != 'all':
            if pages not in self.preferences.common_page_ranges:
                self.preferences.common_page_ranges.append(pages)
                # 最多保留5个常用范围
                if len(self.preferences.common_page_ranges) > 5:
                    self.preferences.common_page_ranges = self.preferences.common_page_ranges[-5:]

        self._save_preferences()

    def learn_terminology(self, source_term: str, target_term: str) -> None:
        """
        学习用户的术语偏好

        Args:
            source_term: 原文（英文）
            target_term: 用户偏好的翻译（中文）
        """
        if not source_term or not target_term:
            return

        source_term = source_term.strip().lower()
        target_term = target_term.strip()

        # 如果已有映射，增加置信度
        if source_term in self.preferences.terminology:
            existing = self.preferences.terminology[source_term]
            # 如果用户多次使用相同的翻译，增加置信度
            if existing == target_term:
                pass  # 相同的翻译，不需要额外操作
            else:
                # 如果用户使用不同的翻译，替换（用户可能改变了偏好）
                self.preferences.terminology[source_term] = target_term
        else:
            self.preferences.terminology[source_term] = target_term

        self._save_preferences()

    def extract_terminology_from_corrections(
        self,
        original_latex: str,
        corrected_latex: str
    ) -> List[Tuple[str, str]]:
        """
        从用户的修改中提取术语映射

        Args:
            original_latex: 原始 LaTeX
            corrected_latex: 用户修改后的 LaTeX

        Returns:
            [(英文术语, 用户翻译), ...]
        """
        mappings = []

        # 提取英文术语（简单实现：查找中英文混合的段落变化）
        # 这是一个启发式方法，实际使用时可能需要更复杂的 NLP

        # 查找被替换的中文术语
        # 模式：可能是 \textbf{中文} 或直接的中文文本
        chinese_pattern = re.compile(r'[一-鿿]+')

        original_chinese = set(chinese_pattern.findall(original_latex))
        corrected_chinese = set(chinese_pattern.findall(corrected_latex))

        # 新增或改变的中文术语可能是用户的偏好
        for chinese in corrected_chinese:
            if chinese not in original_chinese:
                # 这是新增的中文，可能需要关联到某个英文原文
                # 这里简化处理，实际可能需要更复杂的上下文分析
                pass

        return mappings

    def get_terminology_prompt(self) -> str:
        """
        获取术语偏好提示词，用于添加到系统提示词中

        Returns:
            格式化的术语提示词
        """
        if not self.preferences.terminology:
            return ""

        lines = ["用户偏好术语翻译（请优先使用以下翻译）："]
        for source, target in sorted(self.preferences.terminology.items()):
            lines.append(f"  {source} -> {target}")

        return "\n".join(lines)

    def get_template_prompt(self) -> str:
        """
        获取模板偏好提示词

        Returns:
            模板偏好描述
        """
        if not self.preferences.template_usage:
            return ""

        # 找出最常用的模板
        most_used = max(
            self.preferences.template_usage.items(),
            key=lambda x: x[1],
            default=('article', 0)
        )

        if most_used[1] >= 2:  # 至少使用2次才提示
            return f"用户偏好模板：{most_used[0]}（已使用 {most_used[1]} 次）"
        return ""

    def get_preferred_model(self) -> Optional[str]:
        """获取用户最常用的模型"""
        if not self.preferences.model_usage:
            return None

        most_used = max(
            self.preferences.model_usage.items(),
            key=lambda x: x[1],
            default=(None, 0)
        )

        return most_used[0] if most_used[1] >= 2 else None

    def get_all_preferences(self) -> Dict[str, Any]:
        """获取所有偏好设置"""
        return self.preferences.to_dict()

    def update_preference(self, key: str, value: Any) -> bool:
        """
        更新单个偏好设置

        Args:
            key: 偏好键
            value: 偏好值

        Returns:
            是否更新成功
        """
        valid_keys = {
            'default_translate', 'quality_mode',
            'terminology', 'template_usage', 'model_usage'
        }

        if key not in valid_keys:
            return False

        if key == 'default_translate':
            self.preferences.default_translate = bool(value)
        elif key == 'quality_mode':
            if value in ('standard', 'high'):
                self.preferences.quality_mode = value
            else:
                return False
        elif key in ('terminology', 'template_usage', 'model_usage'):
            if isinstance(value, dict):
                setattr(self.preferences, key, value)

        self._save_preferences()
        return True

    def reset_preferences(self) -> None:
        """重置所有偏好"""
        self.preferences = UserPreferences()
        self._save_preferences()


# 全局偏好学习器实例
preference_learner = PreferenceLearner()


# ==================== 全局实例 ====================

# 全局历史管理器实例
history_manager = HistoryManager(max_records=20)
