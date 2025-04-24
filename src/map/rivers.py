from pathlib import Path
from PIL import Image, ImageChops
import numpy as np
from dataclasses import dataclass
from typing import Optional, List, Tuple
from scipy.interpolate import interp1d
import random

# River map color constants
RIVER_COLORS = {
    'SOURCE': (0, 255, 0),      # Pure green: river source
    'TRIBUTARY': (255, 0, 0),   # Pure red: tributary joining
    'SPLIT': (255, 252, 0),     # Pure yellow: river splitting
    'WATER': (255, 0, 128),     # Magenta: sea/lakes/navigable rivers
    'LAND': (255, 255, 255),    # White: land
}

@dataclass
class RiverPoint:
    x: float
    y: float
    color: tuple[int, int, int]

class River:
    def __init__(self):
        self.points: List[RiverPoint] = []
        self.tributaries: List[Tuple[River, int]] = []  # Now stores (tributary, parent_point_index)
        self.start_pixel_color_type: str = ''
        self.end_pixel_color_type: str = ''
    
    def scale(self, factor: float, offset: tuple[int, int], deletion_rate: float = 0) -> 'River':
        """Scale the river curve by a factor and ensure tributaries stay connected"""
        # Scale main river points
        scaled_points = []
        for point in self.points:
            scaled_points.append(RiverPoint(
                x=point.x * factor + offset[0],
                y=point.y * factor + offset[1],
                color=point.color
            ))
        self.points = scaled_points

        # Scale tributaries and ensure they stay connected
        for tributary, parent_idx in self.tributaries:
            # Get the parent point where this tributary connects
            parent_point = self.points[parent_idx]
            
            # Scale tributary
            tributary.scale(factor, offset, deletion_rate)
            
            # Adjust tributary's first point to match parent point
            if tributary.points:
                tributary.points[0] = RiverPoint(
                    x=parent_point.x,
                    y=parent_point.y,
                    color=tributary.points[0].color
                )
        
        return self

    def follow(self, start_pixel: RiverPoint, image_array: np.ndarray, visited: set):
        """Follow the river from the start pixel, building the river structure"""
        current = start_pixel
        self.points.append(current)
        visited.add((int(current.x), int(current.y)))

        while True:
            x, y = int(current.x), int(current.y)
            neighbors = [(x+1, y), (x-1, y), (x, y+1), (x, y-1)]
            
            next_point = None
            for nx, ny in neighbors:
                if (nx, ny) in visited:
                    continue
                    
                if 0 <= nx < image_array.shape[1] and 0 <= ny < image_array.shape[0]:
                    color = tuple(image_array[ny, nx])
                    
                    if color == RIVER_COLORS['TRIBUTARY']:
                        # Store the tributary with the index of its parent point
                        tributary = River()
                        tributary.start_pixel_color_type = 'TRIBUTARY'
                        tributary.follow_tributary(RiverPoint(nx, ny, color), image_array, visited)
                        self.tributaries.append((tributary, len(self.points) - 1))
                    elif color != RIVER_COLORS['LAND']:
                        next_point = RiverPoint(nx, ny, color)
                        break
            
            if next_point is None:
                break
                
            current = next_point
            self.points.append(current)
            visited.add((int(current.x), int(current.y)))

    def follow_tributary(self, start_pixel: RiverPoint, image_array: np.ndarray, visited: set):
        """Follow tributary from its joining point"""
        self.follow(start_pixel, image_array, visited)

# Start with the main river and build tributaries on the way
 
def convert_rivers_map(
        original_rivers_map_path: Path,
        destination_rivers_map_path: Path,
        conversion_scale: float,
        conversion_offset: tuple[int, int],
        destination_dimensions: tuple[int, int],
):
    """Convert rivers using vector-based scaling"""
    # Load original image
    original_image = Image.open(original_rivers_map_path)
    if original_image.mode != 'RGB':
        original_image = original_image.convert('RGB')
    
    # Convert to numpy array for easier pixel access
    image_array = np.array(original_image)
    
    # Find all river systems (starting from green source pixels)
    river_systems = []
    visited = set()
    print("Following rivers...")
    for y in range(image_array.shape[0]):
        for x in range(image_array.shape[1]):
            if tuple(image_array[y, x]) == RIVER_COLORS['SOURCE'] and (x, y) not in visited:
                river = River()
                start_pixel = RiverPoint(x, y, RIVER_COLORS['SOURCE'])
                river.start_pixel_color_type = 'SOURCE'
                river.follow(start_pixel, image_array, visited)
                river_systems.append(river)
    
    # Scale river systems
    for system in river_systems:
        system.scale(conversion_scale, conversion_offset, deletion_rate=0.)
    
    # Create new image
    final_image = Image.new('RGB', destination_dimensions, RIVER_COLORS['LAND'])
    
    print("Drawing rivers...")
    # Draw scaled rivers
    for system in river_systems:
        draw_river_system(final_image, system)
    
    # Save result
    final_image.save(destination_rivers_map_path, "PNG")

def draw_river_system(image: Image.Image, river: River):    
    """Draw a river system onto the image using exact pixel placement"""
    pixels = image.load()
    drawn_pixels = set()  # Keep track of all pixels drawn by main rivers
    special_points = []  # Store (x, y, color) tuples for special points
    
    def get_line_pixels(p1: RiverPoint, p2: RiverPoint) -> List[Tuple[int, int]]:
        """Get all pixels for a line segment using Bresenham's algorithm"""
        x1, y1 = int(round(p1.x)), int(round(p1.y))
        x2, y2 = int(round(p2.x)), int(round(p2.y))
        line_pixels = []
        
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        
        x, y = x1, y1
        step_x = 1 if x1 < x2 else -1
        step_y = 1 if y1 < y2 else -1
        
        if dx > dy:
            err = dx / 2
            while x != x2:
                x += step_x
                err -= dy
                if err < 0:
                    y += step_y
                    err += dx
                if 0 <= x < image.width and 0 <= y < image.height:
                    line_pixels.append((x, y))
        else:
            err = dy / 2
            while y != y2:
                y += step_y
                err -= dx
                if err < 0:
                    x += step_x
                    err += dy
                if 0 <= x < image.width and 0 <= y < image.height:
                    line_pixels.append((x, y))
        
        return line_pixels

    # Draw main river first - collect all pixels
    main_river_pixels = []
    if len(river.points) > 1:
        # Get all segments
        for i in range(len(river.points) - 1):
            p1, p2 = river.points[i], river.points[i + 1]
            # Use regular blue color for the line
            color = p2.color
            if color in [RIVER_COLORS['SOURCE'], RIVER_COLORS['TRIBUTARY'], RIVER_COLORS['SPLIT']]:
                color = p1.color  # Use previous point's color
            pixels_in_segment = get_line_pixels(p1, p2)
            main_river_pixels.extend((x, y, color) for x, y in pixels_in_segment)
        
        # Store source point if it exists
        if river.start_pixel_color_type == 'SOURCE':
            start_x, start_y = int(round(river.points[0].x)), int(round(river.points[0].y))
            special_points.append((start_x, start_y, RIVER_COLORS['SOURCE']))
        
        # Draw main river and track pixels
        for x, y, color in main_river_pixels:
            pixels[x, y] = color
            drawn_pixels.add((x, y))

    # Draw tributaries
    for tributary, parent_idx in river.tributaries:
        if len(tributary.points) > 1:
            # Collect all tributary pixels first
            tributary_pixels = []
            for i in range(len(tributary.points) - 1):
                p1, p2 = tributary.points[i], tributary.points[i + 1]
                # Use regular blue color
                color = p2.color
                if color in [RIVER_COLORS['SOURCE'], RIVER_COLORS['TRIBUTARY'], RIVER_COLORS['SPLIT']]:
                    color = p1.color
                pixels_in_segment = get_line_pixels(p1, p2)
                tributary_pixels.extend((x, y, color) for x, y in pixels_in_segment)
            
            # Find first intersection with main river
            first_intersection = None
            for i, (x, y, _) in enumerate(tributary_pixels):
                if (x, y) in drawn_pixels:
                    first_intersection = i
                    break
            
            if first_intersection is not None:
                # Remove all pixels up to and including intersection
                tributary_pixels = tributary_pixels[first_intersection + 1:]
            
            if tributary_pixels:
                # Add tributary marker at first remaining point
                first_x, first_y, _ = tributary_pixels[0]
                special_points.append((first_x, first_y, RIVER_COLORS['TRIBUTARY']))
                
                # Draw remaining tributary pixels
                for x, y, color in tributary_pixels[1:]:
                    if (x, y) not in drawn_pixels:  # Extra safety check
                        pixels[x, y] = color

    # Draw all special points last
    for x, y, color in special_points:
        if 0 <= x < image.width and 0 <= y < image.height:
            pixels[x, y] = color
