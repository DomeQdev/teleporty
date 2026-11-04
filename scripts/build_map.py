#!/usr/bin/env python3
"""Buduje out/mapa.html – interaktywna mapa do przeglądania kandydatów na teleporty.

Podkład: Esri World Imagery (domyślnie) / OSM / CyclOSM. Nakładka: infrastruktura rowerowa z OSM.
Lista hotspotów z filtrem, przyciski oceny (TELEPORT / nie / ?) zapisywane w localStorage,
eksport ocen do CSV.

Użycie:
    python3 scripts/build_map.py data/warszawa_ways.pkl out/hotspoty.json out/mapa.html
"""
import json
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(__file__))
from find_candidates import classify  # noqa: E402

BBOX = (20.84, 52.09, 21.28, 52.37)


def main(pkl, hotspots_path, out):
    d = pickle.load(open(pkl, "rb"))
    feats = []
    for w in d["ways"]:
        c = classify(w["tags"])
        if c[0] == "infra":
            k = {"pas": "p", "kontraruch": "p", "przejazd": "x"}.get(c[1], "d")
        elif c[0] == "crossing_ped":
            k = "c"
        else:
            continue
        co = w["coords"]
        if not any(BBOX[0] <= lo <= BBOX[2] and BBOX[1] <= la <= BBOX[3] for lo, la in co):
            continue
        feats.append([k, w["id"], [[round(lo, 6), round(la, 6)] for lo, la in co]])

    H = json.load(open(hotspots_path))
    hs = []
    for h in H:
        hs.append({
            "r": h["rank"], "s": h["score"], "t": h["teleport"], "n": h["names"],
            "la": h["lat"], "lo": h["lon"], "ty": [h["typ"]] if h.get("typ") else h["types"],
            "w": h.get("werdykt"), "k": h.get("komentarz"),
            "e": [{"id": e["node"], "la": e["lat"], "lo": e["lon"], "s": e["score"], "i": e["infra"],
                   "et": e["end_type"], "rs": e["reasons"],
                   "g": [e["gap"]["gap_lat"], e["gap"]["gap_lon"]] if e.get("gap") and e["gap"]["gap_m"] >= 2.5 else None,
                   "f": [e["fwd"]["fwd_lat"], e["fwd"]["fwd_lon"]] if e.get("fwd") else None}
                  for e in h["endpoints"]],
        })

    title = "Teleporty rowerowe Warszawa" + (" – zweryfikowane" if any(h.get("werdykt") for h in H) else "")
    html = TEMPLATE.replace("__TITLE__", title).replace("__INFRA__", json.dumps(feats, separators=(",", ":"))) \
                   .replace("__HOTSPOTS__", json.dumps(hs, ensure_ascii=False, separators=(",", ":")))
    with open(out, "w") as f:
        f.write(html)
    print(f"{out}: {len(hs)} hotspotów, {len(feats)} odcinków infry, {os.path.getsize(out) / 1e6:.1f} MB")


TEMPLATE = r"""<!doctype html>
<html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--bg:#fff;--fg:#111;--mut:#666;--line:#ddd;--sel:#fff3c4}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#1b1b1b;--fg:#eee;--mut:#999;--line:#333;--sel:#4a3f12}}
:root[data-theme="dark"]{--bg:#1b1b1b;--fg:#eee;--mut:#999;--line:#333;--sel:#4a3f12}
html,body{margin:0;height:100%;font:13px/1.35 system-ui,sans-serif;background:var(--bg);color:var(--fg)}
#app{display:flex;height:100%}
#side{width:390px;max-width:45vw;display:flex;flex-direction:column;border-right:1px solid var(--line)}
#map{flex:1}
#controls{padding:8px;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:6px;align-items:center}
#controls input[type=number]{width:55px}
#list{overflow:auto;flex:1}
.it{padding:6px 8px;border-bottom:1px solid var(--line);cursor:pointer}
.it.sel{background:var(--sel)}
.it b{font-variant-numeric:tabular-nums}
.tag{display:inline-block;padding:0 5px;border-radius:3px;font-size:11px;margin-right:3px;background:#8884}
.tp{background:#e0f;color:#fff}
.v-tak{border-left:5px solid #d00}.v-nie{border-left:5px solid #0a0}.v-moze{border-left:5px solid #e90}
.mut{color:var(--mut)}
#detail{padding:8px;border-top:1px solid var(--line);max-height:42%;overflow:auto}
#detail ul{margin:4px 0;padding-left:18px}
button{cursor:pointer}
.legend{background:#000a;color:#fff;padding:6px 8px;border-radius:4px;font-size:12px;line-height:1.6}
.sw{display:inline-block;width:18px;height:4px;vertical-align:middle;margin-right:5px}
@media (max-width:700px){#app{flex-direction:column-reverse}#side{width:auto;max-width:none;height:50%}}
</style></head><body>
<div id="app">
 <div id="side">
  <div id="controls">
   <label>min score <input id="min" type="number" step="0.5" value="0"></label>
   <label><input id="onlyTp" type="checkbox"> tylko z luką do innej infry</label>
   <select id="wf"><option value="">każdy werdykt</option><option value="teleport">teleport</option><option value="niepewne">niepewne</option><option value="blad_mapy">błąd mapy</option></select>
   <select id="vf"><option value="">wszystkie</option><option value="none">nieocenione</option><option value="tak">TELEPORT</option><option value="moze">?</option><option value="nie">nie</option></select>
   <input id="q" placeholder="ulica…" size="10">
   <button id="exp">CSV ocen</button>
   <span id="cnt" class="mut"></span>
  </div>
  <div id="list"></div>
  <div id="detail" class="mut">Kliknij hotspot. Klawisze: <b>j/k</b> następny/poprzedni, <b>t</b> TELEPORT, <b>n</b> nie, <b>m</b> ?, <b>s</b> Street View.</div>
 </div>
 <div id="map"></div>
</div>
<script>
const INFRA=__INFRA__;
const H=__HOTSPOTS__;
const KEY='teleporty-oceny-v1-'+document.title;
let votes={};try{votes=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
function saveVotes(){try{localStorage.setItem(KEY,JSON.stringify(votes))}catch(e){}}

const map=L.map('map',{preferCanvas:true,maxZoom:21}).setView([52.23,21.01],12);
const esri=L.tileLayer('https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}?blankTile=false',{maxZoom:21,maxNativeZoom:19,attribution:'Esri World Imagery'}).addTo(map);
const osm=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:21,maxNativeZoom:19,attribution:'© OpenStreetMap'});
const cyc=L.tileLayer('https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png',{maxZoom:21,maxNativeZoom:20,attribution:'CyclOSM / © OpenStreetMap'});
const ST={d:{color:'#00e000',weight:3},p:{color:'#1e8cff',weight:4},x:{color:'#ffe600',weight:4},c:{color:'#ff50c8',weight:2,dashArray:'3 3'}};
const infra=L.layerGroup();
const rend=L.canvas({padding:.5});
for(const [k,id,co] of INFRA){L.polyline(co.map(c=>[c[1],c[0]]),{...ST[k],renderer:rend,opacity:.9}).bindTooltip('way '+id).addTo(infra)}
infra.addTo(map);
const marks=L.layerGroup().addTo(map);
L.control.layers({'Esri satelita':esri,'OSM':osm,'CyclOSM':cyc},{'infra rowerowa (OSM)':infra,'kandydaci':marks}).addTo(map);
const lg=L.control({position:'bottomright'});lg.onAdd=()=>{const d=L.DomUtil.create('div','legend');d.innerHTML=
'<span class=sw style="background:#00e000"></span>DDR/CPR<br><span class=sw style="background:#1e8cff"></span>pas<br><span class=sw style="background:#ffe600"></span>przejazd<br><span class=sw style="background:#ff50c8"></span>przejście bez przejazdu<br><span class=sw style="background:#f0f"></span>luka do innej infry<br><span class=sw style="background:#f90"></span>dalszy ciąg na wprost';return d};lg.addTo(map);

function col(s,w){if(w)return {teleport:'#ff0040',niepewne:'#ffd000',blad_mapy:'#3aa0ff'}[w]||'#999';return s>=10?'#ff0040':s>=6?'#ff7a00':s>=3?'#ffd000':'#9adf6a'}
const hmark={};
for(const h of H){
  const m=L.circleMarker([h.la,h.lo],{radius:5+Math.min(9,h.s/1.5),color:'#000',weight:1,fillColor:col(h.s,h.w),fillOpacity:.85});
  m.on('click',()=>select(h.r,false));m.bindTooltip('#'+h.r+' '+h.n.slice(0,2).join(' / '));
  hmark[h.r]=m;
}
const det=L.layerGroup().addTo(map);
let shown=[],cur=null;
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function render(){
  const mn=+document.getElementById('min').value||0,tp=document.getElementById('onlyTp').checked,
        vf=document.getElementById('vf').value,wf=document.getElementById('wf').value,q=document.getElementById('q').value.toLowerCase();
  shown=H.filter(h=>h.s>=mn&&(!wf||h.w===wf)&&(!tp||h.t)&&(!vf||(vf==='none'?!votes[h.r]:votes[h.r]===vf))&&(!q||h.n.join(' ').toLowerCase().includes(q)));
  marks.clearLayers();shown.forEach(h=>hmark[h.r].addTo(marks));
  const L_=document.getElementById('list');
  L_.innerHTML=shown.map(h=>`<div class="it ${votes[h.r]?'v-'+votes[h.r]:''} ${cur===h.r?'sel':''}" data-r="${h.r}"><b>#${h.r}</b> <span class="mut">[${h.s}]</span> ${h.w?'<span class="tag" style="background:'+col(0,h.w)+';color:#000">'+esc(h.w)+'</span>':''}${h.t?'<span class="tag tp">luka</span>':''}${esc(h.n.slice(0,3).join(' / ')||'—')}<br><span class="mut">${h.ty.map(esc).join(', ')} · ${h.e.length} końc.</span>${h.k?'<br>'+esc(h.k):''}</div>`).join('');
  document.getElementById('cnt').textContent=shown.length+' / '+H.length;
}
document.getElementById('list').addEventListener('click',e=>{const it=e.target.closest('.it');if(it)select(+it.dataset.r,true)});
['min','onlyTp','vf','wf','q'].forEach(id=>document.getElementById(id).addEventListener('input',render));
function sv(la,lo){return `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${la},${lo}`}
function select(r,fly){
  cur=r;const h=H.find(x=>x.r===r);det.clearLayers();
  for(const e of h.e){
    L.circleMarker([e.la,e.lo],{radius:7,color:'#f00',weight:3,fill:false}).addTo(det);
    if(e.g)L.polyline([[e.la,e.lo],e.g],{color:'#f0f',weight:3}).addTo(det);
    if(e.f)L.polyline([[e.la,e.lo],e.f],{color:'#f90',weight:2,dashArray:'6 4'}).addTo(det);
  }
  if(fly)map.setView([h.la,h.lo],19);
  const v=votes[r]||'';
  document.getElementById('detail').className='';
  document.getElementById('detail').innerHTML=`<b>#${h.r}</b> score ${h.s} — ${esc(h.n.join(' / '))}<br>${h.w?'<b>'+esc(h.w)+'</b>: '+esc(h.k||'')+'<br>':''}
  <button data-v="tak" ${v==='tak'?'style="font-weight:bold"':''}>TELEPORT (t)</button>
  <button data-v="moze" ${v==='moze'?'style="font-weight:bold"':''}>? (m)</button>
  <button data-v="nie" ${v==='nie'?'style="font-weight:bold"':''}>nie (n)</button>
  <a href="${sv(h.la,h.lo)}" target="_blank">Street View</a> ·
  <a href="https://www.openstreetmap.org/#map=19/${h.la}/${h.lo}&layers=Y" target="_blank">OSM</a> ·
  <a href="https://www.google.com/maps/@${h.la},${h.lo},20z/data=!3m1!1e3" target="_blank">Google sat</a>
  ${h.e.map(e=>`<div style="margin-top:6px"><a href="https://www.openstreetmap.org/node/${e.id}" target="_blank">node ${e.id}</a> · ${esc(e.i)} · <i>${esc(e.et)}</i> · ${e.s} · <a href="${sv(e.la,e.lo)}" target="_blank">SV</a><ul>${e.rs.map(x=>'<li>'+esc(x)+'</li>').join('')}</ul></div>`).join('')}`;
  document.querySelectorAll('#detail button').forEach(b=>b.onclick=()=>vote(b.dataset.v));
  render();
  const el=document.querySelector('.it.sel');if(el)el.scrollIntoView({block:'nearest'});
}
function vote(v){if(cur==null)return;if(votes[cur]===v)delete votes[cur];else votes[cur]=v;saveVotes();select(cur,false)}
function step(d){if(!shown.length)return;let i=shown.findIndex(h=>h.r===cur);i=Math.max(0,Math.min(shown.length-1,i+d));select(shown[i].r,true)}
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT'||e.target.tagName==='SELECT')return;
  if(e.key==='j')step(1);else if(e.key==='k')step(-1);else if(e.key==='t')vote('tak');else if(e.key==='n')vote('nie');else if(e.key==='m')vote('moze');
  else if(e.key==='s'&&cur!=null){const h=H.find(x=>x.r===cur);window.open(sv(h.la,h.lo),'_blank')}});
document.getElementById('exp').onclick=()=>{
  const rows=[['rank','score','ocena','miejsce','lat','lon']];
  for(const h of H)if(votes[h.r])rows.push([h.r,h.s,votes[h.r],h.n.join(' / '),h.la,h.lo]);
  const csv=rows.map(r=>r.map(x=>'"'+String(x).replace(/"/g,'""')+'"').join(',')).join('\n');
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));a.download='teleporty_oceny.csv';a.click();
};
render();
</script></body></html>
"""

if __name__ == "__main__":
    main(*sys.argv[1:4])
