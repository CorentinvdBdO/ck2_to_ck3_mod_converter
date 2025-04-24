FROM_FOLDER = "Faerun/Faerun"
TO_FOLDER = "converted_mods"
NEW_MOD_NAME = "faerun_ck3"

from src.converter import convert_mod

convert_mod(
    FROM_FOLDER, 
    TO_FOLDER,
    NEW_MOD_NAME,
    destination_dimensions=(8192, 4096), # Same as CK3 base map
    conversion_scale = 5918./4096.,      # Scale for 1:1 Fareun
    conversion_offset=(-146, 26)         # Offset for Faerun chosen placement
)
