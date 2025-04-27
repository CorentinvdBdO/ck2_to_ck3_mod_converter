from pathlib import Path
from typing import Dict, Tuple, List, Optional, Union, Any
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
    
    Special handling:
    - Conditions with <, >, <=, >= are kept as raw strings only at innermost level
    - Single enum dictionaries are converted to lists
    """
    lines_with_comments = file_reader(file_path)
    content = compact_lines([line for line, _ in lines_with_comments])
    
    def convert_number(value: str) -> Union[int, float]:
        """Convert string to int or float based on presence of decimal point"""
        return float(value) if '.' in value else int(value)
    
    def convert_enum_dicts(obj: Union[Dict, List, Any]) -> Union[Dict, List, Any]:
        """Recursively convert enum-only dicts to lists"""
        if isinstance(obj, dict):
            # First convert all nested structures
            converted = {k: convert_enum_dicts(v) for k, v in obj.items()}
            # Then check if this is an enum-only dict
            if len(converted) == 1 and 'enum' in converted:
                return converted['enum']
            return converted
        elif isinstance(obj, list):
            return [convert_enum_dicts(item) for item in obj]
        return obj
    
    def is_condition_block(content: str) -> bool:
        """Check if block contains condition operators"""
        condition_patterns = [
            # r'\b(OR|AND|NOR|NOT|NAND)\s*=\s*{',  # Logic operators as block starters
            r'\w+\s?[<>]=?\s?[\d\.]+',  # <, >, <=, >= followed by number
            # r'opinion\s*=\s*{\s*who\s*=.*value\s*[<>]=?',  # Opinion blocks with conditions
        ]
        return any(re.match(r'^\s*' + pattern, content) for pattern in condition_patterns)

    def find_matching_brace(content: str) -> int:
        """Find the position of matching closing brace, handling nested braces"""
        count = 1
        pos = 0
        while count > 0 and pos < len(content):
            if content[pos] == '{':
                count += 1
            elif content[pos] == '}':
                count -= 1
            pos += 1
        return pos if count == 0 else -1

    def parse_condition(content: str) -> Dict:
        """Parse a condition string into a dictionary"""
        # Handle simple comparisons like "age < 6"
        match = re.match(r'\s*(\w+)\s*([<>]=?)\s*(\d+)\s*', content)
        if match:
            key, op, value = match.groups()
            return {key: {'operator': op, 'value': int(value)}}
            
        # Handle simple equality like "culture = norwegian"
        match = re.match(r'\s*(\w+)\s*=\s*(\w+)\s*', content)
        if match:
            key, value = match.groups()
            return {key: value}
            
        # If no pattern matches, return as-is
        return {'raw_condition': content.strip()}

    def parse_block(content: str) -> Tuple[Dict, str]:
        """Parse a block of content recursively"""
        result = {}
        while content:
            content = content.lstrip()
            if not content or content.startswith('}'):
                return result, content[1:] if content else ''
            
            match = re.match(r'''
                (?P<key>[\w\.]+)\s?=\s?                   # Key = 
                (
                    (?P<value>-?\d+\.?\d*|yes|no|\w+)  # Simple value
                    |"(?P<string>[^"]+)"             # Quoted string
                    |(?P<block>\{)                   # Opening brace
                    |(?P<date>\d+\.\d+\.\d+)         # Date
                )
                |(?P<enum>-?\d+\.?\d*|\w+)(?!\s?=)    # Enumeration
                ''', content, re.VERBOSE)
            
            if not match:
                content = content[1:]
                continue
                
            if match.group('enum'):
                # Handle enumeration
                enum_value = match.group('enum')
                if 'enum' not in result:
                    result['enum'] = []
                if re.match(r'-?\d+\.?\d*', enum_value):
                    enum_value = convert_number(enum_value)
                result['enum'].append(enum_value)
                content = content[match.end():].lstrip()
                continue
            
            key = match.group('key')
            
            if match.group('block') is not None:
                block_start = match.end()
                block_end = find_matching_brace(content[block_start:])
                if block_end == -1:
                    raise ValueError(f"Unmatched brace in block starting with key {key}")
                
                block_content = content[block_start:block_start + block_end - 1].strip()
                
                # Check if any part of the block contains conditions
                has_conditions = is_condition_block(block_content)
                
                if has_conditions:
                    # Keep the entire block as a raw string if it contains conditions
                    parsed_content = block_content
                else:
                    # Parse normally if no conditions
                    nested_dict, _ = parse_block(block_content)
                    parsed_content = nested_dict
                
                if key in result:
                    if not isinstance(result[key], list):
                        result[key] = [result[key]]
                    result[key].append(parsed_content)
                else:
                    result[key] = parsed_content
                
                content = content[block_start + block_end:].lstrip()
            else:
                # Handle other value types
                if match.group('string'):
                    value = match.group('string')
                elif match.group('date'):
                    value = match.group('date')
                else:
                    value = match.group('value')
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
    return convert_enum_dicts(parsed_dict)