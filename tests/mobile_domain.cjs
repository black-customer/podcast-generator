const assert = require('node:assert/strict');
const C = require('../web/mobile-core.js');
require('../web/mobile-api-core.js');
const now = '2026-10-03T10:00:00+08:00';
const fresh = () => C.createState();
const raw = {title:'Synthetic food chat',messages:[
  {id:'m1',role:'user',text:'What is dietary fiber? Mushrooms has some fiber.'},
  {id:'m2',role:'assistant',text:'Say: Mushrooms have some dietary fiber.'},
]};
const result = {dialogue:[
  {speaker:'A',en:'What would you like to say?',zh:'你想说什么？'},
  {speaker:'B',en:'Mushrooms have some dietary fiber.',zh:'蘑菇含有一些膳食纤维。'},
],notes:[{kind:'explicit_gap',target:'dietary fiber',prompt_zh:'说说蘑菇含有什么。',
  reference_en:'Mushrooms have some dietary fiber.',explanation:'fiber 不可数。',
  sources:[{message_id:'m1',quote:'dietary fiber'}]}]};
let s=fresh();
let item=C.importConversation(s,raw,now);
assert.equal(C.importConversation(s,raw,now).id,item.id);
assert.equal(Object.keys(s.conversations).length,1);
let changed=C.importConversation(s,{...raw,messages:[...raw.messages,
  {id:'m3',role:'user',text:'Thank you.'}]},now);
assert.notEqual(changed.id,item.id);
assert.equal(s.conversations[item.id].messages[0].text,raw.messages[0].text);
assert.throws(()=>C.importConversation(s,{messages:[{role:'system',text:'bad'}]},now));
assert.throws(()=>C.validateResult({...result,notes:[{...result.notes[0],
  sources:[{message_id:'m2',quote:'dietary fiber'}]}]},raw.messages));
assert.throws(()=>C.validateResult({...result,notes:[{...result.notes[0],
  sources:[{message_id:'m1',quote:'invented quote'}]}]},raw.messages));
assert.throws(()=>C.validateResult({...result,notes:[{...result.notes[0],kind:'text_supported_error',
  original_error:{quote:'dietary fiber',issue:'发音不准',correction:'fiber'}}]},raw.messages));
assert.throws(()=>C.validateResult({...result,dialogue:[]},raw.messages));
assert.throws(()=>C.validateResult({...result,dialogue:[{speaker:'A',en:'芝麻 means sesame.',zh:'芝麻。'}]},raw.messages));
assert.throws(()=>C.validateResult({...result,notes:[{...result.notes[0],sources:[{message_id:'setup',quote:'dietary fiber'}]}]},
 [{id:'setup',role:'user',text:'Role: Tutor. Teach dietary fiber.'}]));
assert.equal(C.normalizeMessages([{id:'__proto__',role:'user',text:'Hello'}]).length,1);
C.applyResult(s,item.id,result,now);
let cards=Object.values(s.cards);
assert.equal(cards.length,1);
assert.equal(cards[0].due_date,'2026-10-04');
assert.equal(cards[0].learned_at,null);
C.applyResult(s,item.id,result,now);
assert.equal(Object.keys(s.cards).length,1);
let session=C.startSession(s,'2026-10-04T10:00:00+08:00');
assert.equal(session.cards.length,1);
assert.equal(C.sessionView(s,session.id).current_card.en,undefined);
C.sessionAction(s,session.id,'answered_without_recording','a1');
C.sessionAction(s,session.id,'show_answer','a2');
assert.equal(C.sessionView(s,session.id).current_card.en,cards[0].en);
let attempt=C.submitAttempt(s,session.id,'independent','r1','2026-10-04T10:01:00+08:00');
assert.equal(attempt.next_due_date,'2026-10-07');
assert.deepEqual(C.submitAttempt(s,session.id,'independent','r1','2026-10-04T10:02:00+08:00'),attempt);
assert.equal(s.attempts.length,1);
session=C.startSession(s,'2026-10-07T10:00:00+08:00');
C.sessionAction(s,session.id,'hint','a3');
C.sessionAction(s,session.id,'answered_without_recording','a4');
C.sessionAction(s,session.id,'show_answer','a5');
assert.throws(()=>C.submitAttempt(s,session.id,'independent','r2','2026-10-07T10:01:00+08:00'));
assert.equal(C.submitAttempt(s,session.id,'needs_hint','r2','2026-10-07T10:01:00+08:00').next_due_date,'2026-10-08');
session=C.startSession(s,'2026-10-08T10:00:00+08:00');
C.sessionAction(s,session.id,'show_answer','reveal-first');
C.sessionAction(s,session.id,'answered_without_recording','after-reveal');
assert.throws(()=>C.submitAttempt(s,session.id,'independent','r3','2026-10-08T10:01:00+08:00'));
C.submitAttempt(s,session.id,'needs_hint','r3','2026-10-08T10:01:00+08:00');
assert.equal(C.addDays('2026-12-31',1),'2027-01-01');
assert.equal(C.addDays('2028-02-28',1),'2028-02-29');
assert.equal(C.addDays('2026-03-08',1),'2026-03-09');
const ascii='User: Hello\nAssistant: Hi\nUser: How do I say 糙米?\nAssistant: Brown rice.';
assert.equal(C.parseTranscript(ascii).messages.length,4);
assert.equal(C.parseTranscript('User: First.\nAssistant is a word I just learned.\nAssistant: Okay.').messages.length,2);
assert.equal(C.parseTranscript('## User\nHello.\n## Assistant\nHi.').messages.length,2);
assert.throws(()=>C.parseTranscript('This has no known speakers.'));
assert.equal(C.parseTranscript(JSON.stringify(raw)).messages[0].role,'user');
const arr=[{_1:2},'loaderData',{_3:4},'mapping',{},'current_node','last'];
const g={a:{id:'a',parent:null,message:{id:'a',author:{role:'user'},content:{parts:['Hello']}}},
 b:{id:'b',parent:'a',message:{id:'b',author:{role:'assistant'},content:{parts:[{content_type:'audio_transcription',text:'Hi'}]}}}};
assert.deepEqual(C.messagesFromChatGPT({mapping:g,current_node:'b'}).map(m=>m.text),['Hello','Hi']);
g.a.parent='b'; assert.throws(()=>C.messagesFromChatGPT({mapping:g,current_node:'b'}));
const body={data:{share_info:{share_name:'Sample'},message_snapshot:{message_list:[
 {message_id:'x',user_type:1,index_in_conv:'1',content:JSON.stringify([{content:{text_block:{text:'Hello'}}}])},
 {message_id:'y',user_type:2,index_in_conv:'2',content:JSON.stringify({text:'Hi'})}
]}}};
assert.deepEqual(C.messagesFromDoubao(body).messages.map(m=>m.role),['user','assistant']);
let legacy=fresh();C.migratePack(legacy,{pack_version:1,topics:[{id:'t',name:'Test',items:[{id:'i'}]}]},
 [{topic_id:'t',id:'i',texts:{question:'A question',original_answer:'Original'},audio:{},meta:{}}]);
assert.equal(legacy.topics.t.items.i.texts.original_answer,'Original');
legacy.topics.t.items.i.progress.stage='summary';
C.migratePack(legacy,{pack_version:2,topics:[{id:'t',name:'Test'}]},[
 {topic_id:'t',id:'i',texts:{question:'A question',original_answer:'Original'},
  audio:{podcast:'/new-bytes.mp3'},audioFingerprints:{podcast:'new-bytes'},meta:{}}]);
assert.equal(legacy.topics.t.items.i.audio.podcast,'/new-bytes.mp3');
assert.equal(legacy.topics.t.items.i.progress.stage,'summary');
assert.throws(()=>C.migratePack(legacy,{pack_version:99,topics:[]},[]));
const backup=C.exportExchange(s);assert.equal(JSON.stringify(backup).includes('api_key'),false);
assert.throws(()=>C.importExchange(s,{...backup,version:99},now));
let before=JSON.stringify(s.attempts); C.importExchange(s,backup,now);assert.equal(JSON.stringify(s.attempts),before);
let duplicateGoal=C.importConversation(s,{title:'Second scene',messages:[{id:'n1',role:'user',text:'What is dietary fiber?'}]},now);
C.applyResult(s,duplicateGoal.id,{...result,notes:[{...result.notes[0],reference_en:'This food has dietary fiber.',sources:[{message_id:'n1',quote:'dietary fiber'}]}]},now);
assert.equal(Object.keys(s.cards).length,1);
let draft=C.saveDraft(s,'q','Q','answer','api',0);
assert.equal(draft.revision,1);assert.throws(()=>C.saveDraft(s,'q','Q','stale','api',0));
assert.equal(C.saveDraft(s,'q','Q','new','api',1).answer,'new');
assert.throws(()=>C.openState({version:99}));
assert.equal(C.splitMessages(raw.messages,40).flat().length,2);
console.log('Mobile domain regressions passed');
const dbDoc={data:{share_info:{share_name:'Synthetic quotes'},message_snapshot:{message_list:[
 {message_id:'one',index_in_conv:1,user_type:2,content:'Hello'},
 {message_id:'two',index_in_conv:2,user_type:1,content:'Hi'}]}}};
const dbArgs=JSON.stringify(['ignored',[{routerDataFnArgs:[JSON.stringify(dbDoc)]}]]).replace(/&/g,'&amp;').replace(/'/g,'&#39;');
assert.equal(C.parseDoubaoPage("<script data-fn-args='"+dbArgs+"'></script>").messages.length,2);
const dbDirect=JSON.stringify(['ignored','',dbDoc]).replace(/'/g,'&#39;');
assert.equal(C.parseDoubaoPage("<script data-fn-args='"+dbDirect+"'></script>").messages.length,2);
const linkedState=fresh(),firstLink=C.importConversation(linkedState,{...raw,source_url:'https://chatgpt.com/share/synthetic',provider:'chatgpt'},now);
const updatedLink=C.importConversation(linkedState,{...raw,source_url:'https://chatgpt.com/share/synthetic',provider:'chatgpt',messages:raw.messages.concat([{id:'m3',role:'user',text:'How do I say whole grain?'}])},now);
assert.equal(updatedLink.previous_import_id,firstLink.id);
assert.equal(linkedState.conversations[firstLink.id].messages.length,2);
assert.equal(C.parseTranscript({messages:[{role:'user',content:[{text:'Hello'}]},{role:'assistant',content:'Hi'}]}).messages[0].text,'Hello');
const bank={questions:[{id:'q',text:'Your work?',part:1}],topics:[],sets:[]};
let device=fresh();let job=C.route(device,'POST','/api/generation-requests',
  {question_id:'q',answer:'I work in a school.',mode:'api'},now,bank);
assert.equal(job.kind,'ielts');
assert.equal(C.route(device,'GET',`/api/topics/${job.topic_id}/items/${job.item_id}`,{},now,bank).original_answer,'I work in a school.');
assert.equal(C.route(device,'GET','/api/bank/questions?answer_status=answered',{},now,bank).total,1);
const filterBank={questions:[{id:'q1',text:'Work?',part:1,topic_id:'work'},
 {id:'q2',text:'Food?',part:1,topic_id:'food'}],topics:[{id:'work',name_en:'Work or studies'},{id:'food',name_en:'Food'}],
 sets:[{id:'s1',start_month:9,end_month:12,question_ids:['q2']}]};
assert.equal(C.bankQuery(device,filterBank,{set_filter:'core'}).items[0].id,'q1');
assert.equal(C.bankQuery(device,filterBank,{set_filter:'s1'}).total,1);
let di=device.topics[job.topic_id].items[job.item_id];di.audio={podcast:'/native/old.m4a'};di.audioFingerprints={podcast:'old-bytes'};
const listening={kind:'item',topic_id:job.topic_id,item_id:job.item_id,track:'podcast',
 audio_fingerprint:'old-bytes',position:17,duration:50,completed:false};
C.route(device,'PUT','/api/listening-progress',listening,now,bank);
let listenUrl=`/api/listening-progress?kind=item&topic_id=${job.topic_id}&item_id=${job.item_id}&track=podcast`;
assert.equal(C.route(device,'GET',listenUrl,null,now,bank).position,17);
device.media_positions={'/native/old.m4a':{position:33,duration:50,completed:false,fingerprint:'old-bytes'}};
assert.equal(C.route(device,'GET',listenUrl,null,now,bank).position,33);
device.media_positions['/native/old.m4a'].fingerprint='different-audio';
assert.equal(C.route(device,'GET',listenUrl,null,now,bank).position,17);
di.audioFingerprints.podcast='new-bytes';
assert.equal(C.route(device,'GET',listenUrl,null,now,bank).position,0);
assert.equal(C.route(device,'GET',listenUrl,null,now,bank).state,'audio_changed');
let itemUrl=`/api/topics/${job.topic_id}/items/${job.item_id}`;
C.route(device,'PATCH',itemUrl,{original_answer:'A revised original answer.'},now,bank);
assert.equal(C.route(device,'GET',itemUrl,null,now,bank).original_answer,'A revised original answer.');
di.texts.podcast_text='A: Food?\nB: Mushrooms have fiber.';
let prep=C.route(device,'POST',itemUrl+'/study/prepare',{},now,bank);
assert.equal(prep.kind,'study');
assert.equal(C.route(device,'GET',itemUrl+'/study',{},now,bank).status,'preparing');
assert.throws(()=>C.openState({version:1,topics:{}}));
const texts={question:'Food?',original_answer:'Mushrooms has fiber.',natural_english:'Mushrooms have fiber.',
  podcast_text:'A: Food?\nB: Mushrooms have fiber.',podcast_script:'A: Food?\nB: Mushrooms have fiber.'};
const ir={...texts,dialogue:[{speaker:'A',en:'Food?',zh:'饮食？'},{speaker:'B',en:'Mushrooms have fiber.',zh:'蘑菇含纤维。'}]};
assert.equal(C.validateIeltsResult(ir,texts.original_answer).dialogue.length,2);
assert.throws(()=>C.validateIeltsResult({...ir,podcast_script:'A: A different question?\nB: Wrong.'},texts.original_answer));
let material={complete_chinese:'蘑菇含纤维。',sentences:[{zh:'蘑菇含纤维。',en:'Mushrooms have fiber.',explanation:'主谓一致',usage:'have fiber'}]};
assert.equal(C.validateStudyMaterial(material,texts).sentences.length,1);
let phoneExchange=C.exportExchange(device);
let exchangedItem=phoneExchange.topics[job.topic_id].items[job.item_id];
assert.equal(exchangedItem.progress,undefined);
assert.equal(Object.keys(exchangedItem.audio || {}).length,0);
exchangedItem.texts={...texts,original_answer:'A revised original answer.'};
exchangedItem.dialogue=ir.dialogue;exchangedItem.material=material;
C.importExchange(device,phoneExchange,now);
assert.equal(device.topics[job.topic_id].items[job.item_id].texts.podcast_text,texts.podcast_text);
assert.equal(device.topics[job.topic_id].items[job.item_id].progress.stage,'before');
assert.throws(()=>C.validateStudyMaterial({...material,sentences:[{...material.sentences[0],en:'Invented.'}]},texts));
assert.throws(()=>C.validateStudyMaterial({...material,sentences:[{...material.sentences[0],original_error:{quote:'other quote',issue:'grammar',correction:'fix'}}]},texts));
assert.equal(C.splitAudioLine({speaker:'A',en:'Hello there. Welcome back.',zh:'你好，欢迎回来。'},14).map(x=>x.en).join(' '),'Hello there. Welcome back.');
