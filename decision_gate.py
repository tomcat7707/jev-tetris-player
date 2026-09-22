def should_call_jev(
    policy,
    summary,
    candidates,
    ambiguity_gap,
    high_stack_trigger,
):
    """Return (call_jev, gate_info) for selective judgment routing."""
    if policy == "always":
        return True, {"reason": "policy_always"}
    if policy == "off":
        return False, {"reason": "policy_off"}

    if not candidates:
        return False, {"reason": "no_candidates"}

    max_height = max(summary["column_heights"])
    holes = summary["current_holes"]

    if holes > 0:
        return True, {
            "reason": "recovery_holes",
            "holes": holes,
            "max_height": max_height,
        }

    if max_height >= high_stack_trigger:
        return True, {
            "reason": "high_stack",
            "holes": holes,
            "max_height": max_height,
        }

    if len(candidates) < 2:
        return False, {
            "reason": "single_safe_candidate",
            "holes": holes,
            "max_height": max_height,
        }

    top = candidates[0]
    second = candidates[1]
    top_score = float(top.get("two_ply_score", top.get("heuristic_score", 0.0)))
    second_score = float(second.get("two_ply_score", second.get("heuristic_score", 0.0)))
    gap = top_score - second_score

    call = gap <= ambiguity_gap
    return call, {
        "reason": "ambiguous_gap" if call else "clear_deterministic_winner",
        "holes": holes,
        "max_height": max_height,
        "top_id": top.get("id"),
        "second_id": second.get("id"),
        "two_ply_gap": round(gap, 3),
        "threshold": ambiguity_gap,
    }
