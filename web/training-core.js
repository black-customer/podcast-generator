/* 与 server/training.py 对应的纯领域规则；Rhino 与 Node 共用，无网络与密钥。 */
(function(root){
  'use strict';
  function cp(x){return JSON.parse(JSON.stringify(x));}
  function bad(m){throw new Error(m);}
  function initial(old,fp){var done=old.stage==='summary';return {version:2,fingerprint:fp,
    phase:done?'summary':'before',status:done?'awaiting_review':'unstarted',legacy_completed:done,
    sentences:{},focus:[],index:0,whole_hint:false,successes:0,due_date:null,last_success_day:null,
    attempts:[],receipts:{},paused:false,elapsed_sec:0,inputs:cp(old.training_inputs || {answer:'',intent:'',feedback:''}),notes:''};}
  function indices(a,rows){var seen={};if(!Array.isArray(a) || a.length>rows.length)bad('练习句子序号错误');
    a.forEach(function(n){if(typeof n!=='number' || n%1 || n<0 || n>=rows.length || seen[n])bad('练习句子序号错误');seen[n]=true;});}
  function add(day,n){var a=day.split('-');return new Date(Date.UTC(+a[0],+a[1]-1,+a[2]+n)).toISOString().slice(0,10);}
  function reduce(state,p,m,now,part){
    if(p.version!==2 || p.fingerprint!==state.fingerprint)bad('训练版本已变化，请重新打开；原记录保留');
    var aid=p.action_id,action=p.action;if(typeof aid!=='string' || !aid.length || aid.length>128)bad('缺少有效动作标识');
    if(['__proto__','constructor','prototype'].indexOf(aid)>=0)bad('动作标识无效');
    if(Object.prototype.hasOwnProperty.call(state.receipts,aid))return cp(state);var s=cp(state),rows=m.sentences || [],day=now.slice(0,10),phase=s.phase,previous={},n,f,rating,focus,weak;
    if(action==='undo'){if(!s.undo)bad('没有可撤销的操作');var receipts=s.receipts;s=s.undo;s.receipts=receipts;}
    else {
      Object.keys(s).forEach(function(k){if(k!=='undo' && k!=='receipts')previous[k]=cp(s[k]);});
      if(action==='start'){
        if(phase!=='before')bad('当前步骤不能重新创建首答');s.phase='inputs';s.status='training';s.baseline_unexposed=!!p.unexposed;s.baseline_recording_id=p.recording_id || null;
      }else if(action==='inputs'){
        if(phase!=='inputs')bad('请先完成首答');['answer','intent','feedback'].forEach(function(k){var v=p[k] || '';if(typeof v!=='string' || v.length>30000)bad('原回答或补充内容过长');s.inputs[k]=v;});s.phase='understand';
      }else if(action==='understand'){
        if(phase!=='understand' || !rows.length)bad('请先准备并理解学习材料');focus=p.focus;
        if(focus===undefined){focus=[];rows.forEach(function(r,i){if(r.original_error && focus.length<3)focus.push(i);});if(!focus.length)focus=rows.slice(0,3).map(function(r,i){return i;});}
        indices(focus,rows);s.focus=focus;s.index=0;s.phase=focus.length?'sentence':'outline';focus.forEach(function(i){var f=s.sentences[i] || (s.sentences[i]={});f.hint=false;f.visible=false;});
      }else if(['reveal','hide','dictation','sentence'].indexOf(action)>=0){
        n=p.index;indices([n],rows);if(phase!=='sentence' || s.focus[s.index]!==n)bad('当前不在该句练习阶段');f=s.sentences[n] || (s.sentences[n]={});
        if(action==='reveal'){f.hint=true;f.visible=true;}
        else if(action==='hide')f.visible=false;
        else if(action==='dictation'){if(typeof p.draft!=='string' || p.draft.length>10000)bad('默写草稿过长');f.draft=p.draft;f.written_passed=p.passed===true;}
        else {rating=p.rating;if(['independent','needs_hint','unable'].indexOf(rating)<0 || (rating==='independent' && f.hint))bad('用过答案或提示后不能记为独立说出');
          if(f.visible)bad('请先隐藏英文，再尝试口答');f.oral=rating;f.alternative=p.alternative===true;s.index++;if(s.index>=s.focus.length)s.phase='outline';}
      }else if(action==='outline_done'){if(phase!=='outline')bad('请先完成局部练习');s.phase='whole';s.whole_hint=false;
      }else if(action==='review'){if(['summary','whole'].indexOf(phase)<0)bad('请先完成当前训练');s.phase='whole';s.whole_hint=false;
      }else if(action==='refocus'){if(phase!=='summary')bad('请先结束当前回答');s.phase='understand';s.status='training';
      }else if(action==='whole_hint'){if(phase!=='whole')bad('当前不在整题回答阶段');s.whole_hint=true;
      }else if(action==='whole'){
        rating=p.rating;if(phase!=='whole' || ['independent','needs_hint','unable'].indexOf(rating)<0)bad('请先独立完成整题回答');
        if(rating==='independent' && s.whole_hint)bad('用过提示不能记为独立完成');
        if(!p.recording_id && p.no_recording!==true)bad('请先保存录音，或明确选择无录音自评');
        if(part===3 && rating==='independent' && !p.followup_completed)bad('请先完成相关追问');
        weak=p.weak_indices || [];indices(weak,rows);var delayed=s.due_date && day>=s.due_date;
        if(rating==='independent'){
          if(day!==s.last_success_day && (delayed || !s.due_date)){if(delayed)s.successes++;s.last_success_day=day;s.due_date=add(day,[1,3,7,14,30][Math.min(s.successes,4)]);}
          s.phase='summary';s.status=s.successes>=2?'mastered':'awaiting_review';
        }else {s.successes=0;s.due_date=null;s.last_success_day=null;s.status='training';s.phase=rows.length?'sentence':'understand';s.index=0;
          s.focus=weak.length?weak:rows.slice(0,3).map(function(r,i){return i;});s.focus.forEach(function(i){var f=s.sentences[i] || (s.sentences[i]={});f.hint=false;f.visible=false;});}
        s.attempts.push({id:aid,created_at:now,rating:rating,hint_used:state.whole_hint,recording_id:p.recording_id || null,
          no_recording:p.no_recording===true,followup_completed:p.followup_completed===true,next_due_date:s.due_date,weak_indices:weak});
      }else if(action==='pause'){if(typeof p.paused!=='boolean')bad('暂停状态错误');s.paused=p.paused;
      }else if(action==='activity'){
        if(typeof p.seconds!=='number' || !isFinite(p.seconds) || p.seconds<0 || p.seconds>120)bad('练习用时错误');s.elapsed_sec+=p.seconds;
        var notes=p.notes===undefined?s.notes:p.notes;if(typeof notes!=='string' || notes.length>10000)bad('准备笔记过长');s.notes=notes;
      }else bad('未知训练动作');
      if(['activity','dictation','reveal','hide','whole_hint'].indexOf(action)<0)s.undo=previous;
    }
    s.receipts[aid]=true;s.updated_at=now;return s;
  }
  function context(C,s,i,bank){
    var m=i.material || {},old=i.progress || {},fp=C.hash(JSON.stringify([m,C.sourceFingerprint(i.texts || {}),i.audioFingerprints || {},i.audio || {}]));
    if(old.training && old.training.version!==2)bad('训练记录版本不受支持，请保留原件');
    var state=old.training && old.training.fingerprint===fp?cp(old.training):initial(old,fp),part=(i.meta || {}).ielts_part || 1;
    if(old.training && old.training.awaiting_material && old.training.fingerprint!==fp){state=cp(old.training);state.fingerprint=fp;state.awaiting_material=!i.material;delete state.undo;}
    (bank.questions || []).some(function(q){if(q.text===(i.texts || {}).question){part=q.part;return true;}return false;});
    return {state:state,material:m,material_status:i.material?'ready':(i.meta || {}).study_status || 'needs_input',
      part:+part,item:cp(i.texts || {}),recordings:cp(old.recordings || []),history:cp(old.training_history || []),changed:!!(old.training && old.training.fingerprint!==fp)};
  }
  function overview(C,s,bank,now){var rows=[];C.values(s.topics).forEach(function(t){C.values(t.items).forEach(function(i){
    var ctx=context(C,s,i,bank);if(ctx.state.status!=='unstarted')rows.push({topic_id:t.id,item_id:i.id,question:(i.texts || {}).question,part:ctx.part,state:ctx.state});
  });});rows.sort(function(a,b){return String(b.state.updated_at || '').localeCompare(a.state.updated_at || '');});return {version:2,items:rows,today:now.slice(0,10)};}
  var T={initial:initial,reduce:reduce,context:context,overview:overview};root.TrainingCore=T;if(typeof module!=='undefined')module.exports=T;
}(this));
