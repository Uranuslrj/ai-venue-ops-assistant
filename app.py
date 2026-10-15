"""剧本杀门店 AI 运营系统 V1 本地 Demo。

启动：
    <bundled-python> app.py

浏览器打开：
    http://127.0.0.1:8765

依赖：仅 Python 标准库。
"""

from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
import urllib.request
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent
RAG_DIR = BASE_DIR / "rag"
if str(RAG_DIR) not in sys.path:
    sys.path.insert(0, str(RAG_DIR))
from retrieval import query_knowledge, load_chunks
DB_FILE = BASE_DIR / "script_kill_ops.sqlite3"
PORT = int(os.getenv("PORT", "8765"))
PROVIDER_CONFIG = {
    "provider": os.getenv("AI_PROVIDER", ""),
    "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
    "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    "api_key": os.getenv("OPENAI_API_KEY", ""),
    "wire_api": os.getenv("OPENAI_WIRE_API", "chat_completions"),
}

CSV_TABLES = {
    "dm_profiles": "dm_profile_template.csv",
    "player_requirements": "player_requirement_weights.csv",
    "script_catalog": "script_catalog.csv",
    "sessions": "session_records.csv",
    "feedback": "feedback_records.csv",
    "recommendations": "recommendation_records.csv",
    "ai_feedback": "ai_feedback_results.csv",
    "improvements": "improvement_records.csv",
}

DIMENSIONS = (
    ("rule_explanation", "rule_explanation_weight", "规则讲解"),
    ("script_pace", "script_pace_weight", "剧本节奏"),
    ("humor_comedy", "humor_comedy_weight", "幽默搞笑"),
    ("performance_immersion", "performance_immersion_weight", "演绎沉浸"),
    ("on_site_adaptability", "on_site_adaptability_weight", "控场应变"),
    ("service_attitude", "service_attitude_weight", "服务态度"),
)

WEEKDAYS = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}

HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>剧本杀门店 AI 运营系统</title>
<style>
:root{font-family:Inter,"Microsoft YaHei",sans-serif;color:#19353b;background:#f4f8f7}
*{box-sizing:border-box}body{margin:0}.top{background:#123f45;color:white;padding:22px 34px}
.top h1{margin:0 0 6px;font-size:24px}.top p{margin:0;color:#c9e5e1}
main{max-width:1220px;margin:24px auto;padding:0 20px}.toolbar,.panel{background:white;border:1px solid #dce9e6;border-radius:8px;padding:18px;margin-bottom:18px}
.toolbar{display:flex;gap:12px;align-items:end;flex-wrap:wrap}.field{display:flex;flex-direction:column;gap:7px;min-width:220px}
label{font-size:13px;color:#537075}select,button{height:40px;border:1px solid #b9d0cc;border-radius:6px;padding:0 13px;font-size:14px;background:white}
button{background:#0b9d9b;color:white;border-color:#0b9d9b;cursor:pointer;font-weight:600}button.secondary{background:#eef7f5;color:#16716e}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}.metric{background:white;border:1px solid #dce9e6;border-radius:8px;padding:16px}.metric b{display:block;font-size:26px;color:#0b8584;margin-top:8px}
.panel h2{font-size:17px;margin:0 0 14px}.muted{color:#6d8588;font-size:13px}.status{padding:10px 12px;border-radius:6px;background:#eef7f5;color:#176d6a;margin-bottom:12px;display:none}
.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;min-width:760px}th,td{text-align:left;padding:10px 9px;border-bottom:1px solid #edf2f1;font-size:13px;vertical-align:top}th{color:#557174;background:#f7fbfa;font-weight:600}
.tag{display:inline-block;padding:3px 7px;border-radius:12px;background:#eef7f5;color:#237976;font-size:12px}.tag.warn{background:#fff4df;color:#9b6916}.tag.bad{background:#ffeded;color:#a34545}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.empty{padding:24px;color:#71868a;text-align:center}
.rag-results{margin-top:12px}.rag-query{display:flex;gap:8px;margin:10px 0}.rag-query input{flex:1;min-width:180px;height:36px;padding:0 9px;border:1px solid #b9d0cc;border-radius:5px}.rag-card{border-top:1px solid #e7efed;padding:12px 0}.rag-meta{font-size:12px;color:#637b7d}.rag-chunk{background:#f6faf9;border-left:3px solid #0b9d9b;padding:9px;margin-top:7px;font-size:13px}.rag-fallback{padding:10px;background:#fff4df;color:#795817;border-radius:5px}
.review-select{height:32px;padding:0 6px;border:1px solid #b9d0cc;border-radius:5px}.review-input{width:180px;height:32px;padding:0 7px;border:1px solid #b9d0cc;border-radius:5px}.small-button{height:32px;padding:0 9px;font-size:12px}.operation-form{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;align-items:end}.operation-form .form-field{min-width:0}.operation-form .wide{grid-column:span 2}.operation-form input,.operation-form select{height:38px;width:100%;padding:0 9px;border:1px solid #b9d0cc;border-radius:6px;font-size:14px}.feedback-form{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;align-items:end}.feedback-form .form-field{min-width:0}.feedback-form .wide{grid-column:span 2}.feedback-form input,.feedback-form select,.feedback-form textarea{height:38px;width:100%;padding:0 9px;border:1px solid #b9d0cc;border-radius:6px;font-size:14px}.feedback-form textarea{height:76px;padding-top:9px;resize:vertical}.score-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:8px}.score-grid label{font-size:12px}.score-grid select{margin-top:5px}.operation-actions{display:flex;gap:6px;flex-wrap:wrap}
.modal-backdrop{position:fixed;inset:0;background:rgba(20,45,48,.45);display:none;align-items:center;justify-content:center;padding:20px;z-index:10}.modal-backdrop.open{display:flex}.modal{width:min(620px,100%);max-height:90vh;overflow:auto;background:white;border-radius:10px;padding:22px;box-shadow:0 18px 55px rgba(0,0,0,.2)}.modal-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.modal-head h2{margin:0;font-size:19px}.icon-button{width:34px;height:34px;padding:0;background:white;color:#537075;border-color:#d5e2df;font-size:20px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.form-field{display:flex;flex-direction:column;gap:6px}.form-field.full{grid-column:1/-1}.form-field input,.form-field select{height:38px;width:100%;padding:0 10px;border:1px solid #b9d0cc;border-radius:6px;font-size:14px}.modal-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:18px}.hint{font-size:12px;color:#71868a;line-height:1.5}.provider-status{font-size:12px;color:#537075;margin-left:auto}.danger-note{background:#fff7e6;color:#8b651f;border:1px solid #f1d89b;border-radius:6px;padding:10px;font-size:12px;line-height:1.5}
@media(max-width:800px){.metrics{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}.top{padding:18px 20px}}
@media(max-width:600px){.form-grid{grid-template-columns:1fr}.form-field.full{grid-column:auto}.provider-status{width:100%;margin-left:0}}
@media(max-width:900px){.operation-form,.feedback-form{grid-template-columns:repeat(2,1fr)}.operation-form .wide,.feedback-form .wide{grid-column:span 2}.score-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:600px){.operation-form,.feedback-form{grid-template-columns:1fr}.operation-form .wide,.feedback-form .wide{grid-column:auto}.score-grid{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<header class="top"><h1>剧本杀门店 AI 运营系统</h1><p>DM资源调度、玩家反馈分析与改进闭环 V1</p></header>
<main>
<section class="toolbar">
  <div class="field"><label for="request">选择玩家需求 / 场次</label><select id="request"></select></div>
  <button id="recommend">计算DM推荐</button>
  <button class="secondary" id="analyze">分析未处理评价</button>
  <button class="secondary" id="aggregate">聚合近30天问题</button>
  <button class="secondary" id="refresh">刷新数据</button>
  <button class="secondary" id="providerConfig">AI接口配置</button>
  <span class="provider-status" id="providerStatus">未配置大模型</span>
</section>
<div id="status" class="status"></div>
<section class="metrics">
  <div class="metric">DM总数<b id="dmCount">-</b></div>
  <div class="metric">待排场次<b id="pendingCount">-</b></div>
  <div class="metric">已收评价<b id="feedbackCount">-</b></div>
  <div class="metric">待处理改进<b id="improvementCount">-</b></div>
</section>
<section class="panel" id="recommendationPanel"><h2>DM推荐结果</h2><div class="muted" id="recommendationStatus">选择玩家需求后点击“计算DM推荐”，结果将在此处显示；店长保留最终确认权。</div><div class="table-wrap"><table><thead><tr><th>排名</th><th>DM</th><th>硬性条件</th><th>匹配分</th><th>可信度</th><th>最终分</th><th>推荐理由</th></tr></thead><tbody id="recommendations"><tr><td colspan="7" class="empty">尚未计算推荐</td></tr></tbody></table></div></section>
<section class="panel"><h2>场次执行台</h2><div class="muted">创建新场次后，先计算推荐，再点击“安排该DM”；场次结束后改为“已完成”，即可录入玩家评价。</div><form class="operation-form" id="sessionForm">
  <div class="form-field"><label for="sessionScript">剧本</label><select id="sessionScript" required></select></div>
  <div class="form-field"><label for="sessionDate">日期</label><input id="sessionDate" type="date" required></div>
  <div class="form-field"><label for="sessionTime">开场时间</label><input id="sessionTime" type="time" required></div>
  <div class="form-field"><label for="sessionPlayers">人数</label><input id="sessionPlayers" type="number" min="1" max="20" value="6" required></div>
  <div class="form-field"><label for="sessionRoom">房间</label><input id="sessionRoom" value="R001" required></div>
  <div class="form-field wide"><label for="sessionScenario">场次备注</label><input id="sessionScenario" value="新建场次"></div>
  <button type="submit">创建场次</button>
</form><div class="table-wrap" style="margin-top:16px"><table><thead><tr><th>场次</th><th>剧本</th><th>日期时间</th><th>房间</th><th>人数</th><th>状态</th><th>已安排DM</th><th>操作</th></tr></thead><tbody id="sessions"></tbody></table></div></section>
<section class="panel"><h2>玩家评价录入</h2><div class="muted">客服可将问卷内容录入这里。提交后会进入“AI评价人工复核”，再点击“分析未处理评价”。后续问卷平台可调用 POST /api/feedback 自动导入。</div><form class="feedback-form" id="feedbackForm">
  <div class="form-field"><label for="feedbackSession">已完成场次</label><select id="feedbackSession" required></select></div>
  <div class="form-field"><label for="feedbackDm">DM</label><select id="feedbackDm" required></select></div>
  <div class="form-field"><label for="feedbackPlayer">玩家编号</label><input id="feedbackPlayer" placeholder="例如 P013" required></div>
  <div class="form-field wide"><label>六维评价（1-5）</label><div class="score-grid" id="scoreGrid"></div></div>
  <div class="form-field wide"><label for="feedbackComment">具体反馈（可选）</label><textarea id="feedbackComment" placeholder="请描述具体问题或体验亮点"></textarea></div>
  <button type="submit">提交玩家评价</button>
</form></section>
<section class="panel"><h2>AI评价人工复核</h2><div class="muted">AI只提供初始判断。店长可以查看具体建议、修改问题等级、填写修正意见、确认或驳回。</div><div class="table-wrap"><table><thead><tr><th>评价</th><th>DM</th><th>问题维度</th><th>问题类型</th><th>原始证据</th><th>AI建议</th><th>AI等级</th><th>店长最终等级</th><th>复核意见</th><th>知识依据</th><th>操作</th></tr></thead><tbody id="reviews"></tbody></table></div></section>
<div id="ragResults" class="rag-results" aria-live="polite"></div>
<div class="grid">
<section class="panel"><h2>近期同类问题聚合</h2><div class="muted">同一DM、同一问题类型、近30天；高2次、中3次、低4次触发建议。</div><div class="table-wrap"><table><thead><tr><th>DM</th><th>维度</th><th>问题</th><th>次数</th><th>最终等级</th><th>具体建议</th><th>动作</th></tr></thead><tbody id="issues"></tbody></table></div></section>
<section class="panel"><h2>改进任务</h2><div class="muted">AI建议经店长复核后生成；点击“发送给DM”设置考核方式和日期，发送后立即进入执行中。</div><div class="table-wrap"><table><thead><tr><th>DM</th><th>问题</th><th>具体改进建议</th><th>优先级</th><th>触发规则</th><th>状态</th><th>考核方式 / 日期</th><th>考核结果 / 处理结果</th><th>操作</th></tr></thead><tbody id="improvements"></tbody></table></div></section>
</div>
</main>
<div class="modal-backdrop" id="improvementModal" role="dialog" aria-modal="true" aria-labelledby="improvementTitle"><div class="modal"><div class="modal-head"><h2 id="improvementTitle">发送改进任务给 DM</h2><button class="icon-button" id="closeImprovement" aria-label="关闭">×</button></div><div class="hint" id="improvementHint">发送后任务将直接进入“执行中”，不再等待 DM 另行确认。</div><div class="form-grid" style="margin-top:15px"><div class="form-field full"><label for="assessmentMethod">考核方式</label><select id="assessmentMethod"><option>规则讲解现场考核</option><option>剧本节奏情景题</option><option>幽默搞笑破冰演示</option><option>演绎沉浸现场演绎</option><option>控场应变模拟</option><option>服务态度情景演练</option></select></div><div class="form-field"><label for="assessmentDate">考核日期</label><input id="assessmentDate" type="datetime-local" required></div><div class="form-field"><label for="assessmentOwner">考核人</label><input id="assessmentOwner" value="店长" required></div><div class="form-field"><label for="sentBy">发送人</label><input id="sentBy" value="店长" required></div></div><div class="modal-actions"><button class="secondary" id="cancelImprovement">取消</button><button id="confirmImprovement">确认发送并开始执行</button></div></div></div>
<div class="modal-backdrop" id="providerModal" role="dialog" aria-modal="true" aria-labelledby="providerTitle">
  <div class="modal">
    <div class="modal-head"><h2 id="providerTitle">AI接口配置</h2><button class="icon-button" id="closeProvider" aria-label="关闭">×</button></div>
    <div class="danger-note">API Key 只会保存在当前本地服务进程的内存中，不写入数据库、CSV或浏览器存储。不要在聊天、截图或作品集中公开密钥。</div>
    <div class="form-grid" style="margin-top:15px">
      <div class="form-field"><label for="providerName">服务商/接口类型</label><select id="providerName">
        <option value="OpenAI">OpenAI 官方</option>
        <option value="OpenAI兼容中转站">OpenAI 兼容中转站</option>
        <option value="DeepSeek">DeepSeek</option>
        <option value="通义千问">通义千问</option>
        <option value="Moonshot">Moonshot</option>
        <option value="智谱">智谱</option>
        <option value="硅基流动">硅基流动</option>
        <option value="自定义">自定义</option>
      </select></div>
      <div class="form-field"><label for="wireApi">接口协议</label><select id="wireApi"><option value="chat_completions">Chat Completions</option><option value="responses">Responses</option></select></div>
      <div class="form-field full"><label for="baseUrl">API Base URL</label><input id="baseUrl" placeholder="例如：https://api.openai.com/v1"></div>
      <div class="form-field"><label for="apiModel">模型名称</label><input id="apiModel" placeholder="例如：gpt-5.5"></div>
      <div class="form-field"><label for="apiKey">API Key</label><input id="apiKey" type="password" autocomplete="off" placeholder="粘贴新生成的密钥"></div>
      <div class="form-field full"><div class="hint">预设只填写常见接口地址和示例模型，实际可用模型以服务商后台为准。使用中转站时请选择“OpenAI兼容中转站”，再填写其 Base URL。</div></div>
    </div>
    <div class="modal-actions"><button class="secondary" id="clearProvider">清除当前配置</button><button id="saveProvider">保存配置</button></div>
  </div>
</div>
<script>
const $=s=>document.querySelector(s);
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function tag(v){let cls=v==='通过'||v==='已完成'||v==='是'?'':' '+(v==='不通过'||v==='高'?'bad':'warn');return `<span class="tag${cls}">${esc(v)}</span>`}
function show(msg){const e=$('#status');e.textContent=msg;e.style.display='block';setTimeout(()=>e.style.display='none',4000)}
async function get(url){const r=await fetch(url);const d=await r.json();if(!r.ok)throw Error(d.error||'请求失败');return d}
async function load(){
  const d=await get('/api/dashboard'); $('#dmCount').textContent=d.metrics.dm;$('#pendingCount').textContent=d.metrics.pending;$('#feedbackCount').textContent=d.metrics.feedback;$('#improvementCount').textContent=d.metrics.improvements;
  const s=$('#request'); const old=s.value;s.innerHTML=d.requests.map(x=>`<option value="${esc(x.request_id)}">${esc(x.request_id)} · ${esc(x.scenario_name)} · ${esc(x.script_name)}</option>`).join('');if(old)s.value=old;
  renderScripts(d.scripts); renderSessions(d.sessions,d.dms); renderFeedbackOptions(d.sessions,d.dms); renderReviews(d.reviews,d.feedback_rows); renderImprovements(d.improvements);
  const aggregateResult=await get('/api/aggregate'); renderIssues(aggregateResult.groups);
}
function renderScripts(rows){$('#sessionScript').innerHTML=rows.map(x=>`<option value="${esc(x.script_id)}">${esc(x.script_name)}（${esc(x.script_type)}）</option>`).join('')}
function renderSessions(rows,dms){$('#sessions').innerHTML=rows.length?rows.map(x=>{const canStart=x.session_status==='已排班';const canFinish=x.session_status==='进行中';const canCancel=['待排班','已排班','进行中'].includes(x.session_status);return `<tr><td>${esc(x.session_id)}</td><td>${esc(x.script_name)}</td><td>${esc(x.session_date)} ${esc(x.session_time)}</td><td>${esc(x.room_id)}</td><td>${esc(x.player_count)}</td><td>${tag(x.session_status)}</td><td>${esc(x.assigned_dm_name||'未安排')}</td><td class="operation-actions">${x.session_status==='待排班'?'<button type="button" class="small-button session-action" data-action="recommend" data-id="'+esc(x.session_id)+'" data-request="'+esc(x.request_id||'')+'">生成推荐</button>':''}${canStart?'<button type="button" class="small-button session-action" data-action="start" data-id="'+esc(x.session_id)+'">开始</button>':''}${canFinish?'<button type="button" class="small-button session-action" data-action="finish" data-id="'+esc(x.session_id)+'">结束</button>':''}${canCancel?'<button type="button" class="small-button secondary session-action" data-action="cancel" data-id="'+esc(x.session_id)+'">取消场次</button>':''}</td></tr>`}).join(''):`<tr><td colspan="8" class="empty">暂无场次</td></tr>`}
function renderFeedbackOptions(sessions,dms){const done=sessions.filter(x=>['已完成','已结束'].includes(x.session_status));$('#feedbackSession').innerHTML=done.length?done.map(x=>`<option value="${esc(x.session_id)}">${esc(x.session_id)} · ${esc(x.script_name)} · ${esc(x.session_date)}</option>`).join(''):'<option value="">暂无已完成场次</option>';$('#feedbackDm').innerHTML=dms.map(x=>`<option value="${esc(x.dm_id)}">${esc(x.dm_id)} · ${esc(x.dm_name)}</option>`).join('')}
const scoreDims=[['rule_explanation_rating','规则讲解'],['script_pace_rating','剧本节奏'],['humor_comedy_rating','幽默搞笑'],['performance_immersion_rating','演绎沉浸'],['on_site_adaptability_rating','控场应变'],['service_attitude_rating','服务态度']];
function initScoreGrid(){$('#scoreGrid').innerHTML=scoreDims.map(([key,label])=>`<label>${label}<select id="score-${key}"><option>5</option><option>4</option><option>3</option><option>2</option><option>1</option></select></label>`).join('')}
function renderImprovements(rows){$("#improvements").innerHTML=rows.length?rows.map(x=>{const send=["待店长复核","待发送"].includes(x.status)?`<button type="button" class="small-button improvement-send" data-id="${esc(x.improvement_id)}">发送给DM</button>`:"";const assess=["执行中","待考核"].includes(x.status)?`<button type="button" class="small-button improvement-action" data-id="${esc(x.improvement_id)}">填写考核</button>`:"";return `<tr><td>${esc(x.dm_id)}</td><td>${esc(x.issue_type)}</td><td>${esc(x.improvement_action)}</td><td>${tag(x.priority)}</td><td>${esc(x.trigger_rule)}</td><td>${tag(x.status)}</td><td>${esc(x.assessment_method||"未设置")}<br>${esc(x.assessment_date||"未设置")}</td><td>${esc(x.assessment_result||"未考核")}<br>${esc(x.result_note||"")}</td><td>${send}${assess}</td></tr>`}).join(""):`<tr><td colspan="9" class="empty">暂无改进任务</td></tr>`}
function severitySelect(id,value){return `<select class="review-select" id="severity-${esc(id)}"><option ${value==='低'?'selected':''}>低</option><option ${value==='中'?'selected':''}>中</option><option ${value==='高'?'selected':''}>高</option></select>`}
function renderReviews(rows,feedbackRows){const feedbackById=Object.fromEntries(feedbackRows.map(x=>[x.feedback_id,x]));$("#reviews").innerHTML=rows.length?rows.map(x=>{const query=feedbackById[x.feedback_id]?.comment_text||x.evidence||x.issue_type;return `<tr><td>${esc(x.feedback_id)}</td><td>${esc(x.dm_id)}</td><td>${esc(x.issue_dimension)}</td><td>${esc(x.issue_type)}</td><td>${esc(x.evidence)}</td><td>${esc(x.suggestions)}</td><td>${tag(x.severity)}</td><td>${severitySelect(x.ai_result_id,x.manager_severity||x.severity)}</td><td><input class="review-input" id="correction-${esc(x.ai_result_id)}" value="${esc(x.manager_correction||"")}"></td><td><button type="button" class="small-button rag-action" data-query="${esc(query)}" data-feedback="${esc(x.feedback_id)}">检索依据</button></td><td><button type="button" class="small-button review-action" data-action="save" data-id="${esc(x.ai_result_id)}">保存</button><button type="button" class="small-button secondary review-action" data-action="reject" data-id="${esc(x.ai_result_id)}">驳回</button></td></tr>`}).join(""):`<tr><td colspan="11" class="empty">暂无AI分析结果</td></tr>`}
function renderIssues(rows){$('#issues').innerHTML=rows.length?rows.map(x=>`<tr><td>${esc(x.dm_id)}</td><td>${esc(x.issue_dimension)}</td><td>${esc(x.issue_type)}</td><td>${esc(x.count)}</td><td>${tag(x.manager_severity)}</td><td>${esc(x.suggestions)}</td><td>${tag(x.triggered?'生成建议':'继续观察')}</td></tr>`).join(''):`<tr><td colspan="7" class="empty">近30天没有识别到问题</td></tr>`}
async function saveReview(id){try{const severity=$('#severity-'+id).value;const correction=$('#correction-'+id).value;await post('/api/review',{ai_result_id:id,manager_severity:severity,manager_correction:correction,ai_status:'已确认'});show(`已保存 ${id} 的店长复核结果`);await load()}catch(e){show(`保存失败：${e.message}`)}}
async function rejectReview(id){try{const correction=$('#correction-'+id).value||'店长驳回该条AI分析';await post('/api/review',{ai_result_id:id,manager_severity:'',manager_correction:correction,ai_status:'已驳回'});show(`已驳回 ${id}，该结果不再参与聚合`);await load()}catch(e){show(`驳回失败：${e.message}`)}}
async function recommend(){const requestId=$('#request').value;if(!requestId){show('请先选择一条玩家需求或场次');return}const panel=$('#recommendationPanel');const status=$('#recommendationStatus');const body=$('#recommendations');body.innerHTML='<tr><td colspan="7" class="empty">正在计算推荐…</td></tr>';status.textContent=`正在计算需求 ${requestId} 的DM推荐`;try{const d=await get('/api/recommend?request_id='+encodeURIComponent(requestId));const eligible=d.results.filter(x=>x.hard_filter_result==='通过');body.innerHTML=d.results.map(x=>`<tr><td>${esc(x.rank)}</td><td>${esc(x.dm_name)}</td><td>${tag(x.hard_filter_result)}</td><td>${esc(x.match_score)}</td><td>${esc(x.review_credibility)}</td><td><b>${esc(x.final_recommendation_score)}</b></td><td>${esc(x.recommendation_reason)} ${x.hard_filter_result==='通过'?`<button type="button" class="small-button session-action" data-action="assign" data-id="${esc(x.session_id)}" data-dm="${esc(x.dm_id)}">安排该DM</button>`:''}</td></tr>`).join('')||'<tr><td colspan="7" class="empty">没有DM档案</td></tr>';status.textContent=eligible.length?`需求 ${d.request_id}：找到 ${eligible.length} 位符合硬性条件的DM，已按最终推荐分排序。`:`需求 ${d.request_id}：当前没有DM通过硬性筛选，请检查可用状态、出勤时间和可主持剧本。`;panel.scrollIntoView({behavior:'smooth',block:'start'});show(eligible.length?`推荐已生成：${eligible.length} 位DM符合条件`:'推荐已计算，但没有符合条件的DM')}catch(e){body.innerHTML='<tr><td colspan="7" class="empty">推荐计算失败</td></tr>';status.textContent=`推荐计算失败：${e.message}`;panel.scrollIntoView({behavior:'smooth',block:'start'});show(`推荐计算失败：${e.message}`)}}
async function createSession(event){event.preventDefault();try{const d=await post('/api/session',{script_id:$('#sessionScript').value,session_date:$('#sessionDate').value,session_time:$('#sessionTime').value,player_count:$('#sessionPlayers').value,room_id:$('#sessionRoom').value,scenario_name:$('#sessionScenario').value});show(`已创建场次 ${d.session_id}`);$('#sessionForm').reset();$('#sessionPlayers').value=6;$('#sessionRoom').value='R001';await load()}catch(e){show(`创建场次失败：${e.message}`)} }
async function sessionAction(action,id,dm,requestId){try{if(action==='recommend'){if(requestId){$('#request').value=requestId;await recommend()}else{show(`场次 ${id} 尚未建立玩家需求记录`)}return}const body={session_id:id,action};if(dm)body.dm_id=dm;const d=await post('/api/session',body);show(d.message);await load()}catch(e){show(`场次操作失败：${e.message}`)} }
async function submitFeedback(event){event.preventDefault();try{const body={session_id:$('#feedbackSession').value,dm_id:$('#feedbackDm').value,player_id:$('#feedbackPlayer').value,comment_text:$('#feedbackComment').value};for(const [key] of scoreDims)body[key]=$('#score-'+key).value;const d=await post('/api/feedback',body);show(`已录入玩家评价 ${d.feedback_id}`);$('#feedbackForm').reset();initScoreGrid();await load()}catch(e){show(`提交评价失败：${e.message}`)} }
async function analyze(){try{const d=await post('/api/analyze',{});show(`已分析 ${d.analyzed} 条评价，使用${d.mode==='llm'?'大模型':'本地规则兜底'}；请查看AI评价人工复核区域`);await load()}catch(e){show(`AI分析失败：${e.message}`)}}
async function aggregate(){const d=await get('/api/aggregate');renderIssues(d.groups);show(`已聚合 ${d.groups.length} 组近期同类问题`)}
async function saveImprovement(id){const method=prompt('考核方式：现场演绎 / 规则讲解 / 情景问答 / 控场模拟 / 服务情景演练');if(method===null)return;const date=prompt('考核日期，例如 2026-10-01 09:00');if(date===null)return;const result=prompt('考核结果：通过 / 失败 / 部分改善 / 无法判断');if(result===null)return;const note=prompt('店长或客服处理结果');if(note===null)return;const next=result==='通过'?'关闭任务':result==='失败'?'重新生成建议或安排培训':result==='部分改善'?'延长考核窗口':'补充考核';try{await post('/api/improvement',{improvement_id:id,assessment_method:method,assessment_date:date,assessment_result:result,result_note:note,next_action:next,status:result==='通过'?'考核通过':result==='失败'?'考核失败':'待考核'});show('已保存 '+id+' 的现场考核结果');await load()}catch(e){show('保存考核失败：'+e.message)}}
async function post(url,body){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.error||'请求失败');return d}
const providerPresets={
  'OpenAI':{base_url:'https://api.openai.com/v1',model:'gpt-4o-mini',wire_api:'chat_completions'},
  'OpenAI兼容中转站':{base_url:'https://codex.aigo0.com/v1',model:'gpt-5.5',wire_api:'responses'},
  'DeepSeek':{base_url:'https://api.deepseek.com/v1',model:'deepseek-chat',wire_api:'chat_completions'},
  '通义千问':{base_url:'https://dashscope.aliyuncs.com/compatible-mode/v1',model:'qwen-plus',wire_api:'chat_completions'},
  'Moonshot':{base_url:'https://api.moonshot.cn/v1',model:'moonshot-v1-8k',wire_api:'chat_completions'},
  '智谱':{base_url:'https://open.bigmodel.cn/api/paas/v4',model:'glm-4-flash',wire_api:'chat_completions'},
  '硅基流动':{base_url:'https://api.siliconflow.cn/v1',model:'deepseek-ai/DeepSeek-V3',wire_api:'chat_completions'},
  '自定义':{base_url:'',model:'',wire_api:'chat_completions'}
};
function setProviderStatus(d){$('#providerStatus').textContent=d.configured?`已配置：${d.provider||'自定义'} / ${d.model}`:'未配置大模型'}
async function loadProvider(){const d=await get('/api/provider');setProviderStatus(d);return d}
function openProvider(){const p=$('#providerName').value;const preset=providerPresets[p]||providerPresets['自定义'];$('#baseUrl').value=preset.base_url;$('#apiModel').value=preset.model;$('#wireApi').value=preset.wire_api;$('#apiKey').value='';$('#providerModal').classList.add('open')}
$('#providerName').onchange=()=>{const p=providerPresets[$('#providerName').value]||providerPresets['自定义'];$('#baseUrl').value=p.base_url;$('#apiModel').value=p.model;$('#wireApi').value=p.wire_api}
$('#providerConfig').onclick=openProvider;$('#closeProvider').onclick=()=>$('#providerModal').classList.remove('open');$('#providerModal').onclick=e=>{if(e.target.id==='providerModal')$('#providerModal').classList.remove('open')}
$('#clearProvider').onclick=async()=>{try{const d=await post('/api/provider',{clear:true});setProviderStatus(d);$('#providerModal').classList.remove('open');show('已清除当前大模型配置')}catch(e){show(`清除失败：${e.message}`)}}
$('#saveProvider').onclick=async()=>{try{const d=await post('/api/provider',{provider:$('#providerName').value,base_url:$('#baseUrl').value,model:$('#apiModel').value,api_key:$('#apiKey').value,wire_api:$('#wireApi').value});setProviderStatus(d);$('#providerModal').classList.remove('open');show('大模型配置已保存，可点击“分析未处理评价”验证调用')}catch(e){show(`保存失败：${e.message}`)}}
document.addEventListener('click',event=>{const button=event.target.closest('.rag-action');if(!button)return;runRag(button.dataset.feedback,button.dataset.query)});
async function runRag(feedbackId,query){const panel=$('#ragResults');panel.innerHTML=`<h3>${esc(feedbackId)} · 运营知识依据</h3><div class="rag-query"><input id="ragQuery" value="${esc(query)}" aria-label="检索问题"><button id="ragSearch">重新检索</button></div><div id="ragMeta" class="muted">混合检索配置加载中；相关度分仅用于排序，不是概率；无足够依据时降级人工处理。</div><div id="ragOutput" class="rag-fallback">检索中...</div>`;panel.scrollIntoView({behavior:'smooth',block:'start'});window.setTimeout(()=>panel.scrollIntoView({behavior:'smooth',block:'start'}),120);document.getElementById('ragQuery').focus();document.getElementById('ragSearch').onclick=()=>runRag(feedbackId,document.getElementById('ragQuery').value);try{const d=await get('/api/rag?query='+encodeURIComponent(query)+'&top_k=2');const out=document.getElementById('ragOutput');out.innerHTML=d.grounded&&d.results.length?d.results.map(x=>`<article class="rag-card"><div class="rag-meta">${esc(x.source)} · ${esc(x.section)} · ${esc(x.chunk_id)} · 相关度 ${esc(x.relevance_score)} · 覆盖 ${esc(x.query_coverage)}</div><div class="rag-chunk">${esc(x.content)}</div><div class="rag-meta">引用：${esc(x.citation)}</div></article>`).join('')+`<div class="rag-meta">操作建议需店长复核：${esc(d.guidance||'')}</div>`:`<div class="rag-fallback">${esc(d.fallback||'正向反馈，不生成负向纠偏建议')}</div>`;panel.scrollIntoView({behavior:'smooth',block:'start'});window.setTimeout(()=>panel.scrollIntoView({behavior:'smooth',block:'start'}),120);document.getElementById('ragQuery').focus()}catch(e){document.getElementById('ragOutput').textContent='检索失败：'+e.message}}
document.addEventListener('click',event=>{const button=event.target.closest('.review-action,.session-action');if(!button)return;const id=button.dataset.id;const action=button.dataset.action;if(button.classList.contains('review-action')){if(action==='save')saveReview(id);if(action==='reject')rejectReview(id)}else{sessionAction(action,id,button.dataset.dm,button.dataset.request)}});
document.addEventListener('click',event=>{const button=event.target.closest('.improvement-action,.improvement-send');if(!button)return;if(button.classList.contains('improvement-send'))openImprovementModal(button.dataset.id);else saveImprovement(button.dataset.id)});
let pendingImprovementId='';
function openImprovementModal(id){pendingImprovementId=id;const d=new Date();d.setDate(d.getDate()+1);const pad=n=>String(n).padStart(2,'0');document.getElementById('assessmentDate').value=d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+'T09:00';document.getElementById('improvementModal').classList.add('open')}
function closeImprovementModal(){document.getElementById('improvementModal').classList.remove('open');pendingImprovementId=''}
async function sendImprovement(){if(!pendingImprovementId)return;const method=document.getElementById('assessmentMethod').value;const date=document.getElementById('assessmentDate').value;const owner=document.getElementById('assessmentOwner').value.trim();const sentBy=document.getElementById('sentBy').value.trim();if(!date||!owner||!sentBy){show('请完整填写考核日期、考核人和发送人');return}try{await post('/api/improvement',{improvement_id:pendingImprovementId,status:'执行中',assessment_method:method,assessment_date:date,assessment_owner:owner,sent_by:sentBy});closeImprovementModal();show('已发送给DM，任务已进入执行中');await load()}catch(e){show('发送失败：'+e.message)}}
document.getElementById('closeImprovement').onclick=closeImprovementModal;document.getElementById('cancelImprovement').onclick=closeImprovementModal;document.getElementById('confirmImprovement').onclick=sendImprovement;document.getElementById('improvementModal').onclick=e=>{if(e.target.id==='improvementModal')closeImprovementModal()};
$('#sessionForm').addEventListener('submit',createSession);$('#feedbackForm').addEventListener('submit',submitFeedback);initScoreGrid();$('#recommend').onclick=()=>recommend().catch(e=>show(e.message));$('#analyze').onclick=()=>analyze();$('#aggregate').onclick=()=>aggregate().catch(e=>show(e.message));$('#refresh').onclick=()=>load().catch(e=>show(e.message));$('#request').onchange=()=>recommend().catch(e=>show(e.message));load().then(loadProvider).catch(e=>show(e.message));
</script>
</body></html>"""


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def import_csv_table(conn: sqlite3.Connection, table: str, filename: str) -> None:
    path = BASE_DIR / filename
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fields = reader.fieldnames or []
        if not fields:
            return
        columns = ", ".join(f"{quote_identifier(field)} TEXT" for field in fields)
        conn.execute(f"DROP TABLE IF EXISTS {quote_identifier(table)}")
        conn.execute(f"CREATE TABLE {quote_identifier(table)} ({columns})")
        placeholders = ", ".join("?" for _ in fields)
        sql = f"INSERT INTO {quote_identifier(table)} ({', '.join(quote_identifier(x) for x in fields)}) VALUES ({placeholders})"
        conn.executemany(sql, ([row.get(field, "") for field in fields] for row in reader))


def init_db() -> None:
    conn = db_connect()
    existing_tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    # SQLite is the runtime source of truth; CSV files bootstrap only a new database.
    if not set(CSV_TABLES).issubset(existing_tables):
        for table, filename in CSV_TABLES.items():
            import_csv_table(conn, table, filename)
    improvement_columns = {row[1] for row in conn.execute("PRAGMA table_info(improvements)")}
    for column in (
        ("assessment_owner", "TEXT"),
        ("assessment_method", "TEXT"),
        ("assessment_date", "TEXT"),
        ("assessment_result", "TEXT"),
        ("next_action", "TEXT"),
    ):
        if column[0] not in improvement_columns:
            conn.execute(f'ALTER TABLE improvements ADD COLUMN "{column[0]}" {column[1]}')
    requirement_columns = {row[1] for row in conn.execute("PRAGMA table_info(player_requirements)")}
    if "session_id" not in requirement_columns:
        conn.execute('ALTER TABLE player_requirements ADD COLUMN "session_id" TEXT')
        conn.execute("UPDATE player_requirements SET session_id=(SELECT session_id FROM sessions s WHERE s.script_name=player_requirements.script_name AND s.session_date=player_requirements.session_date AND s.session_time=player_requirements.session_time ORDER BY s.session_id LIMIT 1) WHERE COALESCE(session_id,'')=''")
    refresh_dm_scores(conn)
    conn.commit()
    conn.close()


def rows(conn: sqlite3.Connection, table: str) -> list[dict[str, str]]:
    return [dict(row) for row in conn.execute(f"SELECT * FROM {quote_identifier(table)}").fetchall()]


def append_csv_row(table: str, row: dict[str, object]) -> None:
    """兼容旧调用；运行时数据只写 SQLite，CSV 仅作为导入/导出格式。"""
    return None


def update_csv_row(table: str, key_field: str, key_value: str, updates: dict[str, object]) -> None:
    """兼容旧调用；运行时更新由 SQLite 事务完成。"""
    return None


def next_identifier(conn: sqlite3.Connection, table: str, field: str, prefix: str) -> str:
    values = [str(item.get(field, "")) for item in rows(conn, table)]
    numbers = []
    for value in values:
        match = re.search(r"(\d+)$", value)
        if match:
            numbers.append(int(match.group(1)))
    candidate = max(numbers, default=0) + 1
    existing = set(values)
    while f"{prefix}{candidate:03d}" in existing:
        candidate += 1
    return f"{prefix}{candidate:03d}"


def session_request_map(conn: sqlite3.Connection) -> dict[str, str]:
    requests = rows(conn, "player_requirements")
    sessions = rows(conn, "sessions")
    mapping = {}
    # Prefer direct session linkage; tuple matching remains for legacy rows.
    for session in sessions:
        match = next((item for item in requests if item.get("script_name") == session.get("script_name")
                      and item.get("session_date") == session.get("session_date")
                      and item.get("session_time") == session.get("session_time")), None)
        if match:
            mapping[session["session_id"]] = match["request_id"]
    return mapping


def session_rows(conn: sqlite3.Connection) -> list[dict[str, str]]:
    mapping = session_request_map(conn)
    return [{**item, "request_id": mapping.get(item.get("session_id", ""), "")} for item in rows(conn, "sessions")]


def split_values(value: str) -> set[str]:
    return {x.strip() for x in value.replace("，", ",").split(",") if x.strip()}


def number(value: str, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return fallback


def time_minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def in_slots(target: str, slots: str) -> bool:
    try:
        target_num = time_minutes(target)
    except ValueError:
        return False
    for slot in split_values(slots):
        try:
            start, end = slot.split("-")
            if time_minutes(start) <= target_num <= time_minutes(end):
                return True
        except ValueError:
            continue
    return False


def date_available(date: str, days: str) -> bool:
    try:
        weekday = WEEKDAYS[datetime.strptime(date, "%Y-%m-%d").weekday()]
    except ValueError:
        return False
    return weekday in split_values(days)


def credibility(dm: dict[str, str]) -> float:
    count = number(dm.get("total_review_count"))
    k = max(number(dm.get("smoothing_k"), 5), 0)
    if count <= 0:
        return 0.75
    return 0.75 + 0.25 * count / (count + k)


def refresh_dm_scores(conn: sqlite3.Connection) -> None:
    """用评价表刷新六维档案分数；无评价DM保留默认分和0.75可信度规则。"""
    feedback = rows(conn, "feedback")
    dms = rows(conn, "dm_profiles")
    cutoff = datetime.now() - timedelta(days=30)
    score_fields = (
        "rule_explanation",
        "script_pace",
        "humor_comedy",
        "performance_immersion",
        "on_site_adaptability",
        "service_attitude",
    )
    rating_fields = tuple(f"{field}_rating" for field in score_fields)
    for dm in dms:
        own = [item for item in feedback if item.get("dm_id") == dm.get("dm_id")]
        total_reviews = len(own)
        recent_reviews = 0
        for item in own:
            try:
                if datetime.strptime(item.get("submitted_at", ""), "%Y-%m-%d %H:%M") >= cutoff:
                    recent_reviews += 1
            except ValueError:
                continue
        default_score = number(dm.get("default_score"), 3.8)
        k = max(number(dm.get("smoothing_k"), 5), 0)
        updates: dict[str, str] = {
            "total_review_count": str(total_reviews),
            "last_30d_review_count": str(recent_reviews),
        }
        for score_field, rating_field in zip(score_fields, rating_fields):
            values = [number(item.get(rating_field)) for item in own if number(item.get(rating_field)) > 0]
            count = len(values)
            refreshed = (sum(values) + default_score * k) / (count + k) if count + k else default_score
            updates[score_field] = f"{refreshed:.4f}"
        set_clause = ", ".join(f"{quote_identifier(key)}=?" for key in updates)
        conn.execute(
            f"UPDATE dm_profiles SET {set_clause} WHERE dm_id=?",
            [*updates.values(), dm["dm_id"]],
        )


def existing_conflict(dm_id: str, date: str, time: str, sessions: list[dict[str, str]]) -> bool:
    return any(
        s.get("assigned_dm_id") == dm_id
        and s.get("session_date") == date
        and s.get("session_time") == time
        and s.get("session_status") not in {"已取消", "已完成", "已结束", ""}
        for s in sessions
    )


def recommend(request_id: str) -> list[dict[str, str]]:
    conn = db_connect()
    requests, sessions, dms = rows(conn, "player_requirements"), rows(conn, "sessions"), rows(conn, "dm_profiles")
    conn.close()
    request = next((x for x in requests if x["request_id"] == request_id), None)
    if not request:
        raise ValueError(f"找不到需求 {request_id}")
    session = next((x for x in sessions if x.get("session_id") == request.get("session_id")), None)
    if not session:
        session = next(
            (x for x in sessions if x["script_name"] == request["script_name"]
             and x["session_date"] == request["session_date"]
             and x["session_time"] == request["session_time"]),
            None,
        )
    if not session:
        raise ValueError("找不到与需求对应的场次")
    if session.get("session_status") == "已取消":
        raise ValueError("已取消场次不能生成DM推荐")
    result = []
    for dm in dms:
        reasons = []
        if dm.get("available_status") != "可用":
            reasons.append("当前不可用")
        if not date_available(session["session_date"], dm.get("available_days", "")):
            reasons.append("日期不可出勤")
        if not in_slots(session["session_time"], dm.get("available_time_slots", "")):
            reasons.append("时间段不可用")
        if session["script_name"] not in split_values(dm.get("hostable_scripts", "")):
            reasons.append("未登记可主持该剧本")
        if existing_conflict(dm["dm_id"], session["session_date"], session["session_time"], sessions):
            reasons.append("存在场次冲突")
        match = sum(number(dm.get(d_field)) * number(request.get(w_field)) for d_field, w_field, _ in DIMENSIONS)
        conf = credibility(dm)
        final = match * conf
        dims = sorted(
            ((label, number(dm.get(d_field)) * number(request.get(w_field))) for d_field, w_field, label in DIMENSIONS),
            key=lambda x: x[1],
            reverse=True,
        )
        reason = f"通过硬性筛选；{dims[0][0]}、{dims[1][0]}对本场贡献较高" if not reasons else "未进入正常推荐：" + "、".join(reasons)
        result.append({
            "rank": "", "dm_id": dm["dm_id"], "dm_name": dm["dm_name"],
            "session_id": session["session_id"],
            "hard_filter_result": "通过" if not reasons else "不通过",
            "match_score": f"{match:.4f}", "review_credibility": f"{conf:.4f}",
            "final_recommendation_score": f"{final:.4f}", "recommendation_reason": reason,
        })
    passed = sorted((x for x in result if x["hard_filter_result"] == "通过"), key=lambda x: number(x["final_recommendation_score"]), reverse=True)
    for index, item in enumerate(passed, 1):
        item["rank"] = str(index)
    result.sort(key=lambda x: (x["hard_filter_result"] != "通过", int(x["rank"] or 999)))
    for index, item in enumerate(result, 1):
        item["rank"] = item["rank"] or f"未入选-{index}"
    return result


def local_analyze(text: str) -> dict[str, str] | None:
    rules = [
        (("规则", "听不清", "没听清", "重复提问", "解释"), "规则讲解", "规则讲解不充分", "中", "规则讲解后主动确认玩家是否理解；关键规则增加示例"),
        (("节奏", "等待", "推进慢", "拖", "停顿"), "剧本节奏", "中段推进偏慢", "低", "设置阶段时间提醒；减少非必要停顿并记录各阶段耗时"),
        (("幽默", "搞笑", "互动少", "气氛"), "幽默搞笑", "前半段互动不足", "中", "增加开场破冰；在不影响剧情的前提下加入轻量互动"),
        (("出戏", "沉浸", "演绎", "代入"), "演绎沉浸", "演绎沉浸感不足", "低", "加强角色语气和情绪衔接；减少与剧情无关的打断"),
        (("控场", "临时", "混乱", "提问"), "控场应变", "现场应变不足", "中", "提前准备突发情况话术；集中处理重复问题并确认玩家理解"),
        (("服务", "态度", "冷淡", "耐心"), "服务态度", "服务沟通体验不足", "中", "保持主动沟通；在关键节点主动确认玩家体验"),
    ]
    for keywords, dimension, issue, severity, suggestions in rules:
        if any(word in text for word in keywords):
            if any(word in text for word in ("多次", "严重", "投诉", "没有及时", "歧视", "安全")):
                severity = "高"
            return {"issue_dimension": dimension, "issue_type": issue, "evidence": text[:160], "severity": severity, "suggestions": suggestions}
    return None


def normalize_analysis(parsed: dict[str, object], text: str) -> dict[str, str]:
    severity = str(parsed.get("severity", "低"))
    if severity not in {"低", "中", "高"}:
        severity = "低"
    suggestions = parsed.get("suggestions", "")
    if isinstance(suggestions, list):
        suggestions = "；".join(str(item) for item in suggestions)
    return {
        "issue_dimension": str(parsed.get("issue_dimension", "未分类")),
        "issue_type": str(parsed.get("issue_type", "")),
        "evidence": str(parsed.get("evidence", text[:160])),
        "severity": severity,
        "suggestions": str(suggestions or "请结合原始反馈进行针对性复盘"),
    }


def llm_analyze(text: str) -> dict[str, str] | None:
    config = PROVIDER_CONFIG
    api_key = config.get("api_key", "")
    if not api_key:
        return None
    base_url = str(config.get("base_url") or "").rstrip("/")
    model = str(config.get("model") or "")
    wire_api = config.get("wire_api", "chat_completions")
    system_prompt = "你是剧本杀门店运营分析助手。只输出JSON，字段为issue_dimension,issue_type,evidence,severity,suggestions。严重程度只能是低、中、高。没有具体问题时输出空issue_type。"
    user_prompt = f"请分析这条玩家评价：{text}"
    if wire_api == "responses":
        endpoint = f"{base_url}/responses"
        payload = {
            "model": model,
            "temperature": 0,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
    else:
        endpoint = f"{base_url}/chat/completions"
        payload = {
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        if wire_api == "responses":
            content = data.get("output_text", "")
            if not content:
                for item in data.get("output", []):
                    for part in item.get("content", []):
                        if part.get("type") in {"output_text", "text"}:
                            content += part.get("text", "")
        else:
            content = data["choices"][0]["message"]["content"]
        return normalize_analysis(json.loads(content), text)
    except Exception:
        return None


def analyze_unprocessed_feedback() -> tuple[int, str]:
    conn = db_connect()
    feedback = rows(conn, "feedback")
    existing = {item["feedback_id"]: item for item in rows(conn, "ai_feedback")}
    analyzed = 0
    used_llm = False
    for item in feedback:
        previous = existing.get(item["feedback_id"])
        if previous and previous.get("ai_status") != "已驳回":
            continue
        text = item.get("comment_text", "").strip()
        if not text:
            continue
        parsed = llm_analyze(text)
        if parsed:
            used_llm = True
        else:
            parsed = local_analyze(text)
        if not parsed or not parsed.get("issue_type"):
            continue
        parsed = normalize_analysis(parsed, text)
        fields = {
            "feedback_id": item["feedback_id"],
            "dm_id": item["dm_id"],
            "issue_dimension": parsed.get("issue_dimension", "未分类"),
            "issue_type": parsed.get("issue_type", ""),
            "evidence": parsed.get("evidence", text[:160]),
            "severity": parsed.get("severity", "低"),
            "suggestions": parsed.get("suggestions", "请结合原始反馈进行针对性复盘"),
            "ai_status": "待确认",
            "manager_correction": "",
            "review_window_days": "30",
            "same_issue_count": "1",
            "manager_severity": "",
            "triggered_recommendation": "否",
            "sent_to_dm": "否",
            "sent_at": "",
        }
        if previous:
            conn.execute(
                "UPDATE ai_feedback SET feedback_id=?, dm_id=?, issue_dimension=?, issue_type=?, evidence=?, "
                "severity=?, suggestions=?, ai_status=?, manager_correction=?, review_window_days=?, "
                "same_issue_count=?, manager_severity=?, triggered_recommendation=?, sent_to_dm=?, sent_at=? "
                "WHERE ai_result_id=?",
                (*fields.values(), previous["ai_result_id"]),
            )
        else:
            next_id = f"AI-AUTO-{len(existing) + analyzed + 1:03d}"
            conn.execute(
                "INSERT INTO ai_feedback "
                "(ai_result_id,feedback_id,dm_id,issue_dimension,issue_type,evidence,severity,suggestions,"
                "ai_status,manager_correction,review_window_days,same_issue_count,manager_severity,"
                "triggered_recommendation,sent_to_dm,sent_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (next_id, *fields.values()),
            )
        analyzed += 1
    conn.commit()
    conn.close()
    return analyzed, ("llm" if used_llm else "local")


def aggregate_issues() -> list[dict[str, str]]:
    conn = db_connect()
    feedback = rows(conn, "feedback")
    existing = {x["feedback_id"]: x for x in rows(conn, "ai_feedback")}
    conn.close()
    cutoff = datetime.now() - timedelta(days=30)
    groups: dict[tuple[str, str], dict[str, object]] = defaultdict(
        lambda: {"severity_counts": {"高": 0, "中": 0, "低": 0}, "evidence": [], "suggestions": []}
    )
    for item in feedback:
        try:
            submitted = datetime.strptime(item["submitted_at"], "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        if submitted < cutoff:
            continue
        text = item.get("comment_text", "")
        analysis = existing.get(item["feedback_id"])
        # Only manager-confirmed analyses may create or influence improvement tasks.
        # Pending analyses must wait for review; rejected analyses must never be reclassified here.
        if not analysis or analysis.get("ai_status") != "已确认":
            continue
        severity = analysis.get("manager_severity") or analysis.get("severity", "低")
        issue_type = analysis.get("issue_type", "").strip()
        if severity not in {"高", "中", "低"} or not issue_type:
            continue
        key = (item["dm_id"], issue_type)
        groups[key]["issue_dimension"] = analysis.get("issue_dimension", "未分类")
        groups[key]["severity_counts"][severity] += 1
        groups[key]["evidence"].append(analysis.get("evidence", text))
        suggestion = analysis.get("suggestions", "")
        if suggestion and suggestion not in groups[key]["suggestions"]:
            groups[key]["suggestions"].append(suggestion)
    output = []
    for (dm_id, issue_type), data in groups.items():
        severity_counts = data["severity_counts"]
        count = sum(severity_counts.values())
        trigger_severity = next(
            (level for level, threshold in (("高", 2), ("中", 3), ("低", 4))
             if severity_counts[level] >= threshold),
            "",
        )
        trigger_count = {"高": 2, "中": 3, "低": 4}.get(trigger_severity, 0)
        final_severity = next((level for level in ("高", "中", "低") if severity_counts[level]), "低")
        triggered = bool(trigger_severity)
        output.append({
            "dm_id": dm_id, "issue_dimension": str(data["issue_dimension"]), "issue_type": issue_type,
            "count": str(count), "manager_severity": final_severity,
            "severity_counts": severity_counts,
            "trigger_severity": trigger_severity,
            "trigger_count": str(trigger_count),
            "suggestions": "；".join(data["suggestions"]), "triggered": triggered,
        })
    conn = db_connect()
    existing_tasks = rows(conn, "improvements")
    for item in output:
        if not item["triggered"]:
            continue
        duplicate = any(
            task.get("dm_id") == item["dm_id"]
            and task.get("issue_type") == item["issue_type"]
            and task.get("status") != "已完成"
            for task in existing_tasks
        )
        if duplicate:
            continue
        trigger_severity = item["trigger_severity"]
        priority = "高" if trigger_severity == "高" else ("中" if trigger_severity == "中" else "低")
        trigger_rule = f"{trigger_severity}严重度累计{item['trigger_count']}次（近30天同DM同类问题）"
        next_id = f"IMP-AUTO-{len(existing_tasks) + 1:03d}"
        conn.execute(
            "INSERT INTO improvements "
            "(improvement_id,dm_id,issue_dimension,issue_type,source_review_count,priority,action_owner,"
            "improvement_action,review_period,status,result_note,trigger_rule,manager_reviewed,sent_by,sent_at,"
            "acknowledged_at,follow_up_session_count,assessment_owner,assessment_method,assessment_date,assessment_result,next_action) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                next_id, item["dm_id"], item["issue_dimension"], item["issue_type"], item["count"],
                priority, item["dm_id"], item["suggestions"] or f"针对{item['issue_type']}制定训练和复盘动作",
                "现场考核待设置", "待店长复核", "由近30天同类问题聚合自动生成", trigger_rule,
                "待复核", "", "", "", "0", "", "", "", "", "",
            ),
        )
        existing_tasks.append({
            "dm_id": item["dm_id"], "issue_type": item["issue_type"], "status": "待店长复核",
        })
    conn.commit()
    conn.close()
    return sorted(output, key=lambda x: (x["triggered"] is False, x["dm_id"], x["issue_type"]))


def json_response(handler: BaseHTTPRequestHandler, payload: object, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path in {"/", "/index.html"}:
                body = HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            query = parse_qs(parsed.query)
            conn = db_connect()
            if parsed.path == "/api/dashboard":
                payload = {
                    "metrics": {
                        "dm": conn.execute("SELECT COUNT(*) FROM dm_profiles").fetchone()[0],
                        "pending": conn.execute("SELECT COUNT(*) FROM sessions WHERE session_status='待排班'").fetchone()[0],
                        "feedback": conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0],
                        "improvements": conn.execute("SELECT COUNT(*) FROM improvements WHERE status!='已完成'").fetchone()[0],
                    },
                    "requests": rows(conn, "player_requirements"),
                    "scripts": rows(conn, "script_catalog"),
                    "sessions": session_rows(conn),
                    "dms": rows(conn, "dm_profiles"),
                    "reviews": rows(conn, "ai_feedback"),
                    "feedback_rows": rows(conn, "feedback"),
                    "improvements": rows(conn, "improvements"),
                }
                conn.close()
                json_response(self, payload)
                return
            if parsed.path == "/api/provider":
                json_response(self, {
                    "configured": bool(PROVIDER_CONFIG.get("api_key")),
                    "provider": PROVIDER_CONFIG.get("provider", ""),
                    "model": PROVIDER_CONFIG.get("model", ""),
                    "wire_api": PROVIDER_CONFIG.get("wire_api", "chat_completions"),
                })
                conn.close()
                return
            if parsed.path == "/api/recommend":
                request_id = query.get("request_id", [""])[0]
                try:
                    result = recommend(request_id)
                except ValueError as exc:
                    conn.close()
                    json_response(self, {"error": str(exc)}, 400)
                    return
                json_response(self, {"request_id": request_id, "results": result})
                return
            if parsed.path == "/api/rag":
                rag_query = query.get("query", [""])[0]
                if not rag_query.strip():
                    conn.close()
                    json_response(self, {"error": "query不能为空"}, 400)
                    return
                try:
                    top_k = int(query.get("top_k", ["2"])[0])
                    result = query_knowledge(rag_query, top_k=top_k)
                except (TypeError, ValueError) as exc:
                    conn.close()
                    json_response(self, {"error": str(exc)}, 400)
                    return
                result["guidance"] = "；".join(item["content"] for item in result["results"][:2])
                conn.close()
                json_response(self, result)
                return
            if parsed.path == "/api/aggregate":
                json_response(self, {"groups": aggregate_issues()})
                return
            if parsed.path == "/api/export":
                payload = {}
                for table in CSV_TABLES:
                    payload[table] = rows(conn, table)
                conn.close()
                json_response(self, payload)
                return
            if parsed.path == "/api/storage":
                payload = {
                    "primary_storage": "SQLite",
                    "database_file": str(DB_FILE),
                    "csv_role": "bootstrap_and_backup_only",
                    "tables": sorted(CSV_TABLES.keys()),
                    "note": "运行时新增和修改的数据保存在 SQLite；CSV 文件只作为初始导入和人工备份格式。",
                }
                conn.close()
                json_response(self, payload)
                return
            conn.close()
            json_response(self, {"error": "Not Found"}, 404)
        except Exception as exc:
            json_response(self, {"error": str(exc)}, 500)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            if parsed.path == "/api/analyze":
                analyzed, mode = analyze_unprocessed_feedback()
                json_response(self, {"ok": True, "analyzed": analyzed, "mode": mode})
                return
            if parsed.path == "/api/session":
                conn = db_connect()
                action = str(body.get("action", "create")).strip()
                if action == "create":
                    script_id = str(body.get("script_id", "")).strip()
                    script = conn.execute("SELECT * FROM script_catalog WHERE script_id=?", (script_id,)).fetchone()
                    if not script:
                        conn.close()
                        json_response(self, {"error": "找不到所选剧本"}, 400)
                        return
                    date = str(body.get("session_date", "")).strip()
                    time = str(body.get("session_time", "")).strip()
                    room = str(body.get("room_id", "")).strip()
                    players = str(body.get("player_count", "")).strip()
                    if not date or not time or not room or not players:
                        conn.close()
                        json_response(self, {"error": "日期、时间、人数和房间不能为空"}, 400)
                        return
                    session_id = next_identifier(conn, "sessions", "session_id", "SES")
                    session = {
                        "session_id": session_id, "script_id": script["script_id"], "script_name": script["script_name"],
                        "script_type": script["script_type"], "session_date": date, "session_time": time,
                        "player_count": players, "room_id": room, "required_equipment": script["required_equipment"],
                        "session_status": "待排班", "assigned_dm_id": "", "assigned_dm_name": "",
                    }
                    fields = ",".join(quote_identifier(key) for key in session)
                    marks = ",".join("?" for _ in session)
                    conn.execute(f"INSERT INTO sessions ({fields}) VALUES ({marks})", list(session.values()))
                    request_id = next_identifier(conn, "player_requirements", "request_id", "REQ")
                    request = {
                        "request_id": request_id, "session_id": session_id, "scenario_name": str(body.get("scenario_name", "新建场次")).strip() or "新建场次",
                        "script_name": script["script_name"], "session_date": date, "session_time": time,
                        "player_count": players, "player_type": "偏好不明确", "rule_explanation_weight": "0.17",
                        "script_pace_weight": "0.17", "humor_comedy_weight": "0.16", "performance_immersion_weight": "0.17",
                        "on_site_adaptability_weight": "0.16", "service_attitude_weight": "0.17", "total_weight": "1.00",
                        "priority_note": "新建场次默认均衡权重",
                    }
                    fields = ",".join(quote_identifier(key) for key in request)
                    marks = ",".join("?" for _ in request)
                    conn.execute(f"INSERT INTO player_requirements ({fields}) VALUES ({marks})", list(request.values()))
                    conn.commit(); conn.close(); append_csv_row("sessions", session); append_csv_row("player_requirements", request)
                    json_response(self, {"ok": True, "session_id": session_id, "request_id": request_id})
                    return
                session_id = str(body.get("session_id", "")).strip()
                if not session_id:
                    conn.close(); json_response(self, {"error": "缺少 session_id"}, 400); return
                current = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
                if not current:
                    conn.close(); json_response(self, {"error": "找不到该场次"}, 404); return
                updates = {}
                if action == "cancel":
                    if current["session_status"] not in {"待排班", "已排班", "进行中"}: conn.close(); json_response(self, {"error": "只有未完成场次可以取消"}, 400); return
                    updates = {"session_status": "已取消"}; message = f"{session_id} 已取消，保留记录但不再参与正常排班"
                elif action == "assign":
                    if current["session_status"] not in {"待排班", "已排班"}:
                        conn.close(); json_response(self, {"error": "场次开始后不能更换DM"}, 400); return
                    dm_id = str(body.get("dm_id", "")).strip()
                    dm = conn.execute("SELECT * FROM dm_profiles WHERE dm_id=?", (dm_id,)).fetchone()
                    if not dm: conn.close(); json_response(self, {"error": "找不到该DM"}, 400); return
                    updates = {"assigned_dm_id": dm_id, "assigned_dm_name": dm["dm_name"], "session_status": "已排班"}
                    message = f"已将 {dm['dm_name']} 安排到 {session_id}"
                elif action == "start":
                    if current["session_status"] != "已排班": conn.close(); json_response(self, {"error": "请先完成排班"}, 400); return
                    if not current["assigned_dm_id"]: conn.close(); json_response(self, {"error": "请先安排DM"}, 400); return
                    updates = {"session_status": "进行中"}; message = f"{session_id} 已开始"
                elif action == "finish":
                    if current["session_status"] != "进行中": conn.close(); json_response(self, {"error": "只有进行中的场次可以结束"}, 400); return
                    updates = {"session_status": "已完成"}; message = f"{session_id} 已结束，可录入玩家评价"
                else:
                    conn.close(); json_response(self, {"error": "不支持的场次操作"}, 400); return
                set_clause=",".join(f"{quote_identifier(k)}=?" for k in updates)
                conn.execute(f"UPDATE sessions SET {set_clause} WHERE session_id=?", [*updates.values(),session_id]); conn.commit(); conn.close(); update_csv_row("sessions","session_id",session_id,updates)
                json_response(self, {"ok": True, "message": message}); return
            if parsed.path == "/api/feedback":
                conn = db_connect(); session_id=str(body.get("session_id","")).strip(); dm_id=str(body.get("dm_id","")).strip(); player_id=str(body.get("player_id","")).strip()
                session=conn.execute("SELECT * FROM sessions WHERE session_id=?",(session_id,)).fetchone()
                if not session: conn.close(); json_response(self,{"error":"找不到该场次"},400); return
                if session["session_status"] == "已取消": conn.close(); json_response(self,{"error":"已取消场次不能录入评价"},400); return
                if session["session_status"] not in {"已完成","已结束"}: conn.close(); json_response(self,{"error":"只有已完成场次可以录入评价"},400); return
                if not session["assigned_dm_id"] or dm_id != session["assigned_dm_id"]: conn.close(); json_response(self,{"error":"评价DM必须与该场次已安排的DM一致"},400); return
                required=["rule_explanation_rating","script_pace_rating","humor_comedy_rating","performance_immersion_rating","on_site_adaptability_rating","service_attitude_rating"]
                if not dm_id or not player_id: conn.close(); json_response(self,{"error":"DM和玩家编号不能为空"},400); return
                ratings={key:str(body.get(key,"5")).strip() for key in required}
                if any(value not in {"1","2","3","4","5"} for value in ratings.values()): conn.close(); json_response(self,{"error":"六维评价必须为1-5"},400); return
                feedback_id=next_identifier(conn,"feedback","feedback_id","FB"); submitted=datetime.now().strftime("%Y-%m-%d %H:%M")
                record={"feedback_id":feedback_id,"session_id":session_id,"dm_id":dm_id,"player_id":player_id,"submitted_at":submitted,**ratings,"comment_text":str(body.get("comment_text","")).strip()}
                fields=",".join(quote_identifier(k) for k in record); marks=",".join("?" for _ in record); conn.execute(f"INSERT INTO feedback ({fields}) VALUES ({marks})",list(record.values())); refresh_dm_scores(conn); conn.commit(); conn.close(); append_csv_row("feedback",record)
                json_response(self,{"ok":True,"feedback_id":feedback_id}); return
            if parsed.path == "/api/provider":
                if body.get("clear"):
                    PROVIDER_CONFIG.update({"provider": "", "api_key": "", "model": "", "wire_api": "chat_completions"})
                    json_response(self, {"configured": False, "provider": "", "model": "", "wire_api": "chat_completions"})
                    return
                provider = str(body.get("provider", "")).strip()
                base_url = str(body.get("base_url", "")).strip().rstrip("/")
                model = str(body.get("model", "")).strip()
                api_key = str(body.get("api_key", "")).strip()
                wire_api = str(body.get("wire_api", "chat_completions")).strip()
                if not base_url or not model or not api_key:
                    json_response(self, {"error": "请完整填写 Base URL、模型名称和 API Key"}, 400)
                    return
                if wire_api not in {"chat_completions", "responses"}:
                    json_response(self, {"error": "不支持的接口协议"}, 400)
                    return
                PROVIDER_CONFIG.update({
                    "provider": provider or "自定义",
                    "base_url": base_url,
                    "model": model,
                    "api_key": api_key,
                    "wire_api": wire_api,
                })
                json_response(self, {
                    "configured": True,
                    "provider": PROVIDER_CONFIG["provider"],
                    "model": model,
                    "wire_api": wire_api,
                })
                return
            if parsed.path == "/api/improvement":
                improvement_id = str(body.get("improvement_id", "")).strip()
                if not improvement_id:
                    json_response(self, {"error": "缺少 improvement_id"}, 400)
                    return
                status = str(body.get("status", "待考核")).strip()
                allowed_statuses = {"待店长复核", "待发送", "待执行", "执行中", "待考核", "考核通过", "考核失败", "已关闭"}
                if status not in allowed_statuses:
                    json_response(self, {"error": "不支持的改进任务状态"}, 400)
                    return
                conn = db_connect()
                found = conn.execute("SELECT 1 FROM improvements WHERE improvement_id=?", (improvement_id,)).fetchone()
                if not found:
                    conn.close()
                    json_response(self, {"error": "找不到该改进任务"}, 404)
                    return
                conn.execute(
                    "UPDATE improvements SET status=?, result_note=?, assessment_owner=?, assessment_method=?, "
                    "assessment_date=?, assessment_result=?, next_action=?, manager_reviewed=?, sent_by=?, sent_at=? "
                    "WHERE improvement_id=?",
                    (status, str(body.get("result_note", "")).strip(), str(body.get("assessment_owner", "店长")).strip(),
                     str(body.get("assessment_method", "")).strip(), str(body.get("assessment_date", "")).strip(),
                     str(body.get("assessment_result", "")).strip(), str(body.get("next_action", "")).strip(), "是",
                     str(body.get("sent_by", "")).strip(), datetime.now().strftime("%Y-%m-%d %H:%M") if body.get("sent_by") else "", improvement_id),
                )
                conn.commit()
                conn.close()
                json_response(self, {"ok": True, "improvement_id": improvement_id, "status": status})
                return
            if parsed.path != "/api/review":
                json_response(self, {"error": "Not Found"}, 404)
                return
            ai_result_id = str(body.get("ai_result_id", "")).strip()
            if not ai_result_id:
                json_response(self, {"error": "缺少 ai_result_id"}, 400)
                return
            status = str(body.get("ai_status", "已确认"))
            if status not in {"已确认", "已驳回"}:
                json_response(self, {"error": "复核状态只能是已确认或已驳回"}, 400)
                return
            severity = str(body.get("manager_severity", "")).strip()
            if status == "已确认" and severity not in {"低", "中", "高"}:
                json_response(self, {"error": "最终等级必须是低、中或高"}, 400)
                return
            conn = db_connect()
            found = conn.execute("SELECT 1 FROM ai_feedback WHERE ai_result_id=?", (ai_result_id,)).fetchone()
            if not found:
                conn.close()
                json_response(self, {"error": "找不到该AI分析结果"}, 404)
                return
            conn.execute(
                "UPDATE ai_feedback SET manager_severity=?, manager_correction=?, ai_status=? WHERE ai_result_id=?",
                (severity, str(body.get("manager_correction", "")).strip(), status, ai_result_id),
            )
            conn.commit()
            conn.close()
            json_response(self, {"ok": True, "ai_result_id": ai_result_id, "ai_status": status})
        except Exception as exc:
            json_response(self, {"error": str(exc)}, 500)


def main() -> None:
    init_db()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"剧本杀门店 AI 运营系统已启动：http://127.0.0.1:{PORT}")
    print(f"SQLite数据库：{DB_FILE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()




