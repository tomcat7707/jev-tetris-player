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

        if max_h >= 12:
            strategy_prompt = (
                "EMERGENCY: Stack is high. Prioritize low landing_height and clear lines. "
                "Do not place tall vertical pieces on ridges."
            )
        elif current_holes > 0:
            strategy_prompt = (
                "RECOVERY: Clear lines to uncover holes. Pick snug interlocking placements."
            )
        else:
            strategy_prompt = (
                "CLEAN INTERLOCKING: Maximize contact fit. "
                "Nest T-blocks (ㅗ) into sockets and use flat orientations (ㅜ/ㅡ) on plains. "
                "Avoid perching sideways (ㅏ/ㅓ) on edges."
            )

        criteria = {}
        for move in candidate_moves:
            m_id = move["id"]
            fit_status = f"Contact: {move['contact_edges']} edges"
            overhang_status = f"Overhangs: {move['overhangs']} gaps"
            criteria[m_id] = (
                f"Col {move['col']}, Shape: [{move['rot_label']}] | "
                f"Landing: {move['landing_height']}칸, {fit_status}, {overhang_status}, "
                f"Lines Cleared: {move['lines_cleared']}, Holes After: {move['total_holes_after']}."
            )

        instructions = (
            "Select the single best placement ID.\n"
            "1. FIT QUALITY: Strongly prefer moves with High Contact and 0 Overhangs (snug puzzle fit).\n"
            "2. TERRAIN MATCH: Fit T-pieces nose-down (ㅗ) into depressions. Do NOT perch sideways (ㅏ/ㅓ) on ledges.\n"
            "3. SURVIVAL: Keep landing height low and clear lines whenever safe."
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
