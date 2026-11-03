# Windows 웹 빌드 실행 정책 오류 수정

- 범위: RQ-44/T-126, REG-0036. 기준 main `e86c5cbbf53cd360a1b90eafcc1c37b050e3659e`.
- 사용자 증거: 로컬 저장소에서 `scripts/build.cmd` 실행 시 `build.ps1`을 로드하지 못하고 `PSSecurityException/UnauthorizedAccess` 출력. 빌드 본문 진입 전 PowerShell 실행 정책 차단이다. 이전 공유 드라이브 오류 REG-0030의 원인을 확정하는 증거는 아니다.
- 수정: `build.cmd`의 자식 PowerShell 호출에만 `-ExecutionPolicy Bypass`를 추가하고, `setlocal` 범위에서 상속 `PSModulePath`를 비워 Windows PowerShell 기본 모듈 탐색을 사용한다. 절대 스크립트 경로·인자 전달·실패 pause·원래 종료 코드 유지. 사용자/컴퓨터 정책과 부모 환경을 저장하거나 변경하지 않으며 관리자 권한은 필요하지 않다. 그룹 정책은 여전히 우선한다.
- 변경 파일: `scripts/build.cmd`, 사용 안내, 요구사항/시험/진행/회귀 기록, `tests/test_build_entrypoint.py`. DB·설정 데이터 변경 없음, 실제 장비/서버 실행 없음.
- 방지 시험: Restricted 환경을 상속한 실제 PowerShell에서 기존 직접 호출 실패를 재현하고 CMD 경유 성공을 확인한다. LF/CRLF, 공백 포함 경로, 다른 cwd, 인자 전달, 종료 코드0/7, 호출 전후 실행 정책 목록 일치와 자식 모듈 경로에서 상속된 외부 디렉터리 제거를 확인한다.
- 독립 GPT-6-astra 코드·시험·안내 리뷰 APPROVED. reviewer도 신규 시험4 PASS를 확인했다. 최초 기본 pytest 임시 디렉터리 권한 때문에 fixture4 ERROR가 발생했고 고유 basetemp로 재실행했다. 최종 실행 기록 문서 전체에 대한 리뷰를 의미하지 않는다.
- 독립 GPT-6-sol 신규4 PASS, 기존 setup 회귀49 PASS/4 플랫폼 SKIP, 실제 CMD 양쪽 UI 빌드 PASS. [정확한 명령·환경·결과](20261103-build-execution-policy-sol.md). 주 작업자가 시험 코드와 보고 결과를 검토했다. 영구 실행 정책 전후 동일을 확인했다.
- 로컬 시험의 고정 코드·시험 커밋: `a54af9ee60b11452a9639d73611fcc5e6c98bbb0`. GitHub Actions Linux/Windows 결과는 PR에서 별도로 확인한다.
- 회사 그룹 정책/SMB/장비 인수는 NOT_RUN, 운영 baseline NONE 유지.
- 회귀 유지: Windows CI의 명시적 pytest 파일 목록에도 신규 시험을 추가했다. Linux에서는 Windows 전용 4건을 SKIP하므로 Windows job에서 실행해야 한다.

## PR #12 첫 CI 실패 기록

- [GitHub Actions run #48](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/41655112965), head `b21ac7a13ebe5c44bba7f8d98c2b4bcf68ff1c9d`: Windows package pytest **4 FAIL / 231 PASS / 3 SKIP / 1 warning**. 신규 시험의 네 parameter 조합 모두 wrapper 실행 전 정책 조회에서 중단됐다.
- 로그에 남은 예외: `subprocess.CalledProcessError: Command '['powershell.exe', '-NoLogo', '-NoProfile', '-Command', 'Get-ExecutionPolicy -List | ConvertTo-Json -Compress']' returned non-zero exit status 1.` 시험이 `stderr`를 캡처한 채 예외를 발생시켜 실제 PowerShell 오류 문구는 CI 로그에 표시되지 않았다. 원인은 이 기록만으로 확정하지 않는다.
- 이 실패를 보존하고 정책 조회의 stdout/stderr를 실패 메시지에 표시하는 진단 시험을 추가해 재실행한다. CI 성공 전 병합하지 않는다.
- [진단 run #49](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/41655724480), head `c1ad0464c21bdeec14ece099204a1239f59a933a`: Windows package는 다시 **4 FAIL / 231 PASS / 3 SKIP / 1 warning**. stderr에 `Get-ExecutionPolicy`가 `Microsoft.PowerShell.Security` 모듈에서 발견됐지만 자동 로드하지 못했다는 오류와 `FullyQualifiedErrorId : CouldNotAutoloadMatchingModule`이 표시됐다. Restricted 조회 자식에서 발생했으며 wrapper 실행 이전이다. 정책 조회 자식에만 `-ExecutionPolicy Bypass`를 적용하고, 직접 `-File`의 Restricted 실패 검증과 `build.cmd`의 Bypass·인자·종료 코드 검증은 유지한다. 수정 시험의 CI 결과는 아직 미확인이다.
- [재실행 run #50](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/41656399603), head `ecfc3efbd1ca0d79966f7ed46086678bf717d9cd`: 정책 조회 자식에 `-ExecutionPolicy Bypass`를 지정해도 Windows package **4 FAIL / 231 PASS / 3 SKIP / 1 warning**. `Get-ExecutionPolicy`의 `Microsoft.PowerShell.Security` 자동 로드 실패가 동일하게 나타나 직접 `-File` 및 wrapper 실행 단계에 도달하지 못했다. 정확한 모듈 로드 오류는 아직 확인되지 않았다. CI 성공 전 병합하지 않는다.
- [모듈 진단 run #51](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/41656974795), head `19ba8323c4238cdc0cf61256392d20828a75d36f`: Windows의 임시 진단 단계가 `Import-Module Microsoft.PowerShell.Security -ErrorAction Stop`에서 exit 1을 반환했다. stderr는 `Error in TypeData "System.Security.AccessControl.ObjectSecurity": The member AccessToString is already present`(Sddl/Access/Group/Owner/Path도 중복), `FullyQualifiedErrorId : FormatXmlUpdateException,Microsoft.PowerShell.Commands.ImportModuleCommand`이다. `PSModulePath`에서 PowerShell 7 Modules가 WindowsPowerShell v1.0 Modules보다 앞선다. 정확히 선택된 모듈 파일 경로는 로그에 없다. 모듈 경로 호환성 문제를 가리키며, 앞선 Restricted 자체 원인 추정은 철회한다. 임시 진단 단계는 최종 CI 설정에서 제거한다.
- 후속 로컬 시험은 새 4 PASS, 기존 setup 49 PASS/4 SKIP, 실제 CMD 두 UI 빌드 PASS이며 [독립 재시험 및 변이 확인](20261103-build-execution-policy-sol.md)을 따른다. 임시 외부 모듈 fixture는 이 호스트에서 실행 실패를 일으키지는 않았지만, 자식 모듈 경로에 외부 디렉터리가 남으면 강화된 시험이 실패한다. CI에서 관찰한 모듈 로드 충돌 해소는 새 Windows CI로 확인한다.
