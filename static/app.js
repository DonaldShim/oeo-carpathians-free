const state={
 map:null,baseLayer:null,aoiLayer:null,aoi:null,config:null,health:null,scenario:'forest',
 s1Scenes:[],s2Scenes:[],nisarScenes:[],footprintLayers:[],events:[],eventLayers:[],eventLayerById:{},alertMeta:null,
 s2Layer:null,s1Layer:null,compareLayers:[],compareControl:null,lastActivity:null
};
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(t,ms=2600){const e=$('toast');e.textContent=t;e.style.display='block';clearTimeout(e._t);e._t=setTimeout(()=>e.style.display='none',ms)}
function fmtDate(v){if(!v)return'—';try{return new Date(v).toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'})}catch(e){return v}}
function fmtShort(v){if(!v)return'—';try{return new Date(v).toLocaleDateString('ru-RU',{day:'2-digit',month:'2-digit',year:'2-digit'})}catch(e){return v}}
function bboxString(){return state.aoi?state.aoi.join(','):null}
function setStatus(ok,text){$('sysDot').style.background=ok?'#39b983':'#e56f6f';$('sysText').textContent=text}
function setUpdated(){ $('updatedAt').textContent=new Date().toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'}) }

const bases={
 esri:L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution:'Esri World Imagery'}),
 cloudless:L.tileLayer('https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2025_3857/default/GoogleMapsCompatible/{z}/{y}/{x}.jpg',{maxZoom:17,attribution:'EOX Cloudless'}),
 hybrid:L.layerGroup([
  L.tileLayer('https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2025_3857/default/GoogleMapsCompatible/{z}/{y}/{x}.jpg',{maxZoom:17}),
  L.tileLayer('https://tiles.maps.eox.at/wmts/1.0.0/overlay_base_3857/default/GoogleMapsCompatible/{z}/{y}/{x}.png',{maxZoom:17,attribution:'EOX'})
 ]),
 terrain:L.tileLayer('https://tiles.maps.eox.at/wmts/1.0.0/terrain_3857/default/g/{z}/{y}/{x}.jpg',{maxZoom:17,attribution:'EOX Terrain'}),
 osm:L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap'}),
 topo:L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',{maxZoom:17,attribution:'© OpenTopoMap'})
};

function initMap(){
 state.map=L.map('map',{zoomControl:true,preferCanvas:true}).setView([48.55,24.05],8);
 state.baseLayer=bases.hybrid;state.baseLayer.addTo(state.map);
 state.map.on(L.Draw.Event.CREATED,e=>setAOILayer(e.layer,e.layerType==='polygon'?'Полигон':'Прямоугольник',true));
 state.map.on('moveend',()=>{});
}
function switchBase(){
 const key=$('base').value;if(state.baseLayer)state.map.removeLayer(state.baseLayer);
 state.baseLayer=bases[key]||bases.hybrid;state.baseLayer.addTo(state.map);
 bringOperationalLayers();
}
function bringOperationalLayers(){
 for(const l of state.footprintLayers){try{l.bringToFront()}catch(e){}}
 for(const l of state.eventLayers){try{l.bringToFront()}catch(e){}}
 if(state.aoiLayer){try{state.aoiLayer.bringToFront()}catch(e){}}
}
function boundsToBbox(b){return [b.getWest(),b.getSouth(),b.getEast(),b.getNorth()].map(x=>+x.toFixed(6))}
function setAOILayer(layer,label,fit=true){
 if(state.aoiLayer){try{state.map.removeLayer(state.aoiLayer)}catch(e){}}
 state.aoiLayer=layer;
 if(layer.setStyle)layer.setStyle({color:'#49d096',weight:2,fillColor:'#37b77f',fillOpacity:.07});
 layer.addTo(state.map);
 const b=layer.getBounds();state.aoi=boundsToBbox(b);
 $('aoiLabel').textContent=label+' · '+state.aoi.join(', ');
 $('topAoi').textContent=label;
 $('mapHint').style.display='none';
 if(fit)state.map.fitBounds(b,{padding:[24,24],maxZoom:14});
}
function setPreset(p){setAOILayer(L.rectangle([[p.bbox[1],p.bbox[0]],[p.bbox[3],p.bbox[2]]]),p.label,true)}
function currentScreenAOI(){const b=state.map.getBounds();setAOILayer(L.rectangle([[b.getSouth(),b.getWest()],[b.getNorth(),b.getEast()]]),'Текущий экран',false)}
function clearAOI(){
 stopCompare();hideS2();hideS1();clearFootprints();clearEvents();
 if(state.aoiLayer){state.map.removeLayer(state.aoiLayer);state.aoiLayer=null}
 state.aoi=null;$('aoiLabel').textContent='Участок ещё не выбран';$('topAoi').textContent='не выбран';$('mapHint').style.display='block';
 resetSummary();
}
function exportGeoJSON(){
 if(!state.aoiLayer){toast('Сначала выберите участок');return}
 const blob=new Blob([JSON.stringify(state.aoiLayer.toGeoJSON(),null,2)],{type:'application/geo+json'});
 const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='OEO_AOI.geojson';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}
async function importGeoFile(file){
 try{
  const obj=JSON.parse(await file.text());const l=L.geoJSON(obj,{style:{color:'#49d096',weight:2,fillOpacity:.07}});
  if(!l.getLayers().length)throw new Error('В файле нет геометрии');
  setAOILayer(l,'Импортированный AOI',true);toast('AOI импортирован');
 }catch(e){toast('Ошибка импорта: '+e.message,5000)}
}

async function getJSON(u){
 const r=await fetch(u,{cache:'no-store'});let data=null;try{data=await r.json()}catch(e){}
 if(!r.ok)throw new Error((data&&data.detail)||r.status+' '+r.statusText);return data;
}
async function health(){
 try{const x=await getJSON('/health');state.health=x;setStatus(true,'система готова · '+x.version);return x}
 catch(e){setStatus(false,'система недоступна');throw e}
}
function setupConfig(c){
 state.config=c;
 $('preset').innerHTML='<option value="">— выберите район —</option>'+c.presets.map(p=>`<option value="${esc(p.id)}">${esc(p.label)}</option>`).join('');
 $('scenarios').innerHTML=c.scenarios.map(s=>`<button data-id="${esc(s.id)}">${esc(s.label)}</button>`).join('');
 document.querySelectorAll('#scenarios button').forEach(b=>b.onclick=()=>selectScenario(b.dataset.id));
 selectScenario('forest');
}
function selectScenario(id){
 const s=state.config.scenarios.find(x=>x.id===id);if(!s)return;state.scenario=id;
 document.querySelectorAll('#scenarios button').forEach(b=>b.classList.toggle('active',b.dataset.id===id));
 const meaning=s.meaning||('Источники: '+(s.sources||[]).join(' · '));$('scenarioHelp').textContent=meaning;
 if([...$('days').options].some(o=>o.value===String(s.days)))$('days').value=String(s.days);
 if(s.base&&bases[s.base]){$('base').value=s.base;switchBase()}
 if(s.s2_mode&&[...$('s2Mode').options].some(o=>o.value===s.s2_mode))$('s2Mode').value=s.s2_mode;
 $('periodMetric').textContent=$('days').value+'д';
}

function resetSummary(){
 for(const id of ['ready','s1','s2','nisar','firms'])$(id).textContent='—';
 $('event').className='event waiting';$('event').innerHTML='<div class="event-icon">◎</div><div><b>Ожидает проверки</b><span>Выберите участок и запустите мониторинг.</span></div>';
 $('confidenceBadge').textContent='нет данных';$('confidenceBadge').className='badge muted';
 $('explain').innerHTML='OEO разделяет <b>новые данные</b> и <b>подтверждённое событие</b>. Появление свежего снимка само по себе не считается событием.';
 $('alertCount').textContent='0';$('dataCount').textContent='0';
}
function renderSummary(x){
 const s=x.summary||{},r=x.evidence_readiness||{};
 $('ready').textContent=(r.level||'—')+' '+(r.signals??0)+'/'+(r.of??4);
 $('s1').textContent=s.sentinel1??0;$('s2').textContent=s.sentinel2??0;$('nisar').textContent=s.nisar??0;$('firms').textContent=s.firms??0;
 $('periodMetric').textContent=$('days').value+'д';
 const ev=$('event');const no=x.status==='NO_CONFIRMED_EVENT';
 ev.className='event '+(no?'ok':'warn');
 ev.innerHTML=`<div class="event-icon">${no?'✓':'!'}</div><div><b>${no?'Подтверждённых новых событий нет':esc(x.status||'Требуется проверка')}</b><span>${esc(x.interpretation||'')}</span></div>`;
 $('confidenceBadge').textContent='данные '+(r.level||'—');$('confidenceBadge').className='badge';
 $('explain').textContent=x.interpretation||'';
}
function clearFootprints(){for(const l of state.footprintLayers){try{state.map.removeLayer(l)}catch(e){}}state.footprintLayers=[]}
function clearEvents(){
 for(const l of state.eventLayers){try{state.map.removeLayer(l)}catch(e){}}
 state.eventLayers=[];state.eventLayerById={};state.events=[];state.alertMeta=null;
}
function eventColor(e){
 if(e.class==='direct')return '#ff4d4f';
 if(e.scenario==='flood')return '#3fa7ff';
 if(e.scenario==='slope')return '#b985ff';
 if(e.scenario==='fire')return '#ff6b3d';
 return '#ffb84d';
}
function eventLabel(e){
 if(e.class==='direct')return 'ПРЯМОЙ АЛЕРТ';
 return 'КАНДИДАТ · требует подтверждения';
}
function focusEvent(id,open=true){
 const e=state.events.find(x=>x.id===id),l=state.eventLayerById[id];if(!e||!l)return;
 try{
  if(e.geometry?.type==='Point'){
    const c=l.getLatLng?l.getLatLng():null;if(c)state.map.setView(c,15,{animate:true});
  }else if(l.getBounds){
    state.map.fitBounds(l.getBounds(),{padding:[70,70],maxZoom:15,animate:true});
  }
  if(open&&l.openPopup)l.openPopup();
 }catch(err){}
}
function compareEvent(id){
 const e=state.events.find(x=>x.id===id);if(!e||!e.before?.id||!e.after?.id){toast('Для этой находки нет пары сцен');return}
 if(!findS2(e.before.id)||!findS2(e.after.id)){
   toast('Сцены находки не входят в текущий список. Обновите участок.',4500);return;
 }
 $('beforeScene').value=e.before.id;$('afterScene').value=e.after.id;$('compareMode').value=e.mode||'NBR';
 startCompare();focusEvent(id,false);
}
function eventCard(e){
 const pct=Math.round((e.confidence||0)*100);
 const direct=e.class==='direct';
 const meta=direct
  ? `${esc(e.source||'')} · ${esc(e.date||'')} ${esc(e.time||'')} ${e.frp?'· FRP '+esc(e.frp):''}`
  : `${esc(e.source||'')} · ${esc(e.mode||'')} · уверенность ${pct}%`;
 return `<div class="alert-card ${direct?'direct':'candidate'}" style="--event:${eventColor(e)}">
   <div class="alert-card-head"><span class="alert-class">${eventLabel(e)}</span><span class="alert-score">${direct?'THERMAL':pct+'%'}</span></div>
   <b>${esc(e.title||'Изменение')}</b>
   <small>${meta}</small>
   <div class="alert-actions"><button data-event-focus="${esc(e.id)}">Показать на карте</button>${(!direct&&e.before?.id&&e.after?.id)?`<button data-event-compare="${esc(e.id)}">До / после</button>`:''}</div>
 </div>`;
}
function renderEvents(payload){
 clearEvents();
 state.alertMeta=payload||{};state.events=(payload&&payload.events)||[];
 const configured=!!payload?.firms_configured;
 const sourceHtml=`<div class="source-strip">
   <span class="src on">Sentinel‑2 candidates: ON</span>
   <span class="src ${configured?'on':'off'}">FIRMS: ${configured?'ON':'нет ключа'}</span>
   <span class="src ext">GFW: внешний источник</span>
 </div>`;
 let html=sourceHtml;
 if(state.events.length){
   html+=state.events.map(eventCard).join('');
 }else{
   html+=`<div class="empty"><b>На этом AOI находок нет.</b><br>Кандидатный анализ Sentinel‑2 выполнен; FIRMS ${configured?'подключён':'не подключён'}. Новые сцены смотрите во вкладке «Новые данные».</div>`;
 }
 $('alertList').innerHTML=html;$('alertCount').textContent=String(state.events.length);
 for(const e of state.events){
   const col=eventColor(e);let l=null;
   try{
    if(e.geometry?.type==='Point'){
      const [lon,lat]=e.geometry.coordinates;
      l=L.circleMarker([lat,lon],{radius:10,color:'#fff',weight:2,fillColor:col,fillOpacity:.92});
    }else{
      l=L.geoJSON(e.geometry,{style:{color:col,weight:3,fillColor:col,fillOpacity:.22,dashArray:e.class==='candidate'?'7 4':null}});
    }
    if(!l)continue;
    l.bindPopup(`<b style="color:${col}">${esc(eventLabel(e))}</b><br><strong>${esc(e.title||'')}</strong><br>${esc(e.source||'')}${e.confidence?'<br>Уверенность: '+Math.round(e.confidence*100)+'%':''}`);
    l.addTo(state.map);state.eventLayers.push(l);state.eventLayerById[e.id]=l;
   }catch(err){}
 }
 const direct=state.events.filter(e=>e.class==='direct').length;
 const cand=state.events.filter(e=>e.class==='candidate').length;
 if(direct>0){
   $('event').className='event bad';$('event').innerHTML=`<div class="event-icon">!</div><div><b>Прямых алертов: ${direct}</b><span>Есть FIRMS/VIIRS термосигнал. Откройте вкладку «Алерты».</span></div>`;
 }else if(cand>0){
   $('event').className='event warn';$('event').innerHTML=`<div class="event-icon">△</div><div><b>Кандидатов изменений: ${cand}</b><span>Это автоматический скрининг Sentinel‑2, а не подтверждённое событие. Проверьте «до / после» и SAR.</span></div>`;
 }else{
   $('event').className='event ok';$('event').innerHTML='<div class="event-icon">✓</div><div><b>Значимых находок не выявлено</b><span>Свежие данные есть, но текущий автоматический скрининг не сформировал кандидатов.</span></div>';
 }
 bringOperationalLayers();
 if(state.events.length)focusEvent(state.events[0].id,true);
}

function addFootprints(){
 clearFootprints();if(!$('footprints').checked)return;
 const groups=[['Sentinel‑1',state.s1Scenes,'#4fc3f7'],['Sentinel‑2',state.s2Scenes,'#79d48d'],['NISAR',state.nisarScenes,'#ffc857']];
 for(const [name,items,color] of groups){for(const x of (items||[]).slice(0,12)){if(!x.geometry)continue;try{
  const l=L.geoJSON(x.geometry,{style:{color,weight:1,fillOpacity:.025}}).addTo(state.map);
  l.bindPopup(`<b>${name}</b><br>${esc(fmtDate(x.datetime))}<br>${esc(x.id||'')}`);state.footprintLayers.push(l);
 }catch(e){}}}
 bringOperationalLayers();
}
function sceneLabel(x){
 const cloud=x.cloud_cover!=null?` · облачность ${Math.round(x.cloud_cover)}%`:'';
 return `${fmtShort(x.datetime)}${cloud}`;
}
function fillSceneSelectors(){
 const s2=state.s2Scenes;
 const opts=s2.length?s2.map(x=>`<option value="${esc(x.id)}">${esc(sceneLabel(x))}</option>`).join(''):'<option value="">Сцен не найдено</option>';
 for(const id of ['s2Scene','beforeScene','afterScene'])$(id).innerHTML=opts;
 if(s2.length){$('afterScene').value=s2[0].id;$('beforeScene').value=s2[Math.min(3,s2.length-1)].id;$('s2Scene').value=s2[0].id;updateS2Info()}
 const s1=state.s1Scenes;
 $('s1Scene').innerHTML=s1.length?s1.map(x=>`<option value="${esc(x.id)}">${esc(fmtShort(x.datetime))} · ${esc(x.id)}</option>`).join(''):'<option value="">SAR сцен не найдено</option>';
}
function findS2(id){return state.s2Scenes.find(x=>x.id===id)}
function findS1(id){return state.s1Scenes.find(x=>x.id===id)}
function updateS2Info(){
 const x=findS2($('s2Scene').value);if(!x){$('s2Info').textContent='Сцена не выбрана';return}
 $('s2Info').textContent=`${fmtDate(x.datetime)} · облачность ${x.cloud_cover==null?'—':Math.round(x.cloud_cover)+'%'} · ${x.platform||'Sentinel‑2'}`;
}
function tileUrlS2(id,mode){return `/api/v3/sentinel2/tile/${encodeURIComponent(id)}/${mode}/{z}/{x}/{y}.png`}
function tileUrlS1(id,pol){return `/api/v3/sentinel1/tile/${encodeURIComponent(id)}/${pol}/{z}/{x}/{y}.png`}
function setActiveLayer(kind,text){
 $('activeLayerKind').textContent=kind;$('activeLayerKind').className='badge';
 $('activeLayerText').textContent=text;$('layerBadge').hidden=false;$('layerBadge').textContent=kind+' · '+text;
}
function clearActiveLayer(){
 $('activeLayerKind').textContent='подложка';$('activeLayerKind').className='badge muted';$('activeLayerText').textContent='Аналитический слой пока не включён';$('layerBadge').hidden=true;
}
function hideS2(){if(state.s2Layer){state.map.removeLayer(state.s2Layer);state.s2Layer=null}if(!state.s1Layer&&!state.compareLayers.length)clearActiveLayer()}
function hideS1(){if(state.s1Layer){state.map.removeLayer(state.s1Layer);state.s1Layer=null}if(!state.s2Layer&&!state.compareLayers.length)clearActiveLayer()}
function showS2ById(id,mode){
 if(!id){toast('Нет выбранной Sentinel‑2 сцены');return}
 stopCompare();hideS2();
 const x=findS2(id);state.s2Layer=L.tileLayer(tileUrlS2(id,mode),{opacity:.88,maxZoom:14,minZoom:5,updateWhenIdle:true,keepBuffer:2});
 let warned=false;state.s2Layer.on('tileerror',()=>{if(!warned){warned=true;toast('Raster-слой прогружается медленно или сцена не покрывает этот тайл',4500)}});
 state.s2Layer.addTo(state.map);bringOperationalLayers();
 setActiveLayer('Sentinel‑2 '+mode,`${fmtShort(x?.datetime)} · ${x?.cloud_cover==null?'облачность —':Math.round(x.cloud_cover)+'% облачности'}`);
}
function showS1ById(id,pol){
 if(!id){toast('Нет выбранной Sentinel‑1 сцены');return}
 stopCompare();hideS1();
 const x=findS1(id);state.s1Layer=L.tileLayer(tileUrlS1(id,pol),{opacity:.82,maxZoom:14,minZoom:5,updateWhenIdle:true});
 state.s1Layer.addTo(state.map);bringOperationalLayers();setActiveLayer('Sentinel‑1 '+pol,fmtShort(x?.datetime));
}
function stopCompare(){
 if(state.compareControl){try{state.map.removeControl(state.compareControl)}catch(e){}state.compareControl=null}
 for(const l of state.compareLayers){try{state.map.removeLayer(l)}catch(e){}}state.compareLayers=[];
 $('compareInfo').textContent='После загрузки сцен появится интерактивный разделитель «до ↔ после».';
 if(!state.s1Layer&&!state.s2Layer)clearActiveLayer();
}
function startCompare(){
 const a=$('beforeScene').value,b=$('afterScene').value,mode=$('compareMode').value;
 if(!a||!b){toast('Нужны две Sentinel‑2 сцены');return}if(a===b){toast('Выберите разные сцены «до» и «после»');return}
 hideS2();hideS1();stopCompare();
 const left=L.tileLayer(tileUrlS2(a,mode),{opacity:.92,maxZoom:14,minZoom:5,updateWhenIdle:true}).addTo(state.map);
 const right=L.tileLayer(tileUrlS2(b,mode),{opacity:.92,maxZoom:14,minZoom:5,updateWhenIdle:true}).addTo(state.map);
 state.compareLayers=[left,right];state.compareControl=L.control.sideBySide(left,right).addTo(state.map);
 const aa=findS2(a),bb=findS2(b);$('compareInfo').textContent=`До: ${fmtDate(aa?.datetime)} · После: ${fmtDate(bb?.datetime)} · режим ${mode}`;
 setActiveLayer('Сравнение '+mode,`${fmtShort(aa?.datetime)} ↔ ${fmtShort(bb?.datetime)}`);
 bringOperationalLayers();
}

function sceneItem(name,x,kind){
 const cloud=x.cloud_cover!=null?` · облачность ${Math.round(x.cloud_cover)}%`:'';
 const maturity=x.dataMaturity?` · ${x.dataMaturity}`:'';
 let action='';
 if(kind==='s2')action=`<button data-kind="s2" data-id="${encodeURIComponent(x.id)}">RGB на карте</button><button data-kind="s2nbr" data-id="${encodeURIComponent(x.id)}">NBR</button>`;
 if(kind==='s1')action=`<button data-kind="s1" data-id="${encodeURIComponent(x.id)}">SAR VV</button>`;
 return `<div class="item"><div class="item-head"><div><b>${esc(name)} · ${esc(x.id||x.platform||'scene')}</b><small>${esc(fmtDate(x.datetime))}${esc(cloud)}${esc(maturity)}</small></div></div><div class="meta">${esc(x.source||'')}</div>${action?`<div class="item-actions">${action}</div>`:''}</div>`;
}
function renderData(activity){
 const n=activity.latest?.nisar||[];state.nisarScenes=n;
 const html=[
  ...state.s1Scenes.slice(0,5).map(x=>sceneItem('Sentinel‑1',x,'s1')),
  ...state.s2Scenes.slice(0,5).map(x=>sceneItem('Sentinel‑2',x,'s2')),
  ...n.slice(0,5).map(x=>sceneItem('NISAR',x,'nisar'))
 ].join('');
 $('dataList').innerHTML=html||'<div class="empty">Новых данных в выбранном окне нет.</div>';
 $('dataCount').textContent=String(state.s1Scenes.length+state.s2Scenes.length+n.length);
}
function renderAlerts(activity){ /* UX4.1: alerts are rendered by renderEvents() */ }
async function sensors(){
 try{const p=await getJSON('/api/v3/providers');$('sensorList').innerHTML=p.providers.map(x=>`<div class="item"><b>${esc(x.name)}</b><small>${esc((x.missions||[]).join(' · '))}</small><div class="meta">${esc(x.mode)}${x.key_required?' · требуется ключ':''}</div></div>`).join('')}
 catch(e){$('sensorList').innerHTML='<div class="empty">Не удалось получить состояние провайдеров.</div>'}
}

async function scan(){
 if(!state.aoi){toast('Сначала выберите или нарисуйте участок');return}
 const b=encodeURIComponent(bboxString()),days=Number($('days').value||30);$('periodMetric').textContent=days+'д';
 $('scan').disabled=true;$('scan').textContent='Проверка…';
 try{
  await health();
  const activity=await getJSON(`/api/v3/activity/scan?bbox=${b}&days=${days}`);
  state.lastActivity=activity;
  const lookback=Math.max(days,90);
  const [s1,s2]=await Promise.all([
    getJSON(`/api/v3/sentinel1/search?bbox=${b}&days=${lookback}&max_results=18`),
    getJSON(`/api/v3/sentinel2/search?bbox=${b}&days=${lookback}&max_results=24&cloud_max=70`)
  ]);
  state.s1Scenes=s1.results||[];state.s2Scenes=s2.results||[];
  renderSummary(activity);fillSceneSelectors();renderData(activity);addFootprints();
  $('scan').textContent='Анализ изменений…';
  let ev=null;
  try{ev=await getJSON(`/api/v3/events/candidates?bbox=${b}&days=${days}&scenario=${encodeURIComponent(state.scenario)}`)}
  catch(err){ev={events:[],count:0,firms_configured:state.health?.firms_configured,warning:err.message};toast('Слой находок временно недоступен: '+err.message,5000)}
  renderEvents(ev);
  setUpdated();$('mapHint').style.display='none';toast(`Обновлено: находки ${state.events.length} · S1 ${state.s1Scenes.length} · S2 ${state.s2Scenes.length} · NISAR ${state.nisarScenes.length}`);
 }catch(e){setStatus(false,'ошибка обновления');toast('Не удалось обновить мониторинг: '+e.message,6000)}
 finally{$('scan').disabled=false;$('scan').textContent='Проверить участок'}
}

function setupTabs(){
 document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===b));
  document.querySelectorAll('.tab-body').forEach(x=>x.classList.toggle('active',x.id===b.dataset.tab));
 });
}
function setupEvents(){
 $('usePreset').onclick=()=>{const p=state.config.presets.find(x=>x.id===$('preset').value);if(p)setPreset(p)};
 $('drawRect').onclick=()=>new L.Draw.Rectangle(state.map,{shapeOptions:{color:'#49d096',weight:2,fillOpacity:.07}}).enable();
 $('drawPoly').onclick=()=>new L.Draw.Polygon(state.map,{allowIntersection:false,shapeOptions:{color:'#49d096',weight:2,fillOpacity:.07}}).enable();
 $('screenAoi').onclick=currentScreenAOI;$('clearAoi').onclick=clearAOI;$('exportGeo').onclick=exportGeoJSON;
 $('importGeo').onclick=()=>$('geoFile').click();$('geoFile').onchange=e=>{if(e.target.files[0])importGeoFile(e.target.files[0]);e.target.value=''};
 $('scan').onclick=scan;$('refreshTop').onclick=()=>state.aoi?scan():health().then(setUpdated).catch(()=>{});
 $('base').onchange=switchBase;$('footprints').onchange=addFootprints;
 $('s2Scene').onchange=updateS2Info;$('showS2').onclick=()=>showS2ById($('s2Scene').value,$('s2Mode').value);$('hideS2').onclick=hideS2;
 $('showS1').onclick=()=>showS1ById($('s1Scene').value,$('s1Pol').value);$('hideS1').onclick=hideS1;
 $('startCompare').onclick=startCompare;$('stopCompare').onclick=stopCompare;
 $('openGfw').onclick=()=>window.open('https://www.globalforestwatch.org/map/','_blank','noopener');
 $('openFirms').onclick=()=>window.open('https://firms.modaps.eosdis.nasa.gov/map/','_blank','noopener');
 $('dataList').onclick=e=>{const b=e.target.closest('button[data-kind]');if(!b)return;const id=decodeURIComponent(b.dataset.id);if(b.dataset.kind==='s2')showS2ById(id,'RGB');if(b.dataset.kind==='s2nbr')showS2ById(id,'NBR');if(b.dataset.kind==='s1')showS1ById(id,'VV')};
 $('alertList').onclick=e=>{const f=e.target.closest('button[data-event-focus]');if(f){focusEvent(f.dataset.eventFocus,true);return}const c=e.target.closest('button[data-event-compare]');if(c){compareEvent(c.dataset.eventCompare);return}};
}
async function init(){
 initMap();setupTabs();setupEvents();resetSummary();
 const c=await getJSON('/api/config');setupConfig(c);await health();await sensors();setUpdated();
 setInterval(()=>health().catch(()=>{}),60000);
}
init().catch(e=>{setStatus(false,'ошибка запуска');toast('Ошибка запуска OEO: '+e.message,7000)});
