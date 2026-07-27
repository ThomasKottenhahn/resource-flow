# CLI Reference

Resource Flow provides the command-line utility `rflow` for parsing, solving, and generating reports from `.rf` files.

---

## Usage Syntax

```bash
rflow <file_path> [-o <output_directory>]
```

### Options

| Option | Short | Description |
| :--- | :--- | :--- |
| `--output-dir` | `-o` | Optional output directory where `plan.txt` and `flow.mermaid` are exported. |
| `--help` | `-h` | Show help message and exit. |

---

## Examples

### Terminal Execution

Print execution summary to stdout:

```bash
rflow examples/05_tomato_pasta.rf
```

### Export Execution Plan & Mermaid Graph

Save execution plan and graph visualization:

```bash
rflow examples/05_tomato_pasta.rf -o ./build
```

Generated files:
- **`./build/plan.txt`**: Detailed process execution schedule, scaled input quantities, and aggregated costs.
- **`./build/flow.mermaid`**: Mermaid TD flowchart string.
