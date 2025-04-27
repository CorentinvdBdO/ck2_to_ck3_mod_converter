Convert as much as possible from ck2 to ck3 compatible TC mod. The developpement is tested with the [CK2 Faerun mod](https://github.com/ProjectFaerun/Faerun).

- Start from [Atlantis mod template](https://github.com/bombusfrigidus/Atlantis)
- Automatise  what it can + explain the manual steps
- Keep the comments as much as possible

# Side tools
This project allows for the creation of a few utility scripts beyond the specific context of ck2->ck3 conversion.

## Map utils
Map resizer & offset & auto save compatible with the game: heightmap, provinces, rivers.
- Status: In the code (no nice interface)

# Roadmap

## Scopes

- Map (resize and convert)
    - [X] Rescale, resize, offset
    - [X] Heightmap (grayscale rescaling)
    - [X] Provinces 
    - [X] Rivers (don't break the rivers even when resizing)
- Holdings
    - [ ] Keep only the baronnies activated in history & comment the others
    - [ ] Give a color to all kept baronies but only the first one gets assigned the map color
    - [ ] Voronoi based random barony placement within counties
    - [ ] Assign colors to ALL baronies
- Land titles
    - [ ] All de jure land titles
    - [ ] History
- Cultures
- Ethnicities (don't exist in CK2 + can't auto generate 3D models)
- Religions
- Characters
- History

## Games
Need to implement read, check and write capabilites for each game. For conversion from, need at least read and check, for conversion to, need at least check and write.

Then for each pair of games, implement the conversion logic.

### CK2
Read Check Write
- [X] [ ] [X] Map (heightmap, provinces, rivers)
- [X] [X] [ ] modifers
- [X] [X] [ ] traits (depends on modifiers)
- [ ] [ ] [ ] religions (depends on modifiers)
- [ ] [ ] [ ] cultures
- [ ] [ ] [ ] provinces (depends on modifiers, culture, religion, buildings, wonders)
- [ ] [ ] [ ] titles (depends on modifiers, culture, religion, provinces)
- [ ] [ ] [ ] characters

### CK3
Read Check Write
- [ ] [ ] [ ] modifers
- [ ] [ ] [ ] traits (depends on modifiers)
- [ ] [ ] [ ] religions (depends on modifiers)
- [ ] [ ] [ ] ethnicities
- [ ] [ ] [ ] cultures
- [ ] [ ] [ ] provinces (depends on modifiers, culture, religion, buildings, wonders)
- [ ] [ ] [ ] titles (depends on modifiers, culture, religion, provinces)
- [ ] [ ] [ ] characters

## Converter
### CK2 -> CK3
- [X] map (heightmap, provinces, rivers)
- [ ] holdings
- [ ] history
- [ ] titles
- [ ] provinces
- [ ] characters

## Utility

- One UI to own them all
- Map utils
- Reindexing
    - [ ] Province Ids
    - [ ] Characters Ids