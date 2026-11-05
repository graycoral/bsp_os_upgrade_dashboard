# 작업 진행 기록

## 2026-11-05~06 · GUI Test 구조 분리 · 로컬 검증 완료

RQ-54/D-57. 사용자 승인에 따라 단독 앱 `apps/gui-test/`, Python `backend/gui_test/`, 공유 React `packages/gui-test-ui/src/`로 나눈다. 소스 `backend.gui_test.*`와 설치 `gui_test.*`/기존 CLI를 구분하고 세 경로 ZIP·wheel staging으로 Dashboard/Git 없는 빌드를 유지한다. 기존 RQ-52 Git 정보/RQ-53 모듈 TC 선택/D-54 화면 정리와 미커밋 변경을 보존한다. API·DB·runtime·설정·운영 정책 변경과 실제 외부 실행은 없다.

요구 분석·구조 설계 Astra XHigh, 상세 설계 Astra High, 구현 Sol High, 별도 시험 작성 Sol Medium을 거쳤다. 사용자 지정 새 독립 Astra High 최종 리뷰는 APPROVED이고 109개 source manifest를 기록했다. 별도 새 Luna Low가 현재 트리에서 Python **384 PASS/6 SKIP**, 두 production 빌드 PASS, 합성 브라우저 **66 PASS**, 단독 GUI **18 PASS**, 통합/단독 live-view **각 1 PASS**를 확인했다. RQ-20/39/52/53 병행 변경도 이 현재 회귀에 포함한다. REG-0048 독립 builder의 Git 의존 시험 선택과 REG-0049 README 인코딩 손상을 수정했으며 최초 실패·재시험은 보존했다.

T-164~168은 로컬 PASS다. Node22.12.0/CPython3.12.10과 실제 Git 없는 자식 PATH에서 세 경로 반입본의 기본 Windows builder가 **134 PASS/4 deselected**, full wheelhouse31개·설치된 Mock demo5개 통과로 완료됐다. 격리 wheel 설치·`gui-test.exe` start/status/restart/stop 및 source health/JS/CSS를 확인했다. 새 Runner ZIP의 실제 pytest는 **7 PASS**이며 파일 직접 호출이0개 시험을 수집한 앞선 보고는 통과 근거에서 제외했다. 최종 독립 ZIP은16,659,175 bytes·SHA256 `438dde4f85dd970303a6f56a9417b78278c2dc238a68130c79b77273a3fa7872`다. REG-0048/49의 builder·패키지 README 검증도 완료했다.

독립 문서 재검사는839링크/54요구사항/168시험·오류0 PASS이며 최초 링크/추적 표 오류도 보존했다. 짧은 임시 경로와 해당 프로세스 실행 정책으로 재시도한 최초 5 FAIL/12 ERROR·패키지 MAX_PATH 실패도 기록한다. 상세 명령·manifest·산출물·남은 제약은 [이번 실행 기록](../testing/runs/20261105-gui-test-layout.md)을 따른다. 사용 중인 서비스 배포·재시작과 실제 보드·모델·Jira·SSH는 수행하지 않았다. 운영 baseline NONE 유지; branch push·PR/CI·main 병합은 조정자의 후속 작업이며 실제 결과를 별도 기록한다.

## 2026-11-04 · 탭 소개 정리와 Test 현황 결과 조작

2026-11-06 후속: 기존 기능 변경과 REG-0043~47 수정을 새 구조의 현재 트리에 보존했다. 별도 새 Luna가 focused Python384/6 SKIP·두 빌드·합성66·단독18·통합/단독 live 각1 PASS를 확인했다. 과거 검증 사본의 차단·최초 FAIL은 [기능 기록](../testing/runs/20261104-test-results-cleanup.md)에 유지하며 [현재 트리 실행 기록](../testing/runs/20261105-gui-test-layout.md)으로 이어진다. 새 구조의 독립 패키지 인수는 별도다.

사용자 구현 승인에 따라 RQ-20/39/D-54를 반영한다. 주 탭 소개 문구를 제거하고, 전체 트리 ＋/−를 이름 헤더의 체크박스 옆으로 옮긴다. 실행 조작은 진행률·집계 아래에 두며 작은 세션 정보와 결과·로그를 상시 표시한다. 후속 요청은 중복 결과 버튼/제목 제거·진행률과 상태 개수 통합·모드 선택의 환경 설정 이동·미준비 안내 접기·TC Git 정보(RQ-52/D-55)·모듈별 TC 자동 목록(RQ-53/D-56)이다. Git 카탈로그와 선택 문맥 검증을 확장하며 DB 스키마·기존 운영 게이트는 유지한다. 요구 분석/구조 설계 Astra XHigh, 상세 설계 Astra High, 구현 Sol High, 시험 작성 Sol Medium, 분리된 새 Sol High 리뷰와 Luna Low 실행 보고로 분담한다. 최종 구현·시험·검토 상태는 [화면 정리 기록](../testing/runs/20261104-test-results-cleanup.md)을 따른다. 기존 포터블 Runner 작업과 이력은 보존한다.

## 2026-11-04 · Windows Runner 포터블 EXE · 로컬 검증 완료

RQ-51/D-53. Runner의 Python·의존성을 포함한 `dist/windows-runner/BSP-Windows-Runner.zip`을 실제 빌드했다. 회사 PC에서 Runner용 pip 설치 없이 EXE로 설정·Runner·SSH 실행을 관리하고 기존 사용자 설정/DPAPI/runtime을 재사용한다. TC는 기존 외부 Windows Python을 사용한다. frozen helper의 Job Object gate와 토큰/DLL 환경 분리를 유지했다.

지정 역할별 분석/설계/구현/시험 작성과 별도 Sol High 리뷰 APPROVED, 별도 Luna 실행 Windows 회귀258 PASS/4 SKIP·실제 ZIP smoke7 PASS. 실제 EXE의 CP949 출력 결함 REG-0042를 수정하고 재빌드·재시험했다. 초기 임시 폴더/실행 정책/Windows 경로 길이와 전체 Linux fixture 실패는 [실행 기록](../testing/runs/20261104-portable-runner.md)에 보존한다. [사용 안내](../gui_test/WINDOWS_RUNNER_PORTABLE.md). 실제 회사 SSH/공유 폴더/보드 T-160은 NOT_RUN이며 운영 baseline NONE을 유지한다.

## 2026-11-04 · UI 감사와 main 통합 · 검증 PASS

`ui/web-guidelines-audit`의 `412a39a`에 `origin/main`의 `2572aee`를 병합했다. 감사의 접근성·입력 보호와 main의 컴팩트 요약·모션·상태 기반 단일 트리 토글을 함께 보존한다. 독립 Sol High 리뷰와 두 빌드, workflow51, standalone18, package pytest6이 PASS했다. CI는 main push 뒤 자동 실행 예정이고 실제 BSP·장비·Jira 인수는 NOT_RUN이다. [통합 실행 기록](../testing/runs/20261104-web-guidelines-main-merge.md)과 [증거 manifest](../testing/runs/20261104-web-guidelines-main-merge-evidence/source-manifest.json)를 참조한다.

main과 감사 브랜치가 독립적으로 같은 식별자를 사용했다. main의 T-150~152/REG-0039~0040은 유지하고 감사 항목을 T-153~155/REG-0041로 재할당했다. 기존 실행 증거의 내용·해시는 보존한다.

## 2026-11-04 · UI 규칙 점검

사용자 지시로 Web Interface Guidelines를 적용해 접근성·성능·UX 위반을 우선순위대로 수정한다. 기존 미커밋 변경을 보존하기 위해 `97a509d` 기반 별도 작업 트리를 사용한다. 상세 설계/구현/시험 작성/독립 리뷰/실행 보고는 사용자 지정 모델로 분리했다. 설계와 실제 검증 결과는 [UI 점검 실행 기록](../testing/runs/20261104-web-guidelines-audit.md)을 따른다. 서버 데이터 계약·운영 게이트 변경 및 실제 장비 실행은 없다.

## 2026-11-04 · TC 트리 단일 ＋/− 토글

RQ-39/D-52/T-152. 사용자 정정에 따라 Test cases의 두 아이콘을 상태 기반 버튼 하나로 변경했다. 모두 펼쳐지면 −, 하나라도 접히면 ＋이며 폴더가 없으면 비활성화한다. 선택·실행 순서와 기존 28px 크기를 유지한다. Terra Low 구현, Sol Medium 시험 작성, 독립 Sol High APPROVED, Luna Low 단독 GUI **18 PASS·두 빌드 PASS**. 최초 시험 선택자 오류 REG-0040의 17 PASS/1 FAIL과 재시험을 [실행 기록](../testing/runs/20261104-tree-toggle.md)에 보존했다. 8766에 최신 정적 자산을 반영하고 HTTP200·파일 해시·작업 목록 보존을 확인했다. API/DB/worker 변경이나 실제 장비 실행은 없다. 커밋·main 머지·푸시는 사용자 승인 범위다.

## 2026-11-04 · 메인 화면 가독성·TC 트리 아이콘

RQ-19/20/24/11 및 RQ-39, D-52/T-150. 메인 진행률을 컴팩트 요약 띠로 정리하고 장식 문구·정적 아바타를 제거했다. 핵심 설명/상태 대비와 긴 소스·경로 줄바꿈, 작은 화면 배치를 개선했다. Test cases의 전체 펼치기/접기는 작은 ＋/− 아이콘으로 바꾸며 접근성 이름과 기존 동작을 유지했다. API/DB/worker/계산·게이트 변경 없음.

사용자 지정 모델 분담으로 분석·설계·구현·시험을 수행하고 별도 Sol High 리뷰 APPROVED. 최초 격리40+GUI18 PASS 후 최신 main의 모션 개선을 통합했다. 최종 코드 `a58b26f764609f44dac49949197e755788e4e396`에서 Luna Low **회귀44+단독GUI18 PASS·두 빌드 PASS**, 독립 통합 재검토 APPROVED. 초기 누락·공유 스타일 REG-0039와 Windows npx harness 실행 실패/재시험을 [실행 기록](../testing/runs/20261104-hallmark-overview.md)에 보존했다. 실제 BSP/회사/장비 인수는 미수행이다. 기존 8766 서비스에 검증된 정적 자산을 반영하고 HTTP200·JS/CSS SHA256·작업 목록 보존을 확인했다. API 프로세스 재시작은 자동 승인 검토에서 차단되어 수행하지 않았다. main 머지·푸시는 사용자 승인 범위다.

## 2026-11-04 · 서브 단계 축소·그룹 접기·화이트

기능·시험 커밋 `e475eb8ac267e29cdeb7501c5c39eddac10d982e`으로 고정했으며 PORT-001의 최신 전달 기준이다.

RQ-50/D-51 사용자 후속: 단계96px/글씨9~10px, IP180px로 축소하고 선행/일반 그룹 독립 접기·하위 펼침 복원을 추가했다. 참고 Archify 화이트 테마 정정에 맞춰 밝은 배경/흰 카드로 변경했다. 전체37 PASS, 두 UI 빌드 PASS, 독립 Sol High APPROVED. [실행·시각 증거](../testing/runs/20261104-workflow-diagram-light-groups.md). localhost:8766 최신 자산 제공 확인. 서버/데이터/운영 정책 변경 및 실제 ACON/장비 실행 없음.

## 2026-11-04 · 컴팩트 다이어그램·배율·영역 집중

기능·시험 커밋 `8702037dff276c3dd930e851cf7649ccb6ec46db`으로 고정했다. PORT-001의 최신 전달 기준이며 아래 미커밋 표현은 이전 검증 시점의 이력이다.

RQ-50/D-51 후속 사용자 요구: 카드/간격 축소, 25~160% 확대/축소·전체 맞춤, 모듈/그룹/서비스 선택 영역 중앙 이동과 주변 약화, 전체 보기/Esc 복귀. `web/viewport.ts`에 화면 상태를 분리했다. REG-0037 수동 배율 덮기, REG-0038 창 크기 변경·탭 왕복 카메라 복원 경계를 수정하고 회귀를 추가했다. 독립 Sol High 최종 APPROVED, 주 작업자 전체 36 PASS 및 두 UI 빌드 PASS. [실패·재시험·소스·화면 증거](../testing/runs/20261104-workflow-diagram-zoom.md). localhost:8766 최신 자산 제공 확인. API/DB/worker 변경 및 실제 ACON/장비 실행 없음. 사용자가 완료 후 커밋·푸시를 승인했다.

## 2026-11-04 · 다이어그램 오른쪽 펼침과 이동 화살표

RQ-50/D-51 후속 사용자 요청을 반영했다. IP별 5단계를 오른쪽 가로로 펼치고 지정한 Archify HTML의 남색 점 격자·역할별 테두리를 참고해 UI를 바꿨다. 신선한 RUNNING 단계의 진입선에 이동 화살촉/신호를 제공한다. 상태/adapter/host/API/DB/worker 변경 없음. 독립 Sol High 리뷰 APPROVED, 두 빌드 PASS, 주 작업자 전체 재시험 33 PASS. 별도 시험 세션의 환경 실패 20 PASS/7 FAIL/6 NOT_RUN도 보존했다. [실행·증거](../testing/runs/20261104-workflow-diagram-rightward.md). localhost:8766에서 최신 자산 제공을 확인했다. 실제 ACON/회사 인수는 별도이며 후속 UI 커밋은 아직 고정하지 않았다.

## 2026-11-03 · Windows 빌드 실행 정책

RQ-44/T-126/REG-0036. build.cmd에서 자식 PowerShell 프로세스에만 Bypass를 전달하여 build.ps1 로드 시 UnauthorizedAccess를 해결한다. Windows CI 진단에서 PowerShell 7 모듈 경로가 Windows PowerShell의 기본 경로보다 앞서고 Security 모듈 TypeData 중복 오류가 발생함을 확인해, 배치 `setlocal` 안에서 자식 `PSModulePath`를 비워 기본 모듈 탐색을 사용하도록 수정했다. 영구 정책과 부모 환경은 변경하지 않는다. 로컬 신규4/기존49 PASS·4 SKIP, 실제 CMD 두 UI 빌드 PASS. PR #12 통합 CI는 Linux465 PASS/11 SKIP·브라우저25+18 PASS, Windows235 PASS/3 SKIP·설치 스모크 PASS였고 `0ad952fd036e49601c37fc0d3cae95a5c8cc075d`로 main에 병합했다. 실패 시도와 최종 범위는 [원인·수정·독립 검증 기록](../testing/runs/20261103-build-execution-policy.md)에 남긴다. 회사 그룹 정책·공유 드라이브·장비 인수는 별도다.

## 2026-11-03 · Test 현황 실제 연결 보기

RQ-49/D-50. 실행기 설치 전 실제 연결 보기·미설정/미연결 상태·빈 목록·새 실행 차단을 추가했다. Mock 기록 보존, DB schema 변경 없음. 새 Astra 최종 APPROVED. 별도 GPT-6-sol GUI181 PASS·두 UI 빌드 PASS·Chrome1 PASS, 주 작업자가 REG-0032를 발견해 화면 전환 시험을 강화하고 재시험했다. REG-0031 오프라인 중단 차단도 수정했다. [실행 기록](../testing/runs/20261103-live-test-view.md)에 초기 실패·제약과 GitHub Actions Linux/Windows 성공을 보존한다. PR #11을 `01e497167aff7e5f0ae64567a6ce63915b4f6902`로 main에 병합했다. 실제 회사 장비는 실행하지 않았다.

## 2026-11-03 · Windows 직접 실행 진입점

RQ-48/T-139/REG-0030. 사용자 회사 PC에서 Get-Content·CMD dir Z:·직접 py -3 마법사 실행 성공을 확인했다. 이전 드라이브 단절 단정은 철회하며 실제 CMD 오류 원인은 미확정이다. setup.cmd/setup.ps1은 절대 Python 파일을 직접 호출하고 build.cmd의 공유 경로 추정/재연결도 제거한다. [독립 검토·시험 기록](../testing/runs/20261103-direct-windows-launch.md)에 근거를 남긴다. 회사 공유 폴더의 새 CMD/빌드 인수는 사용자 확인 전 미완료다.

## 2026-11-03 · 실제 연결 설정 마법사

RQ-48/D-49. Linux `scripts/setup.sh`, Windows `scripts/setup.cmd`/`setup.ps1`의 단계별 입력·저장/변경·재실행·설치/빌드·실행기/SSH 점검·선택적 이미지/manifest 메뉴를 구현했다. 토큰은 DPAPI/소유자 전용 파일로 분리하며 기존 JSON 추가 필드·DB·Mock 이력을 보존한다. 새 Astra 리뷰 APPROVED, 별도 GPT-6-sol 모의 시험과 CI는 [실행 기록](../testing/runs/20261103-setup-wizard.md)에 기록한다. 실제 SSH/보드/퓨징을 대신 실행하지 않았으며 T-141은 NOT_RUN이다. 초기 프로세스 정리/설정 일관성/호환성 지적은 REG-0029에 남긴다. 최종 CI head96e3a02에서 Linux459/통합UI24/단독UI18·Windows221 및 PS5.1/7 독립 배포 모두 PASS. PR #10 main8831df0 머지 완료; 설정/시험 증거는 같은 실행 기록에 보존한다.


## 2026-11-03 · 자동 이미지 퓨징·TC

RQ-47/D-48. 사용자가 구현·요구사항 갱신을 승인했다. Windows 콘솔 reboot lkshell/fast → manifest로 고정한 이미지 배치 → 부팅 준비 → 필수 TC를 동일 BSP Attempt에 연결한다. 기본 수동/Mock/최종 검토 유지. API/worker/UI 및 JSON 데이터 확장, 실제 장비 실행 없음. 별도 Astra APPROVED, GPT-6-sol 관련 Python163 PASS(Windows POSIX2 제외)·T-135 화면1 PASS·두 UI 빌드 PASS이며 최종 CI head145ee98의 Linux413/통합UI24/단독UI18 및 Windows175·PowerShell5.1/7 독립 빌드/설치가 모두 PASS다. PR #9를 main c72c2da로 머지했다. [실행 기록](../testing/runs/20261103-automatic-flash-test.md)에 실패와 재시험을 보존한다. 실제 배치/baud/프롬프트/serial이 미확인이므로 설정은 기본 비활성, T-136 NOT_RUN이다.

## 2026-11-03 · 회사판 코드 이식 절차

DEV-PORT-01 / 문서 전용. [이식 절차·요청문](../porting/README.md), 기능 안내서와 회사 구조·적용 이력 양식을 추가하고 AGENTS/CLAUDE·문서 지도·변경 규칙·구현 계획에 연결했다. 원본 코드·시험 재사용, 회사 추가 기능 보존, 고정 커밋·선행 기능 확인, 부분 적용 이력과 회사 검증 분리를 명시했다.

제품 코드·DB·기존 제품 시험 결과는 변경하지 않는다. 실제 PORT 기능 묶음은 아직 발행하지 않았고 회사 코드 조사·이식·장비 인수·Claude/OpenCode 호출은 수행하지 않았다. 별도 `docs/company-porting-workflow` worktree에서 작성하며 기존 자동 퓨징 작업은 포함하지 않는다. 검사 결과·게시 기준은 [문서 검증 기록](../testing/runs/20261103-porting-workflow.md)을 따른다. 다음 전달 기능부터 PORT 안내서를 작성하고, 회사에서는 COMPANY_MAP/APPLIED를 초기화한다.

후속 병합: 최신 main의 자동 퓨징 기록과 이식 절차 기록이 같은 위치에 추가되어 충돌했으며 두 기록을 모두 보존했다. [병합 검증](../testing/runs/20261103-porting-merge.md)을 수행하고 사용자 지시에 따라 main에 게시한다.

## 2026-11-03 · 결과 우선 화면과 실행 분리

RQ-39/T-112/T-117. 결과 위·접이식 실행 카드 아래, 설정 아이콘 왼쪽 Run 선택, 세션 정보/결과 상세/로그 접기를 구현한다. API/DB/명령/실행 상태 로직 변경 없음. 새 Astra 최종 APPROVED. 별도 GPT-6-sol 두 UI 빌드 및 새 runtime 브라우저18 PASS. REG-0023 키보드 guard 위치와 REG-0024 숨겨진 관찰 모드를 수정했으며 초기16 PASS/2 FAIL과 재시험을 [실행 기록](../testing/runs/20261103-result-layout.md)에 보존한다. Linux CI에서 Dashboard 공통 label 방향으로 인한 REG-0025 정렬 실패(22 PASS/1 FAIL)를 고친 뒤, 최종 head037be8a의 Linux366/통합UI23/단독UI18 및 Windows149·PowerShell5.1/7 빌드/설치가 모두 PASS였다. PR #8을 main4858d8f로 머지했다.

## 2026-11-03 · 확정 TC 명령과 비용 요약

RQ-46/T-127/T-129 및 RQ-42/T-114. Single `python3 tc1.py -p COM7`, Dual `python3 tc_2.py -n n295_sadk -n2 n296_sadk`를 신규 Windows 프로파일 기본값에 반영한다. 선택 보드의 node 필드와 엄격한 노드명 쌍 치환을 추가하고 python/python3 모두 고정 Python 경로로 치환한다. 저장 프로파일/Mock/기존 COM 계약 유지, DB 스키마 변경 없음. Run/TC 토큰·비용 상세는 기본 접힘이며 진행률 아래 완료 횟수·비용을 요약한다. 미집계·부분 집계·0을 구분한다. 새 Astra/별도 GPT-6-sol 결과는 [실행 기록](../testing/runs/20261103-confirmed-commands-costs.md)에 남긴다. 실제 회사 TC/COM/노드 연결 인수는 미수행이다. 로컬 GUI Python149/단독UI17/두 UI 빌드 PASS. Astra P1인 Manager python3 거부 REG-0022를 수정하고 재시험했다. 로컬 통합 UI fcntl BLOCKED는 보존하고 Linux CI 전체366/통합UI22/단독UI17 PASS, Windows149 및 PowerShell5.1/7 빌드·설치 PASS를 확인했다. Astra 최종 APPROVED. PR #7의 ecc5fd5를 main 0f71a1f로 머지했다.

## 2026-11-03 · 같은 행 전체 선택과 드래그 순서 변경

RQ-39/T-111/T-125. 전체 선택과 이름의 같은 행 배치를 명시적으로 검증하고 TC 위아래 이동 버튼·미사용 로직/스타일을 제거한다. 드래그 순서 변경·Preflight 무효화·기존 Run 불변과 반복 설정은 유지한다. 데이터/API/외부 실행 변경 없음. 새 Astra APPROVED, 별도 GPT-6-sol 두 UI 빌드·단독 브라우저16 PASS. 코드 해시 일치를 주 작업자가 확인했다. [실행 기록](../testing/runs/20261103-drag-only.md). T-111 전체 인수 INVALIDATED는 유지하며 이번 드래그 회귀 PASS와 구분한다.

## 2026-11-03 · TC 필터와 이름 옆 전체 선택

사용자 후속 요청 RQ-39/D-47/T-125. 검색칸 옆에 작은 전체/Single/Dual 유형 필터를 배치하고 전체 선택은 이름 제목 옆으로 이동한다. 전체 선택·부분 선택·필터 밖 선택·실행 순서와 이름 정렬의 독립 동작을 유지한다. 데이터/API/실행기 변경 없음. 새 Astra 검토 세션과 별도 GPT-6-sol 시험 세션의 결과는 [실행 기록](../testing/runs/20261103-compact-catalog.md)에 남긴다. 최종 Astra APPROVED, 두 UI 빌드와 단독 브라우저16 PASS. 최소240px·기본300px·모바일375px 배치 검증 PASS. 최소 너비 헤더 겹침 REG-0021을 수정하고 재검증했다.

## 2026-11-03 · 빌드·전체 선택·Windows 공유 TC 실행기

사용자 요청 RQ-39/44/46, D-47. `scripts`의 Windows/Bash 화면 빌드 진입점, 필터 범위 TC 전체 선택, Linux Dashboard→SSH 터널→Windows Python 실행 경로를 구현했다. Windows 공유 파일을 로컬 snapshot으로 고정하고 실제 COM 인자를 전달한다. Mock/실행기 DB를 분리하며 실제 Job 자동 반영은 이미지/매핑 증거가 없어 계속 비활성이다. 코드/모의 시험 범위이며 실제 Linux/회사 TC/COM 실행은 사용자 수행이다.

사용자 지정에 따라 새 Astra 세션이 구현을 검토하고, 다른 GPT-6-sol 세션이 시험만 수행하며 주 작업자가 실패를 수정·재시험 요청한다. 초기/실패/재시험과 코드 기준은 [이번 실행 기록](../testing/runs/20261103-windows-runner.md)에 보존한다. 최종: Astra 코드 리뷰 APPROVED, 별도 GPT-6-sol 로컬 Python133/브라우저16 및 빌드 PASS. 같은 코드 0ad590d의 CI Linux350/통합UI21/단독UI16, Windows133 및 PS5.1/7 오프라인 패키지 PASS를 확인하여 PR #6을 a80371c로 main에 머지했다. 독립 Claude 검토와 실환경 인수 T-130은 미실행이다. [설정·실행 안내](../gui_test/WINDOWS_RUNNER.md).

## 2026-11-03 · 최신 main과 PR #4 충돌 해결

사용자 지시로 clean main을 `2e2d24b`에서 `50ecbea`로 업데이트하고 Windows 빌드·공통 명령 PR #4에 병합했다. 14개 충돌에서 최신 TC 작업 화면/반복/Retry/사용량·실행 대상과 명령 snapshot을 함께 보존했다. 겹친 PR 요구사항/시험은 RQ-44~45/T-119~124로 재배정하고 과거 실행 문서는 보존한다. 새 명령+반복 통합 시험 및 설정 탭 브라우저 회귀를 추가했다. DB 이전·운영 데이터 변경·실제 외부 실행 없음. [검증 증거·환경 실패·원인/수정](../testing/runs/20261103-merge.md)을 따른다. Windows 전체 Python 결과와 Linux CI를 구분하며 과거 PASS를 새 코드 전체 PASS로 승격하지 않는다.

최종: 코드 `d551492`의 CI 전체 PASS를 확인하고 PR #4를 `104e729`로 main에 머지했다. Linux Python331 / Dashboard 브라우저18 / 단독 브라우저13 PASS, Windows GUI114 및 PowerShell5.1/7 독립 빌드·오프라인 설치 PASS. [최종 CI 실행 기록](../testing/runs/20261103-merge-ci.md), T-119~124 PASS, REG-0015 VERIFIED. 로컬 main도 동기화했으며 실제 BSP/장비/회사 환경 인수와 Claude 독립 검토는 미실행이다.

기준일: 2026-10-11

| 항목 | 상태 | 근거/다음 작업 |
|---|---|---|
| 기존 운영 정책 수집 | COMPLETE | 종합 계획 v0.8 기준, 사용자 후속 문서 요청 반영 |
| 구현 인수인계 문서 | WRITTEN | AGENTS/CLAUDE 및 분리 문서. 문서 검사는 testing/DOC_VALIDATION.md 참고 |
| Claude 검토 | NOT_REVIEWED | 실제 Claude 검토 결과 없음 |
| P0~P7 제품 구현 | NOT_STARTED | 애플리케이션 코드/DB/테스트 러너 없음 |
| 제품 테스트 | NOT_RUN | TEST_RESULTS.csv 초기 상태 |
| Linux·에이전트 실제 연동 | NOT_VERIFIED | OpenCode/Codex 설치는 사용자 진술; 실제 호출 미확인 |
| 보드 시험 | NOT_RUN | 초기 수동 방식 확정, 실제 보드/시험 기준 미설정 |
| Jira 실제 연동 | NOT_VERIFIED | 직접 설정/MCP 선택 정책만 확정 |
| 정상 제품 기준 버전 | NONE | 검증된 코드 기준 아직 없음 |

다음 구현 작업: P0 환경·설계 확인 후 P1 도메인/저장 계층. 이 기록의 “문서 작성” 완료는 구현 착수나 실제 운영 실행 승인이 아니다.

## 후속 기록 형식

날짜 / 수행자·도구 / 기준 커밋 / 단계 / 변경 요약 / RQ·T ID / 실행 ID / 미해결·차단 / 다음 작업. 과거 기록은 삭제하지 않고 새 항목을 추가한다. “완료”에는 확인 가능한 근거를 붙인다.

## 2026-10-12 · 1차 구현 및 후속 변경

위 2026-10-11 표는 구현 전 이력이다. 최신 상태는 아래와 같다.

| 항목 | 상태 | 구현/검증 범위 |
|---|---|---|
| P1 도메인·영속 기록 | IMPLEMENTED_LOCAL | 명령 중복 방지, 계획/선행 게이트, attempt 이력, SQLite WAL |
| P2 worker·잠금·복구 | PARTIAL | 독립 worker, 공유 수정/빌드 잠금, 불명 실행 재시도 차단. 실제 프로세스 재접속 미구현 |
| P3 화면·설정 | IMPLEMENTED_LOCAL | 진행률, 접이식 모듈 표, 설정 UI/JSON, 질문/명령, 실패 재시도 |
| P4 도구 연결 | PARTIAL | JSON 브리지와 도구 선택·교차 리뷰 정책. 실제 CLI wrapper/인증/세션 live 검증 미실행 |
| P5 수동 시험 | IMPLEMENTED_LOCAL | 사례별 PASS/FAIL만 필수. 기타 입력 선택, 현재 작업 기준 자동 연결. 실제 장비 시험 미실행 |
| 데모 선행 수동 완료 | IMPLEMENTED_LOCAL | 계획 확인 후 선행 모듈별 모의 완료. 실제 모드와 나머지 그룹 거부. T-64~67 |
| P6 판단/Jira | PARTIAL | 내부 판단·의존 대기, 직접/MCP 어댑터, 생성 유실 중복 방지 모의 시험. 사내 연동/자동 상태 polling 미검증 |
| P7 회귀·운영 | PARTIAL | Python 78개 PASS, 브라우저 3개 PASS, UI 빌드 PASS. CI/운영 서비스/실제 인수 미완료 |
| README 사용법 | UPDATED | 설치·실행, Windows SSH, 설정 관리, 결과 등록, 데모 완료, 문제 해결 |
| Claude 검토 | NOT_REVIEWED | 독립 Claude 검토는 수행하지 않음 |
| 실제 Linux·SSH·보드·사내 Jira | NOT_RUN | 환경별 브리지와 실제 시험 필요 |

이번 정책 변경은 RQ-14/15/28과 D-36/37에 연결한다. 기존 테이블 schema_version=1을 유지하며 JSON 결과 필드 추가로 이전 결과를 보존한다. 로컬 코드 내용 식별자와 시험별 PASS, 실패 후 재시험 이력은 [20261012 구현 검증](../testing/runs/20261012-implementation.md)에 기록했다.

남은 범위: 모듈별 세부 DAG, Claude 모듈 제안 diff/승인, 시험 사례 편집, 다중 이미지 묶음, 소스 snapshot OS 격리, 최소 영향 무효화, 실제 프로세스 복구, 다중 사용자 권한. 위 PARTIAL 항목을 전체 완료로 승격하지 않는다.

## 2026-10-12 · 키 없는 진입과 외부 에이전트 보고 계약

- 사용자 요청에 따라 로컬/SSH 접속 키 입력과 로그인 세션을 제거했다. 이전 access-token 파일은 사용하지 않으며 새로 만들지 않는다. 현재 8765 화면에 적용했고 기존 작업 DB는 보존했다. RQ-25/29, D-38, T-68~70.
- 단일 운영자 loopback 연결·Host/Origin/Fetch-Site 검사 및 UI 변경 요청 헤더는 유지한다. 화면을 연 것만으로 업그레이드를 생성하지 않는다. DB 스키마 변경은 없다.
- [외부 에이전트 상태·결과 보고 계약](../design/AGENT_STATUS_CONTRACT.md)을 새로 작성했다. bridge/worker/engine과 대조한 요청·결과 필드, 보고 시점, 오류 분류, 빌드 산출물·별도 리뷰·조정/질문 형식, 설정 절차, 인수 체크리스트를 담았다.
- 기존 에이전트 운영/역할 지침의 입력·출력 필드 목록은 삭제하고 새 계약 링크로 대체했다. 실행 운영 정책·역할 업무·논리 데이터 모델은 각 문서에 유지하며 전송 계약과 구분한다.
- 현재는 단계가 끝나면 JSON 결과를 받는다. 중간 퍼센트·heartbeat·agent push API, 에이전트 판단의 자동 Jira 등록과 변경별 분석 분류 자동 반영은 미구현이다. 이번 문서화로 기능 구현 완료를 주장하지 않는다.
- 검증: Python **87 PASS**, UI **3 PASS**, TypeScript/Vite 빌드 PASS. 문서 JSON 예시 6개 형식 PASS. [실행 기록과 파일별 코드 기준](../testing/runs/20261012-local-entry-agent-contract.md)에 최초 시험 실패와 재시험을 보존했다. T-61~70의 최신 결과를 갱신하고 T-01~60의 전체 인수는 NOT_RUN 유지.
- 실제 Linux·외부 CLI wrapper·SSH·장비·사내 Jira와 독립 Claude 검토는 미실행이다. 다음 외부 연동 작업은 새 계약을 외부 에이전트 프로젝트에 전달해 wrapper를 맞추고 환경별 인수를 수행하는 것이다.

## 2026-10-12 · 오케스트레이터 역할과 전체 문서 동기화

수행: Codex / D-39, ADR-06 / RQ-30~34 / T-71~85 / 범위: 문서만 변경.

| 항목 | 상태 | 내용 |
|---|---|---|
| 오케스트레이터 명세 | DESIGNED | 작업별 Claude 1개, 권한/금지, 이벤트 호출, 입력/제안, 버전/중복/재시작/한도, 새 판단 처리 |
| 모듈 보고 계약 | UPDATED_DESIGN | 현재 v1 유지, 목표 v2의 역할별 필수 보고·판단 후보·호환/실패 규칙 추가 |
| 영향 문서 | UPDATED | 루트 README/AGENTS/CLAUDE, 종합 계획 v0.12, 구조/요구사항/상태/데이터/API/UI/역할/운영, 결정·검토 규칙 |
| 구현 계획 | NOT_STARTED | O1 계약 → O2 영속 상태 → O3 조정 실행 → O4 화면/판단 → O5 실제 wrapper 인수 |
| 제품·DB·설정 | UNCHANGED | 기존 코드/시험 파일 manifest와 동일. 실행 코드·runtime·환경 설정 변경 없음 |
| 신규 제품 시험 | NOT_RUN | 15개 추가, 총 85개. 기존 70개 결과와 과거 FAIL 기록 보존 |
| 문서 검증 | PASS | 링크/추적 ID/CSV·JSON 예시·계약 구분·기존 코드/결과 보존 확인. 아래 실행 기록 참조 |
| Claude/외부 연동 검토 | NOT_REVIEWED / NOT_RUN | 독립 Claude 검토, 실제 Linux/CLI/Jira/장비 신규 인수 미실행 |

새 [오케스트레이터 명세](../design/ORCHESTRATOR_SPEC.md)와 [모듈 보고 계약](../design/AGENT_STATUS_CONTRACT.md)이 외부 에이전트 프로젝트 인계 자료다. 모듈 → worker/DB → 오케스트레이터/화면의 보고 경로를 통일했다. blocking 판단 후보의 접수/보류 원자성, 조정 응답 저장에 의한 자기 무효화 방지, 실패 시 없는 자료를 만들지 않는 규칙도 검토해 반영했다.

문서 검사와 변경 파일별 해시는 [오케스트레이터 문서 검증](../testing/runs/20261012-orchestrator-docs.md)에 기록한다. 이 기록은 신규 기능 구현이나 신규 제품 시험 PASS를 의미하지 않는다. 과거 실행 기록은 수정하지 않는다.

## 2026-10-12 · M0 Claude 수동 오케스트레이터 제공

수행: Codex / D-40, ADR-07 / RQ-35 / T-86~91. 실제 agent 정의, 표준 라이브러리 검사·내보내기 CLI, 가상 입력/결과/근거, 사용 안내를 추가했다. 신규 패키지 66 + 기존 백엔드 87 = 153 PASS, UI 빌드 PASS, 격리 브라우저 3 PASS. [실행 증거](../testing/runs/20261012-claude-agent-package.md)에 파일 해시·개별 결과를 기록했다.

| 항목 | 상태 | 의미 |
|---|---|---|
| M0 수동 호출 패키지 | IMPLEMENTED / LOCAL_TESTED | 준비된 파일→제안→수동 검사. 실제 작업 실행 없음 |
| T-86~90 | PASS | 패키지 구조/입출력/오류/보류 미리보기/독립 배포 검증 |
| T-91 Claude 인수 | NOT_RUN | 사용자가 직접 모델을 호출할 예정. 모델 품질·실제 도구 제한 미확인 |
| O1~O5 / T-71~85 | NOT_STARTED / NOT_RUN | 자동 대시보드 연결·모듈 v2는 이번 패키지와 별개 |
| DB/API/worker/UI | UNCHANGED | 기존 기능 회귀 시험 재실행 |
| GitHub 반영·Claude 독립 검토 | NOT_PERFORMED | 로컬 결과이며 새 PR/머지나 모델 검토 없음 |

사용법은 [Claude 안내](../agents/CLAUDE_ORCHESTRATOR_GUIDE.md)에 모았다. 기존 runtime이나 외부 BSP 프로젝트를 초기화/덮어쓰지 않았다.

## 2026-10-12 · 소스 기준 입력 선택·브리지 기본값

D-41 / ADR-08 / RQ-36 / T-92~95. 소스 기준 빈칸은 새 작업 시 clean new_base Git HEAD를 읽어 고정한다. 기본 브리지 경로, 빈 항목 채우기, 사용자 명령/기존 작업 보존, 누락/권한 점검과 [사용 안내](../agents/ENVIRONMENT_AND_BRIDGES.md)를 추가했다. DB 스키마 변경 없음.

Python 173 PASS, 화면 빌드 PASS, 브라우저 4 PASS. [실행 기록](../testing/runs/20261012-settings-defaults.md)에 증거와 미실행 범위를 기록했다. 현재 8765 화면에도 기본값/자동 기준을 반영하고 기존 job snapshot 보존을 확인했다. 실제 agent/BSP 빌드/원격 연결/Claude 검토는 미실행이며 기본 경로가 설치 성공을 뜻하지 않는다. GitHub 반영 없음.


## 2026-10-12 · N1 작업 폴더 기반 내장 CLI 연결

D-42 / ADR-09 / RQ-37 / T-96~102. 내장 연결을 기본으로 추가하고 기존 JSON 브리지를 고급 호환 모드로 보존했다. 작업 폴더/계정 PATH의 도구 탐지·버전/옵션/로컬 로그인 설정 점검, 기존 역할 Markdown 읽기·job 고정, 도구별 비대화형 호출/구조화 출력 정규화, 등록 빌드/검증/통합 명령·이미지 검증을 구현했다. 별도 bridges 폴더나 사용자 wrapper 제작은 필요하지 않다.

- 코드/설정: backend/settings.py, adapters/native.py·process.py·bridge.py, worker/main.py, domain/engine.py, api/main.py, apps/web/src/main.tsx, config/examples/settings.json.
- DB: 테이블/schema_version=1 유지. 새 설정·job/result JSON 필드 확장, 기존 job snapshot/사용자 브리지 보존. 실행불명은 UNKNOWN·lease 유지, 종료된 연결 실패만 사용자 재시도.
- 화면: 내장 연결 기본, 지침/명령 입력, 접이식 경로/모델/역할 매핑, 도구 점검 상태. 코드 수정/리뷰 세션 분리와 기존 게이트·수동 시험 유지.
- 검증: Python 217 PASS, TypeScript/Vite 빌드 PASS, 브라우저 5 PASS. 최초 화면/프로세스 경계 실패와 수정은 REG-0006~0008 및 [실행 기록](../testing/runs/20261012-native-cli.md)에 보존한다.
- 로컬 8765: 새 API/worker와 UI 적용. 기존 작업 1개의 전체 JSON snapshot 해시 보존, 설정은 데모 유지. 외부 작업 시작 없음.
- 미실행: 실제 Linux/Claude/OpenCode/Codex 모델 호출·BSP 빌드/보드·사내 Jira 인수, Claude 독립 검토. O1~O5 자동 orchestrate·모듈 보고 v2·실제 프로세스 재접속·OS snapshot 격리는 후속 범위다. GitHub 반영 없음(현재 폴더에 .git 없음).

상세 사용법은 [환경 안내](../agents/ENVIRONMENT_AND_BRIDGES.md), 외부 agent 필드 기준은 [보고 계약](../design/AGENT_STATUS_CONTRACT.md) 12절을 따른다. 모의 CLI 프로세스 시험을 실제 모델/하드웨어 인수로 표현하지 않는다.

## 2026-10-25 · GUI Test 모듈

D-43 / ADR-10 / RQ-38 / T-103~108. `feature/gui-test`에서 공통 Python Core/Mock Adapter/SQLite/API/React UI, Windows 단독 관리자, 기존 Dashboard 최소 연결, 자동 결과 이력/재검증/아웃박스, 설치·패키징·CI를 구현했다. 기존 DB와 수동시험·업그레이드 게이트를 보존한다. 회사 TC/RBM/실장비 연결은 미정이므로 운영 실행은 차단돼 있다.

증거 및 실제 수행 결과: [GUI Test 검증](../testing/runs/20261025-gui-test.md). T-108 실제 회사 인수, 자동 로그 정리/현장 DAG 확인, 독립 Claude 검토는 별도 범위다. Mock 결과를 운영 검증 완료로 승격하지 않는다.

## 2026-10-25 · GUI Test 설정 접기·TC 목록·순서 편집

수행: Codex / 기준 커밋 `f7e082fe9d46420e4f36c884cd5831ec77fdb835` / P3 UI / D-44·ADR-11 / RQ-39 / T-109~111.

- 상태: IN_PROGRESS. 사용자 후속 요청 3개와 문서 동기화 요구를 요구사항·결정·화면 설계·시험 목록에 반영했다.
- 변경: 공통 `gui_test/web/TestPage.tsx`, `test.css`; 설정 접기/상태 기억, 소스·Suite 접기, 폴더별 TC 목록 정돈. 드래그 순서 편집을 이어서 구현·검증한다.
- 데이터: 브라우저 접힘 설정만 추가. DB/API/worker 변경 없음. 기존 실행 데이터와 외부 BSP·Jira·장비는 변경하지 않는다.
- 중간 검증: 최초 설정 접기 버전의 두 빌드와 Windows 단독 기존 브라우저 4개 PASS. TC 목록/드래그 추가 후의 최종 검증을 대신하지 않는다. 새 T-109~111은 검증 전 NOT_RUN이다.
- 다음: 드래그 구현, 최종 빌드·격리 Mock 브라우저·화면 확인, 실행 증거와 최신 결과 갱신. 실제 통합/장비 시험과 Claude 검토는 범위 밖이다.

## 2026-10-26 · GUI Test 사용성 변경 검증 완료

위 IN_PROGRESS 항목의 후속 결과: **IMPLEMENTED_LOCAL / WINDOWS_MOCK_TESTED**. RQ-39 / D-44·ADR-11 / T-109~111. 설정 4개 접기·입력 보존·접힘 상태 기억, TC 폴더 부분 선택/펼침/유형 배지/빈 검색, 행 드래그 및 번호 선택을 구현했다. 순서 변경 시 기존 Preflight를 해제하고 완료 Run의 고정 순서를 보존한다.

- 검증: Dashboard·단독 TypeScript/Vite 빌드 PASS. Windows 단독 브라우저 5 PASS, 추가 화면 검사 T-109~111 PASS. 드래그 삽입 표시/취소/같은 위치, 키보드 조작, 새로고침, 375/680px 화면 확인. [실행 기록과 manifest](../testing/runs/20261026-gui-ux.md)에 도구 실패/수정 및 범위를 보존했다.
- 문서: 요구사항·결정·UI 설계·구현 계획·시험 목록·최신 결과·사용 안내를 동기화했다. 작업 중 추가된 `50579ff`의 `docs/gui_test/` 요구사항 원문은 유지하고 해당 지도에 후속 RQ-39 링크를 추가했다.
- 데이터/운영: DB/API/worker 변경 없음. 화면은 기존 8767 서버에 반영됐으며 새로고침으로 적용된다. 시험은 별도 runtime/18767 포트에서 수행했다. 실제 Linux 통합·모델/보드/사내망·독립 Claude 검토는 미실행이고 운영 baseline은 NONE 유지.
- 다음: 변경 내용을 커밋·푸시하고 현재 화면의 사용자 확인을 받는다. 실제 환경 인수는 기존 미완료 범위로 유지한다.

## 2026-11-01 · 로컬 main 업데이트

사용자 승인 계획에 따라 main `2e2d24b`의 코드·문서를 반영했다. 기존 코드/DB/산출물은 `.local-update/20261101T052210Z/`에 복원 가능하게 보관하고 새 DB를 사용한다. 기본 포트 8766·무로그인을 유지한다. Python 284 PASS, 두 UI 빌드 PASS, 백업 복원 PASS. 스크린샷 4개 미동기화, charset-normalizer 설치 미완료, 서버·브라우저는 권한 제한으로 BLOCKED. 소스 갱신과 실행 인수 완료를 구분한다. [실행 기록·제약·복원](../testing/runs/20261101-local-update.md).

2026-11-01 후속: 사용자 재실행 요청 후 bash run.sh로 8766 서버 시작. Chrome에서 무로그인 대시보드와 API 연결됨 확인. 기본 서버/브라우저 접속 차단 해소, 전체 E2E는 미실행. 상세는 20261101-local-update 실행 기록 후속 항목 참고.

## 2026-11-01 · TC 작업 화면 후속 구현

RQ-39 / D-45 / T-109~114. 트리 검색·정렬, 목록 안 드래그(번호 제거), 설정 접기, 검색 패널 숨김·너비 저장, 실패 TC 단독 재실행, 모델별 토큰/비용의 작은 progress·TC 표시를 구현했다. Attempt JSON optional usage 필드 추가; DB 테이블 이전 없음. 사용량은 실제 어댑터 보고만 사용하며 현재 Mock는 모델 호출 없음이다.

GUI Python 69 PASS, 두 UI 빌드 PASS, Chrome 직접 검색/정렬/드래그/접기/패널 너비·숨김 복원/단일 실패 재실행 확인. 격리 전체 자동 E2E는 socket 권한으로 BLOCKED. 실모델 계량·실장비 인수는 NOT_RUN. [실행 증거·실패 이력·남은 범위](../testing/runs/20261101-tc-workspace.md). 서버 8766 재시작/최신 화면 확인. GitHub 게시 없음.

## 2026-11-01 · 설정 통합·반복·탐색기형 목록·실행 대상

RQ-39~41/D-46/T-115~118. 소스·Suite까지 설정 탭 통합, 복귀 버튼/톱니바퀴 toggle/Esc, TC별/전체 반복과 고정 plan/회차별 집계, 32px 행, 열 제목 정렬, 실행 당시 보드 이름/local 표시를 구현했다. DB는 optional JSON만 확장, 이전 Run 호환 유지. [이번 검증](../testing/runs/20261101-repeat-settings.md): GUI Python82 PASS/두 빌드 PASS/Chrome 직접 6회 Mock 반복 및 설정복귀·정렬 확인. 실제 모델·보드/BCM 미연동, 격리 자동 전체 E2E는 기존 환경 제약 유지. 서버8766 최신 버전으로 재시작.

## 2026-11-02 · 요구사항 통합 및 Git 게시

사용자 지시로 RQ-39~43을 최종 기능별로 정리하고, UI·GUI 실행 계약·구조·API·데이터·상태·사용법·시험 계획/문서 지도를 동기화했다. 중간 시안/과거 시험 이력은 보존했다. 현재 코드 전체 Python299 PASS와 두 빌드를 검증했다. GitHub의 기준 main은 로컬 원본과 같은 2e2d24b이며 변경 파일만 별도 브랜치/PR로 반영한다. [게시 검증·포함 범위·실제 미연동](../testing/runs/20261102-publication.md)을 참고한다. 실제 인수와 독립 Claude 검토는 완료하지 않았다.

## 2026-10-28 · Windows GUI Test 전용 빌드

RQ-44/T-119~121. `gui_test/web`의 npm/TypeScript/Vite 설정을 독립시키고 Windows build.ps1/build.cmd 및 standalone ZIP 모드를 추가한다. 기존 Dashboard 빌드와 legacy 통합 patch 모드는 보존한다. DB/API/Run 동작 변경 없음. 실행 증거와 미검증 범위는 [빌드 검증 기록](../testing/runs/20261028-gui-test-build.md)을 따른다.

검증 완료: Python 전체 회귀 289 PASS, 독립 폴더 시험 58 PASS(전체 회귀에서 다루는 Git/Dashboard 2개 제외), Windows PowerShell 5.1/7 독립 빌드·오프라인 설치·CLI smoke·Mock E2E PASS. 위 실행 기록의 커밋과 CI 증거를 기준으로 하며 실장비/회사 환경 인수는 포함하지 않는다.

## 2026-10-28 · TC 실행 명령 템플릿

RQ-45/T-122~124. 공통 Single/Dual argv 프로파일, TC 이름/파일/경로 및 COM 변수, 로컬 저장·미리보기·버전 검사와 Run snapshot을 추가한다. Mock은 명령 치환 결과만 기록하며 실제 명령 실행은 계속 차단한다. 기존 documents/runs JSON을 사용하고 DB schema_version=1을 유지한다. [검증 기록](../testing/runs/20261028-gui-command-templates.md)을 따른다.

명령 템플릿 검증: 전체 Python315 PASS(신규26 포함), 단독/통합 웹 빌드 PASS, 브라우저17 PASS(단독6+통합11), 문서 검사 PASS. 위 검증 기록에 커밋/범위를 명시했다. 실제 명령 실행은 활성화하지 않았다.

## 2026-11-03 · 다이어그램 탭 문서 작성

수행: Codex / 상태: **DESIGN_ONLY / 구현 지시 대기** / RQ-50 / D-51 / T-144~149. 사용자 요청은 문서 우선 작성이며 제품 코드 구현은 승인되지 않았다.

- 작성: [다이어그램 상세 설계](../design/WORKFLOW_DIAGRAM.md), [PORT-001 이식 안내 초안](../porting/PORT-001.md). 가로 상위 흐름·IP 단계 접기/펼치기·현재 단계/진행률·상태 점·진행 선 효과와 전용 폴더/최소 접점을 정리했다.
- 동기화: 요구사항·결정·UI/구조·구현/시험 계획·시험 목록/결과·문서 지도·porting 목록. T-144~149는 전부 NOT_RUN이다.
- 데이터/운영: 코드·DB·설정·실행 중 서비스 변경 없음. 외부 ACON/BSP/장비/Jira 호출 없음. 기존 미추적 다이어그램 산출물은 보존했다.
- 미확정: ACON 상태 제공/만료 기준, 6개 서버 단계를 5개 표시 단계로 대응하는 세부 구현, 회사 UI/데이터 구조. PORT의 코드 커밋·실행 명령·시험 증거는 구현 후 고정한다.
- 문서 검사와 범위: [작성 기록](../testing/runs/20261103-workflow-diagram-docs.md). 제품 검증·회사 인수·Claude 독립 검토는 수행하지 않았고 운영 baseline을 변경하지 않았다.
- 다음: 사용자 구현 지시 후 adapter/fixture부터 구현·검증하고 코드 기준을 고정하여 이식 안내서를 완성한다.

## 2026-11-03 · 다이어그램 문서 후속 리뷰

수행: Codex / RQ-50·D-51 / **DESIGN_ONLY 유지**. 사용자 요청으로 동작·효율성·연동 관점에서 문서와 현재 코드를 대조하고 문서를 보완했다. 별도 컨텍스트 리뷰·실제 검사 결과는 [새 리뷰 기록](../testing/runs/20261103-workflow-diagram-review.md)에 남긴다.

- 보완: 연결 점/실행 표시 분리, 화살표별 게이트/활동 의미, 현재 단계·유효성·취소 중·자동 Test 판정, snapshot 조회 관찰/선택 세대·역순 응답, 순수 adapter와 앱 의존 방향, 100개 규모·비활성 탭 비용·격리 호스트 시험.
- 동기화: 상세 설계·PORT-001·요구사항/결정·UI/구조·구현/시험 계획·T-144~149 목록/CSV·문서 지도. 시험 상태는 전부 NOT_RUN이다.
- 현재 제약: ACON 계약/회사 구조 미확정, 기존 N/A 집계/완료와 목표 정책의 차이. 호스트 online/updated_at만으로 새 표시 요구를 충족하지 못하므로 향후 최소 연결 변경에 관찰 정보와 refresh 보호도 포함한다.
- 제품 코드·DB·설정·서비스·외부 연동 변경 없음. 이전 작성 기록/제품 시험 이력과 기존 미추적 시안 산출물은 보존했다. 구현 착수는 별도 사용자 지시 대기다.
- 별도 세션 재검토: 문서 설계 범위 APPROVED. 영구 pending 복구·명령 충돌 복구를 포함한 모든 snapshot 유입 보호·실제 이력 크기 측정 권고를 추가 반영했다. 문서 정합성 대체 검사와 diff 공백 검사는 PASS, Python 표준 검사기는 참조 실행 파일 누락으로 BLOCKED다. 제품 시험/구현 승인을 의미하지 않는다.

## 2026-11-03 · 다이어그램 탭 구현

RQ-50 / D-51 / T-144~149. 후속 사용자 구현 승인으로 `workflow_diagram/`의 순수 adapter·화면 타입·독립 화면/CSS·조회 보호·시험을 작성하고 `apps/web/src/main.tsx`와 `tsconfig.json`을 연결했다. 이전 문서 전용 기록은 이력으로 보존한다.

- 표시: 상위 네 노드 가로 흐름, IP별 접기/펼치기와 5단계, code/build 보존, 서버 진행률·유효 결과·연결 점/실행 상태 분리, 활동 경로별 모션, 숨김/모션 줄이기·일시정지 지원.
- 연동: 기존 polling 재사용, 5초 읽기 제한시간·이벤트 실패 분리·세대/순서/version 보호·명령 충돌 복구 공통 수용 경계. 새 작업/대상 전환 시 펼침 초기화, 일반 탭 왕복은 유지한다.
- 데이터/운영: DB·worker·설정·BSP 실행 정책 변경 없음. 실제 ACON 근거 미제공은 확인 불가다. 기존 미추적 시안과 작업 도중 별도로 바뀐 `scripts/build.cmd` 및 `.runtime-gui/`는 건드리지 않았다.
- 검증 완료(로컬 모의): 별도 Sol High 코드 리뷰 APPROVED, Luna Low 실행 전체 32 PASS(단위·브라우저·실제 앱 route mock), 두 UI 빌드와 전용 폴더 격리 production 빌드 PASS. 100개 표시 39.6ms/모두 펼침 134.3ms, 탭 왕복 추가 조회 0·비활성 실제 렌더 증가 0. 초기 Vite/esbuild sandbox 차단과 재시험·시각 확인 근거는 [실행 기록](../testing/runs/20261103-workflow-diagram-implementation.md)에 구분한다.
- 문서/이식: 실제 파일·의존성·명령·검토 근거를 [PORT-001](../porting/PORT-001.md)에 반영했다. 미커밋 코드를 고정 커밋으로 표시하지 않으며 회사/ACON T-149와 운영 baseline NONE은 유지한다.

후속 커밋·게시 승인: 사용자의 커밋/푸시 지시로 구현·시험·문서를 `199b04b5c080e41ec9794326828fbc4874cef633`에 고정하고 PORT-001에 전달 기준을 기록했다. 코드/시험 내용은 검증 시점과 같으며 후속 변경은 기준 기록 문서뿐이다. 별도 scripts/build.cmd·실행 데이터·기존 시안은 포함하지 않는다. 회사/ACON 인수와 운영 baseline은 그대로다.


## 2026-11-04 · 전체 탭 애니메이션

사용자 요청 / RQ-19·20·39·50 / T-151. Emil 기준 변경표를 먼저 제시한 뒤 버튼 120ms, 모달 200ms 진입, transform 진행률 180ms, 즉시 탐색·카메라, 단일 화살촉 1200ms와 키보드/reduced-motion을 구현했다. DB/API·실행 정책 변경 없음. 공유 폴더 43개 회귀 PASS. 게시용 독립 worktree 41개 회귀와 두 빌드 PASS. 검증 범위·초기 실패와 제약은 [실행 기록](../testing/runs/20261104-ui-motion.md)에 기록했다. 별도 레이아웃 작업을 보존하고 모션 변경만 게시한다.

## 2026-11-04 · main 동기화와 이식 안내

작업 브랜치를 원격 main `ab4580c36f1aad2ab627a1f12beb440da7004845`에 동기화했다. 이전 미커밋 소스와 문서는 stash `11a8d299b8f70cca7b850d242e007b361b4e0839`에 보존하고 이미 통합된 main 코드와 시험 기록을 기준으로 사용한다. [PORT-001](../porting/PORT-001.md)과 [PORT-002](../porting/PORT-002.md)는 현재 전달 코드와 역사적 증거를 구분한다. 로컬 Chrome 회귀 51 PASS, 두 빌드 PASS, 독립 코드·문서 리뷰 APPROVED. 범위와 증거는 [실행 기록](../testing/runs/20261104-ui-finish.md)에 남긴다. 실제 외부 연동·회사/실장비 인수는 NOT_RUN이다.
