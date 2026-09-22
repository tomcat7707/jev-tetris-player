import os
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드
load_dotenv()

TYPESAFE_API_KEY = os.getenv("TYPESAFE_API_KEY", "")
TYPESAFE_API_URL = "https://api.typesafe.ai/v1/systemone"

# 테트리스 규격 및 화면 설정
BLOCK_SIZE = 30
BOARD_WIDTH = 10
BOARD_HEIGHT = 20
SCREEN_WIDTH = BOARD_WIDTH * BLOCK_SIZE + 480
SCREEN_HEIGHT = BOARD_HEIGHT * BLOCK_SIZE
FPS = 60

# 실시간 스트레스 테스트 설정
# - iid: 매 블록을 독립적으로 1/7 확률로 추첨 (패턴/보정 없는 스트레스 테스트)
# - 7bag: 현대 테트리스에서 흔히 쓰는 7-bag 방식
PIECE_RANDOMIZER = os.getenv("PIECE_RANDOMIZER", "iid").strip().lower()
if PIECE_RANDOMIZER not in {"iid", "7bag"}:
    PIECE_RANDOMIZER = "iid"

_seed_raw = os.getenv("TETRIS_RANDOM_SEED", "").strip()
TETRIS_RANDOM_SEED = int(_seed_raw) if _seed_raw else None

# 블록은 JEV 응답을 기다리지 않고 즉시 낙하한다.
# 이 시간 안에 JEV가 도착하지 않으면 휴리스틱 1위 후보로 계속 진행한다.
JEV_DECISION_DEADLINE_MS = int(os.getenv("JEV_DECISION_DEADLINE_MS", "1600"))


# JEV 호출 정책
# - always: 모든 블록마다 JEV 호출
# - ambiguous: deterministic 후보가 애매하거나 위험상태일 때만 JEV 호출
# - off: JEV를 전혀 호출하지 않고 deterministic fallback만 사용
JEV_POLICY = os.getenv("JEV_POLICY", "always").strip().lower()
if JEV_POLICY not in {"always", "ambiguous", "off"}:
    JEV_POLICY = "always"

# ambiguous 모드에서 top-2 two-ply score 차이가 이 값 이하이면 JEV 호출
JEV_AMBIGUITY_GAP = float(os.getenv("JEV_AMBIGUITY_GAP", "10.0"))

# 이 높이 이상에서는 score gap과 무관하게 JEV를 호출해 위험상태를 재검토
JEV_HIGH_STACK_TRIGGER = int(os.getenv("JEV_HIGH_STACK_TRIGGER", "8"))


# v4 selective gate risk triggers
JEV_LOW_FLEX_TRIGGER = int(os.getenv("JEV_LOW_FLEX_TRIGGER", "2"))
JEV_DEEP_WELL_TRIGGER = int(os.getenv("JEV_DEEP_WELL_TRIGGER", "4"))
