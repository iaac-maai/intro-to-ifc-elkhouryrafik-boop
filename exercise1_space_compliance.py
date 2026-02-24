"""Exercise 1: Space compliance against basic Catalan code thresholds."""

from pathlib import Path
from typing import Any, Dict, List, Optional


REQUIREMENTS = {
    "Living Room": {"min_height": 2.6, "min_area": 16.0},
    "Bedroom": {"min_height": 2.6, "min_area": 9.0},
    "Kitchen": {"min_height": 2.6, "min_area": 8.0},
    "Bathroom": {"min_height": 2.3, "min_area": 4.0},
    "Corridor": {"min_height": 2.3, "min_area": 1.5},
}


def _extract_quantities(space: Any) -> Dict[str, float]:
    values: Dict[str, float] = {}
    # Some IFC exports expose quantities directly on the entity.
    if hasattr(space, "Quantities") and getattr(space, "Quantities", None):
        for quantity in getattr(space.Quantities, "Quantities", []) or []:
            qname = (getattr(quantity, "Name", "") or "").lower()
            if hasattr(quantity, "AreaValue"):
                values[qname] = float(quantity.AreaValue)
            elif hasattr(quantity, "LengthValue"):
                values[qname] = float(quantity.LengthValue)
            elif hasattr(quantity, "VolumeValue"):
                values[qname] = float(quantity.VolumeValue)

    for rel in getattr(space, "IsDefinedBy", []) or []:
        pdef = getattr(rel, "RelatingPropertyDefinition", None)
        if not pdef:
            continue
        if pdef.is_a("IfcElementQuantity"):
            for quantity in getattr(pdef, "Quantities", []) or []:
                qname = (getattr(quantity, "Name", "") or "").lower()
                if hasattr(quantity, "AreaValue"):
                    values[qname] = float(quantity.AreaValue)
                elif hasattr(quantity, "LengthValue"):
                    values[qname] = float(quantity.LengthValue)
                elif hasattr(quantity, "VolumeValue"):
                    values[qname] = float(quantity.VolumeValue)
        elif pdef.is_a("IfcPropertySet"):
            for prop in getattr(pdef, "HasProperties", []) or []:
                pname = (getattr(prop, "Name", "") or "").lower()
                nominal = getattr(prop, "NominalValue", None)
                wrapped = getattr(nominal, "wrappedValue", None)
                if isinstance(wrapped, (int, float)):
                    values[pname] = float(wrapped)
    return values


def _classify_from_text(text: str) -> Optional[str]:
    t = (text or "").lower()
    if any(k in t for k in ["living", "salon", "sala", "menjador"]):
        return "Living Room"
    if any(k in t for k in ["bed", "bedroom", "habit", "dorm"]):
        return "Bedroom"
    if any(k in t for k in ["kitchen", "cuina", "cocina"]):
        return "Kitchen"
    if any(k in t for k in ["bath", "toilet", "lavabo", "wc", "bany"]):
        return "Bathroom"
    if any(k in t for k in ["corridor", "hall", "pasillo", "entry", "vestib", "distrib"]):
        return "Corridor"
    return None


def _classify_space(space: Any, area: Optional[float]) -> Optional[str]:
    # Try multiple metadata fields before area heuristics.
    candidates = [
        getattr(space, "Name", None),
        getattr(space, "LongName", None),
        getattr(space, "Description", None),
        getattr(space, "ObjectType", None),
    ]
    for value in candidates:
        classified = _classify_from_text(value or "")
        if classified:
            return classified

    # Fallback for coded names like A101/B201 where semantics are not present.
    if area is not None:
        if area >= 16.0:
            return "Living Room"
        if area >= 9.0:
            return "Bedroom"
        if area >= 8.0:
            return "Kitchen"
        if area >= 4.0:
            return "Bathroom"
        return "Corridor"
    return None


def check_space_compliance(spaces: List[Any]) -> Dict[str, Any]:
    """
    Validate each IfcSpace against area/height minimums.

    Returns a report with passed/failed spaces, warnings, and summary metrics.
    """
    report: Dict[str, Any] = {"passed": [], "failed": [], "warnings": [], "summary": {}}

    for space in spaces:
        name = getattr(space, "Name", None) or "Unnamed"
        q = _extract_quantities(space)

        area = next((q[k] for k in ["netfloorarea", "grossfloorarea", "area", "net area"] if k in q), None)
        height = next((q[k] for k in ["height", "netheight", "clearheight", "unbounded height"] if k in q), None)
        if height is None and area and "grossvolume" in q and area > 0:
            height = q["grossvolume"] / area
        space_type = _classify_space(space, area)

        item = {
            "space": name,
            "space_type": space_type or "Unknown",
            "area": area,
            "height": height,
            "guid": getattr(space, "GlobalId", None),
        }

        reasons: List[str] = []
        if not space_type:
            reasons.append("Space type could not be inferred from name")
        else:
            req = REQUIREMENTS[space_type]
            if area is None:
                reasons.append("Missing floor area")
            elif area < req["min_area"]:
                reasons.append(f"Area {area:.2f}m2 < required {req['min_area']}m2")

            if height is None:
                reasons.append("Missing room height")
            elif height < req["min_height"]:
                reasons.append(f"Height {height:.2f}m < required {req['min_height']}m")

        if reasons:
            item["reasons"] = reasons
            report["failed"].append(item)
            if not space_type:
                report["warnings"].append(f"{name}: unknown space type")
        else:
            report["passed"].append(item)

    total = len(spaces)
    passed_count = len(report["passed"])
    failed_count = len(report["failed"])
    report["summary"] = {
        "total_spaces": total,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "compliance_rate": (passed_count / total) if total else 0.0,
        "overall_compliant": failed_count == 0,
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
    report = check_space_compliance(spaces)
    summary = report["summary"]
    print("Exercise 1 - Space Compliance")
    print(f"Total spaces: {summary['total_spaces']}")
    print(f"Passed: {summary['passed_count']}")
    print(f"Failed: {summary['failed_count']}")
    print(f"Compliance rate: {summary['compliance_rate']:.1%}")
    if report["failed"]:
        print("Sample failures:")
        for item in report["failed"][:5]:
            print(f"- {item['space']}: {', '.join(item['reasons'])}")
    return 0


if __name__ == "__main__":
    _run_cli()
