'use strict';
const el = id => document.getElementById(id);
let duration = 0, filename = null, start = 0, end = 0, busy = false, previewSelection = false;
const labels = {queued:'Waiting in the queue…', downloading:'Downloading the source…', encoding:'Trimming and framing your clip…', transcribing:'Transcribing speech locally…', captioning:'Burning in captions…'};
const format = value => `${Math.floor(value / 60)}:${Math.floor(value % 60).toString().padStart(2,'0')}`;
function status(id, text, kind = '') { el(id).textContent = text; el(id).className = kind; }
function setBusy(value) { busy = value; el('loadBtn').disabled = value; el('createBtn').disabled = value; }
async function api(path, data) {
  const response = await fetch(path, {signal:AbortSignal.timeout(30000), ...(data ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)} : {})});
  let result;
  try { result = await response.json(); } catch { throw new Error('The server returned an unreadable response. Check that the app is running.'); }
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status}).`);
  return result;
}
async function waitForJob(job, statusId) {
  // Await each poll before scheduling the next: slow requests never overlap.
  while (true) {
    const result = await api(`/api/job/${job}`);
    if (result.status === 'done') return result;
    if (result.status === 'error') throw new Error(result.error);
    status(statusId, labels[result.status] || 'Processing…', 'busy');
    await new Promise(resolve => setTimeout(resolve, 1200));
  }
}
el('loadForm').addEventListener('submit', async event => {
  event.preventDefault(); if (busy) return;
  setBusy(true); filename = null; previewSelection = false; el('preview').pause();
  el('editorPanel').classList.add('hidden'); el('resultPanel').classList.add('hidden');
  status('loadStatus','Adding your source…','busy');
  try {
    const job = await api('/api/load', {url:el('url').value.trim()});
    const source = await waitForJob(job.job_id,'loadStatus');
    filename = source.filename; duration = source.duration; start = 0; end = Math.min(30,duration);
    el('preview').src = source.stream_url;
    el('captionsToggle').disabled = !source.has_audio; el('captionsToggle').checked = source.has_audio;
    el('editorPanel').classList.remove('hidden'); render();
    status('loadStatus',`Source ready · ${format(duration)}${source.has_audio ? '' : ' · No audio; captions disabled'}`);
    status('status','');
  } catch(error) { status('loadStatus',error.message,'error'); }
  finally { setBusy(false); }
});
function render() {
  if (!duration) return;
  const percent = time => `${time / duration * 100}%`;
  el('selection').style.left = percent(start); el('selection').style.width = percent(end-start);
  el('handleStart').style.left = percent(start); el('handleEnd').style.left = percent(end);
  for (const [id,time,min,max] of [['handleStart',start,0,end-.1],['handleEnd',end,start+.1,duration]]) {
    el(id).setAttribute('aria-valuenow',time.toFixed(1)); el(id).setAttribute('aria-valuemin',Math.max(0,min));
    el(id).setAttribute('aria-valuemax',Math.max(0,max)); el(id).setAttribute('aria-valuetext',`${time.toFixed(1)} seconds`);
  }
  el('startInput').value = start.toFixed(1); el('endInput').value = end.toFixed(1);
  el('startInput').max = duration; el('endInput').max = duration;
  el('selectionLabel').textContent = `${format(start)} → ${format(end)} · ${(end-start).toFixed(1)}s`;
  el('durationLabel').textContent = format(duration);
}
function change(isStart, value) {
  if (!Number.isFinite(value) || !duration) return;
  const gap = Math.min(.1,duration);
  if(isStart) start = Math.max(0,Math.min(value,end-gap));
  else end = Math.min(duration,Math.max(value,start+gap));
  render();
}
for(const [id,isStart] of [['handleStart',true],['handleEnd',false]]) {
  const handle = el(id);
  handle.addEventListener('pointerdown', event => {event.preventDefault();handle.setPointerCapture(event.pointerId);});
  handle.addEventListener('pointermove', event => {
    if(!handle.hasPointerCapture(event.pointerId))return;
    const rect=el('timeline').getBoundingClientRect();change(isStart,(event.clientX-rect.left)/rect.width*duration);
  });
  handle.addEventListener('pointerup',event=>{if(handle.hasPointerCapture(event.pointerId))handle.releasePointerCapture(event.pointerId);});
  handle.addEventListener('keydown',event=>{
    const value=isStart?start:end,step=event.shiftKey?1:.1;
    if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){
      event.preventDefault();change(isStart,event.key==='Home'?0:event.key==='End'?duration:value+(event.key==='ArrowLeft'?-step:step));
    }
  });
}
el('startInput').addEventListener('change',()=>change(true,el('startInput').valueAsNumber));
el('endInput').addEventListener('change',()=>change(false,el('endInput').valueAsNumber));
el('preview').addEventListener('timeupdate',()=>{
  if(duration)el('playhead').style.left=`${el('preview').currentTime/duration*100}%`;
  if(previewSelection && el('preview').currentTime>=end){el('preview').pause();previewSelection=false;}
});
el('preview').addEventListener('error',()=>status('status','This browser could not preview the source codec. You can still select times and try an export.','error'));
el('previewBtn').addEventListener('click',async()=>{
  el('preview').currentTime=start;previewSelection=true;
  try{await el('preview').play();}catch{previewSelection=false;status('status','Preview playback is unavailable. Try the video controls.','error');}
});
el('createBtn').addEventListener('click',async()=>{
  if(busy||!filename)return;
  if(end-start>180){status('status','Select a clip no longer than 180 seconds.','error');return;}
  setBusy(true);el('resultPanel').classList.add('hidden');status('status','Queuing your export…','busy');
  try{
    const job=await api('/api/create_clip',{filename,start,end,captions:el('captionsToggle').checked});
    const result=await waitForJob(job.job_id,'status');
    const video=document.createElement('video');video.controls=true;video.src=result.download_url;video.setAttribute('aria-label','Exported short preview');
    const link=document.createElement('a');link.className='download';link.href=result.download_url;link.download='framecut.mp4';link.textContent='Download MP4 ↓';
    el('result').replaceChildren(video,link);el('resultPanel').classList.remove('hidden');status('status','Export complete.');
  }catch(error){status('status',error.message,'error');}
  finally{setBusy(false);}
});
