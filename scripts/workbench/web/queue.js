'use strict';
Object.assign(statusLabels,{assigned:'正在派发',partial:'部分完成'});
const inFlight=['queued','running','stopping'];
const baseCreateQueue=renderCreate;
renderCreate=function(){
  baseCreateQueue();const f=$('#create-form');if(!f)return;
  const people=state.config.people,oldPicker=$('.person-picker'),oldCount=$('#count-input');
  const fallback=createDraft.person||state.config.defaultPerson||people[0]?.id;
  const selections=createDraft.people||[{id:fallback,count:Number(createDraft.count)||1}];
  const preferenceMap={...(createDraft.videoPreferenceMap||{})};let slots=[];
  if(!Object.keys(preferenceMap).length){let n=0;for(const p of selections)for(let i=0;i<p.count;i++)preferenceMap[p.id+':'+i]=createDraft.videoPreferences?.[n++]||'';}
  const label=oldPicker.closest('.form-group').querySelector('.label-row>label');if(label)label.outerHTML='<span class="field-label">出镜数字人与每人数量</span>';
  oldPicker.outerHTML=`<fieldset class="batch-people"><legend class="sr-only">选择出镜数字人与每人制作数量</legend>${people.map(p=>{const s=selections.find(x=>x.id===p.id);return `<div class="batch-person ${s?'is-selected':''}"><label class="batch-person-choice"><input type="checkbox" data-queue-person="${E(p.id)}" aria-label="选择${E(p.name)}" ${s?'checked':''}>${p.hasPortrait?`<img src="/media/person/${E(p.id)}" alt="">`:icon('person')}<span><strong>${E(p.name)}</strong><small>${E(p.social_media_name||'待补齐署名')}</small></span></label><div class="batch-person-count"><label class="sr-only" for="quantity-${E(p.id)}">${E(p.name)}制作数量</label><select data-search="false" id="quantity-${E(p.id)}" data-queue-count="${E(p.id)}" ${s?'':'disabled'}>${Array.from({length:20},(_,i)=>i+1).map(n=>`<option value="${n}" ${n===(s?.count||1)?'selected':''}>${n} 条</option>`).join('')}</select></div></div>`;}).join('')}</fieldset>`;
  oldCount.closest('.form-group').hidden=true;oldCount.closest('.form-row').classList.add('batch-title-row');
  const capturePreferences=()=>f.querySelectorAll('[data-slot-key]').forEach(t=>preferenceMap[t.dataset.slotKey]=t.value);
  const chosen=()=>[...f.querySelectorAll('[data-queue-person]:checked')].map(x=>({id:x.dataset.queuePerson,count:Number(f.querySelector('[data-queue-count="'+CSS.escape(x.dataset.queuePerson)+'"]').value)}));
  const paint=()=>{const selected=chosen();slots=[];for(const p of selected){const person=people.find(x=>x.id===p.id);for(let i=0;i<p.count;i++)slots.push({key:p.id+':'+i,name:person.name,number:i+1});}f.querySelectorAll('[data-queue-person]').forEach(x=>{const row=x.closest('.batch-person');row.classList.toggle('is-selected',x.checked);row.querySelector('select').disabled=!x.checked;});const area=$('#video-preference-fields');area.innerHTML=slots.map((x,i)=>`<div class="form-group"><label class="field-label" for="video-pref-${i}">${E(x.name)} · 本批第 ${i+1} 条</label><textarea id="video-pref-${i}" data-video-preference="${i}" data-slot-key="${E(x.key)}" rows="2" placeholder="留空继承整批偏好。可指定这一条的重点，封面、标题、口播和镜头会一起适配。">${E(preferenceMap[x.key]||'')}</textarea></div>`).join('');let preview=$('#batch-order-preview');if(!preview){area.closest('details').insertAdjacentHTML('beforebegin','<div id="batch-order-preview" class="batch-order-preview"></div>');preview=$('#batch-order-preview');}preview.innerHTML=`<strong>本批次 ${slots.length} 条</strong><p>${selected.map(x=>E(people.find(p=>p.id===x.id).name)+' '+x.count+' 条').join(' → ')||'先选择出镜人物'}</p><small>按上方顺序追加到队尾，同一时刻只制作一条。</small>`;f.querySelector('[type=submit]').innerHTML=icon('plus')+` 提交 ${slots.length} 条，加入队尾 `+icon('arrow-right');createDraft.people=selected;createDraft.person=selected[0]?.id;createDraft.count=slots.length;createDraft.videoPreferenceMap=preferenceMap;createDraft.videoPreferences=slots.map(x=>preferenceMap[x.key]||'');};
  paint();const oldInput=f.oninput;
  f.oninput=e=>{capturePreferences();oldInput(e);createDraft.people=chosen();createDraft.person=createDraft.people[0]?.id;createDraft.videoPreferenceMap=preferenceMap;if(e.target.matches('[data-queue-person],[data-queue-count]'))paint();createDraft.count=slots.length;createDraft.videoPreferences=slots.map(x=>preferenceMap[x.key]||'');saveDraft();};
  const note=f.querySelector('.inline-note');if(note&&hasServices()&&hasPerson())note.textContent=state.config.agent.mode==='local'?'提交后由本机工作台按顺序制作。':'提交后会保存在本地队列。Agent 连接后按顺序执行，不需要逐条点开始。';
  f.onsubmit=async e=>{e.preventDefault();$('#create-error').textContent='';capturePreferences();await busy(f.querySelector('[type=submit]'),async()=>{try{const selected=chosen();if(!selected.length)throw new Error('请选择至少一位出镜数字人');const values={...Object.fromEntries(new FormData(f)),people:selected,person:selected[0].id,count:slots.length,music:f.elements.music.checked,videoPreferences:slots.map(x=>preferenceMap[x.key]||'')};await api('/api/draft',{...values,videoPreferenceMap:preferenceMap});const task=await api('/api/tasks',values);await api('/api/tasks/'+task.id+'/start',{});await refresh(false);setRoute('task/'+task.id);}catch(err){$('#create-error').textContent=err.message;}});};
};
function queueButton(row,options={}){
  if(row.stopReason==='timeout'&&!row.settled)return '<span class="subtle">超时，等待执行者退出</span>';
  if(['completed','cancelled','timed_out'].includes(row.status)&&row.settled)return '';
  const atHead=row.id===state.queue.headId;
  const inspect=options.inspect!==false&&!row.settled&&atHead?`<button class="text-button" data-action="inspect-progress" data-id="${row.id}">查看状态诊断</button>`:'';
  const cancel=`<button class="text-button" data-action="queue-cancel" data-id="${row.id}">${row.settled?'取消此条':'请求停止'}</button>`;
  if(['completed','stopping','cancelled','timed_out'].includes(row.status)){
    const cancelling=['stopping','cancelled'].includes(row.status);
    const pending=row.recoveryRequested;
    const confirm=atHead&&row.kind==='video'&&!row.settled?`<button class="text-button" data-action="queue-recover" data-id="${row.id}" ${pending?'disabled':''}>${pending?'已请求，等待 Agent 确认':'请求确认结束'}</button>`:'';
    return (cancelling?'<button class="text-button" disabled aria-label="取消已提交，等待执行者退出确认">取消中</button>':'<span class="subtle">制作完成，等待执行者退出</span>')+confirm+inspect;
  }
  if(['failed','interrupted'].includes(row.status))return `<button class="secondary" data-action="queue-retry" data-id="${row.id}" ${!row.settled||!atHead?'disabled':''}>${!row.settled?'等待当前制作结束':!atHead?'等待前序处理':'重试当前条'}</button>`+cancel+inspect;
  if(row.answerPending)return '<span class="subtle">补充已保存，等待当前制作结束</span>'+inspect;
  if(row.status==='needs_input')return `<a class="secondary" href="#task/${row.taskId}">补充信息</a>`+cancel+inspect;
  return row.status==='queued'?`<button class="text-button" data-action="queue-cancel" data-id="${row.id}">取消排队</button>`:cancel+inspect;
}
function queueStatusLabel(row){
  if(row.stopReason==='timeout'&&!row.settled)return '超时，正在停止';
  if(!row.settled&&['cancelled','stopping'].includes(row.status))return '取消中';
  if(!row.settled&&row.status==='completed')return '待结束确认';
  return statusLabels[row.status]||row.status;
}
function queueDisplayMessage(row) {
  if(row.status==='cancelled')return row.settled?'已取消，执行者已结束；已有文件保留':'取消已提交，等待执行者退出确认；已有文件保留';
  if(row.status==='stopping')return '取消已提交，正在等待停止检查点与执行者退出确认';
  if(row.status==='queued'&&row.id===state.queue?.headId&&['video','planning'].includes(row.kind)&&!(state.config.agent.canDispatch??(state.config.agent.state==='connected')))return state.config.agent.mode==='local'?'等待启用独立制作，任务已保存在原队列。':'等待 '+(state.config.agent.label||'WorkBuddy')+' 重新连接接单；任务已保存，顺序不变';
  if(row.activityMessage)return row.activityMessage;
  if(row.message!=='正在检查当前制作状态；确认结束前不会开始下一条')return row.message||'';
  const task=state.tasks.find(t=>t.id===row.taskId),prefix='第 '+(row.index+1)+' 条 · ';
  const report=task?.events?.slice().reverse().find(e=>e.message.startsWith(prefix));
  return report?report.message.slice(report.message.indexOf('：')+1):'当前执行位仍由这条视频占用，最新状态见诊断记录';
}
function batchProgress(task){
  const rows=task.queueItems||[];
  if(!rows.length)return Number(task.progress)||0;
  const planning=task.planning,credit=planning?(planning.status==='completed'?2:Math.min(2,Math.max(0,planning.phase||0))):0;
  return Math.floor(rows.reduce((sum,row)=>sum+Math.max(credit,row.phase||0),0)/rows.length/6*100);
}
function connectionHelp(row){
  if(!row||row.status!=='queued'||!['video','planning'].includes(row.kind)||(state.config.agent.canDispatch??(state.config.agent.state==='connected')))return '';
  if(state.config.agent.mode==='local')return `<p class="queue-connection">任务会在配置完成后按原顺序运行。<a class="text-button" href="#settings">配置模型 ${icon('arrow-right')}</a></p>`;
  return `<p class="queue-connection">等待 ${E(state.config.agent.label||'WorkBuddy')} 接单。<button class="text-button" data-action="check-agent">请求恢复连接</button><a class="text-button" href="#settings">连接方式 ${icon('arrow-right')}</a></p>`;
}
function queueItemTitle(row) {
  return row.kind === 'planning' ? '整批素材整理与统一策划' : row.kind === 'cover' ? '更新视频首帧' : E(row.personName) + ' · 本批第 ' + (row.index + 1) + ' 条';
}
function queueItemLink(row) {
  return row.kind === 'cover' ? '#video/' + row.taskId + '/' + row.index + '/cover' : '#task/' + row.taskId;
}
function queuePanel() {
  const q = state.queue;
  if (!q) return '';
  const pending = q.items.filter(x => x.position), head = pending[0];
  if (!head) return '<div class="queue-idle">' + icon('check') + '<span>队列空闲，新任务会从这里按顺序开始。</span></div>';
  const title = q.paused ? '队首需要处理' : head.status === 'stopping' ? '正在停止当前制作' : ['completed','cancelled'].includes(head.status) && !head.settled ? '等待当前制作结束确认' : head.status === 'queued' ? '等待按顺序开始' : '正在执行队首';
  const label = q.paused ? '队列暂停' : head.status === 'stopping' ? '等待停止' : ['completed','cancelled'].includes(head.status) && !head.settled ? '等待确认' : q.busy ? '执行中' : '已排队';
  return `<section class="queue-panel" aria-label="制作队列">
    <div class="queue-panel-heading"><div><h2>${title}</h2><p>当前队列 ${pending.length} 条 · 按提交顺序 · 同时运行 1 条</p></div>${badge(label,q.paused?'warn':'neutral')}</div>
    <div class="queue-head">
      <span class="queue-number" aria-label="当前队列第 ${head.position} 位">第 ${head.position} 位</span>
      <strong class="queue-item-title">${queueItemTitle(head)}</strong>
      <div class="queue-actions">${queueButton(head)}</div>
      <div class="queue-item-description"><p>${E(queueDisplayMessage(head))}</p><a class="queue-batch-link" href="${queueItemLink(head)}">${E(head.title)} ${icon('arrow-right')}</a>${!head.settled?'<small>'+(head.kind==='cover'?'首帧更新结束后，会继续下一条。':'当前制作完全结束并确认后，会继续下一条。')+'</small>':''}</div>
    </div>
    ${pending.length>1?`<details class="queue-next"><summary>查看后面的 ${pending.length-1} 条</summary>${pending.slice(1).map(x=>`<div class="queue-next-item"><span class="queue-number" aria-label="当前队列第 ${x.position} 位">第 ${x.position} 位</span><div class="queue-next-info"><a href="${queueItemLink(x)}">${queueItemTitle(x)}</a><span>${E(x.title)}</span></div><div class="queue-actions">${queueButton(x)}</div></div>`).join('')}</details>`:''}
    ${typeof productionDiagnosticHtml==='function'?productionDiagnosticHtml(head):''}
    ${connectionHelp(head)}
  </section>`;
}
const tasksBeforeQueue=renderTasks;
renderTasks=function(){tasksBeforeQueue();main.querySelector('.page-heading').insertAdjacentHTML('afterend','<div id="queue-panel-area">'+queuePanel()+'</div>');};
const taskControlsBeforeQueue=taskControls;
function taskAnswerRow(t) {
  if(t.planning&&t.planning.id===t.activeItemId)return t.planning;
  return t.queueItems?.find(x=>x.id===t.activeItemId);
}
function taskAnswerNotice(t) {
  const row=taskAnswerRow(t);
  if(t.status==='needs_input'&&row?.answerPending)
    return '<p class="inline-note" role="status">答复已保存。当前执行者结束后，会按原序号继续。</p>';
  if(t.status!=='queued'||!row?.answerSaved)return '';
  const agent=state.config.agent;
  if(agent.mode==='local')return `<p class="inline-note" role="status">答复已保存。${agent.canDispatch?'本机工作台会按原序号继续。':'<a href="#settings">启用独立制作</a>后会按原序号继续。'}</p>`;
  if(agent.canDispatch??(agent.state==='connected'))
    return '<p class="inline-note" role="status">答复已保存，等待 Agent 领取原任务。</p>';
  const label=E(agent.label||'Agent');
  const open=agent.host==='workbuddy'?'<button type="button" class="text-button" data-action="open-workbuddy">打开 WorkBuddy</button>':'';
  return `<div class="inline-note"><p role="status">答复已保存，任务仍在原队首。等待 ${label} 重新接单。</p><p>把连接指令发到原对话，Agent 接单后会读取已保存的答复。</p><button type="button" class="secondary" data-action="copy-agent">复制连接指令</button> ${open}</div>`;
}
taskControls=function(t){
  if(t.queueItems?.length){
    if(t.status==='needs_input')return taskAnswerNotice(t)||taskControlsBeforeQueue(t);
    if(inFlight.includes(t.status))return `${taskAnswerNotice(t)}<button class="danger-button" data-action="cancel-task" data-id="${t.id}">取消本批剩余制作</button><p class="form-help">当前条需等确认停止；本批尚未开始的条目直接取消，已有成品保留。</p>`;
    if(['failed','interrupted'].includes(t.status))return `<button class="primary" data-action="start-task" data-id="${t.id}">继续队首这一条</button>`;
    return '';
  }
  if(t.status==='draft')return `<button class="primary" data-action="start-task" data-id="${t.id}">提交到队尾 ${icon('arrow-right')}</button>`;
  return taskControlsBeforeQueue(t);
};
function batchCoverItems(t) {
  return (state.queue?.items||[]).filter(x=>x.kind==='cover'&&x.taskId===t.id);
}
function batchCoverOperations(t) {
  const rows=batchCoverItems(t);if(!rows.length)return '';
  const pending=rows.filter(x=>x.position).length;
  return `<div class="batch-cover-operations"><div class="section-heading"><h3>成品修改</h3><span>${pending?pending+' 项待处理':'修改记录'}</span></div><p class="form-help">封面首帧更新也按提交顺序执行，不计入上方的视频条数。</p>${rows.map(x=>`<div class="batch-item batch-cover-item" data-cover-operation="${x.id}"><span class="queue-number">${icon('image')}</span><strong class="queue-item-title">第 ${x.index+1} 条视频 · 更新封面首帧</strong><div class="batch-item-tools">${badge(queueStatusLabel(x),statusClass(x.status))}<div class="queue-actions"><a class="text-button" href="${queueItemLink(x)}">查看封面修改</a>${queueButton(x,{inspect:false})}</div></div><p class="queue-item-description">${x.position?'当前队列第 '+x.position+' 位 · ':''}${E(queueDisplayMessage(x))}</p></div>`).join('')}</div>`;
}
function batchPlanningHtml(t){
  const p=t.planning;if(!p)return '';
  return `<div class="batch-planning-summary"><div class="batch-item"><span class="queue-number">${icon('folder')}</span><strong class="queue-item-title">整批素材整理与统一策划</strong><div class="batch-item-tools">${badge(queueStatusLabel(p),statusClass(p.status))}<div class="queue-actions">${queueButton(p,{inspect:false})}</div></div><p class="queue-item-description">${E(queueDisplayMessage(p))}</p></div><p class="form-help">整批先统一事实与各条文案、分镜差异，通过后再按顺序制作以下视频。</p></div>`;
}
function batchItems(t) {
  return `<section class="batch-items panel" aria-label="本批视频">${batchPlanningHtml(t)}<div class="section-heading"><h2>本批视频</h2><span>${t.completedCount||0}/${t.count} 条已完成</span></div>${t.queueItems.map(x=>{
    const r=t.results.find(r=>r.index===x.index&&r.video);
    return `<div class="batch-item ${x.status==='running'?'is-active':''}"><span class="queue-number" aria-label="本批第 ${x.index+1} 条">${x.index+1}</span><strong class="queue-item-title">${queueItemTitle(x)}</strong><div class="batch-item-tools">${badge(queueStatusLabel(x),statusClass(x.status))}<div class="queue-actions">${r?`<a class="secondary" href="#preview/${t.id}/${x.index}">查看成品</a>${editActions(t.id,x.index)}${!x.settled?queueButton(x,{inspect:false}):''}`:queueButton(x,{inspect:false})}</div></div><p class="queue-item-description">${E(queueDisplayMessage(x))}</p></div>`;
  }).join('')}${batchCoverOperations(t)}</section>`;
}
// Display batch order rather than historical global job IDs; retain the stored audit event.
const eventLogBeforeQueue = eventLog;
eventLog = function(t) {
  return eventLogBeforeQueue({...t, events:t.events.map(e=>({...e, message:e.message.replace(/^本批 (\d+) 条已进入队尾，序号 \d+[–-]\d+$/, '本批 $1 条已进入队尾，将按提交顺序制作')}))});
};
const taskCurrentBeforeQueue=taskCurrent;
taskCurrent=function(t){if(t.queueItems?.length&&['queued','partial','cancelled','timed_out'].includes(t.status)){const label=t.status==='queued'?'已排队，等待按顺序开始':t.status==='partial'?'本批已结束，完成的作品已保留':'本次制作已停止';return `<div class="current-step"><span>${icon(t.status==='partial'?'check':'clapper')}</span><div><h2>${label}</h2><p>${E(t.message)}</p></div></div>`;}return taskCurrentBeforeQueue(t);};
const taskBeforeQueue=renderTask;
renderTask=function(){taskBeforeQueue();const t=state.tasks.find(x=>x.id===selectedTask);if(!t?.queueItems?.length)return;const stageArea=$('#task-stages');if(['partial','cancelled','timed_out'].includes(t.status))stageArea.hidden=true;else if(t.status==='queued'&&t.queueItems.every(x=>!x.phase))stageArea.innerHTML=stages(-1,false);stageArea.insertAdjacentHTML('afterend',batchItems(t));if(t.status==='needs_input'){const question=document.createElement('section');question.className='panel queue-question-panel';question.append($('#task-current'),$('#task-controls'));stageArea.before(question);}};
const refreshBeforeQueue=refresh;
refresh=async function(paint=true){
  const oldQueue=state?.queue, oldAgent=state?.config.agent, open=$('.queue-next')?.open;
  const previous=state?.tasks.find(x=>x.id===selectedTask);
  await refreshBeforeQueue(paint);
  if(!paint)return;
  const queueChanged=JSON.stringify(oldQueue)!==JSON.stringify(state.queue);
  const agentChanged=oldAgent?.canDispatch!==state.config.agent.canDispatch;
  if((queueChanged||agentChanged)&&$('#queue-panel-area')){
    $('#queue-panel-area').innerHTML=queuePanel();
    if(open&&$('.queue-next'))$('.queue-next').open=true;
  }
  if(route!=='task')return;
  const t=state.tasks.find(x=>x.id===selectedTask);
  if(!t?.queueItems?.length)return;
  const row=taskAnswerRow(t), oldRow=previous&&taskAnswerRow(previous);
  if(previous?.status===t.status&&$('#task-controls')&&
     ((t.status==='queued'&&row?.answerSaved&&agentChanged)||
      (t.status==='needs_input'&&row?.answerPending&&!oldRow?.answerPending))){
    $('#task-controls').innerHTML=taskControls(t);
  }
  if(queueChanged&&$('.batch-items')){
    const scratch=document.createElement('div');
    scratch.innerHTML=batchItems(t);
    $('.batch-items').replaceWith(scratch.firstElementChild);
  }
};
document.addEventListener('click',async e=>{const b=e.target.closest('[data-action]');if(!b||!b.dataset.action.startsWith('queue-'))return;const action=b.dataset.action.slice(6);await busy(b,async()=>{try{await api('/api/queue/items/'+b.dataset.id+'/'+action,{});await refresh(false);if(route==='tasks')renderTasks();else if(route==='task')renderTask();notify(action==='cancel'?'已请求取消，现有成品与云端任务 ID 保留':action==='recover'?'已请求检查当前状态，请保持 Agent 连接；确认前不会开始下一条':'按原序号继续，不改变队列顺序');}catch(err){notify(err.message,true);}});});
const chromeBeforeQueue=updateChrome;
updateChrome=function(){chromeBeforeQueue();$('#works-count').textContent=state.tasks.filter(t=>!(state.archives||[]).some(a=>a.id===t.id)).reduce((n,t)=>n+t.results.filter(r=>r.video).length,0)+(state.archives||[]).reduce((n,t)=>n+t.results.length,0)+state.institutions.filter(x=>x.reference).length;};
// acceptance.js starts the app after all lifecycle screens register.
