import unittest

from tetris_engine import TetrisGame


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

    def test_candidate_generation_returns_ranked_fallback_pool(self):
        game = TetrisGame(randomizer_mode="iid", seed=7)
        candidates = game.generate_candidate_moves(game.current_piece)
        self.assertGreaterEqual(len(candidates), 1)
        self.assertLessEqual(len(candidates), 5)
        for candidate in candidates:
            self.assertIn("id", candidate)
            self.assertIn("drop_y", candidate)
            self.assertIn("contact_edges", candidate)


if __name__ == "__main__":
    unittest.main()
