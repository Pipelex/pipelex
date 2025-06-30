from typing import Any, Dict, List, Optional

from pipelex.tools.misc.attribute_utils import AttributePolisher
from pipelex.tools.misc.json_utils import purify_json_dict
from pipelex.tools.misc.string_utils import snake_to_capitalize_first_letter


def convert_to_markdown(data: Any, level: int = 1, is_pretty: bool = False, key: Optional[str] = None) -> str:
    """
    Convert arbitrary JSON-compatible Python data to a Markdown string
    without needing to specify the markdown type explicitly.
    """
    if isinstance(data, dict):
        the_dict: Dict[str, Any] = data
        # Treat keys as headings and values as their content
        dict_result_lines: List[str] = []
        for key, value in the_dict.items():
            heading_prefix = "#" * min(level, 6)  # Limit heading levels to 6
            # Use the key as a heading
            if is_pretty:
                converted_line = f"{heading_prefix} {snake_to_capitalize_first_letter(key)}"
            else:
                converted_line = f"{heading_prefix} {key}"
            # Convert the value recursively, increasing the heading level
            # dict_result_lines.append(convert_to_markdown(data=value, level=level + 1))
            converted_value = convert_to_markdown(data=value, level=level + 1, key=key)
            converted_value_nb_lines = len(converted_value.split("\n"))
            if converted_value_nb_lines > 1:
                dict_result_lines.append(converted_line)
                dict_result_lines.append(converted_value)
            else:
                dict_result_lines.append(f"{converted_line}: {converted_value}")
        return "\n\n".join(line for line in dict_result_lines if line.strip())

    elif isinstance(data, list):
        # Treat lists as bullet lists. If list items are complex,
        # they get recursively converted. If they are simple strings,
        # they become list items.
        if not data:
            return ""
        the_list: List[Any] = data
        list_result_lines: List[str] = []
        for item in the_list:
            # Convert the item first
            item_md = convert_to_markdown(item, level=level)
            # If the item is multiline, indent it, else just place it as a bullet
            lines = item_md.split("\n")
            # The first line as a bullet point
            first_line = f"- {lines[0]}"
            subsequent_lines = [f"  {line}" for line in lines[1:] if line.strip()]
            list_result_lines.append(first_line)
            list_result_lines.extend(subsequent_lines)
        return "\n".join(list_result_lines)

    elif isinstance(data, (str, int, float, bool)):
        # Simple scalar types become paragraphs (strings) or inline text
        # If it's a string with multiple lines, just output them as-is.
        str_value = str(data)
        if key and AttributePolisher.should_truncate(name=key, value=str_value):
            return str(AttributePolisher.get_truncated_value(name=key, value=str_value))
        return str_value

    elif data is None:
        # No value
        return "None"

    else:
        pure_dict, _ = purify_json_dict(data, is_warning_enabled=False)
        return convert_to_markdown(pure_dict, level=level)
