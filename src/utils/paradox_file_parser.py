from pathlib import Path
from typing import Dict, Tuple, List, Optional, Union
import re
from pprint import pprint   

def file_reader(file_path: Path) -> List[Tuple[str, Optional[str]]]:
    """
    Reads a file and returns a list of tuples containing (line_content, comment).
    
    Args:
        file_path: Path to the file to read
        
    Returns:
        List of tuples where each tuple contains:
        - The content of the line (stripped, without comments)
        - The comment if present (including the # character), or None if no comment
    """
    result = []
    
    try:
        with open(file_path, "r", encoding='utf-8-sig') as file:  # Use utf-8-sig for potential BOM
            for line in file:
                original_line = line.strip()
                
                # Handle empty lines
                if not original_line:
                    result.append(("", None))
                    continue
                
                # Handle pure comment lines
                if original_line.startswith("#"):
                    result.append(("", original_line))
                    continue
                
                # Handle lines with inline comments
                if "#" in original_line:
                    parts = original_line.split("#", 1)
                    content = parts[0].strip()
                    comment = "#" + parts[1] if len(parts) > 1 else None
                    result.append((content, comment))
                else:
                    # Lines without comments
                    result.append((original_line, None))
                    
    except FileNotFoundError:
        print(f"Warning: File not found at {file_path}")
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        
    return result

def compact_lines(lines: List[str]) -> List[str]:
    """
    Compact lines by removing empty lines (supposes comments already removed)
    """
    full_file = '\n'.join(lines)
    compact_file = re.sub(r'\s+', ' ', full_file).strip()
    return compact_file

def regex_paradox_parser(file_path: Path) -> Dict:
    """
    General regex parser for Paradox txt files.
    Returns a nested dictionary structure.
    
    Type conversion:
    - Integers: Matches \d+ or -\d+
    - Floats: Matches numbers with decimal points
    - Booleans: 'yes' -> True, 'no' -> False
    - Enums: Converts {enum: [1,2,3]} to [1,2,3]
    - Repeated keys: Converts {key=a, key=b} to {key:[a,b]}
    """
    def convert_repeated_keys(d: Dict) -> Dict:
        """Convert repeated keys into lists in dictionary"""
        if not isinstance(d, dict):
            return d
            
        # First convert all nested dictionaries
        result = {k: convert_repeated_keys(v) if isinstance(v, dict) else v 
                 for k, v in d.items()}
        
        # Then find keys that appear multiple times with same name
        keys = {}
        for k, v in result.items():
            if k not in keys:
                keys[k] = []
            keys[k].append(v)
            
        # Convert to lists where needed
        return {k: v[0] if len(v) == 1 else v for k, v in keys.items()}

    def convert_enum_dict(d: Dict) -> Union[Dict, List]:
        """Convert enum dictionary to list if it only contains an enum key"""
        if isinstance(d, dict):
            if len(d) == 1 and 'enum' in d:
                return d['enum']
            return {k: convert_enum_dict(v) for k, v in d.items()}
        return d

    lines_with_comments = file_reader(file_path)
    content = compact_lines([line for line, _ in lines_with_comments])
    
    def convert_number(value: str) -> Union[int, float]:
        """Convert string to int or float based on presence of decimal point"""
        return float(value) if '.' in value else int(value)

    def find_matching_brace(content: str) -> int:
        """Find the position of matching closing brace, handling nested braces"""
        count = 1  # We start after an opening brace
        pos = 0
        while count > 0 and pos < len(content):
            if content[pos] == '{':
                count += 1
            elif content[pos] == '}':
                count -= 1
            pos += 1
        return pos if count == 0 else -1

    def parse_block(content: str) -> Tuple[Dict, str]:
        """
        Parse a block of content recursively.
        Returns (parsed_dict, remaining_content)
        """
        result = {}
        while content:
            # Skip leading whitespace
            content = content.lstrip()
            if not content or content.startswith('}'):
                # End of block
                return result, content[1:] if content else ''
            
            # Match key-value or enumeration
            match = re.match(r'''
                (?P<key>[\w\.]+)\s?=\s?                   # Key = 
                (
                    (?P<value>-?\d+\.?\d*|yes|no|\w+)  # Simple value (including numbers and booleans)
                    |"(?P<string>[^"]+)"             # Quoted string
                    |(?P<block>\{)                   # Opening brace
                    |(?P<date>\d+\.\d+\.\d+)         # Date
                )
                |(?P<enum>-?\d+\.?\d*|\w+)(?!\s?=)    # Enumeration (not followed by =)
                ''', content, re.VERBOSE)
            
            if not match:
                # Skip unmatched content
                content = content[1:]
                continue
                
            if match.group('enum'):
                # Handle enumeration with type conversion
                enum_value = match.group('enum')
                if 'enum' not in result:
                    result['enum'] = []
                # Try to convert to number if it matches number pattern
                if re.match(r'-?\d+\.?\d*', enum_value):
                    enum_value = convert_number(enum_value)
                result['enum'].append(enum_value)
                content = content[match.end():].lstrip()
                continue
            
            key = match.group('key')
            
            if match.group('block') is not None:
                # Handle nested block with proper brace matching
                block_start = match.end()
                block_end = find_matching_brace(content[block_start:])
                if block_end == -1:
                    raise ValueError(f"Unmatched brace in block starting with key {key}")
                
                nested_content = content[block_start:block_start + block_end - 1]
                nested_dict, _ = parse_block(nested_content)
                
                # Handle repeated keys by converting to list
                if key in result:
                    if not isinstance(result[key], list):
                        result[key] = [result[key]]
                    result[key].append(nested_dict)
                else:
                    result[key] = nested_dict
                
                content = content[block_start + block_end:].lstrip()
            elif match.group('string'):
                value = match.group('string')
                if key in result:
                    if not isinstance(result[key], list):
                        result[key] = [result[key]]
                    result[key].append(value)
                else:
                    result[key] = value
                content = content[match.end():].lstrip()
            elif match.group('date'):
                value = match.group('date')
                if key in result:
                    if not isinstance(result[key], list):
                        result[key] = [result[key]]
                    result[key].append(value)
                else:
                    result[key] = value
                content = content[match.end():].lstrip()
            else:
                value = match.group('value')
                # Convert value types
                if re.match(r'-?\d+\.?\d*', value):
                    value = convert_number(value)
                elif value == 'yes':
                    value = True
                elif value == 'no':
                    value = False
                
                if key in result:
                    if not isinstance(result[key], list):
                        result[key] = [result[key]]
                    result[key].append(value)
                else:
                    result[key] = value
                content = content[match.end():].lstrip()
        
        return result, ''

    parsed_dict, _ = parse_block(content)
    # Apply both conversions
    parsed_dict = convert_repeated_keys(parsed_dict)
    return convert_enum_dict(parsed_dict)