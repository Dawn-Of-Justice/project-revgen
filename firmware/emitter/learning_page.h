#pragma once
static const char LEARNING_PAGE[] PROGMEM = R"HTML(
<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RevGen remote setup</title><style>
body{font:17px system-ui;max-width:760px;margin:32px auto;padding:0 20px;color:#172b3a;background:#f5f8fa}h1{font-size:28px}section{background:white;padding:22px;margin:18px 0;border-radius:12px}label{display:block;margin:12px 0}input,select,button{font:inherit;padding:10px;box-sizing:border-box}input,select{width:100%;margin-top:5px}button{margin:5px 8px 5px 0;cursor:pointer}small{display:block}pre{white-space:pre-wrap;overflow-wrap:anywhere}#message{font-weight:600}li{margin:12px 0}
</style><h1>Teach RevGen your remotes</h1><p>Learning mode is open because you held the emitter button. Regular voice commands are paused. Keep this page on your home Wi-Fi.</p>
<section><label>Device ID <input id="device" value="tv" maxlength="32" pattern="[a-z][a-z0-9_]*"></label><small>Use tv or stb for the main television/box; bedroom_tv, fan, etc. for additional devices.</small>
<label>Device name <input id="device_name" value="Living room TV" maxlength="64"></label>
<label>Action ID <input id="action" value="volume_up" maxlength="32" list="actions"></label><datalist id="actions"><option>power</option><option>volume_up</option><option>volume_down</option><option>channel_up</option><option>channel_down</option><option>digit_0</option><option>digit_1</option><option>digit_2</option><option>digit_3</option><option>digit_4</option><option>digit_5</option><option>digit_6</option><option>digit_7</option><option>digit_8</option><option>digit_9</option><option>mute</option><option>up</option><option>down</option><option>left</option><option>right</option><option>ok</option></datalist>
<label>Action name <input id="name" value="Volume up" maxlength="64"></label>
<label>Button behavior <select id="behavior"><option value="button">Ordinary button</option><option value="power_toggle">Power toggle (same button turns on and off)</option><option value="power_on">Discrete power ON only</option><option value="power_off">Discrete power OFF only</option></select></label>
<small>Most power buttons are toggles. Only select discrete ON/OFF if the original remote has separate commands.</small>
<button id="capture">Start capture / retry</button><button id="test" disabled>Test captured signal</button><button id="save" disabled>Save and upload</button>
<p id="message" aria-live="polite">Start capture, then press and release the original remote button twice.</p><pre id="code"></pre></section>
<section><h2>Channel names</h2><p>First learn digits 0–9 for device stb. Then assign a channel name to its number.</p><label>Channel ID <input id="channel_id" placeholder="asianet_hd" maxlength="32"></label><label>Channel name <input id="channel_name" placeholder="Asianet HD" maxlength="64"></label><label>Channel number <input id="channel_number" inputmode="numeric" maxlength="6" placeholder="804"></label><button id="channel">Save channel</button></section>
<section><h2>Saved mappings</h2><p>Saved locally survives resets. Uploaded means the backend confirmed storage; it does not mean the appliance responded.</p><ul id="entries"></ul><button id="retry">Retry uploads</button><button id="exit">Exit learning mode</button></section>
<script>
const token='__SESSION__', $=id=>document.getElementById(id);let captureVersion=0;
async function api(path,data){const r=await fetch('/api/'+path,{method:'POST',headers:{'Content-Type':'application/json','X-Learn-Token':token},body:JSON.stringify(data||{})});const b=await r.json();if(!r.ok)throw Error(b.error||'Request failed');return b;}
function fields(){return Object.fromEntries(['device','device_name','action','name','behavior'].map(k=>[k,$(k).value.trim()]));}
async function act(path,data){try{const r=await api(path,data);$('message').textContent=r.message||'Done';return r;}catch(e){$('message').textContent=e.message;}}
$('capture').onclick=()=>act('capture');$('test').onclick=()=>act('test',{version:captureVersion});
$('save').onclick=()=>{if(confirm('Save this command? This replaces the same device/action ID if it already exists. Check any duplicate warning first.'))act('save',{...fields(),version:captureVersion});};
$('channel').onclick=()=>act('channel',{device:'stb',device_name:'Set-top box',action:$('channel_id').value.trim(),name:$('channel_name').value.trim(),channel_number:$('channel_number').value.trim(),behavior:'button'});
$('retry').onclick=()=>act('retry');$('exit').onclick=async()=>{if(await act('exit')){clearInterval(timer);$('message').textContent='Learning mode closed. Hold the button for 5 seconds to reopen.';}};
async function poll(){try{const r=await fetch('/api/status',{headers:{'X-Learn-Token':token}});if(!r.ok)throw Error();const b=await r.json();captureVersion=b.version;$('message').textContent=b.message;$('code').textContent=b.code?JSON.stringify(b.code,null,2):'';$('test').disabled=$('save').disabled=!b.ready;const list=$('entries');list.replaceChildren();for(const e of b.entries){const li=document.createElement('li');li.textContent=e.device_name+' / '+e.name+' — '+(e.error||e.warning||(e.synced?'Uploaded':'Saved locally; upload pending'));list.append(li);}}catch(e){$('message').textContent='Connection closed or learning mode expired. Reopen with a 5-second button hold.';}}
const timer=setInterval(poll,1800);poll();
</script></html>
)HTML";
