# Language guide

A step-by-step tutorial that teaches the Resource Flow DSL by building progressively more complex recipes. Each step introduces one new concept and includes a runnable `.rf` example.

---

## Step 1. Basics

A Resource Flow script defines processes that convert input resources into output resources. Let's start with a simple tea recipe:

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

Here's what happened:

- **Process declarations go before `make`.** The label (`boil_water`, `steep_tea`, `add_honey`) is followed by a colon, then `inputs -> outputs`, terminated with `;`.
- **Basic resources use an asterisk `*`.** This marks a raw material that is supplied externally. `water`, `tea_leaves`, and `honey` are basic resources because they aren't produced by any other process.
- **The `make` statement tells the solver what end product you want.** The solver walks backwards through the process graph to compute the exact inputs needed.

---

## Step 2. Units and automatic scaling

Resource Flow supports standard units and converts between them automatically. Here are the supported unit families:

| Dimension | Supported Units |
| :--- | :--- |
| **Mass** | `mg`, `g`, `kg` |
| **Volume** | `ml`, `l` |
| **Count / Discrete** | `piece` |

What happens if you request more than a single batch? Take the tea recipe from Step 1 and change the query:

```text
boil_water: 500 ml water * -> 500 ml boiled_water;
steep_tea: 500 ml boiled_water, 5 g tea_leaves * -> 500 ml brewed_tea;
add_honey: 500 ml brewed_tea, 10 g honey * -> 500 ml sweet_tea;

make 1 l sweet_tea;
```

The solver converts `1 l` to `1000 ml` and determines it needs to run every process twice (scale factor = 2). All inputs scale linearly:

- `1000 ml water` (was 500)
- `10 g tea_leaves` (was 5)
- `20 g honey` (was 10)

Incompatible conversions, like mixing mass (`g`) and volume (`ml`) for the same resource, produce an error.

---

## Step 3. Tags and constraints

Tags label resources with properties. The solver uses tags to choose the right process path. Here's a stir-fry recipe where vegetables arrive frozen and must be thawed before cooking:

```text
thaw: 300 g vegetables * [frozen] -> 300 g vegetables;
chop: 300 g vegetables [!frozen] -> 280 g vegetables [chopped];
stir_fry: 280 g vegetables [chopped], 15 ml oil * -> 280 g stir_fry;

make 280 g stir_fry;
```

- **Flag tags like `[frozen]` and `[chopped]` track resource state.** The solver treats `vegetables [frozen]` and `vegetables [chopped]` as distinct resources.
- **Negating a tag means the resource cannot have that property.** `[!frozen]` on `chop`'s input means the vegetables cannot be frozen. The solver must route through `thaw` first. Thawing strips the `[frozen]` tag and produces plain `vegetables`, satisfying the requirement.
- **Processes transform tags.** `thaw` takes `vegetables [frozen]` and outputs plain `vegetables`. Use this to model state changes like defrosting, curing, or fermenting.

---

## Step 4. Cost, time, and custom tags

You can attach numeric metadata to basic resources and processes using key-value tags. Resource Flow aggregates these metrics across the entire process graph.

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

- **Assign costs to basic resources.** `200 g mango * [cost: 4.00]` sets the batch cost to 4.00. The solver scales this linearly if it needs more mango.
- **Assign time to processes.** `[time: 2 min]` means chopping takes 2 minutes per batch. Time scales with the process scale factor.
- **Process execution costs work the same way.** They also scale linearly.
- **Add custom quantitative tags to any resource or process.** `[co2: 0.8 kg]` adds a numeric CO₂ metric. The solver aggregates these metrics across the graph just like cost. You can optimize for them later with `[min co2]`.
- **Add custom qualitative tags to processes.** `[manual_labour]` carries no numeric value, but the solver can count how many processes in a solution carry it. We use this in the next step.

---

## Step 5. Solver goals

Solver goals let you control which path the solver picks when multiple exist. Specify goals in brackets before `make`.

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

The solver evaluates goals left to right:

1. `min manual_labour` eliminates `hand_forge` + `quench` because that uses two flagged processes. The solver prefers `power_hammer_forge` + a quench step, which uses at most one flagged process. This leaves two candidates.
2. `fastest` breaks the tie. `auto_quench` takes 30 minutes, beating `quench` at 2 hours.

### Built-in goal shorthands

| Goal | Meaning |
| :--- | :--- |
| `[cheapest]` | Minimize total cost (resource cost + process cost) |
| `[fastest]` | Minimize total process execution time |

### Custom goals

- **Minimize or maximize a tag metric with `min` or `max`.** `[min manual_labour]` reduces the count of processes carrying that flag. `[min co2]` minimizes the aggregate CO₂ across the graph.
- **Enforce bounds on a tag using relational constraints.** `[time <= 45 min]` only accepts solutions taking 45 minutes or less. If no solution meets the constraint, the solver reports the closest value it found.
- **Chain multiple goals.** `[cheapest, fastest]` tells the solver to evaluate left to right and use secondary goals to break ties.

---

## Step 6. Multiple queries

A single `.rf` file can contain multiple `make` queries. The solver evaluates each query independently and reports results for all of them:

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

Both queries share the same process definitions but are solved separately. The first produces a full latte (espresso + steamed milk); the second produces a double espresso. Each query gets its own execution plan with independently calculated scale factors and costs.

---

## Step 7. Tools

Some processes require equipment that isn't consumed. These non-consumable requirements are called tools.

```text
chop: 300 g vegetables * -> 280 g vegetables [chopped] with 1 knife;
peel: 200 g potatoes * -> 180 g potatoes [peeled] with 1 knife;
boil: 280 g vegetables [chopped], 180 g potatoes [peeled], 500 ml water *
    -> 900 ml soup;

make 900 ml soup using 1 knife;
```

- **`with` declares that a process needs a tool.** `with 1 knife` means the process requires one knife.
- **`using` declares which tools are available.** `using 1 knife` supplies one knife for the entire query.
- **Tools can be shared.** A single knife satisfies both `chop` and `peel` simultaneously because tools aren't consumed.

---

## Step 8. Modules and imports

As recipes grow, you can split them across files or group related processes into named modules.

### File imports

Suppose you have this file structure:

```text
project/
├── sauce.rf
└── pasta.rf
```

**`sauce.rf`** defines how to make tomato sauce:

```text
make_sauce [time: 15 min]:
    250 g tomatoes * [cost: 3.00], 20 ml oil * [cost: 0.50]
    -> 250 g tomato_sauce;
```

**`pasta.rf`** imports the sauce and builds a full recipe:

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

Running `rflow pasta.rf` resolves the `use "sauce";` import, finds `sauce.rf` in the same directory, and brings its processes into scope.

### Selective imports

You can import specific items from a module:

```text
use sauce::make_sauce;
use kitchen::chop, boil;
```

### Inline modules

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

### How modules work

- **Every `.rf` file is implicitly a module named after its filename.** `sauce.rf` becomes the `sauce` module.
- **Imports are transitive.** If module A imports module B, any file importing A also gets B's processes.
