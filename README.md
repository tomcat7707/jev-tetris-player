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
