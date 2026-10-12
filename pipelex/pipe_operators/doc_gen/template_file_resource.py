from pipelex.core.bundle_resources.bundle_resource import BundleResource, canonical_resource_path_or_none
from pipelex.interpreter_hub import get_library


def bundle_resource_of_template_file(*, template_file: str) -> BundleResource | None:
    """The file submitted with the bundle under the path a step's `template_file` names, or None when none was.

    Looked up in the current library, which holds the files submitted with the bundles it loaded from content strings
    and the ones a transported crate carries: the factory reads an HTML template from it when the step is built, and
    the step reads an office template from it when it composes, so the run's own copy is the one it prints.
    """
    canonical_path = canonical_resource_path_or_none(path=template_file)
    if canonical_path is None:
        return None
    return get_library().bundle_resources.get(canonical_path)
