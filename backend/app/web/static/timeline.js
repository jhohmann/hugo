/* Local, read-only renderer. Text from data is never inserted as HTML. */
(() => {
  'use strict';
  const payload = document.getElementById('timeline-data');
  if (!payload) return;
  const data = JSON.parse(payload.textContent);
  const $ = id => document.getElementById(id);
  const app = $('timeline-app'), scroll = $('tl-scroll'), grid = $('tl-grid');
  const day = 86400000;
  const stamp = value => value ? Date.parse(value.length === 10 ? `${value}T12:00:00Z` : value) : NaN;
  const today = stamp(data.today);
  const dateFormat = new Intl.DateTimeFormat('de-DE', {timeZone:'Europe/Berlin', day:'2-digit', month:'short', year:'numeric'});
  const timeFormat = new Intl.DateTimeFormat('de-DE', {timeZone:'Europe/Berlin', day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit'});
  const format = value => value ? (value.length > 10 ? timeFormat : dateFormat).format(stamp(value)) : 'Ohne Datum';
  const labels = {activity:'Aktivität', planning:'Geplanter Zeitpunkt', deadline:'Deadline', idea:'Hugos Idee · Vorschlag'};
  const origins = {user:'Nutzer', calendar:'Kalender', hugo:'Hugo', unknown:'Herkunft unbekannt'};
  const commitments = {confirmed:'Bestätigt', planned:'Geplant', suggested:'Vorschlag', unknown:'Verbindlichkeit unbekannt'};
  const kinds = {recorded:'Erfasst', scheduled:'Geplant für', deadline:'Frist', review:'Wiedervorlage'};
  const statuses = {proposed:'Idee', active:'Aktiv', waiting:'Wartend', completed:'Abgeschlossen', archived:'Archiviert'};
  const y = {activity:38, planning:69, deadline:99, idea:127};
  const closed = t => ['completed','archived'].includes(t.status);
  const node = (tag, className, text) => {
    const e = document.createElement(tag);
    if (className) e.className = className;
    if (text !== undefined) e.textContent = text;
    return e;
  };
  const url = new URL(location.href), params = url.searchParams;
  const allowed = (key, options, fallback) => options.includes(params.get(key)) ? params.get(key) : fallback;
  const state = {
    status:allowed('status',['active','inactive','all'],'active'),
    tag:allowed('tag',['all','arbeit','privat'],'all'),
    sort:allowed('sort',['age','pause'],'age'), range:allowed('range',['30','90','365','all'],'90'),
    layers:new Set(params.has('layers') ? params.get('layers').split(',').filter(k => k in labels) : Object.keys(labels)),
    center:Number.isFinite(stamp(params.get('center'))) ? stamp(params.get('center')) : today,
  };
  // Index once; a row never scans all other threads' points.
  const byThread = new Map(data.threads.map(t => [t.id, []]));
  data.points.forEach(p => byThread.get(p.thread_id)?.push(p));
  const dated = data.points.flatMap(p => [stamp(p.start), stamp(p.end)]).filter(Number.isFinite);
  const starts = data.threads.map(t => stamp(t.created_on));
  const min = Math.min(today - 45 * day, ...starts, ...dated) - 15 * day;
  const max = Math.max(today + 60 * day, ...dated) + 15 * day;
  let scale = 1, labelWidth = 252, visibleWidth = 600, scrollTimer, resizeTimer;
  const tooltip = $('tl-tooltip'), dialog = $('tl-detail');
  const hideTooltip = () => { tooltip.hidden = true; };
  const period = p => `${format(p.start)}${p.end ? ' bis ' + format(p.end) : ''}${p.precision === 'approximate' ? ' · ungefähr' : ''}`;
  function saveURL() {
    const u = new URL(location.href);
    ['status','tag','sort','range'].forEach(k => u.searchParams.set(k,state[k]));
    u.searchParams.set('layers', [...state.layers].join(','));
    u.searchParams.set('center',new Date(state.center).toISOString());
    history.replaceState(null,'',u);
  }
  function showDetails(points, title) {
    hideTooltip();
    const content = $('tl-detail-content'); content.replaceChildren(node('h2','',title));
    points.forEach(p => {
      const item = node('section','tl-detail-item');
      item.append(node('h3','',p.title),node('p','muted',`${labels[p.layer]} · ${commitments[p.commitment]}`),
        node('p','',`${kinds[p.time_kind]}: ${period(p)}`), node('p','muted',origins[p.origin]), node('p','',p.summary));
      if (p.source_url && (/^https:\/\//.test(p.source_url) || /^\/(?![\/\\])/.test(p.source_url))) {
        const link = node('a','',p.source_label || 'Quelle öffnen'); link.href = p.source_url; item.append(link);
      }
      content.append(item);
    });
    if (!dialog.open) dialog.showModal();
  }
  function bindPoint(button, points) {
    const p = points[0];
    const title = points.length > 1 ? `${points.length} Ereignisse · ${labels[p.layer]}` : p.title;
    button.setAttribute('aria-label', points.length > 1 ? `${title}, Einzelereignisse öffnen` : `${title}, ${period(p)}, ${commitments[p.commitment]}`);
    button.addEventListener('click', () => showDetails(points,title));
    const show = () => {
      tooltip.textContent = points.length > 1
        ? `${title}\n${format(p.start)} bis ${format(points[points.length-1].start)}\nAuswählen, um Herkunft und Verbindlichkeit der Einzelereignisse zu lesen.`
        : `${title}\n${period(p)}\n${commitments[p.commitment]} · ${origins[p.origin]}\n${p.summary}`;
      tooltip.hidden = false;
      const rect = button.getBoundingClientRect();
      tooltip.style.left = `${Math.max(12,Math.min(rect.left,innerWidth-tooltip.offsetWidth-12))}px`;
      tooltip.style.top = `${Math.max(12,Math.min(rect.bottom+8,innerHeight-tooltip.offsetHeight-12))}px`;
    };
    button.addEventListener('pointerenter', e => { if(e.pointerType !== 'touch') show(); });
    button.addEventListener('focus',show);
    button.addEventListener('pointerleave',hideTooltip);
    button.addEventListener('blur',hideTooltip);
  }
  function render() {
    hideTooltip(); clearTimeout(scrollTimer);
    labelWidth = parseFloat(getComputedStyle(app).getPropertyValue('--tl-label'));
    visibleWidth = Math.max(160,scroll.clientWidth-labelWidth);
    const days = state.range === 'all' ? (max-min)/day : Number(state.range);
    scale = visibleWidth/(days*day);
    const width = Math.max(visibleWidth,(max-min)*scale);
    const x = value => (value-min)*scale;
    const step = [1,2,7,14,30,90,180,365].find(n => n*day*scale >= 85) || 730;
    const ticks = [];
    for(let t=min; t<=max; t+=step*day) ticks.push(t);
    grid.style.width = `${labelWidth+width}px`;
    const track = () => {
      const e = node('div','tl-track'); e.style.width = `${width}px`;
      e.style.backgroundSize = `${step*day*scale}px 100%`;
      const mark = node('div','tl-today-line'); mark.style.left = `${x(today)}px`; e.append(mark);
      return e;
    };
    const axis = node('div','tl-row tl-axis'); axis.append(node('div','tl-label','Handlungsstränge'));
    const ruler = track();
    ticks.forEach(t => { const tick=node('span','tl-tick',dateFormat.format(t)); tick.style.left=`${x(t)}px`; ruler.append(tick); });
    const todayLabel=node('span','tl-today-label','Heute'); todayLabel.style.left=`${x(today)}px`; ruler.append(todayLabel);
    axis.append(ruler);
    const rows = data.threads.filter(t => (state.status === 'all' || closed(t) === (state.status === 'inactive')) && (state.tag === 'all' || t.tags.includes(state.tag)));
    rows.sort((a,b) => {
      const value = t => state.sort === 'age' ? stamp(t.created_on) : (t.last_user_activity ? stamp(t.last_user_activity) : Infinity);
      return value(a)-value(b) || a.id.localeCompare(b.id);
    });
    const fragment = document.createDocumentFragment(); fragment.append(axis);
    const undated = [];
    rows.forEach(t => {
      const row=node('div','tl-row'); row.dataset.thread=t.id;
      const side=node('div','tl-label'), title=node('button','tl-title',t.title); title.type='button';
      title.addEventListener('click',()=>showDetails(byThread.get(t.id),`${t.title} · Beispieldaten`));
      side.append(title,node('div','tl-meta',`${statuses[t.status]} · ${t.tags.map(tag=>tag==='arbeit'?'Arbeit':'Privat').join(', ') || 'Ohne Bereich'}`),
        node('div','tl-age',`Seit ${format(t.created_on)}`));
      const pause=t.last_user_activity ? Math.max(0,Math.floor((today-stamp(t.last_user_activity))/day)) : null;
      side.append(node('div',`tl-meta ${pause >= 60 ? 'tl-pause' : ''}`,pause === null ? 'Nutzeraktivität unbekannt' : `Letzte Nutzeraktivität vor ${pause} Tagen`));
      row.append(side); const lane=track();
      const points=byThread.get(t.id);
      const end=closed(t) ? Math.max(stamp(t.created_on),...points.filter(p=>p.layer==='activity' && p.start).map(p=>stamp(p.start))) : today;
      const line=node('div','tl-spine'); line.style.left=`${x(stamp(t.created_on))}px`; line.style.width=`${Math.max(0,x(end)-x(stamp(t.created_on)))}px`; lane.append(line);
      if(!closed(t)) { const future=node('div','tl-spine tl-future'); future.style.left=`${x(today)}px`; future.style.width=`${width-x(today)}px`; lane.append(future); }
      Object.keys(labels).filter(layer=>state.layers.has(layer)).forEach(layer => {
        const filtered=points.filter(p=>p.layer===layer);
        undated.push(...filtered.filter(p=>!p.start).map(p=>({p,thread:t.title})));
        const sorted=filtered.filter(p=>p.start).sort((a,b)=>stamp(a.start)-stamp(b.start));
        const groups=[];
        sorted.forEach(p=>{
          if(p.end) { const bar=node('div',`tl-span ${p.precision}`); bar.style.left=`${x(stamp(p.start))}px`; bar.style.top=`${y[layer]}px`; bar.style.width=`${Math.max(5,(stamp(p.end)-stamp(p.start))*scale)}px`; lane.append(bar); }
          const last=groups[groups.length-1];
          if(last && (stamp(p.start)-stamp(last[0].start))*scale < 28) last.push(p); else groups.push([p]);
        });
        groups.forEach(group=>{
          const button=node('button',`tl-node ${layer}${group.length>1?' group':''}`,group.length>1?String(group.length):''); button.type='button';
          button.style.left=`${x(stamp(group[0].start))}px`; button.style.top=`${y[layer]}px`;
          bindPoint(button,group); lane.append(button);
        });
      });
      row.append(lane); fragment.append(row);
    });
    grid.replaceChildren(fragment);
    $('tl-count').textContent=`${rows.length} Handlungsstränge · ${dateFormat.format(min)} bis ${dateFormat.format(max)}`;
    $('tl-empty').hidden=rows.length>0;
    $('tl-undated-count').textContent=`(${undated.length})`;
    $('tl-undated-items').replaceChildren(...undated.map(({p,thread})=>{
      const button=node('button','button',`${thread}: ${p.title} · ${commitments[p.commitment]}`); button.type='button'; bindPoint(button,[p]); return button;
    }));
    scroll.scrollLeft=Math.max(0,Math.min(width-visibleWidth,x(state.center)-visibleWidth/2));
    state.center=min+(scroll.scrollLeft+visibleWidth/2)/scale;
    saveURL();
  }
  ['status','tag','sort','range'].forEach(k=>{
    const select=$(`tl-${k}`); select.value=state[k];
    select.addEventListener('change',()=>{ state[k]=select.value; render(); });
  });
  document.querySelectorAll('.tl-layers input').forEach(input=>{
    input.checked=state.layers.has(input.value);
    input.addEventListener('change',()=>{ input.checked?state.layers.add(input.value):state.layers.delete(input.value); render(); });
  });
  const zoom = direction => {
    const ranges=['30','90','365','all']; state.range=ranges[Math.max(0,Math.min(3,ranges.indexOf(state.range)+direction))];
    $('tl-range').value=state.range; render();
  };
  $('tl-in').addEventListener('click',()=>zoom(-1)); $('tl-out').addEventListener('click',()=>zoom(1));
  $('tl-today').addEventListener('click',()=>{ state.center=today; render(); });
  $('tl-close').addEventListener('click',()=>dialog.close());
  document.addEventListener('keydown',e=>{ if(e.key==='Escape') hideTooltip(); });
  scroll.addEventListener('scroll',()=>{
    hideTooltip(); clearTimeout(scrollTimer);
    scrollTimer=setTimeout(()=>{ state.center=min+(scroll.scrollLeft+visibleWidth/2)/scale; saveURL(); },150);
  });
  window.addEventListener('resize',()=>{ clearTimeout(resizeTimer); resizeTimer=setTimeout(render,150); });
  app.hidden=false;
  render();
  $('tl-fallback').open=false;
})();
