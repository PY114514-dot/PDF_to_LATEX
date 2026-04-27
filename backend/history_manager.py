#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
历史记录管理模块
- 保存转换历史
- 清理旧文件
- 只保留最近20条记录
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

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

# 全局历史管理器实例
history_manager = HistoryManager(max_records=20)
