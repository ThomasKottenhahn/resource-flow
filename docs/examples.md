# Examples

Explore real-world Resource Flow recipes and execution plans.

---

## 1. Tomato Pasta Recipe

### DSL Script (`examples/05_tomato_pasta.rf`)

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

### Execution Flowchart (Mermaid)

```mermaid
graph TD
    make_sauce["make_sauce (x2.00)\nTime: 30.00 min"]
    boil_pasta["boil_pasta (x2.00)\nTime: 20.00 min"]
    combine["combine (x1.00)\nTime: 5.00 min"]
    basic_dry_pasta["dry_pasta* (500.00 g, Cost: 3.00)"]
    basic_oil["oil* (20.00 ml, Cost: 0.04)"]
    basic_onions["onions* (50.00 g, Cost: 1.00)"]
    basic_tomatoes["tomatoes* (500.00 g, Cost: 6.00)"]
    basic_water["water* (2000.00 ml)"]
    Query["Query: 1100.00 g tomato_pasta"]
    basic_oil -->|"20.00 ml"| make_sauce
    basic_tomatoes -->|"500.00 g"| make_sauce
    basic_onions -->|"50.00 g"| make_sauce
    basic_water -->|"2000.00 ml"| boil_pasta
    basic_dry_pasta -->|"500.00 g"| boil_pasta
    make_sauce -->|"500.00 g tomato_sauce"| combine
    boil_pasta -->|"700.00 g cooked_pasta"| combine
    combine -->|"1100.00 g tomato_pasta"| Query
    Metrics["Metrics Summary\nResource Cost: 10.04\nProcess Cost: 0.00\nTotal Cost: 10.04\nTotal Time: 55.00 min"]
```

---

## 2. Custom Batch Costs Example

```text
buy_carrots: 300 g carrots * [cost: 20.00] -> 300 g raw_carrots;
prep_soup: 300 g raw_carrots, 500 ml water * [cost: 2.00] -> 800 ml carrot_soup;

make 1600 ml carrot_soup;
```

In this example, requesting `1600 ml carrot_soup` doubles the process scale ($s=2$), scaling total basic inputs to `600 g carrots` (Cost: $40.00) and `1000 ml water` (Cost: $4.00) for a total calculated cost of $44.00.
