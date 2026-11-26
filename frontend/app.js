
/* --- диагностика: любую ошибку JS показываем прямо на странице --- */
window.addEventListener('error', function(e){
  try{
    var d=document.createElement('div');
    d.style.cssText='position:fixed;left:10px;top:10px;z-index:99999;max-width:92vw;background:#7f1d1d;color:#fff;padding:10px 14px;border-radius:10px;font:12px/1.5 monospace;white-space:pre-wrap';
    d.textContent='Ошибка страницы: '+(e.message||e)+'\n'+(((e.error&&e.error.stack)||'').split('\n').slice(0,3).join('\n'));
    (document.body||document.documentElement).appendChild(d);
  }catch(_){}
});
window.addEventListener('unhandledrejection', function(e){
  try{
    var d=document.createElement('div');
    d.style.cssText='position:fixed;left:10px;top:10px;z-index:99999;max-width:92vw;background:#7f1d1d;color:#fff;padding:10px 14px;border-radius:10px;font:12px/1.5 monospace;white-space:pre-wrap';
    d.textContent='Ошибка (promise): '+(e.reason&&e.reason.message||e.reason);
    (document.body||document.documentElement).appendChild(d);
  }catch(_){}
});

'use strict';
/* ================= ИКОНКИ ================= */
const svgI = (p, extra='') => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" ${extra}>${p}</svg>`;
const ICONS = {
  grid: svgI('<rect x="3" y="3" width="8" height="8" rx="1.6"/><rect x="13" y="3" width="8" height="8" rx="1.6"/><rect x="3" y="13" width="8" height="8" rx="1.6"/><rect x="13" y="13" width="8" height="8" rx="1.6"/>'),
  kanban: svgI('<rect x="3" y="3" width="5" height="14" rx="1.5"/><rect x="10" y="3" width="5" height="18" rx="1.5"/><rect x="17" y="3" width="4" height="10" rx="1.5"/>'),
  chat: svgI('<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5z"/>'),
  tag: svgI('<path d="M20.6 13.4l-7.2 7.2a2 2 0 0 1-2.8 0L2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8z"/><circle cx="7" cy="7" r="1.4"/>'),
  chart: svgI('<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>'),
  bolt: svgI('<polygon points="13 2 3 14 10 14 9 22 21 9 13 9 13 2"/>'),
  gear: svgI('<line x1="4" y1="7" x2="20" y2="7"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="17" x2="20" y2="17"/><circle cx="9" cy="7" r="2"/><circle cx="15" cy="12" r="2"/><circle cx="8" cy="17" r="2"/>'),
};

/* ================= ДАННЫЕ (только реальные, с сервера) ================= */
const PF = {
  funpay:   {name:'FunPay',   color:'#3b82f6', cls:'pf-funpay'},
  playerok: {name:'Playerok', color:'#8b5cf6', cls:'pf-playerok'},
};
const ST = {
  new:     {title:'Оплачен · ждёт выдачи',      short:'Ждёт выдачи',  color:'#fbbf24'},
  sent:    {title:'Выдан · ждёт подтверждения', short:'Ждёт подтв.',  color:'#38bdf8'},
  done:    {title:'Завершённые',                short:'Завершён',     color:'#34d399'},
  dispute: {title:'Споры · возвраты',           short:'Спор',         color:'#f87171'},
};


const state = {
  view:'dashboard',
  draft:'', gsearch:'', gfilter:'all', ordTab:'all', chatPf:'',
  activeChat:1,
  chatOpen:false,
  /* Никаких выдуманных цифр: состояние пустое, пока сервер не отдаст
     реальные данные площадок (FunPay / Playerok). */
  stats:{},
  orders:[],
  chats:[],
  products:[],
  alerts:[],
  rules:[],
  fees:{funpay:5.5, playerok:10},
  wfees:{funpay:3, playerok:6},
  tg:{bot:'', chat:''},
  accounts:{
    funpay:{connected:false, login:'', key:'', error:''},
    playerok:{connected:false, login:'', key:'', error:''},
  },
};
const TITLES = {dashboard:'Дашборд', orders:'Заказы', goods:'Товары', chats:'Сообщения', analytics:'Аналитика', settings:'Настройки'};
const TEMPLATES = [
  'Спасибо за заказ! Уже выдаю товар ⚡',
  'Товар выдан — подтвердите, пожалуйста, получение ✅',
  'Сейчас отойду, отвечу в течение 5–10 минут 🙏',
  'Буду рад вашему отзыву ⭐ Приятной игры!',
];

/* ============ PLAYEROK: КАТЕГОРИИ, СТАВКИ, ПРЕМИУМ ============
   Публичные ставки площадки: 10% — донат, пополнения, лицензии игр и
   приложений, подписки на сервисы; 20% — остальные разделы.
   Премиум-размещение (карточка в топе категории) списывается ЗА КАЖДУЮ
   сделку, если включено «Оставить в продаже»; цена зависит от цены товара
   и ставки раздела. Столбец 20% частично восстановлен по шаблону сетки
   (известны 25 ₽ для 90–499 и 49 ₽ для 1000–2499) — помечен как ≈. */
const PO_CAT_FEES = [
  {id:'donate', t:'Донат и внутриигровая валюта (гемы, Robux, VP…)', fee:10},
  {id:'topup',  t:'Пополнение баланса (Steam, кошельки…)',           fee:10},
  {id:'lic',    t:'Лицензии игр и приложений',                       fee:10},
  {id:'subs',   t:'Подписки на сервисы (Telegram Premium и т.п.)',   fee:10},
  {id:'acc',    t:'Аккаунты',                                        fee:20},
  {id:'skins',  t:'Скины и предметы',                                fee:20},
  {id:'keys',   t:'Ключи и подарочные карты',                        fee:20},
  {id:'boost',  t:'Буст и игровые услуги (прокачка, буст ранга…)',   fee:20},
  {id:'other',  t:'Прочее (дизайн, монтаж, услуги)',                 fee:20},
];
/* Игры-подсказки, снятые с реальных каталогов площадок (playerok.com/games, funpay.com).
   Начинаешь печатать «Pu» — выпадают PUBG Mobile, PUBG (ПК) и т.д. */
const GAMES_PF = {
  playerok:['PUBG Mobile','PUBG (ПК)','Roblox','Genshin Impact','Honkai: Star Rail','Zenless Zone Zero',
    'Wuthering Waves','Standoff 2','Brawl Stars','Mobile Legends Bang Bang','Free Fire','Clash Royale',
    'Fortnite','Valorant','Counter-Strike 2','Dota 2','Minecraft','GTA 5 Online','GTA 6','Warframe',
    'Apex Legends','World of Warcraft','Hearthstone','Delta Force','Warface','Escape from Tarkov','Rust',
    'Cyberpunk 2077','Red Dead Redemption 2','The Sims','EA Sports FC 27','eFootball','Arena Breakout',
    'Dead by Daylight','SCraft','Танки ПК','Шахматы','Rob Run','Call of Duty: Modern Warfare 4'],
  funpay:['Steam (кошелёк)','Steam (ключи)','Minecraft','Counter-Strike 2','Dota 2','GTA 5','World of Tanks',
    'World of Warcraft','Escape from Tarkov','Rust','Warface','Valorant','Fortnite','Roblox','Genshin Impact',
    'Honkai: Star Rail','Zenless Zone Zero','Wuthering Waves','Brawl Stars','Mobile Legends Bang Bang',
    'Standoff 2','PUBG Mobile','Free Fire','Albion Online','Aion 2','Lineage 2','Black Desert','Lost Ark',
    'Path of Exile','Warframe','Apex Legends','Call of Duty','EA Sports FC 27','Dead by Daylight','Hearthstone',
    'The Sims','Cyberpunk 2077','Red Dead Redemption 2','Elden Ring','Diablo IV','Overwatch 2',
    'Rainbow Six Siege','Discord Nitro','Spotify Premium','YouTube Premium','Netflix','PlayStation Plus',
    'Xbox Game Pass','Nintendo eShop','PSN карты','Among Us','Unturned'],
};
/* Разделы FunPay из реального каталога */
const FP_SECTS = ['Аккаунты','Ключи','Предметы','Услуги','Пополнение баланса','Подписка','Game Pass',
  'Коучинг','Twitch Drops','Кошельки','Подарочные карты','Скины','Другое'];
/* [верх цены товара, премиум для ставки 10%, премиум для ставки 20%] */
const PO_PREMIUM = [
  [499, 19, 25],
  [999, 25, 37],
  [2499, 37, 49],
  [4999, 49, 75],
  [9999, 75, 99],
  [Infinity, 99, 99],
];
function poPremium(price, fee){
  for(const [max,p10,p20] of PO_PREMIUM) if(price<=max) return fee<=10 ? p10 : p20;
  return 99;
}

/* ================= УТИЛИТЫ ================= */
const $ = (s,el=document)=>el.querySelector(s);
const $$ = (s,el=document)=>[...el.querySelectorAll(s)];
const fmt = n => n.toLocaleString('ru-RU') + ' ₽';
const fmtN = n => n.toLocaleString('ru-RU');
function ago(m){
  if(m < 1) return 'только что';
  if(m < 60) return m + ' мин назад';
  const h = Math.floor(m/60);
  if(h < 24) return h + ' ч назад';
  return Math.floor(h/24) + ' дн назад';
}
function clockStr(m){ const d=new Date(Date.now()-m*60000); return d.getHours().toString().padStart(2,'0')+':'+d.getMinutes().toString().padStart(2,'0'); }
function pfBadge(p){ return `<span class="pf-badge pf-${p}">${PF[p].name}</span>`; }
function stPill(s){ return `<span class="st-pill" style="background:${ST[s].color}22;color:${ST[s].color}">${ST[s].short}</span>`; }

function toast(text, kind='', icon='🔔'){
  const t = document.createElement('div');
  t.className = 'toast ' + kind;
  t.innerHTML = `<span class="tt">${icon}</span><span>${text}</span>`;
  $('#toasts').appendChild(t);
  setTimeout(()=>{ t.style.opacity='0'; t.style.transition='opacity .4s'; setTimeout(()=>t.remove(),420); }, 4600);
}

/* ================= ГРАФИКИ (чистый SVG) ================= */

function donut(shares,size=140){
  const r=52, C=2*Math.PI*r; let off=0, segs='';
  const total=shares.reduce((a,b)=>a+(b.v||0),0);
  if(!total){
    // выручки пока нет — показываем пустое кольцо, а не выдуманные 50%
    return `<svg viewBox="0 0 140 140" width="${size}" height="${size}">
      <circle cx="70" cy="70" r="${r}" fill="none" stroke="#232c3f" stroke-width="17"/>
      <text x="70" y="72" text-anchor="middle" fill="#8b95ab" font-size="12">нет данных</text></svg>`;
  }
  shares.forEach(s=>{
    const len=Math.max(0,(s.v||0)/100*C);
    if(len<=0) return;
    segs += `<circle cx="70" cy="70" r="${r}" fill="none" stroke="${s.color}" stroke-width="17" stroke-linecap="butt" stroke-dasharray="${Math.max(0,len-2)} ${C-Math.max(0,len-2)}" stroke-dashoffset="${-off}" transform="rotate(-90 70 70)"/>`;
    off += len;
  });
  const lead=shares.slice().sort((a,b)=>b.v-a.v)[0];
  const leadName=(PF[lead.name]&&PF[lead.name].name)||lead.label||'';
  return `<svg viewBox="0 0 140 140" width="${size}" height="${size}">${segs}
    <text x="70" y="66" text-anchor="middle" fill="#e8ecf4" font-size="19" font-weight="800">${Math.round(lead.v)}%</text>
    <text x="70" y="84" text-anchor="middle" fill="#8b95ab" font-size="10">${leadName}</text></svg>`;
}

/* ================= РЕНДЕР: КАРКАС ================= */
const NAV = [
  {v:'dashboard', t:'Дашборд',      i:'grid'},
  {v:'orders',    t:'Заказы',       i:'kanban', badge:()=>state.orders.filter(o=>o.status==='new').length},
  {v:'goods',     t:'Товары',       i:'tag',  badge:()=>(state.products||[]).filter(p=>p.status==='draft').length},
  {v:'chats',     t:'Сообщения',    i:'chat',   badge:()=>state.chats.reduce((s,c)=>s+c.unread,0)},
  {v:'analytics', t:'Аналитика',    i:'chart'},
  {v:'settings',  t:'Настройки',    i:'gear'},
];
function renderNav(){
  $('#nav').innerHTML = NAV.map(n=>{
    const b = n.badge ? n.badge() : 0;
    return `<div class="nav-item ${state.view===n.v?'active':''}" data-act="nav" data-view="${n.v}" title="${n.t}">
      ${ICONS[n.i]}<span class="nav-label">${n.t}</span>${b?`<span class="nav-badge">${b}</span>`:''}</div>`;
  }).join('');
}
function renderChips(){
  const tb=$('#tb-chips');
  if(tb) tb.innerHTML=['funpay','playerok'].map(p=>{
    const a=state.accounts[p]||{};
    return `<div class="tb-chip"><span class="dot ${a.connected?'green':'red'}"></span> ${PF[p].name} ${a.connected?('подключён'+(a.login?' · '+a.login:'')):'не подключён'}</div>`;
  }).join('');
  const side=$('#side-accts');
  if(side) side.innerHTML=['funpay','playerok'].map(p=>{
    const a=state.accounts[p]||{};
    return `<div class="side-acct"><span class="dot ${a.connected?'green':'red'}"></span> ${PF[p].name}${a.connected&&a.login?' · '+a.login:''}</div>`;
  }).join('');
  const dc=$('#demo-chip');
  if(dc){
    const live=['funpay','playerok'].filter(p=>(state.accounts[p]||{}).connected);
    dc.textContent = live.length ? 'LIVE · '+live.map(p=>PF[p].name).join(' + ') : 'Нет подключённых площадок · данные не загружены';
    dc.style.color = live.length ? 'var(--ok)' : 'var(--muted)';
    dc.style.background = live.length ? 'rgba(52,211,153,.1)' : 'rgba(139,149,171,.08)';
    dc.style.borderColor = live.length ? 'rgba(52,211,153,.35)' : 'rgba(139,149,171,.22)';
  }
}
function renderBellCount(){
  const el=$('#bell-count');
  el.textContent = state.alerts.length;
  el.classList.toggle('hidden', state.alerts.length===0);
}
function renderClock(){
  const d=new Date();
  $('#clock').textContent = d.toLocaleTimeString('ru-RU');
}

const VIEWS = {};
function render(){
  state.view = (location.hash || '#dashboard').slice(1);
  if(!TITLES[state.view]) state.view='dashboard';
  $('#view-title').textContent = TITLES[state.view];
  $('#view').innerHTML = VIEWS[state.view]();
  renderNav(); renderBellCount(); renderChips();
  if(state.view==='orders'){ bindDnD(); bindOrders(); }
  if(state.view==='goods') bindGoods();
  if(state.view==='chats') bindChat();
  if(state.view==='analytics') bindCalc();
}

/* ================= ПЛАШКИ ПЛОЩАДОК (каталоги) ================= */
function pfCard(p){
  const a=state.accounts[p]||{};
  const s=state.stats||{};
  const rev=(s.revPf||{})[p]||0, net=(s.netPf||{})[p]||0, netw=(s.netWPf||{})[p]||0;
  const cnt=state.orders.filter(o=>o.platform===p&&o.real!==false).length;
  const b=p==='funpay'?{cls:'fp',letter:'F',name:'FunPay'}:{cls:'po',letter:'P',name:'Playerok'};
  return `<div class="pf-card ${b.cls}">
    <div class="pf-head">
      <div class="pf-ava">${/^https?:/.test(a.avatar||'')?`<img src="${a.avatar}" alt="${b.name}">`:b.letter}</div>
      <div class="pf-id">
        <div class="pf-name">${b.name}</div>
        <div class="pf-status ${a.connected?'on':''}">${a.connected?'подключён'+(a.login?' · '+a.login:''):'не подключён'}</div>
      </div>
    </div>
    <div class="pf-stats">
      <div><span>Сделок</span><b>${cnt}</b></div>
      <div><span>Выручка</span><b>${fmt(rev)}</b></div>
      <div><span>На руки</span><b class="ok">${fmt(net)}</b></div>
      <div><span>На карту</span><b>${fmt(netw)}</b></div>
    </div>
    <div class="pf-actions">
      <button class="btn ghost small" data-act="pfcatalog" data-p="${p}">📦 Каталог заказов</button>
      ${a.connected?'':`<button class="btn small" data-act="nav" data-view="settings">Подключить</button>`}
    </div>
  </div>`;
}

/* ================= РЕНДЕР: ДАШБОРД ================= */
VIEWS.dashboard = function(){
  const s = state.stats||{};
  const active = (s.active!=null? s.active : state.orders.filter(o=>o.status==='new'||o.status==='sent').length);
  const disputes = (s.disputes!=null? s.disputes : state.orders.filter(o=>o.status==='dispute').length);
  const revPf = s.revPf || {};
  const netPf = s.netPf || {};
  const fpRev = revPf.funpay||0, poRev = revPf.playerok||0, totRev = fpRev+poRev;
  const fpShare = totRev? Math.round(fpRev*100/totRev) : 0;
  const avg = s.doneTotal? Math.round((s.revTotal||0)/s.doneTotal) : 0;
  const net = s.netTotal||0;
  const netW = s.netWTotal||0;
  const wPf = s.netWPf||{};
  const feeSum = (s.revTotal||0) - net;
  const wSum = net - netW;
  const wf = p => (state.wfees||{})[p]||0;
  /* Только реальные сделки FunPay и Playerok — никаких демо-данных */
  const REAL_PF = ['funpay','playerok'];
  const realOrders = state.orders.filter(o=>REAL_PF.includes(o.platform) && o.real!==false);
  const byLot = {};
  for(const o of realOrders){
    if(o.status!=='done') continue;
    const k = o.lot||'?';
    byLot[k] = (byLot[k]||0) + (o.price||0);
  }
  const top = Object.entries(byLot).sort((a,b)=>b[1]-a[1]).slice(0,5);
  const maxTop = top.length? top[0][1] : 1;
  const last = realOrders.slice(0,7);
  return `
  <div class="pf-cards">${pfCard('funpay')}${pfCard('playerok')}</div>
  <div class="grid kpis">
    <div class="card kpi" style="--kpi-accent:#38bdf8"><div class="lbl"><span class="kpi-ic">📦</span>Всего сделок</div><div class="val">${s.orders||0}</div><div class="delta neu">чатов: ${s.chats||0}</div></div>
    <div class="card kpi" style="--kpi-accent:#34d399"><div class="lbl"><span class="kpi-ic">💰</span>Выручка</div><div class="val">${fmt(s.revTotal||0)}</div><div class="delta neu">завершено: ${s.doneTotal||0}</div></div>
    <div class="card kpi" style="--kpi-accent:#a78bfa"><div class="lbl"><span class="kpi-ic">✅</span>На руки</div><div class="val">${fmt(net)}</div><div class="delta ${feeSum?'down':'neu'}">${feeSum?`комиссия −${fmt(feeSum)} · вывод −${fmt(wSum)}`:'после комиссии'}</div></div>
    <div class="card kpi" style="--kpi-accent:#fbbf24"><div class="lbl"><span class="kpi-ic">⚙️</span>В работе</div><div class="val">${active}</div><div class="delta ${disputes?'down':'neu'}">${disputes?`⚠ возврат/спор: ${disputes}`:'возвратов нет'}</div></div>
    <div class="card kpi" style="--kpi-accent:#f87171"><div class="lbl"><span class="kpi-ic">💬</span>Непрочитано</div><div class="val">${s.unread||0}</div><div class="delta neu">средний чек: ${fmt(avg)}</div></div>
  </div>
  <div class="grid row2">
    <div class="card">
      <h3>Топ-5 лотов по выручке</h3>
      ${top.length? top.map(([lot,v])=>`
        <div style="margin:11px 0">
          <div style="display:flex;justify-content:space-between;gap:10px;font-size:12.5px;margin-bottom:5px">
            <span style="color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${lot}</span>
            <b style="color:var(--text);flex:none">${fmt(v)}</b>
          </div>
          <div class="mini-track"><div class="mini-fill" style="width:${Math.max(4,Math.round(v/maxTop*100))}%"></div></div>
        </div>`).join('')
      : '<div class="kempty">Пока нет завершённых сделок</div>'}
    </div>
    <div class="card">
      <h3>Выручка по площадкам</h3>
      <div class="donut-wrap">
        ${donut([{v:fpShare,color:'#3b82f6',name:'funpay'},{v:totRev?100-fpShare:0,color:'#8b5cf6',name:'playerok'}])}
        <div class="dn-legend">
          <div><span class="dot" style="display:inline-block;background:#3b82f6;margin-right:6px"></span>FunPay <b>${fmt(fpRev)}</b>
            <div class="dn-sub">на руки ${fmt((netPf.funpay||0))} (−${state.fees.funpay}%) · на карту ${fmt(wPf.funpay||0)} (−${wf('funpay')}%)</div></div>
          <div><span class="dot" style="display:inline-block;background:#8b5cf6;margin-right:6px"></span>Playerok <b>${fmt(poRev)}</b>
            <div class="dn-sub">на руки ${fmt((netPf.playerok||0))} (−${state.fees.playerok}%) · на карту ${fmt(wPf.playerok||0)} (−${wf('playerok')}%)</div></div>
        </div>
      </div>
      <div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--border);display:flex;flex-direction:column;gap:7px;font-size:12.5px">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="color:var(--muted)">На руки после комиссии</span>
          <b style="color:var(--ok);font-size:16px">${fmt(net)}</b>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="color:var(--muted)">После вывода на карту</span>
          <b style="color:var(--text);font-size:14px">${fmt(netW)}</b>
        </div>
      </div>
    </div>
  </div>
  <div class="grid row2e">
    <div class="card">
      <h3>⚠ Требует внимания</h3>
      ${state.alerts.length ? state.alerts.slice(0,4).map(a=>`
        <div class="alert-item"><span class="ai">${a.icon}</span><div><div class="at">${a.text}</div><div class="atime">${ago(a.mins)}</div></div></div>`).join('')
      : '<div class="kempty">Всё спокойно 🎉</div>'}
    </div>
    <div class="card">
      <h3>Последние заказы</h3>
      ${last.length? last.map(o=>`
        <div class="last-order" style="cursor:pointer" data-act="order" data-id="${o.id}">
          ${pfBadge(o.platform)}
          <div class="lo-info"><div class="lo-title">${o.lot}</div><div class="lo-sub">${o.game} · ${o.buyer}</div></div>
          ${stPill(o.status)}
          <div class="lo-price">${fmt(o.price)}</div>
        </div>`).join('')
      : '<div class="kempty">Заказов пока нет — появятся, как только площадка подключится</div>'}
    </div>
  </div>`;
};

/* ================= РЕНДЕР: ЗАКАЗЫ (КАНБАН) ================= */
VIEWS.orders = function(){
  const TABS = {active:['new','sent'], done:['done'], dispute:['dispute'], all:['new','sent','done','dispute']};
  const tab = TABS[state.ordTab] ? state.ordTab : 'all';
  const cnt = k => TABS[k].reduce((a,s)=>a+state.orders.filter(o=>o.status===s).length,0);
  const seg = [['active','Действующие'],['done','Завершённые'],['dispute','Споры'],['all','Все']].map(([k,l])=>
    `<button class="mode-btn ${tab===k?'active':''}" data-act="ordtab" data-tab="${k}">${l} · ${cnt(k)}</button>`).join('');
  const cols = TABS[tab].map(s=>{
    const q=(state.ordQ||'').trim().toLowerCase();
    const pfF=state.pfF||'';
    const list = state.orders.filter(o=>o.status===s && (!pfF || o.platform===pfF) && (!q ||
      [o.lot,o.buyer,o.game,String(o.ext_id||''),String(o.id)].join(' ').toLowerCase().includes(q)));
    const sum = list.reduce((a,o)=>a+o.price,0);
    return `<div class="kcol" data-status="${s}">
      <div class="kcol-head">
        <span class="dot" style="background:${ST[s].color}"></span>
        <span class="kt">${ST[s].title}</span>
        <span class="kc">${list.length}</span>
      </div>
      <div class="kcol-body">
        ${list.length? list.map(o=>`
          <div class="kcard" draggable="true" data-id="${o.id}" data-pf="${o.platform}" data-act="order">
            <div class="kcard-top">${pfBadge(o.platform)} ${o.auto?'<span class="auto-badge">⚡ авто</span>':''}</div>
            <div class="kcard-lot">${o.lot}</div>
            <div class="kcard-game">${o.game} · ${o.buyer} · #${o.id}</div>
            <div class="kcard-bot"><span class="kcard-price" data-p="${o.price}">${fmt(o.price)}</span><span class="kcard-time">${ago(o.mins)}</span></div>
          </div>`).join('')
        : '<div class="kempty">Пусто — перетащите заказ сюда</div>'}
      </div>
      <div class="ksum" style="padding:0 15px 12px;color:var(--dim);font-size:11px">Σ ${fmt(sum)}</div>
    </div>`;
  }).join('');
  return `<div class="mode-seg" style="margin-top:0;margin-bottom:10px">${seg}</div>
  <div class="orders-tools">
    <svg class="ot-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
    <input id="ord-q" placeholder="Поиск по заказам: лот, покупатель, игра, № сделки…" value="${(state.ordQ||'').replace(/"/g,'&quot;')}">
    ${state.pfF?`<span class="ot-chip">${PF[state.pfF].name} <i data-act="pfclear" title="Показать все площадки">✕</i></span>`:''}
    <span class="ot-clear ${state.ordQ?'':'hidden'}" data-act="ordclear" title="Сбросить поиск">✕</span>
  </div>
  <div style="color:var(--muted);font-size:12.5px;margin-bottom:12px">«Действующие» — новые и отправленные сделки, «Завершённые» — закрытые, «Споры» — проблемные. Все площадки FunPay и Playerok в одной доске; на ПК карточки можно перетаскивать между колонками.</div><div class="kanban">${cols}</div>`;
};
function bindDnD(){
  $$('.kcard').forEach(c=>{
    c.addEventListener('dragstart', ev=>{ ev.dataTransfer.setData('text/plain', c.dataset.id); ev.stopPropagation(); setTimeout(()=>c.classList.add('dragging'),0); });
    c.addEventListener('dragend', ()=>c.classList.remove('dragging'));
  });
  $$('.kcol').forEach(col=>{
    col.addEventListener('dragover', ev=>{ ev.preventDefault(); col.classList.add('over'); });
    col.addEventListener('dragleave', ()=>col.classList.remove('over'));
    col.addEventListener('drop', ev=>{
      ev.preventDefault(); col.classList.remove('over');
      const id = +ev.dataTransfer.getData('text/plain'), to = col.dataset.status;
      const o = state.orders.find(x=>x.id===id);
      if(o && o.status!==to){ o.status=to; o.mins=0; api('move',{id,to}); toast(`Заказ #${id} → «${ST[to].title}»`,'ok','📦'); render(); }
    });
  });
}

/* ================= РЕНДЕР: СООБЩЕНИЯ ================= */
function chatAva(name){
  let h=0; for(const ch of name) h=(h*31+ch.charCodeAt(0))%360;
  return `background:hsl(${h},55%,42%)`;
}
VIEWS.chats = function(){
  const all = state.chats;
  const pf = state.chatPf||'';
  const cnt = p => all.filter(ch=>ch.platform===p).length;
  const seg = `<div class="chat-pf-seg">
    <button class="cpf-btn ${!pf?'active':''}" data-act="chatpf" data-pf="">Все · ${all.length}</button>
    <button class="cpf-btn ${pf==='playerok'?'active':''}" data-act="chatpf" data-pf="playerok">🟣 Playerok · ${cnt('playerok')}</button>
    <button class="cpf-btn ${pf==='funpay'?'active':''}" data-act="chatpf" data-pf="funpay">🔵 FunPay · ${cnt('funpay')}</button>
  </div>`;
  if(!all.length){
    // реальных переписок пока нет — показываем честную пустоту, а не выдуманный чат
    return `<div class="card"><h3>Сообщения</h3>
      <div class="kempty">Переписок пока нет. Подключите площадку в разделе «Настройки» —
      чаты покупателей с FunPay и Playerok появятся здесь.</div></div>`;
  }
  const shown = pf? all.filter(ch=>ch.platform===pf) : all;
  const c = shown.find(x=>x.id===state.activeChat) || shown[0];
  if(!c){
    return `<div class="chats-wrap"${state.chatOpen?' data-open':''}>
      <div class="chat-list">${seg}<div class="kempty" style="padding:20px">Переписок этой площадки пока нет — переключи режим выше.</div></div>
      <div class="chat-main"><div class="kempty" style="padding:20px">Выбери переписку из списка.</div></div>
    </div>`;
  }
  const list = shown.map(ch=>{
    const lm = (ch.msgs&&ch.msgs.length)? ch.msgs[ch.msgs.length-1] : {from:'',text:'',mins:0};
    return `<div class="chat-item ${ch.id===c.id?'active':''}" data-act="chat" data-id="${ch.id}">
      <div class="chat-ava" style="${chatAva(ch.buyer)}">${ch.buyer[0].toUpperCase()}</div>
      <div class="ci-body">
        <div class="ci-top"><span class="ci-name">${ch.buyer}</span><span class="ci-time">${clockStr(lm.mins)}</span></div>
        <div class="ci-last">${lm.from==='me'||lm.from==='auto'?'Вы: ':''}${lm.text||'—'}</div>
      </div>
      ${ch.unread?`<span class="ci-unread">${ch.unread}</span>`:''}
    </div>`;
  }).join('');
  const msgs = (c.msgs||[]).map(m=>`<div class="msg ${m.from}">${m.text.replace(/</g,'&lt;')}<div class="mt">${clockStr(m.mins)}</div></div>`).join('');
  return `<div class="chats-wrap"${state.chatOpen?' data-open':''}>
    <div class="chat-list">${seg}${list}</div>
    <div class="chat-main">
      <div class="chat-head">
        <div class="chat-back" data-act="chatback" title="Назад к списку переписок">←</div>
        <div class="chat-ava" style="${chatAva(c.buyer)}">${c.buyer[0].toUpperCase()}</div>
        <div><div class="ch-name">${c.buyer} ${pfBadge(c.platform)}</div><div class="ch-sub">${c.lot} · ${c.game}</div></div>
      </div>
      <div class="chat-msgs" id="chat-msgs">${msgs}</div>
      <div class="tpl-row">${TEMPLATES.map((t,i)=>`<div class="tpl" data-act="tpl" data-i="${i}" title="${t}">${t}</div>`).join('')}</div>
      <div class="chat-input">
        <input id="msg-input" placeholder="Ответить покупателю… (ответ уйдёт в чат ${PF[c.platform].name})" value="${state.draft.replace(/"/g,'&quot;')}">
        <button class="btn" data-act="send">Отправить</button>
      </div>
    </div>
  </div>`;
};
function filterOrdersDom(){
  const q=(state.ordQ||'').trim().toLowerCase();
  $$('.kcol').forEach(col=>{
    let shown=0, sum=0;
    $$('.kcard',col).forEach(card=>{
      const pfF=state.pfF||'';
      const hit=(!pfF || card.dataset.pf===pfF) && (!q || card.textContent.toLowerCase().includes(q));
      card.style.display=hit?'':'none';
      if(hit){ shown++; const p=card.querySelector('.kcard-price'); if(p) sum+=+(p.dataset.p||0); }
    });
    const kc=col.querySelector('.kc'); if(kc) kc.textContent=shown;
    const ks=col.querySelector('.ksum'); if(ks) ks.textContent='Σ '+fmt(sum);
  });
}
function bindOrders(){
  const inp=$('#ord-q');
  if(inp) inp.addEventListener('input',()=>{
    state.ordQ=inp.value; filterOrdersDom();
    const cl=$('.ot-clear'); if(cl) cl.classList.toggle('hidden',!inp.value);
  });
}
function bindChat(){
  const box=$('#chat-msgs'); if(box) box.scrollTop=box.scrollHeight;
  const inp=$('#msg-input');
  if(inp){
    inp.addEventListener('keydown', e=>{ if(e.key==='Enter') sendMessage(); });
    inp.focus();
  }
}
function sendMessage(){
  const inp=$('#msg-input'); if(!inp) return;
  const text=inp.value.trim(); if(!text) return;
  const c=state.chats.find(x=>x.id===state.activeChat);
  if(!c){ toast('Чат не выбран','warn','💬'); return; }
  (c.msgs=c.msgs||[]).push({from:'me', text, mins:0});
  state.draft='';
  api('message',{id:c.id,text});
  render();
}

/* ================= РЕНДЕР: ТОВАРЫ (выставление и конфигурация) ================= */
function prodFee(p){
  if(p.platform==='playerok'){
    const c=PO_CAT_FEES.find(c=>c.id===p.cat);
    return c? c.fee : +(state.fees.playerok||0);
  }
  return +(state.fees.funpay||0);
}
function prodEcon(p){
  const fee=prodFee(p), wfee=+((state.wfees||{})[prodPF(p)]||0);
  const price=+p.price||0, cost=+p.cost||0;
  const saleFee=Math.round(price*fee/100);
  const net=price-saleFee;
  const wFee=Math.round(net*wfee/100);
  const card=net-wFee;
  const prem=prodPF(p)==='playerok'? poPremium(price,fee) : 0;
  return {fee,wfee,saleFee,net,wFee,card,prem,profit:card-cost};
}
function prodCatName(p){
  if(prodPF(p)==='playerok'){
    const c=PO_CAT_FEES.find(c=>c.id===p.cat);
    return c? c.t : 'категория не выбрана';
  }
  return p.cat||'раздел магазина';
}
function prodCard(p){
  const e=prodEcon(p), r=recommendDest(p);
  const dest=p.dest? pfBadge(p.dest) : `<span class="prod-dest" data-act="prodplace" data-id="${p.id}" title="Куда ставить: ${r.dest==='funpay'?'FunPay':'Playerok'} — нажми, чтобы поставить">→ ${r.dest==='funpay'?'FunPay':'Playerok'} ${r.score}%</span>`;
  return `<div class="prod-card">
    <div class="prod-top">${pfBadge(p.platform)}${dest}
      <span class="prod-cat" title="Комиссия площадки с продажи">−${e.fee}%</span>
      <span class="prod-status ${p.status}">${p.status==='listed'?'выставлен':'черновик'}</span></div>
    <div class="prod-lot">${p.lot}</div>
    <div class="prod-sub">${p.game} · ${prodCatName(p)}</div>
    <div class="prod-econ">
      <div><span>Цена</span><b>${fmt(p.price)}</b></div>
      <div><span>На руки</span><b class="ok">${fmt(e.net)}</b></div>
      <div><span>На карту</span><b>${fmt(e.card)}</b></div>
      <div><span>Прибыль</span><b class="${e.profit>0?'ok':'bad'}">${fmt(e.profit)}</b></div>
    </div>
    <div class="prod-note">комиссия −${fmt(e.saleFee)} · вывод −${fmt(e.wFee)}${p.platform==='playerok'?` · премиум ${fmt(e.prem)}/сделка`:''}</div>
    <div class="prod-actions">
      <button class="btn ghost small" data-act="prodplace" data-id="${p.id}" title="Поставить на рекомендованную площадку">🎯</button>
      <button class="btn ghost small" data-act="prodcopy" data-id="${p.id}" title="Скопировать заголовок и описание">📋</button>
      <button class="btn ghost small" data-act="prodopen" data-id="${p.id}" title="Скопировать данные и открыть страницу публикации">🚀 Публикация</button>
      <button class="btn ghost small" data-act="prodedit" data-id="${p.id}" title="Настроить">✏️</button>
      <button class="btn danger small" data-act="proddel" data-id="${p.id}" title="Удалить">🗑</button>
    </div>
  </div>`;
}
VIEWS.goods = function(){
  const q=(state.prodQ||'').trim().toLowerCase();
  const list=(state.products||[]).filter(p=>!q || [p.lot,p.game,p.platform,prodCatName(p)].join(' ').toLowerCase().includes(q));
  const drafts=(state.products||[]).filter(p=>p.status==='draft').length;
  return `<div class="orders-tools">
    <svg class="ot-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
    <input id="prod-q" placeholder="Поиск по товарам…" value="${(state.prodQ||'').replace(/"/g,'&quot;')}">
    <button class="btn ghost small" data-act="aiopen" title="AI прочитает страницы по ссылкам и создаст черновики">🤖 AI из ссылок</button>
    <button class="btn ghost small" data-act="prodimport">📥 Пак (JSON)</button>
    <button class="btn ghost small" data-act="prodauto" title="Автоматически расставить все товары по площадкам">🎯 Куда ставить: авто</button>
    <button class="btn small" data-act="prodadd">➕ Товар</button>
  </div>
  <div style="color:var(--muted);font-size:12.5px;margin-bottom:12px">Каталог лотов: черновиков ${drafts} · всего ${(state.products||[]).length}. Карточку можно заполнить вручную или прислать мне в чат ссылку/пак ссылок — я определю платформу и категорию, напишу заголовок с описанием, посчитаю цену и маржу и загружу сюда готовым JSON.</div>
  ${list.length? `<div class="prod-grid">${list.map(prodCard).join('')}</div>`
    : '<div class="kempty">Товаров пока нет. Нажми «➕ Товар», импортируй пакет JSON или пришли мне ссылки — подготовлю и загружу.</div>'}`;
};
function bindGoods(){
  const inp=$('#prod-q');
  if(inp) inp.addEventListener('input',()=>{ state.prodQ=inp.value; render(); });
}
function openProdForm(id){
  const p = id? (state.products||[]).find(x=>x.id===id) : null;
  const v = k => p? (p[k]??'') : '';
  showModal(`
    <div class="modal-head"><div class="mh-t">${p?'Настроить товар':'Новый товар'}</div><div class="modal-x" data-act="closeModal">✕</div></div>
    <div class="modal-body">
      <div class="set-row"><label>Площадка</label>
        <select id="pf-sel">
          <option value="playerok" ${v('platform')!=='funpay'?'selected':''}>Playerok</option>
          <option value="funpay" ${v('platform')==='funpay'?'selected':''}>FunPay</option>
        </select></div>
      <div class="set-row"><label>Игра / приложение</label><input id="pf-game" list="pf-games-dl" value="${v('game')}" placeholder="Начни печатать: Pu → PUBG Mobile, PUBG (ПК)…"><datalist id="pf-games-dl"></datalist></div>
      <div class="set-row" id="cat-po-row"><label>Категория Playerok (влияет на комиссию)</label>
        <select id="pf-cat">${PO_CAT_FEES.map(c=>`<option value="${c.id}" ${v('cat')===c.id?'selected':''}>${c.t} — ${c.fee}%</option>`).join('')}</select></div>
      <div class="set-row" id="cat-fp-row" style="display:none"><label>Раздел FunPay</label><input id="pf-cat-fp" list="pf-sects-dl" value="${v('cat')}" placeholder="раздел магазина"><datalist id="pf-sects-dl">${FP_SECTS.map(s=>`<option value="${s}">`).join('')}</datalist></div>
      <div class="set-row"><label>Заголовок лота</label><input id="pf-lot" value="${v('lot')}" placeholder="Кристаллы 980+160 · мгновенно"></div>
      <div class="set-row"><label>Описание</label><textarea id="pf-desc" rows="5" placeholder="Что входит, как передаётся, сроки, гарантии…">${v('desc')}</textarea></div>
      <div class="set-row"><label>Цена, ₽</label><input type="number" id="pf-price" min="0" value="${v('price')||''}"></div>
      <div class="set-row"><label>Себестоимость, ₽</label><input type="number" id="pf-cost" min="0" value="${v('cost')||''}"></div>
      <div class="set-row"><label>Куда ставить товар</label>
        <select id="pf-dest">
          <option value="">— выбрать автоматически —</option>
          <option value="playerok" ${v('dest')==='playerok'?'selected':''}>Playerok</option>
          <option value="funpay" ${v('dest')==='funpay'?'selected':''}>FunPay</option>
        </select></div>
      <div class="hint" id="pf-rec"></div>
      <div class="set-row"><label>Статус</label>
        <select id="pf-status">
          <option value="draft" ${v('status')!=='listed'?'selected':''}>черновик</option>
          <option value="listed" ${v('status')==='listed'?'selected':''}>выставлен</option>
        </select></div>
      <div class="set-row"><label>Ссылка-источник</label><input id="pf-url" value="${v('url')}" placeholder="откуда взят товар (если есть)"></div>
      <div class="hint" id="pf-econ"></div>
    </div>
    <div class="modal-actions"><button class="btn" id="pf-save">Сохранить</button></div>`);
  const upd=()=>{
    const pf=$('#pf-sel').value;
    $('#cat-po-row').style.display = pf==='playerok'? '':'none';
    $('#cat-fp-row').style.display = pf==='funpay'? '':'none';
    const dl=$('#pf-games-dl');
    if(dl){   // подсказки игр меняются вместе с площадкой
      const extra=(state.products||[]).filter(x=>x.platform===pf).map(x=>x.game).filter(Boolean);
      dl.innerHTML=[...new Set([...(GAMES_PF[pf]||[]),...extra])]
        .map(g=>`<option value="${g.replace(/"/g,'&quot;')}">`).join('');
    }
    const price=+($('#pf-price').value||0), cost=+($('#pf-cost').value||0);
    const fake={platform:pf, dest:$('#pf-dest').value, cat: pf==='playerok'? $('#pf-cat').value : '',
      lot:$('#pf-lot').value, desc:$('#pf-desc').value, game:$('#pf-game').value, price, cost};
    const e=prodEcon(fake);
    $('#pf-econ').innerHTML=`Комиссия продажи −${e.fee}% (${fmt(e.saleFee)}), вывод −${e.wfee}% (${fmt(e.wFee)})`+
      (prodPF(fake)==='playerok'?`, премиум ${fmt(e.prem)}/сделка`:'')+
      `. На руки ${fmt(e.net)}, на карту ${fmt(e.card)}, прибыль ${fmt(e.profit)}.`;
    const r=recommendDest(fake), d=$('#pf-dest').value;
    $('#pf-rec').innerHTML=`🎯 Куда ставить: <b>${r.dest==='funpay'?'FunPay':'Playerok'}</b> (${r.score}%)${d&&d!==r.dest?' — у тебя выбрано другое, оставим твой выбор':''}. ${r.why.join('; ')||'универсальный товар'}.`;
  };
  $('#pf-sel').onchange=upd; $('#pf-cat').onchange=upd; $('#pf-dest').onchange=upd;
  $('#pf-price').oninput=upd; $('#pf-cost').oninput=upd;
  $('#pf-lot').oninput=upd; $('#pf-game').oninput=upd; upd();
  $('#pf-save').onclick=()=>{
    const pf=$('#pf-sel').value;
    const prod={platform:pf, game:$('#pf-game').value.trim(), lot:$('#pf-lot').value.trim(),
      desc:$('#pf-desc').value.trim(), price:+($('#pf-price').value||0), cost:+($('#pf-cost').value||0),
      status:$('#pf-status').value, url:$('#pf-url').value.trim(), dest:$('#pf-dest').value,
      cat: pf==='playerok'? $('#pf-cat').value : $('#pf-cat-fp').value.trim()};
    if(!prod.lot){ toast('Укажи заголовок лота','warn','✏️'); return; }
    if(p) api('produpd',{id:p.id, product:prod}); else api('prodadd',{product:prod});
    hideModal(); toast(p?'Товар обновлён':'Товар добавлен в каталог','ok','📦');
  };
}
function openProdImport(){
  showModal(`
    <div class="modal-head"><div class="mh-t">Импорт пакета товаров</div><div class="modal-x" data-act="closeModal">✕</div></div>
    <div class="modal-body">
      <div class="hint">Вставь JSON-массив карточек (формат выдаёт ИИ-подготовка из чата):<br>
      [{"platform":"playerok","game":"…","cat":"donate","lot":"…","desc":"…","price":150,"cost":60}]<br>
      cat для Playerok: donate/topup/lic/subs (10%) или acc/skins/keys/boost/other (20%).</div>
      <div class="set-row"><textarea id="imp-json" rows="9" placeholder='[{"platform":"playerok","cat":"donate","lot":"…","price":100}]'></textarea></div>
    </div>
    <div class="modal-actions"><button class="btn" id="imp-go">📥 Импортировать</button></div>`);
  $('#imp-go').onclick=()=>{
    try{
      let d=JSON.parse($('#imp-json').value);
      const items=Array.isArray(d)? d : (d.items||[]);
      if(!items.length) throw 0;
      api('prodimport',{items});
      hideModal(); toast(`Импортировано: ${items.length}`,'ok','📥');
    }catch(e){ toast('Не удалось разобрать JSON','bad','⚠️'); }
  };
}
function copyProd(id){
  const p=(state.products||[]).find(x=>x.id===id); if(!p) return;
  const e=prodEcon(p);
  const text=`${p.lot}\n\n${p.desc||''}\n\n💰 Цена: ${fmt(p.price)}\n🎮 ${p.game}\n📂 ${prodCatName(p)} (−${e.fee}%)`;
  (navigator.clipboard? navigator.clipboard.writeText(text) : Promise.reject()).then(
    ()=>toast('Заголовок и описание скопированы','ok','📋'),
    ()=>toast('Буфер недоступен — скопируй вручную из карточки','warn','📋'));
}
function openProd(id){
  const p=(state.products||[]).find(x=>x.id===id); if(!p) return;
  copyProd(id);
  const url = p.platform==='funpay'? 'https://funpay.com/seller/lots/' : 'https://playerok.com/';
  setTimeout(()=>window.open(url,'_blank'),250);
  toast('Данные скопированы — вставь их на странице публикации','ok','🚀');
}

/* ================= ФОН ПРИЛОЖЕНИЯ (готовые пресеты) ================= */
const BG_PRESETS=[
  {id:'space', t:'Космос', d:'звёзды, планеты и туманности — единственный фон'},
];
function setSky(id){
  const el=$('#sky'); if(!el) return;
  el.className='';   // фон один — космос, классы больше не нужны
}
function applyBG(){ setSky('space'); }
function openBG(){
  const cur=localStorage.getItem('sellhub_bg')||'sky';
  showModal(`
    <div class="modal-head"><div class="mh-t">🎨 Фон приложения</div><div class="modal-x" data-act="closeModal">✕</div></div>
    <div class="modal-body">
      <div class="hint">Готовые варианты — ничего настраивать не нужно, просто выбери.</div>
      <div class="bg-grid">${BG_PRESETS.map(p=>`
        <button class="bg-pick bg-${p.id}${p.id===cur?' active':''}" data-act="bgpick" data-bg="${p.id}">
          <span class="bg-prev"><i></i></span>
          <span class="bg-name">${p.t}</span><span class="bg-desc">${p.d}</span>
        </button>`).join('')}</div>
      <div class="set-row"><label class="sw"><input type="checkbox" id="bg-sky-on"${cur==='sky'?' checked':''}> <span>☁️ плывущие облака (только на фоне «Небо»)</span></label></div>
    </div>`);
  $('#bg-sky-on').onchange=e=>{ localStorage.setItem('sellhub_clouds',e.target.checked?'1':'0'); document.body.classList.toggle('no-clouds',!e.target.checked); };
}

/* ================= КУДА СТАВИТЬ ТОВАР: АВТОВЫБОР ПЛОЩАДКИ ================= */
function recommendDest(p){
  const t=((p.lot||'')+' '+(p.desc||'')+' '+(p.game||'')).toLowerCase();
  let po=50, fp=50, why=[];
  const G=[['genshin',14,'Genshin'],['honkai',14,'Honkai'],['wuthering',10,'Wuthering Waves'],['roblox',10,'Roblox'],['brawl',10,'Brawl Stars'],['mobile legends',8,'Mobile Legends'],['valorant',6,'Valorant'],['fortnite',6,'Fortnite'],['standoff',6,'Standoff 2'],['pubg',6,'PUBG'],['free fire',6,'Free Fire'],['clash',6,'Clash']];
  for(const [k,w,n] of G){ if(t.includes(k)){ po+=w; why.push(`${n}: аудитория на Playerok`); } }
  const P=[['донат',10,'донат'],['валюта',8,'игровая валюта'],['подписка',8,'подписка'],['nitro',8,'Nitro'],['plus',6,'Plus'],['аккаунт',6,'аккаунт'],['профиль',5,'профиль'],['скин',5,'скины'],['предмет',4,'предметы'],['буст',6,'буст'],['услуга',5,'услуги'],['пополнен',8,'пополнение баланса']];
  for(const [k,w,n] of P){ if(t.includes(k)){ po+=w; why.push(`«${n}» — профиль Playerok`); } }
  const F=[['steam',12,'Steam'],['ключ',10,'ключи'],['кошелёк',10,'кошельки Steam'],['wallet',8,'кошельки'],['gift',8,'подарочные карты'],['cs2',8,'CS2'],['dota',8,'Dota 2'],['csgo',6,'CS:GO'],['minecraft',6,'Minecraft'],['подарочн',6,'подарочные карты']];
  for(const [k,w,n] of F){ if(t.includes(k)){ fp+=w; why.push(`«${n}» — сильная ниша FunPay`); } }
  const price=+p.price||0;
  if(price>=3000){ fp+=10; why.push('чек от 3000 ₽: на FunPay больше покупателей дорогих лотов'); }
  else if(price>0 && price<=700){ po+=8; why.push('низкий чек: быстрые сделки Playerok'); }
  if(p.cat==='donate'||p.cat==='topup'||p.cat==='subs'||p.cat==='lic'){ po+=10; why.push('категория с комиссией 10% есть только на Playerok'); }
  const cur=p.platform==='funpay'? fp : po;
  if(p.platform==='funpay'){ fp+=5; why.push('учтён твой текущий раздел магазина на FunPay'); }
  else { po+=5; why.push('учтён твой магазин на Playerok'); }
  const win = po>fp? 'playerok' : (fp>po? 'funpay' : (p.platform||'playerok'));
  const sc = win==='playerok'? Math.min(95,50+po-cur+20) : Math.min(95,50+fp-cur+20);
  return {dest:win, score:sc, why:why.slice(0,4)};
}
function prodPF(p){ return p.dest||p.platform; }

/* ================= РЕНДЕР: АНАЛИТИКА ================= */
VIEWS.analytics = function(){
  const topLots = [...state.orders].filter(o=>o.status==='done').sort((a,b)=>b.price-a.price).slice(0,5);
  const cnt = st => state.orders.filter(o=>o.status===st).length;
  const rows = [['Завершено','done'],['Новые','new'],['Выдано, ждёт подтверждения','sent'],['Споры','dispute']];
  const tot = state.orders.length || 1;
  const revPf = (state.stats&&state.stats.revPf)||{};
  return `
  <div class="grid row2">
    <div class="card">
      <h3>Топ завершённых сделок</h3>
      ${topLots.length? topLots.map(o=>`<div class="last-order">${pfBadge(o.platform)}<div class="lo-info"><div class="lo-title">${o.lot}</div><div class="lo-sub">${o.buyer}</div></div><div class="lo-price">${fmt(o.price)}</div></div>`).join('') : '<div class="kempty">Пока нет завершённых сделок</div>'}
      <div style="margin-top:14px">
        <h3 style="margin-bottom:8px">Калькулятор: продажа → на руки → на карту</h3>
        <div class="calc2">
          <div class="calc2-in">
            <input type="number" id="calc-sum" value="1000" min="0" inputmode="decimal" aria-label="Сумма продажи">
            <select id="calc-pf" aria-label="Площадка">
              <option value="funpay">FunPay</option>
              <option value="playerok" selected>Playerok</option>
            </select>
          </div>
          <div class="calc2-in">
            <select id="calc-cat" aria-label="Категория Playerok">
              ${PO_CAT_FEES.map(c=>`<option value="${c.id}">${c.t} — ${c.fee}%</option>`).join('')}
            </select>
            <label class="calc2-prem"><input type="checkbox" id="calc-prem"> премиум-размещение (топ категории)</label>
          </div>
          <div class="calc2-steps" id="calc-steps"></div>
          <div class="hint" style="margin-top:8px">Ставки: FunPay — продажа ${state.fees.funpay}% (публично 3–10%, обычно 5,5%), вывод ${(state.wfees||{}).funpay||0}% (1–5% по способу). Playerok — продажа ${state.fees.playerok}% (донат/пополнения 10%, остальное 20%), вывод ${(state.wfees||{}).playerok||0}% (СБП/карта РФ 6%, ин. карта 10%, USDT 4%). Свои значения — в «Настройках».</div>
        </div>
      </div>
    </div>
    <div class="card">
      <h3>Статусы сделок</h3>
      ${rows.map(([t,st])=>`
        <div class="hbar-row"><div class="hbar-name">${t}</div>
        <div class="hbar-track"><div class="hbar-fill" style="width:${(cnt(st)/tot*100).toFixed(1)}%"></div></div>
        <div class="hbar-val">${cnt(st)}</div></div>`).join('')}
      <div class="rev-legend" style="margin-top:12px">
        <span>Всего сделок: <b style="color:var(--text)">${state.orders.length}</b></span>
        <span>Средний чек: <b style="color:var(--text)">${fmt(state.stats&&state.stats.doneTotal? Math.round(state.stats.revTotal/state.stats.doneTotal):0)}</b></span>
      </div>
      <h3 style="margin:18px 0 8px">Выручка по площадкам (завершённые)</h3>
      ${Object.keys(revPf).length? Object.entries(revPf).map(([p,v])=>`
        <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border);font-size:13px">
          <span>${pfBadge(p)} ${PF[p]?PF[p].name:p}</span>
          <span style="text-align:right"><b style="color:var(--text)">${fmt(v)}</b> <span style="color:var(--muted);font-size:11.5px">→ на руки ${fmt((state.stats&&state.stats.netPf||{})[p]||0)} (−${state.fees[p]||0}%) → на карту ${fmt((state.stats&&state.stats.netWPf||{})[p]||0)} (−${(state.wfees||{})[p]||0}%)</span></span>
        </div>`).join('') : '<div class="kempty">Нет завершённых сделок</div>'}
    </div>
  </div>
  <div class="card" style="margin-top:14px">
    <h3>Playerok: категории · ставка · что останется с 1 000 ₽</h3>
    <div class="hint" style="margin-bottom:10px">Ставка зависит от раздела: <b>10%</b> — донат, пополнения, лицензии, подписки; <b>20%</b> — остальное.
      Премиум-размещение держит карточку в топе категории и списывается <b>за каждую сделку</b> (при «Оставить в продаже»): 19–99 ₽ по сетке цен. Вывод — ${ (state.wfees||{}).playerok||6 }% (СБП/карта РФ, мин. 60 ₽; минимум вывода 500 ₽).</div>
    ${PO_CAT_FEES.map(c=>{
      const price=1000, fee=c.fee, w=+((state.wfees||{}).playerok||6);
      const saleFee=Math.round(price*fee/100), net=price-saleFee;
      const wFee=Math.round(net*w/100), card=net-wFee;
      const prem=poPremium(price,fee), cardPrem=card-prem;
      const eff=((price-cardPrem)/price*100).toFixed(1).replace('.',',');
      return `<div class="pocat">
        <div class="pocat-h"><span class="pocat-t">${c.t}</span><span class="pocat-fee ${fee<=10?'low':'high'}">−${fee}%</span></div>
        <div class="pocat-chain">Выставил <b>${fmt(price)}</b> → комиссия −<b>${fmt(saleFee)}</b> → на руки <b>${fmt(net)}</b> → вывод −<b>${fmt(wFee)}</b> → на карту <b class="pos">${fmt(card)}</b></div>
        <div class="pocat-chain dim">+ премиум (топ категории) −<b>${fmt(prem)}</b> → на карту <b class="pos">${fmt(cardPrem)}</b> · итоговая комиссия <b>${eff}%</b> с цены</div>
      </div>`;
    }).join('')}
    <div class="hint" style="margin-top:10px">Сетка премиума за сделку: до 499 ₽ — 19 ₽ (ставка 10%) / 25 ₽ (20%); 500–999 — 25 / ≈37; 1 000–2 499 — 37 / 49; 2 500–4 999 — 49 / ≈75; 5 000–9 999 — 75 / ≈99; от 10 000 — 99 / ≈99+. «≈» — значения 20%-ставки восстановлены по шаблону сетки, проверяйте в кабинете при публикации.</div>
  </div>`;
};
function bindCalc(){
  const upd=()=>{
    const sum=Math.max(0,+($('#calc-sum')?.value||0));
    const pf=$('#calc-pf')?.value||'playerok';
    const catSel=$('#calc-cat'), premBox=$('#calc-prem');
    const isPo = pf==='playerok';
    if(catSel) catSel.style.display = isPo ? '' : 'none';
    if(premBox) premBox.parentElement.style.display = isPo ? '' : 'none';
    let fee, catName='';
    if(isPo){
      const cat = PO_CAT_FEES.find(c=>c.id===(catSel&&catSel.value)) || PO_CAT_FEES[0];
      fee = cat.fee; catName = ' · '+cat.t.split(' (')[0];
    } else fee = +(state.fees.funpay||0);
    const wfee=+((state.wfees||{})[pf]||0);
    const prem = (isPo && premBox && premBox.checked) ? poPremium(sum, fee) : 0;
    const saleFee=Math.round(sum*fee/100);
    const net=sum-saleFee-prem;
    const wFee=Math.round(net*wfee/100);
    const card=net-wFee;
    const eff = sum>0 ? ((sum-card)/sum*100).toFixed(1).replace('.',',') : '0';
    const box=$('#calc-steps'); if(!box) return;
    box.innerHTML=`
      <div class="cs"><span>Цена продажи${catName?` (${catName})`:''}</span><b>${fmt(sum)}</b></div>
      <div class="cs neg"><span>Комиссия сайта за продажу −${fee}%</span><b>−${fmt(saleFee)}</b></div>
      ${prem?`<div class="cs neg"><span>Премиум-размещение (топ категории), за сделку</span><b>−${fmt(prem)}</b></div>`:''}
      <div class="cs"><span>На руки (остаётся на балансе)</span><b class="pos">${fmt(net)}</b></div>
      <div class="cs neg"><span>Комиссия вывода средств −${wfee}%</span><b>−${fmt(wFee)}</b></div>
      <div class="cs total"><span>Придёт на карту / кошелёк</span><b>${fmt(card)}</b></div>
      <div class="cs"><span>Итоговая комиссия с цены (сайт+премиум+вывод)</span><b>${eff}%</b></div>`;
  };
  $('#calc-sum')?.addEventListener('input', upd);
  $('#calc-pf')?.addEventListener('change', upd);
  $('#calc-cat')?.addEventListener('change', upd);
  $('#calc-prem')?.addEventListener('change', upd);
  upd();
}

/* ================= РЕНДЕР: НАСТРОЙКИ ================= */
VIEWS.settings = function(){
  const a=state.accounts;
  const m=state.pfmode||'both';
  return `
  <div class="grid set-grid">
    <div class="card">
      <div class="sec-title">🔀 Режим подключения площадок</div>
      <div class="hint">FunPay и Playerok между собой не конфликтуют — режим нужен, чтобы поставить площадку на паузу: сервер не держит её сессию и не шлёт по ней пуши (например, пока Playerok сбрасывает сессию из-за открытого сайта).</div>
      <div class="mode-seg">
        <button class="mode-btn${m==='both'?' active':''}" data-act="setmode" data-mode="both">Обе площадки</button>
        <button class="mode-btn${m==='funpay'?' active':''}" data-act="setmode" data-mode="funpay">Только FunPay</button>
        <button class="mode-btn${m==='playerok'?' active':''}" data-act="setmode" data-mode="playerok">Только Playerok</button>
      </div>
    </div>
    <div class="card">
      <div class="sec-title">${pfBadge('funpay')} Подключение FunPay</div>
      <div class="status-line">${a.funpay.connected?`<span class="dot green"></span> Подключён · аккаунт <b>${a.funpay.login}</b> · ключ ${a.funpay.key}`:`<span class="dot red"></span> Не подключён${a.funpay.error?` · <span style="color:#fca5a5">${a.funpay.error}</span>`:''}`}</div>
      <div class="set-row"><label>Golden key</label><input type="password" id="fp-key" placeholder="значение cookie golden_key с funpay.com" value="${a.funpay.connected?(a.funpay.key||''):''}"></div>
      <div class="set-row"><label>User-Agent браузера</label><input id="fp-ua" placeholder="Mozilla/5.0 … — из того же браузера, где взят ключ"></div>
      <div class="hint">Где взять ключ: войдите на funpay.com → F12 (DevTools) → Application → Cookies → funpay.com → скопируйте значение <b>golden_key</b>. User-Agent: DevTools → Network → любой запрос → Request Headers → user-agent (или whatmyuseragent.com). Если UA не совпадёт с браузером, FunPay может сбросить сессию. Ключ хранится на вашем сервере (data/credentials.json, в git не попадает) и отправляется только на FunPay.</div>
      <div style="margin-top:12px">${a.funpay.connected?'<button class="btn danger small" data-act="disconnect" data-p="funpay">Отключить</button>':'<button class="btn small" data-act="connect" data-p="funpay">Подключить</button>'}</div>
    </div>
    <div class="card">
      <div class="sec-title">${pfBadge('playerok')} Подключение Playerok</div>
      <div class="status-line">${a.playerok.connected?`<span class="dot green"></span> Подключён · аккаунт <b>${a.playerok.login}</b> · токен ${a.playerok.key}`:`<span class="dot red"></span> Не подключён${a.playerok.error?` · <span style="color:#fca5a5">${a.playerok.error}</span>`:''}`}</div>
      <div class="set-row"><label>Access-токен</label><input type="password" id="po-key" placeholder="eyJ… или вся Cookie-строка из Cookie-Editor (кнопка Copy)" value="${a.playerok.connected?(a.playerok.key||''):''}"></div>
      <div class="set-row"><label>User-Agent браузера</label><input id="po-ua" placeholder="Mozilla/5.0 … — из того же браузера, где взят токен"></div>
      <div class="hint">Где взять токен: playerok.com → F12 → Network → фильтр <b>Fetch/XHR</b> → открой любую страницу сайта (профиль/лоты) → запрос <b>graphql</b> → Request Headers → <b>Authorization</b> («Bearer eyJ…»). Если Authorization в Network не видно: токен лежит в <b>Application → Local Storage → https://playerok.com</b> — ключ с длинным значением, начинающимся на <b>eyJ</b> (JWT). Куки (cf_clearance и т.п.) — это защита Cloudflare, а не вход: по ним подключиться нельзя. User-Agent обязателен, если токен «отклоняется»: Cloudflare сверяет его с браузером, где токен получен (DevTools → Network → любой запрос → user-agent). Панель слушает сделки и чаты через GraphQL + WebSocket, как сам сайт.</div>
      <div style="margin-top:12px">${a.playerok.connected?'<button class="btn danger small" data-act="disconnect" data-p="playerok">Отключить</button>':'<button class="btn small" data-act="connect" data-p="playerok">Подключить</button>'}</div>
    </div>
    <div class="card">
      <div class="sec-title">🔔 Telegram-уведомления</div>
      <div class="set-row"><label>Токен бота</label><input id="tg-bot" placeholder="123456:ABC-DEF…" value="${state.tg.bot}"></div>
      <div class="set-row"><label>Chat ID</label><input id="tg-chat" placeholder="Куда слать уведомления" value="${state.tg.chat}"></div>
      <div class="hint">События: новый заказ · сообщение без ответа 10 мин · спор · остаток товара &lt; 3 · конкурент снизил цену.</div>
      <div style="margin-top:12px"><button class="btn small" data-act="tgtest">Отправить тестовое уведомление</button></div>
    </div>
    <div class="card">
      <div class="sec-title">🪐 Фон приложения</div>
      <div class="hint">Космос: звёзды, планеты и туманности. Единственная тема — настраивать не нужно.</div>
    </div>
    <div class="card">
      <div class="sec-title">💰 Комиссии и автопрайс</div>
      <div class="set-row"><label>FunPay · комиссия с продажи, %</label><input type="number" id="fee-fp" min="0" max="30" step="0.5" value="${state.fees.funpay}"></div>
      <div class="set-row"><label>FunPay · комиссия вывода, %</label><input type="number" id="wfee-fp" min="0" max="30" step="0.5" value="${(state.wfees||{}).funpay??3}"></div>
      <div class="set-row"><label>Playerok · комиссия с продажи, %</label><input type="number" id="fee-po" min="0" max="30" step="0.5" value="${state.fees.playerok}"></div>
      <div class="set-row"><label>Playerok · комиссия вывода, %</label><input type="number" id="wfee-po" min="0" max="30" step="0.5" value="${(state.wfees||{}).playerok??6}"></div>
      <div class="hint">Публичные ставки площадок: FunPay — с продажи обычно 5,5% (по категориям 3–10%), вывод 1–5% в зависимости от способа. Playerok — с продажи 10% (донат, пополнения, лицензии, подписки) или 20% (остальные разделы); вывод 6% на СБП/карту РФ (мин. 60 ₽), 10% иностранная карта, 4% USDT. Подставьте свои фактические проценты — они попадут в дашборд, аналитику, калькулятор и Telegram-бота.</div>
      <div style="margin-top:12px"><button class="btn small" data-act="saveset">Сохранить настройки</button></div>
    </div>
  </div>
  <div class="card" style="margin-top:14px">
    <div class="sec-title">⚠️ Важно</div>
    <div class="hint" style="font-size:12.5px">
      1. FunPay и Playerok не имеют официальных публичных API — подключение идёт через внутренние механизмы сайтов (как у популярных ботов FunPayAPI / PlayerokAPI). Площадки могут менять их; нужен мониторинг и быстрые обновления.<br>
      2. Автоматизация должна вести себя «по-человечески»: разумные интервалы, без спама. Все действия — под ответственность владельца аккаунта.<br>
      3. Панель показывает только реальные данные подключённых площадок: заказы, чаты и суммы берутся с FunPay и Playerok. Ничего не выдумывается — если площадка не подключена, её цифры равны нулю.
    </div>
    <div style="margin-top:12px"><button class="btn small" data-act="reset">Обновить данные</button></div>
  </div>`;
};

/* ================= МОДАЛКА ЗАКАЗА ================= */
function openOrder(id){
  const o = state.orders.find(x=>x.id===id); if(!o) return;
  let actions='';
  if(o.status==='new') actions=`
    <button class="btn" data-act="move" data-id="${o.id}" data-to="sent">📦 Отметить «выдано»</button>
    <button class="btn ghost" data-act="gotochat" data-id="${o.id}">💬 Написать</button>
    <button class="btn danger" data-act="move" data-id="${o.id}" data-to="dispute">Возврат</button>`;
  else if(o.status==='sent') actions=`
    <button class="btn" data-act="move" data-id="${o.id}" data-to="done">✅ Подтвердить завершение</button>
    <button class="btn ghost" data-act="gotochat" data-id="${o.id}">💬 Написать</button>`;
  else if(o.status==='dispute') actions=`
    <button class="btn danger" data-act="move" data-id="${o.id}" data-to="done">💸 Оформить возврат и закрыть</button>
    <button class="btn ghost" data-act="gotochat" data-id="${o.id}">💬 Написать</button>`;
  else actions=`<button class="btn ghost" data-act="gotochat" data-id="${o.id}">💬 Чат с покупателем</button>`;
  const net = Math.round(o.price*(1-state.fees[o.platform]/100));
  $('#modal').innerHTML=`
    <div class="modal-head">${pfBadge(o.platform)}<div class="mh-t">Заказ #${o.id}</div><div class="modal-x" data-act="closeModal">✕</div></div>
    <div class="modal-body">
      <div class="mrow"><span class="mk">Товар</span><span class="mv">${o.lot}</span></div>
      <div class="mrow"><span class="mk">Игра / категория</span><span class="mv">${o.game}</span></div>
      <div class="mrow"><span class="mk">Покупатель</span><span class="mv">${o.buyer}</span></div>
      <div class="mrow"><span class="mk">Цена</span><span class="mv">${fmt(o.price)}</span></div>
      <div class="mrow"><span class="mk">На руки (комиссия ${state.fees[o.platform]}%)</span><span class="mv" style="color:var(--ok)">${fmt(net)}</span></div>
      <div class="mrow"><span class="mk">На карту после вывода (−${(state.wfees||{})[o.platform]||0}%)</span><span class="mv">${fmt(Math.round(net*(1-((state.wfees||{})[o.platform]||0)/100)))}</span></div>
      <div class="mrow"><span class="mk">Статус</span><span class="mv">${stPill(o.status)}</span></div>
      <div class="mrow"><span class="mk">Сделка №</span><span class="mv">${o.ext_id||o.id}</span></div>
    </div>
    <div class="modal-actions">${actions}</div>`;
  $('#modal-backdrop').classList.remove('hidden');
}
function showModal(html){
  $('#modal').innerHTML=html;
  $('#modal-backdrop').classList.remove('hidden');
}
function hideModal(){ $('#modal-backdrop').classList.add('hidden'); }
function openAiModal(){
  $('#modal').innerHTML=`
    <div class="modal-head"><div class="mh-t">🤖 AI-выставление из ссылок</div><div class="modal-x" data-act="closeModal">✕</div></div>
    <div class="modal-body">
      <div style="color:var(--muted);font-size:12.5px;margin-bottom:10px">Вставь одну или несколько ссылок, по одной на строку;
      подписи — свободным текстом рядом. AI прочитает страницы, определит площадку и категорию,
      напишет заголовок и описание, поставит цену с наценкой 25%. Создадутся <b>черновики</b> —
      ничего не публикуется без твоего подтверждения.</div>
      <textarea id="ai-text" rows="8" placeholder="https://playerok.com/… — кристаллы 980&#10;https://store.steampowered.com/app/…&#10;…"></textarea>
    </div>
    <div class="modal-actions"><button class="btn" id="ai-go">🤖 Создать черновики</button></div>`;
  $('#modal-backdrop').classList.remove('hidden');
  $('#ai-go').onclick=()=>{
    const t=$('#ai-text').value.trim();
    if(!t){ toast('Вставь хотя бы одну ссылку','bad','🤖'); return; }
    hideModal(); api('aidrafts',{text:t});
    toast('AI читает страницы… черновики появятся в «Товарах»','ok','🤖');
  };
}

/* ================= ДЕЙСТВИЯ ================= */
function moveOrder(id, to){
  const o=state.orders.find(x=>x.id===id); if(!o) return;
  o.status=to; o.mins=0;
  api('move',{id,to});
  hideModal();
  if(to==='sent') toast(`Заказ #${id}: статус «выдан» отправлен на площадку`,'ok','📦');
  else if(to==='done') toast(`Заказ #${id} завершён · ${fmt(o.price)}`,'ok','✅');
  else if(to==='dispute') toast(`По заказу #${id} оформляется возврат`,'bad','⚖️');
  render();
}
function toggleRule(id){
  const r=state.rules.find(x=>x.id===id); r.on=!r.on;
  api('rule',{id});
  toast(`Правило «${r.t}» ${r.on?'включено ✓':'выключено'}`, r.on?'ok':'', r.on?'⚙️':'⏸');
  render();
}
function toggleAutoPrice(id){
  const p=state.products.find(x=>x.id===id); p.auto=!p.auto;
  api('autoprice',{id});
  toast(`Автопрайс «${p.lot}» ${p.auto?'включён — цена будет держаться ниже конкурента':'выключен'}`, p.auto?'ok':'', '💰');
  render();
}
function matchPrice(id){
  api('match',{id});
  const p=state.products.find(x=>x.id===id);
  p.price=Math.max(p.comp-10, Math.round(p.price*0.9));
  toast(`Цена «${p.lot}» подстроена: ${fmt(p.price)}`,'ok','💰');
  render();
}
function matchAll(){
  api('matchall',{});
  let n=0;
  state.products.forEach(p=>{ if(p.active&&p.comp<p.price){ p.price=p.comp-10; n++; } });
  toast(n?`Автопрайс подстроил ${n} лот(а) под конкурентов`:'Все цены уже в рынке', n?'ok':'', '💰');
  render();
}
async function connect(p){
  if(!LIVE){ toast('Сервер недоступен — подключение невозможно. Обновите страницу.','bad','⛔'); return; }
  const inp = p==='funpay' ? $('#fp-key') : $('#po-key');
  const key = ((inp && inp.value) || '').trim();
  if(!key){ toast('Введите ключ: '+(p==='funpay'?'golden key (cookie) FunPay':'access-токен Playerok'),'warn','🔑'); return; }
  const ua = (((($(p==='funpay'?'#fp-ua':'#po-ua')||{}).value)||'').trim());
  toast(`Подключаем ${PF[p].name}…`,'','⏳');
  try{
    const r=await fetch('/api/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({platform:p,key,ua})});
    const d=await r.json();
    if(d.ok) toast(`${PF[p].name}: подключён — аккаунт ${d.login}. Загружаю заказы и чаты…`,'ok','🟢');
    else toast(`${PF[p].name}: ${d.error||'ошибка подключения'}`,'bad','⛔');
  }catch(e){ toast('Сервер недоступен','bad','⛔'); }
}
async function disconnect(p){
  if(!LIVE){ toast('Сервер недоступен','bad','⛔'); return; }
  await fetch('/api/disconnect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({platform:p})}).catch(()=>{});
  toast(`${PF[p].name} отключён`,'warn','🔌');
}
function toggleBell(){
  const panel=$('#bell-panel');
  if(panel.classList.contains('hidden')){
    panel.innerHTML=`<div class="bell-head">Уведомления <span data-act="alertclear">Очистить</span></div>` +
      (state.alerts.length? state.alerts.map(a=>`<div class="bell-item"><span class="bi">${a.icon}</span><div><div>${a.text}</div><div class="bt">${ago(a.mins)}</div></div></div>`).join('')
      : '<div class="bell-item">Новых уведомлений нет 🎉</div>');
    panel.classList.remove('hidden');
  } else panel.classList.add('hidden');
}

/* Глобальный обработчик кликов */
document.addEventListener('click', e=>{
  const bellOpen = !$('#bell-panel').classList.contains('hidden');
  const t = e.target.closest('[data-act]');
  if(bellOpen && !e.target.closest('.bell-wrap')) $('#bell-panel').classList.add('hidden');
  if(e.target.id==='modal-backdrop') hideModal();
  if(!t) return;
  const act=t.dataset.act;
  switch(act){
    case 'nav': location.hash='#'+t.dataset.view; break;
    case 'order': openOrder(+t.dataset.id); break;
    case 'closeModal': hideModal(); break;
    case 'move': moveOrder(+t.dataset.id, t.dataset.to); break;
    case 'gotochat': {
      const o=state.orders.find(x=>x.id===+t.dataset.id);
      let c=state.chats.find(x=>x.buyer===o.buyer);
      if(!c){ c={id:Date.now()%9999, platform:o.platform, buyer:o.buyer, game:o.game, lot:o.lot, unread:0, msgs:[{from:'me',text:`Здравствуйте! По вашему заказу «${o.lot}» — чем могу помочь?`,mins:1}]}; state.chats.unshift(c); api('createchat',{chat:c}); }
      c.unread=0; state.activeChat=c.id; hideModal(); location.hash='#chats';
      break;
    }
    case 'chatback': state.chatOpen=false; render(); break;
    case 'chat': {
      const c=state.chats.find(x=>x.id===+t.dataset.id);
      state.activeChat=c.id; c.unread=0; state.draft=''; state.chatOpen=true; api('chatread',{id:c.id}); render();
      break;
    }
    case 'tpl': {
      const inp=$('#msg-input'); if(inp){ inp.value=TEMPLATES[+t.dataset.i]; state.draft=inp.value; inp.focus(); }
      break;
    }
    case 'send': sendMessage(); break;
    case 'rule': toggleRule(+t.dataset.id); break;
    case 'autoprice': toggleAutoPrice(+t.dataset.id); break;
    case 'match': matchPrice(+t.dataset.id); break;
    case 'matchall': matchAll(); break;
    case 'connect': connect(t.dataset.p); break;
    case 'disconnect': disconnect(t.dataset.p); break;
    case 'tgtest': tgTest(); break;
    case 'saveset':
      state.fees.funpay=Math.max(0,Math.min(30,+($('#fee-fp').value||0)));
      state.fees.playerok=Math.max(0,Math.min(30,+($('#fee-po').value||0)));
      state.wfees=state.wfees||{};
      state.wfees.funpay=Math.max(0,Math.min(30,+($('#wfee-fp').value||0)));
      state.wfees.playerok=Math.max(0,Math.min(30,+($('#wfee-po').value||0)));
      api('saveset',{fees:{funpay:state.fees.funpay, playerok:state.fees.playerok},
                     wfees:{funpay:state.wfees.funpay, playerok:state.wfees.playerok}});
      toast('Настройки сохранены','ok','💾'); render();
      break;
    case 'setmode':{
      const mode=t.dataset.mode;
      api('setmode',{mode}); state.pfmode=mode;
      toast(mode==='both'?'Режим: обе площадки':mode==='funpay'?'Режим: только FunPay':'Режим: только Playerok','ok','🔀');
      render(); break;
    }
    case 'prodadd': openProdForm(); break;
    case 'aiopen': openAiModal(); break;
    case 'prodedit': openProdForm(+t.dataset.id); break;
    case 'proddel': if(confirm('Удалить товар из каталога?')) api('proddel',{id:+t.dataset.id}); break;
    case 'prodcopy': copyProd(+t.dataset.id); break;
    case 'prodopen': openProd(+t.dataset.id); break;
    case 'prodimport': openProdImport(); break;
    case 'prodplace':{
      const pr=(state.products||[]).find(x=>x.id===+t.dataset.id);
      if(pr){ const r=recommendDest(pr); api('produpd',{id:pr.id,product:{dest:r.dest}});
        toast(`Поставлено на ${r.dest==='funpay'?'FunPay':'Playerok'} (${r.score}%)`,'ok','🎯'); }
      break;
    }
    case 'prodauto':{
      let n=0;
      for(const pr of (state.products||[])){ const r=recommendDest(pr);
        if(pr.dest!==r.dest){ api('produpd',{id:pr.id,product:{dest:r.dest}}); n++; } }
      toast(n? `Авторасстановка: ${n} товар(ов) получили площадку` : 'Все товары уже расставлены','ok','🎯');
      break;
    }
    case 'bgopen': openBG(); break;
    case 'bgpick':{
      const id=t.dataset.bg; localStorage.setItem('sellhub_bg',id); setSky(id);
      document.querySelectorAll('.bg-pick').forEach(b=>b.classList.toggle('active',b.dataset.bg===id));
      const cb=$('#bg-sky-on'); if(cb) cb.checked=(id==='sky');
      toast('Фон: '+((BG_PRESETS.find(x=>x.id===id)||{}).t||id),'ok','🎨');
      break;
    }
    case 'ordclear': state.ordQ=''; render(); break;
    case 'ordtab': state.ordTab=t.dataset.tab; render(); break;
    case 'chatpf': state.chatPf=t.dataset.pf||''; render(); break;
    case 'pfclear': state.pfF=''; render(); break;
    case 'pfcatalog':
      state.pfF=t.dataset.p;
      if(state.view!=='orders') location.hash='#orders'; else render();
      toast(`Каталог: только ${PF[state.pfF].name}`,'','📦');
      break;
    case 'refresh': pullState(); break;
    case 'reset': location.reload(); break;
    case 'bell': toggleBell(); break;
    case 'alertclear': state.alerts=[]; api('alertclear',{}); renderBellCount(); toggleBell(); toggleBell(); break;
  }
});
document.addEventListener('input', e=>{
  if(e.target.id==='msg-input') state.draft=e.target.value;
});
document.addEventListener('keydown', e=>{
  if(e.key!=='Escape') return;
  if(!$('#modal-backdrop').classList.contains('hidden')){ hideModal(); return; }
  const bp=$('#bell-panel'); if(bp && !bp.classList.contains('hidden')) bp.classList.add('hidden');
});

/* ================= СЕРВЕР (LIVE-РЕЖИМ) ================= */
async function pullState(){
  toast('Обновляю данные с площадок…','','🔄');
  try{
    const r=await fetch('/api/state',{cache:'no-store'});
    if(r.status===401){ location.reload(); return; }
    if(!r.ok) throw 0;
    Object.assign(state, await r.json());
    render();
    toast('Данные обновлены','ok','✅');
  }catch(e){ toast('Не удалось обновить — сервер недоступен','bad','⛔'); }
}
let LIVE=false, ws=null;
async function tgTest(){
  toast('Отправляю тестовое уведомление…','','📨');
  try{
    const r = await fetch('/api/tgtest',{method:'POST'});
    const d = await r.json();
    if(d.ok) toast('Тестовое уведомление отправлено в Telegram','ok','✅');
    else toast(d.msg||'Не отправлено','warn','⚠️');
  }catch(e){ toast('Сервер недоступен','bad','⛔'); }
}
function api(action, payload={}){
  if(!LIVE) return;
  fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({action},payload))}).catch(()=>{});
}
function applyServerState(s, t){
  const keep={view:state.view, draft:state.draft, gsearch:state.gsearch, gfilter:state.gfilter, ordTab:state.ordTab, chatPf:state.chatPf, activeChat:state.activeChat, chatOpen:state.chatOpen};
  Object.assign(state, s, keep);
  const ac=state.chats.find(c=>c.id===state.activeChat);
  if(state.view==='chats' && ac && ac.unread){ ac.unread=0; api('chatread',{id:ac.id}); }
  render();
  if(t) toast(t.text, t.kind||'', t.icon||'🔔');
}
function connectWS(){
  try{
    ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');
    ws.onmessage=ev=>{ const m=JSON.parse(ev.data); if(m.type==='state') applyServerState(m.state, m.toast); };
    ws.onclose=()=>{ if(LIVE) setTimeout(connectWS, 3000); };
  }catch(e){}
}
function askPass(){
  return new Promise(res=>{
    const w=document.createElement('div');
    w.style.cssText='position:fixed;inset:0;background:rgba(8,10,15,.86);z-index:99998;display:flex;align-items:center;justify-content:center;font-family:inherit';
    w.innerHTML=`<div style="background:#151a26;border:1px solid #2a3245;border-radius:16px;padding:26px 30px;width:330px;text-align:center">
      <div style="font-size:30px">🔐</div>
      <div style="color:#e8ecf4;font-weight:700;margin:8px 0 4px">Вход только для владельца</div>
      <div style="color:#9aa6bd;font-size:12px;margin-bottom:14px">Код придёт в ваш личный Telegram (@shopchezze_bot). Пароль больше не нужен.</div>
      <div id="step1">
        <button id="getcode" style="width:100%;background:#0ea5e9;border:none;color:#04121f;font-weight:700;border-radius:10px;padding:11px;font-size:14px;cursor:pointer">📨 Получить код в Telegram</button>
      </div>
      <div id="step2" style="display:none">
        <div style="color:#9aa6bd;font-size:12px;margin-bottom:8px">Код отправлен. Введите 6 цифр из Telegram:</div>
        <input id="pw" inputmode="numeric" maxlength="6" placeholder="••••••" style="width:100%;box-sizing:border-box;background:#0d1017;border:1px solid #2a3245;color:#e8ecf4;border-radius:10px;padding:10px 12px;font-size:18px;letter-spacing:6px;text-align:center;outline:none">
        <button id="pwb" style="width:100%;margin-top:8px;background:#0ea5e9;border:none;color:#04121f;font-weight:700;border-radius:10px;padding:10px;font-size:14px;cursor:pointer">Войти</button>
        <div id="again" style="color:#7db4fc;font-size:11.5px;margin-top:8px;cursor:pointer">Отправить код ещё раз</div>
      </div>
      <div id="pwe" style="color:#f87171;font-size:12px;min-height:16px;margin-top:8px"></div>
    </div>`;
    document.body.appendChild(w);
    const err=w.querySelector('#pwe'), inp=w.querySelector('#pw');
    const getCode=async()=>{
      err.textContent='';
      const r=await fetch('/api/login/code',{method:'POST'}).catch(()=>null);
      if(r&&r.ok){ w.querySelector('#step1').style.display='none'; w.querySelector('#step2').style.display='block'; setTimeout(()=>inp.focus(),50); }
      else{ const d=r?await r.json().catch(()=>null):null; err.textContent=(d&&d.error)||'Не удалось отправить код'; }
    };
    const verify=async()=>{
      err.textContent='';
      const r=await fetch('/api/login/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:inp.value})}).catch(()=>null);
      if(r&&r.ok){ w.remove(); res(true); }
      else err.textContent='Неверный или просроченный код';
    };
    w.querySelector('#getcode').onclick=getCode;
    w.querySelector('#again').onclick=getCode;
    w.querySelector('#pwb').onclick=verify;
    inp.onkeydown=e=>{ if(e.key==='Enter') verify(); };
  });
}
function initTgWebApp(){
  /* если сайт открыт внутри Telegram (WebView), разворачиваем на весь экран
     и красим шапку Telegram в цвет неба; вне Telegram — ничего не делаем */
  try{
    const wa=window.Telegram && window.Telegram.WebApp;
    if(wa){ wa.ready(); wa.expand(); wa.setHeaderColor && wa.setHeaderColor('#0a0f26'); }
  }catch(e){}
  applyBG();
  document.body.classList.toggle('no-clouds', localStorage.getItem('sellhub_clouds')==='0');
}
initTgWebApp();

async function boot(){
  try{
    let r=await fetch('/api/state',{cache:'no-store'});
    if(r.status===401){
      const ok=await askPass();
      if(!ok) throw new Error('auth');
      r=await fetch('/api/state',{cache:'no-store'});
    }
    if(!r.ok) throw new Error('no api');
    const d=await r.json();
    LIVE=true;
    Object.assign(state, d);
    render(); connectWS();
    setTimeout(()=>toast('Сервер подключён — live-режим. Откройте вторую вкладку: данные синхронизируются','ok','🟢'),700);
  }catch(e){
    LIVE=false;
    render();
    setTimeout(()=>toast('Сервер недоступен — данные не загружены. Обновите страницу (Ctrl+F5).','bad','⛔'),700);
  }finally{
    const sp=document.getElementById('splash');
    if(sp){ sp.classList.add('off'); setTimeout(()=>sp.remove(),450); }
  }
}

/* ================= СТАРТ ================= */
window.addEventListener('hashchange', render);
renderClock(); setInterval(renderClock,1000);
if(!location.hash) location.hash='#dashboard';
render();
boot();
