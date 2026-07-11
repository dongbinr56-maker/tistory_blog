from __future__ import annotations

import datetime as dt
import html
import json
import re
from pathlib import Path
from typing import Any

from .models import Draft, QualityReport


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def paragraphs(value: str) -> str:
    return "".join(f"<p>{esc(paragraph)}</p>" for paragraph in value.split("\n\n") if paragraph.strip())


def render_article_html(draft: Draft, site: dict[str, Any]) -> str:
    sources = {source.id: source for source in draft.source_items}
    hero = draft.images.get("hero", {})
    hero_image = f'<img class="hero-image" src="{esc(hero.get("url"))}" alt="{esc(draft.title)} 대표 이미지">' if hero.get("url") else ""
    sections: list[str] = []
    for number, section in enumerate(draft.sections, start=1):
        source_image = next((draft.images.get(source_id, {}) for source_id in section.source_ids if draft.images.get(source_id, {}).get("url")), {})
        issue_image = f'<img class="issue-image" src="{esc(source_image.get("url"))}" alt="{esc(section.headline)} 관련 이미지">' if source_image else ""
        links = "".join(
            f'<li><a href="{esc(sources[source_id].url)}" rel="nofollow noopener noreferrer" target="_blank">{esc(sources[source_id].source)} 원문 보기</a></li>'
            for source_id in section.source_ids
            if source_id in sources
        )
        sections.append(
            f"""<section class="issue-card">
  <p class="issue-number">ISSUE {number:02d}</p>
  <h2>{esc(section.headline)}</h2>
  {issue_image}
  <h3>이번 변화의 요점</h3>{paragraphs(section.what_happened)}
  <h3>쉽게 풀어 보면</h3>{paragraphs(section.plain_explanation)}
  <h3>실무에서 달라지는 점</h3>{paragraphs(section.why_it_matters)}
  <h3>먼저 볼 지점</h3>{paragraphs(section.editorial_take)}
  <h3>확인해 볼 것</h3>{paragraphs(section.reader_action)}
  <h3>출처</h3><ul class="sources">{links}</ul>
</section>"""
        )
    return f"""<article class="tistory-newsroom" lang="ko">
  <style>
    .tistory-newsroom {{max-width:760px;margin:0 auto;color:#1f2937;font-family:Apple SD Gothic Neo,Malgun Gothic,sans-serif;line-height:1.85}}
    .tistory-newsroom .hero {{padding:30px 26px;border:1px solid #dbe4ee;border-radius:18px;background:#f8fafc}}
    .tistory-newsroom .hero-image,.tistory-newsroom .issue-image {{display:block;width:100%;margin:0 0 20px;border-radius:14px;object-fit:cover;background:#e2e8f0}}
    .tistory-newsroom .hero-image {{max-height:380px}} .tistory-newsroom .issue-image {{max-height:330px}}
    .tistory-newsroom h1 {{margin:0 0 16px;color:#111827;font-size:30px;line-height:1.38}}
    .tistory-newsroom h2 {{color:#111827;font-size:23px;line-height:1.45}}
    .tistory-newsroom h3 {{margin:20px 0 6px;color:#334155;font-size:16px}}
    .tistory-newsroom p {{margin:0 0 14px}}
    .tistory-newsroom .eyebrow,.tistory-newsroom .issue-number {{color:#0f766e;font-weight:700;font-size:13px;letter-spacing:.04em}}
    .tistory-newsroom .issue-card {{margin:28px 0;padding:24px;border:1px solid #e2e8f0;border-radius:16px;background:#fff}}
    .tistory-newsroom .sources {{padding-left:20px}} .tistory-newsroom a {{color:#0f766e}}
  </style>
  <header class="hero">
    {hero_image}
    <p class="eyebrow">{esc(draft.date)} · {esc(site.get('default_category', 'IT·개발'))}</p>
    <h1>{esc(draft.title)}</h1>
    {paragraphs(draft.intro)}
  </header>
  {''.join(sections)}
  <section><h2>마무리</h2>{paragraphs(draft.closing)}</section>
</article>"""


def _copy_page(drafts: list[dict[str, Any]], site: dict[str, Any] | None = None) -> str:
    site = site or {}
    payload = json.dumps(drafts, ensure_ascii=False).replace("</", "<\\/")
    automation = {
        "repository": str(site.get("github_repository", "")),
        "branch": str(site.get("github_branch", "main")),
        "workflow_file": str(site.get("github_workflow_file", "daily-tistory-draft.yml")),
    }
    automation_payload = json.dumps(automation, ensure_ascii=False).replace("</", "<\\/")
    template = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>티스토리 초안 검토</title>
<style>
body{margin:0;background:#f3f6fa;color:#172033;font-family:Apple SD Gothic Neo,Malgun Gothic,sans-serif;line-height:1.6}main{width:min(1120px,calc(100% - 32px));margin:36px auto}header,.panel{border:1px solid #dbe4ee;border-radius:18px;background:#fff;box-shadow:0 10px 30px #0f17210b}header{padding:28px;margin-bottom:18px}h1,h2{margin:0 0 8px}.muted{color:#64748b}.layout{display:grid;grid-template-columns:280px minmax(0,1fr);gap:18px}.panel{padding:18px}.draft-button{width:100%;margin:5px 0;padding:12px;border:1px solid #dbe4ee;border-radius:10px;background:#fff;text-align:left;cursor:pointer}.draft-button:hover,.draft-button.active{background:#ecfdf5;border-color:#5eead4}.copy{width:auto;padding:9px 13px;border:0;border-radius:9px;background:#0f766e;color:#fff;font-weight:700;cursor:pointer}.copy:disabled{background:#94a3b8;cursor:not-allowed}.field{padding:12px;margin:10px 0;background:#f8fafc;border-radius:10px;overflow-wrap:anywhere}.field b{display:block;margin-bottom:5px}.field p{margin:4px 0 10px;color:#526174;font-size:14px}.regenerate{border:1px solid #fed7aa;background:#fffaf5}.regenerate .copy{background:#c2410c}.regenerate-panel{margin-top:12px;padding:12px;border:1px solid #fed7aa;border-radius:9px;background:#fff}.regenerate-panel label{display:block;font-size:14px;font-weight:700}.regenerate-panel input{display:block;width:100%;margin:7px 0;padding:10px;border:1px solid #cbd5e1;border-radius:8px;box-sizing:border-box}.regenerate-status{display:block;min-height:20px;margin-top:9px;color:#9a3412;font-size:13px;font-weight:700}.workflow-link{color:#0f766e;font-size:13px}.tabs{display:flex;gap:8px;margin:22px 0 0;border-bottom:1px solid #dbe4ee}.tab{min-width:88px;padding:10px 15px;border:0;border-radius:10px 10px 0 0;background:#eef2f7;color:#526174;font-weight:800;cursor:pointer}.tab[aria-selected="true"]{background:#0f766e;color:#fff}.tab-pane{padding-top:16px}.tab-pane[hidden]{display:none}textarea{display:block;width:100%;min-height:520px;resize:vertical;padding:16px;border:1px solid #cbd5e1;border-radius:12px;background:#0b1220;color:#d9f99d;font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;box-sizing:border-box}iframe{display:block;width:100%;height:620px;border:1px solid #dbe4ee;border-radius:12px;background:#fff}.pane-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}.pane-head p{margin:0;color:#64748b;font-size:14px}.status{min-height:20px;margin-top:12px;color:#0f766e;font-size:14px;font-weight:700}.policy-link{color:#0f766e}@media(max-width:760px){main{width:min(100% - 20px,1120px);margin:12px auto}.layout{grid-template-columns:1fr}.pane-head{align-items:stretch;flex-direction:column}.copy{width:100%}textarea{min-height:400px}iframe{height:520px}}
</style></head><body><main><header><h1>티스토리 초안 검토</h1><p class="muted">기본 화면은 HTML 소스입니다. 티스토리 글쓰기의 HTML 모드에 그대로 붙여넣고, View에서 실제 렌더링 결과를 확인하세요.</p><a class="policy-link" href="tistory-pages/index.html">티스토리 정책 페이지 복사본</a> · <a class="policy-link" href="adsense-checklist.html">애드센스 발행 전 체크리스트</a></header><div class="layout"><aside class="panel" id="list" aria-label="초안 날짜 목록"></aside><section class="panel" id="detail" aria-live="polite"></section></div></main>
<script>
const drafts=__DRAFT_PAYLOAD__;
const automation=__AUTOMATION_PAYLOAD__;
const list=document.querySelector('#list'),detail=document.querySelector('#detail');
let current=null,currentHtml='';
const automationReady=/^[^/]+[/][^/]+$/.test(automation.repository)&&!automation.repository.includes('YOUR_')&&Boolean(automation.workflow_file);
function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));}
function values(value){return Array.isArray(value)?value:[];}
function status(text){const target=document.querySelector('#status');if(target)target.textContent=text;}
function workflowUrl(){return automationReady?`https://github.com/${automation.repository}/actions/workflows/${encodeURIComponent(automation.workflow_file)}`:'';}
function apiBase(){return `https://api.github.com/repos/${automation.repository.split('/').map(encodeURIComponent).join('/')}/actions/workflows/${encodeURIComponent(automation.workflow_file)}`;}
function regenerationStatus(text){const target=detail.querySelector('#regeneration-status');if(target)target.textContent=text;}
function setTab(name){
  detail.querySelectorAll('[role="tab"]').forEach(tab=>{const active=tab.dataset.tab===name;tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;});
  detail.querySelectorAll('[data-pane]').forEach(pane=>pane.hidden=pane.dataset.pane!==name);
}
async function copyText(text,label){
  try{await navigator.clipboard.writeText(text);}catch(error){const code=document.querySelector('#html-code');if(!code)throw error;code.focus();code.select();document.execCommand('copy');}
  status(`${label} 복사 완료`);
}
function showRegenerationPanel(){
  const panel=detail.querySelector('#regeneration-panel');if(!panel)return;panel.hidden=false;detail.querySelector('#github-token')?.focus();
}
async function pollRegeneration(token,startedAt,attempt=0){
  if(attempt>=60){regenerationStatus('실행 상태 확인 시간이 지났습니다. Actions 페이지에서 결과를 확인하세요.');return;}
  try{
    const response=await fetch(`${apiBase()}/runs?event=workflow_dispatch&per_page=10`,{headers:{Accept:'application/vnd.github+json',Authorization:`Bearer ${token}`,'X-GitHub-Api-Version':'2022-11-28'}});
    if(!response.ok)throw new Error(`HTTP ${response.status}`);
    const data=await response.json();
    const run=values(data.workflow_runs).find(item=>item.head_branch===automation.branch&&new Date(item.created_at).getTime()>=startedAt-60000);
    if(!run){regenerationStatus('재생성 작업을 등록했습니다. GitHub Actions 실행을 찾는 중입니다…');setTimeout(()=>pollRegeneration(token,startedAt,attempt+1),5000);return;}
    const link=detail.querySelector('#workflow-link');if(link){link.href=run.html_url;link.hidden=false;}
    if(run.status!=='completed'){regenerationStatus(`원문 재생성 진행 중 (${run.status})…`);setTimeout(()=>pollRegeneration(token,startedAt,attempt+1),5000);return;}
    if(run.conclusion==='success'){regenerationStatus('재생성이 완료됐습니다. GitHub Pages 반영 후 페이지를 새로고침하세요.');return;}
    regenerationStatus(`재생성이 완료되지 않았습니다 (${run.conclusion||'unknown'}). Actions 로그를 확인하세요.`);
  }catch(error){regenerationStatus(`실행 상태를 확인하지 못했습니다: ${error.message}`);}
}
async function triggerRegeneration(){
  if(!current||!automationReady)return;
  const input=detail.querySelector('#github-token'),button=detail.querySelector('#confirm-regeneration');
  const token=input?.value.trim()||'';
  if(!token){regenerationStatus('GitHub 토큰을 입력하세요. 토큰은 이 브라우저에 저장하지 않습니다.');input?.focus();return;}
  button.disabled=true;regenerationStatus(`${current.date} 원문 재생성을 요청하는 중입니다…`);
  const startedAt=Date.now();
  try{
    const response=await fetch(`${apiBase()}/dispatches`,{method:'POST',headers:{Accept:'application/vnd.github+json',Authorization:`Bearer ${token}`,'X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'},body:JSON.stringify({ref:automation.branch,inputs:{run_date:current.date,refresh:'true'}})});
    if(response.status!==204){let message=`HTTP ${response.status}`;try{message=(await response.json()).message||message;}catch(_error){}throw new Error(message);}
    input.value='';regenerationStatus('재생성 작업을 시작했습니다. 품질 검토를 통과한 경우에만 기존 초안을 덮어씁니다.');pollRegeneration(token,startedAt);
  }catch(error){regenerationStatus(`재생성 요청에 실패했습니다: ${error.message}`);button.disabled=false;}
}
function renderDetail(raw){
  const d={title:escapeHtml(raw.title),date:escapeHtml(raw.date),tags:values(raw.tags).map(escapeHtml),candidates:values(raw.title_candidates).map(escapeHtml),quality:escapeHtml(raw.quality_status),checks:values(raw.publish_checklist).map(escapeHtml)};
  const regeneration=automationReady?`<div class="field regenerate"><b>원문 재생성</b><p>같은 날짜의 초안을 새로 작성합니다. 품질 검토를 통과한 경우에만 기존 본문을 덮어씁니다.</p><button class="copy" type="button" id="open-regeneration">원문 재생성</button><div class="regenerate-panel" id="regeneration-panel" hidden><label for="github-token">GitHub fine-grained PAT (Actions 쓰기 권한)</label><input id="github-token" type="password" autocomplete="off" placeholder="github_pat_..." aria-describedby="token-note"><p id="token-note">토큰은 GitHub API로만 전송되며 브라우저 저장소에 보관하지 않습니다.</p><button class="copy" type="button" id="confirm-regeneration">재생성 실행</button><a class="workflow-link" id="workflow-link" href="${escapeHtml(workflowUrl())}" target="_blank" rel="noopener" hidden>Actions 실행 보기</a><span class="regenerate-status" id="regeneration-status"></span></div></div>`:`<div class="field regenerate"><b>원문 재생성</b><p>GitHub 저장소 설정이 없어 재생성 기능을 사용할 수 없습니다.</p><button class="copy" type="button" disabled>원문 재생성</button></div>`;
  detail.innerHTML=`<h2>${d.title}</h2><div class="field"><b>제목 후보</b>${d.candidates.map(item=>`• ${item}`).join('<br>')}<br><button class="copy" id="copy-title" type="button">제목 복사</button></div><div class="field"><b>태그</b>${d.tags.join(', ')}<br><button class="copy" id="copy-tags" type="button">태그 복사</button></div><div class="field"><b>품질 상태</b>${d.quality} · 사람 검토 필수</div>${regeneration}<div class="field"><b>발행 전 확인</b><ul>${d.checks.map(item=>`<li>${item}</li>`).join('')}</ul></div><div class="tabs" role="tablist" aria-label="본문 표시 방식"><button class="tab" role="tab" aria-selected="true" aria-controls="html-pane" id="html-tab" data-tab="html">HTML</button><button class="tab" role="tab" aria-selected="false" aria-controls="view-pane" id="view-tab" data-tab="view" tabindex="-1">View</button></div><section class="tab-pane" id="html-pane" data-pane="html" role="tabpanel" aria-labelledby="html-tab"><div class="pane-head"><p>아래 소스를 티스토리 글쓰기의 HTML 모드에 바로 붙여넣으세요.</p><button class="copy" id="copy-html" type="button">본문 HTML 복사</button></div><textarea id="html-code" aria-label="티스토리 본문 HTML" readonly>불러오는 중...</textarea></section><section class="tab-pane" id="view-pane" data-pane="view" role="tabpanel" aria-labelledby="view-tab" hidden><div class="pane-head"><p>HTML 탭의 동일한 원본을 렌더링한 미리보기입니다.</p></div><iframe id="article-view" title="${d.date} 블로그 본문 미리보기" referrerpolicy="no-referrer"></iframe></section><p class="status" id="status"></p>`;
  detail.querySelector('#copy-title').onclick=()=>copyText(raw.title,'제목');
  detail.querySelector('#copy-tags').onclick=()=>copyText(values(raw.tags).join(','),'태그');
  detail.querySelector('#copy-html').onclick=()=>copyText(currentHtml,'본문 HTML');
  detail.querySelector('#open-regeneration')?.addEventListener('click',showRegenerationPanel);
  detail.querySelector('#confirm-regeneration')?.addEventListener('click',triggerRegeneration);
  detail.querySelectorAll('[role="tab"]').forEach(tab=>tab.onclick=()=>setTab(tab.dataset.tab));
  setTab('html');
}
async function selectDraft(raw){
  current=raw;currentHtml='';
  document.querySelectorAll('[data-date]').forEach(item=>item.classList.toggle('active',item.dataset.date===raw.date));
  renderDetail(raw);
  const code=detail.querySelector('#html-code'),frame=detail.querySelector('#article-view');
  try{const response=await fetch(raw.html_path+`?v=${Date.now()}`);if(!response.ok)throw new Error(`HTTP ${response.status}`);currentHtml=await response.text();code.value=currentHtml;frame.src=raw.html_path+`?v=${Date.now()}`;status(`${raw.date} 본문을 불러왔습니다. HTML 탭에서 복사할 수 있습니다.`);}catch(error){const message=`본문을 불러오지 못했습니다: ${error.message}`;code.value=message;frame.removeAttribute('src');status(message);}
}
drafts.forEach((draft,index)=>{const button=document.createElement('button');button.className='draft-button';button.dataset.date=draft.date;button.textContent=`${draft.date} — ${draft.title}`;button.onclick=()=>selectDraft(draft);list.append(button);if(!index)selectDraft(draft);});
if(!drafts.length)detail.innerHTML='<p>아직 생성된 초안이 없습니다.</p>';
</script></body></html>"""
    return template.replace("__DRAFT_PAYLOAD__", payload).replace("__AUTOMATION_PAYLOAD__", automation_payload)


def _checklist_page(site: dict[str, Any]) -> str:
    today = dt.date.today().isoformat()
    items = [
        "실제 작성자 이름, 소개, 문의 이메일을 입력했고 소개·문의 페이지를 티스토리에 만들었다.",
        "개인정보처리방침과 편집·AI 활용 원칙을 티스토리 페이지로 공개했다.",
        "각 원문 링크가 열리고, 외부 기사 전체를 복사·번역·단순 재작성하지 않았다.",
        "사실 요약 외에 나만의 영향 분석·의견·실무 점검 항목을 각 이슈에 추가했다.",
        "제목·본문·태그에 과장, 허위 정보, 광고 클릭 유도, 제한 가능성이 높은 콘텐츠가 없다.",
        "비어 있거나 공사 중인 페이지, 감사/로그인 페이지에는 광고 코드를 넣지 않았다.",
        "카테고리와 관련된 기존 글 내부 링크를 적절히 추가했고, 이미지와 링크의 권리를 확인했다.",
        "애드센스 승인 후 실제 도메인 루트에 올바른 ads.txt를 배치했다.",
        "발행 전 사람이 원문·출처·사실·표현을 최종 검토했다.",
    ]
    rows = ''.join(f'<li><label><input type="checkbox"> {esc(item)}</label></li>' for item in items)
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>애드센스 발행 전 체크리스트</title><style>body{{max-width:800px;margin:40px auto;padding:0 20px;color:#1f2937;font-family:Apple SD Gothic Neo,Malgun Gothic,sans-serif;line-height:1.7}}li{{margin:13px 0;padding:13px;background:#f8fafc;border-radius:9px;list-style:none}}ul{{padding:0}}input{{width:18px;height:18px;vertical-align:middle}}.note{{padding:16px;border-left:4px solid #0f766e;background:#f0fdfa}}</style></head><body><h1>애드센스 발행 전 체크리스트</h1><p>{esc(site.get('blog_name'))} · {today}</p><p class="note">이 목록은 자동 승인을 보장하지 않습니다. Google 정책은 바뀔 수 있으므로 발행 전 공식 정책과 정책 센터를 확인하세요.</p><ul>{rows}</ul><h2>티스토리 페이지 템플릿</h2><p><a href="tistory-pages/index.html">실제 설정값이 반영된 소개·문의·개인정보처리방침·편집 원칙 HTML</a>을 각각 복사해 티스토리 페이지로 등록하세요.</p><p><a href="https://support.google.com/adsense/answer/10008391?hl=ko">Google 게시자 정책</a> · <a href="https://support.google.com/publisherpolicies/answer/11190248?hl=ko">복제 콘텐츠 정책</a> · <a href="https://support.google.com/adsense/answer/12171612?hl=ko">ads.txt 가이드</a></p></body></html>"""


def _render_policy_html(markdown: str, site: dict[str, Any]) -> str:
    replacements = {
        "{{author_name}}": str(site.get("author_name", "")),
        "{{blog_name}}": str(site.get("blog_name", "")),
        "{{contact_email}}": str(site.get("contact_email", "")),
        "{{today}}": dt.date.today().isoformat(),
    }
    for token, value in replacements.items():
        markdown = markdown.replace(token, value)
    rows: list[str] = []
    list_open = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        numbered = re.match(r"^\d+\.\s+(.+)$", line)
        if numbered:
            if not list_open:
                rows.append("<ol>")
                list_open = True
            rows.append(f"<li>{esc(numbered.group(1))}</li>")
            continue
        if list_open:
            rows.append("</ol>")
            list_open = False
        if not line:
            continue
        if line.startswith("# "):
            rows.append(f"<h1>{esc(line[2:])}</h1>")
        else:
            rows.append(f"<p>{esc(line)}</p>")
    if list_open:
        rows.append("</ol>")
    return """<article style="max-width:760px;margin:0 auto;color:#1f2937;font-family:Apple SD Gothic Neo,Malgun Gothic,sans-serif;line-height:1.8">
""" + "\n".join(rows) + "\n</article>"


def _write_tistory_pages(root: Path, site: dict[str, Any]) -> None:
    source_dir = root / "content" / "tistory-pages"
    if not source_dir.exists():
        source_dir = Path(__file__).resolve().parents[2] / "content" / "tistory-pages"
    output_dir = root / "docs" / "tistory-pages"
    output_dir.mkdir(parents=True, exist_ok=True)
    links: list[str] = []
    for source_path in sorted(source_dir.glob("*.md")):
        page_name = source_path.stem
        output_path = output_dir / f"{page_name}.html"
        output_path.write_text(_render_policy_html(source_path.read_text(encoding="utf-8"), site), encoding="utf-8")
        links.append(f'<li><a href="{esc(output_path.name)}">{esc(page_name)}.html</a> — 티스토리 HTML 모드에 복사</li>')
    index = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>티스토리 정책 페이지 복사</title><style>body{max-width:760px;margin:40px auto;padding:0 20px;color:#1f2937;font-family:Apple SD Gothic Neo,Malgun Gothic,sans-serif;line-height:1.7}li{margin:12px 0;padding:12px;background:#f8fafc;border-radius:9px}a{color:#0f766e;font-weight:700}</style></head><body><h1>티스토리 정책 페이지 복사</h1><p>각 링크를 열어 내용을 복사한 뒤, 티스토리의 페이지 작성 화면 HTML 모드에 붙여넣으세요.</p><ul>""" + "".join(links) + "</ul></body></html>"
    (output_dir / "index.html").write_text(index, encoding="utf-8")


def write_outputs(root: Path, draft: Draft, report: QualityReport, site: dict[str, Any]) -> None:
    docs = root / "docs"
    tistory = docs / "tistory"
    tistory.mkdir(parents=True, exist_ok=True)
    article_path = tistory / f"{draft.date}.html"
    article_path.write_text(render_article_html(draft, site), encoding="utf-8")
    metadata = {
        "date": draft.date,
        "title": draft.title,
        "title_candidates": draft.title_candidates,
        "tags": draft.tags,
        "meta_description": draft.meta_description,
        "article_count_note": draft.article_count_note,
        "quality_status": report.status,
        "manual_review_required": True,
        "publish_checklist": [
            "원문 링크와 사실관계를 확인합니다.",
            "작성자 분석이 자신의 실제 관점인지 검토합니다.",
            str(site.get("required_internal_link_note", "관련 글 내부 링크를 추가합니다.")),
            "소개·문의·개인정보 페이지가 실제 값으로 공개됐는지 확인합니다.",
            "티스토리 HTML 모드에 붙여넣은 뒤 모바일 화면을 확인합니다.",
        ],
        "sources": [{"name": source.source, "title": source.title, "url": source.url} for source in draft.source_items],
        "images": draft.images,
    }
    (tistory / f"{draft.date}.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    build_site(root, site)


def build_site(root: Path, site: dict[str, Any]) -> None:
    docs = root / "docs"
    tistory = docs / "tistory"
    tistory.mkdir(parents=True, exist_ok=True)
    drafts: list[dict[str, Any]] = []
    for metadata_path in sorted(tistory.glob("????-??-??.json"), reverse=True):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        html_path = metadata_path.with_suffix(".html")
        if not html_path.exists():
            continue
        metadata["html_path"] = f"tistory/{html_path.name}"
        drafts.append(metadata)
    (tistory / "index.json").write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_tistory_pages(root, site)
    (docs / "index.html").write_text(_copy_page(drafts, site), encoding="utf-8")
    (docs / "adsense-checklist.html").write_text(_checklist_page(site), encoding="utf-8")
    (docs / ".nojekyll").touch()
