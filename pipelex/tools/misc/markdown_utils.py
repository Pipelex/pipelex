from typing import Any, Dict, List, Optional, cast

from pipelex.tools.misc.attribute_utils import AttributePolisher
from pipelex.tools.misc.json_utils import purify_json_dict
from pipelex.tools.misc.string_utils import snake_to_capitalize_first_letter


def convert_to_markdown(
    data: Any,
    level: int = 1,
    is_pretty: bool = False,
    key: Optional[str] = None,  # parent key used for truncation heuristics
) -> str:
    """
    Convert arbitrary JSON-compatible Python data to a Markdown string
    without needing to specify the markdown type explicitly.
    """
    if isinstance(data, dict):
        the_dict = cast(Dict[str, Any], data)  # <-- precise key/value types
        lines: List[str] = []
        for k, v in the_dict.items():
            heading_prefix = "#" * min(level, 6)
            heading_text = snake_to_capitalize_first_letter(k) if is_pretty else k
            heading_line = f"{heading_prefix} {heading_text}"

            rendered = convert_to_markdown(data=v, level=level + 1, key=str(k))
            rendered_lines = rendered.split("\n")
            if len(rendered_lines) > 1:
                lines.append(heading_line)
                lines.append(rendered)
            else:
                lines.append(f"{heading_line}: {rendered}")

        return "\n\n".join(line for line in lines if line.strip())

    elif isinstance(data, list):
        the_list = cast(List[Any], data)  # <-- precise element type
        if not the_list:
            return ""
        out_lines: List[str] = []
        for item in the_list:
            item_md = convert_to_markdown(item, level=level, key=key)
            parts = [p for p in item_md.split("\n")]
            first = f"- {parts[0]}"
            rest = [f"  {p}" for p in parts[1:] if p.strip()]
            out_lines.append(first)
            out_lines.extend(rest)
        return "\n".join(out_lines)

    elif isinstance(data, (str, int, float, bool)):
        s = str(data)
        if key and AttributePolisher.should_truncate(name=key, value=s):
            return str(AttributePolisher.get_truncated_value(name=key, value=s))
        return s

    elif data is None:
        return "None"

    else:
        # Fall back to a purified dict representation, then render
        purified, _ = purify_json_dict(data, is_warning_enabled=False)
        return convert_to_markdown(purified, level=level, is_pretty=is_pretty, key=key)
