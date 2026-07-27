# Getting Started

Get up and running with Resource Flow in minutes.

---

## Installation

Install Resource Flow directly from GitHub using `pip`:

```bash
pip install git+https://github.com/ThomasKottenhahn/resource-flow.git
```

To verify installation, check the CLI tool availability:

```bash
rflow --help
```

---

## Writing Your First `.rf` File

Create a file named `salad.rf`:

```text
slice_tomatoes: 200 g tomatoes * -> 200 g tomatoes [sliced];
chop_lettuce: 100 g lettuce * -> 100 g lettuce [chopped];
make_dressing: 15 ml olive_oil *, 5 ml lemon_juice * -> 20 ml dressing;
mix_salad: 200 g tomatoes [sliced], 100 g lettuce [chopped], 20 ml dressing -> 320 g salad;

make 320 g salad;
```


---

## Running the Solver

Execute `rflow` against your `.rf` file:

```bash
rflow salad.rf
```

### Outputting Files

Export the step-by-step execution report and Mermaid flowchart to an output directory:

```bash
rflow salad.rf -o ./build
```

This generates:
- `./build/plan.txt`: Text report detailing total basic resources, total costs, and process execution order.
- `./build/flow.mermaid`: Mermaid TD flowchart visualizing process nodes and inputs/outputs.
