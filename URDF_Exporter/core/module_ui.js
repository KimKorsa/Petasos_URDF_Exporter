/* Module ownership is separate from link grouping and controller selection. */
const ModuleEditor = {
    active: false, editing: null, selection: {linkIds: [], jointIds: []}, errors: [], busy: false,
    enter(id = null) {
        this.active = true; this.editing = id; this.errors = [];
        const existing = (treeData._modules || []).find(m => m.id === id);
        this.selection = existing ? {linkIds: [...existing.link_ids], jointIds: [...existing.joint_ids]} : {linkIds: [], jointIds: []};
        patcherControllerSelectionMode = false; patcherControllerJointSelection.clear();
        patcherGroupingMode = false; patcherGroupSelection.clear();
        selectedElement = null; render({skipPreview: true}); this.status();
    },
    cancel() { this.active = false; this.errors = []; render({skipPreview: true}); },
    pick(kind, id, event) {
        if (!id) return;
        if (!event.ctrlKey && !event.metaKey) this.selection = {linkIds: [], jointIds: []};
        this.selection = ModuleSelection.toggleModuleSelection(this.selection, kind, id);
        this.errors = []; render({skipPreview: true}); this.status();
    },
    status(message) {
        const status = document.getElementById('patcher-validation');
        if (status) status.textContent = message || `모듈 수동 선택 · 링크 ${this.selection.linkIds.length} / 내부 조인트 ${this.selection.jointIds.length} · Ctrl+클릭 또는 빈 곳 드래그 · 장착 조인트는 제외 · ESC 취소`;
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
            this.button(dialog,'모듈 이름 적용',()=>{if(/^[A-Za-z][A-Za-z0-9_]*$/.test(input.value)){answer=input.value;dialog.close();}else{input.setCustomValidity('영문자로 시작하는 영문·숫자·밑줄만 사용하세요.');input.reportValidity();}});
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
        this.active = false;
        selectedElement = {type: 'module', moduleId: id};
        const module = (treeData._modules || []).find(m => m.id === id);
        highlight3DComponents(patcherEntries().filter(e => module.link_ids.includes(e.node._link_id)).flatMap(e => e.node.components));
        updatePanel();
    },
    properties(body, id) {
        const module = (treeData._modules || []).find(m => m.id === id);
        if (!module) { body.textContent = '모듈을 찾을 수 없습니다.'; return; }
        body.replaceChildren();
        const title = document.createElement('h3'); title.textContent = `Module · ${module.name}`;
        body.append(title);
        const info = document.createElement('p'); info.textContent = `링크 ${module.link_ids.length} · 내부 조인트 ${module.joint_ids.length} · 단일 장착 끝단 모듈`;
        body.append(info);
        const entries = patcherEntries().filter(e => module.link_ids.includes(e.node._link_id));
        const list = document.createElement('p'); list.textContent = entries.map(e => e.node.name).join(' · '); body.append(list);
        const rootEntry = entries.find(e => e.node._link_id === module.root_link_id);
        const mount = rootEntry?.jointObj;
        const attachment = document.createElement('p'); attachment.textContent = `장착: ${rootEntry?.parentNode?.name || '-'} → ${mount?.joint_name || '-'}`; body.append(attachment);
        const inputs = [];
        const infoValues = [...(mount?.joint_info?.xyz || [0,0,0]).map(v=>v*1000),...(mount?.joint_info?._manual_rpy || mount?.joint_info?.rpy || [0,0,0]).map(v=>v*180/Math.PI)];
        ['X (mm)','Y (mm)','Z (mm)','Roll (°)','Pitch (°)','Yaw (°)'].forEach((name,index)=>{
            const label = document.createElement('label'); label.textContent=name; label.style.cssText='display:inline-block;width:32%;margin:6px 0';
            const input=document.createElement('input'); input.type='number'; input.step='any'; input.value=Number(infoValues[index].toFixed(5)); input.style.width='90%';
            inputs.push(input); label.append(input); body.append(label);
        });
        this.button(body,'장착 좌표 적용',()=>this.action(async()=>{
            const result=await this.request('/modules/placement',{tree:treeData,module_id:id,revision:treeData._module_revision,
                xyz_m:inputs.slice(0,3).map(i=>Number(i.value)/1000),rpy_rad:inputs.slice(3).map(i=>Number(i.value)*Math.PI/180)});
            this.accept(result,true);
        }));
        this.button(body, '범위 수정', () => this.enter(id));
        this.button(body, '라이브러리에 저장', () => this.action(async () => {
            await this.request('/modules/library/save', {tree: treeData, module_id: id, revision: treeData._module_revision});
            alert('모듈 라이브러리에 저장했습니다.');
        }));
        this.button(body, '다른 모듈로 교체', () => this.library(id));
        this.button(body, '모듈 지정 해제 (부품 유지)', () => this.action(async () => {
            const result = await this.request('/modules/unassign', {tree: treeData, module_id: id, revision: treeData._module_revision});
            this.accept(result, false);
        }));
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
            const end = point(e), entries = [];
            canvas.querySelectorAll('[data-module-link],[data-module-joint]').forEach(element => {
                const box = element.getBoundingClientRect();
                entries.push({kind:element.dataset.moduleLink?'link':'joint', id:element.dataset.moduleLink||element.dataset.moduleJoint,
                    x:(box.left+box.width/2-rect.left)/zoom,y:(box.top+box.height/2-rect.top)/zoom});
            });
            this.selection = ModuleSelection.selectModuleRect(this.selection, entries,{x1:start.x,y1:start.y,x2:end.x,y2:end.y},event.ctrlKey||event.metaKey);
            render({skipPreview:true}); this.status();
        };
        const cancel = () => { document.removeEventListener('pointermove',move); document.removeEventListener('pointerup',finish); document.removeEventListener('pointercancel',cancel); marquee.remove(); };
        document.addEventListener('pointermove',move); document.addEventListener('pointerup',finish); document.addEventListener('pointercancel',cancel);
        return true;
    },
    decorate(canvas) {
        canvas.querySelectorAll('.module-outline').forEach(e => e.remove());
        canvas.querySelectorAll('[data-module-link],[data-module-joint]').forEach(element => {
            const id = element.dataset.moduleLink || element.dataset.moduleJoint;
            const picked = this.active && [...this.selection.linkIds,...this.selection.jointIds].includes(id);
            element.style.outline = this.errors.includes(id) ? '3px solid #ff6b6b' : picked ? '3px solid #38bdf8' : '';
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
            dialog.style.cssText = 'width:460px;max-width:90vw;max-height:80vh;overflow:auto;background:#202c31;color:#e8f6fa;border:1px solid #38bdf8;border-radius:10px;padding:20px';
            const title = document.createElement('h3'); title.textContent = replaceId ? '모듈 교체' : '모듈 라이브러리'; dialog.append(title);
            const choose = document.createElement('select'); choose.style.width = '100%';
            (library.items || []).forEach(item => choose.add(new Option(`${item.name} · ${item.link_count} links`,item.id))); dialog.append(choose);
            const parent = document.createElement('select'); parent.style.cssText = 'width:100%;margin-top:12px';
            patcherEntries().forEach(e => parent.add(new Option(`Parent · ${e.node.name}`, e.node._link_id)));
            if (selectedElement?.type === 'link') parent.value = selectedElement.node._link_id;
            const oldModule = (treeData._modules || []).find(m=>m.id===replaceId);
            if (oldModule) {
                const rootEntry = patcherEntries().find(e=>e.node._link_id===oldModule.root_link_id);
                parent.value = rootEntry.parentNode._link_id; parent.disabled = true;
            }
            dialog.append(parent);
            const prefix = document.createElement('input'); prefix.placeholder = 'Prefix · tool_'; prefix.value = 'tool_'; prefix.style.cssText='width:100%;margin:12px 0'; dialog.append(prefix);
            const values = [];
            ['X (mm)','Y (mm)','Z (mm)','Roll (°)','Pitch (°)','Yaw (°)'].forEach(label => {
                const wrapper = document.createElement('label'); wrapper.style.cssText='display:inline-block;width:32%;margin-bottom:8px'; wrapper.textContent=label;
                const input = document.createElement('input'); input.type='number'; input.value='0'; input.step='any'; input.style.width='90%'; input.disabled=!!replaceId;
                values.push(input); wrapper.append(input); dialog.append(wrapper);
            });
            const note = document.createElement('p'); note.textContent=replaceId?'장착 조인트의 위치·방향·설정을 그대로 유지합니다.':'부모 링크 기준 좌표입니다. 미리보기로 구성을 확인한 후 장착하세요.'; dialog.append(note);
            const payload = () => ({tree:treeData,library_id:choose.value,parent_link_id:parent.value,prefix:prefix.value,
                xyz_m:values.slice(0,3).map(e=>Number(e.value)/1000),rpy_rad:values.slice(3).map(e=>Number(e.value)*Math.PI/180),replace_id:replaceId,revision:treeData._module_revision});
            this.button(dialog,'미리보기',()=>this.action(async()=>{ const result=await this.request('/modules/preview',payload()); note.textContent=`${result.changes.module} · ${result.changes.links} links · ${result.changes.message}`; }));
            this.button(dialog,replaceId?'교체 적용':'장착 적용',()=>this.action(async()=>{ const result=await this.request('/modules/apply',payload()); dialog.close(); this.accept(result,true); }));
            this.button(dialog,'ZIP 내보내기',()=>{if(choose.value) location.href=`/modules/library/${choose.value}/download`;});
            const upload=document.createElement('input'); upload.type='file'; upload.accept='.zip'; upload.onchange=()=>this.action(async()=>{
                const form=new FormData(); form.append('file',upload.files[0]); const response=await fetch('/modules/library/import',{method:'POST',body:form});
                const result=await response.json(); if(!response.ok) throw new Error(result.error); dialog.close(); await this.library(replaceId);
            }); dialog.append(upload);
            this.button(dialog,'닫기',()=>dialog.close()); document.body.append(dialog); dialog.showModal();
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
