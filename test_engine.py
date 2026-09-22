import unittest

from tetris_engine import TetrisGame
from path_planner import find_control_path
from decision_gate import should_call_jev


def board_from_strings(rows):
    return [[None if ch == "." else ch for ch in row] for row in rows]


class TetrisEngineTests(unittest.TestCase):
    def test_7bag_contains_all_seven_pieces_once_per_bag(self):
        game = TetrisGame(randomizer_mode="7bag", seed=1234)
        first_bag = [game.current_piece, game.next_piece]
        first_bag.extend(game._draw_piece() for _ in range(5))
        self.assertEqual(len(first_bag), 7)
        self.assertEqual(len(set(first_bag)), 7)

    def test_iid_is_reproducible_with_fixed_seed(self):
        game_a = TetrisGame(randomizer_mode="iid", seed=42)
        game_b = TetrisGame(randomizer_mode="iid", seed=42)

        seq_a = [game_a.current_piece, game_a.next_piece]
        seq_b = [game_b.current_piece, game_b.next_piece]
        seq_a.extend(game_a._draw_piece() for _ in range(20))
        seq_b.extend(game_b._draw_piece() for _ in range(20))

        self.assertEqual(seq_a, seq_b)

    def test_collision_check_blocks_invalid_positions(self):
        game = TetrisGame(randomizer_mode="iid", seed=1)
        self.assertFalse(game.can_place("T", 0, -2, 0))
        self.assertFalse(game.can_place("I", 1, 3, game.height - 2))
        self.assertTrue(game.can_place("T", 0, 3, 0))

    def test_candidate_generation_contains_dellacherie_and_two_ply_features(self):
        game = TetrisGame(randomizer_mode="iid", seed=7)
        candidates = game.generate_candidate_moves(
            game.current_piece,
            next_piece=game.next_piece,
        )
        self.assertGreaterEqual(len(candidates), 1)
        self.assertLessEqual(len(candidates), 8)

        required = {
            "id",
            "drop_y",
            "heuristic_score",
            "row_transitions",
            "col_transitions",
            "eroded_piece_cells",
            "hole_depth",
            "next_best_holes",
            "next_best_max_height",
            "two_ply_score",
            "safety_filtered",
        }
        for candidate in candidates:
            self.assertTrue(required.issubset(candidate))
            self.assertTrue(candidate["safety_filtered"])

    def test_safety_envelope_rejects_avoidable_holes_from_logged_failure(self):
        # 2026-09-22 run #2 piece 37 직전 보드.
        # 기존 알고리즘은 O를 오른쪽에 놓아 holes 0 -> 3을 만들었다.
        game = TetrisGame(randomizer_mode="iid", seed=1)
        game.board = board_from_strings([
            "..........",
            "..........",
            "..........",
            "..........",
            "..........",
            "..........",
            "..........",
            "..........",
            "..........",
            "..........",
            "..........",
            "..........",
            "..........",
            "....OOOO..",
            "...JOOOO..",
            "...JJJOO..",
            "..JJJLOO..",
            "I.OOJLJJJ.",
            "I.OOSLLSJ.",
            "I.ZSSSSSS.",
        ])

        candidates = game.generate_candidate_moves("O", next_piece="I")
        self.assertGreater(len(candidates), 0)
        self.assertEqual(game.count_holes(), 0)
        self.assertTrue(all(c["total_holes_after"] == 0 for c in candidates))


    def test_selective_gate_skips_clear_deterministic_winner(self):
        summary = {
            "column_heights": [2, 2, 3, 3, 2, 2, 1, 1, 0, 0],
            "current_holes": 0,
        }
        candidates = [
            {"id": "a", "two_ply_score": -100.0, "heuristic_score": -80.0},
            {"id": "b", "two_ply_score": -120.5, "heuristic_score": -90.0},
        ]
        call, info = should_call_jev(
            "ambiguous",
            summary,
            candidates,
            ambiguity_gap=10.0,
            high_stack_trigger=8,
        )
        self.assertFalse(call)
        self.assertEqual(info["reason"], "clear_deterministic_winner")

    def test_selective_gate_calls_jev_on_ambiguous_or_risky_state(self):
        clean_summary = {
            "column_heights": [2, 2, 3, 3, 2, 2, 1, 1, 0, 0],
            "current_holes": 0,
        }
        candidates = [
            {"id": "a", "two_ply_score": -100.0, "heuristic_score": -80.0},
            {"id": "b", "two_ply_score": -106.0, "heuristic_score": -82.0},
        ]
        call, info = should_call_jev(
            "ambiguous",
            clean_summary,
            candidates,
            ambiguity_gap=10.0,
            high_stack_trigger=8,
        )
        self.assertTrue(call)
        self.assertEqual(info["reason"], "ambiguous_gap")

        recovery_summary = {
            "column_heights": [3, 3, 4, 4, 3, 3, 2, 2, 1, 1],
            "current_holes": 1,
        }
        call, info = should_call_jev(
            "ambiguous",
            recovery_summary,
            candidates,
            ambiguity_gap=10.0,
            high_stack_trigger=8,
        )
        self.assertTrue(call)
        self.assertEqual(info["reason"], "recovery_holes")

    def test_path_planner_finds_collision_aware_route(self):
        game = TetrisGame(randomizer_mode="iid", seed=1)
        path = find_control_path(
            game,
            "T",
            start_x=3,
            start_y=0,
            start_rot=0,
            target_col=0,
            target_rot=2,
        )
        self.assertIsNotNone(path)
        self.assertGreater(len(path), 0)


if __name__ == "__main__":
    unittest.main()
