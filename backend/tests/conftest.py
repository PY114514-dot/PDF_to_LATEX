#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pytest 配置和 fixtures
"""

import sys
import os
from pathlib import Path

# 添加 backend 目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# 设置测试环境变量
os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('DEEPSEEK_API_KEY', 'test-key')
os.environ.setdefault('DOUBAO_API_KEY', 'test-key')
os.environ.setdefault('OPENAI_API_KEY', 'test-key')