from pathlib import Path
from PIL import Image
import numpy as np

default_curve = "0 0 0.11609779916158537 0 0.16708812351795393 0 0.24117917936991867 0 0.32469172187931633 0.0047780102825537574 0.35372965142045404 0.048227133620360574 0.36996233015322161 0.056717994885567058 0.3800659077336252 0.088662127213393171 0.48523363988043861 0.18455742111106588 0.6546260264696997 0.32451771881620761 0.87591033429730669 0.46060741678210571 0.97367036352794567 0.62462249086090704 0.99824867145155827 1"

def load_curve_scaled(curve_str: str) -> list[tuple[int, int]]:
    """Parses the curve string and scales points to 0-255 integer range."""
    # All points as floats 0.0-1.0
    points_float = [float(x) for x in curve_str.split()]
    # Make pairs (x, y)
    pairs_float = [points_float[i:i+2] for i in range(0, len(points_float), 2)]

    # Scale to 0-255 and convert to int tuples
    pairs_scaled = [(int(x * 255), int(y * 255)) for x, y in pairs_float]

    # Ensure points are sorted by input value (x)
    pairs_scaled.sort()

    # Ensure (0,0) and (255,255) exist for interpolation, similar to GIMP handling
    if not any(p[0] == 0 for p in pairs_scaled):
        pairs_scaled.insert(0, (0, 0))
    if not any(p[0] == 255 for p in pairs_scaled):
        # Find the correct insertion point if 255 isn't the max x
        idx = 0
        while idx < len(pairs_scaled) and pairs_scaled[idx][0] < 255:
            idx += 1
        pairs_scaled.insert(idx, (255, 255))

    # Remove duplicates that might have been added
    final_points = []
    seen_x = set()
    for p in pairs_scaled:
        if p[0] not in seen_x:
            final_points.append(p)
            seen_x.add(p[0])

    print(f"Parsed and scaled {len(final_points)} curve points.")
    return final_points

def generate_lut_from_curve(points: list[tuple[int, int]]) -> list[int]:
    """Generates a 256-entry LUT using linear interpolation between points."""
    if not points:
        # Return identity LUT if no points
        return list(range(256))

    x_coords, y_coords = zip(*points)
    # Ensure input x_coords are suitable for np.interp (must be increasing)
    # load_curve_scaled already sorts them, but double-check/handle edge cases if necessary
    if not np.all(np.diff(x_coords) >= 0):
         print("Warning: Curve points x-coordinates are not monotonically increasing. LUT might be incorrect.")
         # Attempt to fix by sorting again, though duplicates might cause issues
         sorted_indices = np.argsort(x_coords)
         x_coords = np.array(x_coords)[sorted_indices]
         y_coords = np.array(y_coords)[sorted_indices]


    lut = np.interp(range(256), x_coords, y_coords).astype(int)
    # Clamp values just in case interpolation goes slightly out of bounds
    lut = np.clip(lut, 0, 255)
    return list(lut)

default_curve_points = load_curve_scaled(default_curve) 
    

def convert_height_map(
        original_map_path: Path,
        converted_map_path: Path,
        conversion_scale: float,
        conversion_offset: tuple[int, int],
        destination_dimensions: tuple[int, int],
        curve_points: list[tuple[int, int]] | None = default_curve_points,
        fill_color: float = 0. # Black
):
    """
    take in map/topology.bpm
    Apply map scaling, new size and color curve to match CK3 map.
    return map_data/heightmap.png
    """
    # Open
    try:
        original_image = Image.open(original_map_path)
    except FileNotFoundError:
        print(f"Error: Original heightmap not found at {original_map_path}")
        return
    except Exception as e:
        print(f"Error opening image {original_map_path}: {e}")
        return

    # Convert to grayscale
    if original_image.mode != 'L':
        print(f"Converting image {original_map_path} to grayscale ('L' mode)")
        original_image = original_image.convert('L')

    # Resize
    original_dimensions = original_image.size
    try:
        resized_image = original_image.resize(
            (
                int(original_dimensions[0] * conversion_scale),
                int(original_dimensions[1] * conversion_scale)
            ),
            Image.Resampling.LANCZOS
        )
    except ValueError as e:
        print(f"Error resizing image: {e}. Check conversion_scale.")
        return

    # Offset
    final_image = Image.new(resized_image.mode, destination_dimensions, fill_color)
    paste_x, paste_y = conversion_offset
    final_image.paste(resized_image, (paste_x, paste_y))

    # Color curve
    if curve_points:
        print(f"Applying color curve using provided points.")
        lut = generate_lut_from_curve(curve_points)
        if len(lut) == 256:
            final_image = final_image.point(lut)
        else:
             print("Warning: Failed to generate valid LUT from curve points. Skipping curve application.")
    else:
        print("No curve points provided, skipping curve application.")

    # Save as Grayscale 8bpc PNG
    try:
        final_image.save(converted_map_path, "PNG")
        print(f"Successfully saved converted heightmap to {converted_map_path}")
    except Exception as e:
        print(f"Error saving image {converted_map_path}: {e}")