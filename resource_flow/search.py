from .models import Process, Query, Resource, SolutionCandidate

class CandidateSearch:
    """Explores the process graph to find valid candidate combinations of processes."""
    
    def __init__(self, processes: list[Process], query: Query, basic_resources: dict[str, Resource], basic_resource_names: set[str]):
        self.processes = processes
        self.query = query
        self.basic_resources = basic_resources
        self.basic_resource_names = basic_resource_names

    def _matches_tags(self, required: Resource, provided: Resource) -> bool:
        """Check if a provided resource satisfies the required resource's tags."""
        req_tags = required.tags - {"basic"}
        prov_tags = provided.tags - {"basic"}
        if not req_tags.issubset(prov_tags):
            return False
        if not required.negated_tags.isdisjoint(prov_tags):
            return False
        return True

    def _can_be_basic(self, res: Resource) -> bool:
        """Check if a resource can be satisfied as a basic (externally supplied) resource."""
        if res.basic:
            return True
        if res.name in self.basic_resources:
            basic_res = self.basic_resources[res.name]
            if self._matches_tags(res, basic_res):
                return True
        return False

    def find_all_producers(self, target: Resource | str) -> list[Process]:
        """Find all processes that can produce the target resource."""
        if isinstance(target, str):
            target_name = target
            target_res = None
        else:
            target_name = target.name
            target_res = target

        producers = []
        for p in self.processes:
            for _, out_res in p.out:
                if out_res.name == target_name:
                    if target_res is None or self._matches_tags(target_res, out_res):
                        producers.append(p)
                        break
        return producers

    def topological_sort(self, procs: list[Process]) -> list[Process] | None:
        """Sort processes topologically based on resource dependencies. Returns None if a cycle exists."""
        if not procs:
            return []

        proc_map = {p.name: p for p in procs}
        in_degree = {p.name: 0 for p in procs}
        adj: dict[str, set[str]] = {p.name: set() for p in procs}

        for p2 in procs:
            for _, ingr in p2.inp:
                for p1 in procs:
                    if p1.name != p2.name:
                        for _, out_res in p1.out:
                            if out_res.name == ingr.name and self._matches_tags(ingr, out_res):
                                if p2.name not in adj[p1.name]:
                                    adj[p1.name].add(p2.name)
                                    in_degree[p2.name] += 1

        queue = sorted([p.name for p in procs if in_degree[p.name] == 0])
        sorted_names = []

        while queue:
            node = queue.pop(0)
            sorted_names.append(node)
            for neighbor in sorted(adj[node]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
                    queue.sort()

        if len(sorted_names) == len(procs):
            return [proc_map[name] for name in sorted_names]
        return None

    def find_all_candidate_dags(self) -> tuple[list[SolutionCandidate], set[str], set[str]]:
        """Search the graph and return all valid candidate combinations of processes."""
        results: list[SolutionCandidate] = []
        seen_keys: set[tuple[str, ...]] = set()
        missing_resources: set[str] = set()
        cycle_procs: set[str] = set()

        def search(
            needed: list[tuple[Process | None, Resource]],
            chosen_procs: list[Process],
            chosen_proc_names: set[str],
            active_stack: set[str],
            basic_reqs: set[str],
        ) -> None:
            unresolved = []
            for consumer, res in needed:
                is_produced = any(
                    proc != consumer
                    and any(out_res.name == res.name and self._matches_tags(res, out_res) for _, out_res in proc.out)
                    for proc in chosen_procs
                )
                if not is_produced:
                    unresolved.append((consumer, res))

            if not unresolved:
                dag_key = tuple(sorted(chosen_proc_names))
                if dag_key not in seen_keys:
                    seen_keys.add(dag_key)
                    results.append(SolutionCandidate(processes=list(chosen_procs), basic_requirements=set(basic_reqs)))
                return

            consumer, res = unresolved[0]
            producers = [p for p in self.find_all_producers(res) if p != consumer]
            can_basic = self._can_be_basic(res)

            if not producers and not can_basic:
                missing_resources.add(res.name)
                return

            if can_basic:
                search(
                    unresolved[1:],
                    chosen_procs,
                    chosen_proc_names,
                    active_stack,
                    basic_reqs | {res.name},
                )

            for proc in producers:
                if proc.name in active_stack:
                    cycle_procs.add(proc.name)
                    continue

                if proc.name in chosen_proc_names:
                    search(
                        unresolved[1:],
                        chosen_procs,
                        chosen_proc_names,
                        active_stack,
                        basic_reqs,
                    )
                else:
                    new_inputs = [(proc, r) for _, r in proc.inp]
                    chosen_procs.append(proc)
                    chosen_proc_names.add(proc.name)
                    active_stack.add(proc.name)

                    search(
                        new_inputs + unresolved[1:],
                        chosen_procs,
                        chosen_proc_names,
                        active_stack,
                        basic_reqs,
                    )

                    active_stack.remove(proc.name)
                    chosen_proc_names.remove(proc.name)
                    chosen_procs.pop()

        initial_needed: list[tuple[Process | None, Resource]] = [(None, res) for _, res in self.query.query]
        search(initial_needed, [], set(), set(), set())

        valid_candidates = []
        for cand in results:
            topo_procs = self.topological_sort(cand.processes)
            if topo_procs is not None:
                cand.processes = topo_procs
                valid_candidates.append(cand)
            else:
                cycle_procs.update(p.name for p in cand.processes)

        return valid_candidates, cycle_procs, missing_resources
