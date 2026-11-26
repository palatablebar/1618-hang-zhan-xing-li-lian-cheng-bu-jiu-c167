export function draw(target, data, {node, mark, choose}) {
  const ranked = data.decisions.filter(row=>row.estimate!==null).sort((a,b)=>b.estimate-a.estimate);
  const selection = ranked.slice(0,6);
  const ruler = node('div','','risk-axis');
  for (const value of ['低','0.25','0.50','0.75','高']) ruler.append(node('span',value));
  const list = node('div','','departure-bars');
  for (const item of selection) {
    const row = node('button','','viz-button');
    row.dataset.key=item.key;
    row.type = 'button';
    row.setAttribute('aria-label',`${item.key} 风险 ${mark(item.estimate)}，剩余截关 ${item.raw.slack} 分钟`);
    const meter = node('span','','risk-track');
    const fill = node('i');
    fill.style.width=`${Math.max(1,Math.min(100,item.estimate*100))}%`;
    meter.append(fill);
    row.append(node('strong',item.key.replace('BAG-','')),meter,node('span',mark(item.estimate)));
    row.onclick=()=>choose(item.key);
    list.append(row);
  }
  const description = node('p',selection.length ? '按短接风险从高到低显示。选择条形可查看实际截关和安检交接。' : '当前无可评分行李。','chart-caption');
  target.replaceChildren(ruler,list,description);
}
