def is_variable_satisfied_by_inputs(variable_path: str, input_names: set[str]) -> bool:
    """Check if a variable path is satisfied by the declared inputs.

    A variable path is satisfied if:
    - It exactly matches an input name, OR
    - Its root (or any prefix) matches an input name (attribute access on an input)

    Args:
        variable_path: The full dotted variable path (e.g., 'page.text_and_images.text')
        input_names: Set of declared input names

    Returns:
        True if the variable path is satisfied by the inputs.
    """
    # Check for exact match
    if variable_path in input_names:
        return True

    # Check if any prefix of the path matches an input name
    parts = variable_path.split(".")
    for idx in range(1, len(parts)):
        prefix = ".".join(parts[:idx])
        if prefix in input_names:
            return True

    return False


def is_input_used_by_variables(input_name: str, variable_paths: set[str]) -> bool:
    """Check if an input is used by any of the variable paths.

    An input is considered used if:
    - It exactly matches a variable path, OR
    - It is a prefix of any variable path (the input is accessed via attributes)

    Args:
        input_name: The declared input name
        variable_paths: Set of full dotted variable paths used in the template

    Returns:
        True if the input is used by any variable path.
    """
    for var_path in variable_paths:
        # Exact match
        if var_path == input_name:
            return True
        # Input is a prefix of the variable path
        if var_path.startswith(input_name + "."):
            return True
    return False
