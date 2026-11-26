import { draw } from './visual.js';

const find = (selector) => document.querySelector(selector);
const form = find('#scenario');
const ui = {
  quota: find('#quota'), reserve: find('#reserve'), region: find('#region'), status: find('#status'),
  queue: find('#queue'), detail: find('#detail'), filter: find('#filter'), search: find('#search'),
  chart: find('#chart'), stats: find('#kpis'), replay: find('#replay-data'),
  policy: find('#policy-data'),
  start: find('#start'), stop: find('#stop'), publish: find('#publish'), download: find('#download')
};
const fmt = new Intl.NumberFormat('zh-CN', {maximumFractionDigits: 2});
const statuses = {booked:'已安排', wait:'候补待排', manual:'待人工核实', locked:'已锁定', normal:'常规处置'};
const modeOf = (data) => ['classification','anomaly','residual'].includes(data.context.estimate_type) ? '风险分数' : '分窗预测';
let batch;
let selection;
let lastScenario;
let pending = false;
let modified = false;

function node(tag, text = '', className = '') {
  const el = document.createElement(tag);
  if (text !== '') el.textContent = text;
  if (className) el.className = className;
  return el;
}

function announce(text, failed = false) {
  ui.status.textContent = text;
  ui.status.dataset.error = String(failed);
}

async function request(path, payload) {
  const options = payload === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)};
  const res = await fetch(path, options);
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const detail = data.detail;
    const message = typeof detail === 'string' ? detail : detail?.reason;
    throw new Error(message || `服务未接受请求（${res.status}）`);
  }
  return res;
}

function capture() {
  return {budget:ui.quota.valueAsNumber,reserve:ui.reserve.valueAsNumber,
          region:ui.region.value || null,start:ui.start.valueAsNumber,stop:ui.stop.valueAsNumber};
}

function showScenario(scenario) {
  for (const [element, value] of [[ui.quota,scenario.budget],[ui.reserve,scenario.reserve],
    [ui.start,scenario.start],[ui.stop,scenario.stop],[ui.region,scenario.region || '']]) {
    element.value = value;
  }
}

function setPending(value) {
  pending = value;
  const blocked = batch?.result.readiness === 'blocked';
  form.querySelector('button[type=submit]').disabled = value;
  ui.publish.disabled = value || modified || blocked || !batch;
  ui.download.disabled = value || modified || !batch;
}

function time(value) {
  return value === null ? '—' : `${String(Math.floor(value/60)).padStart(2,'0')}:${String(value%60).padStart(2,'0')}`;
}

function mark(value) { return value === null || value === undefined ? '—' : fmt.format(value); }

function stats(data) {
  const summary = data.ledger;
  const states = summary.status_counts;
  return [['已分派额度',summary.booked_units],['候补单据',states.wait],['待人工核实',states.manual],
          ['余量与预留',`${mark(summary.free_units)} / ${mark(summary.reserved_units)}`]];
}

function renderDetail(row) {
  if (!row) {
    ui.detail.replaceChildren(node('p','当前筛选没有单据。','empty'));
    return;
  }
  const head = node('div','','detail-title');
  head.append(node('span',row.region,'context-text'),node('h3',row.key),node('b',row.action,`badge ${row.status}`));
  const metrics = node('dl','','facts');
  const data = batch.result;
  const entries = [[modeOf(data),mark(row.estimate)],['本轮分派',`${row.units} / ${row.requested}`],
    ['确认窗口',row.start === null ? '未排定' : `${time(row.start)}–${time(row.end)}`],['单据版本',`第 ${row.revision} 版`]];
  entries.forEach(([name,value]) => { metrics.append(node('dt',name),node('dd',value)); });
  const reason = node('p',row.reason,'disposition');
  const raw = node('details','','measures');
  raw.append(node('summary','现场读数和预测依据'));
  const facts = node('dl','','facts');
  for (const field of data.context.fields) {
    const value = row.raw[field.key];
    facts.append(node('dt',field.title),node('dd',value === null ? '缺测' : `${mark(value)} ${field.unit}`));
  }
  const influences = Object.entries(row.drivers).sort((a,b)=>Math.abs(b[1])-Math.abs(a[1])).slice(0,3);
  const explain = node('ul','','drivers');
  for (const [name,value] of influences) {
    explain.append(node('li',`${name.replaceAll('_',' ')} · ${value > 0 ? '+' : ''}${mark(value)}`));
  }
  if (row.interval) explain.append(node('li',`历史误差带 ${mark(row.interval[0])}–${mark(row.interval[1])}`));
  const checks = node('dl','','facts evidence-checks');
  for (const check of row.business_evidence.checks) {
    const amount = node('dd',`${mark(check.value)} ${check.unit}${check.exceeded ? ' · 越界' : ''}`);
    amount.dataset.outside = String(check.exceeded);
    checks.append(node('dt',check.label),amount);
  }
  raw.append(facts,checks,explain);
  ui.detail.replaceChildren(head,metrics,reason,raw);
}

function renderQueue(items) {
  const count = find('#result-count');
  count.textContent = `${items.length} 条`;
  if (!items.length) {
    ui.queue.replaceChildren(node('p','没有匹配的处置记录。','empty'));
    return;
  }
  const group = document.createDocumentFragment();
  for (const item of items) {
    const control = node('button','',`case-row ${item.status}`);
    control.type = 'button';
    control.dataset.key = item.key;
    control.setAttribute('aria-pressed',String(item.key === selection));
    const identity = node('span','','case-id');
    identity.append(node('strong',item.key), node('small',item.region));
    const score = node('span',mark(item.estimate),'case-estimate');
    const outcome = node('span',item.action,`case-action badge ${item.status}`);
    control.append(identity,score,outcome);
    control.onclick = () => select(item.key, true);
    group.append(control);
  }
  ui.queue.replaceChildren(group);
}

function select(key, focusRow = false) {
  selection = key;
  for (const button of ui.queue.querySelectorAll('[data-key]')) {
    const match = button.dataset.key === key;
    button.setAttribute('aria-pressed',String(match));
    if (match && focusRow) button.focus({preventScroll:true});
  }
  renderDetail(batch.result.decisions.find(row => row.key === key));
  ui.chart.querySelectorAll('[data-key]').forEach(el => el.classList.toggle('marked',el.dataset.key === key));
}

function filterRows() {
  if (!batch) return;
  const term = ui.search.value.trim().toLowerCase();
  const chosen = ui.filter.value;
  const visible = batch.result.decisions.filter(row => (!chosen || row.status === chosen) &&
    (!term || [row.key,row.region,row.action].some(value=>value.toLowerCase().includes(term))));
  const first = visible.find(row=>row.key===selection) || visible[0];
  selection = first?.key;
  renderQueue(visible);
  select(selection);
}

function policyBasis(data) {
  if (!ui.policy) return;
  const review = data.dispatch_replay || data.policy_replay || data.dispatch;
  if (!review) {
    ui.policy.replaceChildren(node('p','暂无排班回放证据。','domain-note'));
    return;
  }
  const adoption = review.adoption || review.recommendation || review;
  ui.policy.dataset.adopt = String(Boolean(adoption.adopt || adoption.enabled));
  ui.policy.dataset.enabled = ui.policy.dataset.adopt;
  const before = review.baseline || {};
  const after = review.candidate || {};
  const head = node('div','','policy-head');
  head.append(node('strong', adoption.adopt ? '达到启用条件' : '暂不启用',
    `policy-verdict ${adoption.adopt ? 'enable' : 'hold'}`));
  head.append(node('span', adoption.adopt ? '新排法可启用' : '继续使用原排法','context-text'));
  const grid = node('dl','','evidence-list policy-metrics');
  const rows = [
    ['原排法覆盖已确认误机', `${mark(before.covered_confirmed_missed)} 件 / ${mark(before.covered_confirmed_missed_cases)} 单`],
    ['新排法覆盖已确认误机', `${mark(after.covered_confirmed_missed)} 件 / ${mark(after.covered_confirmed_missed_cases)} 单`],
    ['覆盖增量', `${mark(adoption.covered_confirmed_missed_delta)} 件`],
    ['已确认误机总量', `${mark(after.confirmed_missed_total)} 单`],
    ['迟到回报（仅计分）', `${mark(after.late_reports)} 单`],
    ['未回报（另算）', `${mark(after.unreported)} 单`],
    ['车位 / 安检窗', adoption.identical_conditions === false ? '条件不一致' : '两排法相同'],
    ['受保护最早截关单', (adoption.protected_earliest_keys || review.earliest_closeout_keys || []).join('、') || '—']
  ];
  rows.forEach(([key,value]) => grid.append(node('dt',key),node('dd',value)));
  const reasons = node('ul','','policy-reasons');
  for (const text of adoption.reasons || []) reasons.append(node('li',text));
  if (adoption.basis) reasons.append(node('li',adoption.basis));
  ui.policy.replaceChildren(head,grid,reasons);
}

function replay(data) {
  const recap = data.replay.holdout;
  const kind = recap.mae === undefined ? 'Brier' : '平均绝对误差';
  const error = recap.mae === undefined ? recap.brier : recap.mae;
  const baseline = recap.mae === undefined ? recap.baseline_brier : recap.baseline_mae;
  const fields = [['算法',data.model.algorithm],['训练样本',data.model.train_rows],['近窗回放',recap.count],
                  [kind,mark(error)],['历史基线',mark(baseline)],['校准方式',data.replay.adjustment],['输入隔离',data.intake.isolated]];
  const table = node('dl','','evidence-list');
  fields.forEach(([key,value]) => table.append(node('dt',key),node('dd',value)));
  const issue = node('p',data.drift.reasons.join('。') || '当前输入处于训练支持范围。','domain-note');
  ui.replay.replaceChildren(table,issue);
}

function render(response) {
  batch = response;
  const data = response.result;
  lastScenario = data.scenario;
  const possible = Object.keys(data.cohorts.current_by_region);
  ui.region.replaceChildren(node('option','全部片区'));
  ui.region.options[0].value = '';
  possible.forEach(region=> { const o = node('option',region); o.value = region; ui.region.append(o); });
  showScenario(lastScenario);
  ui.stats.replaceChildren(...stats(data).map(([key,value])=>{
    const cell = node('div','','metric');
    cell.append(node('span',key),node('strong',String(value)));
    return cell;
  }));
  find('#estimate-title').textContent = modeOf(data);
  policyBasis(data);
  draw(ui.chart, data, {node,mark,time,choose:key=>{ ui.search.value=''; ui.filter.value=''; selection=key; filterRows(); }});
  replay(data);
  filterRows();
  modified = false;
  setPending(false);
  announce(`预览 ${response.id.slice(0,8)} · 归档第 ${response.revision} 版${data.readiness==='blocked' ? ' · 暂停发布' : ''}`);
}

form.addEventListener('input', () => { modified = true; setPending(pending); });
form.addEventListener('submit', async event=>{
  event.preventDefault();
  setPending(true);
  try { render(await (await request('/api/scenario',capture())).json()); }
  catch (error) { announce(error.message,true); setPending(false); }
});
ui.filter.addEventListener('change',filterRows);
ui.search.addEventListener('input',filterRows);

ui.publish.addEventListener('click',async()=>{
  setPending(true);
  try {
    const result = await (await request('/api/publish',{expected_revision:batch.revision,id:batch.id,scenario:lastScenario})).json();
    batch.revision = result.current_revision;
    announce(result.replay ? `已归档于第 ${result.revision} 版，重复提交已合并` : `已发布第 ${result.revision} 版`);
  } catch (error) { announce(error.message,true); }
  finally { setPending(false); }
});

ui.download.addEventListener('click',async()=>{
  setPending(true);
  try {
    const csv = await (await request('/api/manifest.csv',lastScenario)).blob();
    const anchor = node('a');
    anchor.download = 'dispatch-manifest.csv';
    anchor.href = URL.createObjectURL(csv);
    anchor.click();
    setTimeout(()=>URL.revokeObjectURL(anchor.href),1000);
  } catch (error) { announce(error.message,true); }
  finally { setPending(false); }
});

setPending(true);
request('/api/snapshot').then(r=>r.json()).then(render).catch(error=>{
  announce(error.message,true);
  setPending(false);
});
