#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务持久化管理器
- 保存异步任务状态到本地 JSON
- 支持任务查询和恢复
"""

import json
import logging
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from config import settings

logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self, store_file: str = "task_store.json"):
        self.store_file = Path(store_file)
        self._lock = threading.Lock()
        self.tasks: Dict[str, Dict[str, Any]] = self._load()
        interrupted = self._mark_interrupted_tasks()
        pruned = self._prune_locked()
        if interrupted or pruned:
            self._save()

    def _mark_interrupted_tasks(self) -> bool:
        """Make tasks left mid-flight by a prior process explicitly resumable."""
        active = {"processing", "extracting", "converting", "translating"}
        changed = False
        for task in self.tasks.values():
            if task.get("status") not in active:
                continue
            task["status"] = "failed"
            task["error"] = "服务重启导致任务中断，请点击重试以继续。"
            task["updated_at"] = datetime.now().isoformat()
            changed = True
        return changed

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if not self.store_file.exists():
            return {}
        try:
            with open(self.store_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except (OSError, json.JSONDecodeError) as exc:
            backup = self.store_file.with_name(
                f"{self.store_file.stem}.corrupt-{datetime.now():%Y%m%d%H%M%S}.json"
            )
            try:
                self.store_file.replace(backup)
                logger.warning("Task store was corrupt and moved to %s: %s", backup, exc)
            except OSError:
                logger.warning("Failed to read task store %s: %s", self.store_file, exc)
        return {}

    def _save(self):
        try:
            temp_file = self.store_file.with_suffix(self.store_file.suffix + ".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.tasks, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, self.store_file)
        except OSError as exc:
            logger.exception("Failed to persist task store %s: %s", self.store_file, exc)

    def _prune_locked(self) -> bool:
        """Remove expired terminal tasks and cap retained task history."""
        now = datetime.now()
        ttl = timedelta(seconds=max(1, settings.TASK_STORE_TTL_SECONDS))
        terminal = {"completed", "failed", "cancelled"}
        removed = False
        for task_id, task in list(self.tasks.items()):
            if task.get("status") not in terminal:
                continue
            try:
                updated_at = datetime.fromisoformat(task.get("updated_at", ""))
            except (TypeError, ValueError):
                updated_at = datetime.min
            if now - updated_at > ttl:
                self.tasks.pop(task_id, None)
                removed = True

        max_tasks = max(1, settings.MAX_PERSISTED_TASKS)
        if len(self.tasks) > max_tasks:
            terminal_tasks = sorted(
                (
                    (task.get("updated_at", ""), task_id)
                    for task_id, task in self.tasks.items()
                    if task.get("status") in terminal
                )
            )
            for _, task_id in terminal_tasks[:max(0, len(self.tasks) - max_tasks)]:
                self.tasks.pop(task_id, None)
                removed = True
        return removed

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
            self._prune_locked()
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
            self._prune_locked()
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
            if self._prune_locked():
                self._save()
            all_tasks = list(self.tasks.values())
            all_tasks.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            return json.loads(json.dumps(all_tasks[:max(1, limit)]))


# 全局任务管理器
async_task_manager = TaskManager()
