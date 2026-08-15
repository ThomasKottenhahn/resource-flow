#!/usr/bin/env python3
import argparse
import random
import os
from dataclasses import dataclass, field

@dataclass
class Process:
    name: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def render(self) -> str:
        process_str = f"{self.name} [{', '.join(self.tags)}]:\n"
        if self.inputs:
            process_str += f"    {', '.join(self.inputs)}\n"
        process_str += f"    -> {', '.join(self.outputs)};"
        return process_str

def format_resources(resource_names: list[str], all_resources: list[str]) -> list[str]:
    formatted = []
    for res in resource_names:
        qty = random.randint(1, 10)
        formatted.append(f"{qty} piece {res}")
        all_resources.append(res)
    return formatted

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
        input_strs = format_resources(inputs, all_resources)
            
        if not input_strs:
            qty = random.randint(1, 10)
            base_cost = random.randint(1, 10)
            base_res = f"base_{node}"
            input_strs.append(f"{qty} piece {base_res} * [cost: {base_cost}]")
            all_resources.append(base_res)
            
        outputs = outputs_by_node[node]
        output_strs = format_resources(outputs, all_resources)
            
        if not output_strs:
            qty = random.randint(1, 10)
            res_name = f"final_{node}"
            output_strs.append(f"{qty} piece {res_name}")
            all_resources.append(res_name)
            
        tags = [f"cost: {cost}", f"time: {time}"]
        for tag_name in ["tagA", "tagB", "tagC"]:
            if random.random() > 0.5:
                tags.append(f"{tag_name}")
                
        process = Process(name=f"process_{node}", inputs=input_strs, outputs=output_strs, tags=tags)
        processes.append(process.render())
        
    # Unique resources
    all_resources = list(set(all_resources))
        
    return processes, all_resources

def main():
    parser = argparse.ArgumentParser(description="Generate synthetic benchmark DAGs.")
    parser.add_argument("--nodes", type=int, required=True, help="Number of nodes (processes) in the DAG.")
    parser.add_argument("--density", type=float, required=True, help="Edge density (0.0 to 1.0).")
    parser.add_argument("--files", type=int, required=True, help="Number of files to generate.")
    parser.add_argument("--out", type=str, required=True, help="Output directory.")
    
    args = parser.parse_args()
    
    os.makedirs(args.out, exist_ok=True)
    
    processes, all_resources = generate_dag(args.nodes, args.density)
    base_dag_str = "\n\n".join(processes)
    
    if not all_resources:
        all_resources = ["final_fallback"]
        
    # The max number of resources to query will be 25% of all available resources
    max_resources_to_query = max(1, int(len(all_resources) * 0.25))
    
    for file_idx in range(args.files):
        file_path = os.path.join(args.out, f"benchmark_{args.nodes}_{args.density:.2f}_{file_idx+1}.rf")
        with open(file_path, "w") as f:
            f.write(base_dag_str)
            f.write("\n\n")
            
            if args.files > 1:
                fraction = file_idx / (args.files - 1)
                num_to_query = int(1 + fraction * (max_resources_to_query - 1))
            else:
                num_to_query = 1
                
            num_to_query = max(1, min(num_to_query, len(all_resources)))
            
            chosen_resources = random.sample(all_resources, num_to_query)
            
            demand_strs = []
            for res in chosen_resources:
                qty = random.randint(1, 100)
                demand_strs.append(f"{qty} piece {res}")
                
            f.write(f"[cheapest] make {', '.join(demand_strs)};\n")
            print(f"Generated {file_path}")

if __name__ == "__main__":
    main()
