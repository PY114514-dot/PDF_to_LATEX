#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
论文结构知识图谱分析模块
从 LaTeX 文档中提取论文的逻辑结构：定理、引理、证明及其依赖关系
输出可视化的知识骨架图
"""

import re
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


class TheoremType(Enum):
    """定理类型枚举"""
    LEMMA = "lemma"
    THEOREM = "theorem"
    PROPOSITION = "proposition"
    COROLLARY = "corollary"
    CLAIM = "claim"
    FACT = "fact"
    OBSERVATION = "observation"
    DEFINITION = "definition"
    PROOF = "proof"
    EXAMPLE = "example"
    REMARK = "remark"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, s: str) -> 'TheoremType':
        """从字符串转换为 TheoremType"""
        s_lower = s.lower().strip()
        mapping = {
            'lemma': cls.LEMMA,
            'theorem': cls.THEOREM,
            'proposition': cls.PROPOSITION,
            'corollary': cls.COROLLARY,
            'claim': cls.CLAIM,
            'fact': cls.FACT,
            'observation': cls.OBSERVATION,
            'definition': cls.DEFINITION,
            'proof': cls.PROOF,
            'example': cls.EXAMPLE,
            'remark': cls.REMARK,
        }
        return mapping.get(s_lower, cls.UNKNOWN)

    def is_proof_block(self) -> bool:
        """是否是证明块"""
        return self == TheoremType.PROOF

    def is_theorem_like(self) -> bool:
        """是否是定理类结构（需要被引用的）"""
        return self in {
            TheoremType.LEMMA,
            TheoremType.THEOREM,
            TheoremType.PROPOSITION,
            TheoremType.COROLLARY,
            TheoremType.CLAIM,
            TheoremType.FACT,
            TheoremType.OBSERVATION,
        }


@dataclass
class TheoremBlock:
    """定理块"""
    id: str  # 如 "thm:main", "lem:2.1"
    type: TheoremType
    label: str  # 用户可见的标签，如 "Lemma 2.1"
    title: Optional[str]  # 标题（如果有）
    content: str  # 完整内容
    content_preview: str  # 内容预览（用于tooltip）
    line_number: int  # 在文档中的行号
    page_number: Optional[int]  # 页码（如果知道）
    dependencies: List[str] = field(default_factory=list)  # 依赖的定理ID列表
    referenced_by: List[str] = field(default_factory=list)  # 引用此定理的ID列表
    level: int = 0  # 在依赖图中的层级（0为基础层）

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'type': self.type.value,
            'label': self.label,
            'title': self.title,
            'content_preview': self.content_preview[:200] + '...' if len(self.content_preview) > 200 else self.content_preview,
            'line_number': self.line_number,
            'page_number': self.page_number,
            'dependencies': self.dependencies,
            'referenced_by': self.referenced_by,
            'level': self.level
        }


@dataclass
class KnowledgeGraph:
    """知识图谱"""
    theorems: Dict[str, TheoremBlock] = field(default_factory=dict)
    sections: List[Dict[str, Any]] = field(default_factory=list)  # 章节结构
    references: Dict[str, str] = field(default_factory=dict)  # label -> id 映射
    orphan_refs: List[str] = field(default_factory=list)  # 未找到对应定理的引用

    def to_dict(self) -> Dict[str, Any]:
        """转换为可序列化的字典"""
        return {
            'nodes': [thm.to_dict() for thm in self.theorems.values()],
            'edges': self._build_edges(),
            'sections': self.sections,
            'statistics': self._build_statistics(),
            'orphan_refs': self.orphan_refs
        }

    def _build_edges(self) -> List[Dict[str, str]]:
        """构建边列表（用于可视化）"""
        edges = []
        seen = set()

        for thm_id, thm in self.theorems.items():
            for dep_id in thm.dependencies:
                edge_key = f"{dep_id}->{thm_id}"
                if edge_key not in seen:
                    edges.append({
                        'source': dep_id,
                        'target': thm_id,
                        'source_label': self.theorems[dep_id].label if dep_id in self.theorems else dep_id,
                        'target_label': thm.label
                    })
                    seen.add(edge_key)

        return edges

    def _build_statistics(self) -> Dict[str, int]:
        """构建统计信息"""
        stats = {
            'total_theorems': 0,
            'by_type': defaultdict(int),
            'max_depth': 0,
            'total_references': 0
        }

        for thm in self.theorems.values():
            stats['total_theorems'] += 1
            stats['by_type'][thm.type.value] += 1
            stats['max_depth'] = max(stats['max_depth'], thm.level)
            stats['total_references'] += len(thm.dependencies)

        stats['by_type'] = dict(stats['by_type'])
        return stats

    def get_theorem_chain(self, thm_id: str) -> List[str]:
        """获取定理的完整依赖链"""
        chain = []
        visited = set()

        def dfs(node_id: str):
            if node_id in visited:
                return
            visited.add(node_id)
            if node_id in self.theorems:
                chain.append(node_id)
                for dep in self.theorems[node_id].dependencies:
                    dfs(dep)

        dfs(thm_id)
        return chain


class KnowledgeGraphAnalyzer:
    """知识图谱分析器"""

    # 定理环境的正则模式
    THEOREM_PATTERNS = [
        # \begin{xxx}[标题] 或 \begin{xxx}
        re.compile(
            r'\\begin\{(' + '|'.join([
                'lemma', 'theorem', 'proposition', 'corollary',
                'claim', 'fact', 'observation', 'definition',
                'proof', 'example', 'remark', 'exercise', 'problem', 'solution'
            ]) + r')\*?\}(?:\[([^\]]+)\])?',
            re.IGNORECASE
        ),
        # \newtheorem{xxx}{...} 或 \newtheorem{xxx}[yyy]{...}
        re.compile(r'\\newtheorem\{(\w+)\}(?:\[[^\]]+\])?\{([^}]+)\}', re.IGNORECASE),
        # 简单命令形式：\lemma 2.1 或 \theorem{2.1}
        re.compile(r'\\(lemma|theorem|proposition|corollary|claim|fact)\s+\{?([^}\s]+)\}?', re.IGNORECASE),
    ]

    # 引用模式
    REF_PATTERN = re.compile(r'\\ref\{([^}]+)\}')
    LABEL_PATTERN = re.compile(r'\\label\{([^}]+)\}')

    # 章节模式
    SECTION_PATTERNS = [
        re.compile(r'\\(section|subsection|subsubsection|paragraph)\{([^}]+)\}', re.IGNORECASE),
    ]

    def __init__(self):
        self.graph = KnowledgeGraph()

    def analyze(self, latex_content: str, page_boundaries: Optional[List[int]] = None) -> KnowledgeGraph:
        """
        分析 LaTeX 内容，构建知识图谱

        Args:
            latex_content: LaTeX 文档内容
            page_boundaries: 每页起始行号列表（用于估算页码）

        Returns:
            KnowledgeGraph 对象
        """
        self.graph = KnowledgeGraph()

        lines = latex_content.split('\n')
        self.graph.sections = self._extract_sections(lines)

        # 第一次扫描：提取所有 \label 和 \ref
        self._extract_labels_and_refs(lines)

        # 第二次扫描：提取定理块
        self._extract_theorem_blocks(lines)

        # 构建依赖关系
        self._build_dependencies()

        # 计算层级
        self._calculate_levels()

        return self.graph

    def _extract_labels_and_refs(self, lines: List[str]) -> None:
        """提取所有 label 和 ref"""
        for line_num, line in enumerate(lines, 1):
            # 提取 \label
            for match in self.LABEL_PATTERN.finditer(line):
                label = match.group(1)
                # 跳过临时label（用于页面布局的）
                if not label.startswith('tmp:'):
                    self.graph.references[label] = ''  # 先置空，后面填充

            # 提取 \ref
            for match in self.REF_PATTERN.finditer(line):
                ref = match.group(1)
                if ref not in self.graph.references:
                    self.graph.orphan_refs.append(ref)

    def _extract_theorem_blocks(self, lines: List[str]) -> None:
        """提取所有定理块"""
        current_theorem: Optional[TheoremBlock] = None
        theorem_content: List[str] = []
        in_environment = False
        current_env_type = ""
        brace_count = 0

        for line_num, line in enumerate(lines, 1):
            # 跳过注释行
            if line.strip().startswith('%'):
                continue

            # 检查是否进入定理环境
            env_match = re.search(
                r'\\begin\{(' + '|'.join([
                    'lemma', 'theorem', 'proposition', 'corollary',
                    'claim', 'fact', 'observation', 'definition',
                    'proof', 'example', 'remark', 'exercise', 'problem', 'solution'
                ]) + r')\*?\}',
                line,
                re.IGNORECASE
            )

            if env_match:
                env_name = env_match.group(1).lower()
                current_env_type = env_name
                in_environment = True

                # 提取标题（如果有）
                title_match = re.search(r'\\begin\{' + env_name + r'\*?\}\[([^\]]+)\]', line, re.IGNORECASE)
                title = title_match.group(1) if title_match else None

                # 生成 ID
                thm_id = self._generate_theorem_id(env_name, line_num)

                current_theorem = TheoremBlock(
                    id=thm_id,
                    type=TheoremType.from_string(env_name),
                    label=f"{env_name.capitalize()} {len([t for t in self.graph.theorems.values() if t.type.value == env_name]) + 1}",
                    title=title,
                    content="",
                    content_preview="",
                    line_number=line_num
                )
                theorem_content = []
                continue

            # 检查是否离开定理环境
            if in_environment and re.search(r'\\end\{' + current_env_type + r'\*?\}', line, re.IGNORECASE):
                in_environment = False

                if current_theorem:
                    content = '\n'.join(theorem_content)
                    current_theorem.content = content
                    current_theorem.content_preview = content
                    self.graph.theorems[current_theorem.id] = current_theorem

                    # 更新 references 映射
                    for match in self.REF_PATTERN.finditer(content):
                        ref = match.group(1)
                        self.graph.references[ref] = current_theorem.id

                current_theorem = None
                theorem_content = []
                continue

            # 如果在定理环境内，收集内容
            if in_environment and current_theorem:
                theorem_content.append(line)

                # 提取 label（可能在环境内的第一行）
                for match in self.LABEL_PATTERN.finditer(line):
                    label = match.group(1)
                    if not label.startswith('tmp:'):
                        current_theorem.id = label
                        self.graph.references[label] = label

        # 处理没有明确 \end 的定理（环境不完整的情况）
        if current_theorem and current_theorem.content:
            self.graph.theorems[current_theorem.id] = current_theorem

    def _generate_theorem_id(self, env_type: str, line_num: int) -> str:
        """生成定理的唯一ID"""
        count = len([t for t in self.graph.theorems.values() if t.type.value == env_type]) + 1
        return f"{env_type}:{count}"

    def _build_dependencies(self) -> None:
        """构建定理间的依赖关系"""
        for thm_id, thm in self.graph.theorems.items():
            deps = []
            for match in self.REF_PATTERN.finditer(thm.content):
                ref = match.group(1)
                # 查找引用对应的定理
                target_id = self.graph.references.get(ref)
                if target_id and target_id in self.graph.theorems:
                    deps.append(target_id)

                    # 更新被引用者的 referenced_by
                    if thm_id not in self.graph.theorems[target_id].referenced_by:
                        self.graph.theorems[target_id].referenced_by.append(thm_id)

            thm.dependencies = deps

    def _calculate_levels(self) -> None:
        """计算每个定理在依赖图中的层级"""
        # 使用拓扑排序计算层级
        # 基础层：没有依赖的定理
        # 每上升一层：依赖于更低层级的定理

        def calculate_level(thm_id: str, visited: Set[str], memo: Dict[str, int]) -> int:
            if thm_id in memo:
                return memo[thm_id]

            if thm_id not in self.graph.theorems:
                return 0

            thm = self.graph.theorems[thm_id]
            if not thm.dependencies:
                memo[thm_id] = 0
                return 0

            max_dep_level = 0
            for dep_id in thm.dependencies:
                if dep_id in self.graph.theorems:
                    dep_level = calculate_level(dep_id, visited, memo)
                    max_dep_level = max(max_dep_level, dep_level)

            memo[thm_id] = max_dep_level + 1
            return max_dep_level + 1

        memo: Dict[str, int] = {}
        for thm_id in self.graph.theorems:
            self.graph.theorems[thm_id].level = calculate_level(thm_id, set(), memo)

    def _extract_sections(self, lines: List[str]) -> List[Dict[str, Any]]:
        """提取章节结构"""
        sections = []

        for line_num, line in enumerate(lines, 1):
            for pattern in self.SECTION_PATTERNS:
                match = pattern.search(line)
                if match:
                    sec_type = match.group(1).lower()
                    title = match.group(2)
                    level = {
                        'section': 1,
                        'subsection': 2,
                        'subsubsection': 3,
                        'paragraph': 4
                    }.get(sec_type, 1)

                    sections.append({
                        'type': sec_type,
                        'title': title,
                        'line_number': line_num,
                        'level': level
                    })
                    break

        return sections

    def get_core_theorems(self, top_n: int = 5) -> List[TheoremBlock]:
        """获取核心定理（被引用次数最多的）"""
        sorted_theorems = sorted(
            self.graph.theorems.values(),
            key=lambda t: len(t.referenced_by),
            reverse=True
        )
        return sorted_theorems[:top_n]

    def get_dependency_tree(self, thm_id: str) -> Dict[str, Any]:
        """获取某个定理的依赖树"""
        if thm_id not in self.graph.theorems:
            return {}

        thm = self.graph.theorems[thm_id]

        def build_tree(node_id: str) -> Dict[str, Any]:
            if node_id not in self.graph.theorems:
                return {}
            node = self.graph.theorems[node_id]
            return {
                'id': node.id,
                'label': node.label,
                'type': node.type.value,
                'level': node.level,
                'dependencies': [build_tree(dep_id) for dep_id in node.dependencies if dep_id in self.graph.theorems]
            }

        return build_tree(thm_id)


# 快捷函数
def analyze_paper_structure(latex_content: str) -> Dict[str, Any]:
    """分析论文结构，返回知识图谱"""
    analyzer = KnowledgeGraphAnalyzer()
    graph = analyzer.analyze(latex_content)
    return graph.to_dict()


def get_core_theorems(latex_content: str, top_n: int = 5) -> List[Dict[str, Any]]:
    """获取核心定理列表"""
    analyzer = KnowledgeGraphAnalyzer()
    analyzer.analyze(latex_content)
    return [thm.to_dict() for thm in analyzer.get_core_theorems(top_n)]