#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LaTeX 语法检查与自动纠错模块
用于检测和修复 LLM 输出的 LaTeX 常见语法错误
"""

import re
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class LaTeXError:
    """LaTeX 语法错误描述"""
    error_type: str  # 'brace', 'environment', 'command', 'math', 'table'
    message: str
    line: int
    position: int
    severity: str  # 'error', 'warning', 'info'
    original: str
    suggestion: Optional[str] = None


class LaTeXSyntaxChecker:
    """LaTeX 语法检查器"""

    # 常见的 LaTeX 环境
    KNOWN_ENVIRONMENTS = {
        'document', 'equation', 'eqnarray', 'align', 'align*', 'gather', 'gather*',
        'multline', 'multline*', 'flalign', 'flalign*', 'tabular', 'tabular*',
        'table', 'figure', 'center', 'flushleft', 'flushright', 'quote',
        'quotation', 'verse', 'itemize', 'enumerate', 'description',
        'theorem', 'lemma', 'proof', 'definition', 'corollary', 'proposition',
        'remark', 'example', 'exercise', 'problem', 'solution',
        'algorithm', 'algorithmic', 'frame', 'columns', 'column',
        'abstract', 'titlepage', 'part', 'chapter', 'section', 'subsection',
        'subsubsection', 'paragraph', 'subparagraph',
        'bibliography', 'thebibliography', 'references',
        'verbatim', 'listing', 'minipage', 'vbox', 'hbox',
        'multicol', 'sidebysideside', 'caption', 'label', 'ref',
        'footnote', 'marginpar', 'hyperref', 'href',
        'babel', 'input', 'include', 'includegraphics',
        'centering', 'raggedright', 'raggedleft',
        'toprule', 'midrule', 'bottomrule', 'cmidrule', 'hline',
        'rowcolor', 'cellcolor', 'rowlines', 'columncolor',
        'rotate', 'scalebox', 'resizebox', 'phantom',
        'frac', 'sqrt', 'binom', 'choose', 'underbrace', 'overbrace',
        'textbf', 'textit', 'texttt', 'textsf', 'scshape', 'slshape',
        'series', 'fontseries', 'fontshape', 'fontfamily',
        'textbf', 'textbf', 'text', 'mbox', 'fbox', 'savebox',
        'parbox', 'makebox', 'rule', 'raisebox', 'settowidth', 'settoheight',
    }

    # 需要匹配的环境（开始和结束必须配对）
    PAIRED_ENVIRONMENTS = {
        'document', 'equation', 'eqnarray', 'align', 'align*', 'gather', 'gather*',
        'multline', 'multline*', 'flalign', 'flalign*', 'tabular', 'tabular*',
        'table', 'figure', 'center', 'flushleft', 'flushright', 'quote',
        'quotation', 'verse', 'itemize', 'enumerate', 'description',
        'theorem', 'lemma', 'proof', 'definition', 'corollary', 'proposition',
        'remark', 'example', 'exercise', 'problem', 'solution',
        'algorithm', 'algorithmic', 'frame', 'columns', 'column',
        'abstract', 'titlepage', 'minipage', 'vbox', 'hbox',
        'verbatim', 'listing', 'multicol',
        'thebibliography', 'bibliography', 'references',
    }

    def __init__(self):
        self.errors: List[LaTeXError] = []

    def check(self, latex_content: str) -> List[LaTeXError]:
        """
        检查 LaTeX 内容的语法错误

        Args:
            latex_content: LaTeX 内容

        Returns:
            错误列表
        """
        self.errors = []
        lines = latex_content.split('\n')

        self._check_braces(latex_content, lines)
        self._check_environments(latex_content, lines)
        self._check_math_delimiters(latex_content, lines)
        self._check_common_errors(latex_content, lines)

        return self.errors

    def _check_braces(self, content: str, lines: List[str]) -> None:
        """检查大括号匹配"""
        stack = []
        line_num = 1
        pos = 0

        i = 0
        while i < len(content):
            char = content[i]

            if char == '\n':
                line_num += 1
                pos = 0
            elif char == '{':
                stack.append((line_num, pos, '{'))
            elif char == '}':
                if stack and stack[-1][2] == '{':
                    stack.pop()
                elif stack:
                    # 非配对的 }
                    self.errors.append(LaTeXError(
                        error_type='brace',
                        message=f'多余的反闭括号 }}',
                        line=line_num,
                        position=pos,
                        severity='warning',
                        original='}',
                        suggestion=None
                    ))
                else:
                    self.errors.append(LaTeXError(
                        error_type='brace',
                        message=f'缺少开括号 {{',
                        line=line_num,
                        position=pos,
                        severity='error',
                        original='}',
                        suggestion=None
                    ))
            elif char == '%':
                # 跳过注释
                while i < len(content) and content[i] != '\n':
                    i += 1
                continue

            pos += 1
            i += 1

        # 检查未闭合的括号
        for open_line, open_pos, _ in stack:
            self.errors.append(LaTeXError(
                error_type='brace',
                message=f'缺少闭括号 }}',
                line=open_line,
                position=open_pos,
                severity='error',
                original='(未闭合的开括号',
                suggestion='}'
            ))

    def _check_environments(self, content: str, lines: List[str]) -> None:
        """检查环境匹配"""
        stack = []
        i = 0
        line_num = 1

        while i < len(content):
            char = content[i]

            if char == '\n':
                line_num += 1

            # 跳过注释
            if char == '%':
                while i < len(content) and content[i] != '\n':
                    i += 1
                i += 1
                continue

            # 检查 \begin
            if content[i:i+7] == r'\begin{':
                i += 7
                env_name = ''
                while i < len(content) and content[i] != '}':
                    env_name += content[i]
                    i += 1

                if env_name in self.PAIRED_ENVIRONMENTS or self._is_known_env(env_name):
                    stack.append((line_num, env_name))

            # 检查 \end
            elif content[i:i+5] == r'\end{':
                i += 5
                env_name = ''
                while i < len(content) and content[i] != '}':
                    env_name += content[i]
                    i += 1

                if stack:
                    open_line, open_env = stack.pop()
                    if open_env != env_name:
                        self.errors.append(LaTeXError(
                            error_type='environment',
                            message=f'环境不匹配: \\begin{{{open_env}}} (第 {open_line} 行) 与 \\end{{{env_name}}} (第 {line_num} 行)',
                            line=line_num,
                            position=0,
                            severity='error',
                            original=f'\\end{{{env_name}}}',
                            suggestion=f'\\end{{{open_env}}}'
                        ))
                elif self._is_known_env(env_name):
                    self.errors.append(LaTeXError(
                        error_type='environment',
                        message=f'多余的 \\end{{{env_name}}}',
                        line=line_num,
                        position=0,
                        severity='warning',
                        original=f'\\end{{{env_name}}}',
                        suggestion=None
                    ))

            i += 1

        # 未闭合的环境
        for open_line, env_name in stack:
            self.errors.append(LaTeXError(
                error_type='environment',
                message=f'未闭合的环境 \\begin{{{env_name}}} (第 {open_line} 行)',
                line=open_line,
                position=0,
                severity='error',
                original=f'\\begin{{{env_name}}}',
                suggestion=f'\\end{{{env_name}}}'
            ))

    def _check_math_delimiters(self, content: str, lines: List[str]) -> None:
        """检查数学环境分隔符"""
        math_open = ['\\(','\\[','$','$$']
        math_close = ['\\)','\\]','$','$$']
        stack = []

        i = 0
        line_num = 1

        while i < len(content):
            char = content[i]

            if char == '\n':
                line_num += 1

            # 跳过注释
            if char == '%':
                while i < len(content) and content[i] != '\n':
                    i += 1
                i += 1
                continue

            # 跳过 \begin 等命令
            if char == '\\' and i + 1 < len(content) and content[i+1].isalpha():
                while i < len(content) and content[i] != ' ' and content[i] != '\n' and content[i] != '{' and content[i] != '}':
                    i += 1
                continue

            # 检查 \( 和 \)
            if content[i:i+2] == '\\(':
                stack.append((line_num, '\\(', '\\)'))
                i += 2
                continue
            elif content[i:i+2] == '\\)':
                if stack and stack[-1][1] == '\\(':
                    stack.pop()
                elif stack:
                    self.errors.append(LaTeXError(
                        error_type='math',
                        message=f'数学分隔符不匹配',
                        line=line_num,
                        position=0,
                        severity='warning',
                        original='\\)',
                        suggestion='\\('
                    ))
                else:
                    self.errors.append(LaTeXError(
                        error_type='math',
                        message=f'多余的 \\)',
                        line=line_num,
                        position=0,
                        severity='warning',
                        original='\\)'
                    ))
                i += 2
                continue

            # 检查 \[ 和 \]
            if content[i:i+2] == '\\[':
                stack.append((line_num, '\\[', '\\]'))
                i += 2
                continue
            elif content[i:i+2] == '\\]':
                if stack and stack[-1][1] == '\\[':
                    stack.pop()
                elif stack:
                    self.errors.append(LaTeXError(
                        error_type='math',
                        message=f'数学分隔符不匹配',
                        line=line_num,
                        position=0,
                        severity='warning',
                        original='\\]'
                    ))
                else:
                    self.errors.append(LaTeXError(
                        error_type='math',
                        message=f'多余的 \\]',
                        line=line_num,
                        position=0,
                        severity='warning',
                        original='\\]'
                    ))
                i += 2
                continue

            i += 1

    def _check_common_errors(self, content: str, lines: List[str]) -> None:
        """检查常见错误"""
        # 检测连续空行
        empty_lines = re.findall(r'\n{4,}', content)
        if empty_lines:
            for match in re.finditer(r'\n{4,}', content):
                line_num = content[:match.start()].count('\n') + 1
                self.errors.append(LaTeXError(
                    error_type='format',
                    message='连续空行过多',
                    line=line_num,
                    position=0,
                    severity='info',
                    original=match.group(0),
                    suggestion='\n\n'
                ))

        # 检测独立的 &
        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped == '&' or stripped.endswith('&'):
                # 可能是表格截断
                pass  # 不报错，由表格修复处理

    def _is_known_env(self, env_name: str) -> bool:
        """检查是否已知的环境"""
        # 去掉 * 后缀
        base_name = env_name.rstrip('*')
        return base_name in self.KNOWN_ENVIRONMENTS


class LaTeXAutoFixer:
    """LaTeX 自动纠错器"""

    def __init__(self):
        self.checker = LaTeXSyntaxChecker()

    def fix(self, latex_content: str) -> Tuple[str, List[LaTeXError]]:
        """
        自动修复 LaTeX 语法错误

        Args:
            latex_content: LaTeX 内容

        Returns:
            (修复后的内容, 剩余错误列表)
        """
        content = latex_content
        errors = self.checker.check(content)

        # 记录已修复的问题
        fixed = set()

        # 1. 修复连续空行
        content = re.sub(r'\n{3,}', '\n\n', content)

        # 2. 修复多余的反闭括号（删除孤立行尾的 }）
        lines = content.split('\n')
        fixed_lines = []
        for line in lines:
            stripped = line.strip()
            # 如果一行只有 } 符号，删除它
            if stripped == '}' and 'fixed' not in line:
                continue
            fixed_lines.append(line)
        content = '\n'.join(fixed_lines)

        # 3. 修复常见的 & 截断问题（表格）
        content = self._fix_table_ampercent(content)

        # 重新检查
        remaining_errors = self.checker.check(content)

        return content, remaining_errors

    def _fix_table_ampercent(self, content: str) -> str:
        """修复表格中的截断 & 行"""
        lines = content.split('\n')
        fixed_lines = []

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # 检测可能的截断行：以 & 结尾的短行
            if stripped.endswith('&') and len(stripped) < 20:
                # 检查下一行是否也是短行且以内容开头
                if i + 1 < len(lines):
                    next_stripped = lines[i + 1].strip()
                    # 如果下一行不是以 \ 开始，可能是截断的内容
                    if next_stripped and not next_stripped.startswith('\\') and not next_stripped.startswith('%'):
                        # 合并这两行
                        merged = line.rstrip() + ' ' + lines[i + 1].lstrip()
                        fixed_lines.append(merged)
                        i += 2
                        continue

            fixed_lines.append(line)
            i += 1

        return '\n'.join(fixed_lines)

    def validate(self, latex_content: str) -> Dict[str, Any]:
        """
        验证 LaTeX 内容并返回详细报告

        Returns:
            {
                'valid': bool,
                'errors': List[LaTeXError],
                'warnings': int,
                'errors_count': int,
                'fix_suggestions': List[str]
            }
        """
        errors = self.checker.check(latex_content)

        warnings = [e for e in errors if e.severity == 'warning']
        error_list = [e for e in errors if e.severity == 'error']

        suggestions = []
        for err in errors:
            if err.suggestion:
                suggestions.append(f"第 {err.line} 行: {err.message} -> 建议: {err.suggestion}")

        return {
            'valid': len(error_list) == 0,
            'errors': errors,
            'warnings_count': len(warnings),
            'errors_count': len(error_list),
            'fix_suggestions': suggestions
        }


# 快捷函数
def check_latex_syntax(latex_content: str) -> List[LaTeXError]:
    """检查 LaTeX 语法"""
    checker = LaTeXSyntaxChecker()
    return checker.check(latex_content)


def fix_latex_syntax(latex_content: str) -> Tuple[str, List[LaTeXError]]:
    """自动修复 LaTeX 语法"""
    fixer = LaTeXAutoFixer()
    return fixer.fix(latex_content)


def validate_latex(latex_content: str) -> Dict[str, Any]:
    """验证并返回详细报告"""
    fixer = LaTeXAutoFixer()
    return fixer.validate(latex_content)


# ==================== 转换质量评分系统 ====================

@dataclass
class QualityIssue:
    """质量问题"""
    category: str  # 'formula', 'table', 'image', 'reference', 'structure', 'content'
    severity: str  # 'critical', 'major', 'minor'
    message: str
    line: Optional[int] = None
    suggestion: Optional[str] = None


@dataclass
class QualityScore:
    """质量评分结果"""
    score: int  # 0-100
    grade: str  # 'A', 'B', 'C', 'D', 'F'
    formula_score: int  # 公式完整性分数
    table_score: int  # 表格结构分数
    image_score: int  # 图片覆盖率分数
    reference_score: int  # 参考文献完整性分数
    structure_score: int  # 结构完整性分数
    issues: List[QualityIssue]  # 问题列表
    statistics: Dict[str, Any]  # 基础统计

    def to_dict(self) -> Dict[str, Any]:
        return {
            'score': self.score,
            'grade': self.grade,
            'formula_score': self.formula_score,
            'table_score': self.table_score,
            'image_score': self.image_score,
            'reference_score': self.reference_score,
            'structure_score': self.structure_score,
            'issues': [
                {
                    'category': i.category,
                    'severity': i.severity,
                    'message': i.message,
                    'line': i.line,
                    'suggestion': i.suggestion
                }
                for i in self.issues
            ],
            'statistics': self.statistics,
            'summary': self._generate_summary()
        }

    def _generate_summary(self) -> str:
        """生成评分摘要"""
        summaries = []
        if self.score >= 90:
            summaries.append(f"优秀 (A) - 评分 {self.score}/100")
        elif self.score >= 75:
            summaries.append(f"良好 (B) - 评分 {self.score}/100")
        elif self.score >= 60:
            summaries.append(f"一般 (C) - 评分 {self.score}/100")
        elif self.score >= 40:
            summaries.append(f"较差 (D) - 评分 {self.score}/100")
        else:
            summaries.append(f"极差 (F) - 评分 {self.score}/100，需要大量人工修正")

        critical_issues = [i for i in self.issues if i.severity == 'critical']
        if critical_issues:
            summaries.append(f"\n⚠️ 发现 {len(critical_issues)} 个严重问题需要立即修复")

        major_issues = [i for i in self.issues if i.severity == 'major']
        if major_issues:
            summaries.append(f"⚡ 发现 {len(major_issues)} 个主要问题")

        return "\n".join(summaries)


class LaTeXQualityScorer:
    """LaTeX 转换质量评分器"""

    # 公式环境
    MATH_ENVS = {
        'equation', 'equation*', 'eqnarray', 'eqnarray*',
        'align', 'align*', 'gather', 'gather*',
        'multline', 'multline*', 'flalign', 'flalign*',
        'math', 'displaymath'
    }

    def __init__(self):
        self.issues: List[QualityIssue] = []
        self.statistics: Dict[str, Any] = {}

    def score(self, latex_content: str) -> QualityScore:
        """
        评估 LaTeX 转换质量

        Returns:
            QualityScore 对象
        """
        self.issues = []
        self._collect_statistics(latex_content)

        # 各维度评分
        formula_score = self._score_formula_completeness(latex_content)
        table_score = self._score_table_structure(latex_content)
        image_score = self._score_image_coverage(latex_content)
        reference_score = self._score_reference_completeness(latex_content)
        structure_score = self._score_structure_completeness(latex_content)

        # 加权总分
        total_score = (
            formula_score * 0.30 +
            table_score * 0.20 +
            image_score * 0.15 +
            reference_score * 0.15 +
            structure_score * 0.20
        )

        # 计算等级
        grade = self._score_to_grade(total_score)

        return QualityScore(
            score=round(total_score),
            grade=grade,
            formula_score=formula_score,
            table_score=table_score,
            image_score=image_score,
            reference_score=reference_score,
            structure_score=structure_score,
            issues=self.issues.copy(),
            statistics=self.statistics.copy()
        )

    def _collect_statistics(self, content: str) -> None:
        """收集基础统计信息"""
        lines = content.split('\n')

        # 统计各种元素数量
        self.statistics = {
            'total_lines': len(lines),
            'total_chars': len(content),
            'math_env_count': 0,
            'inline_math_count': 0,
            'tabular_count': 0,
            'figure_count': 0,
            'reference_count': 0,
            'label_count': 0,
            'section_count': 0,
            'theorem_like_count': 0,
        }

        # 统计数学公式
        math_env_pattern = re.compile(r'\\begin\{(' + '|'.join(self.MATH_ENVS) + r')\}')
        self.statistics['math_env_count'] = len(math_env_pattern.findall(content))

        # 统计行内公式
        inline_math_pattern = re.compile(r'\$[^$]+\$')
        self.statistics['inline_math_count'] = len(inline_math_pattern.findall(content))

        # 统计表格
        tabular_pattern = re.compile(r'\\begin\{tabular\*?\}')
        self.statistics['tabular_count'] = len(tabular_pattern.findall(content))

        # 统计图片
        figure_pattern = re.compile(r'\\begin\{figure\*?\}')
        self.statistics['figure_count'] = len(figure_pattern.findall(content))

        # 统计引用
        ref_pattern = re.compile(r'\\ref\{([^}]+)\}')
        self.statistics['reference_count'] = len(ref_pattern.findall(content))

        # 统计标签
        label_pattern = re.compile(r'\\label\{([^}]+)\}')
        self.statistics['label_count'] = len(label_pattern.findall(content))

        # 统计章节
        section_pattern = re.compile(r'\\section\{')
        self.statistics['section_count'] = len(section_pattern.findall(content))

        # 统计定理环境
        theorem_pattern = re.compile(
            r'\\begin\{(theorem|lemma|proposition|corollary|definition|proof|example)\*?\}',
            re.IGNORECASE
        )
        self.statistics['theorem_like_count'] = len(theorem_pattern.findall(content))

    def _score_formula_completeness(self, content: str) -> int:
        """评估公式完整性"""
        score = 100

        # 检查数学环境
        math_count = self.statistics.get('math_env_count', 0)
        inline_count = self.statistics.get('inline_math_count', 0)

        if math_count == 0 and inline_count == 0:
            # 没有公式，不扣分（可能文档本身没有公式）
            return 100

        # 检查公式是否平衡
        dollar_pairs = content.count('$') % 2
        if dollar_pairs != 0:
            self.issues.append(QualityIssue(
                category='formula',
                severity='critical',
                message='行内公式美元符号不匹配',
                suggestion='确保所有 $...$ 公式成对出现'
            ))
            score -= 30

        # 检查 display math 是否平衡
        display_start = len(re.findall(r'\\\[', content))
        display_end = len(re.findall(r'\\\]', content))
        if display_start != display_end:
            self.issues.append(QualityIssue(
                category='formula',
                severity='critical',
                message=f'Display math 不匹配: [ 出现 {display_start} 次，] 出现 {display_end} 次',
                suggestion='确保 \\['
            ))
            score -= 30

        # 检查 equation 环境是否平衡
        eq_start = len(re.findall(r'\\begin\{equation\*?\}', content, re.IGNORECASE))
        eq_end = len(re.findall(r'\\end\{equation\*?\}', content, re.IGNORECASE))
        if eq_start != eq_end:
            self.issues.append(QualityIssue(
                category='formula',
                severity='major',
                message=f'equation 环境不匹配: {eq_start} 个开始，{eq_end} 个结束',
                suggestion='确保 \\begin{equation} 和 \\end{equation} 成对'
            ))
            score -= 20

        return max(0, score)

    def _score_table_structure(self, content: str) -> int:
        """评估表格结构"""
        score = 100

        tabular_count = self.statistics.get('tabular_count', 0)
        if tabular_count == 0:
            return 100

        # 检查 tabular 环境
        tabular_pattern = re.compile(
            r'\\begin\{tabular\*?\}(?:\[[^\]]*\])?\{([^}]*)\}'
            r'([\s\S]*?)'
            r'\\end\{tabular\*?\}',
            re.IGNORECASE
        )

        for match in tabular_pattern.finditer(content):
            spec = match.group(1)
            body = match.group(2)

            # 计算列数
            spec_cols = len(re.findall(r'[clr]', spec))

            # 检查每行的列数
            lines = body.split('\n')
            for line_num, line in enumerate(lines, 1):
                stripped = line.strip()
                if not stripped or stripped.startswith('%'):
                    continue

                # 跳过特殊命令
                if re.match(r'\\(hline|toprule|midrule|bottomrule|cmidrule)', stripped):
                    continue

                # 计算单元格数量
                cells = len(re.split(r'(?<!\\)(?:\\\\)*&', line))
                if cells != spec_cols:
                    abs_line = match.start() + sum(len(l) + 1 for l in lines[:line_num])
                    self.issues.append(QualityIssue(
                        category='table',
                        severity='major',
                        message=f'表格列数不匹配: 预期 {spec_cols} 列，实际 {cells} 列',
                        line=content[:abs_line].count('\n') + 1,
                        suggestion=f'使用 & 分隔符确保每行有 {spec_cols} 列'
                    ))
                    score -= 10

        return max(0, score)

    def _score_image_coverage(self, content: str) -> int:
        """评估图片覆盖率"""
        score = 100

        figure_count = self.statistics.get('figure_count', 0)

        # 检查是否有 figure 环境但没有 \includegraphics
        figure_pattern = re.compile(
            r'\\begin\{figure\*?\}([\s\S]*?)\\end\{figure\*?\}',
            re.IGNORECASE
        )

        for match in figure_pattern.finditer(content):
            figure_body = match.group(1)
            if '\\includegraphics' not in figure_body and '\\includegraphics' not in content:
                self.issues.append(QualityIssue(
                    category='image',
                    severity='minor',
                    message='figure 环境缺少 \\includegraphics 命令',
                    suggestion='添加图片或说明文字'
                ))
                score -= 5

        return max(0, score)

    def _score_reference_completeness(self, content: str) -> int:
        """评估参考文献完整性"""
        score = 100

        ref_count = self.statistics.get('reference_count', 0)
        label_count = self.statistics.get('label_count', 0)

        if ref_count == 0:
            return 100

        # 检查 \ref 和 \label 是否匹配
        refs = set(re.findall(r'\\ref\{([^}]+)\}', content))
        labels = set(re.findall(r'\\label\{([^}]+)\}', content))

        undefined_refs = refs - labels
        unused_labels = labels - refs

        # 只报告未被使用的标签（可能是问题）
        if unused_labels:
            for label in list(unused_labels)[:5]:
                self.issues.append(QualityIssue(
                    category='reference',
                    severity='minor',
                    message=f'未使用的标签: \\label{{{label}}}',
                    suggestion='检查是否需要引用此标签'
                ))
                score -= 3

        return max(0, score)

    def _score_structure_completeness(self, content: str) -> int:
        """评估结构完整性"""
        score = 100

        # 检查 document 环境
        has_begindoc = '\\begin{document}' in content
        has_enddoc = '\\end{document}' in content

        if has_begindoc != has_enddoc:
            self.issues.append(QualityIssue(
                category='structure',
                severity='critical',
                message='document 环境不完整',
                suggestion='确保有 \\begin{document} 和 \\end{document}'
            ))
            score -= 30

        # 检查章节结构
        section_count = self.statistics.get('section_count', 0)
        if section_count == 0:
            self.issues.append(QualityIssue(
                category='structure',
                severity='minor',
                message='文档缺少章节结构',
                suggestion='考虑添加 \\section 命令组织文档'
            ))
            score -= 10

        # 检查定理证明完整性
        theorem_count = self.statistics.get('theorem_like_count', 0)
        # 简化检查：如果有证明环境应该有关联定理

        return max(0, score)

    def _score_to_grade(self, score: int) -> str:
        """将分数转换为等级"""
        if score >= 90:
            return 'A'
        elif score >= 75:
            return 'B'
        elif score >= 60:
            return 'C'
        elif score >= 40:
            return 'D'
        else:
            return 'F'


# 快捷函数
def score_latex_quality(latex_content: str) -> Dict[str, Any]:
    """
    评估 LaTeX 转换质量

    Returns:
        {
            'score': 85,
            'grade': 'B',
            'formula_score': 90,
            'table_score': 100,
            'image_score': 95,
            'reference_score': 80,
            'structure_score': 85,
            'issues': [...],
            'statistics': {...},
            'summary': '...'
        }
    """
    scorer = LaTeXQualityScorer()
    result = scorer.score(latex_content)
    return result.to_dict()