'use strict';
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
let state = null, selectedWeather = 2, selectedWeapon = 10201, category = '全部';
let catalogLoaded = false, toastTimer, submitting = false;
const descriptions = {2:'视野清晰，适合探索。',9:'云层掠过海岛，慢一点也无妨。',3:'让细雨落在这片熟悉的土地。',5:'雷声将至，找一处新的庇护。',12:'能见度降低，每一段路都有未知。',13:'换一场雪，重新认识欧罗巴。'};
function toast(message, error = false) {
  const box = $('#toast'); box.textContent = message; box.classList.toggle('error', error); box.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { box.hidden = true; }, 4500);
}
function weatherSelection(id) {
  selectedWeather = Number(id); $('#weather-select').value = String(id);
  $$('.weather-choice').forEach(button => { const active = Number(button.dataset.weather) === selectedWeather; button.classList.toggle('selected',active); button.setAttribute('aria-pressed',active); });
  const name = state?.weather.find(item => item.id === selectedWeather)?.name || '晴天';
  $('#weather-preview').textContent = name;
  $('#weather-id').textContent = `PRESET ${String(id).padStart(2,'0')}`;
  $('#weather-description').textContent = descriptions[id] || '选择一个原生预设，等待天气慢慢变化。';
}
function renderWeapons() {
  if (!state) return;
  const query = $('#weapon-search').value.trim().toLowerCase();
  const grid = $('#weapon-grid'); grid.replaceChildren();
  const weapons = state.weapons.filter(item => (category === '全部' || item.category === category) && `${item.name} ${item.category}`.toLowerCase().includes(query));
  for (const weapon of weapons) {
    const button = document.createElement('button'); button.type='button';button.className='weapon-card';
    button.classList.toggle('selected',weapon.id === selectedWeapon);button.setAttribute('aria-pressed',weapon.id === selectedWeapon);
    button.setAttribute('aria-label',`${weapon.name}，${weapon.ammo}，弹匣 ${weapon.capacity} 发`);
    const check=document.createElement('span');check.className='checkmark';check.textContent='✓';button.append(check);
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');const use=document.createElementNS(svg.namespaceURI,'use');use.setAttribute('href','#rifle');svg.setAttribute('viewBox','0 0 180 52');svg.setAttribute('aria-hidden','true');svg.append(use);button.append(svg);
    const name=document.createElement('span');name.className='weapon-name';name.textContent=weapon.name;button.append(name);
    const detail=document.createElement('span');detail.className='weapon-meta';detail.textContent=`${weapon.ammo} · ${weapon.capacity} 发`;button.append(detail);
    button.addEventListener('click',()=>{selectedWeapon=weapon.id;renderWeapons();renderSelected();});grid.append(button);
  }
  if (!weapons.length) { const empty=document.createElement('p');empty.className='empty-state';empty.textContent='没有匹配的武器，试试其他名称。';grid.append(empty); }
}
function renderSelected() {
  const weapon=state?.weapons.find(item=>item.id===selectedWeapon);if(!weapon)return;
  $('#selected-weapon').textContent=weapon.name;$('#selected-ammo').textContent=weapon.ammo;
}
function renderState() {
  const ready=state.connected && state.ready;
  $('#connection').className='connection online';$('#connection-text').textContent='控制台已连接';
  $('#session-label').textContent=state.preview?'界面预览':ready?(state.seated?'角色在载具中':'地图已就绪'):state.connected?'地图载入中':'等待游戏连接';
  $('#session-dot').style.background=ready?'#c5df95':'#8b967e';
  $('#current-weather').textContent=state.weather.find(item=>item.id===state.weather_id)?.name || '客户端默认';
  $('#item-count').textContent=state.ground_items;$('#vehicle-count').textContent=state.vehicles.length;
  $('#position').textContent=state.position?state.position.map(n=>(n/100).toFixed(1)).join(' / '):'— / — / —';
  $('#apply-weather').disabled=!ready || submitting;
  $('#spawn-weapon').disabled=!ready || state.seated || !state.weapons_enabled || submitting;
  $('#spawn-vehicle').disabled=!ready || state.seated || !state.vehicles_enabled || state.vehicles.length>=8 || submitting;
  $('#footer-status').textContent=state.preview?'双击 start_offline_control.cmd 启动游戏与控制台':ready?'本地服务 · 操作将在当前地图中发送':'本地服务 · 等待游戏进入地图';
  const list=$('#activity-list');list.replaceChildren();
  const latest=new Map();for(const event of state.events)if(!latest.has(event.id))latest.set(event.id,event);
  for(const event of [...latest.values()].slice(0,8)){
    const li=document.createElement('li'),time=document.createElement('time'),body=document.createElement('span'),tag=document.createElement('span');
    time.textContent=event.time;body.className='event-text';body.textContent=event.message;tag.className=`event-status ${event.status}`;
    tag.textContent={queued:'排队中',sent:'已发送',failed:'未执行',cancelled:'已取消'}[event.status] || event.status;
    li.append(time,body,tag);list.append(li);
  }
  if(!latest.size){const li=document.createElement('li');li.className='empty-state';li.textContent='还没有操作。世界正在等待你的安排。';list.append(li);}
}
async function refresh() {
  try {
    const response=await fetch('/api/state',{cache:'no-store'});if(!response.ok)throw new Error('控制台连接失败');state=await response.json();
    if(!catalogLoaded){const select=$('#weather-select');select.replaceChildren();for(const item of state.weather){const option=document.createElement('option');option.value=item.id;option.textContent=item.name;select.append(option);}catalogLoaded=true;weatherSelection(selectedWeather);renderWeapons();renderSelected();}
    renderState();
  } catch(error) {
    $('#connection').className='connection error';$('#connection-text').textContent='控制台连接已断开';$('#session-label').textContent='服务已停止';
    ['apply-weather','spawn-weapon','spawn-vehicle'].forEach(id=>{document.getElementById(id).disabled=true;});
    $('#footer-status').textContent='重新运行 start_offline_control.cmd 后连接';
  }
}
function number(id) {const input=document.getElementById(id);if(!input.checkValidity() || !Number.isInteger(Number(input.value)) || input.value===''){input.reportValidity();throw new Error('请填写范围内的整数');}return Number(input.value);}
async function submit(data) {
  if(!state || submitting)return;submitting=true;renderState();
  try{const response=await fetch('/api/commands',{method:'POST',headers:{'Content-Type':'application/json','X-Control-Token':state.token},body:JSON.stringify(data)});const result=await response.json();if(!response.ok)throw new Error(result.error || '操作未提交');toast('操作已排队，执行结果会显示在操作记录中。');}
  catch(error){toast(error.message,true);}finally{submitting=false;await refresh();}
}
$$('.weather-choice').forEach(button=>button.addEventListener('click',()=>weatherSelection(button.dataset.weather)));
$('#weather-select').addEventListener('change',event=>weatherSelection(event.target.value));
$$('.filter').forEach(button=>button.addEventListener('click',()=>{category=button.dataset.category;$$('.filter').forEach(item=>{const active=item===button;item.classList.toggle('selected',active);item.setAttribute('aria-pressed',active);});renderWeapons();}));
$('#weapon-search').addEventListener('input',renderWeapons);
function action(button,build){$(button).addEventListener('click',()=>{try{submit(build());}catch(error){toast(error.message,true);}});}
action('#apply-weather',()=>({action:'weather',weather_id:selectedWeather,transition:number('transition')}));
action('#spawn-weapon',()=>({action:'weapon',template:selectedWeapon,count:number('weapon-count'),ammo:number('ammo-count'),distance:number('weapon-distance')}));
action('#spawn-vehicle',()=>({action:'vehicle',config:101,distance:number('vehicle-distance')}));
$$('.nav-link').forEach(link=>link.addEventListener('click',()=>{$$('.nav-link').forEach(item=>item.classList.toggle('active',item===link));}));
async function poll(){await refresh();setTimeout(poll,1200);}poll();
