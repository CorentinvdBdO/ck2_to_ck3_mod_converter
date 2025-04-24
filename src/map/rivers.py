from pathlib import Path
from PIL import Image, ImageChops
import numpy as np
from dataclasses import dataclass
from typing import Optional, List, Tuple
from scipy.interpolate import interp1d

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
        self.tributaries: List[River] = []
        self.start_pixel_color_type: str = ''
        self.end_pixel_color_type: str = ''
    
    def scale(self, factor: float) -> 'River':
        """Scale the river curve by a factor"""
        scaled_river = River()
        scaled_river.start_pixel_color_type = self.start_pixel_color_type
        scaled_river.end_pixel_color_type = self.end_pixel_color_type
        
        # Scale points
        if len(self.points) > 1:
            # Get x and y coordinates as separate arrays
            x_coords = np.array([p.x for p in self.points])
            y_coords = np.array([p.y for p in self.points])
            
            # Scale coordinates
            x_scaled = x_coords * factor
            y_scaled = y_coords * factor
            
            # Create interpolation parameter (distance along the curve)
            t = np.arange(len(self.points))
            t_new = np.linspace(0, len(self.points) - 1, int(len(self.points) * factor))
            
            # Interpolate points along the curve
            if len(self.points) > 2:
                # Use cubic interpolation for smoother curves
                fx = interp1d(t, x_coords, kind='cubic')
                fy = interp1d(t, y_coords, kind='cubic')
            else:
                # Use linear interpolation for short segments
                fx = interp1d(t, x_coords, kind='linear')
                fy = interp1d(t, y_coords, kind='linear')
            
            x_new = fx(t_new)
            y_new = fy(t_new)
            
            # Create new points with interpolated colors
            for i in range(len(t_new)):
                # Find position in original curve for color interpolation
                pos = t_new[i] / (len(self.points) - 1)
                idx = int(pos * (len(self.points) - 1))
                color = self.points[idx].color
                scaled_river.points.append(RiverPoint(x_new[i], y_new[i], color))
        
        # Scale tributaries
        scaled_river.tributaries = [t.scale(factor) for t in self.tributaries]
        return scaled_river

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
                        tributary = River()
                        tributary.start_pixel_color_type = 'TRIBUTARY'
                        tributary.follow_tributary(RiverPoint(nx, ny, color), image_array, visited)
                        self.tributaries.append(tributary)
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
    
    for y in range(image_array.shape[0]):
        for x in range(image_array.shape[1]):
            if tuple(image_array[y, x]) == RIVER_COLORS['SOURCE'] and (x, y) not in visited:
                river = River()
                start_pixel = RiverPoint(x, y, RIVER_COLORS['SOURCE'])
                river.start_pixel_color_type = 'SOURCE'
                river.follow(start_pixel, image_array, visited)
                river_systems.append(river)
    
    # Scale river systems
    scaled_systems = [system.scale(conversion_scale) for system in river_systems]
    
    # Create new image
    final_image = Image.new('RGB', destination_dimensions, RIVER_COLORS['LAND'])
    
    # Draw scaled rivers
    for system in scaled_systems:
        draw_river_system(final_image, system, conversion_offset)
    
    # Save result
    final_image.save(destination_rivers_map_path, "PNG")

def draw_river_system(image: Image.Image, river: River, offset: tuple[int, int]):
    """Draw a river system onto the image using exact pixel placement"""
    pixels = image.load()
    
    def draw_line(p1: RiverPoint, p2: RiverPoint):
        """
        Draw a line segment between two points using exact pixel placement.
        Only colors pixels that lie exactly on the mathematical line.
        """
        x1, y1 = p1.x + offset[0], p1.y + offset[1]
        x2, y2 = p2.x + offset[0], p2.y + offset[1]
        
        # Calculate line length
        length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if length == 0:
            # Handle single point case
            px, py = int(round(x1)), int(round(y1))
            if 0 <= px < image.width and 0 <= py < image.height:
                pixels[px, py] = p1.color
            return
        
        # Calculate how many pixels we need (round up to ensure we don't miss pixels)
        num_points = abs(int(length * 1.5) + 1)
        
        # Generate points along the line
        for i in range(num_points):
            t = i / (num_points)
            # Linear interpolation
            x = x1 + t * (x2 - x1)
            y = y1 + t * (y2 - y1)
            
            # Round to nearest pixel
            px, py = int(round(x)), int(round(y))
            
            # Check bounds and draw if valid
            if 0 <= px < image.width and 0 <= py < image.height:
                # Determine color based on position along the line
                color = p1.color if t < 0.5 else p2.color
                pixels[px, py] = color
    
    # Draw main river
    for i in range(len(river.points) - 1):
        draw_line(river.points[i], river.points[i + 1])
    
    # Draw tributaries
    for tributary in river.tributaries:
        draw_river_system(image, tributary, offset)
