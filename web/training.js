/* 双端单题训练界面；持久化动作成功后才推进，记录与自评明确分开。 */
"use strict";
const TrainingUI = (() => {
  const names={before:'先回答',inputs:'确认原回答',understand:'理解与选重点',sentence:'逐句练习',outline:'组织整题',whole:'独立口答',summary:'复验与记录'};
  const labels={unstarted:'未开始',training:'训练中',awaiting_review:'待复验',mastered:'稳定掌握·本人复验'};
  const ratings={independent:'独立完成',needs_hint:'借助提示',unable:'仍有困难'};
  let ctx=null,tid='',iid='',token=0,busy=false,recorder=null,stream=null,blob=null,recId=null,
    started=0,timer=null,tick=null,lastInput=Date.now(),lastTick=Date.now(),elapsed=0,pending=null,
    playback=null,dictating=false,followup=false,noRecording=false,recordingStage='before',hintTimer=null,draftTimer=null,keyboardMode=false;
  const root=()=>document.getElementById('training-root');
  const path=(suffix='')=>`/api/topics/${encodeURIComponent(tid)}/items/${encodeURIComponent(iid)}/study${suffix}`;
  const link=(t,i)=>`#/train/${encodeURIComponent(t)}/${encodeURIComponent(i)}`;
  const button=(text,action,primary=false,extra='')=>`<button type="button" class="study-button ${primary?'primary':''}" data-train="${action}" ${extra}>${text}</button>`;
  const text=(id,label,value='',extra='')=>`<label class="training-field" for="${id}">${label}</label><textarea id="${id}" ${extra}>${esc(value)}</textarea>`;
  function note(message){const el=document.getElementById('training-status');if(el)el.textContent=message;}
  function touch(event){lastInput=Date.now();if(event)keyboardMode=event.type==='keydown';}
  async function send(action,data={},redraw=true){
    if(busy)return false;busy=true;
    const fingerprint=ctx.state.fingerprint,key=JSON.stringify({action,...data,fingerprint});
    if(!pending || pending.key!==key)pending={key,body:{version:2,fingerprint,action_id:crypto.randomUUID(),action,...data}};
    root()?.setAttribute('aria-busy','true');
    try {const result=await api('POST',path('/training/actions'),pending.body);pending=null;
      if(viewStale(token))return false;ctx=result;if(redraw)render();return true;
    }catch(e){note(`保存失败：${e.message}。内容保留，请重试。`);return false;
    }finally{busy=false;root()?.removeAttribute('aria-busy');}
  }
  function reset(){
    flush();
    const draft=document.getElementById('training-dictation');
    if(draft && ctx && !busy)send('dictation',{index:ctx.state.focus[ctx.state.index],draft:draft.value,passed:false},false);
    clearInterval(timer);clearInterval(tick);clearTimeout(hintTimer);clearTimeout(draftTimer);timer=tick=hintTimer=draftTimer=null;
    if(playback)playback.pause();playback=null;
    if(recorder?.state==='recording')recorder.stop();
    stream?.getTracks().forEach(t=>t.stop());stream=null;
    document.removeEventListener('pointerdown',touch);document.removeEventListener('keydown',touch);
  }
  async function flush(){if(!ctx || !elapsed || busy)return;const seconds=Math.min(120,elapsed);elapsed=0;
    if(!await send('activity',{seconds,notes:document.getElementById('training-notes')?.value ?? ctx.state.notes},false))elapsed+=seconds;}
  async function view(t,i,currentToken){
    reset();tid=t;iid=i;token=currentToken;ctx=null;recId=null;blob=null;dictating=false;followup=false;noRecording=false;
    $app.innerHTML='<div class="training-page"><p role="status">正在读取单题训练…</p></div>';
    try{const data=await api('GET',path('/training'));if(viewStale(token))return;ctx=data;dictating=!!ctx.state.sentences[ctx.state.focus[ctx.state.index]]?.draft;
      pendingRecording=await TrainingBaseline.recoverRecording(path('/recordings')).catch(()=>null);blob=pendingRecording?.data || null;if(viewStale(token))return;render();
      lastInput=lastTick=Date.now();elapsed=0;
      document.addEventListener('pointerdown',touch);document.addEventListener('keydown',touch);
      tick=setInterval(()=>{const now=Date.now();if(!document.hidden && !ctx.state.paused && (now-lastInput<120000 || recorder?.state==='recording' || playback && !playback.paused))elapsed+=Math.min(2,(now-lastTick)/1000);lastTick=now;if(elapsed>=15)flush();},1000);
    }catch(e){if(!viewStale(token))$app.innerHTML=`<div class="training-page"><h1>训练暂时无法读取</h1><p>${esc(e.message)}</p><a href="#/today">返回练习</a></div>`;}
  }
  function audioUrl(url){return MobileRuntime.native?(MobileRuntime.mediaUrl(url) || MobileRuntime.fileUrl(url)):url;}
  function recordings(){return (ctx.recordings || []).map(r=>`<div class="training-record"><p>${esc(({before:ctx.state.baseline_unexposed?'首次试答':'开始训练时口答',chinese:'提纲口答',recall:'独立整题口答',oral_review:'句子口答'})[r.stage] || '练习录音')} · ${esc(r.created_at || '')}</p><audio controls preload="none" src="${esc(r.path?MobileRuntime.fileUrl(r.path):audioUrl(path('/recordings/'+r.id)))}"></audio></div>`).join('') || '<p>还没有保存录音；无录音的尝试仅为本人自评。</p>';}
  function recorderPanel(stage){recordingStage=stage;return `<section class="study-recorder training-recorder"><h2>${stage==='before'?'先试着回答一次':'完整回答录音'}</h2><div class="study-actions">${button('开始录音','record',true)}${button('停止并保存','stop',false,'disabled')}<span id="training-record-time" role="timer"></span></div><p id="training-record-status">停止后自动保存；允许回听与重录，历史保留。</p>${button('重试保存录音','save-record',false,blob?'':'hidden')}</section>`;}
  function promptList(){const m=ctx.material,blocks=ctx.part===2 && m.groups?.length?m.groups:m.outline || [];return blocks.length?blocks.map(x=>`<p>${esc(x.label)}${(x.indices || []).map(n=>`<span class="study-muted">${esc(m.sentences[n]?.zh || '')}</span>`).join('')}</p>`).join(''):`<p>${esc(m.complete_chinese || '材料准备好后显示中文内容提示。')}</p>`;}
  function render(){
    if(!ctx || viewStale(token))return;
    const s=ctx.state,m=ctx.material,rows=m.sentences || [],phase=s.phase;
    let body='';
    if(phase==='before')body=`<p>先回答这道题，不看参考。已有材料的补录将标注为开始训练时口答。</p>${recorderPanel('before')}<label><input id="training-unexposed" type="checkbox"> 我尚未接触这份参考答案</label><div class="study-actions">${button('已完成首答，继续','start',true)}${button('不录音，直接继续','start-without')}</div>`;
    if(phase==='inputs')body=`<p>粘贴实际说出的文字，或使用已有原回答；录音不会自动转写。</p>${text('training-answer','原回答文字',s.inputs.answer || ctx.item.original_answer || '')}${text('training-intent','中文补充意图（未实际说出的部分）',s.inputs.intent)}${text('training-feedback','外部反馈（待核对的建议）',s.inputs.feedback)}${button('确认文字，查看学习材料','inputs',true)}`;
    if(phase==='understand')body=`<h2>听懂参考，选这一轮要练的地方</h2><p>默认选有原话证据的错误，最多三处；其余句子仍完整保留，可自由增减。</p><details><summary>原回答与补充</summary><p>${esc(s.inputs.answer || ctx.item.original_answer || '尚未提供原回答文字')}</p><p>补充意图：${esc(s.inputs.intent)}</p><p>外部建议（未证实）：${esc(s.inputs.feedback)}</p></details>${materialNotice()}${rows.map((r,n)=>`<section class="training-row"><label><input type="checkbox" name="training-focus" value="${n}" ${r.original_error?'checked':''}> ${esc(r.zh)}</label><p>${esc(r.en)}</p><p class="study-muted">${r.original_error?'原话有证据的问题':'可选表达／待你确认的缺口'}</p>${r.original_error?`<p>原话：${esc(r.original_error.quote)}<br>${esc(r.original_error.issue)}<br>修正：${esc(r.original_error.correction)}</p>`:''}<div class="study-actions">${button('听这一句','audio',false,`data-index="${n}"`)}</div><details><summary>解释与用法</summary><p>${esc(r.explanation)}</p><p>${esc(r.usage)}</p></details></section>`).join('')}${rows.length?button('开始这一轮练习','understand',true):''}`;
    if(phase==='sentence'){
      const n=s.focus[s.index],r=rows[n],f=s.sentences[n] || {};
      if(!r){body='<p>材料已变化，请重新打开。</p>';}
      else body=`<p class="study-muted">本轮第 ${s.index+1} / ${s.focus.length} 句</p><h2 class="training-prompt">${esc(r.zh)}</h2><p>先自己说，再看参考；其他正确说法也可以。</p><div class="study-actions">${button('看参考','reveal')}${button('听这一句','audio',false,`data-index="${n}"`)}${button('默写巩固','write')}</div>${f.visible?`<section class="training-reference"><p>${esc(r.en)}</p><details><summary>解释与用法</summary><p>${esc(r.explanation)}</p><p>${esc(r.usage)}</p></details>${button('隐藏英文，再说一次','hide',true)}</section>`:''}${dictating?`${text('training-dictation','根据中文写出英文',f.draft || '')}<div class="study-actions">${button('检查与参考的差异','check')}${button('我用了另一种表达','alternative')}${button('短暂看答案','temporary-hint')}</div><p id="training-diff" role="status"></p>`:''}<label><input id="training-alternative" type="checkbox" ${f.alternative?'checked':''}> 我使用了另一种合适的表达（本人确认）</label><div class="study-actions">${button('独立说出了','sentence-independent',!f.hint && !f.visible,f.hint || f.visible?'disabled':'')}${button('借助帮助后说出了','sentence-needs_hint',!!f.hint && !f.visible,f.visible?'disabled':'')}${button('还没说出，稍后再练','sentence-unable',false,f.visible?'disabled':'')}</div><details><summary>可选：录下这一句回听</summary>${recorderPanel('recall')}</details>`;
    }
    if(phase==='outline')body=`<h2>用自己的话连成完整回答</h2>${promptList()}<details><summary>查看完整中文帮助</summary><p>${esc(m.complete_chinese)}</p></details><p>可以换一种说法。准备好后，撤掉提示回答原题。</p>${button('隐藏提示，独立回答','outline_done',true)}`;
    if(phase==='whole')body=`<p>只根据题目回答；忘记某个词时可以换一种说法。</p>${ctx.part===2?`<section><h2>Part 2 准备</h2><p>准备一分钟，可做笔记；回答最多两分钟。</p>${text('training-notes','准备笔记',s.notes)}${button('开始一分钟准备','prepare')}<p id="training-prep-time" role="timer"></p></section>`:''}${recorderPanel('recall')}<label><input type="checkbox" id="training-no-recording"> 不录音，我已完成口答（本人自评）</label><div class="study-actions">${button('需要内容提示','whole_hint')}</div>${s.whole_hint?promptList():''}${ctx.part===3?`<section><h2>完成主回答后再看追问</h2>${button('展示相关追问','followup')}<div id="training-followup" hidden><p>${esc(m.followup || '')}</p>${!m.followup?text('training-external-followup','粘贴一条相关追问'):''}<label><input id="training-followup-done" type="checkbox"> 我已经回答该追问</label></div></section>`:''}<fieldset class="training-checks"><legend>本人检查（不代表自动评分）</legend>${['切题并适当展开','之前的主要问题已解决','能够连贯说完，忘词可换说法','声音容易理解'].map((x,n)=>`<label><input type="checkbox" name="training-check" value="${n}"> ${x}</label>`).join('')}</fieldset><details><summary>选择需要补练的句子</summary>${rows.map((r,n)=>`<label class="training-choice"><input type="checkbox" name="training-weak" value="${n}"> ${esc(r.zh)}</label>`).join('')}</details><div class="study-actions">${button('独立完成','whole-independent',true,s.whole_hint?'disabled':'')}${button('借助提示','whole-needs_hint')}${button('仍有困难','whole-unable')}</div>`;
    if(phase==='summary')body=`<h2>${s.legacy_completed && !s.attempts.length?'历史已完成，待整题复验':s.status==='mastered'?'稳定掌握·本人复验':'本次完成，待复验'}</h2><p>${s.due_date?'下次复验：'+esc(s.due_date):'需要一次不看参考的整题复验。'}</p><p>这是本人复验记录，不是雅思分数或自动能力认证。</p><div class="study-actions">${button('只看原题，开始复验','review',true)}${button(s.paused?'恢复复习':'暂停复习','pause')}</div>${button('再选需要练习的句子','refocus')}<details><summary>完整材料与自由收听</summary>${rows.map((r,n)=>`<p>${esc(r.zh)}<br>${esc(r.en)} ${button('重听','audio',false,`data-index="${n}"`)}</p>`).join('')}</details>`;
    $app.innerHTML=`<div id="training-root" class="training-page"><header class="training-header"><a href="#/today">返回练习</a><span>Part ${ctx.part}</span>${MobileRuntime.native?MobileAppearance.button():''}</header><p class="study-muted">${esc(names[phase])} · ${esc(labels[s.status])}</p><h1>${esc(ctx.item.question || '雅思单题训练')}</h1>${ctx.changed?'<p role="status">材料版本已变化，旧记录保留，本版本需要重新验证。</p>':''}${s.paused?'<p>当前题目已暂停安排复习。</p>':''}<main>${body}</main><p id="training-status" role="status" aria-live="polite"></p><div class="study-actions">${s.undo?button('撤销上一步','undo'):''}<a class="study-button" href="#/play/${encodeURIComponent(tid)}/${encodeURIComponent(iid)}">自由收听</a></div><details><summary>录音与尝试记录</summary>${recordings()}${s.attempts.map(a=>`<p>${esc(a.created_at)} · ${esc(ratings[a.rating])} · ${a.no_recording?'无录音自评':'有录音'} · ${a.hint_used?'用过提示':'原题口答'}</p>`).join('')}<p>训练有效用时估算：${Math.round(s.elapsed_sec/60)} 分钟，仅保存在本机。</p></details></div>`;
    $app.scrollTop=0;document.querySelector('.main-content')?.scrollTo(0,0);
    root().querySelector('h1').setAttribute('tabindex','-1');if(keyboardMode)root().querySelector('h1').focus({preventScroll:true});
    if(pendingRecording?.savePath===path('/recordings'))root().querySelector('main').insertAdjacentHTML('afterbegin',`<section><p>有一份尚未关联的本机录音，内容已保留。</p>${button('恢复并保存录音','save-record',true)}</section>`);
    if(ctx.history?.length)root().insertAdjacentHTML('beforeend',`<details><summary>历史版本与导入记录</summary><p>历史成绩不作为当前版本掌握证明；个人交换文件不包含录音文件。</p>${ctx.history.map(h=>`<p>${esc(h.updated_at || '')} · ${(h.attempts || []).length} 次尝试 · ${Math.round((h.elapsed_sec || 0)/60)} 分钟</p>`).join('')}</details>`);
    if(MobileRuntime.native)MobileAppearance.refresh();
    root().querySelectorAll('[data-train]').forEach(b=>b.onclick=()=>handle(b).catch(e=>note(e.message)));
    root().querySelectorAll('audio').forEach(a=>a.onplay=()=>{$audio.pause();root().querySelectorAll('audio').forEach(b=>{if(b!==a)b.pause();});});
    if(phase==='understand' && !rows.some(r=>r.original_error))root().querySelectorAll('[name=training-focus]').forEach((x,n)=>x.checked=n<3);
    if(phase==='understand'){let selected=0;root().querySelectorAll('[name=training-focus]:checked').forEach(x=>{if(++selected>3)x.checked=false;});}
    const draft=document.getElementById('training-dictation');if(draft)draft.oninput=()=>{clearTimeout(draftTimer);draftTimer=setTimeout(()=>send('dictation',{index:s.focus[s.index],draft:draft.value,passed:false},false),450);};
    const notes=document.getElementById('training-notes');if(notes)notes.onchange=()=>send('activity',{seconds:0,notes:notes.value},false);
  }
  function materialNotice(){if(ctx.material_status==='ready')return button('听完整参考','full-audio');return `<p>${esc(ctx.reason || '学习材料尚未就绪；已有音频仍可自由播放。')}</p><div class="study-actions">${button('重新读取','refresh')}${button('准备学习材料','prepare-material')}</div>`;}
  async function play(n){
    if(ctx.state.phase==='sentence')if(!await send('reveal',{index:n}))return;
    let a=await api('GET',path('/audio/'+n));if(viewStale(token))return;
    if(a.mode==='estimated'){a={...a,start:0,end:null};note('单句边界不可靠，播放完整音频。');}
    if(playback)playback.pause();$audio.pause();playback=new Audio(audioUrl(a.url));
    playback.onloadedmetadata=()=>{playback.currentTime=a.start || 0;};
    playback.ontimeupdate=()=>{if(a.end && playback.currentTime>=a.end)playback.pause();};
    playback.onerror=()=>note('音频暂时无法播放，文字与训练记录仍保留，可重试。');await playback.play();
  }
  async function record(){
    if(recorder?.state==='recording')return;const localToken=token;
    try {stream=await navigator.mediaDevices.getUserMedia({audio:true});if(viewStale(localToken)){stream.getTracks().forEach(t=>t.stop());return;}
      const chunks=[],savePath=path('/recordings'),saveStage=recordingStage;recorder=new MediaRecorder(stream);started=Date.now();recId=null;blob=null;
      recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
      const localRecorder=recorder,localStream=stream,recordStart=started;
      recorder.onstop=async()=>{clearInterval(timer);localStream.getTracks().forEach(t=>t.stop());const data=chunks.length===1 && chunks[0].nativePath?chunks[0]:new Blob(chunks,{type:localRecorder.mimeType || 'audio/webm'});await saveRecording(localToken,{data,savePath,saveStage,duration:Math.max(.1,(Date.now()-recordStart)/1000)});};
      recorder.start();root().querySelector('[data-train=stop]').disabled=false;root().querySelector('[data-train=record]').disabled=true;
      timer=setInterval(()=>{const seconds=Math.floor((Date.now()-started)/1000),el=document.getElementById('training-record-time');if(el)el.textContent=seconds+' 秒';if(ctx.part===2 && recordingStage==='recall' && seconds>=120 && recorder.state==='recording')recorder.stop();},250);
    }catch(e){note('无法录音：'+e.message+'。可以选择无录音继续。');}
  }
  let pendingRecording=null;
  async function saveRecording(localToken=token,record=null){
    record=record || pendingRecording;if(!record?.data?.size)return;pendingRecording=record;blob=record.data;
    record.upload_key=record.upload_key || crypto.randomUUID();
    try{await TrainingBaseline.keepRecording(record);const response=await fetch(record.savePath+`?stage=${record.saveStage}&duration_sec=${record.duration}&upload_key=${record.upload_key}`,{method:'POST',headers:{'Content-Type':record.data.type || 'audio/webm'},body:record.data});
      const result=await response.json();if(!response.ok)throw new Error(result.detail || '录音未保存');
      await TrainingBaseline.keepRecording(null,record.savePath);pendingRecording=null;if(viewStale(localToken))return;recId=result.id;blob=null;ctx=await api('GET',path('/training'));render();note('录音已保存，可以回听或重录。');
    }catch(e){if(!viewStale(localToken)){note('录音保存失败：'+e.message+'。请保持本页，点击重试保存。');root()?.querySelector('[data-train=save-record]')?.removeAttribute('hidden');}}
  }
  async function handle(b){
    if(busy)return;const a=b.dataset.train,s=ctx.state,n=s.focus[s.index];
    if(recorder?.state==='recording' && a!=='stop' && a!=='followup'){
      note('请先停止并保存当前录音，再继续。');return;
    }
    const draft=document.getElementById('training-dictation');
    if(draft && a!=='check' && draft.value!==(s.sentences[n]?.draft || '')){
      clearTimeout(draftTimer);if(!await send('dictation',{index:n,draft:draft.value,passed:false},false))return;
    }
    if(a==='record')return record();if(a==='stop'){recorder?.stop();return;}if(a==='save-record')return saveRecording();
    if(a==='audio')return play(+b.dataset.index);
    if(a==='full-audio'){if(playback)playback.pause();$audio.pause();playback=new Audio(audioUrl(`/api/topics/${encodeURIComponent(tid)}/items/${encodeURIComponent(iid)}/audio/podcast`));return playback.play();}
    if(a==='refresh'){ctx=await api('GET',path('/training'));return render();}
    if(a==='prepare-material'){await api('POST',path('/prepare'),{});note('已请求准备材料，请稍后重新读取。');return;}
    if(a==='start' || a==='start-without'){if(a==='start' && !recId){note('请先录音，或明确选择不录音继续。');return;}return send('start',{recording_id:a==='start'?recId:null,unexposed:document.getElementById('training-unexposed').checked});}
    if(a==='inputs')return send('inputs',{answer:document.getElementById('training-answer').value,intent:document.getElementById('training-intent').value,feedback:document.getElementById('training-feedback').value});
    if(a==='understand')return send(a,{focus:[...root().querySelectorAll('[name=training-focus]:checked')].map(x=>+x.value)});
    if(a==='reveal' || a==='hide')return send(a,{index:n});
    if(a==='temporary-hint'){await send('reveal',{index:n});hintTimer=setTimeout(()=>send('hide',{index:n}),Number(localStorage.getItem('study-hint-seconds') || 5)*1000);return;}
    if(a==='write'){dictating=true;return render();}
    if(a==='alternative'){document.getElementById('training-alternative').checked=true;note('另一种表达由本人确认；仍需隐藏英文后口答。');return;}
    if(a==='check'){
      const value=document.getElementById('training-dictation').value,expected=ctx.material.sentences[n].en;
      const norm=x=>x.toLowerCase().replace(/[^a-z0-9’']+/g,' ').trim(),same=norm(value)===norm(expected);
      await send('dictation',{index:n,draft:value,passed:same},false);
      document.getElementById('training-diff').textContent=same?'与参考一致。请隐藏英文，再口答一次。':'与参考不同；不代表表达错误。可查看参考核对词形和搭配，也可确认另一种表达。';return;
    }
    if(a.startsWith('sentence-')){const ok=await send('sentence',{index:n,rating:a.slice(9),alternative:document.getElementById('training-alternative')?.checked});if(ok){dictating=false;render();}return;}
    if(a==='prepare'){clearInterval(timer);let remaining=60;const out=document.getElementById('training-prep-time');out.textContent='准备：60 秒';timer=setInterval(()=>{remaining--;out.textContent=remaining>0?'准备：'+remaining+' 秒':'准备结束，可以开始回答。';if(!remaining)clearInterval(timer);},1000);return;}
    if(a==='followup'){document.getElementById('training-followup').hidden=false;followup=true;return;}
    if(a.startsWith('whole-')){
      const rating=a.slice(6);if(rating==='independent' && root().querySelectorAll('[name=training-check]:checked').length!==4){note('请先完成四项本人检查；有困难可选择对应结果。');return;}
      noRecording=document.getElementById('training-no-recording').checked;
      const followupCompleted=followup && document.getElementById('training-followup-done')?.checked && (ctx.material.followup || document.getElementById('training-external-followup')?.value.trim());
      const ok=await send('whole',{rating,recording_id:noRecording?null:recId,no_recording:noRecording,followup_completed:!!followupCompleted,weak_indices:[...root().querySelectorAll('[name=training-weak]:checked')].map(x=>+x.value)});
      if(ok){recId=null;followup=false;}return;
    }
    if(a==='pause')return send(a,{paused:!s.paused});
    if(a==='refocus'){await send('refocus');return;}
    if(a==='outline_done' || a==='review'){recId=null;followup=false;}
    return send(a);
  }
  async function today(currentToken){reset();ctx=null;token=currentToken;
    $app.innerHTML='<div class="training-page"><p role="status">正在读取练习…</p></div>';
    try {const data=await api('GET','/api/study/training');if(viewStale(token))return;
      const active=data.items.filter(x=>x.state.status==='training' && !x.state.paused),due=data.items.filter(x=>!x.state.paused && (!x.state.due_date || x.state.due_date<=data.today) && x.state.status!=='training');
      const row=(x,primary=false)=>`<a class="training-task ${primary?'training-primary':''}" href="${link(x.topic_id,x.item_id)}"><span class="study-muted">Part ${x.part} · ${esc(labels[x.state.status])}</span><strong>${esc(x.question)}</strong><span>${esc(names[x.state.phase])}${x.state.due_date?' · '+esc(x.state.due_date):''}</span></a>`;
      $app.innerHTML=`<div class="training-page"><header class="training-header"><h1>今日练习</h1>${MobileRuntime.native?MobileAppearance.button():''}</header><p>把一道题练到能够独立回答。</p>${active.length?`<section><h2>继续训练</h2>${active.map((x,n)=>row(x,n===0)).join('')}</section>`:''}${due.length?`<section><h2>到期整题复验</h2>${due.map(x=>row(x,!active.length)).join('')}</section>`:''}<section><h2>开始一道新题</h2><p>先试答，再针对卡住的地方练习。</p><a class="study-button ${!active.length && !due.length?'primary':''}" href="#/bank">去题库选题</a></section><details><summary>全部题目与复习安排</summary>${data.items.map(x=>row(x)).join('') || '<p>还没有训练记录。</p>'}</details><details><summary>句子轻练与聊天口答</summary><p>自由查看与收听不计正式完成。</p><a class="study-button" href="${MobileRuntime.native?'#/light-practice':'#/sentence-today'}">进入句子练习</a></details></div>`;
      if(MobileRuntime.native)MobileAppearance.refresh();
    }catch(e){if(!viewStale(token))$app.innerHTML=`<div class="training-page"><h1>练习读取失败</h1><p>${esc(e.message)}</p><a href="#/bank">去题库</a></div>`;}
  }
  return {view,today,reset,link};
})();
