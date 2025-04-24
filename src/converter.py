from src.map.convert_map import convert_map
import git
from pathlib import Path
import shutil

mod_template = "https://github.com/bombusfrigidus/Atlantis"

def initialize_mod(
        to_folder: str,
        mod_name: str,
):  
    flat_name = mod_name.replace(" ", "_").lower()
    destination_path = Path(to_folder) / flat_name


    # destination has to be empty
    if destination_path.exists():
        # raise ValueError(f"Destination path     {destination_path} already exists. Please remove it before initializing a new mod.")
        shutil.rmtree(destination_path)

    # Clone the templatemod from github
    git.Repo.clone_from(mod_template, destination_path)

    # Replace the mod name in the mod.mod file
    # with open(Path(mod_path) / "mod.mod", "r") as file:
    #     mod_content = file.read()
    #     mod_content = mod_content.replace("Atlantis", mod_name)
    #     with open(Path(mod_path) / "mod.mod", "w") as file:
    #         file.write(mod_content)

    pass


def convert_mod(
        # Input / output
        from_folder: str,
        to_folder: str,
        mod_name: str,
        # Map conversion parameters
        destination_dimensions: tuple[int, int] = (8192, 4096),
        conversion_scale: float = 1.0,
        conversion_offset: tuple[int, int] = (0, 0),
        
):
    # Initialize the mod
    initialize_mod(to_folder, mod_name)
    mod_folder = Path(to_folder) / mod_name

    # Convert the map
    convert_map(
        from_folder,
        mod_folder,
        destination_dimensions,
        conversion_scale,
        conversion_offset
    )
