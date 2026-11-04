"""Rebuild both Diagram Design variants from one factual topology."""
from pathlib import Path
import json
from html import escape

ROOT = Path(__file__).resolve().parent
REVISION = '5d2f680a368e5873632b087baccb057be8b621be'
FONT_LINK = 'https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500;600&family=Noto+Serif:ital@0;1&family=Noto+Sans+KR:wght@400;500;600&family=Noto+Serif+KR:wght@400&display=swap'
PALETTES = {
    'default': dict(name='기본 · 밝은 미니멀', paper='#f5f5f5', ink='#2d3142', muted='#4f5d75', soft='#5a6580', accent='#bf4520', link='#2e5aa8', tint='#f4e7e2', store='#ebebec', rule='#bfc0c0'),
    'blueprint': dict(name='블루프린트 · 사용자 지정', paper='#eff4f8', ink='#17324d', muted='#41576b', soft='#4b6276', accent='#0b6e75', link='#2457a6', tint='#e0eeee', store='#e5ecf2', rule='#afbfcd'),
}

def text(x, y, value, cls='name', anchor='middle', fill=None):
    color = f' fill="{fill}"' if fill else ''
    return f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}"{color}>{escape(value)}</text>'

def node(p, x, y, name, sub, tag, kind='backend'):
    fill = p['tint'] if kind == 'focal' else p['store'] if kind in ('store', 'external', 'input') else '#ffffff'
    stroke = p['accent'] if kind == 'focal' else p['muted'] if kind == 'store' else p['ink']
    dash = ' stroke-dasharray="5,4"' if kind == 'optional' else ''
    return '\n'.join([
        f'<g data-node="{escape(tag)}">',
        f'<rect x="{x}" y="{y}" width="224" height="96" rx="6" fill="{p["paper"]}"/>',
        f'<rect x="{x}" y="{y}" width="224" height="96" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1.2"{dash}/>',
        f'<rect x="{x+16}" y="{y+12}" width="80" height="16" rx="2" fill="{p["paper"]}" stroke="{p["rule"]}" stroke-width="0.8"/>',
        text(x+56, y+23, tag, 'tag'), text(x+112, y+51, name), text(x+112, y+73, sub, 'sub'), '</g>'
    ])

def edge(p, prefix, d, label, lx, ly, vertical=False, tone='muted', dashed=False):
    # Label masks have an 8px gap to their connector, outside all node bounds.
    width = ((sum(12 if ord(c) > 127 else 7.2 for c in label)+16+3)//4)*4
    x = lx+8 if vertical else lx-width/2
    y = ly-8 if vertical else ly-24
    dash = ' stroke-dasharray="5,4"' if dashed else ''
    return '\n'.join([
        f'<path data-edge="{escape(label)}" d="{d}" fill="none" stroke="{p[tone]}" stroke-width="1.2" marker-end="url(#{prefix}-{tone})"{dash}/>',
        f'<rect x="{x}" y="{y}" width="{width}" height="16" rx="2" fill="{p["paper"]}"/>',
        text(x+width/2, y+12, label, 'edge-label', fill=p[tone])
    ])

def svg_start(p, prefix, title, desc):
    markers=''.join(f'<marker id="{prefix}-{role}" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{p[role]}"/></marker>' for role in ('muted','accent','link'))
    return f'<svg viewBox="0 0 1280 720" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="{prefix}-title {prefix}-desc"><title id="{prefix}-title">{title}</title><desc id="{prefix}-desc">{desc}</desc><defs>{markers}</defs><rect x="0" y="0" width="1280" height="720" fill="{p["paper"]}"/>'

def legend(p, prefix, detail=False):
    items=[f'<line x1="40" y1="660" x2="1240" y2="660" stroke="{p["rule"]}" stroke-width="0.8"/>']
    for x, fill, stroke, label in [(40,p['tint'],p['accent'],'실행·결과 확정'),(300,'#ffffff',p['ink'],'구현된 구성'),(540,p['store'],p['muted'],'저장소·외부 대상')]:
        items += [f'<rect x="{x}" y="680" width="20" height="16" rx="2" fill="{fill}" stroke="{stroke}"/>', text(x+32,692,label,'legend','start')]
    items += [f'<line x1="860" y1="688" x2="900" y2="688" stroke="{p["link"]}" stroke-dasharray="5,4"/>',text(912,692,'선택 연결 / 코드 재사용','legend','start')]
    return '\n'.join(items)+'</svg>'

def overview(p, variant):
    pre='bsp-system-'+variant+'-overview'
    out=[svg_start(p,pre,'BSP OS 업그레이드 시스템 구성','운영자 화면과 API, BSP 상태 DB, 실행 관리자 및 도구, 별도로 관리되는 GUI Test의 현재 논리 구성을 보여줍니다.')]
    out += [text(48,52,'01 / BSP & DASHBOARD','section-tag','start'), text(1232,52,'현재 구현 · 논리 구성','legend','end')]
    edges=[
        ('M 272,144 H 352','명령·조회',312,144,False,'link',False),
        ('M 576,144 H 656','읽기·쓰기',616,144,False,'muted',False),
        ('M 960,128 H 880','읽기·확정',920,128,False,'muted',False),
        ('M 1072,192 V 320','게이트 통과',1072,256,True,'muted',False),
        ('M 1072,416 V 512','실행·결과',1072,464,True,'muted',False),
        ('M 960,168 H 924 Q 916,168 916,176 V 272 Q 916,280 908,280 H 776 Q 768,280 768,288 V 320','이미지 저장',816,280,False,'muted',False),
        ('M 464,192 V 320','GUI API',464,256,True,'link',False),
        ('M 464,416 V 512','상태·이력',464,464,True,'muted',False),
    ]
    for args in edges: out.append(edge(p,pre,*args))
    nodes=[
        (48,96,'운영자 웹 화면','React / TypeScript','BROWSER','input'),
        (352,96,'Dashboard API','FastAPI / loopback','API','backend'),
        (656,96,'BSP 상태 DB','dashboard.db / SQLite WAL','STATE','store'),
        (960,96,'BSP 실행 관리자','Worker + Engine','CONTROL','focal'),
        (352,320,'GUI Test 관리·실행','Manager + GUI Worker','GUI CORE','backend'),
        (656,320,'BSP 산출물','Image / SHA-256 / evidence','ARTIFACT','store'),
        (960,320,'내장 실행 어댑터','Native / Bridge v1','ADAPTER','backend'),
        (352,512,'GUI 실행 DB','runs.db / mode isolation','GUI STATE','store'),
        (960,512,'BSP 도구·등록 빌드','Claude / OpenCode / Codex','EXTERNAL','external'),
    ]
    for args in nodes: out.append(node(p,*args))
    out += [text(48,396,'화면은 상태를 조회하고,','legend','start'),text(48,420,'서버는 실행과 결과를 확정한다.','legend','start'),text(656,548,'초기 장비 시험: 수동 PASS/FAIL','legend','start'),text(656,572,'다운로드 ≠ 시험 통과','legend','start')]
    out.append(legend(p,pre));return '\n'.join(out)

def gui_detail(p, variant):
    pre='bsp-system-'+variant+'-gui'
    out=[svg_start(p,pre,'GUI Test와 Windows 실행기 구성','GUI Test Core가 모드별 DB와 Mock 또는 Windows 원격 어댑터를 사용하고 Windows 실행기는 공유 소스를 고정해 TC를 실행하며 단독 앱은 별도 인스턴스로 공통 Core를 재사용합니다.')]
    out += [text(48,52,'02 / GUI TEST & WINDOWS RUNNER','section-tag','start'),text(1232,52,'실제 장비 인수 전','legend','end')]
    edges=[
        ('M 272,144 H 352','GUI API',312,144,False,'link',False),
        ('M 576,144 H 656','설정 시',616,144,False,'link',True),
        ('M 880,144 H 960','SSH 터널',920,144,False,'link',False),
        ('M 426.67,192 V 320','기록·판정',426.67,256,True,'muted',False),
        ('M 501.33,192 V 248 Q 501.33,256 509.33,256 H 760 Q 768,256 768,264 V 320','기본 Mock',656,256,False,'muted',False),
        ('M 272,368 H 304 Q 312,368 312,360 V 176 Q 312,168 320,168 H 352','Core 재사용',312,272,True,'link',True),
        ('M 1072,192 V 512','읽기·고정',1072,352,True,'muted',False),
        ('M 960,168 H 920 Q 912,168 912,176 V 552 Q 912,560 904,560 H 880','검증된 argv',912,432,True,'muted',False),
    ]
    for args in edges: out.append(edge(p,pre,*args))
    nodes=[
        (48,96,'통합 GUI Test 화면','Dashboard / common React UI','BROWSER','input'),
        (352,96,'GUI Test Core','Manager + GUI Worker','CONTROL','focal'),
        (656,96,'Windows 원격 어댑터','WindowsRemote / HTTP','REMOTE','optional'),
        (960,96,'Windows TC 실행기','Loopback / token / process','EXECUTOR','backend'),
        (48,320,'Windows 단독 앱','Local API + UI / own Core','STANDALONE','input'),
        (352,320,'모드별 GUI DB','Run / Attempt / reservation','STATE','store'),
        (656,320,'Mock 어댑터','Simulated TC / boards','DEFAULT','backend'),
        (656,512,'TC 프로세스·보드','Windows Python / COM / node','TC','external'),
        (960,512,'공유 TC 소스','Snapshot / source hash','SOURCE','store'),
    ]
    for args in nodes: out.append(node(p,*args))
    out += [text(48,548,'단독 앱은 별도 API·DB를 사용한다.','legend','start'),text(48,572,'원격 실행은 통합 모드에서만 선택한다.','legend','start')]
    out.append(legend(p,pre,True));return '\n'.join(out)

def page(variant,p):
    other='blueprint' if variant=='default' else 'default'
    return f'''<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BSP 시스템 구성 · {p['name']}</title><link href="{FONT_LINK}" rel="stylesheet">
<style>
*{{box-sizing:border-box}}body{{margin:0;background:{p['paper']};color:{p['ink']};font-family:'Geist','Noto Sans KR','Malgun Gothic',sans-serif;padding:48px 32px}}
main{{max-width:1280px;min-width:0;margin:auto}}a{{color:{p['link']};text-underline-offset:4px}}nav{{display:flex;gap:24px;flex-wrap:wrap;font-size:13px;margin:20px 0 40px}}
.eyebrow,.section-tag,.tag{{font-family:'Geist Mono',monospace;font-size:8px;letter-spacing:.08em;fill:{p['soft']}}}.eyebrow{{font-size:11px;color:{p['muted']};letter-spacing:.16em}}
h1{{font-family:'Instrument Serif','Noto Serif','Noto Serif KR',serif;font-size:36px;font-weight:400;line-height:1.3;margin:16px 0}}.lead{{font-size:15px;color:{p['muted']};max-width:800px;line-height:1.8}}
h2{{font-size:18px;font-weight:600;margin:36px 0 12px}}.diagram-container{{width:100%;overflow-x:auto}}svg{{display:block;width:100%;min-width:1280px}}
.name{{font-family:'Geist','Noto Sans KR','Malgun Gothic',sans-serif;font-size:12px;font-weight:600;fill:{p['ink']}}}.sub{{font-family:'Geist Mono',monospace;font-size:9px;fill:{p['muted']}}}.edge-label,.legend{{font-family:'Geist','Noto Sans KR','Malgun Gothic',sans-serif;font-size:12px;font-weight:500;fill:{p['muted']}}}
.notes{{display:grid;grid-template-columns:1.3fr 1fr;gap:32px;padding:24px 0 40px;border-bottom:1px solid {p['rule']}}}.notes h3{{font-size:15px;margin:0 0 10px}}.notes p,details{{font-size:13px;line-height:1.9;color:{p['muted']};margin:0}}.status{{border-left:3px solid {p['accent']};padding-left:20px}}details{{padding:24px 0}}summary{{cursor:pointer;font-weight:600;color:{p['ink']}}}li{{margin:4px 0}}footer{{border-top:1px solid {p['rule']};padding-top:20px;font-size:12px;line-height:1.8;color:{p['muted']}}}code{{font-family:'Geist Mono',monospace;font-size:11px}}:focus-visible{{outline:2px solid {p['link']};outline-offset:5px}}
@media(max-width:720px){{body{{padding:28px 16px}}h1{{font-size:28px}}.notes{{grid-template-columns:1fr}}}}
@media print{{body{{padding:0}}nav{{display:none}}.diagram-container{{overflow-x:visible}}svg{{min-width:0}}section{{break-inside:avoid}}}}
</style></head><body><main>
<header><p class="eyebrow">DIAGRAM DESIGN / SYSTEM ARCHITECTURE / 2026-11-03</p><h1>BSP OS 업그레이드 시스템 구성</h1><p class="lead">실행의 기준은 서버에 저장된 상태입니다. BSP 업그레이드와 GUI Test는 각각의 실행 규칙과 저장소를 유지하며, 화면은 확정된 기록을 조회합니다.</p><nav aria-label="다이어그램 탐색"><span>{p['name']}</span><a href="bsp-system-{other}.html">{PALETTES[other]['name']} 보기</a><a href="#gui-detail">GUI Test 상세</a><a href="#evidence">근거·범위</a></nav></header>
<section aria-labelledby="overview-heading"><h2 id="overview-heading">01. 전체 구성</h2><div class="diagram-container" tabindex="0" aria-label="전체 구성도. 좁은 화면에서는 좌우로 스크롤하세요.">{overview(p,variant)}</div>
<div class="notes"><div><h3>게이트를 통과한 작업만 실행</h3><p>모든 모듈의 분석은 병렬로 진행할 수 있습니다. 설계 이후에는 최초 계획 확인이 필요하며, 나머지 모듈은 부트로더 선행 그룹 전체 완료를 기다립니다. 수정과 빌드는 같은 배타 자원을 사용합니다. API와 worker는 분리되고, GUI worker는 통합 worker 프로세스 안에서 별도 풀로 실행됩니다.</p></div><div class="status"><h3>자동 Claude 조정은 설계 단계</h3><p>현재 v1 실행 경로와 별도 수동 Claude 패키지를 제공합니다. 자동 조정 O1~O5·모듈 보고 v2는 미구현입니다. 계획 제안과 실제 프로세스 배정·결과 확정의 권한은 구분합니다.</p></div></div></section>
<section id="gui-detail" aria-labelledby="gui-heading"><h2 id="gui-heading">02. GUI Test와 Windows 실행기</h2><div class="diagram-container" tabindex="0" aria-label="GUI Test 상세 구성도. 좁은 화면에서는 좌우로 스크롤하세요.">{gui_detail(p,variant)}</div>
<div class="notes"><div><h3>실행 위치와 논리 상태를 분리</h3><p>Manager가 Preflight·예약·반복 계획·최종 판정을 관리합니다. 원격 모드에서는 Windows 실행기가 소스 snapshot과 검증된 Python 명령으로 TC를 실행합니다. 어댑터는 ID·요청 해시·소스 기준을 확인하며 로그와 종료 결과를 수집합니다. Mock 이력은 별도 DB에 보존됩니다.</p></div><div class="status"><h3>실제 장비 검증은 별도</h3><p>실제 Linux·SSH·공유 폴더·COM/보드 인수는 완료되지 않았습니다. 보드 이미지·매핑 근거가 없는 실제 Job 자동 결과 반영은 비활성입니다. 초기 BSP 장비 시험은 사례별 수동 PASS/FAIL과 별도 최종 검토를 유지합니다.</p></div></div></section>
<details id="evidence"><summary>근거와 표현 범위</summary><ul><li>현재 커밋: <code>{REVISION}</code>. 이전 구성도의 코드 근거를 재사용하고 관련 backend·Core·runner 파일의 변경이 없음을 확인했습니다.</li><li>기준 문서: <a href="../architecture/SYSTEM_ARCHITECTURE.md">시스템 구조</a>, <a href="../design/GUI_TEST_CONTRACT.md">GUI Test 계약</a>, <a href="../design/ORCHESTRATOR_SPEC.md">오케스트레이터 명세</a>.</li><li>코드: backend/api/main.py, backend/worker/main.py, backend/domain/engine.py·policy.py, backend/adapters/bridge.py, gui_test/runtime.py, gui_test/core/manager.py·worker.py, gui_test/adapters/windows_remote.py, gui_test/execution/host.py.</li><li>전체 그림에서는 각 도구·빌드를 한 노드로 묶었습니다. GUI 원격 어댑터·실행기·소스·TC·단독 앱은 상세 그림에 유지했습니다. 두 그림 사이의 동일 구성은 확대 설명을 위한 중복 표현입니다.</li><li>API의 산출물 다운로드와 worker의 Jira 직접/MCP 판단 연결은 보조 경로로 설명만 남겼습니다. Jira 실제 사내 인수는 미완료이며, 일반 오류를 무조건 Jira로 보내지 않습니다.</li><li>1280 × 720 문서용 구성도 2장. 정적 HTML·인라인 SVG이며 모바일은 그림 내부에서 가로 스크롤합니다. 웹 글꼴을 가져올 수 없으면 로컬 글꼴로 대체됩니다.</li></ul></details>
<footer>Diagram Design 2.6.139 · {p['name']}<br>이 문서는 시스템 설명용입니다. 다이어그램 검증 결과는 제품 시험 또는 실제 장비 인수 결과를 대신하지 않습니다.</footer>
</main></body></html>'''

if __name__ == '__main__':
    for variant,palette in PALETTES.items():
        dest=ROOT/f'bsp-system-{variant}.html'
        dest.write_text(page(variant,palette),encoding='utf-8')
        print(dest.name)
    (ROOT/'styles.json').write_text(json.dumps({'plugin':'diagram-design@diagram-design','version':'2.6.139','revision':REVISION,'styles':PALETTES,'custom_style_scope':'artifact-only; installed style guide unchanged','scope':'documentation only; no product or external execution'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
