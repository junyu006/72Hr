const $ = selector => document.querySelector(selector);
const state = {patient:null, entries:[], highlights:[], filter:'all', autoGlance:true, selectedHighlightId:null, pendingHighlightId:null, user:null};
const deepLink = new URLSearchParams(location.search);
const role = $('#role');
const toast = $('#toast');
const clinicalKind = document.createElement('select');
clinicalKind.id = 'clinicalKind';
clinicalKind.innerHTML = '<option value="doctor">Doctor</option><option value="nurse">Nurse</option>';
role.after(clinicalKind);
const highlightDeleteDialog=document.createElement('dialog');
highlightDeleteDialog.id='highlightDeleteDialog';
highlightDeleteDialog.innerHTML='<form method="dialog"><h2>Delete highlighted keyword?</h2><p id="highlightDeleteSummary"></p><p class="small-note">This removes only the highlight and its reason. The underlying entry will not be changed.</p><menu><button value="cancel">Cancel</button><button type="button" class="confirm-highlight-delete">Delete highlight</button></menu></form>';
document.body.append(highlightDeleteDialog);
highlightDeleteDialog.addEventListener('close',()=>{if(highlightDeleteDialog.returnValue==='cancel')state.pendingHighlightId=null;});

const recordLabels = {
  system_generated_event:'System generated event', ai_scribe_log:'AI scribe log',
  doctor_patient_consult:'Doctor–Patient Consult', nurse_patient_consult:'Nurse–Patient Consult',
  ai_patient_consult:'AI–Patient Consult', staff_manual_log:'Staff manual log',
  clinician_manual_log:'Clinician manual log', patient_facing_log:'Patient-facing log'
};
const sections = {
  system_generated_event:'ai_scribed', ai_scribe_log:'ai_scribed', ai_patient_consult:'ai_scribed',
  doctor_patient_consult:'clinician_sections', nurse_patient_consult:'clinician_sections',
  clinician_manual_log:'clinician_sections', staff_manual_log:'staff_notes', patient_facing_log:'patient_facing'
};
const allTypes = Object.keys(recordLabels);
const allowedTypes = () => {
  if (role.value === 'patient') return [];
  if (role.value === 'staff') return ['staff_manual_log'];
  if (role.value === 'system') return ['system_generated_event','ai_patient_consult'];
  if (role.value === 'admin') return allTypes.filter(type=>type!=='ai_scribe_log');
  return clinicalKind.value === 'doctor'
    ? ['doctor_patient_consult','clinician_manual_log','patient_facing_log']
    : ['nurse_patient_consult','clinician_manual_log','patient_facing_log'];
};
const canEdit = entry => role.value === 'admin' ||
  (role.value === 'staff' && entry.entry_type === 'staff_manual_log') ||
  (role.value === 'clinician' && allowedTypes().includes(entry.entry_type));
const canHighlight = entry => ['clinician','admin'].includes(role.value);
const canManageHighlights = () => ['clinician','admin'].includes(role.value);
const esc = value => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const say = message => { toast.textContent=message; toast.classList.add('show'); setTimeout(()=>toast.classList.remove('show'),2800); };
const headers = () => ({'Content-Type':'application/json'});
async function api(path, options={}) {
  const response = await fetch(path, {...options, headers:{...headers(), ...(options.headers || {})}});
  const data = await response.json();
  if(response.status===401){location.replace('/login.html');throw Error('Your session has expired.');}
  if (!response.ok) throw Error(data.error || 'Request failed');
  return data;
}

function configureRole() {
  clinicalKind.hidden = role.value !== 'clinician';
  clinicalKind.disabled = true;
  $('#createPatient').hidden = ['patient','system'].includes(role.value);
  $('#deletePatient').hidden = role.value !== 'admin' || !state.patient;
  $('#addEntry').hidden = allowedTypes().length === 0;
  $('#addScribe').hidden = !['system','admin'].includes(role.value);
  $('#aiGlance').hidden = !['clinician','admin','system'].includes(role.value);
  $('#entryType').innerHTML = allowedTypes().map(type => `<option value="${type}">${recordLabels[type]}</option>`).join('');
  syncSection();
}
function syncSection() { $('#section').value = sections[$('#entryType').value] || ''; }

async function loadPatients() {
  const patients = await api('/api/patients');
  $('#patientList').innerHTML = patients.length ? patients.map(patient =>
    `<button class="patient-row ${state.patient?.id===patient.id?'current':''}" data-id="${esc(patient.id)}" data-name="${esc(patient.display_label)}">${esc(patient.display_label)}</button>`
  ).join('') : '<p class="small-note">No patients available for this role.</p>';
  document.querySelectorAll('.patient-row').forEach(button => button.onclick=()=>selectPatient({id:button.dataset.id,display_label:button.dataset.name}));
  if (!state.patient && patients[0]) {
    const requested=patients.find(patient=>patient.id===deepLink.get('patient'));
    await selectPatient(requested||patients[0]);
  }
  if (!patients.length) clearPatient();
}
function clearPatient() {
  state.patient=null; state.entries=[]; state.highlights=[];state.selectedHighlightId=null;
  $('#patientName').textContent='No accessible patient';
  $('#patientMeta').textContent='Role-scoped PostgreSQL view';
  $('#timeline').innerHTML='<div class="empty">No records available.</div>';
  $('#deletePatient').hidden=true;
}
async function selectPatient(patient) {
  state.patient=patient;
  $('#patientName').textContent=patient.display_label;
  $('#heading').textContent=`${patient.display_label} · Care context`;
  $('#patientMeta').textContent=`Patient page · ${patient.id}`;
  $('#deletePatient').hidden=role.value!=='admin';
  await loadTimeline();
  document.querySelectorAll('.patient-row').forEach(button => button.classList.toggle('current', button.dataset.id===patient.id));
  if (state.autoGlance && ['clinician','admin','system'].includes(role.value)) {
    state.autoGlance=false;
    generateGlance();
  }
  const linkedEntry=deepLink.get('entry');
  if(linkedEntry&&deepLink.get('patient')===patient.id&&state.entries.some(entry=>entry.id===linkedEntry)){
    state.filter='all';renderTimeline();jumpTo(linkedEntry);
    if(deepLink.get('comment'))await showComments(linkedEntry);
    history.replaceState(null,'','/app.html');
  }
}
async function loadTimeline() {
  if (!state.patient) return;
  state.entries=await api(`/api/patients/${state.patient.id}/timeline`);
  state.highlights=await api(`/api/patients/${state.patient.id}/highlights`);
  if(!state.highlights.some(highlight=>highlight.id===state.selectedHighlightId))state.selectedHighlightId=null;
  renderTimeline(); renderGlance();
}
function renderGlance() {
  const rows=state.entries.filter(entry=>entry.open_action||entry.risk_level>0).slice(0,3);
  const highlighted=state.highlights.map(highlight=>{
    const entry=state.entries.find(item=>item.id===highlight.entry_id);
    if(!entry)return null;
    return {...highlight,keyword:entry.content.slice(Number(highlight.span_start),Number(highlight.span_end))};
  }).filter(Boolean);
  const attention=rows.map(entry=>`<div><small>${entry.open_action?'Open action':'Risk'} · ${esc(recordLabels[entry.entry_type]||entry.entry_type)}</small><strong>${esc(entry.content.slice(0,48))}</strong><button class="jump" data-id="${entry.id}">View source →</button></div>`).join('');
  const highlights=highlighted.length ? highlighted.map(highlight=>{
    const shortId=highlight.entry_id.replace(/^entry_/,'').slice(-8);
    const selected=state.selectedHighlightId===highlight.id;
    return `<article class="glance-highlight ${selected?'selected':''}" data-highlight-id="${esc(highlight.id)}"><button class="highlight-select" data-id="${esc(highlight.id)}" aria-pressed="${selected}"><span class="highlight-keyword-row"><mark>${esc(highlight.keyword)}</mark><i aria-hidden="true">${selected?'✓':'○'}</i></span><span class="highlight-reason">${esc(highlight.risk_reason)}</span></button><div class="highlight-card-footer"><span class="highlight-origin">${esc(highlight.origin)} highlight</span><button class="highlight-jump" data-id="${esc(highlight.entry_id)}" data-highlight-id="${esc(highlight.id)}" title="View ${esc(highlight.entry_id)}"><span>Source</span><code>…${esc(shortId)}</code><span aria-hidden="true">→</span></button></div></article>`;
  }).join('') : '<p class="highlight-empty">No highlighted keywords in the records visible to this role.</p>';
  const deleteControl=canManageHighlights()?`<button class="delete-selected-highlight" ${state.selectedHighlightId?'':'disabled'} aria-label="Delete selected highlight">Delete selected</button>`:'';
  $('#glanceRows').innerHTML=`<div class="facts glance-facts">${attention||'<div><small>Open actions & risks</small><strong>Nothing currently flagged.</strong></div>'}<div class="highlight-column"><div class="highlight-column-header"><span><small>Highlighted keywords</small><b>${highlighted.length}</b></span>${deleteControl}</div><div class="highlight-list">${highlights}</div></div></div>`;
  document.querySelectorAll('.jump').forEach(button=>button.onclick=()=>jumpTo(button.dataset.id));
  document.querySelectorAll('.highlight-select').forEach(button=>button.onclick=()=>selectHighlight(button.dataset.id));
  document.querySelectorAll('.highlight-jump').forEach(button=>button.onclick=()=>{selectHighlight(button.dataset.highlightId);jumpTo(button.dataset.id);});
  document.querySelector('.delete-selected-highlight')?.addEventListener('click',()=>requestHighlightDeletion(state.selectedHighlightId));
}
function selectHighlight(highlightId) {
  state.selectedHighlightId=highlightId;
  document.querySelectorAll('.keyword-highlight').forEach(button=>button.classList.toggle('selected',button.dataset.highlightId===highlightId));
  renderGlance();
}
function requestHighlightDeletion(highlightId) {
  const highlight=state.highlights.find(item=>item.id===highlightId);
  if(!highlight||!canManageHighlights())return;
  const entry=state.entries.find(item=>item.id===highlight.entry_id);
  const keyword=entry?.content.slice(Number(highlight.span_start),Number(highlight.span_end))||'keyword';
  state.pendingHighlightId=highlightId;
  $('#highlightDeleteSummary').textContent=`“${keyword}” — ${highlight.risk_reason}`;
  highlightDeleteDialog.showModal();
}
$('.confirm-highlight-delete').onclick=async()=>{const highlightId=state.pendingHighlightId;if(!highlightId)return;try{await api(`/api/highlights/${highlightId}`,{method:'DELETE'});state.selectedHighlightId=null;state.pendingHighlightId=null;highlightDeleteDialog.close();await loadTimeline();say('Highlight deleted.');}catch(error){say(error.message);}};
function jumpTo(id) {
  let target=document.querySelector(`#entry-${CSS.escape(id)}`);
  if(!target&&state.entries.some(entry=>entry.id===id)){
    state.filter='all';document.querySelector('.filters .selected')?.classList.remove('selected');document.querySelector('.filters [data-filter="all"]')?.classList.add('selected');renderTimeline();target=document.querySelector(`#entry-${CSS.escape(id)}`);
  }
  if (!target) return say('The source entry is unavailable for this role.');
  target.scrollIntoView({behavior:'smooth',block:'center'});
  target.classList.add('source-target'); setTimeout(()=>target.classList.remove('source-target'),1600);
}
function renderTimeline() {
  const entries=state.filter==='all' ? state.entries : state.entries.filter(entry=>entry.section===state.filter);
  $('#timeline').innerHTML=entries.length ? entries.map(entry=>{
    const editable=canEdit(entry);
    const internalActions=role.value!=='patient';
    const editControl=editable
      ? `<span class="edit-state editable-state">Editable</span><button class="save" data-id="${entry.id}" data-v="${entry.version}">Save new version</button>`
      : `<span class="edit-state readonly-state" title="Your role cannot edit this record type">View only</span>`;
    return `<article id="entry-${esc(entry.id)}"><span class="dot blue"></span><div class="meta"><span class="system">${entry.author_role==='system'?'✦ AI':esc(entry.author_id.slice(0,2))}</span><b>${esc(entry.author_id)}</b><small>${esc(recordLabels[entry.entry_type]||entry.entry_type)}</small><time>${new Date(entry.created_at).toLocaleString('en-US')}</time><mark>Entry ID: ${esc(entry.id)}<br>v${entry.version}</mark></div><div class="text ${editable?'editable':''}" ${editable?'contenteditable="true" role="textbox" aria-multiline="true" aria-label="Editable record content" spellcheck="true"':''}>${esc(entry.content)}</div><div class="actions">${editControl}${internalActions?`<button class="comments-btn" data-id="${entry.id}">Comments</button><button class="versions" data-id="${entry.id}" aria-expanded="false">Versions</button>`:''}${canHighlight(entry)?`<button class="manual-highlight" data-id="${entry.id}">Highlight keyword</button>`:''}</div><div class="comments" id="comments-${entry.id}"></div><div class="history" id="history-${entry.id}"></div></article>`;
  }).join('') : '<div class="empty">No records available in this view.</div>';
  applyHighlights(); attachTimelineActions();
}
function applyHighlights() {
  const grouped=state.highlights.reduce((result,highlight)=>{(result[highlight.entry_id]??=[]).push(highlight);return result;},{});
  Object.entries(grouped).forEach(([entryId,highlights])=>{
    const text=document.querySelector(`#entry-${CSS.escape(entryId)} .text`);
    const entry=state.entries.find(item=>item.id===entryId);
    if(!text||!entry)return;
    const raw=entry.content, fragment=document.createDocumentFragment(); let cursor=0;
    highlights.sort((a,b)=>Number(a.span_start)-Number(b.span_start)).forEach(highlight=>{
      const start=Number(highlight.span_start),end=Number(highlight.span_end);
      if(start<cursor||end<=start||end>raw.length)return;
      fragment.append(document.createTextNode(raw.slice(cursor,start)));
      const button=document.createElement('button');button.className=`keyword-highlight ${state.selectedHighlightId===highlight.id?'selected':''}`;button.dataset.highlightId=highlight.id;button.textContent=raw.slice(start,end);button.title=`${highlight.risk_reason}${canManageHighlights()?' · Right-click to delete':''}`;
      button.onclick=()=>{selectHighlight(highlight.id);highlight.reason_visible?jumpTo(highlight.reason_entry_id):say(highlight.risk_reason);};
      button.oncontextmenu=event=>{event.preventDefault();selectHighlight(highlight.id);if(canManageHighlights())requestHighlightDeletion(highlight.id);else say('Your role cannot delete highlights.');};
      fragment.append(button);cursor=end;
    });
    fragment.append(document.createTextNode(raw.slice(cursor)));text.replaceChildren(fragment);
  });
}
function attachTimelineActions() {
  state.entries.forEach(entry=>{
    if (entry.provenance_pointer?.startsWith('entry:')) {
      const sourceId=entry.provenance_pointer.slice(6);
      if (state.entries.some(candidate=>candidate.id===sourceId)) {
        const actions=document.querySelector(`#entry-${CSS.escape(entry.id)} .actions`);
        if (actions) { const button=document.createElement('button'); button.className='source-consult-link'; button.textContent=`View source consult: ${sourceId}`; button.onclick=()=>jumpTo(sourceId); actions.prepend(button); }
      }
    }
  });
  document.querySelectorAll('.save').forEach(button=>button.onclick=async()=>{
    try {
      const entry=state.entries.find(item=>item.id===button.dataset.id), content=document.querySelector(`#entry-${CSS.escape(button.dataset.id)} .text`).textContent;
      if(content===entry?.content)return say('No changes to save.');
      await api(`/api/entries/${button.dataset.id}`,{method:'PATCH',body:JSON.stringify({content,expected_version:Number(button.dataset.v)})});
      await loadTimeline();say('New version saved.');
    } catch(error){ say(error.message); }
  });
  document.querySelectorAll('.comments-btn').forEach(button=>button.onclick=()=>showComments(button.dataset.id));
  document.querySelectorAll('.versions').forEach(button=>button.onclick=()=>showVersions(button.dataset.id));
  document.querySelectorAll('.manual-highlight').forEach(button=>button.onclick=()=>createHighlight(button.dataset.id));
}
async function showComments(entryId) {
  try {
    const [comments,people]=await Promise.all([api(`/api/entries/${entryId}/comments`),api(`/api/mentionable-users?entry_id=${encodeURIComponent(entryId)}`)]),holder=$(`#comments-${CSS.escape(entryId)}`);
    const formatBody=comment=>{
      let body=esc(comment.body);
      (comment.mention_usernames||[]).sort((a,b)=>b.length-a.length).forEach(username=>{body=body.replaceAll(`@${esc(username)}`,`<mark>@${esc(username)}</mark>`);});
      return body;
    };
    holder.innerHTML=`<div class="comment-list">${comments.map(comment=>`<p class="comment-row"><b>${esc(comment.author_id)}</b> ${formatBody(comment)}</p>`).join('')||'<p class="small-note">No comments yet.</p>'}</div><div class="mention-options">${people.map(person=>`<button type="button" class="mention-chip" data-username="${esc(person.username)}">@${esc(person.username)} <small>${esc(person.clinician_kind||person.role)}</small></button>`).join('')}</div><div class="composer"><input class="comment-input" maxlength="1000" placeholder="Add an internal comment; type @username to notify…"><button class="post-comment">Post</button></div>`;
    holder.classList.add('open');
    const input=holder.querySelector('.comment-input');
    holder.querySelectorAll('.mention-chip').forEach(button=>button.onclick=()=>{const token=`@${button.dataset.username} `;if(!input.value.includes(token.trim()))input.value+=`${input.value&&!input.value.endsWith(' ')?' ':''}${token}`;input.focus();});
    holder.querySelector('.post-comment').onclick=async()=>{const body=input.value.trim();if(!body)return;try{await api(`/api/entries/${entryId}/comments`,{method:'POST',body:JSON.stringify({body})});await showComments(entryId);say('Comment posted and mentions notified.');}catch(error){say(error.message);}};
  } catch(error){say(error.message);}
}

async function refreshNotificationBadge(){
  const notifications=await api('/api/notifications');
  const unread=notifications.filter(notification=>!notification.read_at).length,badge=$('#notificationBadge');
  badge.textContent=unread;badge.hidden=unread===0;
}
async function showVersions(entryId) {
  try {
    const versions=await api(`/api/entries/${entryId}/versions`), holder=$(`#history-${CSS.escape(entryId)}`), entry=state.entries.find(item=>item.id===entryId);
    const trigger=document.querySelector(`.versions[data-id="${CSS.escape(entryId)}"]`);
    if(holder.classList.contains('open')){holder.classList.remove('open');trigger?.setAttribute('aria-expanded','false');return;}
    holder.innerHTML=`<div class="history-heading"><span><b>Version history</b><small>${versions.length} revision${versions.length===1?'':'s'}</small></span><button class="close-history" type="button">Close</button></div>${versions.map(version=>`<section class="version-card"><div class="version-meta"><b>v${version.version}</b><span>${esc(version.change_reason)}</span><time>${new Date(version.changed_at).toLocaleString('en-US')}</time>${canEdit(entry)?`<button class="revert" data-v="${version.version}">Restore this version</button>`:'<em>Read only</em>'}</div><small>Changed by ${esc(version.changed_by)}</small><p>${esc(version.content)}</p></section>`).join('')||'<p class="small-note">No versions are available.</p>'}`;
    holder.classList.add('open');trigger?.setAttribute('aria-expanded','true');
    holder.querySelector('.close-history')?.addEventListener('click',()=>{holder.classList.remove('open');trigger?.setAttribute('aria-expanded','false');});
    holder.querySelectorAll('.revert').forEach(button=>button.onclick=async()=>{try{await api(`/api/entries/${entryId}/revert`,{method:'POST',body:JSON.stringify({version:Number(button.dataset.v)})});await loadTimeline();say('Version restored as a new revision.');}catch(error){say(error.message);}});
  } catch(error){say(error.message);}
}
async function createHighlight(entryId) {
  const keyword=prompt('Keyword in this record:'), reason=prompt('Why is this important?'), reasonEntry=prompt('Reason source Entry ID (optional):');
  if(!keyword||!reason)return;
  try {await api(`/api/entries/${entryId}/highlights`,{method:'POST',body:JSON.stringify({patient_id:state.patient.id,keyword,reason,reason_entry_id:reasonEntry||null})}); await loadTimeline();say('Keyword highlighted.');} catch(error){say(error.message);}
}
async function generateGlance() {
  if(!state.patient||$('#aiGlance').dataset.running==='true')return;
  const button=$('#aiGlance');
  try {button.dataset.running='true';button.disabled=true;button.textContent='Generating…';$('#latency').textContent='Generating AI glance…';const result=await api(`/api/patients/${state.patient.id}/ai-glance`,{method:'POST',body:'{}'});$('#aiGlanceOutput').innerHTML=`<div class="ai-output"><b>✦ Qwen2.5 AI Glance</b><pre>${esc(result.summary)}</pre><div class="ai-sources"></div></div>`;const holder=$('.ai-sources');result.sources.forEach(source=>{const sourceButton=document.createElement('button');sourceButton.className='jump';sourceButton.textContent=`View source: ${source.entry_id}`;sourceButton.onclick=()=>jumpTo(source.entry_id);holder.append(sourceButton);});$('#latency').textContent=`AI glance ${result.generation_ms} ms`;}catch(error){say(error.message);}finally{button.dataset.running='false';button.disabled=false;button.textContent='✦ Generate AI glance';}
}

$('#entryType').onchange=syncSection;
$('#refreshPatients').onclick=loadPatients;
$('#createPatient').onclick=()=>$('#patientDialog').showModal();
$('#deletePatient').onclick=async()=>{
  if(!state.patient||role.value!=='admin')return;
  const patient={...state.patient};
  if(!confirm(`Permanently delete ${patient.display_label} and all of this patient's records, versions, comments, highlights, and audit events? This cannot be undone.`))return;
  try {
    await api(`/api/patients/${patient.id}`,{method:'DELETE'});
    state.patient=null; state.entries=[]; state.highlights=[];
    await loadPatients();
    say(`${patient.display_label} was deleted.`);
  } catch(error){say(error.message);}
};
$('#addEntry').onclick=()=>state.patient?$('#entryDialog').showModal():say('Select a patient first.');
$('#savePatient').onclick=async event=>{event.preventDefault();try{const patient=await api('/api/patients',{method:'POST',body:JSON.stringify({display_label:$('#patientInput').value})});$('#patientDialog').close();await loadPatients();await selectPatient(patient);}catch(error){say(error.message);}};
$('#saveEntry').onclick=async event=>{event.preventDefault();try{const result=await api(`/api/patients/${state.patient.id}/entries`,{method:'POST',body:JSON.stringify({section:$('#section').value,entry_type:$('#entryType').value,content:$('#entryContent').value,open_action:$('#openAction').checked})});$('#entryDialog').close();$('#entryContent').value='';await loadTimeline();say(result.ai_summary?'Record and linked AI scribe saved.':'Record saved.');}catch(error){say(error.message);}};
$('#addScribe').onclick=()=>{if(!state.patient)return say('Select a patient first.');const consults=state.entries.filter(entry=>['doctor_patient_consult','nurse_patient_consult'].includes(entry.entry_type));$('#scribeSourceEntry').innerHTML=consults.map(entry=>`<option value="${entry.id}">${recordLabels[entry.entry_type]} · ${entry.id}</option>`).join('');if(!consults.length)return say('No accessible consult is available.');$('#scribeDialog').showModal();};
$('#runScribe').onclick=async event=>{event.preventDefault();try{await api(`/api/patients/${state.patient.id}/ai-scribe`,{method:'POST',body:JSON.stringify({source_entry_id:$('#scribeSourceEntry').value})});$('#scribeDialog').close();await loadTimeline();say('Linked AI scribe log generated.');}catch(error){say(error.message);}};
$('#aiGlance').onclick=generateGlance;
$('#logout').onclick=async()=>{try{await api('/api/auth/logout',{method:'POST',body:'{}'});}finally{location.replace('/login.html');}};
document.querySelectorAll('.filters button').forEach(button=>button.onclick=()=>{document.querySelector('.filters .selected')?.classList.remove('selected');button.classList.add('selected');state.filter=button.dataset.filter;renderTimeline();});
async function bootstrap(){state.user=await api('/api/auth/me');role.value=state.user.role;if(state.user.clinician_kind)clinicalKind.value=state.user.clinician_kind;$('#signedInUser').textContent=state.user.clinician_kind?`${state.user.username} · ${state.user.clinician_kind}`:state.user.username;$('.avatar').textContent=state.user.username.slice(0,2).toUpperCase();configureRole();await Promise.all([loadPatients(),refreshNotificationBadge()]);}
bootstrap().catch(error=>say(error.message));
