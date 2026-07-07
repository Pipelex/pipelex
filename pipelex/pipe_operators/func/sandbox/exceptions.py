from pipelex.base_exceptions import PipelexError


class SandboxError(PipelexError):
    """Base for failures of the sandbox execution path (provisioning, transport, or in-box run)."""


class SandboxProvisioningError(SandboxError):
    """The sandbox could not be created/reached (subprocess spawn failure, box provisioning failure).

    Infrastructure-class: the customer's code never ran. Retryable by policy at the activity layer.
    """


class SandboxExecutionError(SandboxError):
    """The in-box run failed or returned no usable result (non-zero exit, unreadable result payload).

    Wraps the box's captured stderr so the failure is visible rather than an opaque exit code.
    """
