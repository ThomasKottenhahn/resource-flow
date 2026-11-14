#!/usr/bin/env python3
import argparse
import random
import os
from dataclasses import dataclass, field

@dataclass
class Process:
    name: str
    inputs: list[tuple[float, str, float]] = field(default_factory=list) # (qty, name, base_cost)
    outputs: list[tuple[float, str]] = field(default_factory=list) # (qty, name)
    tags: dict[str, float] = field(default_factory=dict)

    def render(self) -> str:
        tag_list = []
        for k, v in self.tags.items():
            if k in ["cost", "time"]:
                tag_list.append(f"{k}: {v}")
            else:
                tag_list.append(f"{k}")
                
        process_str = f"{self.name} [{', '.join(tag_list)}]:\n"
        
        if self.inputs:
            input_strs = []
            for qty, name, base_cost in self.inputs:
                if base_cost > 0:
                    input_strs.append(f"{qty} piece {name} * [cost: {base_cost}]")
                else:
                    input_strs.append(f"{qty} piece {name}")
            process_str += f"    {', '.join(input_strs)}\n"
            
        output_strs = [f"{qty} piece {name}" for qty, name in self.outputs]
        process_str += f"    -> {', '.join(output_strs)};"
        return process_str

def generate_dag(nodes_count, density):
    possible_edges = [(src_node, dst_node) for src_node in range(nodes_count) for dst_node in range(src_node + 1, nodes_count)]
    
    num_edges = int(len(possible_edges) * density)
    selected_edges = random.sample(possible_edges, num_edges)
    
    outputs_by_node = {node: [] for node in range(nodes_count)}
    inputs_by_node = {node: [] for node in range(nodes_count)}
    
    for (src_node, dst_node) in selected_edges:
        res_name = f"res_{src_node}_{dst_node}"
        outputs_by_node[src_node].append(res_name)
        inputs_by_node[dst_node].append(res_name)
        
    processes = []
    all_resources = []
    
    for node in range(nodes_count):
        cost = random.randint(1, 100)
        time = random.randint(1, 100)
        
        inputs = inputs_by_node[node]
        input_tuples = []
        for res in inputs:
            qty = float(random.randint(1, 10))
            input_tuples.append((qty, res, 0.0))
            all_resources.append(res)
            
        if not input_tuples:
            qty = float(random.randint(1, 10))
            base_cost = float(random.randint(1, 10))
            base_res = f"base_{node}"
            input_tuples.append((qty, base_res, base_cost))
            all_resources.append(base_res)
            
        outputs = outputs_by_node[node]
        output_tuples = []
        for res in outputs:
            qty = float(random.randint(1, 10))
            output_tuples.append((qty, res))
            all_resources.append(res)
            
        if not output_tuples:
            qty = float(random.randint(1, 10))
            res_name = f"final_{node}"
            output_tuples.append((qty, res_name))
            all_resources.append(res_name)
            
        tags = {"cost": float(cost), "time": float(time)}
        for tag_name in ["tagA", "tagB", "tagC"]:
            if random.random() > 0.5:
                tags[tag_name] = 1.0
                
        process = Process(name=f"process_{node}", inputs=input_tuples, outputs=output_tuples, tags=tags)
        processes.append(process)
        
    # Unique resources
    all_resources = list(set(all_resources))
        
    return processes, all_resources

def generate_solvable_query(processes: list[Process], all_resources: list[str], num_to_query: int):
    chosen_resources = random.sample(all_resources, num_to_query)
    
    demands = {res: float(random.randint(1, 100)) for res in chosen_resources}
    
    required_resources = dict(demands)
    process_scales = {}
    
    for i in range(len(processes) - 1, -1, -1):
        proc = processes[i]
        
        needed_scale = 0.0
        for qty, res_name in proc.outputs:
            req = required_resources.get(res_name, 0.0)
            if req > 0:
                needed_scale = max(needed_scale, req / qty)
                
        if needed_scale > 0:
            process_scales[proc.name] = needed_scale
            for qty, res_name, base_cost in proc.inputs:
                required_resources[res_name] = required_resources.get(res_name, 0.0) + qty * needed_scale

    totals = {"cost": 0.0, "time": 0.0, "tagA": 0.0, "tagB": 0.0, "tagC": 0.0}
    
    for proc_name, scale in process_scales.items():
        proc = next(p for p in processes if p.name == proc_name)
        totals["cost"] += scale * proc.tags.get("cost", 0.0)
        totals["time"] += scale * proc.tags.get("time", 0.0)
        for t in ["tagA", "tagB", "tagC"]:
            if t in proc.tags:
                totals[t] += 1.0
                
        for qty, res_name, base_cost in proc.inputs:
            if base_cost > 0:
                totals["cost"] += scale * base_cost
                
    return demands, totals

def main():
    parser = argparse.ArgumentParser(description="Generate synthetic benchmark DAGs.")
    parser.add_argument("--nodes", type=int, required=True, help="Number of nodes (processes) in the DAG.")
    parser.add_argument("--density", type=float, required=True, help="Edge density (0.0 to 1.0).")
    parser.add_argument("--files", type=int, required=True, help="Number of files to generate.")
    parser.add_argument("--out", type=str, required=True, help="Output directory.")
    parser.add_argument("--num_queries", type=int, default=20, help="Maximum number of queries per file to generate.")
    
    args = parser.parse_args()
    
    os.makedirs(args.out, exist_ok=True)
    
    processes, all_resources = generate_dag(args.nodes, args.density)
    base_dag_str = "\n\n".join(p.render() for p in processes)
    
    if not all_resources:
        all_resources = ["final_fallback"]
        
    goal_types = ["cheapest", "fastest"]
    
    for file_idx in range(args.files):
        file_path = os.path.join(args.out, f"benchmark_{args.nodes}_{args.density:.2f}_{file_idx+1}.rf")
        with open(file_path, "w") as f:
            f.write(base_dag_str)
            f.write("\n\n")
            
            if args.files > 1:
                fraction = file_idx / (args.files - 1)
                num_to_query = int(1 + fraction * (args.num_queries - 1))
            else:
                num_to_query = 1
                
            num_to_query = max(1, min(num_to_query, len(all_resources)))
            
            demands, totals = generate_solvable_query(processes, all_resources, num_to_query)
            
            demand_strs = [f"{qty} piece {res}" for res, qty in demands.items()]
            query_str = f"make {', '.join(demand_strs)};\n"
            
            goal = goal_types[file_idx % len(goal_types)]
            query_conditions = [goal]
            
            c_types = ["tagA", "tagB", "tagC"]
            random.shuffle(c_types)
            
            chosen_c = c_types[0]
            if totals[chosen_c] > 0:
                val = totals[chosen_c]
                query_conditions.append(f"{chosen_c} == {val:.4f}")
                
            chosen_c2 = c_types[1]
            if totals[chosen_c2] > 0:
                val = totals[chosen_c2] * 1.05
                query_conditions.append(f"{chosen_c2} <= {val:.4f}")
                
            condition_str = f"[{', '.join(query_conditions)}]"
            f.write(f"{condition_str} {query_str}")
            print(f"Generated {file_path}")

if __name__ == "__main__":
    main()
