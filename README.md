# Resource Flow

Resource Flow is a domain-specific language for moddeling processes. The idea is to make processes as small as possible and by quering for an end product the language will calculate the required input products and steps to take to make the end product.

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

- **Tags**: Tag Resources and processes with costs, time and custom tags.
- **Different solver goals**: Solve for the cheapest or fastest recipe.
- **Tools**: Define tools used in processes and solve with a set of available tools.
- **Modules**: Organize code into different modules and solve queries with processes from other modules.
- **Stock**: Define which resources are in stock and use up stock before buying new resources.
- **Parralel Processes**: Allow for multiple processes to run in parralel if tools are available.

## License

Resource Flow is licensed under an MIT license.