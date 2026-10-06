const assert = require('node:assert/strict');
const C = require('../web/mobile-core.js');
require('../web/mobile-api-core.js');
const now = '2026-10-06T10:00:00+08:00';
const state = C.createState();
const texts = {question:'Where did you grow up?',original_answer:'我在河边长大。',
  natural_english:'I grew up by the river.',podcast_text:'B: I grew up by the river.',
  podcast_script:'B: I grew up by the river.'};
function item(id, extra={}) {
  return {id,title:texts.question,texts:{...texts},audio:{podcast:`/${id}.m4a`},
    material:C.validateStudyMaterial({complete_chinese:'我在河边长大。',sentences:[
      {zh:'我在河边长大。',en:'I grew up by the river.',explanation:'成长经历',usage:'grew up'}]},texts),
    timelines:{podcast:{lines:[{role:'b',text:'I grew up by the river.',start:2,end:5}]}},...extra};
}
state.topics.t={id:'t',name:'家乡',items:{a:item('a'),b:item('b')}};
const before = JSON.stringify(state);
const overview = C.route(state,'GET','/api/study/today',{},now,{});
assert.equal(JSON.stringify(state),before,'读取今日入口不得创建学习进度');
if(process.argv[2]==='read-only') process.exit(0);
assert.equal(typeof C.homePracticeCandidates,'function');
let rows=C.homePracticeCandidates(state,overview);
assert.equal(rows.length,2);
assert.equal(rows[0].zh,'我在河边长大。');
assert.equal(rows[0].audio.start,2);
assert.equal(rows[0].audio.end,5);
assert.equal(rows[0].audio.mode,'measured');
assert.equal(JSON.stringify(state),before,'选句不得改变领域状态');
state.topics.t.items.a.progress={stage:'dictation',sentence_index:0,facts:{},recordings:[]};
state.cards.due={id:'due',kind:'ielts',topic_id:'t',item_id:'b',sentence_index:0,
  zh:'我在河边长大。',en:'I grew up by the river.',
  source_fingerprint:state.topics.t.items.b.material.source_fingerprint,due_date:'2026-10-05'};
state.sessions.s={id:'s',state:'active',cards:['due'],current_index:0};
rows=C.homePracticeCandidates(state,C.route(state,'GET','/api/study/today',{},now,{}));
assert.equal(rows[0].item_id,'b','当前口答优先');
assert.equal(rows[1].item_id,'a','当前学习其次');
assert.equal(rows.length,2,'同一句不得因到期和材料来源重复出现');
state.sessions={};
rows=C.homePracticeCandidates(state,C.route(state,'GET','/api/study/today',{},now,{}));
assert.equal(rows[0].item_id,'a');
const many=C.createState();many.topics.t={id:'t',name:'排序',items:{}};
for(let n=0;n<12;n++){
  const name=String(n).padStart(2,'0');many.topics.t.items[name]=item(name);
  if(n>0)many.cards[name]={id:name,kind:'ielts',topic_id:'t',item_id:name,sentence_index:0,
    zh:'我在河边长大。',en:'I grew up by the river.',due_date:'2026-10-05',
    source_fingerprint:many.topics.t.items[name].material.source_fingerprint};
}
rows=C.route(many,'GET','/api/study/today',{},now,{}).home_practice;
assert.equal(rows[rows.length-1].item_id,'00','超过10个到期句仍应优先于普通材料');
state.topics.t.items.a.material.source_fingerprint='obsolete';
state.topics.t.items.b.audio={};
assert.equal(C.homePracticeCandidates(state,{due_preview:[]}).length,0);
state.topics={};state.cards={};
state.conversations.c={id:'c',title:'周末',audio:'/chat.m4a',duration:9,notes:[],
  dialogue:[{speaker:'A',zh:'周末做什么？',en:'What do you do at weekends?'},
    {speaker:'B',zh:'我和家人一起散步。',en:'I walk with my family.'}],
  timeline:{lines:[{text:'I walk with my family.',start:3,end:6}]}};
rows=C.homePracticeCandidates(state,{});
assert.equal(rows.length,1,'只取已配对的回答，不把提问当答案');
assert.equal(rows[0].en,'I walk with my family.');
assert.equal(rows[0].audio.url,'/chat.m4a');
assert.equal(rows[0].audio.start,3);
state.cards.missing={id:'missing',kind:'conversation',conversation_id:'c',zh:'音频中没有这一句。',en:'This is not spoken.'};
rows=C.homePracticeCandidates(state,{due_preview:[state.cards.missing]});
assert.equal(rows.length,1,'重点英文没有出现在音频源对话中，不得拿整段音频冒充答案');
state.conversations.c.timeline={lines:[]};
rows=C.homePracticeCandidates(state,{});
assert.equal(rows[0].audio.mode,'estimated');
assert.match(rows[0].audio.reason,/完整/);
state.conversations.c.dialogue[1].zh='';
assert.equal(C.homePracticeCandidates(state,{}).length,0);
console.log('home practice domain: PASS');
