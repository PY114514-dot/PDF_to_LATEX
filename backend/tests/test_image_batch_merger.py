"""
Tests for ImageBatchMerger - combines multiple images into single LaTeX document
"""

import pytest
from pathlib import Path
from PIL import Image
import tempfile
import os

from image_batch_merger import ImageBatchMerger


class TestImageBatchMerger:
    """Tests for ImageBatchMerger class"""

    @pytest.fixture
    def temp_image_dir(self):
        """Create a temporary directory with test images"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def single_test_image(self, temp_image_dir):
        """Create a single test image"""
        img_path = Path(temp_image_dir) / "test_image.png"
        img = Image.new('RGB', (100, 100), color='red')
        img.save(img_path)
        return str(img_path)

    @pytest.fixture
    def multiple_test_images(self, temp_image_dir):
        """Create multiple test images"""
        image_paths = []
        for i, name in enumerate(['image_one', 'image_two', 'image_three']):
            img_path = Path(temp_image_dir) / f"{name}.png"
            img = Image.new('RGB', (100, 100), color=(i * 50, i * 100, i * 150))
            img.save(img_path)
            image_paths.append(str(img_path))
        return image_paths

    def test_merge_single_image(self, single_test_image):
        """Verify \section and \begin{document} in output"""
        merger = ImageBatchMerger()
        result = merger.merge_to_latex([single_test_image])

        assert '\\section{test_image}' in result
        assert '\\begin{document}' in result
        assert '\\begin{figure}' in result
        assert '\\includegraphics' in result
        assert '\\end{figure}' in result

    def test_merge_multiple_images(self, multiple_test_images):
        """Verify 3 images produce 3 sections"""
        merger = ImageBatchMerger()
        result = merger.merge_to_latex(multiple_test_images)

        assert result.count('\\section{') == 3
        assert result.count('\\begin{figure}') == 3
        assert result.count('\\end{figure}') == 3
        assert result.count('\\includegraphics') == 3

    def test_latex_content_contains_image_names(self, multiple_test_images):
        """Verify filename appears in output"""
        merger = ImageBatchMerger()
        result = merger.merge_to_latex(multiple_test_images)

        assert 'image_one' in result
        assert 'image_two' in result
        assert 'image_three' in result

    def test_save_merged(self, multiple_test_images, temp_image_dir):
        """Test saving merged content to file"""
        merger = ImageBatchMerger()
        output_path = Path(temp_image_dir) / "merged.tex"

        saved_path = merger.save_merged(multiple_test_images, str(output_path))

        assert Path(saved_path).exists()
        content = Path(saved_path).read_text(encoding='utf-8')
        assert '\\begin{document}' in content
        assert 'image_one' in content

    def test_merge_without_filenames(self, single_test_image):
        """Test merge without filename sections"""
        merger = ImageBatchMerger()
        result = merger.merge_to_latex([single_test_image], include_filenames=False)

        assert '\\section{' not in result
        assert '\\begin{figure}' in result

    def test_merge_without_document_wrapper(self, single_test_image):
        """Test merge without document wrapper"""
        merger = ImageBatchMerger()
        result = merger.merge_to_latex([single_test_image], add_document_wrapper=False)

        assert '\\begin{document}' not in result
        assert '\\begin{figure}' in result
