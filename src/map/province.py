from pathlib import Path
from PIL import Image


def convert_province_map(
        original_province_map_path: Path,
        destination_province_map_path: Path,
        conversion_scale: float,
        conversion_offset: tuple[int, int],
        destination_dimensions: tuple[int, int],
):
    """Convert the province map using nearest-neighbor scaling and converting to RGB 8bpc."""
    try:
        original_image = Image.open(original_province_map_path)
    except FileNotFoundError:
        print(f"Error: Original heightmap not found at {original_province_map_path}")
        return
    except Exception as e:
        print(f"Error opening image {original_province_map_path}: {e}")
        return
    
    # Convert to 8bpc RGB
    if original_image.mode != 'RGB':
        print(f"Converting image {original_province_map_path} to 8bpc RGB ('RGB' mode)")
        original_image = original_image.convert('RGB')

    original_dimensions = original_image.size
    try:
        resized_image = original_image.resize(
            (
                int(original_dimensions[0] * conversion_scale),
                int(original_dimensions[1] * conversion_scale)
            ),
            Image.Resampling.NEAREST
        )
    except ValueError as e:
        print(f"Error resizing image: {e}. Check conversion_scale.")
        return

    final_image = Image.new(resized_image.mode, destination_dimensions, 0)
    paste_x, paste_y = conversion_offset
    final_image.paste(resized_image, (paste_x, paste_y))

    try:
        final_image.save(destination_province_map_path, "PNG")
        print(f"Successfully saved converted province map to {destination_province_map_path}")
    except Exception as e:
        print(f"Error saving image {destination_province_map_path}: {e}")
