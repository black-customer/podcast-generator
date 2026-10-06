/* 手机领域规则：同时运行于 Android 安全 JS 引擎和合成数据测试，不接触密钥或网络。 */
(function (root) {
  'use strict';
  function fail(message) { throw new Error(message); }
  function copy(value) { return JSON.parse(JSON.stringify(value)); }
  function values(value) { return Object.keys(value || {}).map(function (k) { return value[k]; }); }
  function hash(text) {
    if (typeof NativeDigest !== 'undefined') return String(NativeDigest.sha256(String(text)));
    if (typeof require === 'function') return require('node:crypto').createHash('sha256').update(text).digest('hex');
    fail('本地摘要服务不可用');
  }
  function createState() { return {version:1, topics:{}, conversations:{}, cards:{}, sessions:{}, attempts:[],
    receipts:{}, drafts:{}, listening:{}, jobs:{}, settings:{}, migration:{}}; }
  function openState(s) {
    if (!s || s.version !== 1) fail('本机数据版本不受支持，请保留原件');
    ['topics','conversations','cards','sessions','receipts','drafts','listening','jobs','settings','migration'].forEach(function(k){
      if(!s[k] || typeof s[k]!=='object' || Array.isArray(s[k]))fail('本机数据结构损坏，请保留原件');});
    if(!Array.isArray(s.attempts))fail('本机练习记录结构损坏');return s;
  }
  function addDays(day, n) {
    var a=day.split('-'), d=new Date(Date.UTC(+a[0],+a[1]-1,+a[2]+n));
    return d.toISOString().slice(0,10);
  }
  function id(value) { return hash(JSON.stringify(value)).slice(0,24); }
  function normalizeMessages(rows) {
    if (!Array.isArray(rows) || !rows.length) fail('没有取得双方聊天文字');
    var seen=Object.create(null), result=[];
    rows.forEach(function (row, i) {
      var role=row.role, text=String(row.text || blockText(row.content_block || row.content) || '').trim();
      if (role !== 'user' && role !== 'assistant') fail('无法确认发言角色');
      if (!text) return;
      var mid=String(row.id || row.message_id || 'message-'+i);
      if (seen[mid]) { if (seen[mid] !== text) fail('消息 ID 冲突'); return; }
      seen[mid]=text; result.push({id:mid,role:role,text:text});
    });
    if (!result.some(function (m) { return m.role==='user'; })) fail('记录缺少用户发言');
    return result;
  }
  function parseTranscript(raw) {
    if (raw && typeof raw==='object' && typeof raw.text==='string') return parseTranscript(raw.text);
    if (typeof raw !== 'string') {
      if(raw.mapping)return {title:raw.title || 'ChatGPT 聊天',provider:'chatgpt',messages:messagesFromChatGPT(raw)};
      if((raw.data || raw).message_snapshot)return messagesFromDoubao(raw);
      return {title:raw.title || '导入聊天',messages:normalizeMessages(raw.messages || raw)};
    }
    var trimmed=raw.trim();
    if (/^[\[{]/.test(trimmed)) return parseTranscript(JSON.parse(trimmed));
    var rows=[], role=null, text=[];
    function flush() { if (role && text.join('\n').trim()) rows.push({role:role,text:text.join('\n')}); }
    trimmed.split(/\r?\n/).forEach(function (line) {
      var m=line.match(/^(?:#{1,4}\s*)?(?:\*\*)?(User|Assistant|Human|You|ChatGPT|豆包|用户|我|AI)(?:\*\*)?\s*(?:[:：](?:\*\*)?\s*(.*)|$)/i);
      if (m) { flush(); role=/^(user|human|you|用户|我)$/i.test(m[1])?'user':'assistant'; text=[m[2] || '']; }
      else if (role) text.push(line);
    }); flush();
    return {title:'导入聊天',messages:normalizeMessages(rows)};
  }
  function messagesFromChatGPT(doc) {
    var mapping=doc.mapping, cur=doc.current_node, seen=Object.create(null), nodes=[];
    if (!mapping || !cur) fail('分享页不包含可确认的当前分支');
    while (cur) {
      if (seen[cur] || !mapping[cur]) fail('分享分支结构损坏');
      seen[cur]=true; nodes.push(mapping[cur]); cur=mapping[cur].parent;
    }
    var rows=[];
    nodes.reverse().forEach(function (node) {
      var m=node.message; if (!m || !m.author || ['user','assistant'].indexOf(m.author.role)<0) return;
      var parts=(m.content || {}).parts || [], texts=[];
      parts.forEach(function (p) { if (typeof p==='string') texts.push(p);
        else if (p && typeof p.text==='string') texts.push(p.text); });
      if (texts.join('\n').trim()) rows.push({id:m.id,role:m.author.role,text:texts.join('\n')});
    }); return normalizeMessages(rows);
  }
  function unescapeHtml(s) { return s.replace(/&quot;/g,'"').replace(/&#39;|&apos;/g,"'")
    .replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&'); }
  function jsonPrefix(s) {
    var i=0, depth=0, quoted=false, escaped=false;
    for (;i<s.length;i++) { var c=s.charAt(i);
      if (quoted) { if (escaped) escaped=false; else if (c==='\\') escaped=true; else if (c==='"') quoted=false; }
      else if(c==='"') quoted=true; else if(c==='{' || c==='[') depth++;
      else if(c==='}' || c===']') { depth--; if (!depth) return JSON.parse(s.slice(0,i+1)); }
    } fail('分享页数据不完整');
  }
  function parseChatGPTPage(html) {
    var scripts=html.match(/<script\b[^>]*>[\s\S]*?<\/script>/gi) || [], flattened=null;
    scripts.some(function (script) {
      var at=script.indexOf('streamController.enqueue('); if(at<0) return false;
      var tail=script.slice(at+'streamController.enqueue('.length), match=tail.match(/^"(?:\\.|[^"\\])*"/);
      if (!match) return false;
      var decoded=JSON.parse(match[0]); if(decoded.charAt(0)!=='[') return false;
      flattened=JSON.parse(decoded); return true;
    });
    if (!flattened) fail('ChatGPT 分享页暂时无法解析，请导入文字或文件');
    var cache={};
    function decode(index) {
      if(index<0) return null; if(cache[index]!==undefined) return cache[index];
      var v=flattened[index], out;
      if(Array.isArray(v)) { out=[];cache[index]=out;v.forEach(function(r){out.push(typeof r==='number'?decode(r):r);});return out; }
      if(v && typeof v==='object') { out={};cache[index]=out;Object.keys(v).forEach(function(k){
        if(!/^_\d+$/.test(k)) fail('分享数据字段不受支持'); out[flattened[+k.slice(1)]]=decode(v[k]); });return out; }
      return v;
    }
    var mi=flattened.indexOf('mapping'), ci=flattened.indexOf('current_node'), ti=flattened.indexOf('title');
    var container=flattened.filter(function(v){return v && !Array.isArray(v) && typeof v==='object' &&
      v['_'+mi]!==undefined && v['_'+ci]!==undefined;})[0];
    if(!container) fail('分享数据没有当前聊天分支');
    return {title:ti>=0 && container['_'+ti]!==undefined?decode(container['_'+ti]):'ChatGPT 聊天',
      provider:'chatgpt',scope:'shared_snapshot',messages:messagesFromChatGPT({mapping:decode(container['_'+mi]),current_node:decode(container['_'+ci])})};
  }
  function blockText(content) {
    if (typeof content==='string') { try { content=JSON.parse(content); } catch (_) { return content; } }
    if(Array.isArray(content)) return content.map(blockText).filter(Boolean).join('\n');
    if(!content || typeof content!=='object') return '';
    if(typeof content.text==='string') return content.text;
    if(content.text_block) return blockText(content.text_block);
    if(content.content) return blockText(content.content);
    return '';
  }
  function messagesFromDoubao(doc) {
    var d=doc.data || doc, snap=d.message_snapshot || {}, rows=snap.message_list || [], seen=Object.create(null);
    var messages=rows.slice().sort(function(a,b){return Number(a.index_in_conv)-Number(b.index_in_conv);})
      .map(function(m){if(+m.user_type!==1 && +m.user_type!==2)fail('分享页出现未知发言角色，请核对导出文件');return {id:String(m.message_id),role:+m.user_type===1?'user':'assistant',
        text:blockText(m.content_block) || blockText(m.content)};}).filter(function(m){
          if(!m.text || seen[m.id]) return false;seen[m.id]=true;return true;});
    return {title:(d.share_info || {}).share_name || '豆包聊天',provider:'doubao',scope:'shared_snapshot',
      messages:normalizeMessages(messages),warnings:((doc.needLazyLoadThreadMsg && values(snap.thread_message_list).length) || snap.has_more)?
        ['分享页包含延迟加载内容，请核对首尾；必要时导入导出文件']:[]};
  }
  function parseDoubaoPage(html) {
    var tags=html.match(/<script\b(?:"[^"]*"|'[^']*'|[^'">])*?>/gi) || [], args=null;
    tags.some(function(t){var m=t.match(/data-fn-args=(['"])([\s\S]*?)\1/);
      if(!m || m[2].indexOf('message_list')<0) return false;
      var raw=unescapeHtml(m[2]);try { args=JSON.parse(raw); } catch (_) { args=JSON.parse(JSON.parse('"'+raw+'"')); }
      return true;
    });
    if(!args) fail('豆包分享页暂时无法解析，请导入文字或文件');
    var document=args[2] && args[2].data && args[2].data.message_snapshot?args[2]:null;
    if(!document && args[1] && args[1][0] && args[1][0].routerDataFnArgs)document=JSON.parse(args[1][0].routerDataFnArgs[0]);
    if(!document)fail('豆包分享数据结构变化，请导入文字或文件');
    return messagesFromDoubao(document);
  }
  function importConversation(s, input, now) {
    var parsed=parseTranscript(input), fingerprint=hash(JSON.stringify(parsed.messages)), key=fingerprint.slice(0,24);
    if(s.conversations[key]) return copy(s.conversations[key]);
    var previous=input.source_url?values(s.conversations).filter(function(c){return c.source_url===input.source_url;}).pop():null;
    var item={id:key,title:String(input.title || parsed.title),provider:input.provider || parsed.provider || 'file',
      scope:input.scope || 'provided_text',warnings:copy(input.warnings || parsed.warnings || []),source_url:input.source_url || '',
      messages:parsed.messages,source_fingerprint:fingerprint,created_at:now,status:'imported',
      notes:[],dialogue:[],audio:null};
    if(previous){item.previous_import_id=previous.id;item.warnings.push('此分享链接的内容已变化，本次保存为更新版本；原有材料与练习记录保留。');}
    s.conversations[key]=item;return copy(item);
  }
  function validateResult(result,messages) {
    if(!result || !Array.isArray(result.dialogue) || !result.dialogue.length || !Array.isArray(result.notes)) fail('生成结果缺少对话或学习笔记');
    result.dialogue.forEach(function(l){if(['A','B'].indexOf(l.speaker)<0 || typeof l.en!=='string' || !l.en.trim() || typeof l.zh!=='string' || !l.zh.trim() || /\[[^\]]*\]|[\u4e00-\u9fff]/.test(l.en)) fail('对话需要纯英文台词和逐句中文');});
    var users=Object.create(null);messages.forEach(function(m){if(m.role==='user' && !/^\s*(?:Role:|You are (?:a|an)\b|Act as\b)/i.test(m.text))users[m.id]=m.text;});
    result.notes.forEach(function(n){
      if(['explicit_gap','text_supported_error','expression_refinement','learned_chunk','recommendation'].indexOf(n.kind)<0 ||
        !n.target || !n.prompt_zh || !n.reference_en || !n.explanation || !Array.isArray(n.sources) || !n.sources.length) fail('笔记缺少练习或来源');
      n.sources.forEach(function(r){if(!r.quote || !users[r.message_id] || users[r.message_id].indexOf(r.quote)<0) fail('笔记引用不存在于原始用户发言');});
      if(n.kind==='text_supported_error') {
        var e=n.original_error;if(!e || !e.quote || !e.issue || !e.correction || (e.quote.match(/[a-z]+(?:['’][a-z]+)?/gi) || []).length<2 ||
          !n.sources.some(function(r){return r.quote.indexOf(e.quote)>=0;})) fail('个人错误缺少准确英文证据');
        if(/发音|口音|重音|语调|音节|pronunciation|intonation|syllable|accent|score|评分/i.test(e.issue)) fail('文字不能证明发音或评分问题');
        if(/^mushroom has(?:\s|$)/i.test(e.quote.trim()) && /主谓|plural|agreement|复数/i.test(e.issue)) fail('单数 mushroom has 本身正确');
      }
    });return copy(result);
  }
  function applyResult(s,cid,result,now) {
    var conv=s.conversations[cid];if(!conv) fail('聊天不存在');result=validateResult(result,conv.messages);
    if(conv.audio && JSON.stringify(conv.dialogue)!==JSON.stringify(result.dialogue)){
      conv.previous_audio={path:conv.audio,dialogue:copy(conv.dialogue),timeline:copy(conv.timeline || {}),duration:conv.duration || 0};conv.audio=null;conv.timeline=null;
    }
    conv.dialogue=result.dialogue;conv.notes=result.notes;conv.status=conv.audio?'ready':'text_ready';
    result.notes.forEach(function(n){if(['explicit_gap','text_supported_error'].indexOf(n.kind)>=0) enrollNote(s,cid,n,now,true);});
    return copy(conv);
  }
  function enrollNote(s,cid,n,now,automatic) {
    var key=id(['chat',n.target.toLowerCase().trim()]);
    if(s.cards[key]) { if(s.cards[key].sources.indexOf(cid)<0)s.cards[key].sources.push(cid);return s.cards[key]; }
    var card={id:key,kind:'conversation',conversation_id:cid,note_index:s.conversations[cid].notes.indexOf(n),sources:[cid],zh:n.prompt_zh,en:n.reference_en,
      explanation:n.explanation,usage:'合理的其他表达也成立。',question:s.conversations[cid].title,source:s.conversations[cid].title,
      level:0,due_date:addDays((automatic?s.conversations[cid].created_at:now).slice(0,10),1),learned_at:null,last_adjusted_date:null,paused:false,superseded:false};
    s.cards[key]=card;return card;
  }
  function startSession(s,now,requested) {
    var active=values(s.sessions).filter(function(x){return x.state==='active';})[0];if(active)return sessionView(s,active.id);
    if(requested && (!Array.isArray(requested) || requested.length>10 || requested.some(function(k){return !s.cards[k];})))fail('复习选择无效');
    var day=now.slice(0,10), cards=values(s.cards).filter(function(c){return !c.paused && !c.superseded && (requested?requested.indexOf(c.id)>=0:c.due_date<=day);})
      .sort(function(a,b){return a.due_date.localeCompare(b.due_date) || a.id.localeCompare(b.id);}).slice(0,10);
    var key=id([now,Object.keys(s.sessions).length]), session={id:key,state:cards.length?'active':'completed',
      cards:cards.map(function(c){return c.id;}),current_index:0,results:[],recording_id:null,responded:false,
      hint_used:false,answer_visible:false,actions:{},created_at:now};
    s.sessions[key]=session;return sessionView(s,key);
  }
  function sessionView(s,sid) {
    var session=s.sessions[sid];if(!session)fail('复习轮次不存在');var out=copy(session), card=s.cards[session.cards[session.current_index]];
    out.total=session.cards.length;out.current_card=card?copy(card):null;
    if(out.current_card && !session.answer_visible){delete out.current_card.en;delete out.current_card.explanation;delete out.current_card.usage;}
    return out;
  }
  function sessionAction(s,sid,action,receipt) {
    var x=s.sessions[sid];if(!x || x.state!=='active')fail('本轮已结束');
    if(x.actions[receipt])return sessionView(s,sid);
    if(action==='answered_without_recording'){x.responded=true;x.recording_id=null;x.answer_visible=true;}
    else if(action==='hint')x.hint_used=true;
    else if(action==='show_answer'){if(!x.responded)x.hint_used=true;x.answer_visible=true;}
    else if(action==='skip'){var c=s.cards[x.cards[x.current_index]];x.results.push({zh:c.zh,outcome:'skipped'});advance(x);}
    else fail('未知复习动作');x.actions[receipt]=true;return sessionView(s,sid);
  }
  function advance(x) { x.current_index++;x.responded=false;x.answer_visible=false;x.hint_used=false;x.recording_id=null;
    if(x.current_index>=x.cards.length)x.state='completed'; }
  function submitAttempt(s,sid,rating,receipt,now) {
    if(s.receipts[receipt])return copy(s.receipts[receipt]);
    var x=s.sessions[sid];if(!x || x.state!=='active')fail('本轮已结束');
    if(['independent','needs_hint','unable'].indexOf(rating)<0)fail('未知自评结果');
    if(rating==='independent' && (!x.responded || x.hint_used))fail('需要独立口答，且未使用提示');
    var c=s.cards[x.cards[x.current_index]],day=now.slice(0,10);
    if(c.paused || c.superseded)fail('材料已变化或日程已暂停，请跳过并重新加入');
    if(rating==='needs_hint' && !x.responded)fail('尚未完成口答，可选择暂时说不出');
    if(c.last_adjusted_date!==day){if(rating==='independent'){c.level=Math.min(c.level+1,4);c.due_date=addDays(day,[1,3,7,14,30][c.level]);}
      else {c.level=0;c.due_date=addDays(day,1);}c.last_adjusted_date=day;}
    var attempt={id:receipt,session_id:sid,card_id:c.id,zh:c.zh,outcome:rating,recorded:!!x.recording_id,
      recording_id:x.recording_id,next_due_date:c.due_date,created_at:now};
    s.attempts.push(attempt);s.receipts[receipt]=attempt;x.results.push(attempt);advance(x);return copy(attempt);
  }
  function saveDraft(s,qid,text,answer,mode,revision) {
    var old=s.drafts[qid] || {revision:0};if(old.revision!==revision)fail('草稿版本冲突，请恢复后重试');
    var draft={question_id:qid,question_text:text,answer:answer,mode:mode,revision:revision+1};s.drafts[qid]=draft;return copy(draft);
  }
  function migratePack(s,manifest,items) {
    if([1,2].indexOf(manifest.pack_version)<0)fail('语料包版本不受支持');
    manifest.topics.forEach(function(t){if(!s.topics[t.id])s.topics[t.id]={id:t.id,name:t.name,items:{}};});
    items.forEach(function(i){var t=s.topics[i.topic_id];if(!t)fail('导入条目缺少所属话题');
      var entry=copy(i),old=t.items[i.id],same=old && sourceFingerprint(old.texts || {})===sourceFingerprint(entry.texts || {});
      if(same){entry.progress=old.progress || {version:1,stage:'before',draft:[],facts:{},recordings:[]};
        if(!entry.material && old.material)entry.material=copy(old.material);if(old.archived_versions)entry.archived_versions=copy(old.archived_versions);
        if(!Object.keys(entry.audio || {}).length){entry.audio=copy(old.audio || {});entry.audioFingerprints=copy(old.audioFingerprints || {});entry.timelines=copy(old.timelines || {});}}
      else {entry.progress={version:1,stage:'before',draft:[],facts:{},recordings:[]};
        if(old){var archived=copy(old);delete archived.archived_versions;entry.archived_versions=(old.archived_versions || []).concat([archived]);
          values(s.cards).forEach(function(c){if(c.topic_id===i.topic_id && c.item_id===i.id){c.paused=true;c.superseded=true;}});}}
      t.items[i.id]=entry;
    });
    s.migration.legacy_pack=true;return s;
  }
  function exportExchange(s) {
    var conversations={},topics={};values(s.conversations).forEach(function(c){var out=copy(c);delete out.audio;delete out.timeline;delete out.previous_audio;conversations[c.id]=out;});
    values(s.topics).forEach(function(t){var out={id:t.id,name:t.name,items:{}};values(t.items).forEach(function(i){
      out.items[i.id]={id:i.id,title:i.title,texts:copy(i.texts || {}),meta:copy(i.meta || {}),audio:{}};
      if(i.dialogue)out.items[i.id].dialogue=copy(i.dialogue);if(i.material)out.items[i.id].material=copy(i.material);
    });topics[t.id]=out;});return {version:1,type:'personal_learning_exchange',conversations:conversations,topics:topics};
  }
  function importExchange(s,exchange,now) {
    if(exchange.version!==1 || exchange.type!=='personal_learning_exchange')fail('个人交换包版本不支持');
    var original=s;s=copy(s);
    values(exchange.conversations).forEach(function(c){var imported=importConversation(s,c,now);
      if(imported.source_fingerprint!==c.source_fingerprint)fail('交换包原始记录指纹不一致');
      if(c.dialogue && c.dialogue.length)applyResult(s,imported.id,{dialogue:c.dialogue,notes:c.notes},now);});
    values(exchange.topics || {}).forEach(function(t){var entries=[];values(t.items || {}).forEach(function(i){
      var old=s.topics[t.id] && s.topics[t.id].items[i.id];if(old && old.texts.original_answer!==i.texts.original_answer)fail('原始回答已变化，请重新导出任务');
      if(i.dialogue){validateIeltsResult({natural_english:i.texts.natural_english,podcast_text:i.texts.podcast_text,podcast_script:i.texts.podcast_script,dialogue:i.dialogue},i.texts.original_answer);}
      var entry=copy(i);entry.topic_id=t.id;entry.audio={};if(i.material)entry.material=validateStudyMaterial(i.material,i.texts);entries.push(entry);
      values(s.jobs).forEach(function(j){if(j.topic_id===t.id && j.item_id===i.id && (j.state==='queued' || j.state==='running'))j.state='cancelled';});
    });migratePack(s,{pack_version:2,topics:[{id:t.id,name:t.name}]},entries);});
    Object.keys(original).forEach(function(k){delete original[k];});Object.keys(s).forEach(function(k){original[k]=s[k];});
    return s;
  }
  function splitMessages(messages,limit) {
    var chunks=[],chunk=[],size=0;
    messages.forEach(function(m){if(chunk.length && size+m.text.length>limit){chunks.push(chunk);chunk=[];size=0;}
      chunk.push(m);size+=m.text.length;});if(chunk.length)chunks.push(chunk);return chunks;
  }
  function cleanScript(s){return String(s || '').replace(/\[(curious|relaxed|uncertain|emphasis|break)\]/g,'').replace(/[ \t]+/g,' ').trim();}
  function validateIeltsResult(r,original){
    ['natural_english','podcast_text','podcast_script'].forEach(function(k){if(typeof r[k]!=='string' || !r[k].trim())fail('回答缺少 '+k);});
    if(!original || /\[[^\]]*\]|[\u4e00-\u9fff]/.test(r.natural_english+' '+r.podcast_text))fail('原话缺失或英文文本包含标签、中文');
    if(cleanScript(r.podcast_script)!==r.podcast_text.trim())fail('播报稿与可见对话不同');
    if(!Array.isArray(r.dialogue) || !r.dialogue.length || r.dialogue[0].speaker!=='A')fail('缺少可播报的完整 A/B 对话');
    r.dialogue.forEach(function(l){if(['A','B'].indexOf(l.speaker)<0 || !l.en || !l.zh)fail('对话缺少说话人、中英文');});
    if(r.dialogue.map(function(l){return l.speaker+': '+l.en;}).join('\n')!==r.podcast_text.trim())fail('逐句对话与播报文本不对应');
    return copy(r);
  }
  function validateStudyMaterial(material,texts){
    var expected=[];String(texts.podcast_text || '').split(/\r?\n/).forEach(function(l){if(/^B:\s*/.test(l))
      l.replace(/^B:\s*/,'').split(/([.!?])\s+/).reduce(function(a,p,i){if(i%2===0)a.push(p);else a[a.length-1]+=p;return a;},[]).forEach(function(s){if(s.trim())expected.push(s.trim());});});
    if(!material.complete_chinese || !Array.isArray(material.sentences) || material.sentences.length!==expected.length)fail('逐句学习材料不完整');
    material.sentences.forEach(function(row,i){if(row.en!==expected[i] || !row.zh || !row.explanation || !row.usage)fail('材料与 B 回答的句子不对应');
      var e=row.original_error;if(e){if(!e.quote || String(texts.original_answer || '').indexOf(e.quote)<0 || !e.issue || !e.correction || /发音|评分|pronunciation|score/i.test(e.issue))fail('个人错误没有原话证据');}});
    var out=copy(material);out.version=1;out.source_fingerprint=sourceFingerprint(texts);return out;
  }
  function sourceFingerprint(texts){return hash('['+['original_answer','natural_english','podcast_text','podcast_script'].map(function(k){return JSON.stringify(texts[k] || '');}).join(', ')+']');}
  function splitAudioLine(line,limit){
    var text=String(line.en || '').trim(),parts=[],rest=text;
    while(rest.length>limit){var prefix=rest.slice(0,limit+1),at=Math.max(prefix.lastIndexOf('. '),prefix.lastIndexOf('? '),prefix.lastIndexOf('! '));
      if(at>0)at++;else at=prefix.lastIndexOf(' ');if(at<1)fail('台词包含无法安全分段的超长单词');
      parts.push({speaker:line.speaker,en:rest.slice(0,at).trim(),zh:line.zh,split_estimated:true});rest=rest.slice(at).trim();}
    if(rest)parts.push({speaker:line.speaker,en:rest,zh:line.zh,split_estimated:parts.length>0});return parts;
  }
  function homePracticeCandidates(s,overview) {
    overview=overview || {};var pool=[],bySource={},ordered=[],seen={};
    function span(path,timeline,en,duration) {
      if(!path)return null;
      var line=values((timeline || {}).lines).filter(function(l){return typeof l.text==='string' && l.text.indexOf(en)>=0
        && l.role!=='a' && l.speaker!=='A' && isFinite(l.start) && isFinite(l.end) && l.start>=0 && l.end>l.start;})[0];
      if(!line)return {url:path,start:0,end:duration>0?duration:null,mode:'estimated',reason:'未取得单句定位，播放完整回答。'};
      var exact=line.text===en,at=line.text.indexOf(en),scale=(line.end-line.start)/line.text.length;
      return {url:path,start:line.start+(exact?0:at*scale),end:exact?line.end:line.start+(at+en.length)*scale,
        mode:exact?'measured':'estimated',reason:exact?'本句边界来自实际音频片段。':'句内位置为估算，播放包含本句的片段。'};
    }
    function add(key,row,source,href,audio,ref) {
      if(!row || typeof row.zh!=='string' || !row.zh.trim() || typeof row.en!=='string' || !row.en.trim() || !audio)return;
      var entry={id:key,zh:row.zh,en:row.en,source:source,href:href,audio:audio};
      Object.keys(ref || {}).forEach(function(k){entry[k]=ref[k];});pool.push(entry);bySource[key]=entry;
    }
    Object.keys(s.topics || {}).sort().forEach(function(tid){var t=s.topics[tid];
      Object.keys(t.items || {}).sort().forEach(function(iid){var i=t.items[iid],m=i.material;
        if(!m || !Array.isArray(m.sentences) || m.source_fingerprint!==sourceFingerprint(i.texts || {}))return;
        m.sentences.forEach(function(row,n){if(!row || typeof row.en!=='string')return;add('ielts/'+tid+'/'+iid+'/'+n,row,t.name || i.title,
          '#/learn/'+encodeURIComponent(tid)+'/'+encodeURIComponent(iid),
          span((i.audio || {}).podcast || (i.audio || {}).default,(i.timelines || {}).podcast,row.en,(i.meta || {}).duration_sec_podcast),
          {kind:'ielts',topic_id:tid,item_id:iid,sentence_index:n,source_fingerprint:m.source_fingerprint});});
      });
    });
    Object.keys(s.conversations || {}).sort().forEach(function(cid){var c=s.conversations[cid];
      (c.dialogue || []).forEach(function(row,n){if(!row || row.speaker!=='B' || typeof row.en!=='string')return;
        add('chat/'+cid+'/'+n,row,c.title,'#/conversation/'+encodeURIComponent(cid),
          span(c.audio,c.timeline,row.en,c.duration),{kind:'conversation',conversation_id:cid});});
    });
    function push(entry){if(entry && !seen[entry.id]){seen[entry.id]=true;ordered.push(entry);}}
    function fromCard(card){
      if(!card || card.paused || card.superseded || typeof card.en!=='string' || !card.en.trim()
        || typeof card.zh!=='string' || !card.zh.trim())return null;
      if(card.kind==='ielts'){var found=bySource['ielts/'+card.topic_id+'/'+card.item_id+'/'+card.sentence_index];
        return found && found.source_fingerprint===card.source_fingerprint?found:null;}
      var c=s.conversations[card.conversation_id];if(!c)return null;
      var base=pool.filter(function(r){return r.conversation_id===card.conversation_id && r.en===card.en;})[0];
      if(base)return base;
      function spoken(rows){return (rows || []).some(function(r){return r.speaker==='B' && typeof r.en==='string' && r.en.indexOf(card.en)>=0;});}
      var audio=spoken(c.dialogue)?span(c.audio,c.timeline,card.en,c.duration):null;
      if(!audio && c.previous_audio){var old=c.previous_audio;
        if(spoken(old.dialogue))audio=span(old.path,old.timeline,card.en,old.duration);}
      if(!audio)return null;
      return {id:'chat-note/'+card.id,zh:card.zh,en:card.en,source:c.title,kind:'conversation',
        conversation_id:c.id,href:'#/conversation/'+encodeURIComponent(c.id),audio:audio};
    }
    var active=(s.sessions || {})[overview.active_session_id];
    if(active)push(fromCard((s.cards || {})[(active.cards || active.card_ids || [])[active.current_index]]));
    (overview.continue_learning || []).forEach(function(row){var i=((s.topics[row.topic_id] || {}).items || {})[row.item_id];
      var n=(i && i.progress || {}).sentence_index || 0;push(bySource['ielts/'+row.topic_id+'/'+row.item_id+'/'+n]);});
    (overview.due_preview || []).slice().sort(function(a,b){return String(a.due_date || '').localeCompare(String(b.due_date || ''))
      || String(a.id).localeCompare(String(b.id));}).forEach(function(card){push(fromCard(card));});
    pool.forEach(push);return ordered;
  }
  var exported={createState:createState,openState:openState,addDays:addDays,hash:hash,copy:copy,values:values,
    normalizeMessages:normalizeMessages,parseTranscript:parseTranscript,messagesFromChatGPT:messagesFromChatGPT,
    parseChatGPTPage:parseChatGPTPage,messagesFromDoubao:messagesFromDoubao,parseDoubaoPage:parseDoubaoPage,
    importConversation:importConversation,validateResult:validateResult,applyResult:applyResult,enrollNote:enrollNote,
    startSession:startSession,sessionView:sessionView,sessionAction:sessionAction,submitAttempt:submitAttempt,
    saveDraft:saveDraft,migratePack:migratePack,exportExchange:exportExchange,importExchange:importExchange,splitMessages:splitMessages};
  exported.validateIeltsResult=validateIeltsResult;exported.validateStudyMaterial=validateStudyMaterial;exported.splitAudioLine=splitAudioLine;
  exported.sourceFingerprint=sourceFingerprint;
  exported.homePracticeCandidates=homePracticeCandidates;
  root.MobileCore=exported;if(typeof module!=='undefined')module.exports=exported;
}(this));
