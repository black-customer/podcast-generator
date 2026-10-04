/* Android 交互与桥接；桌面保留现有服务调用和媒体元素。 */
"use strict";

const MobileRuntime = (() => {
  const native = !!window.Capacitor?.isNativePlatform?.();
  const plugin = native ? (window.Capacitor.Plugins.Learning || window.Capacitor.registerPlugin("Learning")) : null;
  let state = null, recorder = null;
  const fileUrl = path => path ? window.Capacitor.convertFileSrc(path) : "";
  const unwrap = async promise => (await promise).value;
  async function snapshot() { const incoming=await unwrap(plugin.request({method:"GET",url:"/api/mobile/snapshot"}));
    if(!state || (incoming.revision || 0)>=(state.revision || 0))state=incoming;return state; }
  async function request(method, url, body) {
    const result = await unwrap(plugin.request({method,url,body:body || {}}));
    if (method !== "GET" || /\/jobs\/[^/]+$/.test(url)) await snapshot();
    return result;
  }
  function pathFor(url) {
    if (!state) return "";
    const parts = url.split("?")[0].split("/").map(decodeURIComponent);
    if (parts[2] === "topics") {
      const item = state.topics[parts[3]]?.items[parts[5]];
      if (parts[3] === "conversation") return state.conversations[parts[5]]?.audio || "";
      if (parts[6] === "audio") return parts[7]==='podcast' || parts[7]==='default' ? item?.audio?.podcast || item?.audio?.default || '' : item?.audio?.[parts[7]] || "";
      if (parts[7] === "recordings") return item?.progress?.recordings.find(r=>r.id===parts[8])?.path || "";
    }
    return "";
  }
  function mediaUrl(url) { if (!native) return null; return fileUrl(pathFor(url)); }
  async function toBase64(blob) {
    const bytes = new Uint8Array(await blob.arrayBuffer()); let text="";
    for(let i=0;i<bytes.length;i+=32768)text+=String.fromCharCode(...bytes.subarray(i,i+32768));
    return btoa(text);
  }
  async function migratePack(manual=false) {
    if (!PackState.active) return;
    if (!manual && state?.migration?.legacy_pack) { packUnload(); return; }
    const items=[];
    for(const t of PackState.topics.values()) for(const i of t.items.values()) {
      const audioData={};for(const [track,url] of Object.entries(i.audioUrls || {}))audioData[track]=await toBase64(await (await fetch(url)).blob());
      items.push({id:i.id,topic_id:t.id,title:i.title,texts:i.texts,meta:i.meta || {},material:i.material,
        timelines:i.timelines || {},audioData});
    }
    await request("POST","/api/mobile/migrate",{manifest:PackState.manifest,items,bank:PackState.bank});
    packUnload();
  }
  class NativeRecorder {
    static isTypeSupported(type) { return type === "audio/mp4"; }
    constructor() { this.state="inactive"; this.mimeType="audio/mp4"; recorder=this; }
    start() { this.state="recording"; }
    async finish(meta) {
      this.state="inactive";
      const {base64}=await plugin.readRecording({path:meta.path});
      const blob=new Blob([Uint8Array.from(atob(base64),c=>c.charCodeAt(0))],{type:"audio/mp4"});
      blob.nativePath=meta.path;this.ondataavailable?.({data:blob});this.onstop?.();
      if(meta.interrupted)toast("录音因切换应用而停止，已录内容已保留。");
    }
    stop() { if(this.state!=="recording")return;this.state="inactive";plugin.recordStop().then(meta=>this.finish(meta)).catch(e=>{
      toast(e.message);const root=document.querySelector('.study-recorder') || document.getElementById('oral-recorder');
      if(root){root.querySelectorAll('[data-rec=start],[data-oral=record-start]').forEach(b=>b.disabled=false);ExperienceUI.recordingControls(root,'ready');}
    }); }
  }
  async function init() {
    if(!native)return;
    document.body.classList.add("mobile-learning");
    const viewport=()=>document.documentElement.style.setProperty('--mobile-vh',`${visualViewport?.height || innerHeight}px`);
    viewport();visualViewport?.addEventListener('resize',viewport);
    await snapshot();await migratePack();
    if(navigator.mediaDevices) navigator.mediaDevices.getUserMedia=async()=>{
      const parts=location.hash.slice(2).split('/').map(decodeURIComponent);let source={};
      if(parts[0]==='learn')source={topic_id:parts[1],item_id:parts[2],stage:state.topics[parts[1]]?.items[parts[2]]?.progress?.stage || 'before'};
      if(parts[0]==='oral-review'){const s=state.sessions[parts[1]];source={session_id:parts[1],card_id:s?.cards[s.current_index],stage:'oral_review'};}
      await plugin.recordStart({source});return {getTracks:()=>[{stop(){}}]};
    };
    window.MediaRecorder=NativeRecorder;
    await plugin.addListener("recordingInterrupted",meta=>recorder?.finish(meta));
    const originalFetch=window.fetch.bind(window);
    window.fetch=async(input,opts={})=>{
      const url=String(input);
      if(url.startsWith("/api/") && /\/recordings?\b/.test(url)) {
        if(opts.method==="POST" && opts.body?.nativePath) {
          try {
            const q=new URL(url,location.origin).searchParams;
            const session=url.match(/\/review-sessions\/([^/]+)/);
            const result=await unwrap(plugin.attachRecording({path:opts.body.nativePath,url:url.split("?")[0],
              body:{stage:q.get("stage"),duration_sec:Number(q.get("duration_sec")),session_id:session?.[1] || ""}}));
            await snapshot();return new Response(JSON.stringify(result),{headers:{"Content-Type":"application/json"}});
          }catch(e){return new Response(JSON.stringify({detail:e.message}),{status:400});}
        }
        const file=pathFor(url);if(file)return originalFetch(fileUrl(file),opts);
      }
      return originalFetch(input,opts);
    };
    const shared=await request("GET","/api/mobile/shared");
    if(shared.text){sessionStorage.setItem("chat-import-draft",shared.text);location.hash="#/chat-import";}
    document.addEventListener("visibilitychange",async()=>{if(!document.hidden){const shared=await request("GET","/api/mobile/shared");
      if(shared.incoming && shared.text){sessionStorage.setItem("chat-import-draft",shared.text);location.hash="#/chat-import";}}});
    document.addEventListener('click',event=>{const a=event.target.closest('a[download]');
      if(a?.href.includes('/_capacitor_file_')){event.preventDefault();const marker='/_capacitor_file_';const path=decodeURIComponent(a.href.slice(a.href.indexOf(marker)+marker.length));
        plugin.exportDocument({path,name:path.split('/').pop(),mime:path.endsWith('.mp3')?'audio/mpeg':'audio/mp4'}).catch(e=>toast(e.message));}});
  }
  function navigation(hash=location.hash) {
    if(!native)return;
    const nav=document.querySelector(".sidebar-nav") || document.querySelector(".sidebar nav");
    if(nav)nav.innerHTML=[['today','今日'],['materials','材料'],['bank','题库'],['my','我的']].map(([route,text])=>
      `<a class="nav-item" href="#/${route}" data-filter="${route}"><span>${text}</span></a>`).join("");
    const path=hash.replace(/^#\//,'').split(/[/?]/)[0];
    const owner=['my','settings','mobile-history','study-history','import'].includes(path)?'my'
      : ['bank','practice','setup'].includes(path)?'bank'
      : ['today','oral-review','chat-import',''].includes(path)?'today':'materials';
    nav?.querySelectorAll('.nav-item').forEach(a=>{const selected=a.dataset.filter===owner;
      a.classList.toggle('active',selected);if(selected)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  }
  return {native,plugin,init,request,snapshot,navigation,mediaUrl,fileUrl,pathFor,migratePack,get state(){return state;}};
})();

class NativePlayer extends EventTarget {
  constructor() {
    super();this._src="";this._position=0;this._duration=0;this._paused=true;this._rate=1;this._volume=1;this.readyState=0;
    MobileRuntime.plugin.addListener("mediaState",data=>{
      if(data.path && this._path && data.path!==this._path)return;
      const old=this._paused;this._position=data.position;this._paused=!data.playing;
      if(data.duration>0 && data.duration!==this._duration){this._duration=data.duration;this.readyState=1;this.emit("loadedmetadata");this.emit("durationchange");}
      if(old!==this._paused){this.emit(this._paused?"pause":"play");if(!this._paused)this.emit('playing');}this.emit("timeupdate");
      if(data.ended && !this._ended){this._ended=true;this.emit("ended");}
    });
  }
  emit(type){this[`on${type}`]?.(new Event(type));this.dispatchEvent(new Event(type));}
  get src(){return this._src;}set src(url){this._src=url;this._ended=false;this.readyState=0;this._duration=0;this._position=0;
    const marker="/_capacitor_file_";const path=url.includes(marker)?decodeURIComponent(url.slice(url.indexOf(marker)+marker.length).split('?')[0]):url;
    this._path=path;
    const saved=MobileRuntime.state?.media_positions?.[path];const position=saved && !saved.completed && saved.fingerprint===this.fingerprint?saved.position:0;
    this._load=MobileRuntime.plugin.media({action:"load",path,position,fingerprint:this.fingerprint || '',title:this.title || document.getElementById("gp-title")?.textContent || "英语学习"}).catch(e=>{this.error={code:4,message:e.message};this.emit("error");return false;});}
  get currentTime(){return this._position;}set currentTime(n){this._position=n;MobileRuntime.plugin.media({action:"seek",position:n});}
  get duration(){return this._duration;}get paused(){return this._paused;}get ended(){return this._ended;}
  get playbackRate(){return this._rate;}set playbackRate(n){this._rate=n;MobileRuntime.plugin.media({action:"speed",speed:n});}
  get volume(){return this._volume;}set volume(n){this._volume=n;MobileRuntime.plugin.media({action:"volume",volume:n});}
  async play(){if(await this._load===false)throw new Error(this.error?.message || '音频加载失败');await MobileRuntime.plugin.media({action:"play"});}
  pause(){MobileRuntime.plugin.media({action:"pause"});}
  load(){}removeAttribute(name){if(name==='src')this.pause();}
}

const MobileUI = (() => {
  let timer=null;
  const link = id => `#/conversation/${encodeURIComponent(id)}`;
  const jobNotice = job => !job?'':`${(job.errors || []).map(e=>`<p>${esc(e.message)}</p>`).join('')}${job.inflight?'<p>上次请求是否完成无法确认；继续处理可能再次计费。已保存的有效阶段会复用。</p>':''}`;
  function layout(title,html){$app.innerHTML=`<div class="mobile-page"><h1>${esc(title)}</h1>${html}</div>`;$app.scrollTop=0;}
  function reset(){clearTimeout(timer);timer=null;}
  async function today(token){const data=await api("GET","/api/study/today");if(viewStale(token))return;
    layout("今天练什么",`<section class="mobile-section"><h2>继续积累你的表达</h2><a class="study-button primary" href="#/chat-import">整理一次英语聊天</a></section>
      <section class="mobile-section"><h2>到期口答</h2><p>${data.due_count?`${data.due_count} 个学习点等待练习。每轮最多 10 个。`:"今天没有到期内容。可以听听已有对话，或开始一道新题。"}</p>
      ${data.active_session_id?`<a class="study-button primary" href="#/oral-review/${esc(data.active_session_id)}">继续本轮口答</a>`:
        data.due_count?'<button class="study-button primary" id="mobile-review-start">开始口答</button>':''}</section>
      <section class="mobile-section"><h2>继续学习</h2>${data.continue_learning.map(r=>`<a class="mobile-row" href="#/learn/${encodeURIComponent(r.topic_id)}/${encodeURIComponent(r.item_id)}">${esc(r.question)}</a>`).join('') || '<p>暂无未完成的雅思学习。</p>'}
      <a class="study-button" href="#/bank">从一道题开始</a></section>`);
    document.getElementById('mobile-review-start')?.addEventListener('click',async()=>{try{const s=await api('POST','/api/study/review-sessions',{});location.hash=`#/oral-review/${s.id}`;}catch(e){toast(e.message);}});
  }
  async function materials(token){const [chat,topics]=await Promise.all([api('GET','/api/conversations'),api('GET','/api/topics')]);if(viewStale(token))return;
    layout('我的材料',`<input id="mobile-search" type="search" aria-label="搜索材料" placeholder="搜索聊天、原话或回答">
      <div class="mobile-filters" role="group" aria-label="材料类型"><button data-kind="all" aria-pressed="true">全部</button><button data-kind="conversation">聊天</button><button data-kind="ielts">雅思</button></div>
      <label for="mobile-source">来源</label><select id="mobile-source"><option value="all">全部来源</option><option value="chatgpt">ChatGPT</option><option value="doubao">豆包</option><option value="file">文字或文件</option><option value="ielts">雅思回答</option></select><div id="mobile-material-results"></div>`);
    const rows=[...chat.map(c=>({kind:'conversation',provider:c.provider,title:c.title,href:link(c.id),status:c.has_audio?'可收听':c.status==='imported'?'等待整理':'等待音频',text:c.title+' '+JSON.stringify(MobileRuntime.state?.conversations[c.id] || {})})),
      ...topics.flatMap(t=>Object.values(MobileRuntime.state?.topics[t.id]?.items || {}).map(i=>({kind:'ielts',provider:'ielts',title:i.title,href:`#/play/${encodeURIComponent(t.id)}/${encodeURIComponent(i.id)}`,status:i.audio?.podcast?'可收听':'等待生成',text:Object.values(i.texts).join(' ')})))];
    let kind='all';const render=()=>{const needle=document.getElementById('mobile-search').value.toLowerCase(),provider=document.getElementById('mobile-source').value;document.getElementById('mobile-material-results').innerHTML=rows.filter(r=>(kind==='all'||r.kind===kind)&&(provider==='all'||r.provider===provider)&&r.text.toLowerCase().includes(needle)).map(r=>
      `<a class="mobile-row" href="${esc(r.href)}"><strong>${esc(r.title)}</strong><span>${r.kind==='conversation'?'聊天':'雅思'} · ${esc(r.status)}</span></a>`).join('') || '<p>没有匹配材料。</p>';};
    document.getElementById('mobile-search').addEventListener('input',render);document.getElementById('mobile-source').addEventListener('change',render);$app.querySelectorAll('[data-kind]').forEach(b=>b.addEventListener('click',()=>{kind=b.dataset.kind;$app.querySelectorAll('[data-kind]').forEach(x=>x.setAttribute('aria-pressed',x===b));render();}));render();
  }
  function importView(){const saved=sessionStorage.getItem('chat-import-draft') || '';
    layout('整理一次英语聊天',`<p>在 ChatGPT 或豆包打开聊天，点击分享并复制链接，再粘贴到这里。也可以导入导出的文字文件。</p>
      <label for="chat-import-input">分享链接或聊天文字</label><textarea id="chat-import-input" rows="8" placeholder="https://… 或 User: / Assistant: 标记的记录">${esc(saved)}</textarea>
      <div class="study-actions"><button class="study-button primary" id="chat-read">读取记录</button><label class="study-button" for="chat-file">选择文字文件</label>
      <input id="chat-file" type="file" accept=".txt,.md,.json,text/plain,application/json" class="sr-only"></div><p id="chat-import-error" role="status"></p>
      <details><summary>分享链接打不开怎么办？</summary><p>先确认分享范围包含需要学习的对话。无法读取时，可从网页版使用本地导出扩展，导出 Markdown／JSON 后在这里选择文件；也可粘贴保留双方角色的原文。</p>
      <p>ChatGPT：User / Assistant；豆包：用户 / 豆包。仅有总结无法还原你的原话证据。</p></details>`);
    const input=document.getElementById('chat-import-input');let saveTimer;
    const saveDraft=()=>{sessionStorage.setItem('chat-import-draft',input.value);clearTimeout(saveTimer);saveTimer=setTimeout(()=>api('POST','/api/mobile/import-draft',{text:input.value}).catch(e=>toast(`导入草稿保存失败：${e.message}`)),400);};
    input.addEventListener('input',saveDraft);
    document.getElementById('chat-file').addEventListener('change',async e=>{const f=e.target.files[0];if(!f)return;if(f.size>4*1024*1024){toast('文件过大，请分次导入');return;}input.value=await f.text();saveDraft();});
    document.getElementById('chat-read').addEventListener('click',async e=>{const button=e.currentTarget;button.disabled=true;try{
      clearTimeout(saveTimer);
      const raw=input.value.trim(),url=raw.match(/https:\/\/(?:chatgpt\.com\/share\/|www\.doubao\.com\/thread\/)[^\s]+/);
      const c=url?await api('POST','/api/conversations/import-link',{url:url[0]}):await api('POST','/api/conversations/import',JSON.parseOrText(raw));
      sessionStorage.removeItem('chat-import-draft');location.hash=link(c.id);
    }catch(e){document.getElementById('chat-import-error').textContent=`读取失败：${e.message}。内容仍保留，可以改用文字文件。`;button.disabled=false;}});
  }
  async function conversation(cid,token){const c=await api('GET',`/api/conversations/${encodeURIComponent(cid)}`);if(viewStale(token))return;
    const job=MobileRuntime.state?.jobs[cid];
    layout(c.title,`<a class="back-link" href="#/materials">返回材料</a><p>${c.messages.length} 条文本发言 · ${esc(c.provider)} · ${c.scope==='shared_snapshot'?'分享时的内容快照':'本次提供的文字'}</p>
      ${(c.warnings || []).map(w=>`<p>${esc(w)}</p>`).join('')}
      ${jobNotice(job)}
      ${c.audio || c.notes.length?`<div class="study-actions">${c.audio?'<button class="study-button primary" id="chat-listen">收听对话</button>':''}<button class="study-button" id="chat-practice">练习本次重点</button></div>`:
        `<p>${job?.state==='running' || job?.state==='queued'?'正在处理；可以切换应用，完成阶段会保留。':'原始记录已保存，整理后可收听并复习。'}</p>`}
      ${!c.audio && !['running','queued'].includes(job?.state)?`<section class="mobile-section"><p>将通过你配置的 StepFun 文本和语音服务处理 ${c.messages.length} 条发言。会消耗相应 API 额度，费用以服务商实际计费为准。</p><button id="chat-generate" class="study-button primary">${job?'继续处理':'开始整理'}</button></section>`:''}
      <details><summary>核对原始记录与首尾</summary>${c.messages.map(m=>`<div class="mobile-source"><strong>${m.role==='user'?'我':'对话伙伴'}</strong><p>${esc(m.text)}</p></div>`).join('')}</details>
      ${c.dialogue.length?`<details open><summary>自然对话</summary>${c.dialogue.map(l=>`<p><strong>${l.speaker==='A'?'伙伴':'我'}：</strong>${esc(l.en)}<span class="mobile-translation">${esc(l.zh)}</span></p>`).join('')}</details>`:''}
      ${c.notes.length?`<section class="mobile-section"><h2>这次学到的表达</h2>${c.notes.map((n,index)=>`<details><summary>${esc(n.target)}</summary><p>${esc(n.reference_en)}</p><p>${esc(n.explanation)}</p>
        <p>你的原话：${n.sources.map(r=>esc(r.quote)).join(' / ')}</p>${n.kind==='recommendation' || n.kind==='expression_refinement'?`<button data-enroll="${index}">加入口答复习</button>`:'<p>已加入待复习队列，首次安排在次日。</p>'}</details>`).join('')}</section>`:''}`);
    document.getElementById('chat-generate')?.addEventListener('click',async e=>{e.currentTarget.disabled=true;try{await api('POST',`/api/conversations/${cid}/generate`,{});conversation(cid,token);}catch(e){toast(e.message);document.getElementById('chat-generate').disabled=false;}});
    document.getElementById('chat-listen')?.addEventListener('click',()=>{document.getElementById('gp-title').textContent=c.title;$audio.title=c.title;$audio.fingerprint=c.audio_fingerprint || '';$globalPlayer.style.display='flex';
      const url=MobileRuntime.fileUrl(c.audio);if($audio.src!==url || $audio.ended)$audio.src=url;$audio.play().catch(e=>toast(e.message));});
    document.getElementById('chat-practice')?.addEventListener('click',async e=>{const button=e.currentTarget;button.disabled=true;try{
      const cards=Object.values(MobileRuntime.state.cards).filter(card=>card.kind==='conversation' && card.sources.includes(cid) && !card.paused && !card.superseded).slice(0,10);
      if(!cards.length){toast('这次没有自动加入的重点，可以从笔记里选择表达加入。');return;}
      const session=await api('POST','/api/study/review-sessions',{card_ids:cards.map(card=>card.id)});location.hash=`#/oral-review/${session.id}`;
    }catch(e){toast(e.message);}finally{if(button.isConnected)button.disabled=false;}});
    $app.querySelectorAll('[data-enroll]').forEach(b=>b.addEventListener('click',async()=>{await api('POST',`/api/conversations/${cid}/notes/${b.dataset.enroll}/enroll`,{});b.disabled=true;b.textContent='已加入';}));
    if(job && ['queued','running'].includes(job.state))timer=setTimeout(async()=>{await api('GET',`/api/jobs/${cid}`);if(!viewStale(token))conversation(cid,token);},1500);
  }
  async function download(name,data){if(MobileRuntime.native){await MobileRuntime.plugin.exportDocument({name,data:JSON.stringify(data,null,2),mime:'application/json'});return;}
    const u=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),2000);}
  async function my(token){const [settings,jobs,voices]=await Promise.all([api('GET','/api/settings'),api('GET','/api/jobs'),api('GET','/api/voices')]);if(viewStale(token))return;
    const options=selected=>voices.filter(v=>v.provider==='stepfun').map(v=>`<option value="${esc(v.voice_id)}" ${v.voice_id===selected?'selected':''}>${esc(v.name)} · ${v.gender==='female'?'女声':'男声'}</option>`).join('');
    layout('我的',`<section class="mobile-section"><h2>处理服务</h2><p>${settings.stepfun_api_key_configured?'已配置 StepFun Key':'请先配置 StepFun Key；密钥只保存在这台手机。'}</p>
      <label for="mobile-key">StepFun API Key</label><input id="mobile-key" type="password" autocomplete="off" placeholder="留空保留现有密钥">
      <label for="mobile-model">文本模型</label><input id="mobile-model" value="${esc(settings.stepfun_text_model || 'step-5-preview')}">
      <label for="mobile-base">文本接口地址</label><input id="mobile-base" type="url" value="${esc(settings.stepfun_text_base_url || '')}" placeholder="留空使用标准计费入口">
      <p>标准入口按量计费。订阅用户可填写自己已获授权的专用入口；失败时不会自动切换。</p>
      <label for="mobile-voice-a">对话伙伴的声音</label><select id="mobile-voice-a">${options(settings.question_voice_id || 'lively-girl')}</select><button data-preview-role="a">生成试听（使用语音额度）</button>
      <label for="mobile-voice-b">我的自然表达的声音</label><select id="mobile-voice-b">${options(settings.answer_voice_id || 'vibrant-youth')}</select><button data-preview-role="b">生成试听（使用语音额度）</button>
      <audio id="mobile-preview" controls hidden></audio>
      <label><input type="checkbox" id="mobile-reminder" ${settings.reminder_enabled?'checked':''}>每天晚间提醒到期复习（约 20:00，默认关闭）</label>
      <button id="mobile-save-settings" class="study-button primary">保存配置</button><p id="mobile-settings-status" role="status"></p></section>
      <section class="mobile-section"><h2>任务</h2>${jobs.map(j=>`<div class="mobile-row"><span>${esc(j.kind==='conversation'?'聊天整理':'雅思生成')} · ${esc(j.state)}</span>
        ${jobNotice(j)}
        ${['interrupted','error','cancelled'].includes(j.state)?`<button data-resume="${esc(j.id)}">继续任务</button>`:''}${['queued','running'].includes(j.state)?`<button data-cancel="${esc(j.id)}">取消任务</button>`:''}
        ${j.usage?`<small>文本实际用量：${j.usage.reduce((n,u)=>n+(u.total_tokens || 0),0)} tokens</small>`:''}</div>`).join('') || '<p>暂无处理任务。</p>'}</section>
      <section class="mobile-section"><h2>学习记录与文件</h2><a class="study-button" href="#/mobile-history">查看学习记录</a><button id="mobile-export" class="study-button">导出个人任务交换文件</button>
      <label class="study-button" for="mobile-exchange-file">导入处理结果</label><input class="sr-only" id="mobile-exchange-file" type="file" accept=".json,application/json">
      <a class="study-button" href="#/import">导入电脑语料包</a><p>个人交换文件包含原始记录，不包含 API Key。请只交给你自己的电脑 Agent。</p></section>`);
    const storage=document.createElement('section');storage.className='mobile-section';storage.innerHTML='<h2>本机存储</h2><p id="mobile-storage-status">正在统计…</p><button id="mobile-clear-temp" class="study-button">清理中断任务的临时音频</button><p>原始记录、成品音频和录音保留。</p>';
    $app.querySelector('.mobile-page').append(storage);api('GET','/api/mobile/storage').then(s=>{if(storage.isConnected)document.getElementById('mobile-storage-status').textContent=`音频文件 ${s.media_files} 个，约 ${(s.media_bytes/1048576).toFixed(1)} MB。`;}).catch(e=>{if(storage.isConnected)document.getElementById('mobile-storage-status').textContent=e.message;});
    document.getElementById('mobile-clear-temp').addEventListener('click',async()=>{try{const s=await api('POST','/api/mobile/storage/clear-temp',{});toast(`已清理 ${(s.cleared_bytes/1048576).toFixed(1)} MB 临时音频。`);}catch(e){toast(e.message);}});
    const pending=Object.values(MobileRuntime.state.recording_inbox || {});
    if(pending.length){const section=document.createElement('section');section.className='mobile-section';section.innerHTML=`<h2>尚未保存到练习的录音</h2>${pending.map((r,index)=>
      `<div class="mobile-row"><p>${Number(r.duration_sec).toFixed(1)} 秒 · 文件已保留</p><audio controls preload="none" src="${esc(MobileRuntime.fileUrl(r.path))}"></audio>
      <button data-recover-record="${index}">保存到原练习</button><button data-export-record="${index}">导出录音</button></div>`).join('')}`;
      $app.querySelector('.mobile-page').append(section);
      section.querySelectorAll('[data-export-record]').forEach(b=>b.addEventListener('click',()=>{const r=pending[+b.dataset.exportRecord];MobileRuntime.plugin.exportDocument({path:r.path,name:'my-answer.m4a',mime:'audio/mp4'}).catch(e=>toast(e.message));}));
      section.querySelectorAll('[data-recover-record]').forEach(b=>b.addEventListener('click',async()=>{try{const r=pending[+b.dataset.recoverRecord],s=r.source || {};
        if(!s.session_id && !(s.topic_id && s.item_id))throw new Error('缺少原练习信息，可以导出录音保存。');
        await MobileRuntime.plugin.attachRecording({path:r.path,url:s.topic_id?`/api/topics/${encodeURIComponent(s.topic_id)}/items/${encodeURIComponent(s.item_id)}/study/recordings`:'',
          body:{stage:s.stage,duration_sec:r.duration_sec,session_id:s.session_id || ''}});await MobileRuntime.snapshot();my(token);
      }catch(e){toast(e.message);}}));
    }
    document.getElementById('mobile-save-settings').addEventListener('click',async e=>{const button=e.currentTarget;button.disabled=true;try{const payload={stepfun_text_model:document.getElementById('mobile-model').value.trim(),stepfun_text_base_url:document.getElementById('mobile-base').value.trim(),
      question_voice_id:document.getElementById('mobile-voice-a').value.trim(),answer_voice_id:document.getElementById('mobile-voice-b').value.trim(),reminder_enabled:document.getElementById('mobile-reminder').checked};
      if(payload.reminder_enabled)await MobileRuntime.plugin.reminderPermission();const key=document.getElementById('mobile-key');if(key.value.trim())payload.stepfun_api_key=key.value.trim();
      await api('PUT','/api/settings',payload);key.value='';document.getElementById('mobile-settings-status').textContent='配置已保存。';}catch(e){document.getElementById('mobile-settings-status').textContent=e.message;}finally{button.disabled=false;}});
    $app.querySelectorAll('[data-preview-role]').forEach(b=>b.addEventListener('click',async()=>{b.disabled=true;try{
      const result=await api('POST','/api/mobile/voice-preview',{voice:document.getElementById(`mobile-voice-${b.dataset.previewRole}`).value});
      const player=document.getElementById('mobile-preview');player.src=MobileRuntime.fileUrl(result.path);player.hidden=false;await player.play();
    }catch(e){toast(e.message);}finally{b.disabled=false;}}));
    $app.querySelectorAll('[data-resume]').forEach(b=>b.addEventListener('click',async()=>{b.disabled=true;try{await api('POST',`/api/jobs/${b.dataset.resume}/resume`,{});my(token);}catch(e){toast(e.message);b.disabled=false;}}));
    $app.querySelectorAll('[data-cancel]').forEach(b=>b.addEventListener('click',async()=>{b.disabled=true;try{await api('POST',`/api/jobs/${b.dataset.cancel}/cancel`,{});my(token);}catch(e){toast(e.message);b.disabled=false;}}));
    document.getElementById('mobile-export').addEventListener('click',async()=>download('personal-learning-exchange.json',await api('GET','/api/mobile/exchange')));
    document.getElementById('mobile-exchange-file').addEventListener('change',async e=>{try{const f=e.target.files[0];if(f){await api('POST','/api/mobile/exchange',JSON.parse(await f.text()));toast('处理结果已导入，学习历史保留');}}catch(e){toast(e.message);}});
  }
  async function history(token){const data=await api('GET','/api/study/history');if(viewStale(token))return;
    layout('学习记录',data.days.map(d=>`<section class="mobile-section"><h2>${esc(d.date)}</h2>${d.attempts.map(a=>`<p>${esc(a.zh)}<span class="mobile-translation">${({independent:'独立说出',needs_hint:'需要提示',unable:'说不出'})[a.outcome]} · ${a.recorded?'已录音':'本人自评'} · 下次 ${esc(a.next_due_date)}</span></p>`).join('')}</section>`).join('') || '<p>完成一次口答后，这里会保留实际练习记录。</p>');
  }
  function route(hash,token){if(!MobileRuntime.native)return false;reset();MobileRuntime.navigation(hash);
    const [path,arg]=hash.replace(/^#\//,'').split('/');let action;
    if(path==='today' || !path)action=()=>today(token);else if(path==='materials' || path==='topics')action=()=>materials(token);
    else if(path==='my' || path==='settings')action=()=>my(token);else if(path==='chat-import')action=()=>importView();
    else if(path==='conversation')action=()=>conversation(decodeURIComponent(arg),token);else if(path==='mobile-history' || path==='study-history')action=()=>history(token);
    else if(path==='done'){const parts=hash.replace(/^#\//,'').split('/');action=()=>{location.hash=`#/play/${parts[1]}/${parts[2]}`;};}
    if(!action)return false;Promise.resolve().then(action).catch(e=>{if(!viewStale(token))layout('读取失败',`<p>${esc(e.message)}</p><a class="study-button" href="#/today">返回今日</a>`);});return true;
  }
  return {route,reset};
})();
JSON.parseOrText = text => {try{return JSON.parse(text);}catch(_){return {text};}};
