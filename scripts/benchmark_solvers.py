import argparse
import sys
import time
from pathlib import Path
import importlib
import pkgutil
import typing

# Add project root to sys.path if not there
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from resource_flow.solvers.base import Solver
from resource_flow.parser import RecipeParser

def discover_solvers():
    """Dynamically register and return all Solver subclasses."""
    # Ensure resource_flow.solvers is imported
    import resource_flow.solvers
    
    # Import all submodules in resource_flow.solvers to trigger subclass registration
    package = resource_flow.solvers
    for _, module_name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        importlib.import_module(module_name)
        
    return Solver.__subclasses__()

def run_benchmarks(data_dir: Path):
    """Run all solvers against all .rf files in data_dir."""
    solvers = discover_solvers()
    rf_files = list(data_dir.glob("*.rf"))
    
    if not rf_files:
        print(f"No .rf files found in {data_dir}")
        return {}
        
    results: dict[str, dict[str, typing.Any]] = {}
    for rf_file in rf_files:
        file_results: dict[str, typing.Any] = {}
        for solver_cls in solvers:
            try:
                parser = RecipeParser()
                ctx = parser.parse_file(str(rf_file))
                processes, query = ctx.processes, ctx.query
                
                start_time = time.perf_counter()
                solver_instance = solver_cls(processes, query)
                solver_instance.solve()
                end_time = time.perf_counter()
                
                time_ms = (end_time - start_time) * 1000
                file_results[solver_cls.__name__] = {
                    "success": True,
                    "time_ms": time_ms
                }
            except Exception as e:
                file_results[solver_cls.__name__] = {
                    "success": False,
                    "error": str(e)
                }
        results[rf_file.name] = file_results
        
    return results

def print_report(results):
    """Print a performance report."""
    print("\n=== Benchmark Report ===")
    
    if not results:
        print("No results to report.")
        return
        
    solvers = list(list(results.values())[0].keys())
    
    # Header
    header = f"{'File':<30} | " + " | ".join([f"{s:<15}" for s in solvers])
    print(header)
    print("-" * len(header))
    
    # Rows
    for rf_name, file_results in results.items():
        row = f"{rf_name:<30} | "
        for solver_name in solvers:
            res = file_results.get(solver_name, {"success": False, "error": "Missing"})
            if res["success"]:
                row += f"{res['time_ms']:<15.2f} | "
            else:
                row += f"{'FAIL':<15} | "
        print(row)
        
def main():
    parser = argparse.ArgumentParser(description="Benchmark Resource Flow solvers.")
    parser.add_argument("--dir", type=str, default="examples", help="Directory containing .rf files to benchmark.")
    args = parser.parse_args()
    
    data_dir = Path(args.dir)
    if not data_dir.is_absolute():
        data_dir = project_root / data_dir
        
    if not data_dir.exists() or not data_dir.is_dir():
        print(f"Directory {data_dir} does not exist.")
        sys.exit(1)
        
    results = run_benchmarks(data_dir)
    print_report(results)

if __name__ == "__main__":
    main()
