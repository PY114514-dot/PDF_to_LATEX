"""
Image batch merger - combines multiple images into single LaTeX document
"""

from pathlib import Path
from typing import List, Optional

from latex_utils import wrap_with_template


class ImageBatchMerger:
    """Merges multiple images into a single LaTeX document"""

    def __init__(self, template_name: str = 'article'):
        self.template_name = template_name

    def merge_to_latex(
        self,
        image_paths: List[str],
        include_filenames: bool = True,
        add_document_wrapper: bool = True
    ) -> str:
        """Merge multiple images into LaTeX sections."""
        sections = []

        for idx, image_path in enumerate(image_paths, 1):
            path = Path(image_path)
            stem = path.stem

            if include_filenames:
                sections.append(f'\\section{{{stem}}}')

            sections.append(f'\\begin{{figure}}[htbp]')
            sections.append(f'\\centering')
            sections.append(f'\\includegraphics[width=0.8\\textwidth]{{{path.name}}}')
            sections.append(f'\\caption{{{stem}}}')
            sections.append(f'\\end{{figure}}')
            sections.append('')

        latex_content = '\n'.join(sections)

        if add_document_wrapper:
            latex_content = wrap_with_template(
                latex_content,
                template_name=self.template_name,
                use_chinese=False
            )

        return latex_content

    def save_merged(
        self,
        image_paths: List[str],
        output_path: str,
        include_filenames: bool = True
    ) -> str:
        """Merge images and save to file."""
        latex_content = self.merge_to_latex(image_paths, include_filenames)

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(latex_content, encoding='utf-8')

        return str(output)
