const $=selector=>document.querySelector(selector);
const esc=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const say=message=>{const toast=$('#toast');toast.textContent=message;toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),2800);};
async function api(path,options={}){const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});const data=await response.json();if(response.status===401){location.replace('/login.html');throw Error('Your session has expired.');}if(!response.ok)throw Error(data.error||'Request failed');return data;}
function formatMention(body,username){return esc(body).replaceAll(`@${esc(username)}`,`<mark>@${esc(username)}</mark>`);}
async function loadNotifications(){
  const [user,notifications]=await Promise.all([api('/api/auth/me'),api('/api/notifications')]);
  $('#notificationUser').textContent=`Signed in as ${user.username}`;
  const unread=notifications.filter(notification=>!notification.read_at).length;
  $('#notificationSummary').textContent=`${unread} unread · ${notifications.length} total`;
  $('#notificationList').innerHTML=notifications.length?notifications.map(notification=>`<button class="notification-card ${notification.read_at?'':'unread'}" data-id="${esc(notification.notification_id)}" data-patient="${esc(notification.patient_id)}" data-entry="${esc(notification.entry_id)}"><span class="notification-dot"></span><span class="notification-copy"><strong>${esc(notification.author_username)} mentioned you</strong><span>${formatMention(notification.body,user.username)}</span><small>${esc(notification.patient_label)} · ${esc(notification.entry_type)} · ${new Date(notification.created_at).toLocaleString('en-US')}</small></span><span class="notification-status">${notification.read_at?'Read':'Unread'}</span></button>`).join(''):'<p class="empty">You have no mentions.</p>';
  document.querySelectorAll('.notification-card').forEach(card=>card.onclick=async()=>{try{await api(`/api/notifications/${encodeURIComponent(card.dataset.id)}`,{method:'PATCH',body:'{}'});location.assign(`/app.html?patient=${encodeURIComponent(card.dataset.patient)}&entry=${encodeURIComponent(card.dataset.entry)}&comment=${encodeURIComponent(card.dataset.id)}`);}catch(error){say(error.message);}});
}
$('#refreshNotifications').onclick=()=>loadNotifications().catch(error=>say(error.message));
$('#logout').onclick=async()=>{try{await api('/api/auth/logout',{method:'POST',body:'{}'});}finally{location.replace('/login.html');}};
loadNotifications().catch(error=>say(error.message));
