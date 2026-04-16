"""
gui/components/outputs/lcc_data.py

Pure data-preparation helpers for LCC chart and tables.
No Qt or matplotlib imports - safe to use from any context.
"""

from .plots_helper.Pie import COLORS
from .helper_functions.breakdown_stages import BREAKDOWN_STAGES

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def M(x):
    """Convert to Million INR."""
    return x / 1e6


def sci_label(x):
    import numpy as np
    if x == 0:
        return "0"
    exp = int(np.floor(np.log10(abs(x))))
    coeff = x / (10 ** exp)
    return rf"${coeff:.0f}\cdot10^{{{exp}}}$"


def _get(d, *keys, default=0.0):
    """Safe nested dict access."""
    node = d
    for k in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(k, default)
    return node if node is not None else default


# ---------------------------------------------------------------------------
# Chart data
# ---------------------------------------------------------------------------

def build_chart_data(results: dict):
    """
    Build values, labels, and stage_info from results.
    Returns (values, labels, stage_info).
    Stage order: Initial → Use → Reconstruction (optional) → End-of-Life
    """
    values = []
    labels = []

    # ── Initial stage (0-4) ────────────────────────────────────────────────
    values += [
        M(_get(results, "initial_stage", "economic",     "initial_construction_cost")),
        M(_get(results, "initial_stage", "environmental","initial_material_carbon_emission_cost")),
        M(_get(results, "initial_stage", "economic",     "time_cost_of_loan")),
        M(_get(results, "initial_stage", "social",       "initial_road_user_cost")),
        M(_get(results, "initial_stage", "environmental","initial_vehicular_emission_cost")),
    ]
    labels += [
        "Initial construction cost",
        "Initial carbon emission cost",
        "Time-related cost",
        "Road user cost (construction)",
        "Vehicular emission (rerouting)",
    ]

    # ── Use stage (5-15) ───────────────────────────────────────────────────
    values += [
        M(_get(results, "use_stage", "economic",     "routine_inspection_costs")),
        M(_get(results, "use_stage", "economic",     "periodic_maintenance")),
        M(_get(results, "use_stage", "environmental","periodic_carbon_costs")),
        M(_get(results, "use_stage", "economic",     "major_inspection_costs")),
        M(_get(results, "use_stage", "economic",     "major_repair_cost")),
        M(_get(results, "use_stage", "environmental","major_repair_material_carbon_emission_costs")),
        M(_get(results, "use_stage", "environmental","major_repair_vehicular_emission_costs")),
        M(_get(results, "use_stage", "social",       "major_repair_road_user_costs")),
        M(_get(results, "use_stage", "economic",     "replacement_costs_for_bearing_and_expansion_joint")),
        M(_get(results, "use_stage", "environmental","vehicular_emission_costs_for_replacement_of_bearing_and_expansion_joint")),
        M(_get(results, "use_stage", "social",       "road_user_costs_for_replacement_of_bearing_and_expansion_joint")),
    ]
    labels += [
        "Routine inspection cost",
        "Periodic maintenance cost",
        "Maintenance carbon cost",
        "Major inspection cost",
        "Major repair cost",
        "Repair carbon emission cost",
        "Repair vehicular emission cost",
        "Road user cost (repairs)",
        "Bearing & joint replacement cost",
        "Vehicular emission (replacement)",
        "Road user cost (replacement)",
    ]

    stage_info = [
        {"start": 0,  "end": 4,  "color": "#cfd9e8", "title": "Initial Stage",      "tick_color": "#2c4a75"},
        {"start": 5,  "end": 15, "color": "#cfe8e2", "title": "Use Stage",           "tick_color": "#1f6f66"},
    ]

    # ── Reconstruction stage (optional) ────────────────────────────────────
    if bool(results.get("reconstruction")):
        recon_start = len(values)
        values += [
            M(_get(results, "reconstruction", "economic",     "cost_of_reconstruction_after_demolition")),
            M(_get(results, "reconstruction", "environmental","carbon_cost_of_reconstruction_after_demolition")),
            M(_get(results, "reconstruction", "economic",     "time_cost_of_loan")),
            M(_get(results, "reconstruction", "economic",     "total_demolition_and_disposal_costs")),
            M(_get(results, "reconstruction", "environmental","carbon_costs_demolition_and_disposal")),
            M(_get(results, "reconstruction", "environmental","demolition_vehicular_emission_cost")),
            M(_get(results, "reconstruction", "environmental","reconstruction_vehicular_emission_cost")),
            M(_get(results, "reconstruction", "social",       "ruc_demolition")),
            M(_get(results, "reconstruction", "social",       "ruc_reconstruction")),
            -M(_get(results, "reconstruction", "economic",    "total_scrap_value")),
        ]
        labels += [
            "Reconstruction cost",
            "Reconstruction carbon cost",
            "Time-related cost (recon.)",
            "Demolition & disposal (recon.)",
            "Demolition carbon cost (recon.)",
            "Vehicular emission (demo. recon.)",
            "Vehicular emission (reconstruction)",
            "Road user cost (demo. recon.)",
            "Road user cost (reconstruction)",
            "Scrap value credit (recon.)",
        ]
        stage_info.append({
            "start": recon_start, "end": len(values) - 1,
            "color": "#e8d5f0", "title": "Reconstruction Stage", "tick_color": "#5a3270",
        })

    # ── End-of-life stage ──────────────────────────────────────────────────
    eol_start = len(values)
    values += [
        M(_get(results, "end_of_life", "economic",     "total_demolition_and_disposal_costs")),
        M(_get(results, "end_of_life", "environmental","carbon_costs_demolition_and_disposal")),
        M(_get(results, "end_of_life", "environmental","demolition_vehicular_emission_cost")),
        M(_get(results, "end_of_life", "social",       "ruc_demolition")),
        -M(_get(results, "end_of_life", "economic",    "total_scrap_value")),
    ]
    labels += [
        "Demolition & disposal cost",
        "Demolition carbon cost",
        "Vehicular emission (demolition)",
        "Road user cost (demolition)",
        "Scrap value credit",
    ]
    stage_info.append({
        "start": eol_start, "end": len(values) - 1,
        "color": "#edd5d5", "title": "End-of-Life Stage", "tick_color": "#7a3b3b",
    })

    return values, labels, stage_info


# ---------------------------------------------------------------------------
# Summary table data  (_STAGE_DEFS + _stage_totals)
# ---------------------------------------------------------------------------

# Each entry: (stage_label, result_key, {category: [keys...]} )
# Prefix a key with "-" to subtract it (scrap value credits).
STAGE_DEFS = [
    ("Initial Stage", "initial_stage", {
        "Economic":      ["initial_construction_cost", "time_cost_of_loan"],
        "Environmental": ["initial_material_carbon_emission_cost", "initial_vehicular_emission_cost"],
        "Social":        ["initial_road_user_cost"],
    }),
    ("Use Stage", "use_stage", {
        "Economic":      ["routine_inspection_costs", "periodic_maintenance",
                          "major_inspection_costs", "major_repair_cost",
                          "replacement_costs_for_bearing_and_expansion_joint"],
        "Environmental": ["periodic_carbon_costs",
                          "major_repair_material_carbon_emission_costs",
                          "major_repair_vehicular_emission_costs",
                          "vehicular_emission_costs_for_replacement_of_bearing_and_expansion_joint"],
        "Social":        ["major_repair_road_user_costs",
                          "road_user_costs_for_replacement_of_bearing_and_expansion_joint"],
    }),
    ("Reconstruction Stage", "reconstruction", {
        "Economic":      ["cost_of_reconstruction_after_demolition", "time_cost_of_loan",
                          "total_demolition_and_disposal_costs", "-total_scrap_value"],
        "Environmental": ["carbon_cost_of_reconstruction_after_demolition",
                          "carbon_costs_demolition_and_disposal",
                          "demolition_vehicular_emission_cost",
                          "reconstruction_vehicular_emission_cost"],
        "Social":        ["ruc_demolition", "ruc_reconstruction"],
    }),
    ("End-of-Life Stage", "end_of_life", {
        "Economic":      ["total_demolition_and_disposal_costs", "-total_scrap_value"],
        "Environmental": ["carbon_costs_demolition_and_disposal", "demolition_vehicular_emission_cost"],
        "Social":        ["ruc_demolition"],
    }),
]


def stage_totals(results: dict, result_key: str, cat_keys: dict) -> dict:
    """Return {category: total_M_INR} for one stage.
    
    Sums all keys in each pillar dict (Economic, Environmental, Social)
    found under results[result_key]. Treats 'total_scrap_value' as a credit.
    """
    stage_data = results.get(result_key, {})
    if not isinstance(stage_data, dict):
        return {}

    totals = {}
    # We iterate over the categories defined in STAGE_DEFS (usually Economic, Environmental, Social)
    for cat in cat_keys.keys():
        cat_key = cat.lower()
        cat_data = stage_data.get(cat_key, {})
        
        total_val = 0.0
        if isinstance(cat_data, dict):
            for k, v in cat_data.items():
                if k == "total_scrap_value":
                    total_val -= M(v)
                else:
                    total_val += M(v)
        
        totals[cat] = total_val
        
    return totals


# Derived from COLORS["pillars"] - lowercased keys for category row colouring
CATEGORY_COLORS = {k.lower(): v for k, v in COLORS["pillars"].items()}
