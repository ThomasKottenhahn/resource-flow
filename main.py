from glob import glob
from pathlib import Path
from resource_flow.parser import RecipeParser
from resource_flow.solver import RecipeSolver


def run_compiler(file_path: str) -> None:
    try:
        parser = RecipeParser()
        ctx = parser.parse_file(file_path)

        print("\n------------------------------------------------")
        print("Solving Recipe...")
        print("------------------------------------------------")

        solver = RecipeSolver(ctx)
        scales = solver.solve()
        solver.print_plan(scales)

        print("Mermaid Visualization:")
        print(solver.generate_mermaid(scales))
    except Exception as e:
        print(f"Solver Error: {e}")
    print("------------------------------------------------\n")


if __name__ == "__main__":
    example_files = sorted(glob(str(Path("examples") / "**" / "*.rf"), recursive=True))
    for file_path in example_files:
        print(f"Running file: {file_path}")
        run_compiler(file_path)