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

## Make Queries

The `make` query specifies the end product demand:

```text
make 1100 g tomato_pasta;
make 300g salad;
```
