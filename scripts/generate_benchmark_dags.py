#!/usr/bin/env python3
import argparse
import random
import os

def generate_dag(nodes_count, density):
    possible_edges = [(i, j) for i in range(nodes_count) for j in range(i + 1, nodes_count)]
    
    num_edges = int(len(possible_edges) * density)
    selected_edges = random.sample(possible_edges, num_edges)
    
    outputs_by_node = {i: [] for i in range(nodes_count)}
    inputs_by_node = {i: [] for i in range(nodes_count)}
    
    for (i, j) in selected_edges:
        res_name = f"res_{i}_{j}"
        outputs_by_node[i].append(res_name)
        inputs_by_node[j].append(res_name)
        
    processes = []
    all_resources = []
    
    for i in range(nodes_count):
        cost = random.randint(1, 100)
        time = random.randint(1, 100)
        
        inputs = inputs_by_node[i]
        input_strs = []
        for inp in inputs:
            qty = random.randint(1, 10)
            input_strs.append(f"{qty} piece {inp}")
            all_resources.append(inp)
            
        if not input_strs:
            qty = random.randint(1, 10)
            base_cost = random.randint(1, 10)
            base_res = f"base_{i}"
            input_strs.append(f"{qty} piece {base_res} * [cost: {base_cost}]")
            all_resources.append(base_res)
            
        outputs = outputs_by_node[i]
        output_strs = []
        for out in outputs:
            qty = random.randint(1, 10)
            output_strs.append(f"{qty} piece {out}")
            all_resources.append(out)
            
        if not output_strs:
            qty = random.randint(1, 10)
            res_name = f"final_{i}"
            output_strs.append(f"{qty} piece {res_name}")
            all_resources.append(res_name)
            
        tags = [f"cost: {cost}", f"time: {time}"]
        for tag_name in ["tagA", "tagB", "tagC"]:
            if random.random() > 0.5:
                tags.append(f"{tag_name}")
                
        process_str = f"process_{i} [{', '.join(tags)}]:\n"
        if input_strs:
            process_str += f"    {', '.join(input_strs)}\n"
        process_str += f"    -> {', '.join(output_strs)};"
        
        processes.append(process_str)
        
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
    
    for k in range(args.files):
        file_path = os.path.join(args.out, f"benchmark_{args.nodes}_{args.density:.2f}_{k+1}.rf")
        with open(file_path, "w") as f:
            f.write(base_dag_str)
            f.write("\n\n")
            
            if args.files > 1:
                fraction = k / (args.files - 1)
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
