import time
import requests
from config import TYPESAFE_API_KEY, TYPESAFE_API_URL


class JevTetrisAgent:
    def __init__(self, api_key=None):
        self.api_key = api_key or TYPESAFE_API_KEY
        self.endpoint = TYPESAFE_API_URL

        # HTTP keep-alive로 매 블록마다 TCP/TLS 연결을 새로 맺는 비용을 줄인다.
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })

    def evaluate_best_move(self, board_summary, candidate_moves):
        start_t = time.perf_counter()

        if not self.api_key:
            return {"success": False, "error_msg": "API Key Missing", "sent_payload": {}}

        active_p = board_summary["current_piece"]
        heights = board_summary["column_heights"]
        max_h = max(heights)
        current_holes = board_summary["current_holes"]

        if max_h >= 15:
            strategy_prompt = (
                "CRITICAL SURVIVAL: The stack is near top-out. Preserve spawn space, "
                "avoid creating holes, and prefer continuations that keep next-piece "
                "max height low."
            )
        elif current_holes > 0:
            strategy_prompt = (
                "RECOVERY: Do not add avoidable holes. Prefer moves whose two-ply "
                "continuation reduces or preserves holes while keeping the stack smooth."
            )
        else:
            strategy_prompt = (
                "CLEAN BUILD: Keep zero holes whenever possible. Prefer low-transition, "
                "low-well boards with a safe continuation for the known next piece."
            )

        criteria = {}
        for move in candidate_moves:
            m_id = move["id"]
            criteria[m_id] = (
                f"Col {move['col']}, Shape: [{move['rot_label']}] | "
                f"HolesNow: {move['total_holes_after']} (delta {move['delta_holes']:+d}), "
                f"HoleDepth: {move['hole_depth']}, "
                f"MaxHeight: {move['max_height']}, MaxCliff: {move.get('max_cliff')}, "
                f"MaxWellDepth: {move.get('max_well_depth')}, Wells: {move['cumulative_wells']}, "
                f"NextBestHoles: {move.get('next_best_holes')}, "
                f"NextBestMaxHeight: {move.get('next_best_max_height')}, "
                f"NextBestMaxWell: {move.get('next_best_max_well_depth')}, "
                f"NextOptions: {move.get('next_option_count')}, "
                f"NextNonWorsening: {move.get('next_nonworsening_count')}, "
                f"RowTrans: {move['row_transitions']}, ColTrans: {move['col_transitions']}, "
                f"Lines: {move['lines_cleared']}, ErodedCells: {move['eroded_piece_cells']}, "
                f"DellacherieScore: {move['heuristic_score']}, "
                f"TwoPlyScore: {move.get('two_ply_score')}, "
                f"RobustScore: {move.get('robust_score')}."
            )

        instructions = (
            "Select the single best placement ID for long-run survival.\n"
            "The list intentionally contains diverse legal alternatives; some may accept a "
            "small temporary cost to preserve future maneuverability.\n"
            "Priority guidance:\n"
            "1. AVOID TRAPS: Do not create very deep one-cell wells, huge cliffs, or tall "
            "isolated towers that require a specific future piece to repair.\n"
            "2. FUTURE FLEXIBILITY: Prefer more NextOptions and NextNonWorsening choices. "
            "A state with only one continuation is fragile even if it has zero holes now.\n"
            "3. HOLES: Fewer and shallower holes are strongly preferred, but holes are NOT "
            "an absolute rule. A shallow temporary hole can be better than a catastrophic "
            "canyon or near-top-out stack.\n"
            "4. TWO-PLY SURVIVAL: Use known NEXT outcomes, especially NextBestHoles, "
            "NextBestMaxHeight and NextBestMaxWell.\n"
            "5. GLOBAL SHAPE: Prefer low transitions, low wells, low max height and smooth "
            "terrain. Reward line clears when they improve the board structurally.\n"
            "Choose the move that keeps the system recoverable under unlucky future pieces, "
            "not merely the move that looks clean immediately."
        )

        payload = {
            "model": "jev-latest",
            "state": {
                "active_piece": active_p,
                "next_piece": board_summary.get("next_piece", "Unknown"),
                "board_heights": heights,
                "current_holes": current_holes,
                "strategy_instruction": strategy_prompt
            },
            "questions": {
                "best_placement": {
                    "type": "choice",
                    "instructions": instructions,
                    "criteria": criteria
                }
            }
        }

        try:
            response = self.session.post(self.endpoint, json=payload, timeout=6.0)
            latency = int((time.perf_counter() - start_t) * 1000)

            if response.status_code == 200:
                res_json = response.json()
                answer = res_json["answers"]["best_placement"]
                return {
                    "success": True,
                    "choice_id": answer["choice"],
                    "confidence": answer.get("confidence", 0.0),
                    "latency_ms": latency,
                    "sent_payload": payload["state"],
                    "strategy_summary": strategy_prompt,
                    "error_msg": None
                }

            return {
                "success": False,
                "error_msg": f"HTTP {response.status_code}",
                "latency_ms": latency,
                "sent_payload": payload["state"]
            }

        except requests.exceptions.Timeout:
            latency = int((time.perf_counter() - start_t) * 1000)
            return {
                "success": False,
                "error_msg": "Timeout (6s)",
                "latency_ms": latency,
                "sent_payload": payload["state"]
            }
        except Exception as e:
            latency = int((time.perf_counter() - start_t) * 1000)
            return {
                "success": False,
                "error_msg": str(e),
                "latency_ms": latency,
                "sent_payload": payload["state"]
            }
