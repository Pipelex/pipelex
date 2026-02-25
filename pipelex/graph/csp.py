"""Content Security Policy (CSP) constants for graph HTML output.

Pipelex generates standalone HTML files with embedded JavaScript and CSS.
When loaded into a VS Code webview, these need CSP nonce support.

The sentinel nonce is embedded in the HTML by Pipelex. The VS Code extension
replaces it with a real cryptographic nonce and injects a CSP meta tag.
Standalone browser use is unaffected (no CSP meta tag = nonces are ignored).
"""

CSP_NONCE_SENTINEL = "PIPELEX_CSP_NONCE"
