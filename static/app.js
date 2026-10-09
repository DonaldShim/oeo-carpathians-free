const state={
 map:null,baseLayer:null,aoiLayer:null,aoi:null,config:null,health:null,scenario:'forest',
 s1Scenes:[],s2Scenes:[],nisarScenes:[],footprintLayers:[],events:[],eventLayers:[],eventLayerById:{},alertMeta:null,
 findingType:'all',minSignal:0,currentRegion:'all',scanActive:false,autoWatchTimer:null,
 s2Layer:null,s1Layer:null,compareLayers:[],compareControl:null,lastActivity:null
};
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(t,ms=2600){const e=$('toast');e.textContent=t;e.style.display='block';clearTimeout(e._t);e._t=setTimeout(()=>e.style.display='none',ms)}
function fmtDate(v){if(!v)return'—';try{return new Date(v).toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'})}catch(e){return v}}
function fmtShort(v){if(!v)return'—';try{return new Date(v).toLocaleDateString('ru-RU',{day:'2-digit',month:'2-digit',year:'2-digit'})}catch(e){return v}}
function bboxString(){return state.aoi?state.aoi.join(','):null}
const LS_AOI='oeo_v43_last_aoi',LS_SCENARIO='oeo_v43_scenario',LS_AUTOWATCH='oeo_v43_autowatch';
function persistMonitor(){
 try{
  if(state.aoi)localStorage.setItem(LS_AOI,JSON.stringify({bbox:state.aoi,label:$('topAoi')?.textContent||'Последний участок'}));
  if(state.scenario)localStorage.setItem(LS_SCENARIO,state.scenario);
  if($('autoWatch'))localStorage.setItem(LS_AUTOWATCH,$('autoWatch').checked?'1':'0');
 }catch(e){}
}
function restoreMonitor(){
 try{
  const raw=localStorage.getItem(LS_AOI);if(!raw)return false;
  const x=JSON.parse(raw),b=x?.bbox;
  if(!Array.isArray(b)||b.length!==4||!b.every(Number.isFinite))return false;
  setAOILayer(L.rectangle([[b[1],b[0]],[b[3],b[2]]]),x.label||'Последний участок',true);return true;
 }catch(e){return false}
}
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
 persistMonitor();
}
function setPreset(p){
 if($('region')&&p?.region){$('region').value=p.region;state.currentRegion=p.region;populatePresets(p.region);$('preset').value=p.id}
 const prefix=p?.region==='polissia'?'Полесье · ':p?.region==='carpathians'?'Карпаты · ':'';
 setAOILayer(L.rectangle([[p.bbox[1],p.bbox[0]],[p.bbox[3],p.bbox[2]]]),prefix+p.label,true)
}
function currentScreenAOI(){const b=state.map.getBounds();setAOILayer(L.rectangle([[b.getSouth(),b.getWest()],[b.getNorth(),b.getEast()]]),'Текущий экран',false)}
function clearAOI(){
 stopCompare();hideS2();hideS1();clearFootprints();clearEvents();
 if(state.aoiLayer){state.map.removeLayer(state.aoiLayer);state.aoiLayer=null}
 state.aoi=null;try{localStorage.removeItem(LS_AOI)}catch(e){};$('aoiLabel').textContent='Участок ещё не выбран';$('topAoi').textContent='не выбран';$('mapHint').style.display='block';
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
function populatePresets(region='all'){
 state.currentRegion=region||'all';
 const list=state.config.presets.filter(p=>state.currentRegion==='all'||p.region===state.currentRegion);
 $('preset').innerHTML='<option value="">— выберите район —</option>'+list.map(p=>{
   const prefix=state.currentRegion==='all'?(p.region==='polissia'?'Полесье · ':'Карпаты · '):'';
   return `<option value="${esc(p.id)}">${prefix}${esc(p.label)}</option>`;
 }).join('');
}
function setupConfig(c){
 state.config=c;
 if(c.regions&&$('region'))$('region').innerHTML=c.regions.map(r=>`<option value="${esc(r.id)}">${esc(r.label)}</option>`).join('');
 populatePresets($('region')?.value||'all');
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
 $('periodMetric').textContent=$('days').value+'д';persistMonitor();
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
    state.map.fitBounds(l.getBounds(),{padding:[70,70],maxZoom:16,animate:true});
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
function signalIndex(e){return e.class==='direct'?100:Number(e.signal_index??0)}
function findingVisible(e){
 const type=state.findingType||'all';
 if(type!=='all'&&e.class!==type)return false;
 return e.class==='direct'||signalIndex(e)>=Number(state.minSignal||0);
}
function deltaLabel(e){
 if(e.class==='direct')return '';
 const raw=Number(e.delta_index||0),res=Number(e.residual_delta??raw),base=Number(e.scene_baseline_delta||0);
 return `локальный Δ${e.mode||'index'} ${res>=0?'+':''}${res.toFixed(3)} · фон ${base>=0?'+':''}${base.toFixed(3)}`;
}
function eventCenter(e){
 if(e?.geometry?.type==='Point'){
  const [lon,lat]=e.geometry.coordinates||[];if(Number.isFinite(lat)&&Number.isFinite(lon))return [lat,lon];
 }
 const b=e?.bbox;
 if(Array.isArray(b)&&b.length===4)return [(Number(b[1])+Number(b[3]))/2,(Number(b[0])+Number(b[2]))/2];
 try{
  const l=state.eventLayerById[e?.id];
  if(l?.getBounds){const c=l.getBounds().getCenter();return [c.lat,c.lng]}
 }catch(err){}
 return null;
}
function openOsmAnd(id){
 const e=state.events.find(x=>x.id===id),c=eventCenter(e);if(!c){toast('Нет координат находки');return}
 const [lat,lon]=c.map(Number),z=16;
 const u=`https://osmand.net/map/?pin=${lat.toFixed(6)},${lon.toFixed(6)}#${z}/${lat.toFixed(6)}/${lon.toFixed(6)}`;
 window.open(u,'_blank','noopener');
}
function openOrganic(id){
 const e=state.events.find(x=>x.id===id),c=eventCenter(e);if(!c){toast('Нет координат находки');return}
 const [lat,lon]=c.map(Number),name=encodeURIComponent('OEO · '+(e?.title||'находка'));
 const u=`https://omaps.app/map?v=1&ll=${lat.toFixed(6)},${lon.toFixed(6)}&n=${name}`;
 window.open(u,'_blank','noopener');
}
function eventCard(e){
 const direct=e.class==='direct',idx=signalIndex(e);
 const before=e.before?.datetime?fmtShort(e.before.datetime):'—';
 const after=e.after?.datetime?fmtShort(e.after.datetime):'—';
 const area=e.area_ha!=null?`${Number(e.area_ha).toFixed(2)} га`:'—';
 const meta=direct
  ? `${esc(e.source||'')} · ${esc(e.date||'')} ${esc(e.time||'')} ${e.frp?'· FRP '+esc(e.frp):''}`
  : `${esc(e.mode||'')} · ${deltaLabel(e)} · площадь ≈ ${area}`;
 const temporal=direct?'':`<div class="finding-temporal"><span>До <b>${esc(before)}</b></span><span>После <b>${esc(after)}</b></span></div>`;
 const why=direct
  ? 'Прямой тепловой сигнал FIRMS/VIIRS.'
  : `Контур построен по cloud-masked пикселям после компенсации общего сезонного сдвига сцены. Индекс сигнала ${idx}/100 — внутренний score, не вероятность события.`;
 return `<div class="alert-card ${direct?'direct':'candidate'}" style="--event:${eventColor(e)}">
   <div class="alert-card-head"><span class="alert-class">${eventLabel(e)}</span><span class="alert-score">${direct?'THERMAL':'сигнал '+idx+'/100'}</span></div>
   <b>${esc(e.title||'Изменение')}</b>
   <small>${meta}</small>
   ${temporal}
   <div class="finding-why">${esc(why)}</div>
   <div class="alert-actions"><button data-event-focus="${esc(e.id)}">Показать на карте</button>${(!direct&&e.before?.id&&e.after?.id)?`<button data-event-compare="${esc(e.id)}">До / после</button>`:''}<button data-event-osmand="${esc(e.id)}">OsmAnd ↗</button><button data-event-organic="${esc(e.id)}">Organic ↗</button></div>
 </div>`;
}
function visibleEvents(){return state.events.filter(findingVisible).sort((a,b)=>signalIndex(b)-signalIndex(a))}
function syncEventLayerVisibility(){
 const visible=new Set(visibleEvents().map(e=>e.id));
 const show=$('eventLayer')?.checked!==false;
 for(const e of state.events){
   const l=state.eventLayerById[e.id];if(!l)continue;
   const should=show&&visible.has(e.id);
   const on=state.map.hasLayer(l);
   if(should&&!on)l.addTo(state.map);
   if(!should&&on)state.map.removeLayer(l);
 }
}
function renderEventList(){
 const configured=!!state.alertMeta?.firms_configured;
 const d=state.alertMeta?.diagnostics||{};
 const perf=state.alertMeta?.analysis_seconds!=null
   ? `<div class="analysis-meta">Анализ: <b>${state.alertMeta.analysis_seconds} с</b> · ${d.strategy==='whole_aoi_part'?'единый AOI-растр':'fallback: выборочная детализация'}${d.analysis_resolution_m?' · ≈ '+d.analysis_resolution_m+' м/пиксель':''}${d.strategy!=='whole_aoi_part'?' · coarse '+(d.coarse_cells??'—')+' → refine '+(d.refined_cells??'—'):''}</div>`
   : '';
 const sourceHtml=`<div class="source-strip">
   <span class="src on">Pixel-change engine: ON</span>
   <span class="src ${configured?'on':'off'}">FIRMS: ${configured?'ON':'нет ключа'}</span>
   <span class="src ext">GFW: внешний источник</span>
 </div>${perf}`;
 const list=visibleEvents(),total=state.events.length;
 if($('findingStats'))$('findingStats').textContent=`Показано ${list.length} из ${total} сигналов${state.alertMeta?.diagnostics?.truncated?' · серверный safety-cap 200':''}.`;
 $('alertList').innerHTML=sourceHtml+(list.length?list.map(eventCard).join(''):`<div class="empty"><b>По текущему фильтру находок нет.</b><br>Снизьте минимальный индекс сигнала или включите другой тип.</div>`);
 $('alertCount').textContent=String(list.length);
 syncEventLayerVisibility();
}
function renderEvents(payload){
 clearEvents();
 state.alertMeta=payload||{};state.events=(payload&&payload.events)||[];
 for(const e of state.events){
   const col=eventColor(e);let l=null;
   try{
    if(e.geometry?.type==='Point'){
      const [lon,lat]=e.geometry.coordinates;
      l=L.circleMarker([lat,lon],{radius:10,color:'#fff',weight:2,fillColor:col,fillOpacity:.92});
    }else{
      l=L.geoJSON(e.geometry,{style:{color:col,weight:3,fillColor:col,fillOpacity:.24}});
    }
    if(!l)continue;
    const idx=signalIndex(e),area=e.area_ha!=null?`<br>Площадь ≈ ${Number(e.area_ha).toFixed(2)} га`:'';
    const delta=e.delta_index!=null?`<br>${deltaLabel(e)}`:'';
    l.bindPopup(`<b style="color:${col}">${esc(eventLabel(e))}</b><br><strong>${esc(e.title||'')}</strong><br>${esc(e.source||'')}${e.class==='candidate'?'<br>Индекс сигнала: '+idx+'/100':''}${area}${delta}`);
    state.eventLayers.push(l);state.eventLayerById[e.id]=l;
   }catch(err){}
 }
 renderEventList();
 const direct=state.events.filter(e=>e.class==='direct').length;
 const cand=state.events.filter(e=>e.class==='candidate').length;
 if(direct>0){
   $('event').className='event bad';$('event').innerHTML=`<div class="event-icon">!</div><div><b>Прямых алертов: ${direct}</b><span>Есть FIRMS/VIIRS термосигнал. Откройте вкладку «Находки».</span></div>`;
 }else if(cand>0){
   const top=Math.max(...state.events.filter(e=>e.class==='candidate').map(signalIndex));
   $('event').className='event warn';$('event').innerHTML=`<div class="event-icon">△</div><div><b>Контуров изменений: ${cand}</b><span>Максимальный индекс сигнала ${top}/100. Это скрининг, не подтверждённое событие.</span></div>`;
 }else{
   $('event').className='event ok';$('event').innerHTML='<div class="event-icon">✓</div><div><b>Значимых находок не выявлено</b><span>Свежие данные есть, но pixel-level скрининг не сформировал контуры выше порога.</span></div>';
 }
 bringOperationalLayers();
 const top=visibleEvents()[0];
 if(top){
   document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.dataset.tab==='alerts'));
   document.querySelectorAll('.tab-body').forEach(x=>x.classList.toggle('active',x.id==='alerts'));
   focusEvent(top.id,true);
 }
}

function addFootprints(){
 clearFootprints();if(!$('footprints').checked)return;
 const groups=[['Sentinel‑1',state.s1Scenes,'#4fc3f7'],['Sentinel‑2',state.s2Scenes,'#79d48d'],['NISAR',state.nisarScenes,'#ffc857']];
 for(const [name,items,color] of groups){for(const x of (items||[]).slice(0,12)){if(!x.geometry)continue;try{
  const l=L.geoJSON(x.geometry,{style:{color,weight:1,opacity:.34,fillOpacity:0,dashArray:'4 6'}}).addTo(state.map);
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
function renderEvidenceMatrix(activity){
 const box=$('evidenceMatrix');if(!box)return;
 const s=activity?.summary||{};
 const firmsConfigured=!!state.health?.firms_configured;
 const rows=[
  ['Sentinel‑2',s.sentinel2>0?'ДОСТУПЕН':'НЕТ',s.sentinel2>0?'оптическое изменение':'нет сцен'],
  ['Sentinel‑1',s.sentinel1>0?'ДОСТУПЕН':'НЕТ',s.sentinel1>0?'SAR для проверки':'нет сцен'],
  ['NISAR',s.nisar>0?'ДОСТУПЕН':'НЕТ',s.nisar>0?'L-band контекст':'нет продуктов'],
  ['FIRMS',firmsConfigured?(s.firms>0?'АЛЕРТ':'ON'):'OFF',firmsConfigured?(s.firms>0?'есть термосигнал':'термоточек нет'):'нужен бесплатный MAP_KEY']
 ];
 box.innerHTML=rows.map(r=>`<div><span>${r[0]}</span><b class="${r[1]==='OFF'||r[1]==='НЕТ'?'e-off':'e-on'}">${r[1]}</b><small>${r[2]}</small></div>`).join('');
}
async function sensors(){
 try{const p=await getJSON('/api/v3/providers');$('sensorList').innerHTML=p.providers.map(x=>`<div class="item"><b>${esc(x.name)}</b><small>${esc((x.missions||[]).join(' · '))}</small><div class="meta">${esc(x.mode)}${x.key_required?' · требуется ключ':''}</div></div>`).join('')}
 catch(e){$('sensorList').innerHTML='<div class="empty">Не удалось получить состояние провайдеров.</div>'}
}

async function scan(){
 if(!state.aoi){toast('Сначала выберите или нарисуйте участок');return}
 if(state.scanActive)return;
 state.scanActive=true;persistMonitor();
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
  renderSummary(activity);renderEvidenceMatrix(activity);fillSceneSelectors();renderData(activity);addFootprints();
  $('scan').textContent='Строю контуры изменений…';
  let ev=null;
  try{ev=await getJSON(`/api/v3/events/candidates?bbox=${b}&days=${days}&scenario=${encodeURIComponent(state.scenario)}`)}
  catch(err){ev={events:[],count:0,firms_configured:state.health?.firms_configured,warning:err.message};toast('Слой находок временно недоступен: '+err.message,5000)}
  renderEvents(ev);
  setUpdated();$('mapHint').style.display='none';toast(`Обновлено: находки ${state.events.length} · S1 ${state.s1Scenes.length} · S2 ${state.s2Scenes.length} · NISAR ${state.nisarScenes.length}`);
 }catch(e){setStatus(false,'ошибка обновления');toast('Не удалось обновить мониторинг: '+e.message,6000)}
 finally{state.scanActive=false;$('scan').disabled=false;$('scan').textContent='Проверить участок'}
}

function scheduleAutoWatch(){
 if(state.autoWatchTimer){clearInterval(state.autoWatchTimer);state.autoWatchTimer=null}
 const on=$('autoWatch')?.checked!==false;persistMonitor();
 if($('watchState'))$('watchState').textContent=on?'Автомониторинг включён: перепроверка каждые 15 минут при открытой вкладке.':'Автомониторинг выключен.';
 if(!on)return;
 state.autoWatchTimer=setInterval(()=>{
  if(document.visibilityState==='visible'&&state.aoi&&!state.scanActive)scan();
 },15*60*1000);
}
async function startDefaultMonitor(){
 const restored=restoreMonitor();
 let savedScenario=null;try{savedScenario=localStorage.getItem(LS_SCENARIO)}catch(e){}
 if(savedScenario&&state.config.scenarios.some(x=>x.id===savedScenario))selectScenario(savedScenario);
 if(!restored){
  const p=state.config.presets.find(x=>x.id==='polissia_ovruch')||state.config.presets[0];
  if(p){
   setPreset(p);selectScenario('forest');$('days').value='30';
   toast('Автозапуск: Полесье · строю реальные находки',3500);
  }
 }
 if(state.aoi)await scan();
}
function setupTabs(){
 document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===b));
  document.querySelectorAll('.tab-body').forEach(x=>x.classList.toggle('active',x.id===b.dataset.tab));
 });
}
function setupEvents(){
 $('region').onchange=()=>{populatePresets($('region').value)};
 $('usePreset').onclick=()=>{const p=state.config.presets.find(x=>x.id===$('preset').value);if(p)setPreset(p)};
 $('demoPolissia').onclick=async()=>{const p=state.config.presets.find(x=>x.id==='polissia_ovruch');if(!p)return;setPreset(p);selectScenario('forest');$('days').value='30';toast('Демо: Полесье · Овруч/Народичи');await scan()};
 $('demoCase').onclick=async()=>{const p=state.config.presets.find(x=>x.id==='chornohora');if(!p)return;setPreset(p);selectScenario('forest');$('days').value='30';toast('Демо: Карпаты · Чорногора');await scan()};
 $('drawRect').onclick=()=>new L.Draw.Rectangle(state.map,{shapeOptions:{color:'#49d096',weight:2,fillOpacity:.07}}).enable();
 $('drawPoly').onclick=()=>new L.Draw.Polygon(state.map,{allowIntersection:false,shapeOptions:{color:'#49d096',weight:2,fillOpacity:.07}}).enable();
 $('screenAoi').onclick=currentScreenAOI;$('clearAoi').onclick=clearAOI;$('exportGeo').onclick=exportGeoJSON;
 $('focusAoi').onclick=()=>{if(!state.aoiLayer){toast('Сначала выберите участок');return}state.map.fitBounds(state.aoiLayer.getBounds(),{padding:[50,50],maxZoom:14,animate:true})};
 $('importGeo').onclick=()=>$('geoFile').click();$('geoFile').onchange=e=>{if(e.target.files[0])importGeoFile(e.target.files[0]);e.target.value=''};
 $('scan').onclick=scan;$('refreshTop').onclick=()=>state.aoi?scan():startDefaultMonitor();
 $('autoWatch').onchange=scheduleAutoWatch;
 $('base').onchange=switchBase;$('footprints').onchange=addFootprints;$('eventLayer').onchange=syncEventLayerVisibility;
 $('findingType').onchange=()=>{state.findingType=$('findingType').value;renderEventList()};
 $('signalMin').oninput=()=>{state.minSignal=Number($('signalMin').value);$('signalValue').textContent=String(state.minSignal);renderEventList()};
 $('focusTopFinding').onclick=()=>{const e=visibleEvents()[0];if(e)focusEvent(e.id,true);else toast('Нет находок по текущему фильтру')};
 $('s2Scene').onchange=updateS2Info;$('showS2').onclick=()=>showS2ById($('s2Scene').value,$('s2Mode').value);$('hideS2').onclick=hideS2;
 $('showS1').onclick=()=>showS1ById($('s1Scene').value,$('s1Pol').value);$('hideS1').onclick=hideS1;
 $('startCompare').onclick=startCompare;$('stopCompare').onclick=stopCompare;
 $('openGfw').onclick=()=>window.open('https://www.globalforestwatch.org/map/','_blank','noopener');
 $('openFirms').onclick=()=>window.open('https://firms.modaps.eosdis.nasa.gov/map/','_blank','noopener');
 $('dataList').onclick=e=>{const b=e.target.closest('button[data-kind]');if(!b)return;const id=decodeURIComponent(b.dataset.id);if(b.dataset.kind==='s2')showS2ById(id,'RGB');if(b.dataset.kind==='s2nbr')showS2ById(id,'NBR');if(b.dataset.kind==='s1')showS1ById(id,'VV')};
 $('alertList').onclick=e=>{
  const f=e.target.closest('button[data-event-focus]');if(f){focusEvent(f.dataset.eventFocus,true);return}
  const c=e.target.closest('button[data-event-compare]');if(c){compareEvent(c.dataset.eventCompare);return}
  const o=e.target.closest('button[data-event-osmand]');if(o){openOsmAnd(o.dataset.eventOsmand);return}
  const m=e.target.closest('button[data-event-organic]');if(m){openOrganic(m.dataset.eventOrganic);return}
 };
}
async function init(){
 initMap();setupTabs();setupEvents();resetSummary();
 const c=await getJSON('/api/config');setupConfig(c);await health();await sensors();setUpdated();
 try{$('autoWatch').checked=localStorage.getItem(LS_AUTOWATCH)!=='0'}catch(e){}
 scheduleAutoWatch();
 setInterval(()=>health().catch(()=>{}),60000);
 setTimeout(()=>startDefaultMonitor().catch(e=>toast('Автозапуск не удался: '+e.message,5000)),350);
}
init().catch(e=>{setStatus(false,'ошибка запуска');toast('Ошибка запуска OEO: '+e.message,7000)});
