from pydantic import Field

from pipelex.system.configuration.config_model import ConfigModel


class PipeFuncConfig(ConfigModel):
    # Which PipeFunc execution mode this process runs, selected from the PipeFuncExecutorRegistry the
    # plugins populate (the config-selected-singleton seam, sibling of runtime.storage.method). An open
    # string token: "direct" (core, in-process — imports and runs the customer function here) is the
    # default; "daytona" (our Daytona sandbox plugin) runs it out-of-process. Any non-"direct" mode is a remote/sandbox
    # backend: library loading captures the method's files as they are (onto the crate) instead of
    # importing any of them, a PipeFunc's validation proves its function's form from the captured source,
    # and the function is imported, checked and run inside the sandbox, never here. This is a hosted-deploy concern, not a
    # client preference, so it is intentionally absent from the .pipelex/ override file.
    #
    # Lives in its own module (not configs.py) so the PipeFuncExecutorRegistry can type its factory
    # against it without importing the heavy configs module, which would close an import cycle through
    # aws_config -> hub. Mirrors how StorageProviderConfig sits in its own module.
    execution_mode: str = Field(strict=False)
