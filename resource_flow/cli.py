import argparse
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
from .parser import RecipeParser
from .solver import RecipeSolver
from .visualization import Visualizer


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resource Flow Compiler - compiles resource recipes and resolves DAG scales."
    )
    parser.add_argument("input", help="Path to the .rf source file to compile.")
    parser.add_argument(
        "-o",
        "--output",
        help="Optional directory path or filename prefix. If omitted, outputs print to console.",
    )
    parser.add_argument(
        "--time-unit",
        default="min",
        choices=["s", "min", "h"],
        help="Time unit for execution metrics summary (default: min).",
    )
    args = parser.parse_args()

    try:
        recipe_parser = RecipeParser()
        _, processes, query = recipe_parser.parse_file(args.input)

        solver = RecipeSolver(processes, query)
        dag = solver.solve()
        viz = Visualizer(dag, solver.final_demands, solver.final_surplus, solver.basic_resources, solver.query)
        mermaid_text = viz.generate_mermaid(time_unit=args.time_unit)

        if args.output:
            plan_stream = io.StringIO()
            with redirect_stdout(plan_stream):
                viz.print_plan(time_unit=args.time_unit)
            plan_text = plan_stream.getvalue()

            output_path = Path(args.output)
            is_dir = (
                args.output.endswith("/")
                or args.output.endswith("\\")
                or output_path.is_dir()
            )

            if is_dir:
                output_path.mkdir(parents=True, exist_ok=True)
                plan_file = output_path / "plan.txt"
                mermaid_file = output_path / "flow.mermaid"
            else:
                if output_path.parent:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                plan_file = output_path.with_name(f"{output_path.name}_plan.txt")
                mermaid_file = output_path.with_name(f"{output_path.name}_flow.mermaid")

            plan_file.write_text(plan_text, encoding="utf-8")
            mermaid_file.write_text(mermaid_text, encoding="utf-8")
            print(f"Plan saved to: {plan_file}")
            print(f"Mermaid visualization saved to: {mermaid_file}")
        else:
            print("\n------------------------------------------------")
            print("Solving Recipe...")
            print("------------------------------------------------")
            viz.print_plan(time_unit=args.time_unit)
            print("Mermaid Visualization:")
            print(mermaid_text)
            print("------------------------------------------------\n")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
