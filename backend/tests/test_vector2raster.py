"""
Tests for vector2raster module
"""

import os
import tempfile
import pytest
from pathlib import Path


class TestVectorToRasterConverter:
    """Test cases for VectorToRasterConverter"""

    def test_svg_to_png(self):
        """Creates temp SVG, converts to PNG, verifies output exists"""
        from backend.vector2raster import VectorToRasterConverter

        # Create a simple SVG content
        svg_content = '''<?xml version="1.0" encoding="UTF-8"?>
        <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
            <rect width="100" height="100" fill="blue"/>
        </svg>'''

        converter = VectorToRasterConverter()

        # Skip test if cairosvg not available
        if not converter.cairo_available:
            pytest.skip("cairosvg not installed")

        with tempfile.TemporaryDirectory() as tmpdir:
            svg_path = os.path.join(tmpdir, "test.svg")
            png_path = os.path.join(tmpdir, "test.png")

            # Write SVG file
            with open(svg_path, 'w', encoding='utf-8') as f:
                f.write(svg_content)

            # Convert
            result = converter.svg_to_png(svg_path, png_path, dpi=300)

            # Verify
            assert result is True
            assert os.path.exists(png_path)
            assert os.path.getsize(png_path) > 0

    def test_unsupported_format(self):
        """Verifies ValueError for unsupported formats"""
        from backend.vector2raster import VectorToRasterConverter

        converter = VectorToRasterConverter()

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "test.txt")
            output_path = os.path.join(tmpdir, "test.png")

            # Create a dummy file
            with open(input_path, 'w') as f:
                f.write("dummy content")

            with pytest.raises(ValueError) as exc_info:
                converter.convert_to_raster(input_path, output_path, dpi=300)

            assert "Unsupported vector format" in str(exc_info.value)
            assert ".txt" in str(exc_info.value)

    def test_is_vector_file(self):
        """Verifies .svg and .emf detection"""
        from backend.vector2raster import VectorToRasterConverter

        converter = VectorToRasterConverter()

        # Test SVG detection
        assert converter.is_vector_file("test.svg") is True
        assert converter.is_vector_file("test.SVG") is True

        # Test EMF detection
        assert converter.is_vector_file("test.emf") is True
        assert converter.is_vector_file("test.EMF") is True

        # Test non-vector files
        assert converter.is_vector_file("test.png") is False
        assert converter.is_vector_file("test.jpg") is False
        assert converter.is_vector_file("test.txt") is False
        assert converter.is_vector_file("test.pdf") is False

        # Test EPS and WMF
        assert converter.is_vector_file("test.eps") is True
        assert converter.is_vector_file("test.wmf") is True

    def test_emf_to_png_raises_not_implemented(self):
        """Verifies EMF conversion raises NotImplementedError"""
        from backend.vector2raster import VectorToRasterConverter

        converter = VectorToRasterConverter()

        with tempfile.TemporaryDirectory() as tmpdir:
            emf_path = os.path.join(tmpdir, "test.emf")
            png_path = os.path.join(tmpdir, "test.png")

            # Create a dummy EMF file (not a real EMF, just for testing)
            with open(emf_path, 'wb') as f:
                f.write(b'dummy emf content')

            with pytest.raises(NotImplementedError) as exc_info:
                converter.emf_to_png(emf_path, png_path, dpi=300)

            assert "LibreOffice" in str(exc_info.value)
            assert "ImageMagick" in str(exc_info.value)
