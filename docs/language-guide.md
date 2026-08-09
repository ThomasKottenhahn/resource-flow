# Language Guide

This reference explains the syntax, rules, and semantic conventions of the Resource Flow DSL.

---

## Grammar Overview

A `.rf` script consists of **Process Declarations** followed by one ore more **Query Statements**.

```text
<process_name>: <input_resource_list> -> <output_resource_list>;
make <quantity> <unit> <resource_name>;
```

---

## Processes

A process converts input resources into an output resource.

```text
boil_water: 1000 ml water * -> 1000 ml boiled_water;
```

- Every process has a unique identifier name followed by a colon (`:`).
- In- and Output resources are comma-separated.
- Output resource is indicated after the `->` arrow.

---

## Tools

Processes can require tools that are not consumed during the process. These are specified using the `with` keyword at the end of a process definition.

```text
cut: 500 g carrots * -> 450 g cut_carrots with 1 knife;
```

When writing a query, you can declare which tools are available `using`:

```text
make 450 g cut_carrots using 1 knife;
```

Tools do not flow through the graph as resources do. If a query requires multiple processes that share the same tool, a single instance of that tool satisfies all processes simultaneously.

---

## Cost, Time and Tags

Resources an processes can be tagged to reflect certain properties.

### Basic Resources (`*` tag)

Resources that are raw materials (inputs not produced by any process in your script) are marked with an asterisk (`*`):

```text
500 g flour *
20 ml olive_oil *
```

!!! note
    Basic resources declared anywhere in processes are globally recognized across the script graph.

---

### Cost & Time

Basic resources and prcesses can specify costs:

```text
300 g carrots * [cost: 20]
```
- This assigns 300g of carrots the cost of 20.
- When solving a query resource-flow automatically scales the cost.

```
bake [cost: 50, time: 30 min]: pie -> pie_baked;
```

- Both time and cost scale linearly with the process volume.

---

### Custom Tags

```
rise: dough -> dough [risen];
cut: carrots [organic, !frozen] -> carrots [organic, cut]
```

- You can spcify custom tags on resources.
- The first process returns dough with the risen tag.
- The second process requires carrots that are organic and not frozen.

## Units and Automatic Conversions

Resource Flow natively supports standard mass and volume units:

| Dimension | Supported Units | Standard Base Unit |
| :--- | :--- | :--- |
| **Mass** | `mg`, `g`, `kg` | `g` |
| **Volume** | `ml`, `l` | `ml` |
| **Count / Discrete** | raw names (e.g. `eggs`) | piece |

Unit conversions across compatible dimensions occur automatically:
- Requiring `1.5 kg flour` where a process outputs `500 g flour` will automatically scale the process execution factor `s = 3`.
- Incompatible conversions (e.g., mass `g` to volume `ml`) raise validation errors.

---

## Make Queries and Solver Goals

The `make` query specifies the end product demand. You can attach solver goals in brackets before `make` to control how alternative process routes are selected:

```text
make 1100 g tomato_pasta;

[cheapest] make 1100 g tomato_pasta;
[fastest] make 1100 g tomato_pasta;
[cheapest, fastest] make 1100 g tomato_pasta;
[min manual_labour, time <= 60 min] make 1100 g tomato_pasta;
```

### Supported Solver Goals
- **`[cheapest]`**: Minimizes total cost (`resource_cost` + `process_cost`).
- **`[fastest]`**: Minimizes total process execution duration.
- **`[any]`**: (Default when omitted) Returns the first valid recipe execution graph.
- **Multi-Goal Cascades**: e.g., `[cheapest, fastest]` evaluates goals left-to-right, using secondary goals to break ties.

### Custom Goals

You can define your own goal that operate on the tags used in your processes.

- **`min/max`**: Minimize or maximize the sum of the specified tag (tags without quantity will default to 1): `[min manual_labour]` will reduce the number of processes using the manual_labour tag
- **Relational goals**: Specify constraints that need to hold for your query. Use `<=`, `>=`, `<`, `>`, `==` and `!=` with a tag and number and optionally a unit: `[time < 5h]` will only allow for solutions with the total process time under 5 hours. If no solution with the constraint is possible, the solver will report the closest possible solution.