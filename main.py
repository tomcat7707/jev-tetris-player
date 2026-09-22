import sys
import time
import threading

import pygame

from config import (
    BLOCK_SIZE,
    BOARD_WIDTH,
    BOARD_HEIGHT,
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    FPS,
    PIECE_RANDOMIZER,
    TETRIS_RANDOM_SEED,
    JEV_DECISION_DEADLINE_MS,
)
from tetris_engine import TetrisGame, PIECE_COLORS, SHAPES, ORIENTATION_LABELS
from jev_agent import JevTetrisAgent
from telemetry import ExperimentLogger, compact_board, compact_candidate


def draw_block(screen, x, y, color, border_color=(40, 40, 40), width=0):
    rect = pygame.Rect(x, y, BLOCK_SIZE, BLOCK_SIZE)
    if width == 0:
        pygame.draw.rect(screen, color, rect)
        pygame.draw.line(screen, (255, 255, 255), (x, y), (x + BLOCK_SIZE - 1, y), 2)
        pygame.draw.line(screen, (255, 255, 255), (x, y), (x, y + BLOCK_SIZE - 1), 2)
    pygame.draw.rect(screen, border_color, rect, 1 if width == 0 else width)


def draw_piece_preview(screen, x, y, piece_name, label, font):
    box_rect = pygame.Rect(x, y, 95, 75)
    pygame.draw.rect(screen, (20, 22, 28), box_rect, border_radius=4)
    pygame.draw.rect(screen, (55, 60, 75), box_rect, 1, border_radius=4)

    lbl_color = (0, 240, 200) if label == "CURRENT" else (160, 170, 185)
    screen.blit(font.render(label, True, lbl_color), (x + 8, y + 4))

    shape = SHAPES[piece_name][0]
    color = PIECE_COLORS.get(piece_name, (200, 200, 200))
    min_x = min(cx for cx, cy in shape)
    max_x = max(cx for cx, cy in shape)
    min_y = min(cy for cx, cy in shape)
    max_y = max(cy for cx, cy in shape)
    p_w = (max_x - min_x + 1) * 14
    p_h = (max_y - min_y + 1) * 14
    start_x = x + (95 - p_w) // 2 - min_x * 14
    start_y = y + 20 + (50 - p_h) // 2 - min_y * 14

    for cx, cy in shape:
        r = pygame.Rect(start_x + cx * 14, start_y + cy * 14, 13, 13)
        pygame.draw.rect(screen, color, r)


def terrain_summary(summary):
    h_list = summary["column_heights"]
    min_h, max_h = min(h_list), max(h_list)
    diff = max_h - min_h

    if max_h >= 12:
        terrain = f"위험 상태: 최고 {max_h}칸 (저지대 유도)"
        goal = "굴뚝 회피 및 안전 저지대 안착"
    elif diff >= 5:
        terrain = f"단차 상태: 높이차 {diff}칸 (최저 {min_h} ~ 최고 {max_h})"
        goal = "협곡(Well) 메우기를 통한 평탄화"
    else:
        terrain = f"안정 상태: 평균 {max_h}칸 고른 분포"
        goal = "착지점 낮게 유지하며 라인 클리어"

    return terrain, goal


def move_narrative(move):
    lh = move["landing_height"]
    if move["lines_cleared"] > 0:
        return f"{move['col']}번 열 후보 → 라인 {move['lines_cleared']}줄 삭제 예상"
    if lh <= 8:
        return f"{move['col']}번 열 후보 → 낮은 착지({lh}칸) 유지"
    return f"{move['col']}번 열 후보 → 협곡 억제 및 안정화"


def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("JEV Tetris - Real-Time Decision Stress Test")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("malgungothic", 12)
    bold_font = pygame.font.SysFont("malgungothic", 13, bold=True)
    title_font = pygame.font.SysFont("malgungothic", 18, bold=True)

    randomizer_mode = PIECE_RANDOMIZER
    game = TetrisGame(
        BOARD_WIDTH,
        BOARD_HEIGHT,
        randomizer_mode=randomizer_mode,
        seed=TETRIS_RANDOM_SEED,
    )
    agent = JevTetrisAgent()

    telemetry = ExperimentLogger(
        session_config={
            "fps": FPS,
            "gravity_speed_frames": 12,
            "das_speed_frames": 4,
            "randomizer": randomizer_mode,
            "random_seed": TETRIS_RANDOM_SEED,
            "jev_deadline_ms": JEV_DECISION_DEADLINE_MS,
            "board_width": BOARD_WIDTH,
            "board_height": BOARD_HEIGHT,
        }
    )
    print(f"[telemetry] JSONL: {telemetry.log_path}")
    print(f"[telemetry] summary: {telemetry.summary_path}")

    running = True
    auto_play = True

    inspector_data = {
        "active_piece": game.current_piece,
        "next_piece": game.next_piece,
        "heights": game.get_column_heights(),
        "terrain_diagnosis": "지형 분석 대기 중...",
        "strategy_goal": "평탄화 및 바닥 안착",
        "chosen_move": None,
        "decision_narrative": "실시간 스트레스 테스트 대기 중...",
        "control_action": "대기 중",
        "confidence": 0,
        "latency_ms": 0,
        "decision_source": "NONE",
        "evaluated_moves": [],
    }

    api_status_text = "준비 완료"
    api_status_color = (100, 255, 120)
    is_network_busy = False
    thread_result = None

    # SPAWN -> FALLING -> LOCK_FLASH -> LINE_FLASH
    state = "SPAWN"

    grid_x = 3
    grid_y = 0
    grid_rot = 0

    target_col = 3
    target_rot = 0
    chosen_move_data = None

    gravity_timer = 0
    das_timer = 0
    gravity_speed = 12       # 12F ~= 0.2초/칸 @ 60FPS
    das_speed = 4            # 4F마다 회전 또는 좌우 이동 1단계

    lock_timer = 0
    locked_blocks = []
    clearing_rows = []
    line_flash_timer = 0

    # 비동기 JEV 의사결정 상태
    piece_serial = 0
    decision_requested_for = -1
    decision_applied = False
    decision_finalized = False
    spawn_time = time.perf_counter()
    active_candidates = []
    active_summary = None
    game_over_logged = False

    def background_api_call(serial, summary, candidates):
        nonlocal is_network_busy, thread_result
        try:
            res = agent.evaluate_best_move(summary, candidates)
        except Exception as exc:
            res = {
                "success": False,
                "error_msg": str(exc),
                "latency_ms": 0,
            }
        thread_result = (serial, res, summary, candidates)
        is_network_busy = False

    def reset_game(mode=None):
        nonlocal game, state, chosen_move_data, clearing_rows, locked_blocks
        nonlocal line_flash_timer, lock_timer, piece_serial, thread_result
        nonlocal decision_applied, decision_finalized, decision_requested_for
        nonlocal active_candidates, active_summary, game_over_logged

        selected_mode = mode or randomizer_mode
        telemetry.count("resets")
        telemetry.event(
            "reset",
            previous_score=game.score,
            previous_lines=game.lines_cleared_total,
            previous_holes=game.count_holes(),
            previous_board=compact_board(game.board),
            next_randomizer=selected_mode,
        )
        game = TetrisGame(
            BOARD_WIDTH,
            BOARD_HEIGHT,
            randomizer_mode=selected_mode,
            seed=TETRIS_RANDOM_SEED,
        )
        # 이미 날아가고 있는 오래된 API 응답을 무효화한다.
        piece_serial += 1
        state = "SPAWN"
        chosen_move_data = None
        clearing_rows = []
        locked_blocks = []
        line_flash_timer = 0
        lock_timer = 0
        thread_result = None
        decision_applied = False
        decision_finalized = False
        decision_requested_for = -1
        active_candidates = []
        active_summary = None
        game_over_logged = False

    while running:
        clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    auto_play = not auto_play
                    telemetry.event(
                        "autoplay_toggled",
                        enabled=auto_play,
                        piece_serial=piece_serial,
                        game_state=state,
                    )
                elif event.key == pygame.K_r:
                    reset_game()
                elif event.key == pygame.K_m:
                    randomizer_mode = "7bag" if randomizer_mode == "iid" else "iid"
                    reset_game(randomizer_mode)
                    telemetry.event(
                        "randomizer_changed",
                        randomizer=randomizer_mode,
                    )
                    api_status_text = f"랜덤 모드 변경: {randomizer_mode.upper()}"
                    api_status_color = (120, 210, 255)
                elif event.key == pygame.K_UP:
                    previous_speed = gravity_speed
                    gravity_speed = max(4, gravity_speed - 2)
                    telemetry.event(
                        "gravity_changed",
                        from_frames=previous_speed,
                        to_frames=gravity_speed,
                    )
                elif event.key == pygame.K_DOWN:
                    previous_speed = gravity_speed
                    gravity_speed = min(30, gravity_speed + 2)
                    telemetry.event(
                        "gravity_changed",
                        from_frames=previous_speed,
                        to_frames=gravity_speed,
                    )

        # ----------------- 완료된 JEV 응답 수신 -----------------
        if thread_result is not None:
            result_serial, res, summary, candidates = thread_result
            thread_result = None

            response_latency = res.get("latency_ms", 0)
            telemetry.count("jev_responses")
            telemetry.add_latency(response_latency)
            telemetry.event(
                "jev_response_received",
                piece_serial=result_serial,
                current_piece_serial=piece_serial,
                game_state=state,
                success=bool(res.get("success")),
                choice_id=res.get("choice_id"),
                confidence=res.get("confidence"),
                latency_ms=response_latency,
                error=res.get("error_msg"),
            )

            # 현재 떨어지고 있는 바로 그 블록의 응답만 허용한다.
            if state == "FALLING" and result_serial == piece_serial:
                elapsed_ms = int((time.perf_counter() - spawn_time) * 1000)

                if res.get("success") and elapsed_ms <= JEV_DECISION_DEADLINE_MS:
                    best_id = res["choice_id"]
                    jev_move = next(
                        (c for c in candidates if c["id"] == best_id),
                        candidates[0],
                    )

                    chosen_move_data = jev_move
                    target_col = jev_move["col"]
                    target_rot = jev_move["rot"]
                    decision_applied = True
                    decision_finalized = True

                    telemetry.count("jev_applied")
                    telemetry.event(
                        "decision_applied",
                        piece_serial=piece_serial,
                        elapsed_since_spawn_ms=elapsed_ms,
                        confidence=res.get("confidence", 0.0),
                        latency_ms=res.get("latency_ms", elapsed_ms),
                        heuristic_fallback=compact_candidate(candidates[0]),
                        jev_choice=compact_candidate(jev_move),
                        jev_overrode_heuristic=(jev_move["id"] != candidates[0]["id"]),
                        grid_at_apply={"x": grid_x, "y": grid_y, "rot": grid_rot},
                    )

                    terrain, goal = terrain_summary(summary)
                    inspector_data = {
                        "active_piece": summary["current_piece"],
                        "next_piece": summary["next_piece"],
                        "heights": summary["column_heights"],
                        "terrain_diagnosis": terrain,
                        "strategy_goal": goal,
                        "chosen_move": jev_move,
                        "decision_narrative": "JEV: " + move_narrative(jev_move),
                        "control_action": "JEV 목표 수신 → 실제 이동 경로로 추적",
                        "confidence": int(res.get("confidence", 0.0) * 100),
                        "latency_ms": res.get("latency_ms", elapsed_ms),
                        "decision_source": "JEV",
                        "evaluated_moves": candidates,
                    }
                    api_status_text = (
                        f"JEV 수신 {res.get('latency_ms', elapsed_ms)}ms "
                        f"(spawn+{elapsed_ms}ms)"
                    )
                    api_status_color = (100, 255, 120)

                elif res.get("success"):
                    decision_finalized = True
                    telemetry.count("jev_late")
                    telemetry.event(
                        "decision_late",
                        piece_serial=piece_serial,
                        elapsed_since_spawn_ms=elapsed_ms,
                        deadline_ms=JEV_DECISION_DEADLINE_MS,
                        latency_ms=res.get("latency_ms", elapsed_ms),
                        ignored_choice_id=res.get("choice_id"),
                        active_target=compact_candidate(chosen_move_data),
                        grid={"x": grid_x, "y": grid_y, "rot": grid_rot},
                    )
                    api_status_text = (
                        f"JEV 늦음: {elapsed_ms}ms > "
                        f"{JEV_DECISION_DEADLINE_MS}ms → 휴리스틱 유지"
                    )
                    api_status_color = (255, 185, 80)
                    inspector_data["decision_source"] = "HEURISTIC/LATE"
                    inspector_data["latency_ms"] = res.get("latency_ms", elapsed_ms)
                    inspector_data["control_action"] = "JEV deadline 초과 → 휴리스틱 계속 사용"

                else:
                    decision_finalized = True
                    telemetry.count("jev_errors")
                    telemetry.event(
                        "decision_error",
                        piece_serial=piece_serial,
                        elapsed_since_spawn_ms=elapsed_ms,
                        latency_ms=res.get("latency_ms", 0),
                        error=res.get("error_msg", "unknown"),
                        active_target=compact_candidate(chosen_move_data),
                    )
                    api_status_text = f"JEV 오류 → 휴리스틱: {res.get('error_msg', 'unknown')}"
                    api_status_color = (255, 100, 100)
                    inspector_data["decision_source"] = "HEURISTIC/ERROR"
                    inspector_data["latency_ms"] = res.get("latency_ms", 0)
                    inspector_data["control_action"] = "JEV 오류 → 휴리스틱 계속 사용"

            else:
                # 이전 블록이 이미 끝난 뒤 도착한 응답은 절대 다음 블록에 적용하지 않는다.
                telemetry.event(
                    "stale_jev_response_discarded",
                    response_piece_serial=result_serial,
                    current_piece_serial=piece_serial,
                    game_state=state,
                    latency_ms=response_latency,
                    choice_id=res.get("choice_id"),
                )
                api_status_text = "이전 블록의 늦은 JEV 응답 폐기"
                api_status_color = (180, 180, 200)

        # ----------------- 실시간 자율 조작 루프 -----------------
        if auto_play and not game.game_over:
            if state == "SPAWN":
                piece_serial += 1

                grid_x = 3
                grid_y = 0
                grid_rot = 0
                gravity_timer = 0
                das_timer = 0

                if not game.can_place(game.current_piece, grid_rot, grid_x, grid_y):
                    game.game_over = True
                else:
                    candidates = game.generate_candidate_moves(game.current_piece)
                    if not candidates:
                        game.game_over = True
                    else:
                        # JEV를 기다리는 동안 사용할 deterministic fallback.
                        # generate_candidate_moves()는 이미 휴리스틱 점수 순으로 정렬되어 있다.
                        active_candidates = candidates
                        chosen_move_data = candidates[0]
                        target_col = chosen_move_data["col"]
                        target_rot = chosen_move_data["rot"]

                        active_summary = {
                            "current_piece": game.current_piece,
                            "next_piece": game.next_piece,
                            "column_heights": game.get_column_heights(),
                            "current_holes": game.count_holes(),
                        }

                        telemetry.count("pieces_spawned")
                        telemetry.event(
                            "piece_spawn",
                            piece_serial=piece_serial,
                            piece=game.current_piece,
                            next_piece=game.next_piece,
                            randomizer=randomizer_mode,
                            board_before=compact_board(game.board),
                            column_heights=active_summary["column_heights"],
                            holes=active_summary["current_holes"],
                            heuristic_fallback=compact_candidate(chosen_move_data),
                            candidates=[compact_candidate(c) for c in candidates],
                        )

                        spawn_time = time.perf_counter()
                        decision_requested_for = -1
                        decision_applied = False
                        decision_finalized = False

                        terrain, goal = terrain_summary(active_summary)
                        inspector_data = {
                            "active_piece": active_summary["current_piece"],
                            "next_piece": active_summary["next_piece"],
                            "heights": active_summary["column_heights"],
                            "terrain_diagnosis": terrain,
                            "strategy_goal": goal,
                            "chosen_move": chosen_move_data,
                            "decision_narrative": "휴리스틱 fallback: " + move_narrative(chosen_move_data),
                            "control_action": "블록 즉시 낙하 시작 + JEV 비동기 판단",
                            "confidence": 0,
                            "latency_ms": 0,
                            "decision_source": "HEURISTIC/PENDING",
                            "evaluated_moves": candidates,
                        }

                        api_status_text = f"'{game.current_piece}' 낙하 중 / JEV 판단 대기"
                        api_status_color = (255, 215, 0)
                        state = "FALLING"

            elif state == "FALLING":
                elapsed_ms = int((time.perf_counter() - spawn_time) * 1000)

                # JEV deadline은 현실 시간 기준이다. 게임 세계는 멈추지 않는다.
                if not decision_finalized and elapsed_ms >= JEV_DECISION_DEADLINE_MS:
                    decision_finalized = True
                    telemetry.count("deadline_fallbacks")
                    telemetry.event(
                        "decision_deadline",
                        piece_serial=piece_serial,
                        elapsed_since_spawn_ms=elapsed_ms,
                        deadline_ms=JEV_DECISION_DEADLINE_MS,
                        fallback=compact_candidate(chosen_move_data),
                        grid={"x": grid_x, "y": grid_y, "rot": grid_rot},
                    )
                    api_status_text = (
                        f"deadline {JEV_DECISION_DEADLINE_MS}ms → 휴리스틱 확정"
                    )
                    api_status_color = (255, 185, 80)
                    inspector_data["decision_source"] = "HEURISTIC/DEADLINE"
                    inspector_data["control_action"] = "JEV 대기 종료 → 휴리스틱 목표 확정"

                # 이전 요청이 끝나지 않았다면 일단 휴리스틱으로 계속 움직인다.
                # 회선이 비는 순간 현재 블록의 deadline 전이면 JEV 요청을 시작한다.
                if (
                    decision_requested_for != piece_serial
                    and not is_network_busy
                    and not decision_finalized
                ):
                    decision_requested_for = piece_serial
                    is_network_busy = True
                    telemetry.count("jev_requests")
                    telemetry.event(
                        "jev_request",
                        piece_serial=piece_serial,
                        elapsed_since_spawn_ms=elapsed_ms,
                        piece=game.current_piece,
                        next_piece=game.next_piece,
                        board_heights=active_summary["column_heights"],
                        holes=active_summary["current_holes"],
                        candidates=[compact_candidate(c) for c in active_candidates],
                    )
                    api_status_text = f"'{game.current_piece}' 낙하 중 / JEV 연산 중..."
                    api_status_color = (255, 215, 0)
                    th = threading.Thread(
                        target=background_api_call,
                        args=(piece_serial, active_summary, active_candidates),
                        daemon=True,
                    )
                    th.start()

                das_timer += 1
                gravity_timer += 1

                # ----- collision-aware 실제 키 입력 -----
                if das_timer >= das_speed:
                    das_timer = 0
                    num_rot = len(SHAPES[game.current_piece])

                    if grid_rot != target_rot:
                        new_rot = (grid_rot + 1) % num_rot
                        rotated = False

                        # 간단한 deterministic wall-kick.
                        for kick_x in (0, -1, 1, -2, 2):
                            test_x = grid_x + kick_x
                            if game.can_place(
                                game.current_piece,
                                new_rot,
                                test_x,
                                grid_y,
                            ):
                                grid_x = test_x
                                grid_rot = new_rot
                                rotated = True
                                r_lbl = ORIENTATION_LABELS[game.current_piece].get(
                                    grid_rot, ""
                                )
                                inspector_data["control_action"] = (
                                    f"회전 입력 [{r_lbl}]"
                                    + (f" + kick {kick_x:+d}" if kick_x else "")
                                )
                                break

                        if not rotated:
                            inspector_data["control_action"] = "회전 시도 차단: 충돌"

                    elif grid_x != target_col:
                        step = 1 if grid_x < target_col else -1
                        test_x = grid_x + step
                        if game.can_place(
                            game.current_piece,
                            grid_rot,
                            test_x,
                            grid_y,
                        ):
                            grid_x = test_x
                            inspector_data["control_action"] = (
                                "우측 이동 키 입력 (▶)"
                                if step > 0
                                else "좌측 이동 키 입력 (◀)"
                            )
                        else:
                            inspector_data["control_action"] = "좌우 이동 차단: 충돌"

                # JEV가 아직 생각 중일 때는 소프트드롭하지 않는다.
                # 자연 중력은 계속 적용되므로 시간 압박은 유지된다.
                is_aligned = (grid_x == target_col and grid_rot == target_rot)
                if is_aligned and decision_finalized:
                    current_fall_interval = max(2, gravity_speed // 3)
                    inspector_data["control_action"] = "목표 정렬 완료 → Soft Drop"
                else:
                    current_fall_interval = gravity_speed

                if gravity_timer >= current_fall_interval:
                    gravity_timer = 0

                    if game.can_place(
                        game.current_piece,
                        grid_rot,
                        grid_x,
                        grid_y + 1,
                    ):
                        grid_y += 1
                    else:
                        # 더는 내려갈 수 없는 실제 위치에서 고정한다.
                        # 목표 좌표로 순간이동/스냅하지 않는다.
                        actual_shape = SHAPES[game.current_piece][grid_rot]
                        target_reached = (
                            grid_x == target_col and grid_rot == target_rot
                        )
                        clearing_rows = game.lock_blocks_to_board(
                            actual_shape,
                            grid_x,
                            grid_y,
                            game.current_piece,
                        )
                        locked_blocks = [
                            (grid_x + cx, grid_y + cy)
                            for cx, cy in actual_shape
                        ]

                        telemetry.count("landings")
                        if not target_reached:
                            telemetry.count("target_misses")
                        telemetry.event(
                            "piece_landed",
                            piece_serial=piece_serial,
                            piece=game.current_piece,
                            elapsed_since_spawn_ms=int(
                                (time.perf_counter() - spawn_time) * 1000
                            ),
                            decision_source=inspector_data["decision_source"],
                            decision_applied=decision_applied,
                            target=compact_candidate(chosen_move_data),
                            actual={
                                "col": grid_x,
                                "row": grid_y,
                                "rot": grid_rot,
                                "rot_label": ORIENTATION_LABELS[
                                    game.current_piece
                                ].get(grid_rot, f"Rot{grid_rot}"),
                            },
                            target_reached=target_reached,
                            rows_ready_to_clear=list(clearing_rows),
                            holes_after_lock=game.count_holes(),
                            heights_after_lock=game.get_column_heights(),
                            board_after_lock=compact_board(game.board),
                        )

                        if grid_x != target_col or grid_rot != target_rot:
                            inspector_data["decision_narrative"] += (
                                " | 실시간 제약으로 목표 미도달"
                            )
                        actual_lbl = ORIENTATION_LABELS[game.current_piece].get(
                            grid_rot, f"Rot{grid_rot}"
                        )
                        inspector_data["control_action"] = (
                            f"실제 착지: col {grid_x}, {actual_lbl}"
                        )

                        lock_timer = 4
                        state = "LOCK_FLASH"

            elif state == "LOCK_FLASH":
                lock_timer -= 1
                if lock_timer <= 0:
                    if clearing_rows:
                        line_flash_timer = 10
                        state = "LINE_FLASH"
                    else:
                        game.advance_piece()
                        state = "SPAWN"

            elif state == "LINE_FLASH":
                line_flash_timer -= 1
                if line_flash_timer <= 0:
                    cleared_now = len(clearing_rows)
                    cleared_rows_snapshot = list(clearing_rows)
                    game.clear_full_lines(clearing_rows)
                    telemetry.count("line_clear_events")
                    telemetry.count("lines_cleared", cleared_now)
                    telemetry.event(
                        "lines_cleared",
                        piece_serial=piece_serial,
                        count=cleared_now,
                        rows=cleared_rows_snapshot,
                        total_lines=game.lines_cleared_total,
                        score=game.score,
                        holes_after_clear=game.count_holes(),
                        heights_after_clear=game.get_column_heights(),
                        board_after_clear=compact_board(game.board),
                    )
                    clearing_rows = []
                    game.advance_piece()
                    state = "SPAWN"

        if game.game_over and not game_over_logged:
            game_over_logged = True
            telemetry.count("game_overs")
            telemetry.event(
                "game_over",
                piece_serial=piece_serial,
                score=game.score,
                total_lines=game.lines_cleared_total,
                holes=game.count_holes(),
                heights=game.get_column_heights(),
                randomizer=randomizer_mode,
                board=compact_board(game.board),
            )

        # ----------------- 렌더링 -----------------
        screen.fill((16, 18, 23))

        board_rect = pygame.Rect(
            0, 0, BOARD_WIDTH * BLOCK_SIZE, BOARD_HEIGHT * BLOCK_SIZE
        )
        pygame.draw.rect(screen, (10, 11, 15), board_rect)

        for r in range(BOARD_HEIGHT):
            for c in range(BOARD_WIDTH):
                rect = pygame.Rect(
                    c * BLOCK_SIZE,
                    r * BLOCK_SIZE,
                    BLOCK_SIZE,
                    BLOCK_SIZE,
                )
                pygame.draw.rect(screen, (24, 26, 34), rect, 1)

        for r in range(BOARD_HEIGHT):
            for c in range(BOARD_WIDTH):
                cell = game.board[r][c]
                if cell:
                    draw_block(
                        screen,
                        c * BLOCK_SIZE,
                        r * BLOCK_SIZE,
                        PIECE_COLORS.get(cell, (200, 200, 200)),
                    )

        # 목표 착지 지점(고스트 피스)
        if state == "FALLING" and chosen_move_data:
            g_color = PIECE_COLORS.get(game.current_piece, (200, 200, 200))
            for cx, cy in chosen_move_data["shape"]:
                gx = (chosen_move_data["col"] + cx) * BLOCK_SIZE
                gy = (chosen_move_data["drop_y"] + cy) * BLOCK_SIZE
                if gy >= 0:
                    draw_block(
                        screen,
                        gx,
                        gy,
                        g_color,
                        border_color=(180, 190, 210),
                        width=1,
                    )

        # 실제 낙하 중인 블록
        if state == "FALLING":
            color = PIECE_COLORS.get(game.current_piece, (200, 200, 200))
            active_shape = SHAPES[game.current_piece][grid_rot]
            for cx, cy in active_shape:
                bx = (grid_x + cx) * BLOCK_SIZE
                by = (grid_y + cy) * BLOCK_SIZE
                if by >= 0:
                    draw_block(screen, bx, by, color)

        if state == "LOCK_FLASH":
            for bx, by in locked_blocks:
                rx, ry = bx * BLOCK_SIZE, by * BLOCK_SIZE
                pygame.draw.rect(
                    screen,
                    (255, 255, 255),
                    (rx - 2, ry - 2, BLOCK_SIZE + 4, BLOCK_SIZE + 4),
                    3,
                )

        if state == "LINE_FLASH":
            for r in clearing_rows:
                flash_col = (
                    (255, 255, 255)
                    if (line_flash_timer // 2) % 2 == 0
                    else (255, 220, 80)
                )
                pygame.draw.rect(
                    screen,
                    flash_col,
                    (0, r * BLOCK_SIZE, BOARD_WIDTH * BLOCK_SIZE, BLOCK_SIZE),
                )

        # ----------------- 우측 AI Inspector 패널 -----------------
        px = BOARD_WIDTH * BLOCK_SIZE + 14

        screen.blit(
            title_font.render(
                "JEV Real-Time Flight Inspector",
                True,
                (0, 240, 200),
            ),
            (px, 10),
        )
        spinner = (
            ["|", "/", "-", "\\"][int(time.time() * 6) % 4]
            if is_network_busy
            else ""
        )
        screen.blit(
            bold_font.render(
                f"API: {api_status_text} {spinner}",
                True,
                api_status_color,
            ),
            (px + 250, 13),
        )

        draw_piece_preview(
            screen, px, 38, game.current_piece, "CURRENT", bold_font
        )
        draw_piece_preview(
            screen, px + 105, 38, game.next_piece, "NEXT", bold_font
        )

        sx = px + 220
        screen.blit(
            font.render(f"점수: {game.score:,} 점", True, (240, 240, 240)),
            (sx, 40),
        )
        screen.blit(
            font.render(
                f"클리어한 줄: {game.lines_cleared_total} 줄",
                True,
                (240, 240, 240),
            ),
            (sx, 58),
        )
        screen.blit(
            font.render(
                f"보드 내 구멍: {game.count_holes()} 개",
                True,
                (255, 180, 100)
                if game.count_holes() > 0
                else (120, 220, 150),
            ),
            (sx, 76),
        )
        screen.blit(
            font.render(
                f"낙하: {gravity_speed}F/칸 | 랜덤: {randomizer_mode.upper()}",
                True,
                (180, 180, 240),
            ),
            (sx, 94),
        )
        screen.blit(
            font.render(
                f"JEV deadline: {JEV_DECISION_DEADLINE_MS}ms",
                True,
                (180, 180, 240),
            ),
            (sx, 110),
        )

        pygame.draw.line(
            screen,
            (40, 44, 56),
            (px, 128),
            (SCREEN_WIDTH - 14, 128),
            1,
        )

        # [1] 지형 진단
        screen.blit(
            bold_font.render(
                "1. 지형 진단 (Dellacherie Feature Analysis)",
                True,
                (255, 215, 0),
            ),
            (px, 136),
        )
        input_box = pygame.Rect(px, 156, SCREEN_WIDTH - px - 14, 65)
        pygame.draw.rect(screen, (22, 25, 33), input_box, border_radius=4)
        pygame.draw.rect(screen, (45, 52, 68), input_box, 1, border_radius=4)

        screen.blit(
            font.render(
                f"• 상태 진단: {inspector_data['terrain_diagnosis']}",
                True,
                (255, 200, 120),
            ),
            (px + 10, 162),
        )
        screen.blit(
            font.render(
                f"• 열별 높이: {inspector_data['heights']}",
                True,
                (180, 190, 210),
            ),
            (px + 10, 180),
        )
        screen.blit(
            font.render(
                f"• 전략 지침: {inspector_data['strategy_goal']}",
                True,
                (100, 240, 180),
            ),
            (px + 10, 198),
        )

        # [2] JEV 판단 결과
        screen.blit(
            bold_font.render(
                "2. 실시간 판단 및 격자 조작",
                True,
                (255, 215, 0),
            ),
            (px, 231),
        )
        dec_box = pygame.Rect(px, 251, SCREEN_WIDTH - px - 14, 67)
        pygame.draw.rect(screen, (22, 25, 33), dec_box, border_radius=4)
        pygame.draw.rect(screen, (45, 52, 68), dec_box, 1, border_radius=4)

        m = inspector_data["chosen_move"]
        if m:
            c_lbl = (
                f"▶ 목표: {m['id']} ({m['col']}번 열) | "
                f"Source: {inspector_data['decision_source']}"
            )
            screen.blit(
                bold_font.render(c_lbl, True, (255, 235, 100)),
                (px + 10, 258),
            )
            screen.blit(
                font.render(
                    f"• {inspector_data['decision_narrative']}",
                    True,
                    (255, 215, 130),
                ),
                (px + 10, 278),
            )
            d_line3 = (
                f"• 확신도: {inspector_data['confidence']}% | "
                f"통신: {inspector_data['latency_ms']}ms | "
                f"{inspector_data['control_action']}"
            )
            screen.blit(
                font.render(d_line3, True, (160, 230, 255)),
                (px + 10, 298),
            )

        # [3] 후보군 비교표
        screen.blit(
            bold_font.render(
                "3. Evaluated Candidates",
                True,
                (190, 205, 225),
            ),
            (px, 328),
        )
        tbl_y = 350
        for idx, cand in enumerate(inspector_data["evaluated_moves"][:5]):
            is_winner = m and (cand["id"] == m["id"])
            tag = "★ [목표]" if is_winner else f"   [후보{idx+1}]"
            tag_col = (100, 255, 120) if is_winner else (160, 165, 180)

            fit_str = f"밀착:{cand['contact_edges']}면"
            hang_str = (
                "완전결합"
                if cand["overhangs"] == 0
                else f"걸침({cand['overhangs']}칸)"
            )
            txt = (
                f"{tag} {cand['id']:<10} | 착지:{cand['landing_height']:>2}칸 | "
                f"{fit_str} | {hang_str} | 줄삭제:{cand['lines_cleared']}줄"
            )
            screen.blit(
                font.render(txt, True, tag_col),
                (px + 5, tbl_y + idx * 22),
            )

        # 하단 조작 안내
        guide_box = pygame.Rect(
            px,
            SCREEN_HEIGHT - 55,
            SCREEN_WIDTH - px - 14,
            45,
        )
        pygame.draw.rect(screen, (20, 22, 28), guide_box, border_radius=4)
        screen.blit(
            font.render(
                "[Space] 일시정지 | [R] 새 게임 | [M] IID/7-BAG 전환 | [↑/↓] 낙하 속도",
                True,
                (130, 135, 150),
            ),
            (px + 12, SCREEN_HEIGHT - 43),
        )

        if game.game_over:
            overlay = pygame.Surface(
                (BOARD_WIDTH * BLOCK_SIZE, BOARD_HEIGHT * BLOCK_SIZE),
                pygame.SRCALPHA,
            )
            overlay.fill((0, 0, 0, 190))
            screen.blit(overlay, (0, 0))
            screen.blit(
                title_font.render("GAME OVER", True, (255, 60, 60)),
                (
                    BOARD_WIDTH * BLOCK_SIZE // 2 - 60,
                    SCREEN_HEIGHT // 2 - 20,
                ),
            )

        pygame.display.flip()

    telemetry.close(
        final_state={
            "score": game.score,
            "total_lines": game.lines_cleared_total,
            "holes": game.count_holes(),
            "heights": game.get_column_heights(),
            "randomizer": randomizer_mode,
            "board": compact_board(game.board),
        }
    )
    print(f"[telemetry] saved: {telemetry.log_path}")
    print(f"[telemetry] summary: {telemetry.summary_path}")

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
