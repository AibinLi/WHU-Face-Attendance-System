const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const avatar = id => `/media/faces/${encodeURIComponent(id)}.jpg`;
const photo = id => `/media/images/${encodeURIComponent(id)}.jpg`;
let state, page = 'attendance', sessionId = localStorage.getItem('sessionId') || '', result = null;
let imageId = '', filter = 'absent', selected = new Set(), search = '', uploadKind = 'gallery';
const modal = $('#modal');

async function api(path, body, method = 'POST') {
  const options = body === undefined ? {} : {method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '请求失败');
  return data;
}
function toast(message) { const el=$('#toast'); el.textContent=message;el.style.display='block'; clearTimeout(window.toastTimer);window.toastTimer=setTimeout(()=>el.style.display='none',5500); }
function showDialog(title, body, footer='') {
  $('#modal-content').innerHTML=`<div class="dialog-head"><h2>${esc(title)}</h2><button class="dialog-close" aria-label="关闭" data-action="dismiss">×</button></div><div class="dialog-body">${body}</div>${footer?`<div class="dialog-footer">${footer}</div>`:''}`;
  if(!modal.open) modal.showModal();
}
async function refresh() {
  state=await api('/api/state');
  if(sessionId && state.sessions.some(s=>s.id===sessionId)) result=await api(`/api/sessions/${sessionId}`);
  else {sessionId='';result=null;}
  render();
}
async function watch(jobId) {
  $('#busy').classList.remove('hidden');
  try {
    while(true){
      const job=await api('/api/jobs/'+jobId);
      $('#busy-text').textContent=job.message || '正在处理';
      $('#busy-progress').max=job.total||1;$('#busy-progress').value=job.progress;
      if(job.status==='error') throw new Error(job.error);
      if(job.status==='done') return job;
      await new Promise(resolve=>setTimeout(resolve,650));
    }
  } finally {$('#busy').classList.add('hidden');await refresh();}
}
function heading(kicker,title,description,actions=''){
 return `<div class="page-heading"><div><div class="eyebrow">${kicker}</div><h1>${title}</h1><p>${description}</p></div><div class="row">${actions}</div></div>`;
}
function footer(){return '<footer><span>见齐 · 班级合照考勤系统</span><span>LOCAL INFERENCE / MULTIMEDIA LAB</span></footer>';}
function stat(label,value,note,style='',icon='◌',unit=label.includes('人脸')?'张':'人'){
 return `<div class="stat ${style}"><div class="stat-label">${label}</div><div class="stat-icon">${icon}</div><div class="stat-value">${value}<span class="stat-unit">${unit}</span></div><div class="stat-foot">${note}</div></div>`;
}
function render(){
 $$('.nav').forEach(b=>b.classList.toggle('active',b.dataset.page===page));
 $('#breadcrumb').textContent={attendance:'课堂考勤',gallery:'班级底库'}[page];
 $('#content').innerHTML=page==='gallery'?renderGallery():renderAttendance();
 if(page==='attendance' && result?.images.length) drawImage();
}
function renderAttendance(){
 const counts=result?.counts || {expected:state.people.length,present:0,absent:0,review:0};
 const session=result?.session;
 const options=state.sessions.map(s=>`<option value="${s.id}" ${s.id===sessionId?'selected':''}>${esc(s.title)}${s.closed?' · 已结束':''}</option>`).join('');
 const controls=`${options?`<select id="session-select" class="session-select"><option value="">选择历史场次</option>${options}</select>`:''}<button class="btn primary" data-action="new-session">＋ 新建考勤</button>`;
 const sessionBadge=session?`<span class="badge ${session.closed?'':'warn'}">${session.provisional?'预览 · 底库待核对':session.closed?'✓ 已结束':'● 进行中'}</span>`:'<span class="badge">等待开始</span>';
 const imgPanel=result?.images.length?`<div id="image-view"></div><div class="photo-tabs">${result.images.map(i=>`<button class="photo-tab ${i.id===(imageId||result.images[0].id)?'active':''}" data-image="${i.id}"><img src="${photo(i.id)}" alt="考勤照片">${i.faces} 张人脸${i.reference_overlap?' · 底库原图':''}</button>`).join('')}</div>`:`<div class="empty-upload" id="drop-zone"><div class="upload-symbol">↥</div><h3>${session?'上传照片，开始本场识别':'让每一次到场，都有记录'}</h3><p>${session?'拖入现场合照或个人照片，可连续上传多个角度':'创建考勤场次，上传照片即可查看到场情况'}</p><button class="btn primary" data-action="${session?'upload-attendance':'new-session'}">${session?'＋ 选择考勤照片':'＋ 新建考勤场次'}</button><small>JPG / PNG / WEBP · 每张不超过 35MB · 支持多张累计去重</small></div>`;
 const pending=result?.faces.filter(f=>['review','unknown'].includes(f.status)&&!f.excluded)||[];
 return heading('ATTENDANCE OVERVIEW','课堂考勤','从合照到名单，让到场情况一目了然。',controls)+
 `<div class="stats">${stat(session?.provisional||!state.settings.confirmed?'底库编号 · 待核对':'班级人数',counts.expected,session?.provisional||!state.settings.confirmed?'自动分组数量，并非已确认人数':'来自已核对的班级底库','','▦')}${stat('已确认到场',counts.present,'跨照片按编号去重','green','✓')}${stat(session?.closed?'缺席人数':'暂未匹配',counts.absent,session?.closed?'已结束考勤的最终结果':'结束考勤前可继续补拍','orange','−')}${stat('待处理人脸',counts.review,'未识别 / 身份接近 / 分配冲突','amber','◇')}</div>`+
 `${!state.settings.confirmed?'<div class="hint warn" style="margin-bottom:22px">请先前往「班级底库」核对人脸分组与班级人数，确认后即可开始考勤。 <button class="btn small" data-action="go-gallery">前往底库 →</button></div>':''}`+
 `<div class="workspace"><section><div class="panel"><div class="panel-head"><div class="row"><h2>${esc(session?.title||'照片识别工作台')}</h2>${sessionBadge}</div>${session&&!session.closed?'<button class="btn small" data-action="upload-attendance">＋ 继续上传</button>':''}</div>${imgPanel}<div class="legend"><span><i></i>已识别</span><span><i class="yellow"></i>待处理</span><span style="margin-left:auto">点击人脸框可查看或修正身份</span></div></div>
 <div class="note-strip"><span>ⓘ</span><span>多张照片累计到场，同一人只计一次。低头、遮挡或未入镜的人可能暂未匹配，可补传另一角度的照片。</span></div>
 ${result?.reference_overlap?'<div class="hint warn" style="margin-top:15px">本场包含底库原图，适合检查流程，不能用来报告独立测试准确率。</div>':''}
 ${pending.length?`<div class="panel bottom-panel"><div class="panel-head"><h2>需要处理的身份 <span class="badge warn">${pending.length}</span></h2><span style="font-size:11px;color:#8f9c93">确认身份或标记不计入</span></div><div class="panel-body review-grid">${pending.map(f=>`<button class="review-card" data-resolve="${f.id}"><img src="${avatar(f.id)}" alt="待确认人脸"><div><b>${f.status==='unknown'?'未找到可靠匹配':'身份需要确认'}</b><p>最高相似度 ${f.score?.toFixed(3)??'—'}</p><span class="badge warn">查看候选 →</span></div></button>`).join('')}</div></div>`:''}
 </section><aside><div class="panel side-section"><div class="panel-head"><h2>人员名单</h2><span class="badge">${counts.expected} 人底库</span></div><div class="panel-body"><div class="roster-filter"><button data-filter="absent" class="${filter==='absent'?'active':''}">${session?.closed?'缺席':'未匹配'}</button><button data-filter="present" class="${filter==='present'?'active':''}">已到场</button><button data-filter="uncertain" class="${filter==='uncertain'?'active':''}">身份待确认</button></div><div class="scroll-roster">${renderRoster()}</div></div></div>
 <div class="panel"><div class="panel-head"><h2>本场操作</h2></div><div class="panel-body"><div class="section-subtitle"><span>已上传照片</span><b>${result?.images.length||0} 张</b></div><div class="section-subtitle"><span>自动通过的人脸</span><b>${counts.automatic||0} 张</b></div><div class="section-subtitle"><span>人工确认的人脸</span><b>${counts.manual||0} 张</b></div><button class="btn primary" style="width:100%" data-action="close-session" ${!session||session.closed||session.provisional?'disabled':''}>✓ 结束考勤并确认结果</button><div class="row" style="margin-top:12px">${session?`<a class="btn small" href="/api/sessions/${sessionId}/export">↓ 导出名单</a><a class="btn small" href="/api/sessions/${sessionId}/export?format=json">↓ 导出明细</a>${!session.closed?'<button class="btn small" data-action="local-attendance">项目照片试运行</button>':''}`:''}</div><div class="hint" style="margin-top:16px">${session?.provisional?'本场是预览结果，底库尚待核对。确认底库后，请另建正式场次。':'开始时固定本场班级底库。之后调整底库不会修改历史考勤结果。'}</div></div></div></aside></div>`+footer();
}
function renderRoster(){
 if(!result)return '<div class="zero-state"><div class="zero-icon">▦</div>创建场次后展示人员头像</div>';
 const people=result.people.filter(p=>p.status===filter);
 return people.length?`<div class="roster">${people.map(p=>`<button class="person-thumb ${p.status}" data-person="${p.id}"><img src="${avatar(p.avatar)}" alt="${esc(p.name)}"><b>${esc(p.name)}</b><small>${filter==='present'?'已到场':filter==='uncertain'?'候选身份':'未匹配'}</small></button>`).join('')}</div>`:`<div class="zero-state"><div class="zero-icon">${filter==='present'?'◌':'✓'}</div>${filter==='present'?'尚无确认到场人员':filter==='uncertain'?'暂无身份冲突候选':'所有底库人员均已匹配，或暂无考勤照片'}</div>`;
}
function drawImage(){
 const image=result.images.find(i=>i.id===imageId)||result.images[0];imageId=image.id;
 const faces=result.faces.filter(f=>f.image_id===image.id);
 $('#image-view').innerHTML=`<div class="photo-info"><span>${esc(image.name)} · ${image.width} × ${image.height}</span><span>检测 ${image.faces} 张 · ${image.elapsed}s <button class="btn small" data-enlarge="${image.id}">放大核对 ↗</button></span></div><div class="image-stage"><img src="${photo(image.id)}" alt="考勤原图"><div class="boxes">${faces.map(f=>{
 const [x1,y1,x2,y2]=f.bbox;const person=result.people.find(p=>p.id===f.person_id);
 return `<button aria-label="${esc(person?.name||'查看人脸')}" class="face-box ${f.status}" data-resolve="${f.id}" style="left:${x1/image.width*100}%;top:${y1/image.height*100}%;width:${(x2-x1)/image.width*100}%;height:${(y2-y1)/image.height*100}%"><span>${esc(person?.name||(f.excluded?'不计入':'待处理'))}</span></button>`;
 }).join('')}</div></div>`;
}
function renderGallery(){
 const galleryImages=state.images.filter(i=>i.kind==='gallery');
 const galleryFaces=state.faces.filter(f=>galleryImages.some(i=>i.id===f.image_id));
 const people=state.people.filter(p=>p.name.includes(search)||String(p.number).includes(search));
 return heading('IDENTITY GALLERY','班级底库','从原始合照提取头像，建立可检查、可修正的人员编号。',`<button class="btn" data-action="backup">↓ 保存备份</button>${!state.people.length?'<button class="btn primary" data-action="upload-gallery">＋ 导入底库合照</button>':'<button class="btn primary" data-action="confirm-gallery">✓ 核对并确认底库</button>'}`)+
 `<div class="stats">${stat('当前人员编号',state.people.length,'请与完整班级实际人数核对','','▦')}${stat('有效参考人脸',galleryFaces.filter(f=>!f.excluded).length,'同一编号可保留多张参考脸','green','◈')}<div class="stat"><div class="stat-label">底库合照</div><div class="stat-value">${galleryImages.length}<span class="stat-unit">张</span></div><div class="stat-foot">原图位置与参考头像均可追溯</div></div><div class="stat"><div class="stat-label">底库状态</div><div class="stat-value" style="font-size:24px;margin-top:16px;color:var(--teal)">${state.settings.confirmed?'已确认':'待核对'}</div><div class="stat-foot">${state.settings.confirmed?'可以创建新的考勤场次':'确认人数后再开始考勤'}</div></div></div>`+
 `${!state.people.length?`<div class="steps"><div class="step"><span>01 / IMPORT</span><h3>导入完整班级照片</h3><p>上传前两次完整拍摄的合照。第三次较少人的照片留作独立验证。</p><div class="row" style="margin-top:15px"><button class="btn small" data-action="local-import">从项目目录选择</button><button class="btn small" data-action="upload-gallery">上传照片</button></div></div><div class="step"><span>02 / GROUP</span><h3>提取与跨图去重</h3><p>检测每张人脸，并按相似度生成编号。同一照片中同时出现的人不会被自动合并。</p><button class="btn small" style="margin-top:15px" data-action="build" ${!galleryFaces.length?'disabled':''}>生成编号底库 →</button></div><div class="step"><span>03 / REVIEW</span><h3>核对后开始考勤</h3><p>检查是否重复编号或误合并，确认头像与人数。初始化核对只需完成一次。</p></div></div>`:
 `<div class="gallery-toolbar"><div class="row"><input class="search" id="gallery-search" placeholder="搜索编号或名称" value="${esc(search)}"><span style="font-size:11px;color:#8a9a90">${selected.size} 项已选择</span></div><div class="row"><button class="btn small" data-action="suggestions">◈ 检查疑似重复</button><button class="btn small" data-action="merge" ${selected.size<2?'disabled':''}>合并所选编号</button><button class="btn small" data-action="clear-selection">清空选择</button></div></div>`}`+
 `${galleryImages.length?`<div class="hint" style="margin-bottom:20px">${galleryImages.map((i,index)=>`<button class="btn small" data-gallery-image="${i.id}" style="margin:3px">原图 ${index+1} · ${i.faces} 张人脸</button>`).join('')} <span>点击编号卡片勾选；点击「查看参考脸」检查、拆分或更换头像。</span></div>`:''}`+
 `<div class="gallery-grid">${people.map(p=>`<article class="gallery-card ${selected.has(p.id)?'selected':''}" data-select-person="${p.id}"><span class="check">${selected.has(p.id)?'✓':''}</span><img src="${avatar(p.avatar)}" alt="${esc(p.name)}"><h3>${esc(p.name)}</h3><p>${p.samples.length} 张参考脸 · ${new Set(p.samples.map(f=>f.image_id)).size} 张原图</p><button class="btn small" style="margin-top:12px" data-inspect-person="${p.id}">查看参考脸 ↗</button></article>`).join('')}</div>`+footer();
}
async function localImport(kind='gallery'){
 uploadKind=kind;
 const paths=state.local_photos;
 showDialog('选择项目目录中的照片',`<p>底库使用完整班级照片；较少人到场的第三次照片适合作独立考勤验证。</p><div class="local-list">${paths.map((p,i)=>`<label><input type="checkbox" name="local-photo" value="${i}"> ${esc(p)}</label>`).join('')}</div>${!paths.length?'<p>项目目录中尚无可导入照片。</p>':''}`,`<button class="btn" data-action="dismiss">取消</button><button class="btn primary" data-action="local-submit">开始导入</button>`);
}
async function inspectPerson(id){
 const person=state.people.find(p=>p.id===id);if(!person)return;
 showDialog(person.name,`<div class="row"><p>检查是否都是同一个人。只把误归入的参考脸勾选拆出。</p><button class="btn small" data-rename="${id}">修改名称</button></div><div class="samples">${person.samples.map(f=>`<div class="sample"><img src="${avatar(f.id)}" alt="参考脸"><label><input type="checkbox" name="split-face" value="${f.id}">选择拆出</label><p>人脸宽 ${f.face_size}px</p><button class="btn small" data-source-face="${f.id}">定位原图</button><button class="btn small" data-avatar-person="${id}" data-avatar-face="${f.id}" style="margin-top:5px">${person.avatar===f.id?'当前头像':'设为头像'}</button><button class="btn small danger" data-exclude="${f.id}" style="margin-top:5px">排除此脸</button></div>`).join('')}</div>`,`<button class="btn" data-action="dismiss">关闭</button><button class="btn primary" data-action="split">将所选参考脸拆为新编号</button>`);
}
function sourceImage(id,focusId){
 const image=state.images.find(i=>i.id===id);if(!image)return;
 const faces=state.faces.filter(f=>f.image_id===id);
 showDialog('底库原图与检测位置',`<p style="margin-bottom:15px">${esc(image.name)} · 检测 ${image.faces} 张。请检查是否有漏检、重复框或非人脸误检。</p><div class="image-stage"><img src="${photo(id)}" alt="底库原图"><div class="boxes">${faces.map(f=>{
 const [x1,y1,x2,y2]=f.bbox;const p=state.people.find(p=>p.id===f.person_id);
 return `<button class="face-box ${f.excluded?'ignored':''}" data-gallery-face="${f.id}" style="${focusId===f.id?'border-color:#ffcc44;box-shadow:0 0 0 3px #ffcc4480;':''}left:${x1/image.width*100}%;top:${y1/image.height*100}%;width:${(x2-x1)/image.width*100}%;height:${(y2-y1)/image.height*100}%"><span>${esc(p?.name||'未分组')}${f.excluded?' · 已排除':''}</span></button>`;
 }).join('')}</div></div>`);
}
function enlargeImage(id){
 const image=result.images.find(i=>i.id===id);if(!image)return;
 const faces=result.faces.filter(f=>f.image_id===id);
 showDialog('放大核对照片',`<p style="margin-bottom:12px">可横向及纵向滚动，点击框查看身份。框上悬停时显示编号。</p><div class="zoom-viewport"><div class="image-stage zoom-canvas"><img src="${photo(id)}" alt="放大考勤照片"><div class="boxes">${faces.map(f=>{
 const [x1,y1,x2,y2]=f.bbox;const person=result.people.find(p=>p.id===f.person_id);
 return `<button class="face-box ${f.status}" data-resolve="${f.id}" aria-label="${esc(person?.name||'待处理人脸')}" style="left:${x1/image.width*100}%;top:${y1/image.height*100}%;width:${(x2-x1)/image.width*100}%;height:${(y2-y1)/image.height*100}%"><span>${esc(person?.name||(f.excluded?'不计入':'待处理'))}</span></button>`;
 }).join('')}</div></div></div>`);
}
function resolveFace(id){
 const f=result?.faces.find(f=>f.id===id);if(!f)return;
 const person=result.people.find(p=>p.id===f.person_id);
 const locked=result.session.closed;
 showDialog(locked?'识别结果':'确认人脸身份',`<div class="probe-row"><img src="${avatar(id)}" alt="待识别人脸"><div><h3>${esc(person?.name||(f.excluded?'不计入':'未确认身份'))}</h3><p>最高相似度 ${f.score?.toFixed(3)??'—'} · 候选差值 ${f.margin?.toFixed(3)??'—'}</p><p>人脸宽 ${f.face_size}px · ${f.status==='manual'?'人工确认':f.status==='auto'?'自动匹配':'待处理'}</p></div></div><h3 style="margin-top:24px">相似身份候选</h3><div class="candidate-list">${f.candidates.map(c=>`<button class="candidate" data-confirm-face="${id}" data-confirm-person="${c.id}" ${locked?'disabled':''}><img src="${avatar(c.avatar)}" alt="候选头像"><b>${esc(c.name)}</b><small>余弦 ${c.score.toFixed(3)}</small></button>`).join('')}</div>${!locked?`<div class="row"><select class="session-select" id="manual-person"><option value="">从全部编号中选择</option>${result.people.map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join('')}</select><button class="btn" data-manual-face="${id}">确认所选编号</button></div>`:''}<div class="hint" style="margin-top:18px">请结合头像和现场人员核对。余弦分数不是正确概率，不能仅凭分数把外来人员归入班级。</div>`,`${!locked?`<button class="btn danger" data-ignore="${id}">外来人员或无效人脸，不计入</button>`:''}<button class="btn" data-action="dismiss">关闭</button>`);
}
async function galleryEdit(body){await api('/api/gallery/edit',body);await refresh();}
async function handle(action){
 if(action==='dismiss'){modal.close();return;}
 if(action==='go-gallery'){page='gallery';render();return;}
 if(action==='upload-gallery'||action==='upload-attendance'){
  uploadKind=action==='upload-gallery'?'gallery':'attendance';if(uploadKind==='attendance'&&!sessionId)return handle('new-session');$('#file-input').click();return;
 }
 if(action==='local-import')return localImport();
 if(action==='local-attendance')return localImport('attendance');
 if(action==='local-submit'){
  const paths=$$('input[name="local-photo"]:checked').map(e=>state.local_photos[Number(e.value)]);
  modal.close();const job=await api('/api/import-local',{paths,kind:uploadKind,session_id:uploadKind==='attendance'?sessionId:null});await watch(job.job_id);toast('照片处理完成');return;
 }
 if(action==='build'){const job=await api('/api/gallery/build',{});await watch(job.job_id);toast('编号已生成，请检查分组并确认人数');return;}
 if(action==='backup'){const data=await api('/api/backup',{});toast('已备份到 data/backups/'+data.name);return;}
 if(action==='clear-selection'){selected.clear();render();return;}
 if(action==='merge'){
  if(!confirm('确认所选编号属于同一人？合并后会要求重新确认底库。'))return;
  await galleryEdit({action:'merge',ids:[...selected]});selected.clear();render();toast('编号已合并');return;
 }
 if(action==='split'){
  const face_ids=$$('input[name="split-face"]:checked').map(e=>e.value);
  await galleryEdit({action:'split',face_ids});modal.close();toast('参考脸已拆为新编号');return;
 }
 if(action==='confirm-gallery'){
  showDialog('核对班级底库',`<p>当前底库有 <b>${state.people.length}</b> 个有效编号。请确认重复编号已合并、不同同学没有误合并，并检查原图中的漏检。</p><label class="field" style="margin-top:20px">班级准确人数（知道时填写）<input id="expected-count" type="number" min="1" placeholder="暂不确定可留空"></label><div class="hint warn" style="margin-top:18px">检测到的人脸数不等于班级人数。低头或遮挡的同学需要另一张可辨识参考脸。</div>`,`<button class="btn" data-action="dismiss">继续检查</button><button class="btn primary" data-action="confirm-gallery-submit">已核对，确认底库</button>`);return;
 }
 if(action==='confirm-gallery-submit'){
  await galleryEdit({action:'confirm',expected:$('#expected-count').value||null});modal.close();toast('底库已确认，可以开始考勤');return;
 }
 if(action==='new-session'){
  if(!state.people.length){toast('请先导入合照并生成班级底库');page='gallery';render();return;}
  showDialog('新建课堂考勤',`<label class="field">场次名称<input id="session-title" maxlength="80" value="课堂考勤 ${new Date().toLocaleDateString('zh-CN')}"></label><div class="hint ${state.settings.confirmed?'':'warn'}" style="margin-top:16px">${state.settings.confirmed?'本场以已核对的 '+state.people.length+' 人底库为准。':'当前 '+state.people.length+' 个编号未经人工核对，本次仅生成预览结果，不能确认正式缺席名单。'}多张照片累计到场，并按编号自动去重。</div>`,`<button class="btn" data-action="dismiss">取消</button><button class="btn primary" data-action="create-session">${state.settings.confirmed?'创建并开始':'创建预览场次'}</button>`);return;
 }
 if(action==='create-session'){
  const data=await api('/api/sessions',{title:$('#session-title').value,preview:!state.settings.confirmed});sessionId=data.id;localStorage.setItem('sessionId',sessionId);imageId='';filter='absent';modal.close();page='attendance';await refresh();toast(state.settings.confirmed?'场次已创建，请上传现场照片':'已创建预览场次；正式考勤需先核对底库');return;
 }
 if(action==='close-session'){
  if(result.session.provisional){toast('这是底库待核对的预览场次。请核对底库后新建正式考勤。');return;}
  if(result.counts.review){toast('请先处理未识别或冲突人脸，也可标为不计入');return;}
  if(!confirm(`确认本场拍摄已覆盖全部到场人员？结束后将生成 ${result.counts.absent} 人的缺席结果。`))return;
  await api(`/api/sessions/${sessionId}/close`,{});await refresh();toast('本场考勤已结束');return;
 }
 if(action==='suggestions'){
  const suggestions=await api('/api/gallery/suggestions');
  showDialog('疑似重复编号',`<p>以下按特征相似度排序，仅供核对。点击查看两组参考脸后再决定是否合并。</p>${suggestions.map(s=>{const a=state.people.find(p=>p.id===s.a),b=state.people.find(p=>p.id===s.b);return `<div class="suggestion"><span><img src="${avatar(a.avatar)}" style="width:35px;height:38px;object-fit:cover;vertical-align:middle;border-radius:4px"> ${esc(a.name)}　↔　<img src="${avatar(b.avatar)}" style="width:35px;height:38px;object-fit:cover;vertical-align:middle;border-radius:4px"> ${esc(b.name)}　<span class="badge">${s.score}</span></span><button class="btn small" data-compare-a="${a.id}" data-compare-b="${b.id}">查看与合并</button></div>`;}).join('')||'<div class="zero-state">没有达到提示阈值的候选组</div>'}`);return;
 }
}
document.addEventListener('click',async event=>{
 try{
  const button=event.target.closest('button');if(!button)return;
  if(button.dataset.page){page=button.dataset.page;render();return;}
  if(button.dataset.action)return await handle(button.dataset.action);
  if(button.dataset.image){imageId=button.dataset.image;render();return;}
  if(button.dataset.filter){filter=button.dataset.filter;render();return;}
  if(button.dataset.inspectPerson){event.stopPropagation();return inspectPerson(button.dataset.inspectPerson);}
  if(button.dataset.resolve)return resolveFace(button.dataset.resolve);
  if(button.dataset.enlarge)return enlargeImage(button.dataset.enlarge);
  if(button.dataset.person){const p=result.people.find(p=>p.id===button.dataset.person);showDialog(p.name,`<div class="probe-row"><img src="${avatar(p.avatar)}" alt="底库头像"><div><h3>${esc(p.name)}</h3><p>${{present:'已确认到场',absent:result.session.closed?'本场缺席':'尚未匹配，可补传照片',uncertain:'身份待确认'}[p.status]}</p></div></div>`);return;}
  if(button.dataset.galleryImage)return sourceImage(button.dataset.galleryImage);
  if(button.dataset.sourceFace){const f=state.faces.find(f=>f.id===button.dataset.sourceFace);return sourceImage(f.image_id,f.id);}
  if(button.dataset.galleryFace){const f=state.faces.find(f=>f.id===button.dataset.galleryFace);if(f.person_id)return inspectPerson(f.person_id);showDialog('未分组的人脸',`<img src="${avatar(f.id)}" style="width:120px"><p>${f.excluded?'已排除':'生成底库后可以检查分组'}</p>`,!f.excluded?`<button class="btn danger" data-exclude="${f.id}">排除误检人脸</button>`:'');return;}
  if(button.dataset.avatarPerson){await galleryEdit({action:'avatar',id:button.dataset.avatarPerson,face_id:button.dataset.avatarFace});inspectPerson(button.dataset.avatarPerson);return;}
  if(button.dataset.exclude){if(!confirm('确认将这张参考脸排除？这不会删除原照片。'))return;await galleryEdit({action:'exclude',face_id:button.dataset.exclude});modal.close();return;}
  if(button.dataset.rename){const p=state.people.find(p=>p.id===button.dataset.rename);const name=prompt('输入显示名称',p.name);if(name){await galleryEdit({action:'rename',id:p.id,name});inspectPerson(p.id);}return;}
  if(button.dataset.confirmFace||button.dataset.manualFace||button.dataset.ignore){
   const face_id=button.dataset.confirmFace||button.dataset.manualFace||button.dataset.ignore;
   const person_id=button.dataset.confirmPerson||(button.dataset.manualFace?$('#manual-person').value:null);
   if(button.dataset.manualFace&&!person_id){toast('请先选择编号');return;}
   await api(`/api/sessions/${sessionId}/resolve`,{face_id,person_id});modal.close();await refresh();toast(person_id?'身份已确认':'已标记不计入');return;
  }
  if(button.dataset.compareA){
   const a=state.people.find(p=>p.id===button.dataset.compareA),b=state.people.find(p=>p.id===button.dataset.compareB);
   showDialog('核对两个编号',`<div class="comparison">${[a,b].map(p=>`<div><h3>${esc(p.name)}</h3><div class="samples">${p.samples.map(f=>`<div class="sample"><img src="${avatar(f.id)}" alt="参考脸"></div>`).join('')}</div></div>`).join('')}</div>`,`<button class="btn" data-action="dismiss">保持分开</button><button class="btn primary" data-merge-a="${a.id}" data-merge-b="${b.id}">确认同一人并合并</button>`);return;
  }
  if(button.dataset.mergeA){await galleryEdit({action:'merge',ids:[button.dataset.mergeA,button.dataset.mergeB]});modal.close();toast('已合并');return;}
 }catch(error){toast(error.message);}
});
document.addEventListener('click',event=>{
 const card=event.target.closest('[data-select-person]');if(!card||event.target.closest('button'))return;
 const id=card.dataset.selectPerson;selected.has(id)?selected.delete(id):selected.add(id);render();
});
document.addEventListener('change',async event=>{
 if(event.target.id==='session-select'){sessionId=event.target.value;localStorage.setItem('sessionId',sessionId);imageId='';await refresh();}
});
document.addEventListener('input',event=>{
 if(event.target.id==='gallery-search'){search=event.target.value;const pos=event.target.selectionStart;render();$('#gallery-search').focus();$('#gallery-search').setSelectionRange(pos,pos);}
});
async function uploadFiles(files){
 if(!files.length)return;
 const form=new FormData();[...files].forEach(f=>form.append('files',f));form.append('kind',uploadKind);if(uploadKind==='attendance')form.append('session_id',sessionId);
 const response=await fetch('/api/upload',{method:'POST',body:form});const data=await response.json();if(!response.ok)throw new Error(data.error);await watch(data.job_id);toast('照片处理完成');
}
$('#file-input').addEventListener('change',async event=>{try{await uploadFiles(event.target.files);}catch(error){toast(error.message);}finally{event.target.value='';}});
document.addEventListener('dragover',event=>{if(event.target.closest('#drop-zone'))event.preventDefault();});
document.addEventListener('drop',async event=>{if(!event.target.closest('#drop-zone'))return;event.preventDefault();if(!sessionId)return toast('请先创建考勤场次');uploadKind='attendance';try{await uploadFiles(event.dataTransfer.files);}catch(error){toast(error.message);}});
modal.addEventListener('click',event=>{if(event.target===modal)modal.close();});
$('#date').textContent=new Date().toLocaleDateString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit'});
refresh().catch(error=>toast(error.message));
