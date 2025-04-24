from pathlib import Path
from PIL import Image, ImageChops
import numpy as np
from .heightmap import convert_height_map
from .province import convert_province_map
from .rivers import convert_rivers_map


def convert_map(
        from_folder,
        mod_folder,
        destination_dimensions,
        conversion_scale,
        conversion_offset,
):
    original_heightmap_path = Path(from_folder) / "map" / "topology.bpm"
    converted_heightmap_path = Path(mod_folder) / "map_data" / "heightmap.png"

    convert_height_map(
        original_heightmap_path,
        converted_heightmap_path,
        conversion_scale,
        conversion_offset,
        destination_dimensions,
    )

    original_province_map_path = Path(from_folder) / "map" / "provinces.bmp"
    converted_province_map_path = Path(mod_folder) / "map_data" / "provinces.png"

    convert_province_map(
        original_province_map_path,
        converted_province_map_path,
        conversion_scale,
        conversion_offset,
        destination_dimensions,
    )

    original_rivers_map_path = Path(from_folder) / "map" / "rivers.bmp"
    converted_rivers_map_path = Path(mod_folder) / "map_data" / "rivers.png"

    convert_rivers_map(
        original_rivers_map_path,
        converted_rivers_map_path,
        conversion_scale,
        conversion_offset,
        destination_dimensions,
    )

