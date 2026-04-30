#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
论文思维导图生成模块
将知识图谱转换为 Mermaid 格式的思维导图
"""

import json
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum

from knowledge_graph import KnowledgeGraph, TheoremBlock, TheoremType


class MindMapLayout(Enum):
    """思维导图布局"""
    HIERARCHICAL = "hierarchical"  # 层级树状图
    DEPENDENCY = "dependency"      # 依赖关系图
    TIMELINE = "timeline"          # 按出现顺序
    CLASSIFICATION = "classification"  # 按类型分类


class MindMapNode:
    """思维导图节点"""
    def __init__(self, id: str, text: str, node_type: str = "default", parent: Optional[str] = None):
        self.id = id
        self.text = text
        self.node_type = node_type
        self.parent = parent
        self.children: List['MindMapNode'] = []
        self.metadata: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'text': self.text,
            'type': self.node_type,
            'parent': self.parent,
            'children': [c.id for c in self.children],
            'metadata': self.metadata
        }


class MindMapGenerator:
    """
    思维导图生成器
    从知识图谱生成可视化的思维导图
    """

    # 节点颜色配置
    NODE_COLORS = {
        TheoremType.THEOREM: "#e3f2fd",
        TheoremType.LEMMA: "#f3e5f5",
        TheoremType.PROPOSITION: "#e8f5e9",
        TheoremType.COROLLARY: "#fff3e0",
        TheoremType.DEFINITION: "#fce4ec",
        TheoremType.PROOF: "#f5f5f5",
        TheoremType.EXAMPLE: "#e0f7fa",
        TheoremType.REMARK: "#f9f9f9",
        TheoremType.CLAIM: "#e8eaf6",
        TheoremType.FACT: "#f1f8e9",
        TheoremType.OBSERVATION: "#fff8e1",
        TheoremType.UNKNOWN: "#fafafa",
    }

    # 节点类型到形状的映射
    NODE_SHAPES = {
        TheoremType.THEOREM: "roundedBox",
        TheoremType.LEMMA: "roundedBox",
        TheoremType.PROPOSITION: "roundedBox",
        TheoremType.COROLLARY: "roundedBox",
        TheoremType.DEFINITION: "stadium",
        TheoremType.PROOF: "circle",
        TheoremType.EXAMPLE: "circle",
        TheoremType.REMARK: "circle",
        TheoremType.CLAIM: "roundedBox",
        TheoremType.FACT: "roundedBox",
        TheoremType.OBSERVATION: "roundedBox",
        TheoremType.UNKNOWN: "box",
    }

    def __init__(self, knowledge_graph: KnowledgeGraph):
        self.graph = knowledge_graph
        self.nodes: Dict[str, MindMapNode] = {}

    def generate_mermaid(
        self,
        layout: MindMapLayout = MindMapLayout.HIERARCHICAL,
        include_proofs: bool = False,
        max_preview_length: int = 50
    ) -> str:
        """
        生成 Mermaid 格式的思维导图

        Args:
            layout: 布局类型
            include_proofs: 是否包含证明节点
            max_preview_length: 内容预览的最大长度

        Returns:
            Mermaid 格式的思维导图代码
        """
        if layout == MindMapLayout.HIERARCHICAL:
            return self._generate_hierarchical_mermaid(include_proofs, max_preview_length)
        elif layout == MindMapLayout.DEPENDENCY:
            return self._generate_dependency_mermaid(include_proofs, max_preview_length)
        elif layout == MindMapLayout.TIMELINE:
            return self._generate_timeline_mermaid(include_proofs, max_preview_length)
        elif layout == MindMapLayout.CLASSIFICATION:
            return self._generate_classification_mermaid(include_proofs, max_preview_length)
        else:
            return self._generate_hierarchical_mermaid(include_proofs, max_preview_length)

    def _generate_hierarchical_mermaid(
        self,
        include_proofs: bool,
        max_preview_length: int
    ) -> str:
        """生成层级树状思维导图"""
        lines = ["mindmap", "  root(论文结构)"]

        # 按层级组织节点
        levels: Dict[int, List[TheoremBlock]] = {}
        for thm in self.graph.theorems.values():
            if thm.type == TheoremType.PROOF and not include_proofs:
                continue
            level = thm.level
            if level not in levels:
                levels[level] = []
            levels[level].append(thm)

        # 生成节点
        node_map: Dict[str, str] = {}
        for level in sorted(levels.keys()):
            for thm in sorted(levels[level], key=lambda x: x.line_number):
                node_id = self._safe_id(thm.id)
                preview = self._truncate(thm.label, max_preview_length)
                color = self.NODE_COLORS.get(thm.type, "#fafafa")

                if level == 0:
                    lines.append(f"    {node_id}(({preview}))")
                else:
                    parent_id = self._find_parent_id(thm)
                    if parent_id:
                        lines.append(f"      {node_id}(({preview}))")
                    else:
                        lines.append(f"    {node_id}(({preview}))")

                node_map[thm.id] = node_id

        return "\n".join(lines)

    def _generate_dependency_mermaid(
        self,
        include_proofs: bool,
        max_preview_length: int
    ) -> str:
        """生成依赖关系图"""
        lines = ["flowchart LR"]

        # 添加样式
        lines.append("    classDef theorem fill:#e3f2fd,stroke:#1976d2")
        lines.append("    classDef lemma fill:#f3e5f5,stroke:#7b1fa2")
        lines.append("    classDef definition fill:#fce4ec,stroke:#c2185b")
        lines.append("    classDef proof fill:#f5f5f5,stroke:#757575")
        lines.append("    classDef default fill:#fafafa,stroke:#9e9e9e")
        lines.append("")

        # 添加节点和边
        for thm in self.graph.theorems.values():
            if thm.type == TheoremType.PROOF and not include_proofs:
                continue

            node_id = self._safe_id(thm.id)
            preview = self._truncate(thm.label, max_preview_length)
            thm_type = thm.type.value.lower()

            lines.append(f"    {node_id}[\"{preview}\"]")

        # 添加边
        for thm in self.graph.theorems.values():
            if thm.type == TheoremType.PROOF and not include_proofs:
                continue
            node_id = self._safe_id(thm.id)
            for dep_id in thm.dependencies:
                if dep_id in self.graph.theorems:
                    dep_node_id = self._safe_id(dep_id)
                    lines.append(f"    {dep_node_id} --> {node_id}")

        # 添加样式类
        lines.append("")
        for thm in self.graph.theorems.values():
            if thm.type == TheoremType.PROOF and not include_proofs:
                continue
            node_id = self._safe_id(thm.id)
            lines.append(f"    class {node_id} {thm.type.value.lower()}")

        return "\n".join(lines)

    def _generate_timeline_mermaid(
        self,
        include_proofs: bool,
        max_preview_length: int
    ) -> str:
        """生成按出现顺序的时间线思维导图"""
        lines = ["timeline"]
        lines.append("    论文结构")

        # 按行号排序
        sorted_theorems = sorted(
            [t for t in self.graph.theorems.values()
             if not (t.type == TheoremType.PROOF and not include_proofs)],
            key=lambda x: x.line_number
        )

        current_section = 0
        for thm in sorted_theorems:
            preview = self._truncate(thm.label, max_preview_length)
            lines.append(f"        : {preview}")

        return "\n".join(lines)

    def _generate_classification_mermaid(
        self,
        include_proofs: bool,
        max_preview_length: int
    ) -> str:
        """生成分类思维导图"""
        lines = ["mindmap", "  root(论文结构)"]

        # 按类型分组
        by_type: Dict[TheoremType, List[TheoremBlock]] = {}
        for thm in self.graph.theorems.values():
            if thm.type == TheoremType.PROOF and not include_proofs:
                continue
            if thm.type not in by_type:
                by_type[thm.type] = []
            by_type[thm.type].append(thm)

        # 生成类型分支
        for thm_type in sorted(by_type.keys(), key=lambda x: x.value):
            theorems = by_type[thm_type]
            type_label = thm_type.value.capitalize()
            lines.append(f"    {type_label}(({type_label}s))")

            for thm in sorted(theorems, key=lambda x: x.line_number):
                preview = self._truncate(thm.label, max_preview_length)
                node_id = self._safe_id(thm.id)
                lines.append(f"      {node_id}(({preview}))")

        return "\n".join(lines)

    def _safe_id(self, original_id: str) -> str:
        """生成安全的 Mermaid 节点 ID"""
        # 替换特殊字符
        safe = original_id.replace(":", "_").replace(".", "_").replace("-", "_")
        return f"node_{safe}"

    def _truncate(self, text: str, max_length: int) -> str:
        """截断文本"""
        if len(text) <= max_length:
            return text.replace('"', "'").replace("\\", "/")
        return text[:max_length-3].replace('"', "'").replace("\\", "/") + "..."

    def _find_parent_id(self, thm: TheoremBlock) -> Optional[str]:
        """找到定理的父节点 ID"""
        # 如果有依赖，找到最深层次的依赖
        if thm.dependencies:
            for dep_id in thm.dependencies:
                if dep_id in self.graph.theorems:
                    return self._safe_id(dep_id)
        return None

    def to_json(self) -> str:
        """导出为 JSON 格式"""
        data = {
            'nodes': [],
            'edges': []
        }

        for thm in self.graph.theorems.values():
            node = {
                'id': self._safe_id(thm.id),
                'original_id': thm.id,
                'label': thm.label,
                'type': thm.type.value,
                'title': thm.title,
                'level': thm.level,
                'line_number': thm.line_number,
                'preview': thm.content_preview[:100] if thm.content_preview else ""
            }
            data['nodes'].append(node)

        for thm in self.graph.theorems.values():
            for dep_id in thm.dependencies:
                if dep_id in self.graph.theorems:
                    data['edges'].append({
                        'source': self._safe_id(dep_id),
                        'target': self._safe_id(thm.id)
                    })

        return json.dumps(data, ensure_ascii=False, indent=2)

    def get_summary(self) -> Dict[str, Any]:
        """获取思维导图摘要"""
        stats = self.graph._build_statistics()

        return {
            'total_nodes': stats['total_theorems'],
            'by_type': stats['by_type'],
            'max_depth': stats['max_depth'],
            'total_references': stats['total_references'],
            'layouts_available': [layout.value for layout in MindMapLayout]
        }


def generate_mind_map_from_latex(
    latex_content: str,
    layout: str = "hierarchical",
    include_proofs: bool = False
) -> Dict[str, Any]:
    """
    从 LaTeX 内容生成思维导图的快捷函数

    Args:
        latex_content: LaTeX 文档内容
        layout: 布局类型 (hierarchical, dependency, timeline, classification)
        include_proofs: 是否包含证明节点

    Returns:
        {
            'mermaid': str,  # Mermaid 格式代码
            'json': str,     # JSON 格式数据
            'summary': dict  # 摘要统计
        }
    """
    from knowledge_graph import KnowledgeGraphAnalyzer

    analyzer = KnowledgeGraphAnalyzer()
    graph = analyzer.analyze(latex_content)

    generator = MindMapGenerator(graph)

    layout_enum = MindMapLayout.HIERARCHICAL
    if layout == "dependency":
        layout_enum = MindMapLayout.DEPENDENCY
    elif layout == "timeline":
        layout_enum = MindMapLayout.TIMELINE
    elif layout == "classification":
        layout_enum = MindMapLayout.CLASSIFICATION

    return {
        'mermaid': generator.generate_mermaid(layout_enum, include_proofs),
        'json': generator.to_json(),
        'summary': generator.get_summary()
    }