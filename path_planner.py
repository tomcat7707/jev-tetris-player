from collections import deque

from tetris_engine import SHAPES


WALL_KICKS = (0, -1, 1, -2, 2)


def _rotated_states(game, piece_name, x, y, rot):
    """시계방향 회전 + 단순 wall kick 후보를 반환한다."""
    num_rot = len(SHAPES[piece_name])
    new_rot = (rot + 1) % num_rot
    for kick_x in WALL_KICKS:
        nx = x + kick_x
        if game.can_place(piece_name, new_rot, nx, y):
            yield (nx, y, new_rot), ("ROT", kick_x)


def find_control_path(game, piece_name, start_x, start_y, start_rot, target_col, target_rot):
    """
    현재 높이(start_y)에서 충돌 없이 목표 x/rotation으로 정렬하는 최단 키 입력 경로.

    현재 실험의 후보는 straight-drop landing이므로, 같은 y에서 목표 자세/열로
    정렬할 수 있으면 이후 자연 낙하 경로도 유효하다고 본다.
    """
    start = (start_x, start_y, start_rot)
    if not game.can_place(piece_name, start_rot, start_x, start_y):
        return None

    if start_x == target_col and start_rot == target_rot:
        return []

    q = deque([(start, [])])
    visited = {start}

    while q:
        (x, y, rot), path = q.popleft()

        # 좌/우
        for dx, action in ((-1, "LEFT"), (1, "RIGHT")):
            nx = x + dx
            state = (nx, y, rot)
            if state in visited:
                continue
            if game.can_place(piece_name, rot, nx, y):
                new_path = path + [(action, 0)]
                if nx == target_col and rot == target_rot:
                    return new_path
                visited.add(state)
                q.append((state, new_path))

        # 시계방향 회전 + kick
        for state, action in _rotated_states(game, piece_name, x, y, rot):
            if state in visited:
                continue
            new_path = path + [action]
            if state[0] == target_col and state[2] == target_rot:
                return new_path
            visited.add(state)
            q.append((state, new_path))

    return None


def first_reachable_candidate(game, piece_name, candidates, start_x, start_y, start_rot):
    """후보 순서대로 현재 위치에서 도달 가능한 첫 후보와 경로를 반환한다."""
    for candidate in candidates:
        path = find_control_path(
            game,
            piece_name,
            start_x,
            start_y,
            start_rot,
            candidate["col"],
            candidate["rot"],
        )
        if path is not None:
            return candidate, path
    return None, None
