/* 选题页首答草稿：先存本机，提交生成后关联到实际条目；不重复提交生成请求。 */
"use strict";
const TrainingBaseline = (() => {
  let dbPromise=null,active=null,activeRecorder=null;
  function db(){if(!dbPromise)dbPromise=new Promise((resolve,reject)=>{const r=indexedDB.open('ielts-training-baselines',1);r.onupgradeneeded=()=>r.result.createObjectStore('drafts');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});return dbPromise;}
  async function storage(id,value){const database=await db();return new Promise((resolve,reject)=>{const tx=database.transaction('drafts',value===undefined?'readonly':'readwrite'),s=tx.objectStore('drafts'),r=value===undefined?s.get(id):s.put(value,id);tx.oncomplete=()=>resolve(r.result);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);});}
  async function mount(q){
    const input=document.getElementById('bank-answer-input');if(!input || document.getElementById('baseline-root'))return;
    const box=document.createElement('section');box.id='baseline-root';box.className='training-row';
    box.innerHTML='<h2>先口头试答一次</h2><p>先暴露卡点，再填写实际回答文字；录音不会自动转写。</p><div class="study-actions"><button type="button" class="study-button primary" id="baseline-start">开始首答录音</button><button type="button" class="study-button" id="baseline-stop" disabled>停止并保存</button><button type="button" class="study-button" id="baseline-skip">不录音继续</button></div><p id="baseline-status" role="status"></p><audio id="baseline-audio" controls hidden></audio><label for="baseline-intent">中文补充意图</label><textarea id="baseline-intent"></textarea><label for="baseline-feedback">外部反馈（待核对的建议）</label><textarea id="baseline-feedback"></textarea><button type="button" class="study-button" id="baseline-retry" hidden>重试保存或关联录音</button>';
    input.before(box);let old=await storage(q.id) || {},chunks=[],localBlob=null,rec=null,stream=null,started=0;
    active={qid:q.id,old};const status=x=>{if(box.isConnected)box.querySelector('#baseline-status').textContent=x;};
    function show(){if(old.blob){const audio=box.querySelector('audio');audio.hidden=false;audio.src=URL.createObjectURL(old.blob);status('首答已保存在本机，提交后会关联到本题。');}box.querySelector('#baseline-intent').value=old.intent || '';box.querySelector('#baseline-feedback').value=old.feedback || '';}
    show();
    async function save(){old={...old,blob:localBlob || old.blob,nativePath:localBlob?.nativePath || old.nativePath,duration:localBlob?Math.max(.1,(Date.now()-started)/1000):old.duration,unexposed:true,
      intent:box.querySelector('#baseline-intent').value,feedback:box.querySelector('#baseline-feedback').value};
      try{await storage(q.id,old);if(active?.qid===q.id)active.old=old;show();box.querySelector('#baseline-retry').hidden=true;}
      catch(e){status('本机保存失败，请保持本页并重试：'+e.message);box.querySelector('#baseline-retry').hidden=false;}}
    box.querySelector('#baseline-start').onclick=async()=>{try{stream=await navigator.mediaDevices.getUserMedia({audio:true});chunks=[];rec=new MediaRecorder(stream);started=Date.now();rec.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};rec.onstop=async()=>{stream.getTracks().forEach(t=>t.stop());localBlob=chunks.length===1?chunks[0]:new Blob(chunks,{type:rec.mimeType || 'audio/webm'});await save();box.querySelector('#baseline-start').disabled=false;box.querySelector('#baseline-stop').disabled=true;};rec.start();box.querySelector('#baseline-start').disabled=true;box.querySelector('#baseline-stop').disabled=false;status('正在录音；完成后停止并保存。');}catch(e){status('无法录音：'+e.message+'，可以不录音继续。');}};
    box.querySelector('#baseline-stop').onclick=()=>rec?.stop();
    box.querySelector('#baseline-skip').onclick=async()=>{old.skipped=true;await save();status('本次无首答录音，提交后按本人自评保留。');};
    box.querySelector('#baseline-retry').onclick=async()=>{await save();if(old.target)await attach(q.id,old.target,document.getElementById('bank-answer-input')?.value || old.answer);};
    ['baseline-intent','baseline-feedback'].forEach(id=>box.querySelector('#'+id).onchange=()=>save());
    if(old.target){status('上次回答已提交，可以重试关联首答，不需要重复生成。');box.querySelector('#baseline-retry').hidden=false;}
    activeRecorder=()=>{if(rec?.state==='recording')rec.stop();};
  }
  async function attach(qid,res,answer){
    let old=await storage(qid);if(!old)return;
    old={...old,target:res,answer};await storage(qid,old);
    const base=`/api/topics/${encodeURIComponent(res.topic_id)}/items/${encodeURIComponent(res.item_id)}/study`;
    try{
      let current=await api('GET',base+'/training');
      if(old.blob && !old.recording_id){const blob=old.blob;if(old.nativePath)blob.nativePath=old.nativePath;
        old.upload_key=old.upload_key || crypto.randomUUID();await storage(qid,old);
        const response=await fetch(base+`/recordings?stage=before&duration_sec=${old.duration}&upload_key=${old.upload_key}`,{method:'POST',headers:{'Content-Type':blob.type || 'audio/webm'},body:blob});const result=await response.json();if(!response.ok)throw new Error(result.detail || '录音未保存');old.recording_id=result.id;await storage(qid,old);}
      const action=async(name,data)=>{current=await api('POST',base+'/training/actions',{version:2,fingerprint:current.state.fingerprint,action_id:'baseline-'+qid+'-'+name,action:name,...data});};
      if(current.state.phase==='before')await action('start',{recording_id:old.recording_id || null,unexposed:old.unexposed});
      if(current.state.phase==='inputs')await action('inputs',{answer,intent:old.intent || '',feedback:old.feedback || ''});
      await storage(qid,{completed:true});
    }catch(e){toast('回答已提交，首答仍保存在本机，可返回该题重试关联：'+e.message);}
  }
  async function keepRecording(record,key){return storage('recording:'+(record?.savePath || key),record?{...record,nativePath:record.data.nativePath}:null);}
  async function recoverRecording(key){const record=await storage('recording:'+key);if(record?.nativePath)record.data.nativePath=record.nativePath;return record;}
  return {mount,attach,keepRecording,recoverRecording,values(){return {intent:document.getElementById('baseline-intent')?.value || '',feedback:document.getElementById('baseline-feedback')?.value || ''};},leave(){activeRecorder?.();activeRecorder=null;}};
})();
