import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from task_manager import TaskManager


class TestTaskManager(unittest.TestCase):
    def test_persists_tasks_with_atomic_target_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = Path(temp_dir) / 'tasks.json'
            manager = TaskManager(str(store))
            manager.create_task('task-1', {'pdf_path': 'source.pdf'})

            assert store.exists()
            assert not store.with_suffix('.json.tmp').exists()
            assert json.loads(store.read_text(encoding='utf-8'))['task-1']['status'] == 'queued'

    def test_prunes_expired_terminal_task_on_load(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = Path(temp_dir) / 'tasks.json'
            store.write_text(json.dumps({
                'old-task': {
                    'task_id': 'old-task',
                    'status': 'completed',
                    'updated_at': (datetime.now() - timedelta(days=30)).isoformat(),
                }
            }), encoding='utf-8')

            manager = TaskManager(str(store))
            assert manager.get_task('old-task') is None

    def test_recovers_from_corrupt_store(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = Path(temp_dir) / 'tasks.json'
            store.write_text('{invalid json', encoding='utf-8')

            manager = TaskManager(str(store))
            assert manager.list_tasks() == []
            assert list(Path(temp_dir).glob('tasks.corrupt-*.json'))

    def test_marks_interrupted_task_as_resumable_on_load(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = Path(temp_dir) / 'tasks.json'
            store.write_text(json.dumps({
                'interrupted': {
                    'task_id': 'interrupted',
                    'status': 'converting',
                    'updated_at': datetime.now().isoformat(),
                }
            }), encoding='utf-8')

            manager = TaskManager(str(store))
            task = manager.get_task('interrupted')
            assert task['status'] == 'failed'
            assert '服务重启' in task['error']
