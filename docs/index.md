# Resource Flow

**Resource Flow** is a domain-specific language (DSL) and execution engine for process modeling.

Instead of manually calculating raw material dependencies or steps for complex workflows (such as recipes, manufacturing pipelines, or assembly lines), Resource Flow lets you define processes and query for a target end-product. The engine automatically computes input material requirements, scales batch dependencies backwards through a Directed Acyclic Graph (DAG), normalizes unit conversions, and generates step-by-step execution plans.

---

## Key Features

- **DAG Solver**: Scales input dependencies backwards from queries (`make <quantity> <resource>;`) to raw basic resources.
- **Execution Plan Visualization**: Generates Mermaid TD diagram text representing execution graphs.
- **Cost and Time Aggragation**: Attach costs to basic resources (`300 g carrots * [cost: 20]`) and processes (`cut [time: 2 min, cost: 1]: 300 g carrots -> 290 g carrots [cut]`). The solver will aggregate the metrics to give you insights in the entire process.

---

## Quick Example

```text
make_sauce [time: 15 min]: 
    250 g tomatoes * [cost: 3.00], 25 g onions * [cost: 0.50], 10 ml oil * [cost: 0.02] 
    -> 250 g tomato_sauce;

boil_pasta [time: 10 min]: 
    250 g dry_pasta * [cost: 1.50], 1000 ml water *
    -> 350 g cooked_pasta;

combine [time: 5 min]: 
    700 g cooked_pasta, 500 g tomato_sauce 
    -> 1100 g tomato_pasta;

make 1100 g tomato_pasta;
```

When solved with `rflow`, this computes the exact required raw ingredients (`500 g tomatoes`, `50 g onions`, `20 ml oil`, `500 g dry_pasta`, `2000 ml water`) and produces an execution plan.
