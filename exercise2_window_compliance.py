"""Exercise 2: Window compliance checks for natural light requirements."""

from pathlib import Path
from typing import Any, Dict, List, Tuple


def _extract_space_area(space: Any) -> float:
    for rel in getattr(space, "IsDefinedBy", []) or []:
        pdef = getattr(rel, "RelatingPropertyDefinition", None)
        if pdef and pdef.is_a("IfcElementQuantity"):
            for quantity in getattr(pdef, "Quantities", []) or []:
                qname = (getattr(quantity, "Name", "") or "").lower()
                if "area" in qname and hasattr(quantity, "AreaValue"):
                    return float(quantity.AreaValue)
    return None


def _window_dimensions(window: Any) -> Tuple[float, float]:
    width = getattr(window, "OverallWidth", None)
    height = getattr(window, "OverallHeight", None)
    if width is not None and height is not None:
        return float(width), float(height)
    return None, None


def _window_orientation(window: Any) -> str:
    placement = getattr(window, "ObjectPlacement", None)
    rel = getattr(placement, "RelativePlacement", None) if placement else None
    axis = getattr(rel, "RefDirection", None) if rel else None
    ratios = getattr(axis, "DirectionRatios", None) if axis else None
    if ratios and len(ratios) >= 2:
        x = float(ratios[0])
        y = float(ratios[1])
        return "E/W" if abs(x) >= abs(y) else "N/S"
    return "Unknown"


def _is_habitable(name: str) -> bool:
    n = (name or "").lower()
    return any(k in n for k in ["living", "bed", "habit", "dorm", "kitchen", "salon", "sala"])


def _candidate_space_names(window: Any) -> List[str]:
    names: List[str] = []
    for rel in getattr(window, "ContainedInStructure", []) or []:
        container = getattr(rel, "RelatingStructure", None)
        if container and container.is_a("IfcSpace"):
            names.append(getattr(container, "Name", None) or getattr(container, "GlobalId", None))
    for boundary in getattr(window, "ProvidesBoundaries", []) or []:
        space = getattr(boundary, "RelatingSpace", None)
        if space and space.is_a("IfcSpace"):
            names.append(getattr(space, "Name", None) or getattr(space, "GlobalId", None))
    unique: List[str] = []
    for name in names:
        if name and name not in unique:
            unique.append(name)
    return unique


def analyze_window_compliance(ifc_model: Any, spaces: List[Any]) -> Dict[str, Any]:
    """
    Analyze window coverage per space and verify minimum light/opening criteria.
    """
    windows = ifc_model.by_type("IfcWindow")
    report: Dict[str, Any] = {
        "total_windows": len(windows),
        "windows_by_space": {},
        "compliance_status": {},
        "unassigned_windows": [],
    }

    for space in spaces:
        sname = getattr(space, "Name", None) or getattr(space, "GlobalId", "Unnamed")
        report["windows_by_space"][sname] = {"space_area": _extract_space_area(space), "windows": []}

    for window in windows:
        width, height = _window_dimensions(window)
        area = (width * height) if (width and height) else None
        window_data = {
            "name": getattr(window, "Name", None) or getattr(window, "GlobalId", "UnnamedWindow"),
            "width": width,
            "height": height,
            "area": area,
            "orientation": _window_orientation(window),
            "min_dimensions_ok": bool(width and height and width >= 0.6 and height >= 1.0),
        }

        linked = False
        for sname in _candidate_space_names(window):
            if sname in report["windows_by_space"]:
                report["windows_by_space"][sname]["windows"].append(window_data)
                linked = True
        if not linked:
            report["unassigned_windows"].append(window_data)

    for space in spaces:
        sname = getattr(space, "Name", None) or getattr(space, "GlobalId", "Unnamed")
        entry = report["windows_by_space"][sname]
        space_area = entry["space_area"]
        total_window_area = sum(w["area"] or 0 for w in entry["windows"])
        ratio = (total_window_area / space_area) if (space_area and space_area > 0) else None
        requires_window = _is_habitable(sname)

        compliant = True
        reasons: List[str] = []
        if requires_window and not entry["windows"]:
            compliant = False
            reasons.append("No windows found in habitable space")
        if requires_window and (space_area is None or space_area <= 0):
            compliant = False
            reasons.append("Missing floor area, cannot validate 1/8 window ratio")
        if requires_window and ratio is not None and ratio < 0.125:
            compliant = False
            reasons.append(f"Window/floor ratio {ratio:.3f} < 0.125")
        if any(not w["min_dimensions_ok"] for w in entry["windows"]):
            compliant = False
            reasons.append("At least one window is below 0.6m x 1.0m")

        report["compliance_status"][sname] = {
            "space_area": space_area,
            "window_count": len(entry["windows"]),
            "total_window_area": total_window_area,
            "window_to_floor_ratio": ratio,
            "requires_window": requires_window,
            "compliant": compliant,
            "reasons": reasons,
        }

    return report


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
    report = analyze_window_compliance(model, spaces)
    statuses = report["compliance_status"]
    compliant = [name for name, item in statuses.items() if item["compliant"]]
    failed = [name for name, item in statuses.items() if not item["compliant"]]

    print("Exercise 2 - Window Compliance")
    print(f"Total windows: {report['total_windows']}")
    print(f"Spaces analyzed: {len(statuses)}")
    print(f"Compliant spaces: {len(compliant)}")
    print(f"Non-compliant spaces: {len(failed)}")
    print(f"Unassigned windows: {len(report['unassigned_windows'])}")
    if failed:
        print("Sample non-compliant spaces:")
        for name in failed[:5]:
            reasons = ", ".join(statuses[name]["reasons"]) or "No reason recorded"
            print(f"- {name}: {reasons}")
    return 0


if __name__ == "__main__":
    _run_cli()
