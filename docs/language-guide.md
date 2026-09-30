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

If you omit the unit (e.g. `1 carrots`), it automatically defaults to `piece`.

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
convert 1 EUR = 1.10 USD;

chop_fruit [time: 2 min, co2: 0.1 kg, manual_labour]:
    200 g mango * [cost: 4.40 USD, co2: 0.8 kg], 150 g banana * [cost: 1.50 EUR, co2: 0.3 kg]
    -> 350 g fruit_mix;

blend_manual [time: 3 min, cost: 0, co2: 0, manual_labour]:
    350 g fruit_mix, 200 ml milk * [cost: 1.10 USD, co2: 0.5 kg]
    -> 500 ml smoothie;

blend_electric [time: 1 min, cost: 0.50 EUR, co2: 0.4 kg]:
    350 g fruit_mix, 200 ml milk * [cost: 1.10 USD, co2: 0.5 kg]
    -> 500 ml smoothie;

make 500 ml smoothie;
```

- **Mix currencies using `convert`.** Use `convert 1 EUR = 1.10 USD;` to define exchange rates. The first currency (`EUR`) becomes the base currency, and the solver automatically converts costs like `4.40 USD` into EUR.
- **Assign costs to basic resources.** `200 g mango * [cost: 4.40 USD]` sets the batch cost. The solver scales this linearly if it needs more mango.
- **Assign time to processes.** `[time: 2 min]` means chopping takes 2 minutes per batch. Time scales with the process scale factor.
- **Process execution costs work the same way.** They also scale linearly.
- **Add custom quantitative tags to any resource or process.** `[co2: 0.8 kg]` adds a numeric CO₂ metric. The solver aggregates these metrics across the graph just like cost. You can optimize for them later with `[min co2]`.
- **Add custom qualitative tags to processes.** `[manual_labour]` carries no numeric value, but the solver can count how many processes in a solution carry it. We use this in the next step.

### Global definitions (`def`)

You can define basic resources globally using the `def` keyword. These resources are automatically basic resources. You do not need an asterisk.

```text
def 300 g carrots [cost: 20, organic];
def 200 g carrots [cost: 10, frozen];

boil: 100 g carrots -> 100 g carrots [boiled];
cut: 100 g carrots [!frozen] -> 80 g carrots [organic, cut];
```

In this example, the solver has two initial sources to choose from: 300g of organic carrots and 200g of frozen carrots. If you then query for boiled carrots, the solver will explore both paths. If you query for cut carrots, the solver will only explore the path using organic carrots.

### Aliasing (`let`)

You can define aliases for multisets (groups of resources) to reuse them across multiple processes using the `let` keyword. 

```text
let standard_tools = 1 piece knife, 1 piece pan;
let veggies = 300 g carrots *, 200 g potatoes *;

chop: veggies -> 450 g chopped_veggies with standard_tools;
```

These aliases act as macros: wherever you reference the alias name, the parser substitutes it with the exact resources defined. Macros are immutable and cannot be reassigned, and they must be declared before they are used.

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
[time <= 4 h] make 1 piece steel_sword;
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

## Step 6. Suppliers and batching

Basic resources often come from specific suppliers in fixed batch sizes. The solver can explore different suppliers and buy in discrete batches to fulfill demands. Let's expand our forging recipe:

```text
def 2 kg steel_ingot [cost: 20.00, discrete] at LocalSmith;
def 5 kg steel_ingot [cost: 45.00, discrete] at BulkSupplier;

power_hammer_forge [cost: 25.00, time: 1 h]:
    2 kg steel_ingot, 10 kWh electricity * [cost: 3.00]
    -> 1 piece forged_blade;

[cheapest] make 7 piece forged_blade;
```

- **Define suppliers with `at`.** Adding `at BulkSupplier` to a `def` groups resources by supplier. When multiple suppliers provide the same resource, the solver branches and picks the optimal one based on your goals (like `[cheapest]`).
- **Scale by whole batches with `[discrete]`.** The `[discrete]` tag tells the solver that this resource cannot be divided. If you need 14 kg of `steel_ingot` (for 7 blades), `LocalSmith` would require 7 batches (140.00 cost). `BulkSupplier` would require 3 batches of 5 kg (135.00 cost) to meet the 14 kg demand, leaving a 1 kg surplus. Because of `[cheapest]`, the solver correctly selects `BulkSupplier`.

---

## Step 7. Multiple queries

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

## Step 8. Tools

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

## Step 9. Modules and imports

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

You can import specific items from a module, including processes, global definitions (`def`), and macros (`let`):

```text
use sauce::make_sauce, sauce::standard_tools;
use kitchen::chop, boil;
```

### Inline modules

You can also group processes inside a single file using `mod`:

```text
mod sauces [vegan] {
    def 250 g tomatoes;
    make_sauce: 250 g tomatoes -> 250 g tomato_sauce;
    
    def 50 g cheese [!vegan];
    make_cheese_sauce: 250 g tomatoes, 50 g cheese -> 300 g cheese_sauce;
}

use sauces;

boil_pasta: 250 g dry_pasta *, 1000 ml water * -> 350 g cooked_pasta;
combine: 350 g cooked_pasta, 250 g tomato_sauce -> 550 g pasta;

make 550 g pasta;
```

### How modules work

- **Every `.rf` file is implicitly a module named after its filename.** For example, `sauce.rf` becomes the `sauce` module.
- **File module merging.** If you declare a module inside a file with the exact same name (e.g. `mod sauce [vegan] at Market { ... }` inside `sauce.rf`), the tags and supplier attributes will automatically apply to the entire file's implicit module.
- **Inheritance and Tag Negation.** Resources inside a module inherit the module's tags (e.g. `tomato_sauce` inherits `[vegan]`). You can cancel an inherited tag on a specific resource by negating it: `def 50 g cheese [!vegan];`.
- **Relative imports.** You can import files from subdirectories using relative paths, like `use ./kitchen/sauce;`.
- **Global imports.** The `use` statement imports not only processes, but also macros (`let`) and resource definitions (`def`).
- **Imports are transitive.** If module A imports module B, any file importing A also gets B's processes, macros, and defs.

---

## Step 10. Timings and Deadlines

Resource Flow can schedule processes chronologically on a timeline using `calendar` blocks, execution types, and deadlines. Let's model a sourdough baking process where some steps require active work and others happen without supervision (like dough rising).

```text
calendar {
    work 08:00 to 12:00;
    work 13:00 to 17:00;
}

mix_dough [time: 15 min]:
    500 g flour *, 300 ml water *, 10 g yeast *
    -> 800 g dough;

rise [time: 12 h, unsupervised]:
    800 g dough
    -> 800 g risen_dough;

knead [time: 10 min]:
    800 g risen_dough
    -> 800 g kneaded_dough;

bake [time: 45 min, passive]:
    800 g kneaded_dough
    -> 800 g bread;

make 800 g bread starting Monday 08:00 by Tuesday 12:00;
```

- **Define working hours with `calendar`.** The `calendar` block restricts when active processes can occur. Here, active work happens in two shifts, with a lunch break from 12:00 to 13:00.
- **Time bounds in queries.** You can add `starting` and `by` clauses to `make` queries. The solver uses As-Late-As-Possible (ALAP) scheduling by default to ensure the product is finished right at the deadline (`by Tuesday 12:00`).
- **Execution types.** By default, processes are active and must fit within `calendar` working hours. 
    - The `[unsupervised]` tag (used for `rise`) means the process doesn't require human attention and can freely run outside of working hours, overlapping with breaks or running overnight.
    - The `[passive]` tag (used for `bake`) allows the process to overlap with other tasks (like starting another batch of dough while the first is in the oven), but it typically still requires someone to be present, so it respects the calendar working hours.

### Shelf Life and Hold Constraints

You can constrain the timeline further using resource tags to ensure quality. Let's look at an example with strict timing requirements:

```text
def 10 l fresh_milk [shelf_life: 48 h] at Farm;

pasteurize [time: 30 min]:
    10 l fresh_milk
    -> 10 l pasteurized_milk;

bottle [time: 20 min]:
    10 l pasteurized_milk [hold <= 15 min]
    -> 10 l bottled_milk;

make 10 l bottled_milk starting Monday 08:00 by Friday 17:00;
```

- **`[shelf_life: 48 h]`**: Limits how long a resource can exist before being consumed. In this case, the `fresh_milk` must be pasteurized within 48 hours of being sourced from the farm, forcing the solver to schedule the shopping trip and pasteurization close together.
- **`[hold <= 15 min]`**: Limits the maximum wait time between the producer process ending and the consumer process starting. Here, `pasteurized_milk` must be bottled within 15 minutes of pasteurization finishing, preventing the solver from scheduling a long break in between the two processes.

---

## Step 11. Maps and Shopping

The solver can optimize travel and shopping times across different locations using `map` blocks and the `at` keyword. Let's model a grocery run for dinner prep:

```text
map {
    Home <-> Lidl : 15 min;
    supplier Lidl [shopping_time: 5 min + 2 min / item];
}

def 500 g pasta at Lidl;
def 200 ml cream at Lidl;

cook_dinner [time: 30 min]:
    500 g pasta, 200 ml cream
    -> 700 g pasta_alfredo;

make 700 g pasta_alfredo at Home starting 17:00 by 19:00;
```

- **Define travel time.** `Home <-> Lidl : 15 min;` tells the solver it takes 15 minutes to travel between these locations. When processes occur at different locations, the solver automatically inserts travel transit blocks into the timeline.
- **Shopping heuristics.** `supplier Lidl [shopping_time: 5 min + 2 min / item];` adds a dynamic time cost for acquiring basic resources. The solver calculates this as a base time (5 min) plus a per-item time (2 min) multiplied by the number of unique resources bought at that supplier (2 items: pasta and cream = 9 minutes).
- **Assign locations.** Use `at LocationName` to assign processes or queries to a specific location. The solver will trace dependencies backwards and schedule shopping trips at `Lidl` before returning `at Home` to `cook_dinner` in time for the 19:00 deadline.
