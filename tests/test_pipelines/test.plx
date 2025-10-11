
domain = "test"

[pipe.read_doc_file]
type = "PipeFunc"
description = "Read the content of related codebase files"
inputs = { related_file_paths = "FilePath" }
output = "CodebaseFileContent"
function_name = "read_file_content"

