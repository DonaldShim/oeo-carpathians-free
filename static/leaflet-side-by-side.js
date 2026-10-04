(function(){
if(typeof L==='undefined')return;
L.Control.SideBySide=L.Control.extend({
 options:{position:'topleft'},
 initialize:function(left,right,options){L.setOptions(this,options);this._left=left;this._right=right;},
 onAdd:function(map){
  this._map=map;
  var c=L.DomUtil.create('div','leaflet-sbs-control');
  c.style.position='absolute';c.style.left='0';c.style.top='0';c.style.width='100%';c.style.height='100%';c.style.pointerEvents='none';
  var r=L.DomUtil.create('input','leaflet-sbs-range',c);
  r.type='range';r.min='0';r.max='1000';r.value='500';
  r.style.position='absolute';r.style.left='0';r.style.top='50%';r.style.width='100%';r.style.margin='0';r.style.transform='translateY(-50%)';r.style.pointerEvents='auto';r.style.zIndex='999';
  this._range=r;L.DomEvent.disableClickPropagation(c);L.DomEvent.on(r,'input',this._update,this);
  map.on('move zoom resize layeradd',this._update,this);setTimeout(this._update.bind(this),0);return c;
 },
 onRemove:function(map){if(this._range)L.DomEvent.off(this._range,'input',this._update,this);map.off('move zoom resize layeradd',this._update,this);this._clear(this._left);this._clear(this._right);},
 _container:function(layer){return layer&&(layer.getContainer?layer.getContainer():layer._container);},
 _clear:function(layer){var c=this._container(layer);if(c){c.style.clipPath='';c.style.webkitClipPath='';}},
 _update:function(){
  if(!this._map||!this._range)return;var w=this._map.getSize().x,x=w*(Number(this._range.value)/1000);
  var lc=this._container(this._left),rc=this._container(this._right);
  if(lc){var a='inset(0 '+Math.max(0,w-x)+'px 0 0)';lc.style.clipPath=a;lc.style.webkitClipPath=a;}
  if(rc){var b='inset(0 0 0 '+Math.max(0,x)+'px)';rc.style.clipPath=b;rc.style.webkitClipPath=b;}
 }
});
L.control.sideBySide=function(left,right,options){return new L.Control.SideBySide(left,right,options);};
})();