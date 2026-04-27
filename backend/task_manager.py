#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务持久化管理器
- 保存异步任务状态到本地 JSON
- 支持任务查询和恢复
"""

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class TaskManager:
    def __init__(self, store_file: str = "task_store.json"):
        self.store_file = Path(store_file)
        self._lock = threading.Lock()
        self.tasks: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if not self.store_file.exists():
            return {}
        try:
            with open(self.store_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            print(f"[TaskManager] 加载任务存储失败: {e}")
        return {}

    def _save(self):
        try:
            with open(self.store_file, "w", encoding="utf-8") as f:
                json.dump(self.tasks, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[TaskManager] 保存任务存储失败: {e}")

    def create_task(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now().isoformat()
        task = {
            "task_id": task_id,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "payload": payload,
            "progress": {
                "current": 0,
                "total": 100,
                "percent": 0,
                "message": "任务已创建"
            },
            "result": None,
            "error": None
        }
        with self._lock:
            self.tasks[task_id] = task
            self._save()
        return task

    def update_task(self, task_id: str, **fields) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return None
            task.update(fields)
            task["updated_at"] = datetime.now().isoformat()
            self._save()
            return task

    def update_progress(
        self,
        task_id: str,
        status: str,
        current: int,
        total: int,
        message: str,
        tokens: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return None
            percent = int((current / total) * 100) if total > 0 else 0
            task["status"] = status
            task["progress"] = {
                "current": current,
                "total": total,
                "percent": percent,
                "message": message
            }
            if tokens:
                task["tokens"] = tokens
            task["updated_at"] = datetime.now().isoformat()
            self._save()
            return task

    def set_completed(self, task_id: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.update_task(task_id, status="completed", result=result, error=None)

    def set_failed(self, task_id: str, error: str) -> Optional[Dict[str, Any]]:
        return self.update_task(task_id, status="failed", error=error)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return None
            # 避免直接返回内部可变引用
            return json.loads(json.dumps(task))

    def list_tasks(self, limit: int = 50) -> list:
        """按更新时间倒序返回任务列表。"""
        with self._lock:
            all_tasks = list(self.tasks.values())
            all_tasks.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            return json.loads(json.dumps(all_tasks[:max(1, limit)]))


# 全局任务管理器
async_task_manager = TaskManager()
