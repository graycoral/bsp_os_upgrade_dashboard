# Claude 2.1.317 환경 점검 수정

RQ-37 / D-42 / T-97 / REG-0094. 기준 커밋 `e7b406de9fbebad2d99f7feba501485c2cdf482c`에 CLI 검사·시험 변경을 적용했다.

## 재현과 수정

사용자가 회사 Linux의 Claude 버전을 2.1.317로 확인했다. 같은 버전의 공식 macOS arm64 패키지를 npm 배포 integrity로 확인한 뒤 격리 경로에서 실행했다. `--help`에는 필수 옵션 중 `--max-turns`만 빠져 있었다. 수정 전 검사에서 사용자가 보고한 UNSUPPORTED 메시지를 재현했다.

`claude --help --max-turns`는 exit 1과 `error: option '--max-turns <turns>' argument missing`을 반환했다. 존재하지 않는 옵션과 `--help`를 함께 전달하면 exit 0으로 도움말이 나오므로 성공 종료만으로 옵션 지원을 인정할 수 없다. 수정 코드는 옵션 이름이 일치하는 값 누락 오류를 확인한다. 다른 필수 옵션은 전체 옵션 토큰으로 비교하고, 미확인 옵션과 감지한 버전을 오류에 표시한다.

수정 후 동일 공식 CLI는 옵션 검사를 통과하고 별도 빈 인증 설정에 대해 LOGIN_REQUIRED를 반환했다. 로그인된 모의 CLI는 환경설정 API와 `resolve_tools`에서 CLI_READY였다. 실제 모델 추론·BSP 작업은 실행하지 않았다. 회사 Linux의 도움말·환경 점검 재실행은 NOT_RUN이다.

## 변경과 적용

- Agent Monitor 담당자는 `backend/adapters/native.py`와 `tests/test_native.py`를 적용한다. API·Worker를 재시작하고 환경설정에서 환경 점검을 실행한다.
- 플러그인 담당자는 복사형 Agent Monitor에 같은 서버 코드를 포함하고 점검 결과의 버전·옵션 안내를 전달한다.
- 데이터 변경은 없다. 코드 SHA-256은 `8543e93d16b39e50d72b261a41df3e55147846eaa7a0093f4f0a5d9a8988dd16`, 시험 SHA-256은 `3c5fc201758818cf31a0b39af02fa5cada9197db8b0a87405ef5d54bd6d405f7`다. 수정 코드·시험 게시 커밋은 `99abc6106794b4a332e88f9a0b026231bbc9832d`다.

## 검증

원본 로그는 `.local-reports/20261116-claude-probe/`에 로컬 전용으로 보관한다.

| 실행 | 결과 | 근거 |
|---|---|---|
| 공식 CLI 2.1.317 버전·도움말·누락 인자 및 미지원 옵션 비교 | PASS | `version.log`, `help.log`, `missing-value.log`, `unknown.log` |
| 수정 전·후 실제 CLI 점검 비교 | PASS | `real-cli-comparison.log` |
| `python -m pytest tests/test_native.py -k t97 -q` | 15 PASS | `probe-tests-final.log`, API·지원/미지원·시간 초과·옵션 접두사·인증 검사 |
| 최초 native 전체 | 53 PASS / 1 FAIL | `native-tests.log`, Linux 프로세스 receipt 검증 실패 |
| 최초 API·engine·orchestration 관련 회귀 | 383 PASS / 8 FAIL / 1 SKIP | `related-tests.log` |
| 수정 전 main 격리 checkout에서 실패군 재현 | 31 PASS / 동일 9 FAIL / 1 SKIP | `baseline-tests.log`, Linux `/proc`·프로세스 식별을 macOS에서 확인하지 못함 |

최종 격리 checkout에서 `python -m pytest tests/test_native.py tests/test_api.py tests/test_engine.py tests/test_orchestration_worker.py tests/test_orchestration_runtime.py tests/test_orchestration_contracts.py -q`를 실행했다. 436 PASS / 동일 9 FAIL / 1 SKIP이며 `final-isolated-tests.log`에 보존한다. 9개 실패는 수정 전 main에서 재현한 시험과 일치한다. `python docs/testing/validate_docs.py`는 1677개 링크 검사 PASS였으며 `git diff --check`도 PASS다. 별도 작업 중인 GUI Test 코드 7개는 검증용 checkout에 포함하지 않았다. 실제 Linux·모델·보드 인수는 NOT_RUN이다.

공식 문서의 도움말 생략 설명과 `--max-turns` 계약을 확인했다. [Claude CLI reference](https://code.claude.com/docs/en/cli-reference)
