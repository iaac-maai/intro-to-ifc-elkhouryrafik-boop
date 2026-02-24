"""Bonus exercise: simplified fire safety route analysis."""

from collections import defaultdict, deque
import math
from pathlib import Path
import heapq
from typing import Any, Dict, List, Optional, Tuple


def _space_name(space: Any) -> str:
    return getattr(space, "Name", None) or getattr(space, "GlobalId", "Unnamed")


def _door_connected_spaces(door: Any) -> List[str]:
    names: List[str] = []
    for rel in getattr(door, "ProvidesBoundaries", []) or []:
        space = getattr(rel, "RelatingSpace", None)
        if space and space.is_a("IfcSpace"):
            names.append(_space_name(space))

    unique: List[str] = []
    for name in names:
        if name not in unique:
            unique.append(name)
    return unique


def _space_coords(space: Any) -> Optional[Tuple[float, float]]:
    placement = getattr(space, "ObjectPlacement", None)
    rel = getattr(placement, "RelativePlacement", None) if placement else None
    location = getattr(rel, "Location", None) if rel else None
    coords = getattr(location, "Coordinates", None) if location else None
    if coords and len(coords) >= 2:
        return float(coords[0]), float(coords[1])
    return None


def analyze_evacuation_routes(ifc_model: Any, spaces: List[Any]) -> Dict[str, Any]:
    """
    Build a space graph, estimate max travel distance to exits, and flag risks.
    """
    doors = ifc_model.by_type("IfcDoor")
    analysis: Dict[str, Any] = {
        "total_spaces": len(spaces),
        "total_doors": len(doors),
        "graph": {},
        "longest_route": None,
        "longest_distance": 0.0,
        "safety_issues": [],
        "compliant": False,
    }

    names = [_space_name(space) for space in spaces]
    graph = defaultdict(set)

    for door in doors:
        connected = _door_connected_spaces(door)
        if len(connected) >= 2:
            for i in range(len(connected)):
                for j in range(i + 1, len(connected)):
                    a, b = connected[i], connected[j]
                    graph[a].add(b)
                    graph[b].add(a)

    # Keep graph connected even if IFC boundaries are incomplete.
    for i in range(len(names) - 1):
        if names[i] not in graph and names[i + 1] not in graph:
            graph[names[i]].add(names[i + 1])
            graph[names[i + 1]].add(names[i])

    exits = [n for n in names if any(k in n.lower() for k in ["entry", "entrance", "exit", "hall"])]
    if not exits and names:
        exits = [names[0]]

    assumed_edge_distance_m = 5.0
    coords_by_name = {_space_name(space): _space_coords(space) for space in spaces}

    def edge_distance(a: str, b: str) -> float:
        ca = coords_by_name.get(a)
        cb = coords_by_name.get(b)
        if ca is None or cb is None:
            return assumed_edge_distance_m
        return math.dist(ca, cb)

    def min_distance_to_exit(start: str):
        best = {start: 0.0}
        prev = {start: None}
        heap = [(0.0, start)]
        target = None
        while heap:
            dist, node = heapq.heappop(heap)
            if dist > best.get(node, math.inf):
                continue
            if node in exits:
                target = node
                break
            for nxt in graph[node]:
                nd = dist + edge_distance(node, nxt)
                if nd < best.get(nxt, math.inf):
                    best[nxt] = nd
                    prev[nxt] = node
                    heapq.heappush(heap, (nd, nxt))

        if target is None:
            return math.inf, []

        path = []
        cur = target
        while cur is not None:
            path.append(cur)
            cur = prev.get(cur)
        path.reverse()
        return best[target], path

    for start in names:
        dist, path = min_distance_to_exit(start)
        if dist != math.inf and dist > analysis["longest_distance"]:
            analysis["longest_distance"] = dist
            analysis["longest_route"] = path

    if analysis["longest_distance"] > 25.0:
        analysis["safety_issues"].append(
            f"Longest travel distance is {analysis['longest_distance']:.1f}m (> 25m)"
        )

    for door in doors:
        width = getattr(door, "OverallWidth", None)
        if width is not None and float(width) < 0.8:
            dname = getattr(door, "Name", None) or getattr(door, "GlobalId", "UnnamedDoor")
            analysis["safety_issues"].append(f"Door '{dname}' width {float(width):.2f}m < 0.80m")

    for space in spaces:
        sname = _space_name(space)
        if "corridor" in sname.lower() or "hall" in sname.lower():
            corridor_width = None
            for rel in getattr(space, "IsDefinedBy", []) or []:
                pdef = getattr(rel, "RelatingPropertyDefinition", None)
                if pdef and pdef.is_a("IfcElementQuantity"):
                    for quantity in getattr(pdef, "Quantities", []) or []:
                        qname = (getattr(quantity, "Name", "") or "").lower()
                        if "width" in qname and hasattr(quantity, "LengthValue"):
                            corridor_width = float(quantity.LengthValue)
                            break
                if corridor_width is not None:
                    break
            if corridor_width is not None and corridor_width < 1.2:
                analysis["safety_issues"].append(
                    f"Corridor '{sname}' width {corridor_width:.2f}m < 1.20m"
                )

    # Dead-end check: flag branches longer than 10m before reaching exit or junction.
    for node, neighbors in graph.items():
        if node in exits or len(neighbors) != 1:
            continue
        length = 0.0
        prev = None
        cur = node
        while True:
            nxt_candidates = [n for n in graph[cur] if n != prev]
            if not nxt_candidates:
                break
            nxt = nxt_candidates[0]
            length += edge_distance(cur, nxt)
            prev, cur = cur, nxt
            if cur in exits:
                break
            if len(graph[cur]) != 2:
                break
        if cur not in exits and length > 10.0:
            analysis["safety_issues"].append(
                f"Dead-end branch from '{node}' is {length:.1f}m (> 10m)"
            )

    analysis["graph"] = {node: sorted(list(neighbors)) for node, neighbors in graph.items()}
    analysis["compliant"] = len(analysis["safety_issues"]) == 0
    return analysis


def _run_cli() -> int:
    ifc_path = Path("assets/duplex.ifc")
    try:
        import ifcopenshell  # type: ignore
    except ImportError:
        print("Missing dependency: ifcopenshell. Install with `py -m pip install -r requirements.txt`.")
        return 1

    if not ifc_path.exists():
        print(f"IFC file not found: {ifc_path}")
        return 1

    model = ifcopenshell.open(str(ifc_path))
    spaces = model.by_type("IfcSpace")
    analysis = analyze_evacuation_routes(model, spaces)

    print("Exercise 3 - Evacuation Routes")
    print(f"Total spaces: {analysis['total_spaces']}")
    print(f"Total doors: {analysis['total_doors']}")
    print(f"Longest distance: {analysis['longest_distance']:.1f} m")
    print(f"Compliant: {analysis['compliant']}")
    if analysis["longest_route"]:
        print(f"Longest route: {' -> '.join(analysis['longest_route'])}")
    if analysis["safety_issues"]:
        print("Safety issues:")
        for issue in analysis["safety_issues"][:8]:
            print(f"- {issue}")
    return 0


if __name__ == "__main__":
    _run_cli()
