# Resource Flow

[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://ThomasKottenhahn.github.io/resource-flow/)

Resource Flow is a domain-specific language for modeling processes. The idea is to make processes as small as possible and by querying for an end product the language will calculate the required input products and steps to take to make the end product.

## Features
- **DAG Solver**: Scales input dependencies backwards from queries to sources.
- **Execution Plan Visualization**: Generates Mermaid TD diagram text representing execution graphs.
- **Unit Propagation & Conversion**: Automatic unit conversions (e.g., `g` <-> `kg`, `ml` <-> `l`) and compatibility checks.

---

## DSL Example
Here is a recipe example (`examples/05_tomato_pasta.rf`):
```text
make_sauce: 500 g tomatoes *, 50 g onions *, 20 ml oil * -> 500 g tomato_sauce;
boil_pasta: 250 g dry_pasta *, 1000 ml water * -> 700 g cooked_pasta;
combine: 700 g cooked_pasta, 500 g tomato_sauce -> 1100 g tomato_pasta;

make 1100 g tomato_pasta;
```
*Note: Resources marked with a `*` are basic ingredients (raw materials).*

---

## Installation

Install with pip:

```bash
pip install git+https://github.com/ThomasKottenhahn/resource-flow.git
```

## VS Code Extension

Resource Flow comes with a Language Server Protocol (LSP) extension for VS Code that provides syntax highlighting, real-time diagnostics, and auto-completion.

To install it:
1. Ensure the `rflow` Python package is installed (see above) so the Language Server can run.
2. Build the extension package from source:
   ```bash
   cd vscode-extension/resource-flow
   npm install -g @vscode/vsce
   vsce package
   ```
3. Install the generated `.vsix` file in VS Code:
   - Go to the **Extensions** view (`Ctrl+Shift+X`)
   - Click the `...` menu in the top right corner
   - Select **Install from VSIX...**
   - Choose the `resource-flow-0.0.1.vsix` file you just built.


## Quick Start CLI Usage

Once installed, you can use the command `rflow`:

### 1. Print to Terminal
```bash
rflow examples/02_salad.rf
```

### 2. Export to Files
Write the compiled plan and visualization graph to a directory:
```bash
rflow examples/02_salad.rf -o ./build
```
This saves:
- `./build/plan.txt` — The step-by-step recipe execution report.
- `./build/flow.mermaid` — The Mermaid JS flowchart representation.

---

## Roadmap

- **Suppliers**: Get resources from different suppliers and include acquisition in the plan.
- **Parralel Processes**: Allow for multiple processes to run in parralel if tools are available.
- **Deadlines**: Finish a query by a specified time.
- **Rest**: Include min and max rest times for resources.
- **Stock**: Define which resources are in stock and use up stock before buying new resources.

## License

Resource Flow is licensed under an MIT license.