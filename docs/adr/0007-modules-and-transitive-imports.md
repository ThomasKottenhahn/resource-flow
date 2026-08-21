# Modules and Transitive Imports

We are introducing modules to the Resource Flow DSL to allow grouping and namespacing of processes, especially for larger `.rf` projects.

## Decisions

1. **Implicit File Modules**: Every `.rf` file implicitly acts as a module named after its filename (e.g., `recipes.rf` is module `recipes`).
2. **Inline Modules**: Modules can be explicitly defined inline using `mod name { ... }`.
3. **Mandatory Process Labels**: Processes must have labels. This label serves as the target for module imports and namespacing.
4. **Recursive & Transitive Imports**: 
   - Importing a module recursively imports all its nested sub-modules.
   - Module imports act as inclusions (re-exports). If module `A` imports module `B`, any file that imports `A` will transitively receive `B`'s processes. This allows creating configuration modules (e.g., `kitchen_layout` that groups `oven` and `stove`).
5. **Flat Canonical Namespaces**: Fully qualified process labels are derived strictly from their origin module (e.g., `utilities_clean`), and do not stack infinitely based on the import path (e.g., *not* `kitchen_oven_utilities_clean`). This guarantees single-level qualified names and allows the solver to trivially deduplicate processes that are imported transitively through multiple paths.
6. **Syntax**:
   - `use ./other_file.rf`
   - `use ./other_file.rf::internal`
   - `use mod_name::{process1, process2}`
