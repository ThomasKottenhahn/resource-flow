# Resource Flow VS Code Extension

This is the official Visual Studio Code extension for **Resource Flow**, a domain-specific language for calculating manufacturing resource flows.

## Features

- **Syntax Highlighting**: Beautiful colorization for Resource Flow (`.rf`) files, including keywords, resources, goals, constraints, macros, and comments.
- **Diagnostics**: Real-time syntax error reporting (red squiggles) powered by the Resource Flow Language Server.
- **Auto-Complete**: Intelligent suggestions for resource names you've defined in the current document.

## Requirements

This extension requires the `rflow` Python package to be installed and available in your environment, as it spawns the Language Server via the `rflow lsp` command.

```bash
pip install resource-flow
```

## Release Notes

### 0.0.1
Initial release of the Resource Flow extension. Includes syntax highlighting, basic parser diagnostics, and local autocomplete.
