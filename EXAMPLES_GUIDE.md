# Resource Flow Examples Guide

This guide documents the curated set of 10 example scripts (`examples/*.rf`) in Resource Flow. The suite is balanced 50/50 between **Culinary** and **Technical / Engineering / Crafting** domains. It follows a strict progressive curriculum—starting from tagless baseline syntax, introducing built-in metric tags, multi-output queries, solver goals, and relational constraints, before gradually layering custom process metrics, flag tags, resource state matching, and culminating in a hyper-complex bio-synthesis decision graph.

---

## Curriculum Overview & Feature Matrix

| File | Domain | Key Concepts & Language Features | Tag Usage & Query Highlights |
| :--- | :--- | :--- | :--- |
| **`01_tea_brewing.rf`** | Culinary | Basic resource declarations (`*`), linear graph, volume scaling. | **Zero tags (`[]`)**; basic `make` query |
| **`02_potion_brewing.rf`** | Alchemy | Batch cost normalization (`* [cost: X]`) & unit conversions (`mg` $\rightarrow$ `g`, `ml` $\rightarrow$ `l`). | **Built-in `cost` & `time` metric tags only** |
| **`03_carrot_soup.rf`** | Culinary | Multi-component outputs from a single process & resource state tags (`[organic, !frozen]`). | State tags; **multi-output query** (`carrot_soup` + `roasted_peelings`) |
| **`04_pcb_assembly.rf`** | Electronics | Branching routes: Manual Soldering vs Automated SMT Pick-and-Place. | `[cheapest]` single solver goal optimization |
| **`05_artisan_bread.rf`** | Culinary | Relational duration constraints (`[time <= 45 min]`). | Upper-bound time constraint filtering out sourdough |
| **`06_biofuel_refining.rf`** | Chemistry | **Custom quantitative process metric tags** (`[co2: 12.5 kg]`). | Custom tag metric minimization (`[min co2, cheapest]`) |
| **`07_blacksmith_sword.rf`** | Metallurgy | **Custom non-quantitative flag tags** (`[manual_labour]`) & discrete point counts. | `[min manual_labour, fastest]` labor reduction |
| **`08_software_ci_pipeline.rf`**| CI/CD Tech | **Multi-goal cascades** (`[time <= 15 min, min cost, min co2]`). | Relational filtering & tie-breaking |
| **`09_gourmet_banquet.rf`** | Culinary | Multi-component parallel prep with alternative sauces/preps. | **Multi-output query** (`course_a` + `course_b`) |
| **`10_space_station_synthesis.rf`**| Space Synthesis | 15+ node graph, 4 decision stages, byproduct loops, **negated tag matching (`[!rustic]`)**, alternate recipes. | **Multi-output query** + 4-tier goal cascade |

---

## Detailed Example Rationale

### 1. Tea Brewing (`01_tea_brewing.rf`)
- **Rationale**: Introduces the most basic syntax of Resource Flow with **zero tags** of any kind. Shows how raw ingredients (`water *`, `tea_leaves *`, `honey *`) are declared with an asterisk and transformed step-by-step through process nodes into a single end product.
- **Goal**: Demonstrates default `[any]` solver goal behavior on a clean, tagless linear DAG.

### 2. Potion Brewing (`02_potion_brewing.rf`)
- **Rationale**: Introduces the first built-in metric tags (`cost` and `time`), highlighting unit dimension conversions and batch cost normalization. 
- **Features**: Demonstrates how a batch cost declared on 500 mg of `dragon_herb` (`* [cost: 25.00]`) is converted to unit price per base gram, and automatically scaled when `distill_elixir` requests liquid volumes in milliliters (`ml` $\rightarrow$ `l`).

### 3. Carrot Soup with Roasted Peelings (`03_carrot_soup.rf`)
- **Rationale**: Demonstrates multi-component process outputs, resource state tags (`[organic, !frozen]`), and **multi-output queries**.
- **Features**: The `peel` process outputs both `carrots [peeled, organic]` and `carrot_peelings [organic]`. The single `make` query requests both `700 g carrot_soup` and `100 g roasted_peelings`, forcing the solver to resolve shared upstream process execution in one graph.

### 4. Circuit Board Assembly (`04_pcb_assembly.rf`)
- **Rationale**: Introduces alternative process paths yielding the identical target resource (`assembled_pcb`).
- **Features**: Compares high-cost/fast SMT automated assembly vs low-cost/slow manual soldering. Toggling the solver goal between `[cheapest]` and `[fastest]` switches the active process route in the resulting DAG.

### 5. Artisan Bread Baking (`05_artisan_bread.rf`)
- **Rationale**: Exercises relational solver goal constraints using upper-bound time limits.
- **Features**: Compares quick commercial yeast fermentation against multi-hour sourdough fermentation. The query `[time <= 45 min, cheapest]` eliminates the sourdough path due to its duration and selects commercial bread.

### 6. Biofuel Refining (`06_biofuel_refining.rf`)
- **Rationale**: Introduces **custom quantitative process metric tags** (e.g. `co2` emissions).
- **Features**: Processes specify `[co2: 8.0 kg]` vs `[co2: 1.5 kg]`. The query `[min co2, cheapest]` instructs the solver to calculate total CO2 emissions across candidate recipe graphs and choose the most sustainable path.

### 7. Blacksmithing Steel Sword (`07_blacksmith_sword.rf`)
- **Rationale**: Introduces **custom non-quantitative boolean/flag tags** (e.g., `[manual_labour]`), evaluated by counting flag occurrences across DAG nodes.
- **Features**: Compares hand-forging and manual quenching against automated power hammers. The goal `[min manual_labour, fastest]` selects automated machinery to minimize physical manual labor steps.

### 8. Software CI/CD Build Pipeline (`08_software_ci_pipeline.rf`)
- **Rationale**: Demonstrates complex multi-goal cascades combining relational filtering with primary and secondary tie-breaking goals.
- **Features**: Evaluates Standard Docker Build, Cached Kaniko Build, and Serverless Build under `[time <= 15 min, min cost, min co2]`.

### 9. Gourmet Banquet Prep (`09_gourmet_banquet.rf`)
- **Rationale**: Demonstrates multi-component parallel prep graphs with shared ingredients and **multi-output queries**.
- **Features**: Prepares two distinct banquet courses simultaneously (`banquet_course_a` and `banquet_course_b`), balancing protein preparation speed and sauce reductions under a `[time <= 90 min, cheapest]` goal.

### 10. Space Station Bio-Synthesis & Life Support (`10_space_station_synthesis.rf`)
- **Rationale**: The Master Example—a non-linear graph with 15+ process nodes, 4 distinct assembly recipes for `synth_ration`, byproduct recycling, negated tag matching (`[!rustic]`), and a **multi-output query**.
- **Non-Linear Topology & Alternate Recipes**:
  1. *Protein Extraction*: Cultured bio-slurry (`clean`) vs Insect harvest (`rustic`) vs Algae solar synthesis (`pure`).
  2. *Starch Purification*: Enzymatic hydrolysis (yielding `greywater` byproduct) vs Thermal cracking (yielding `hydro_fuel` byproduct).
  3. *Fortification*: Synthetic vitamin blend (`high_grade`) vs Natural herb infusion (`organic`).
  4. *Byproduct Fuel Routes*: Bio-fuel cell synthesis using `greywater` vs Direct thermal hydro-fuel refining.
  5. *4 Distinct Assembly Recipes for `synth_ration`*:
     - *Recipe A (Auto Thermal Molding)*: Requires non-rustic protein (`800 g protein_paste [!rustic]`, accepting both `clean` and `pure`), starch, and fortifier.
     - *Recipe B (Artisanal Hand Pack)*: Accepts any protein (including `rustic` insect protein), but requires 3 hours and manual labor.
     - *Recipe C (Cryo 3D Printing)*: Strictly requires `pure` algae protein and `high_grade` fortifier.
     - *Recipe D (Slurry Compaction)*: Real alternate binder recipe using `greywater` directly instead of starch purification!
  6. *4-Tier Goal Cascade*: `[time <= 3 h, co2 <= 20 kg, min manual_labour, cheapest] make 1000 g synth_ration, 500 ml hydro_fuel [refined];`
