# backend/vector2raster.py
"""
Vector image (SVG/EMF) to raster (PNG) converter
Uses cairosvg for SVG conversion
"""

import os
from pathlib import Path
from typing import Optional

try:
    import cairosvg
    CAIRO_AVAILABLE = True
except ImportError:
    CAIRO_AVAILABLE = False


class VectorToRasterConverter:
    """Converts vector images (SVG, EMF) to raster format (PNG)"""

    def __init__(self):
        self.cairo_available = CAIRO_AVAILABLE

    def svg_to_png(
        self,
        svg_path: str,
        output_path: str,
        dpi: int = 300
    ) -> bool:
        """Convert SVG to PNG."""
        if not self.cairo_available:
            raise RuntimeError(
                "cairosvg not installed. Install with: pip install cairosvg"
            )

        try:
            cairosvg.svg2png(
                url=svg_path,
                write_to=output_path,
                dpi=dpi
            )
            return True
        except Exception as e:
            print(f"SVG to PNG conversion failed: {e}")
            return False

    def emf_to_png(
        self,
        emf_path: str,
        output_path: str,
        dpi: int = 300
    ) -> bool:
        """Convert EMF to PNG."""
        raise NotImplementedError(
            "EMF conversion requires external tools (LibreOffice or ImageMagick). "
            "Consider using: libreoffice --headless --convert-to png input.emf "
            "or: convert input.emf output.png"
        )

    def convert_to_raster(
        self,
        input_path: str,
        output_path: str,
        dpi: int = 300
    ) -> bool:
        """Auto-detect format and convert to raster."""
        ext = Path(input_path).suffix.lower()

        if ext == '.svg':
            return self.svg_to_png(input_path, output_path, dpi)
        elif ext == '.emf':
            return self.emf_to_png(input_path, output_path, dpi)
        else:
            raise ValueError(f"Unsupported vector format: {ext}. Supported: .svg, .emf")

    def is_vector_file(self, file_path: str) -> bool:
        """Check if file is a vector format."""
        ext = Path(file_path).suffix.lower()
        return ext in ['.svg', '.emf', '.eps', '.wmf']