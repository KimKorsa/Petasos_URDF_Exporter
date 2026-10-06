/* Module ownership is separate from link grouping and controller selection. */
const ModuleEditor = {
    active: false, editing: null, selection: {linkIds: [], jointIds: []}, errors: [], busy: false, marqueeCancel: null,
    enter(id = null) {
        patcherPendingAction = null;
        if (this.marqueeCancel) this.marqueeCancel();
        if (patcherControllerMarqueeCancel) patcherControllerMarqueeCancel();
        this.active = true; this.editing = id; this.errors = [];
        const existing = (treeData._modules || []).find(m => m.id === id);
        this.selection = existing ? {linkIds: [...existing.link_ids], jointIds: [...existing.joint_ids]} : {linkIds: [], jointIds: []};
        patcherControllerSelectionMode = false; patcherControllerJointSelection.clear();
        patcherGroupingMode = false; patcherGroupSelection.clear();
        selectedElement = null; render({skipPreview: true}); this.status();
    },
    cancel() {
        if (this.marqueeCancel) this.marqueeCancel();
        this.active = false; this.editing = null;
        this.selection = {linkIds: [], jointIds: []}; this.errors = [];
        render({skipPreview: true}); this.status('모듈 지정을 취소했습니다.');
    },
    pick(kind, id) {
        if (!id) return;
        this.selection = ModuleSelection.toggleModuleSelection(this.selection, kind, id);
        this.errors = []; render({skipPreview: true}); this.status();
    },
    status(message) {
        const status = document.getElementById('patcher-validation');
        if (status) status.textContent = message || `모듈 수동 선택 · 링크 ${this.selection.linkIds.length} / 내부 조인트 ${this.selection.jointIds.length} · 클릭으로 추가·해제 또는 빈 곳 드래그 · 장착 조인트는 제외 · ESC 취소`;
    },
    async request(path, data) {
        const response = await fetch(path, {method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify(data, (key, value) => key === '_pivot' ? undefined : value)});
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || '모듈 작업 실패');
        return result;
    },
    async action(callback) {
        if (this.busy) return;
        this.busy = true;
        if (workspaceAutosaveTimer) { clearTimeout(workspaceAutosaveTimer); workspaceAutosaveTimer = null; }
        try {
            while (workspaceSaveInFlight) await new Promise(resolve => setTimeout(resolve, 30));
            return await callback();
        } catch (error) { alert(error.message); }
        finally { this.busy = false; }
    },
    async submit() {
        return this.action(async () => {
            const selection = {tree: treeData, link_ids: this.selection.linkIds, joint_ids: this.selection.jointIds, editing_id: this.editing};
            const validation = await this.request('/modules/validate', selection);
            if (!validation.valid) {
                this.errors = validation.errors.flatMap(error => error.ids);
                render({skipPreview: true}); this.status(validation.errors.map(error => error.message).join(' / '));
                return;
            }
            const existing = (treeData._modules || []).find(m => m.id === this.editing);
            const name = await this.askName(existing?.name || 'gripper');
            if (!name) return;
            const result = await this.request(this.editing ? '/modules/update' : '/modules/create',
                {...selection, name, module_id: this.editing, revision: treeData._module_revision});
            this.accept(result, false);
        });
    },
    accept(result, reload) {
        pushHistoryEntry({kind: 'module', token: result.undo_snapshot_id});
        treeData = result.tree; this.active = false; selectedElement = null;
        if (reload) {
            sessionStorage.setItem('petasos-module-history', JSON.stringify(historyStack));
            workspaceAutosaveReady = false; location.reload();
        } else render({skipPreview: true});
    },
    askName(initial) {
        return new Promise(resolve => {
            const dialog=document.createElement('dialog'); dialog.style.cssText='padding:24px;background:#203038;color:#e8f6fa;border:1px solid #38bdf8;border-radius:10px';
            const label=document.createElement('label'); label.textContent='Module name (영문·숫자·밑줄)';
            const input=document.createElement('input'); input.value=initial; input.style.cssText='display:block;margin:12px 0;width:100%'; label.append(input); dialog.append(label);
            let answer=null;
            this.button(dialog,'모듈 이름 적용',()=>{if(/^[A-Za-z][A-Za-z0-9_]*$/.test(input.value)){answer=input.value;dialog.close();}else{input.setCustomValidity(petasosTranslateText('영문자로 시작하는 영문·숫자·밑줄만 사용하세요.'));input.reportValidity();}});
            this.button(dialog,'취소',()=>dialog.close());
            dialog.addEventListener('close',()=>{dialog.remove();resolve(answer);},{once:true});
            document.body.append(dialog);dialog.showModal();input.focus();
        });
    },
    async restore(entry) {
        return this.action(async () => {
            try {
                const result = await this.request('/modules/restore', {snapshot_id: entry.token, revision: treeData._module_revision});
                treeData = result.tree;
                sessionStorage.setItem('petasos-module-history', JSON.stringify(historyStack));
                workspaceAutosaveReady = false; location.reload();
            } catch (error) { historyStack.push(entry); throw error; }
        });
    },
    select(id) {
        if (this.marqueeCancel) this.marqueeCancel();
        this.active = false;
        selectedElement = {type: 'module', moduleId: id};
        const module = (treeData._modules || []).find(m => m.id === id);
        render({skipPreview: true});
        highlight3DComponents(patcherEntries().filter(e => module.link_ids.includes(e.node._link_id)).flatMap(e => e.node.components));
    },
    properties(body, id) {
        const module = (treeData._modules || []).find(m => m.id === id);
        if (!module) { body.textContent = '모듈을 찾을 수 없습니다.'; return; }
        body.replaceChildren();
        const panel = document.createElement('div'); panel.className = 'module-properties'; body.append(panel); body = panel;
        const card = heading => {
            const section = document.createElement('section'); section.className = 'module-property-card';
            const title = document.createElement('h3'); title.textContent = heading;
            section.append(title); body.append(section); return section;
        };
        const settings = card('모듈 설정');
        const nameLabel = document.createElement('label'); nameLabel.className = 'module-properties-name-label';
        nameLabel.textContent = '모듈 이름 (영문·숫자·밑줄)';
        const nameInput = document.createElement('input'); nameInput.className = 'module-properties-name';
        nameInput.type = 'text'; nameInput.value = module.name; nameInput.pattern = '[A-Za-z][A-Za-z0-9_]*';
        nameInput.maxLength = 48; nameInput.setAttribute('aria-label', nameLabel.textContent);
        nameInput.addEventListener('change', () => {
            const name = nameInput.value.trim();
            if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(name)) {
                nameInput.setCustomValidity('영문자로 시작하는 영문·숫자·밑줄만 사용하세요.');
                nameInput.reportValidity(); nameInput.value = module.name; return;
            }
            nameInput.setCustomValidity('');
            if (name === module.name) return;
            module.name = name;
            render({skipPreview: true});
            scheduleWorkspaceAutosave();
        });
        nameLabel.append(nameInput); settings.append(nameLabel);
        const hint = document.createElement('small'); hint.className = 'module-property-hint';
        hint.textContent = '단일 장착 끝단 모듈'; settings.append(hint);
        const contents = card('모듈 구성');
        const counts = document.createElement('div'); counts.className = 'module-property-counts';
        for (const [label, count] of [['링크', module.link_ids.length], ['내부 조인트', module.joint_ids.length]]) {
            const stat = document.createElement('div');
            const caption = document.createElement('span'); caption.textContent = label;
            const value = document.createElement('strong'); value.textContent = String(count);
            stat.append(caption, value); counts.append(stat);
        }
        contents.append(counts);
        const entries = patcherEntries().filter(e => module.link_ids.includes(e.node._link_id));
        const list = document.createElement('ul'); list.className = 'module-properties-links';
        for (const entry of entries) {
            const item = document.createElement('li'); item.textContent = entry.node.name; list.append(item);
        }
        contents.append(list);
        const rootEntry = entries.find(e => e.node._link_id === module.root_link_id);
        const mount = rootEntry?.jointObj;
        const attachment = document.createElement('dl'); attachment.className = 'module-properties-attachment';
        for (const [label, value] of [['부모 링크', rootEntry?.parentNode?.name || '-'], ['장착 조인트', mount?.joint_name || '-']]) {
            const caption = document.createElement('dt'); caption.textContent = label;
            const field = document.createElement('dd'); field.textContent = value;
            attachment.append(caption, field);
        }
        card('장착 정보').append(attachment);
        const removeButton = this.button(body, '모듈 테두리 해제', () => this.action(async () => {
            const result = await this.request('/modules/unassign', {tree: treeData, module_id: id, revision: treeData._module_revision});
            this.accept(result, false);
        }));
        removeButton.className = 'form-control module-property-remove';
        removeButton.title = '모듈 지정을 해제하고 부품과 조인트는 유지합니다.';
        removeButton.style.cssText = '';
    },
    button(container, text, action) {
        const button = document.createElement('button'); button.type = 'button'; button.textContent = text;
        button.style.cssText = 'margin:5px 4px 5px 0;padding:8px;border:1px solid #38bdf8;border-radius:5px;background:#183743;color:#d9f5ff';
        button.onclick = action; container.append(button); return button;
    },
    rectangle(event, viewport) {
        if (!this.active || event.button !== 0 || event.target.closest('.patcher-node,.patcher-joint-label,button,input,select')) return false;
        event.preventDefault(); event.stopPropagation();
        const canvas = document.getElementById('patcher-canvas');
        const rect = canvas.getBoundingClientRect(), zoom = getPatcherView().zoom;
        const point = e => ({x:(e.clientX-rect.left)/zoom,y:(e.clientY-rect.top)/zoom});
        const start = point(event), marquee = document.createElement('div');
        marquee.style.cssText = 'position:absolute;border:1px solid #38bdf8;background:#38bdf822;pointer-events:none;z-index:30';
        canvas.append(marquee);
        const move = e => { const end = point(e); Object.assign(marquee.style,{left:Math.min(start.x,end.x)+'px',top:Math.min(start.y,end.y)+'px',width:Math.abs(end.x-start.x)+'px',height:Math.abs(end.y-start.y)+'px'}); };
        const finish = e => {
            document.removeEventListener('pointermove', move); document.removeEventListener('pointerup', finish); document.removeEventListener('pointercancel', cancel);
            marquee.remove();
            if (this.marqueeCancel === cancel) this.marqueeCancel = null;
            const end = point(e), entries = [];
            canvas.querySelectorAll('[data-module-link],[data-module-joint]').forEach(element => {
                const box = element.getBoundingClientRect();
                entries.push({kind:element.dataset.moduleLink?'link':'joint', id:element.dataset.moduleLink||element.dataset.moduleJoint,
                    x:(box.left+box.width/2-rect.left)/zoom,y:(box.top+box.height/2-rect.top)/zoom});
            });
            this.selection = ModuleSelection.selectModuleRect(this.selection, entries,{x1:start.x,y1:start.y,x2:end.x,y2:end.y},event.ctrlKey||event.metaKey);
            render({skipPreview:true}); this.status();
        };
        const cancel = () => {
            document.removeEventListener('pointermove',move); document.removeEventListener('pointerup',finish); document.removeEventListener('pointercancel',cancel); marquee.remove();
            if (this.marqueeCancel === cancel) this.marqueeCancel = null;
        };
        document.addEventListener('pointermove',move); document.addEventListener('pointerup',finish); document.addEventListener('pointercancel',cancel);
        this.marqueeCancel = cancel;
        return true;
    },
    decorate(canvas) {
        canvas.querySelectorAll('.module-outline').forEach(e => e.remove());
        canvas.querySelectorAll('[data-module-link],[data-module-joint]').forEach(element => {
            const id = element.dataset.moduleLink || element.dataset.moduleJoint;
            const picked = this.active && [...this.selection.linkIds,...this.selection.jointIds].includes(id);
            element.classList.toggle('module-pick-selected', picked);
            element.style.outline = this.errors.includes(id) ? '3px solid #ff6b6b' : picked ? '2px solid #6aafc4' : '';
        });
        (treeData._modules || []).forEach((module, index) => {
            const nodes = [...canvas.querySelectorAll('[data-module-link]')].filter(e => module.link_ids.includes(e.dataset.moduleLink));
            if (!nodes.length) return;
            const left = Math.min(...nodes.map(n=>n.offsetLeft))-16, top = Math.min(...nodes.map(n=>n.offsetTop))-34;
            const right = Math.max(...nodes.map(n=>n.offsetLeft+n.offsetWidth))+16, bottom = Math.max(...nodes.map(n=>n.offsetTop+n.offsetHeight))+16;
            const frame = document.createElement('div'); frame.className = 'module-outline';
            frame.style.cssText = `position:absolute;left:${left}px;top:${top}px;width:${right-left}px;height:${bottom-top}px;border:2px dashed #38bdf8;border-radius:10px;background:#38bdf80a;pointer-events:none;z-index:1`;
            const label = this.button(frame, `⬡ ${module.name}`, () => this.select(module.id));
            label.style.cssText += ';position:absolute;bottom:-32px;left:8px;pointer-events:auto;font-size:11px';
            label.onpointerdown = e => e.stopPropagation(); canvas.append(frame);
        });
        if (this.active) this.status();
    },
    async library(replaceId = null) {
        try {
            document.getElementById('module-library-dialog')?.remove();
            const response = await fetch('/modules/library');
            const library = await response.json();
            const dialog = document.createElement('dialog'); dialog.id = 'module-library-dialog';
            const title = document.createElement('h3'); title.textContent = replaceId ? '모듈 교체' : '모듈 라이브러리'; dialog.append(title);
            const fields = document.createElement('div'); fields.className = 'module-library-fields'; dialog.append(fields);
            const field = (container, name, control) => {
                const label = document.createElement('label'); label.textContent = name;
                label.append(control); container.append(label); return control;
            };
            const choose = field(fields, '라이브러리 모듈', document.createElement('select'));
            (library.items || []).forEach(item => choose.add(new Option(`${item.name} · 링크 ${item.link_count}개`,item.id)));
            if (!choose.options.length) choose.add(new Option('저장된 모듈이 없습니다. ZIP 파일을 가져오세요.', ''));
            const targets = document.createElement('div'); targets.className = 'module-library-targets'; fields.append(targets);
            const parent = field(targets, '장착할 부모 링크', document.createElement('select'));
            patcherEntries().forEach(e => parent.add(new Option(e.node.name, e.node._link_id)));
            if (selectedElement?.type === 'link') parent.value = selectedElement.node._link_id;
            const oldModule = (treeData._modules || []).find(m=>m.id===replaceId);
            if (oldModule) {
                const rootEntry = patcherEntries().find(e=>e.node._link_id===oldModule.root_link_id);
                parent.value = rootEntry.parentNode._link_id; parent.disabled = true;
            }
            const prefix = field(targets, '이름 접두어', document.createElement('input')); prefix.placeholder = '예: tool_'; prefix.value = 'tool_';
            const placement = document.createElement('div'); placement.className = 'module-library-placement'; fields.append(placement);
            const placementTitle = document.createElement('div'); placementTitle.className = 'module-library-section-title'; placementTitle.textContent = '장착 위치 · 부모 링크 기준'; placement.append(placementTitle);
            const poseGrid = document.createElement('div'); poseGrid.className = 'module-library-pose-grid'; placement.append(poseGrid);
            const values = [];
            ['X (mm)','Y (mm)','Z (mm)','Roll (°)','Pitch (°)','Yaw (°)'].forEach(label => {
                const input = document.createElement('input'); input.type='number'; input.value='0'; input.step='any'; input.disabled=!!replaceId;
                values.push(field(poseGrid, label, input));
            });
            const note = document.createElement('p'); note.className = 'module-library-note'; note.textContent=replaceId?'장착 조인트의 위치·방향·설정을 그대로 유지합니다.':'미리보기로 구성을 확인한 후 장착하세요.'; dialog.append(note);
            const payload = () => ({tree:treeData,library_id:choose.value,parent_link_id:parent.value,prefix:prefix.value,
                xyz_m:values.slice(0,3).map(e=>Number(e.value)/1000),rpy_rad:values.slice(3).map(e=>Number(e.value)*Math.PI/180),replace_id:replaceId,revision:treeData._module_revision});
            const upload=document.createElement('input'); upload.type='file'; upload.accept='.zip'; upload.onchange=()=>this.action(async()=>{
                const form=new FormData(); form.append('file',upload.files[0]); const response=await fetch('/modules/library/import',{method:'POST',body:form});
                const result=await response.json(); if(!response.ok) throw new Error(result.error); dialog.close(); await this.library(replaceId);
            });
            const uploadField = document.createElement('div'); uploadField.className = 'module-library-upload'; field(uploadField, 'ZIP 가져오기', upload); dialog.append(uploadField);
            const actions = document.createElement('div'); actions.className = 'module-library-actions'; dialog.append(actions);
            const actionButton = (text, action, className = '') => {
                const button = this.button(actions, text, action); button.removeAttribute('style'); button.className = className; return button;
            };
            actionButton('미리보기',()=>this.action(async()=>{ const result=await this.request('/modules/preview',payload()); note.textContent=`${result.changes.module} · ${result.changes.links} links · ${result.changes.message}`; }));
            actionButton('ZIP 내보내기',()=>{if(choose.value) location.href=`/modules/library/${choose.value}/download`;});
            actionButton('닫기',()=>dialog.close(), 'module-library-close');
            actionButton(replaceId?'교체 적용':'장착 적용',()=>this.action(async()=>{ const result=await this.request('/modules/apply',payload()); dialog.close(); this.accept(result,true); }), 'module-library-primary');
            document.body.append(dialog); dialog.showModal();
        } catch(error) { alert(error.message); }
    }
};
function enterModuleSelection(id = null) { ModuleEditor.enter(id); }
function submitModuleSelection() { ModuleEditor.submit(); }
function renderModuleProperties(id) { ModuleEditor.properties(document.getElementById('panel-body'),id); }
function openModuleLibrary() { ModuleEditor.library(); }
window.addEventListener('load', () => {
    try { const saved=sessionStorage.getItem('petasos-module-history'); if(saved){historyStack=JSON.parse(saved); sessionStorage.removeItem('petasos-module-history');} } catch (_) {}
});
