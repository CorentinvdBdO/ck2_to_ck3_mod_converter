from pathlib import Path
from typing import Dict, Tuple, List, Optional
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
    """
    lines_with_comments = file_reader(file_path)
    content = compact_lines([line for line, _ in lines_with_comments])
    
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
                    (?P<value>\w+)                    # Simple value
                    |"(?P<string>[^"]+)"             # Quoted string
                    |(?P<block>\{)                   # Opening brace
                    |(?P<date>\d+\.\d+\.\d+)         # Date
                )
                |(?P<enum>\w+)(?!\s?=)               # Enumeration (not followed by =)
                ''', content, re.VERBOSE)
            
            if not match:
                # Skip unmatched content
                content = content[1:]
                continue
                
            if match.group('enum'):
                # Handle enumeration
                enum_value = match.group('enum')
                if 'enum' not in result:
                    result['enum'] = []
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
                result[key] = nested_dict
                content = content[block_start + block_end:].lstrip()
            elif match.group('string'):
                result[key] = match.group('string')
                content = content[match.end():].lstrip()
            elif match.group('date'):
                result[key] = match.group('date')
                content = content[match.end():].lstrip()
            else:
                result[key] = match.group('value')
                content = content[match.end():].lstrip()
        
        return result, ''

    parsed_dict, _ = parse_block(content)
    return parsed_dict