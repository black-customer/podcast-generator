/* 手机本地 API 适配规则；网络、文件和密钥操作由原生宿主执行。 */
(function(root){
  'use strict';
  var C=root.MobileCore || require('./mobile-core.js');
  function bad(m){throw new Error(m);}
  function vals(o){return C.values(o);}
  function norm(s){return String(s || '').toLowerCase().replace(/[^\w\u4e00-\u9fff]+/g,' ').trim();}
  function query(url){var q={};(url.split('?')[1] || '').split('&').forEach(function(p){var a=p.split('=');if(a[0])q[decodeURIComponent(a[0])]=decodeURIComponent(a.slice(1).join('=').replace(/\+/g,' '));});return q;}
  function findItem(s,t,i){var item=s.topics[t] && s.topics[t].items[i];if(!item)bad('本机条目不存在');return item;}
  function summary(i){var audio=i.audio || {},t=i.texts || {},m=i.meta || {},pod=!!(audio.podcast || audio.default);return {id:i.id,title:i.title || t.question,
    status:pod || audio.monologue?'generated':t.podcast_text || t.natural_english?'ready':'empty',has_audio:!!(pod || audio.monologue),
    has_podcast:pod,has_monologue:!!audio.monologue,has_audio_podcast:pod,has_audio_monologue:!!audio.monologue,
    duration_sec_podcast:m.duration_sec_podcast || 0,study_status:i.material?'ready':'needs_input',created_at:m.created_at};}
  function full(i){var r=summary(i);Object.keys(i.texts || {}).forEach(function(k){r[k]=i.texts[k];});r.original_answer_effective=r.original_answer || r.chinese || '';return r;}
  function progress(i){if(!i.progress)i.progress={version:1,stage:'before',before_started:false,sentence_index:0,draft:[],facts:{},recordings:[]};return i.progress;}
  function enrollIelts(s,tid,i,now){
    var p=progress(i),rows=(i.material || {}).sentences || [],fp=(i.material || {}).source_fingerprint;
    Object.keys(p.facts).forEach(function(k){var f=p.facts[k],n=+k,row=rows[n];
      if(!row || !f.passed || !(f.hint_used || f.wrong_attempts || f.favorite))return;
      var key=C.hash(JSON.stringify([tid,i.id,n,fp])).slice(0,24);
      if(s.cards[key])return;
      vals(s.cards).forEach(function(c){if(c.topic_id===tid && c.item_id===i.id && c.sentence_index===n){c.superseded=true;c.paused=true;}});
      s.cards[key]={id:key,kind:'ielts',topic_id:tid,item_id:i.id,sentence_index:n,source_fingerprint:fp,
        zh:row.zh,en:row.en,explanation:row.explanation,usage:row.usage,source:s.topics[tid].name,question:i.texts.question,
        level:0,due_date:C.addDays(now.slice(0,10),1),learned_at:now,last_adjusted_date:null,paused:false,superseded:false};
    });
  }
  function publicSession(s,sid){var r=C.sessionView(s,sid);r.phase=r.answer_visible?'compare':'prompt';
    r.can_rate_independent=r.responded && !r.hint_used;r.card_ids=r.cards;
    if(r.current_card){r.current_card.availability=r.current_card.paused?'paused':'ready';if(r.current_card.kind==='conversation'){r.current_card.topic_id='conversation';r.current_card.item_id=r.current_card.conversation_id;r.current_card.sentence_index=Math.max(0,r.current_card.note_index || 0);}}
    return r;}
  function bankQuery(s,bank,q){
    var coreNames=['work or studies','work or study','work studies','work study','work','home accommodation','home or accommodation','home','accommodation','hometown','the area you live in','area you live in','the city you live in','city you live in'];
    var coreIds=(bank.topics || []).filter(function(t){return coreNames.indexOf(norm(t.name_en))>=0;}).map(function(t){return t.id;});
    var setFilter=q.set_filter || q.set || '';
    function memberships(r){return (bank.sets || []).filter(function(x){return (x.question_ids || []).indexOf(r.id)>=0;});}
    function inSet(r){return setFilter==='core'?coreIds.indexOf(r.topic_id)>=0:!setFilter || memberships(r).some(function(x){return x.id===setFilter;});}
    var answered={};vals(s.topics).forEach(function(t){vals(t.items).forEach(function(i){if((i.texts.original_answer || '').trim())
      answered[norm(i.texts.question)]={topic_id:t.id,item_id:i.id,has_audio:!!(i.audio || {}).podcast};});});
    var rows=(bank.questions || []).filter(function(r){var a=answered[norm(r.text)];return (!q.part || r.part===+q.part) &&
      (!q.topic || r.topic_id===q.topic) && (!q.q || (r.text+' '+(r.text_zh || '')).toLowerCase().indexOf(q.q.toLowerCase())>=0) &&
      (q.answer_status!=='answered' || !!a) && (q.answer_status!=='unanswered' || !a) &&
      inSet(r);});
    var size=Math.max(1,Math.min(100,+q.page_size || 20)),count=Math.ceil(rows.length/size),page=Math.max(1,Math.min(+q.page || 1,count || 1));
    var selected=null;if((q.random==='1' || q.random==='true') && rows.length){selected=rows[Math.floor(Math.random()*rows.length)];page=Math.floor(rows.indexOf(selected)/size)+1;}
    var result=selected?[selected]:rows.slice((page-1)*size,page*size);
    result=result.map(function(r){var out=C.copy(r),t=(bank.topics || []).filter(function(t){return t.id===r.topic_id;})[0] || {};
      out.topic_name_en=t.name_en || '';out.topic_name_zh=t.name_zh || '';out.topic_label=[t.name_zh,t.name_en].filter(Boolean).join(' · ');
      out.topic_name=t.name_zh || t.name_en || '';out.core=coreIds.indexOf(r.topic_id)>=0;
      out.set_labels=memberships(r).map(function(x){return x.start_month+'–'+x.end_month+'月';});
      out.answered_item=answered[norm(r.text)] || null;out.has_audio=!!(out.answered_item || {}).has_audio;out.answered=!!out.answered_item;out.sets=[];return out;});
    var topics=(bank.topics || []).map(function(t){var x=C.copy(t);x.count=(bank.questions || []).filter(function(r){return r.topic_id===t.id && (!q.part || r.part===+q.part) && inSet(r);}).length;return x;}).filter(function(t){return t.count>0;});
    return {available:!!(bank.questions || []).length,items:result,total:rows.length,page:page,pageCount:count,page_size:size,
      topics:topics,sets:(bank.sets || []).map(function(x){var out=C.copy(x);out.short=x.start_month+'–'+x.end_month+'月';return out;}),selected_page:page};
  }
  function route(s,method,url,body,now,bank){
    C.openState(s);body=body || {};bank=bank || {};var path=url.split('?')[0].split('/').map(decodeURIComponent).join('/'),q=query(url),m;
    if(path==='/api/health')return {ok:true,mode:'mobile',version:'mobile-learning-1'};
    if(path==='/api/conversations')return vals(s.conversations).map(function(c){return {id:c.id,title:c.title,provider:c.provider,status:c.status,created_at:c.created_at,has_audio:!!c.audio,message_count:c.messages.length};});
    if(path==='/api/conversations/import' && method==='POST')return C.importConversation(s,body,now);
    m=path.match(/^\/api\/conversations\/([^/]+)$/);if(m){var conv=s.conversations[m[1]];if(!conv)bad('聊天不存在');return C.copy(conv);}
    m=path.match(/^\/api\/conversations\/([^/]+)\/notes\/(\d+)\/enroll$/);if(m)return C.enrollNote(s,m[1],s.conversations[m[1]].notes[+m[2]],now);
    if(path==='/api/mobile/exchange'){if(method==='GET')return C.exportExchange(s);C.importExchange(s,body,now);return {ok:true};}
    if(path==='/api/topics')return vals(s.topics).map(function(t){var items=vals(t.items),n=items.filter(function(i){return !!(i.audio || {}).podcast;}).length;
      return {id:t.id,name:t.name,total:items.length,generated:n,ready:items.length-n,empty:0,error:0,total_sec:items.reduce(function(a,i){return a+((i.meta || {}).duration_sec_podcast || 0);},0)};});
    m=path.match(/^\/api\/topics\/([^/]+)$/);if(m){var t=s.topics[m[1]];if(!t)bad('话题不存在');return {id:t.id,name:t.name,items:vals(t.items).map(summary)};}
    m=path.match(/^\/api\/topics\/([^/]+)\/items\/([^/]+)(.*)$/);
    if(m){var tid=m[1],iid=m[2],suffix=m[3],i;
      if(tid==='conversation' && suffix.indexOf('/study/audio/')===0){var c=s.conversations[iid],note=c.notes[+suffix.split('/').pop()],lines=(c.timeline || {}).lines || [],found,ref=note?note.reference_en:'',audio=c.audio;
        if(q.card_id && s.cards[q.card_id] && s.cards[q.card_id].conversation_id===iid)ref=s.cards[q.card_id].en;
        if(ref)found=lines.filter(function(l){return l.text.indexOf(ref)>=0;})[0];
        if(!found && c.previous_audio && ref){found=(c.previous_audio.timeline.lines || []).filter(function(l){return l.text.indexOf(ref)>=0;})[0];if(found)audio=c.previous_audio.path;}
        return {url:audio,start:found?found.start:0,end:found?found.end:c.duration || 0,mode:found?'measured':'estimated',reason:found?'播放包含该表达的实测片段。':'未取得单句定位，播放完整对话。'};}
      i=findItem(s,tid,iid);
      if(!suffix){if(method==='PATCH'){
        if(typeof body.original_answer!=='string' || !body.original_answer.trim())bad('原始回答不能为空');
        i.texts.original_answer=body.original_answer;i.material=null;i.meta.study_status='needs_input';
        vals(s.cards).forEach(function(c){if(c.topic_id===tid && c.item_id===iid){c.paused=true;c.superseded=true;}});
      }return full(i);}
      if(/^\/timeline\//.test(suffix)){var tr=suffix.split('/').pop();return (i.timelines || {})[tr] || {lines:[],words:[],mode:'estimated'};}
      if(suffix==='/study')return {status:i.material?'ready':i.meta.study_status || 'needs_input',material:i.material || null};
      if(suffix==='/study/prepare' && method==='POST'){
        if(!i.texts.original_answer || !i.texts.podcast_text || !i.audio.podcast)bad('请先补齐原话与播客音频');
        var key=C.hash(JSON.stringify(['study',tid,iid,i.texts])).slice(0,24),oldJob=s.jobs[key];
        if(oldJob && (oldJob.state==='running' || oldJob.state==='queued'))return C.copy(oldJob);
        var next={id:key,job_id:key,kind:'study',topic_id:tid,item_id:iid,state:'queued',phase:'study',created_at:now,errors:[]};
        s.jobs[key]=next;i.meta.study_status='preparing';return C.copy(next);
      }
      if(suffix==='/study/progress'){var p=progress(i);if(method==='PATCH'){
        if(body.stage && ['before','dictation','chinese','recall','summary'].indexOf(body.stage)<0)bad('学习阶段错误');
        if(body.facts){Object.keys(body.facts).forEach(function(k){if(!/^\d+$/.test(k) || !i.material || +k>=i.material.sentences.length)bad('句号超出材料');
          var old=p.facts[k] || {},f=body.facts[k];Object.keys(f).forEach(function(x){if(['hint_used','wrong_attempts','favorite','passed','review_attempts'].indexOf(x)<0)bad('学习事实字段错误');old[x]=f[x];});p.facts[k]=old;});}
        ['stage','before_started','sentence_index','draft'].forEach(function(k){if(body[k]!==undefined)p[k]=body[k];});enrollIelts(s,tid,i,now);}
        return C.copy(p);}
      var a=suffix.match(/^\/study\/audio\/(\d+)$/);if(a){var row=i.material.sentences[+a[1]],lines=((i.timelines || {}).podcast || {}).lines || [];
        var l=lines.filter(function(x){return (x.role==='b' || x.speaker==='B') && x.text.indexOf(row.en)>=0;})[0];
        var exact=l && l.text===row.en,at=l?l.text.indexOf(row.en):0,scale=l?(l.end-l.start)/Math.max(1,l.text.length):0;
        return {url:i.audio.podcast,start:l?l.start+(exact?0:at*scale):0,end:l?(exact?l.end:l.start+(at+row.en.length)*scale):(i.meta.duration_sec_podcast || 0),mode:exact?'measured':'estimated',reason:exact?'本句边界来自实际合成片段。':'句内位置为估算；也可以回听完整回答。'};}
      if(suffix==='/study/oral-review')return {cards:vals(s.cards).filter(function(c){return c.topic_id===tid && c.item_id===iid;})};
      if(suffix==='/study/recordings' && method==='POST'){var rec={id:body.id || C.hash(now).slice(0,24),stage:body.stage,created_at:now,
        duration_sec:body.duration_sec || 0,path:body.path,mime_type:body.mime_type || 'audio/mp4'};
        progress(i).recordings.push(rec);return rec;}
      var deleted=suffix.match(/^\/study\/recordings\/([^/]+)$/);if(deleted && method==='DELETE'){
        progress(i).recordings=progress(i).recordings.filter(function(r){return r.id!==deleted[1];});return {ok:true};}
      bad('手机暂不支持该条目操作');
    }
    if(path==='/api/bank/questions')return bankQuery(s,bank,q);
    if(path==='/api/bank/topics')return bank.topics || [];
    m=path.match(/^\/api\/bank\/questions\/([^/]+)\/answers$/);if(m){var question=(bank.questions || []).filter(function(r){return r.id===m[1];})[0],answers=[];
      vals(s.topics).forEach(function(t){vals(t.items).forEach(function(i){if(question && norm(i.texts.question)===norm(question.text) && i.texts.original_answer)
        answers.push({topic_id:t.id,item_id:i.id,has_audio:!!(i.audio || {}).podcast,created_at:(i.meta || {}).created_at || ''});});});
      answers.sort(function(a,b){return b.created_at.localeCompare(a.created_at);});return {answers:answers};}
    if(path==='/api/generation-requests' && method==='POST'){
      var question=(bank.questions || []).filter(function(r){return r.id===body.question_id;})[0];if(!question || !String(body.answer || '').trim())bad('题目或回答为空');
      var tid='mobile-ielts',iid=C.hash(now+String(Object.keys(s.jobs).length)).slice(0,24);
      if(!s.topics[tid])s.topics[tid]={id:tid,name:'我的雅思回答',items:{}};
      s.topics[tid].items[iid]={id:iid,title:question.text,texts:{question:question.text,original_answer:body.answer},audio:{},meta:{created_at:now,status:'empty'}};
      var job={id:iid,job_id:iid,topic_id:tid,item_id:iid,kind:'ielts',state:'queued',phase:'rewrite',errors:[],created_at:now};s.jobs[iid]=job;return C.copy(job);
    }
    if(path==='/api/study/today'){var due=vals(s.cards).filter(function(c){return !c.paused && !c.superseded && c.due_date<=now.slice(0,10);}),pending=[];
      vals(s.topics).forEach(function(t){vals(t.items).forEach(function(i){if(i.material && progress(i).stage!=='summary')pending.push({topic_id:t.id,item_id:i.id,question:i.texts.question,stage:progress(i).stage});});});
      var active=vals(s.sessions).filter(function(x){return x.state==='active';})[0];return {pending_learning:pending,continue_learning:pending,
        due_count:due.length,due_preview:due.slice(0,10),needs_material_count:0,needs_material:[],has_learning_records:!!s.attempts.length,active_session_id:active?active.id:null};}
    if(path==='/api/study/review')return vals(s.cards);
    if(path==='/api/study/review-sessions' && method==='POST')return publicSession(s,C.startSession(s,now,body.card_ids).id);
    m=path.match(/^\/api\/study\/review-sessions\/([^/]+)(.*)$/);if(m){
      if(!m[2])return publicSession(s,m[1]);
      if(m[2]==='/actions'){C.sessionAction(s,m[1],body.action,body.action_id);var out=publicSession(s,m[1]);
        if(body.action==='hint')out.hint_text=s.cards[s.sessions[m[1]].cards[s.sessions[m[1]].current_index]].en;return out;}
      if(m[2]==='/attempts')return C.submitAttempt(s,m[1],body.rating,body.submission_id,now);
    }
    m=path.match(/^\/api\/study\/review-cards\/([^/]+)$/);if(m){var card=s.cards[m[1]];if(!card)bad('句子不存在');if(body.paused!==undefined)card.paused=!!body.paused;return C.copy(card);}
    if(path==='/api/study/history'){var days={};s.attempts.forEach(function(a){var d=a.created_at.slice(0,10);if(!days[d])days[d]={date:d,attempts:[],items:[]};days[d].attempts.push(a);});
      return {days:vals(days).reverse(),undated_legacy_count:0};}
    if(path==='/api/answer-drafts')return {drafts:vals(s.drafts)};
    m=path.match(/^\/api\/answer-drafts\/([^/]+)$/);if(m){var old=s.drafts[m[1]] || {answer:'',mode:'api',revision:0,question_text:''};
      if(method==='PUT')return C.saveDraft(s,m[1],body.question_text,body.answer,body.mode,body.revision);
      if(method==='DELETE'){var revision=body.revision!==undefined?body.revision:q.revision;
        if(revision!==undefined && +revision!==old.revision)bad('草稿版本冲突');s.drafts[m[1]]={answer:'',mode:'api',revision:old.revision+1,question_text:old.question_text};}
      return C.copy(s.drafts[m[1]] || old);}
    if(path==='/api/listening-progress'){
      var source=method==='GET'?q:body;
      if(source.kind!=='item' || !source.topic_id || !source.item_id || !source.track)bad('收听来源不完整');
      var key=C.hash(JSON.stringify([source.kind,source.topic_id,source.item_id,source.track]));
      var item=findItem(s,source.topic_id,source.item_id),fp=(item.audioFingerprints || {})[source.track] || '';
      if(method==='GET'){var old=s.listening[key],nativePath=(item.audio || {})[source.track],nativeRecord=(s.media_positions || {})[nativePath];
        if(fp && nativeRecord && nativeRecord.fingerprint===fp && isFinite(nativeRecord.position) && nativeRecord.position>=0)
          old={audio_fingerprint:fp,position:nativeRecord.position,completed:nativeRecord.completed};
        var changed=old && old.audio_fingerprint!==fp;
        return {kind:source.kind,topic_id:source.topic_id,item_id:source.item_id,track:source.track,title:item.title,
          audio_fingerprint:fp,position:old && !changed && !old.completed?old.position:0,completed:!!(old && !changed && old.completed),state:changed?'audio_changed':'ready'};}
      if(body.audio_fingerprint!==fp || !isFinite(body.position) || body.position<0)bad('音频版本或播放位置无效');
      s.listening[key]=C.copy(body);return s.listening[key];
    }
    if(path==='/api/listening-progress/latest'){var records=vals(s.listening).filter(function(r){return !!(s.topics[r.topic_id] && s.topics[r.topic_id].items[r.item_id]);});
      records.sort(function(a,b){return String(b.saved_at || '').localeCompare(String(a.saved_at || ''));});return records[0] || null;}
    if(path==='/api/search'){var needle=String(q.q || '').toLowerCase(),found=[];
      vals(s.topics).forEach(function(t){vals(t.items).forEach(function(i){var text=vals(i.texts).join('\n');if(needle && text.toLowerCase().indexOf(needle)>=0)
        found.push({topic_id:t.id,topic_name:t.name,item_id:i.id,title:i.title,has_audio:!!(i.audio || {}).podcast,snippet:text.slice(Math.max(0,text.toLowerCase().indexOf(needle)-30),text.toLowerCase().indexOf(needle)+150)});});});
      var size=20,page=Math.max(1,+q.page || 1);return {results:found.slice((page-1)*size,page*size),total:found.length,page:page,pageCount:Math.ceil(found.length/size)};}
    if(path==='/api/jobs')return vals(s.jobs);
    m=path.match(/^\/api\/jobs\/([^/]+)(.*)$/);if(m){var job=s.jobs[m[1]];if(!job)bad('任务不存在');if(method==='POST' && m[2]==='/cancel')job.state='cancelled';return C.copy(job);}
    bad('手机尚不支持此操作：'+method+' '+path);
  }
  C.route=route;C.itemFull=full;C.publicSession=publicSession;C.bankQuery=bankQuery;
  root.MobileCore=C;
  if(typeof module!=='undefined')module.exports=C;
}(this));
