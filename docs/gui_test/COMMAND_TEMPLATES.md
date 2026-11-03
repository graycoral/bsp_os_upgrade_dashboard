# 공통 TC 실행 명령 템플릿

Single/Dual 명령을 한 번 저장한 뒤 선택한 TC 경로·COM·보드 노드명을 치환합니다. 기본 모드는 Mock이며 명령 저장과 미리보기는 실행하지 않습니다. 명시적으로 설정한 Windows 실행기는 고정 Windows Python에서 공유 TC snapshot을 실행합니다. [실행기 안내](WINDOWS_RUNNER.md)를 따릅니다.

## 사용자 확인 명령과 입력

2026-11-03 사용자 확인:

```text
python3 tc1.py -p COM7
python3 tc_2.py -n n295_sadk -n2 n296_sadk
```

톱니바퀴 → TC 실행 명령 설정에서 각 인자를 한 줄씩 입력하고 프로파일을 저장합니다. 신규 Windows 프로파일의 기본값은 다음과 같습니다. 기존 저장 프로파일은 자동으로 덮어쓰지 않습니다.

Single:

```text
python3
{tc_path}
-p
{com_a}
```

Dual:

```text
python3
{tc_path}
-n
{node_a}
-n2
{node_b}
```

현재 TC 유형은 기존 폴더 규칙을 유지합니다. 상위 폴더 이름에 dual(대소문자 무관)이 포함되면 Dual이며 파일명 tc_2.py 자체로는 구분하지 않습니다. 예를 들어 `dual/tc_2.py`가 Dual입니다. 실행 전 목록의 유형을 확인하세요. metadata.kind로 폴더 분류를 덮어쓰지 않으며 불일치는 차단합니다.

연결 설정의 Board A/B를 선택합니다. Single은 선택 COM 이름 전체를 전달하고 Dual은 각 보드에 등록한 node를 전달합니다. 노드명은 COM 번호나 대시보드 보드 표시 이름에서 유추하지 않습니다. Windows 실행기의 boards 설정에 각각 n295_sadk/n296_sadk를 등록해야 하며 실제 PC/보드/COM 연결과 맞춰야 합니다. 예제 두 번째 COM8은 설명용입니다.

미리보기로 argv를 확인하고 실행 탭에서 Preflight를 수행합니다. Windows의 python/python3는 둘 다 실행기 설정의 Python 절대 경로로 치환하며 PATH에서 별도 명령을 찾지 않습니다. Windows 실행기의 두 번째 인자는 반드시 {tc_path}이며 검증한 snapshot의 절대 경로로 치환합니다. 공백이 있는 경로도 한 인자이고 따옴표로 감싸지 않습니다.

## 치환 변수와 제약

| 변수 | 의미 | 예 |
|---|---|---|
| `{tc_name}` | 확장자를 제외한 TC 이름; 일반/Mock 프로파일용 | `tc1` |
| `{tc_file}` | 확장자를 포함한 파일명; 일반/Mock 프로파일용 | `tc1.py` |
| `{tc_path}` | 카탈로그 TC 경로; Windows에서 snapshot 절대 경로 | `dual/tc_2.py` |
| `{com_a}` | Board A COM 포트 | `COM7` |
| `{com_b}` | 기존 Dual COM 계약의 Board B 포트 | `COM8` |
| `{node_a}` | Dual Board A의 등록 노드명 | `n295_sadk` |
| `{node_b}` | Dual Board B의 등록 노드명 | `n296_sadk` |

TC 변수는 하나를 정확히 한 번 사용합니다. Single은 com_a를 한 번 사용합니다. Dual은 node_a/node_b 쌍 또는 기존 com_a/com_b 쌍을 각각 한 번 사용하며 서로 섞지 않습니다. 누락·중복·미등록 변수와 `--node={node_a}`처럼 합친 변수는 거부합니다. 노드명이 없는 보드로 노드명 명령을 시작할 수 없습니다. Windows 서버는 요청 보드의 host/board_id/COM/node 전체가 등록값과 같은지 다시 검사합니다.

파이프·리다이렉션·환경변수 확장·셸 명령 치환을 하지 않습니다. Windows 실행기에서 임의 실행 파일, python -c 같은 다른 진입점은 허용하지 않습니다. 실제 TC 의존 패키지는 해당 Windows Python 환경에 미리 설치해야 합니다.

## 보존과 검증

- 프로파일은 모드별 로컬 SQLite에 저장되며 자동 공유되지 않습니다. 다른 화면에서 수정한 이전 버전은 새 실행에 사용할 수 없습니다.
- Run에 연결/명령 snapshot, Attempt에 치환 argv와 실제 실행 argv를 보존합니다. 노드명을 바꾸어도 과거 Run을 재작성하지 않습니다.
- 기존 node 없는 보드 직렬화와 COM 프로파일, Mock 기본 명령은 보존합니다. 기존 DB schema_version=1을 유지합니다.
- node 등록값을 바꾸면 실행기를 안전하게 재시작하고 대시보드 보드 목록과 저장 연결 프로파일을 갱신합니다. 과거 snapshot이 현재 매핑과 다르면 재개를 차단합니다.
- 비밀번호·토큰을 명령에 넣지 않습니다. 명령은 결과 증빙에 포함됩니다.

실제 회사 TC·노드 접속·물리 COM 인수는 별도이며 자동 시험은 가짜 TC/포트 목록을 사용합니다. [Windows 빌드 가이드](WINDOWS_BUILD.md), [모듈 README](../../gui_test/README.md).
