from glob import glob
from pathlib import Path
from resource_flow.parser import RecipeParser
from resource_flow.solvers import RecipeSolver
from resource_flow.visualization import Visualizer


def run_compiler(file_path: str) -> None:
    try:
        parser = RecipeParser()
        ctx = parser.parse_file(file_path)

        solver = RecipeSolver(ctx.processes, ctx.query)
        dag = solver.solve()
        
        viz = Visualizer(dag, solver.final_demands, solver.final_surplus, solver.basic_resources, solver.query)
        viz.print_plan()

        print("Mermaid Visualization:")
        print(viz.generate_mermaid())
    except Exception as e:
        print(f"Solver Error: {e}")
    print("------------------------------------------------\n")


if __name__ == "__main__":
    example_files = sorted(glob(str(Path("examples") / "**" / "*.rf"), recursive=True))
    for file_path in example_files:
        print(f"Running file: {file_path}")
        run_compiler(file_path)