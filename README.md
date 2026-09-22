# JEV Tetris Player

JEV의 판단 지연을 실제 게임 시간 안에서 검증하기 위한 테트리스 실험입니다.

## 이번 실험의 핵심

기존 버전은 JEV 응답이 올 때까지 블록 낙하가 사실상 멈췄습니다.
현재 실시간 스트레스 테스트 버전은 다음처럼 동작합니다.

1. 블록이 스폰되자마자 자연 중력이 시작됩니다.
2. 동시에 기존 휴리스틱 1위 후보를 fallback 목표로 잡습니다.
3. JEV는 백그라운드에서 비동기로 판단합니다.
4. deadline 안에 JEV가 도착하면 목표를 JEV 선택으로 갱신합니다.
5. 늦거나 실패하면 휴리스틱 fallback을 그대로 사용합니다.
6. 좌우 이동과 회전은 실제 보드 충돌 검사를 통과해야 합니다.
7. 착지 시 목표 좌표로 순간이동하지 않고 실제 현재 위치에 고정됩니다.

즉 게임 세계는 JEV가 생각하는 동안 멈추지 않습니다.

## v2: Safe Lookahead 실험

두 번째 실시간 IID 로그에서 확인된 실패 원인을 반영한 실험 버전입니다.

핵심 변경:

- **Safety envelope**: 현재보다 holes를 늘리지 않는 후보가 하나라도 있으면, hole을 새로 만드는 후보는 JEV에게 보내지 않습니다.
- **정식 Dellacherie 6-feature 복원**: landing height, eroded piece cells, row transitions, column transitions, holes, cumulative wells를 사용합니다.
- **2-ply lookahead**: 현재 블록만 보지 않고 이미 알고 있는 NEXT 블록까지 한 수 더 시뮬레이션해 `next_best_holes`, `next_best_max_height`, `two_ply_score`를 JEV에 전달합니다.
- **Reachability planner**: JEV가 좋은 착지점을 골라도 현재 떨어지는 위치에서 실제로 갈 수 없다면 도달 가능한 안전 후보로 재계획합니다.
- **Control-aware deadline**: 상단이 높아져 이동 시간이 부족해지면 JEV의 절대 timeout보다 먼저 deterministic fallback을 확정합니다.
- **판단 중 자연 중력만 유지**: JEV 응답 전에는 fallback 방향으로 먼저 움직이지 않아, 늦게 도착한 JEV 판단 때문에 반대 방향으로 되돌아가는 손실을 줄였습니다.

이 버전의 질문은 다음과 같습니다.

> 좋은 판단 모델에게 더 많은 자유를 주는 것이 좋은가,  
> 아니면 deterministic safety envelope 안에서만 판단하게 하는 것이  
> 장기 생존성과 실제 제어 가능성을 높이는가?

## v3: Selective JEV 실험

v2 장기 run에서 시스템이 안정 상태에 들어가면서, JEV를 모든 블록에 호출할 필요가 있는지 검증하기 위한 버전입니다.

환경변수:

    JEV_POLICY=always
    JEV_AMBIGUITY_GAP=10.0
    JEV_HIGH_STACK_TRIGGER=8

정책:

- `always`: 모든 블록마다 JEV 호출
- `ambiguous`: deterministic 후보가 애매하거나 복구/고위험 상태일 때만 JEV 호출
- `off`: JEV를 호출하지 않고 safety envelope + 2-ply deterministic fallback만 사용

`ambiguous` 모드에서는 다음 상황에서 JEV를 호출합니다.

- 현재 holes > 0
- 최고 높이가 `JEV_HIGH_STACK_TRIGGER` 이상
- top-2 후보의 `two_ply_score` 차이가 `JEV_AMBIGUITY_GAP` 이하

명확한 deterministic winner가 있으면 API 호출을 생략하고 즉시 실행합니다.

공정한 A/B 비교를 위해 `TETRIS_RANDOM_SEED`를 고정한 뒤,
같은 seed에서 `always / ambiguous / off` 세 모드를 비교하는 것을 권장합니다.

## 블록 randomizer

기본값은 **IID random**입니다.

- `iid`: 매 블록마다 I/O/T/S/Z/J/L 중 하나를 독립적으로 1/7 확률로 추첨
- `7bag`: 현대 테트리스에서 흔히 쓰는 7-bag 방식

게임 중 **M 키**로 IID / 7-BAG을 전환하면 새 게임이 시작됩니다.

환경변수:

    PIECE_RANDOMIZER=iid
    TETRIS_RANDOM_SEED=
    JEV_DECISION_DEADLINE_MS=1600

`TETRIS_RANDOM_SEED`에 정수를 넣으면 동일한 난수열을 재현할 수 있습니다.

## 조작

- `Space`: 자동 플레이 일시정지/재개
- `R`: 새 게임
- `M`: IID / 7-BAG 전환 후 새 게임
- `↑ / ↓`: 낙하 속도 조절

## JEV latency

JEV 호출은 `requests.Session()`을 재사용하여 HTTP keep-alive를 활용합니다.
Inspector의 통신 시간은 API 요청부터 응답까지의 end-to-end latency입니다.

기본 deadline은 1600ms이며 `JEV_DECISION_DEADLINE_MS` 환경변수로 변경할 수 있습니다.
deadline을 초과한 응답은 현재 블록의 행동을 변경하지 않습니다.

## 실험 로그

실행할 때마다 `logs/` 폴더에 두 파일이 자동 생성됩니다.

- `jev_tetris_YYYYMMDD_HHMMSS_PID.jsonl`: 블록 단위 상세 이벤트 로그
- `jev_tetris_YYYYMMDD_HHMMSS_PID_summary.json`: 세션 요약 통계

JSONL에는 다음 사건이 기록됩니다.

- 블록 spawn 당시 보드/높이/구멍/다음 블록
- 상위 후보 5개의 Dellacherie 계열 feature와 휴리스틱 점수
- JEV 요청/응답 시간, choice, confidence
- JEV가 휴리스틱 1위를 바꿨는지
- deadline 초과/오류/이전 블록 응답 폐기
- 실제 착지 위치와 목표 도달 여부
- line clear 이후 보드 상태
- game over 직전 최종 보드

API Key나 Authorization header는 기록하지 않습니다.

실험 후 피드백할 때 가장 최근의 `.jsonl`과 `_summary.json` 두 파일을 함께 주면,
화면 관찰만으로는 알 수 없는 실패 원인까지 piece 단위로 재구성할 수 있습니다.

## 테스트

    python -m unittest -v

현재 엔진 테스트는 다음을 확인합니다.

- 7-bag 한 묶음에 7종 블록이 한 번씩 포함되는지
- IID 난수가 고정 seed에서 재현되는지
- 실제 위치 충돌 검사가 작동하는지
- 휴리스틱 fallback 후보가 정상 생성되는지

## 실험 목적

이 프로젝트의 핵심 질문은 단순히 "JEV가 테트리스를 잘하는가?"가 아닙니다.

> 환경은 계속 움직이고 있는데, 느린 외부 판단 모델이 제한 시간 안에 들어와
> 빠른 deterministic controller와 협력해 장기간 시스템을 안정적으로 유지할 수 있는가?

이 구조는 향후 카메라/YOLO/센서 기반 Physical AI의 실시간 판단 실험으로 확장할 수 있습니다.
