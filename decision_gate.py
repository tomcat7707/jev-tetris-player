def should_call_jev(
    policy,
    summary,
    candidates,
    ambiguity_gap,
    high_stack_trigger,
    low_flex_trigger=2,
    deep_well_trigger=4,
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

    # 위험/복구 상태는 애매도와 무관하게 JEV에게 한 번 더 판단시킨다.
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
        return True, {
            "reason": "single_candidate_risk",
            "holes": holes,
            "max_height": max_height,
        }

    top = candidates[0]
    second = candidates[1]

    # v4 candidate list는 robust_score 순서이므로 gate도 같은 기준으로
    # top-2 ambiguity를 측정해야 한다.
    top_score = float(
        top.get(
            "robust_score",
            top.get("two_ply_score", top.get("heuristic_score", 0.0)),
        )
    )
    second_score = float(
        second.get(
            "robust_score",
            second.get("two_ply_score", second.get("heuristic_score", 0.0)),
        )
    )
    gap = top_score - second_score

    top_nonworsening = top.get("next_nonworsening_count")
    if (
        top_nonworsening is not None
        and int(top_nonworsening) <= low_flex_trigger
    ):
        return True, {
            "reason": "low_future_flexibility",
            "holes": holes,
            "max_height": max_height,
            "top_id": top.get("id"),
            "next_nonworsening_count": int(top_nonworsening),
            "threshold": low_flex_trigger,
            "robust_gap": round(gap, 3),
        }

    top_well = int(top.get("max_well_depth", 0) or 0)
    if top_well >= deep_well_trigger:
        return True, {
            "reason": "deep_well_risk",
            "holes": holes,
            "max_height": max_height,
            "top_id": top.get("id"),
            "max_well_depth": top_well,
            "threshold": deep_well_trigger,
            "robust_gap": round(gap, 3),
        }

    call = gap <= ambiguity_gap
    return call, {
        "reason": "ambiguous_gap" if call else "clear_deterministic_winner",
        "holes": holes,
        "max_height": max_height,
        "top_id": top.get("id"),
        "second_id": second.get("id"),
        "robust_gap": round(gap, 3),
        "threshold": ambiguity_gap,
    }
