# Language Guide

A step-by-step tutorial that teaches the Resource Flow DSL by building
progressively more complex recipes. Each step introduces one new concept and
includes a complete, runnable `.rf` example.

---

## Step 1 — Basics

A Resource Flow script defines **processes** that convert input resources into
output resources. Let's start with a simple tea recipe:

```text
boil_water: 500 ml water * -> 500 ml boiled_water;
steep_tea: 500 ml boiled_water, 5 g tea_leaves * -> 500 ml brewed_tea;
add_honey: 500 ml brewed_tea, 10 g honey * -> 500 ml sweet_tea;

make 500 ml sweet_tea;
```

Save this as `tea.rf` and run it:

```bash
rflow tea.rf
```

Here's what's happening:

- **Process declaration** — Each line before `make` defines a process.
  The label (`boil_water`, `steep_tea`, `add_honey`) is followed by a colon,
  then `inputs -> outputs`, terminated with `;`.
- **Basic resources** — The asterisk `*` marks a raw material that is supplied
  externally. `water`, `tea_leaves`, and `honey` are basic resources — they are
  not produced by any other process.
- **`make` query** — The `make` statement tells the solver what end product you
  want. The solver walks backwards through the process graph, computing the
  exact inputs needed.

---

## Step 2 — Units and Automatic Scaling

Resource Flow supports standard units and converts between them
automatically. Here are the supported unit families:

| Dimension | Supported Units |
| :--- | :--- |
| **Mass** | `mg`, `g`, `kg` |
| **Volume** | `ml`, `l` |
| **Count / Discrete** | `piece` |

What happens if you request more than a single batch? Take the tea recipe from
Step 1 and change the query:

```text
boil_water: 500 ml water * -> 500 ml boiled_water;
steep_tea: 500 ml boiled_water, 5 g tea_leaves * -> 500 ml brewed_tea;
add_honey: 500 ml brewed_tea, 10 g honey * -> 500 ml sweet_tea;

make 1 l sweet_tea;
```

The solver converts `1 l` to `1000 ml` and determines it needs to run every
process twice (scale factor = 2). All inputs scale linearly:

- `1000 ml water` (was 500)
- `10 g tea_leaves` (was 5)
- `20 g honey` (was 10)

Incompatible conversions — like mixing mass (`g`) and volume (`ml`) for the
same resource — produce an error.

---

## Step 3 — Tags and Constraints

Tags let you label resources with properties. The solver uses tags to choose
the right process path. Here's a stir-fry recipe where vegetables arrive
frozen and must be thawed before cooking:

```text
thaw: 300 g vegetables * [frozen] -> 300 g vegetables;
chop: 300 g vegetables [!frozen] -> 280 g vegetables [chopped];
stir_fry: 280 g vegetables [chopped], 15 ml oil * -> 280 g stir_fry;

make 280 g stir_fry;
```

- **Flag tags** — `[frozen]` and `[chopped]` are flag tags that track the state
  of a resource. `vegetables [frozen]` and `vegetables [chopped]` are treated
  as distinct resources.
- **Negated tags** — `[!frozen]` on `chop`'s input means "vegetables that are
  *not* frozen." The solver must route through `thaw` first, which strips the
  `[frozen]` tag, producing plain `vegetables` — which satisfies `[!frozen]`.
- **Tag transformation** — `thaw` takes `vegetables [frozen]` and outputs
  `vegetables` (without the tag). This pattern lets you model state changes
  like defrosting, curing, or fermenting.

---

## Step 4 — Cost, Time, and Custom Tags

You can attach numeric metadata to basic resources and processes using
key-value tags. Resource Flow aggregates these metrics across the entire
process graph.

```text
chop_fruit [time: 2 min, co2: 0.1 kg, manual_labour]:
    200 g mango * [cost: 4.00, co2: 0.8 kg], 150 g banana * [cost: 1.50, co2: 0.3 kg]
    -> 350 g fruit_mix;

blend_manual [time: 3 min, cost: 0, co2: 0, manual_labour]:
    350 g fruit_mix, 200 ml milk * [cost: 1.00, co2: 0.5 kg]
    -> 500 ml smoothie;

blend_electric [time: 1 min, cost: 0.50, co2: 0.4 kg]:
    350 g fruit_mix, 200 ml milk * [cost: 1.00, co2: 0.5 kg]
    -> 500 ml smoothie;

make 500 ml smoothie;
```

- **`[cost: N]` on basic resources** — `200 g mango * [cost: 4.00]` assigns
  a batch cost of 4.00 to 200 g of mango. The solver scales this linearly if
  more mango is needed.
- **`[time: N unit]` on processes** — `[time: 2 min]` means chopping takes
  2 minutes per batch. Time scales with the process scale factor.
- **`[cost: N]` on processes** — Process execution costs, also scaled linearly.
- **Custom quantitative tags** — `[co2: 0.8 kg]` attaches a numeric CO₂
  metric to a resource or process. The solver aggregates it across the graph
  just like cost, scaling with quantities and process factors. You can later
  optimize for it with `[min co2]`.
- **Custom qualitative tags** — `[manual_labour]` is a flag tag on a process.
  It carries no numeric value but the solver can count how many processes in a
  solution carry it. We'll use this in the next step with solver goals.

---

## Step 5 — Solver Goals

When multiple process paths exist, solver goals let you control which path the
solver picks. Goals are specified in brackets before `make`.

```text
hand_forge [cost: 10.00, time: 5 h, manual_labour]:
    2 kg steel_ingot * [cost: 20.00], 5 kg coal * [cost: 5.00]
    -> 1 piece forged_blade;

power_hammer_forge [cost: 25.00, time: 1 h]:
    2 kg steel_ingot * [cost: 20.00], 10 kWh electricity * [cost: 3.00]
    -> 1 piece forged_blade;

quench [cost: 5.00, time: 2 h, manual_labour]:
    1 piece forged_blade, 10 l oil * [cost: 2.00]
    -> 1 piece steel_sword;

auto_quench [cost: 15.00, time: 30 min]:
    1 piece forged_blade, 10 l oil * [cost: 2.00]
    -> 1 piece steel_sword;

[min manual_labour, fastest] make 1 piece steel_sword;
[time <= 2 h] make 1 piece steel_sword;
```

The solver evaluates goals left-to-right:

1. **`min manual_labour`** eliminates both `hand_forge` + `quench` (2 flagged
   processes) in favour of `power_hammer_forge` + one of the quench steps
   (at most 1 flagged). This leaves two candidates: `power_hammer_forge` +
   `quench` and `power_hammer_forge` + `auto_quench`.
2. **`fastest`** breaks the tie — `auto_quench` (30 min) beats `quench` (2 h).
### Built-in Goal Shorthands

| Goal | Meaning |
| :--- | :--- |
| `[cheapest]` | Minimize total cost (resource cost + process cost) |
| `[fastest]` | Minimize total process execution time |

### Custom Goals

- **`min` / `max`** — Minimize or maximize a tag metric:
  `[min manual_labour]` reduces the count of processes carrying that flag.
  `[min co2]` minimizes the aggregate CO₂ across the graph.
- **Relational constraints** — Enforce bounds on a tag:
  `[time <= 45 min]` only accepts solutions where total time is at most
  45 minutes. If no solution meets the constraint, the solver reports
  the closest value found.
- **Multi-goal cascades** — `[cheapest, fastest]` evaluates left-to-right,
  using secondary goals to break ties.

---

## Step 6 — Multiple Queries

A single `.rf` file can contain more than one `make` query. The solver
evaluates each query independently and reports results for all of them:

```text
brew_espresso: 20 g coffee_beans * [cost: 0.80], 30 ml water *
    -> 30 ml espresso;
steam_milk: 200 ml milk * [cost: 0.60]
    -> 200 ml steamed_milk;
make_latte: 30 ml espresso, 200 ml steamed_milk
    -> 230 ml latte;

make 230 ml latte;
make 60 ml espresso;
```

Both queries share the same process definitions but are solved separately.
The first produces a full latte (espresso + steamed milk); the second produces
a double espresso. Each query gets its own execution plan with independently
calculated scale factors and costs.

**What you learned:** Multiple `make` queries in one file, each solved
independently.

---

## Step 7 — Tools

Some processes require equipment that is not consumed. These non-consumable
requirements are called **tools**.

```text
chop: 300 g vegetables * -> 280 g vegetables [chopped] with 1 knife;
peel: 200 g potatoes * -> 180 g potatoes [peeled] with 1 knife;
boil: 280 g vegetables [chopped], 180 g potatoes [peeled], 500 ml water *
    -> 900 ml soup;

make 900 ml soup using 1 knife;
```

- **`with`** — Declares that a process needs a tool:
  `with 1 knife` means the process requires one knife.
- **`using`** — Declares which tools are available in a query:
  `using 1 knife` supplies one knife for the entire query.
- **Shared tools** — A single knife satisfies both `chop` and `peel`
  simultaneously. Tools are not consumed and do not flow through the graph
  like resources.

---

## Step 8 — Modules and Imports

As recipes grow, you can split them across files or group related processes
into named modules.

### File Imports

Suppose you have this file structure:

```text
project/
├── sauce.rf
└── pasta.rf
```

**`sauce.rf`** — defines how to make tomato sauce:

```text
make_sauce [time: 15 min]:
    250 g tomatoes * [cost: 3.00], 20 ml oil * [cost: 0.50]
    -> 250 g tomato_sauce;
```

**`pasta.rf`** — imports the sauce and builds a full recipe:

```text
use sauce;

boil_pasta [time: 10 min]:
    250 g dry_pasta * [cost: 1.50], 1000 ml water *
    -> 350 g cooked_pasta;

combine [time: 2 min]:
    350 g cooked_pasta, 250 g tomato_sauce
    -> 550 g tomato_pasta;

make 550 g tomato_pasta;
```

Running `rflow pasta.rf` resolves the `use "sauce";` import, finds
`sauce.rf` in the same directory, and brings its processes into scope.

### Selective Imports

You can import specific items from a module:

```text
use sauce::make_sauce;
use kitchen::chop, boil;
```

### Inline Modules

You can also group processes inside a single file using `mod`:

```text
mod sauces {
    make_sauce: 250 g tomatoes * -> 250 g tomato_sauce;
    make_pesto: 50 g basil *, 30 g nuts * -> 70 g pesto;
}

use sauces;

boil_pasta: 250 g dry_pasta *, 1000 ml water * -> 350 g cooked_pasta;
combine: 350 g cooked_pasta, 250 g tomato_sauce -> 550 g pasta;

make 550 g pasta;
```


### How Modules Work

- **Implicit file modules** — Every `.rf` file is implicitly a module named
  after its filename. `sauce.rf` becomes the `sauce` module.
- **Transitive re-exports** — If module A imports module B, any file that
  imports A also receives B's processes.
