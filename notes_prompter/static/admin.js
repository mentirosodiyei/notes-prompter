(() => {
  "use strict";
  const tr = window.NPI18n.t;
  const $ = id => document.getElementById(id);
  let state = null, selectedSource = null, selectedPreset = null, ruleIndex = null;
  let dirty = false, metadataDirty = false, loading = false, saving = false, revision = 0;
  let optionSignature = "", presentationSignature = "";
  let liveQueue = null, liveSending = false, liveTimer = null;
  let autoFontScope = "", autoFontMinimum = 48;
  const draggingSpeeds = new Set();
  const activeId = () => state?.effective_preset_id || null;
  const speedLabel = value => `${value > 0 ? "+" : ""}${value} px/s · ${value < 0 ? tr("retrocede") : value > 0 ? tr("avanza") : tr("detenido")}`;
  const nameKey = name => (name || "").replace(/\\/g,"/").split("/").pop().replace(/\.ppt[xm]?$/i,"").toLocaleLowerCase();
  function knownPresentation(name) {return state?.presentations?.find(item => nameKey(item.name) === nameKey(name));}
  function boundTotal(item) {return item?.presentation ? knownPresentation(item.presentation)?.total || item.presentation_total || null : null;}
  function scope() {return {source:state.source,presentation:state.slide.presentation,index:state.slide.index};}
  function feedback(message, error = false) {
    $("feedback").textContent = message;
    $("feedback").classList.toggle("error", error);
  }
  async function request(url, options = {}) {
    const response = await fetch(url, {cache:"no-store", ...options});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : tr("Revisa los valores e inténtalo de nuevo."));
    return data;
  }
  function jsonOptions(method, value) {
    return {method, headers:{"Content-Type":"application/json"}, body:JSON.stringify(value)};
  }
  function preset() {return state?.presets.find(item => item.id === selectedPreset);}
  function values() {
    return {auto_scroll:$("auto-scroll").checked, font_mode:$("fixed-font").checked ? "fixed" : "auto", min_font_px:Number($("min-font").value),
      speed_px_s:Number($("speed").value), start_delay_s:Number($("delay").value)};
  }
  function labels() {
    const value = values();
    $("font-caption").textContent=value.font_mode === "fixed" ? tr("Tamaño de letra fijo") : tr("Letra mínima · Ampliación automática");
    $("font-value").textContent = `${value.min_font_px} px`;
    $("speed-value").textContent = speedLabel(value.speed_px_s);
    markZero("speed");
    $("delay-value").textContent = `${value.start_delay_s} s`;
    $("speed").disabled = $("delay").disabled = saving || !value.auto_scroll;
  }
  function setValues(value) {
    $("auto-scroll").checked=value.auto_scroll; $("fixed-font").checked=value.font_mode==="fixed"; $("min-font").value=value.min_font_px;
    $("speed").value=value.speed_px_s; $("delay").value=value.start_delay_s; labels();
  }
  function guardChanges(includeMetadata = true) {
    if (!dirty && (!includeMetadata || !metadataDirty)) return true;
    return window.confirm(tr("Hay cambios sin guardar. ¿Quieres descartarlos y continuar?"));
  }
  function presetPayload(item) {
    return {name:$("preset-name").value.trim(), presentation:$("preset-presentation").value.trim() || null,
      presentation_total:knownPresentation($("preset-presentation").value)?.total || (nameKey(item.presentation)===nameKey($("preset-presentation").value) ? item.presentation_total : null),
      defaults:{...item.defaults}, rules:structuredClone(item.rules)};
  }
  function setBusy(busy) {
    for (const element of document.querySelectorAll("button, #preset-select, #reading-form input, #preset-metadata input, #preset-metadata select, #rule-slide")) element.disabled=busy;
    if (!busy && state) {renderPresets(); renderSources(); labels();}
  }
  async function mutate(action) {
    if (saving) return;
    saving=true; revision++; setBusy(true);
    try {await action();} catch(error) {feedback(error.message,true);}
    finally {saving=false; setBusy(false); await refresh();}
  }
  function renderSources() {
    const container = $("sources");
    container.replaceChildren();
    for (const source of state.sources) {
      const label = document.createElement("label");
      label.className = "source" + (selectedSource === source.id ? " selected" : "");
      const radio = document.createElement("input");
      radio.type = "radio"; radio.name = "source"; radio.value = source.id; radio.checked = selectedSource === source.id;
      radio.addEventListener("change", () => {selectedSource = source.id; renderSources();});
      const content = document.createElement("div");
      const name = document.createElement("strong"); name.textContent = source.kind === "local" ? tr("PowerPoint de este equipo") : source.name;
      const info = document.createElement("small"); info.textContent = source.kind === "local" ? source.name : `${source.presentation || tr("Sin presentación")} · ${source.id}`;
      content.append(name, info); label.append(radio, content); container.append(label);
    }
    $("apply-source").disabled = saving || !state.source_enabled || !state.sources.some(s => s.id === selectedSource) || selectedSource === state.source;
    const current = state.sources.find(s => s.id === state.source);
    $("current-source").textContent = current ? tr("Actual: {0}", current.kind === "local" ? tr("este equipo") : current.name) : tr("Origen no disponible");
    $("source-help").textContent = state.source_enabled ? tr("Los agentes aparecen automáticamente mientras están en tu red.") : tr("Abre el receptor en modo Escuchar para seleccionar equipos desde su panel.");
  }
  function renderPresets() {
    if (selectedPreset === null) selectedPreset=activeId() || state.active_preset_id || "";
    const signature=JSON.stringify(state.presets.map(item => [item.id,item.name]));
    if (signature !== optionSignature) {
      optionSignature=signature;
      $("preset-select").replaceChildren(new Option(tr("Lectura general · Sin preset"), ""),
        ...state.presets.map(item => new Option(item.name,item.id)));
    }
    $("preset-select").value=selectedPreset;
    const item=preset();
    $("duplicate-preset").disabled=$("delete-preset").disabled=saving || !item;
    $("activate-preset").disabled=saving || dirty || metadataDirty || Boolean(item && !item.presentation) || (selectedPreset || null)===activeId();
    $("activate-preset").textContent=selectedPreset ? tr("Activar preset") : tr("Usar lectura general");
    $("preset-metadata").hidden=!item;
    renderPresentations();
    if (item && !metadataDirty) {$("preset-name").value=item.name; $("preset-presentation").value=item.presentation || "";}
    $("auto-preset").checked=Boolean(state.auto_select_presentation);
    const total=boundTotal(item);
    $("rule-slide").max=total || 99999;
    $("slide-count").textContent=total ? tr("de {0} diapositivas detectadas", total) : tr("Vincula un PowerPoint para detectar sus diapositivas.");
    const draftPresentation=metadataDirty ? $("preset-presentation").value : item?.presentation;
    const draftTotal=knownPresentation(draftPresentation)?.total || (draftPresentation===item?.presentation ? total : null);
    $("presentation-summary").textContent=draftPresentation ? `${draftPresentation} · ${draftTotal ? draftTotal+tr(" diapositivas detectadas") : tr("abre el PPT o elige su archivo para detectar el total")}` : tr("Elige un archivo o usa la presentación actual. El archivo no se modifica ni se guarda en el master.");
    const active=state.presets.find(p => p.id===activeId());
    $("active-preset").textContent=tr("En uso: {0}.", active ? active.name : tr("lectura general")) +
      ((selectedPreset || null)!==activeId() ? tr(" Estás editando una configuración distinta de la activa.") : "");
    $("edit-slide").disabled=saving || !item || !total;
    $("edit-current-slide").disabled=saving || !item || !state.slide.index || (item.presentation && nameKey(item.presentation)!==nameKey(state.slide.presentation));
    $("use-current-presentation").disabled=saving || !state.slide.presentation;
    $("edit-defaults").hidden=ruleIndex===null;
    $("reading-title").textContent=ruleIndex===null ? tr("Lectura por defecto") : tr("Lectura · Diapositiva {0}", ruleIndex);
    $("editing-target").textContent=item ? `${item.name} · ${ruleIndex===null ? tr("Valores por defecto") : tr("Diapositiva ")+ruleIndex}` : tr("Editando: lectura general");
    $("save-reading").textContent=ruleIndex!==null ? tr("Guardar diapositiva") : item ? tr("Guardar valores por defecto") : tr("Guardar lectura general");
    $("save-and-activate").hidden=!item;
    $("save-and-activate").disabled=saving || !item?.presentation;
    $("save-and-activate").textContent=ruleIndex!==null ? tr("Guardar diapositiva y usar preset") : tr("Guardar y usar preset");
    $("reading-hint").textContent=ruleIndex!==null ? tr("Esta regla solo se aplica a esta diapositiva.") : item ? tr("Se usan en las diapositivas sin regla propia.") : tr("Se usan sin preset o si no coincide la presentación.");
    if (!dirty) setValues(item ? (ruleIndex===null ? item.defaults : item.rules[ruleIndex] || item.defaults) : state.display_settings);
    renderRules();
  }
  function renderRules() {
    const item=preset(), body=$("rules-table");
    body.replaceChildren();
    const indices=item ? Object.keys(item.rules).map(Number).sort((a,b)=>a-b) : [];
    const outside=boundTotal(item) ? indices.filter(index=>index>boundTotal(item)).length : 0;
    $("rules-help").textContent=item ? tr("{0} regla(s). El resto de diapositivas usa los valores por defecto de este preset.{1}", indices.length, outside ? tr(" Hay ")+outside+tr(" regla(s) fuera del total actual; revísalas si has cambiado el PPT.") : "") : tr("Crea o selecciona un preset para programar diapositivas.");
    if (!indices.length) {
      const row=document.createElement("tr"), cell=document.createElement("td");
      cell.colSpan=6; cell.className="empty-rule"; cell.textContent=tr("Todavía no hay reglas por diapositiva."); row.append(cell); body.append(row);
    }
    for (const index of indices) {
      const value=item.rules[index], row=document.createElement("tr");
      for (const text of [index, value.auto_scroll ? tr("Desplazamiento") : tr("Páginas manuales"), `${value.min_font_px} px`, value.auto_scroll ? `${value.speed_px_s} px/s` : "—", value.auto_scroll ? `${value.start_delay_s} s` : "—"]) {
        const cell=document.createElement("td"); cell.textContent=text; row.append(cell);
      }
      const cell=document.createElement("td"), edit=document.createElement("button"), remove=document.createElement("button");
      edit.textContent=tr("Editar"); edit.className="secondary"; edit.disabled=saving; edit.setAttribute("aria-label",tr("Editar diapositiva {0}", index));
      edit.addEventListener("click",()=>selectRule(index));
      remove.textContent=tr("Quitar"); remove.className="secondary danger"; remove.disabled=saving; remove.setAttribute("aria-label",tr("Quitar regla de diapositiva {0}", index));
      remove.addEventListener("click",()=>{
        if (!guardChanges() || !window.confirm(tr("¿Quitar la regla de la diapositiva {0}? Usará los valores por defecto.", index))) return;
        const payload={name:item.name,presentation:item.presentation,presentation_total:item.presentation_total,defaults:item.defaults,rules:structuredClone(item.rules)};
        delete payload.rules[index];
        mutate(async()=>{await request(`/api/admin/presets/${item.id}`,jsonOptions("PUT",payload)); dirty=metadataDirty=false; if(ruleIndex===index) ruleIndex=null; feedback(tr("Regla de la diapositiva {0} eliminada.", index));});
      });
      cell.append(edit,remove); row.append(cell); body.append(row);
    }
  }
  function selectRule(index) {
    const total=boundTotal(preset()) || 99999;
    if (!preset() || !Number.isInteger(index) || index<1 || index>total) {feedback(tr("Elige una diapositiva entre 1 y {0}.", total),true); return;}
    if (!guardChanges(false)) return;
    ruleIndex=index; dirty=false; $("rule-slide").value=index; renderPresets();
    $("reading-title").scrollIntoView({block:"center",behavior:"smooth"});
  }
  function render(next) {
    if (selectedSource===null || selectedSource===state?.source) selectedSource=next.source;
    state=next;
    $("settings-error").hidden=!state.settings_error;
    $("settings-error").textContent=state.settings_error || "";
    if(selectedPreset && !state.presets.some(item=>item.id===selectedPreset)){selectedPreset=state.active_preset_id || "";ruleIndex=null;dirty=metadataDirty=false;}
    $("computer").textContent=tr("Master: {0} · {1}", state.computer, location.host);
    $("master-version").textContent=tr("Master {0} · v{1}", state.computer, state.version || tr("sin identificar"));
    $("connection").textContent=tr("● Conectado"); $("connection").classList.remove("offline");
    renderSources(); renderPresets(); renderLive();
    const slide=state.slide;
    $("slide-meta").textContent=slide.presentation ? tr("{0} · Diapositiva {1} de {2}", slide.presentation, slide.index, slide.total) : tr("Sin presentación activa");
    $("preview-notes").textContent=slide.notes || (slide.presentation ? tr("Esta diapositiva no tiene notas.") : tr("Esperando las notas del equipo seleccionado…"));
    const sourceError=document.getElementById("source-error");
    if(sourceError) { sourceError.textContent=state.source_error || ""; sourceError.hidden=!state.source_error; }
    const context=state.reading_context;
    $("active-reading").textContent=!context.preset ? tr("Lectura general.") : !context.matches ? tr("Preset {0}: no coincide la presentación; se usa la lectura general.", context.preset) : `${context.preset} · ${context.rule_slide ? tr("Regla de diapositiva ")+context.rule_slide : tr("Valores por defecto del preset")}.`;
  }
  function renderPresentations() {
    const choices=new Map((state.presentations || []).map(item => [item.name,item.total]));
    for(const item of state.presets) if(item.presentation && !choices.has(item.presentation)) choices.set(item.presentation,item.presentation_total);
    const signature=JSON.stringify([...choices]);
    if(signature!==presentationSignature) {
      const selected=$("preset-presentation").value;
      $("preset-presentation").replaceChildren(new Option(tr("Selecciona un PowerPoint…"),""), ...[...choices].map(([name,total])=>new Option(`${name}${total ? " · "+total+tr(" diapositivas") : ""}`,name)));
      $("preset-presentation").value=selected;
      presentationSignature=signature;
    }
  }
  function renderLive() {
    const enabled=Boolean(state.slide.presentation && state.slide.index);
    const value=state.effective_display_settings;
    const programmed=state.programmed_display_settings || state.display_settings;
    const fontScope=JSON.stringify([scope(),programmed]);
    if(fontScope!==autoFontScope) {
      autoFontScope=fontScope;
      autoFontMinimum=programmed.font_mode==="auto" ? programmed.min_font_px :
        state.display_settings.font_mode==="auto" ? state.display_settings.min_font_px : 48;
    }
    if(value.font_mode==="auto") autoFontMinimum=value.min_font_px;
    const editingActive=(selectedPreset || null)===activeId();
    $("effective-reading").textContent=tr("En pantalla: {0} px{1} · {2} px/s.", value.min_font_px, value.font_mode === "fixed" ? tr(" fijos") : tr(" mínimos (ampliación automática)"), value.speed_px_s) +
      (state.live_adjustment ? tr(" Hay un ajuste temporal en directo.") : "") +
      (!editingActive ? tr(" El preset que estás editando no está en uso; pulsa Guardar y usar preset para activarlo.") : "");
    if(!liveSending && !liveQueue && !liveTimer) {
      $("live-font").value=value.min_font_px;
      $("live-speed").value=value.speed_px_s;
      $("live-scroll").checked=value.auto_scroll;
      $("live-auto-font").checked=value.font_mode==="auto";
    }
    $("live-font-value").textContent=`${$("live-font").value} px${$("live-auto-font").checked ? tr(" mínimos · automático") : tr(" fijos")}`;
    $("live-speed-value").textContent=speedLabel(Number($("live-speed").value));
    markZero("live-speed");
    $("pause-scroll").textContent=state.playback?.paused ? tr("Reanudar") : tr("Pausar");
    $("pause-scroll").setAttribute("aria-pressed",String(Boolean(state.playback?.paused)));
    $("pause-scroll").disabled=!enabled || !value.auto_scroll || saving;
    $("restart-scroll").disabled=!enabled || saving;
    $("live-font").disabled=$("live-auto-font").disabled=$("live-scroll").disabled=!enabled;
    $("live-speed").disabled=!enabled || !$("live-scroll").checked;
    $("save-live-slide").disabled=!enabled || !state.presets.find(p=>p.id===activeId())?.presentation || liveSending || Boolean(liveQueue) || Boolean(liveTimer);
    $("reset-live").disabled=!enabled || !state.live_adjustment || liveSending;
    $("live-target").textContent=enabled ? tr("{0} · Diapositiva {1} de {2}", state.slide.presentation, state.slide.index, state.slide.total) : tr("Esperando una diapositiva…");
    $("live-status").textContent=state.live_adjustment ? tr("Ajuste en directo aplicado. Al cambiar de diapositiva se recupera su programación.") : tr("Los cambios se aplican al instante. Guarda aquí para incorporarlos al preset de esta diapositiva.");
  }
  async function flushLive() {
    liveTimer=null;
    if(liveSending || !liveQueue) return;
    liveSending=true;
    try {
      while(liveQueue) {
        const payload=liveQueue;liveQueue=null;
        render(await request("/api/admin/live-settings",jsonOptions("PUT",payload)));
      }
    } catch(error) {liveQueue=null;feedback(error.message,true);}
    finally {liveSending=false;renderLive();await refresh();}
  }
  function queueLive(field) {
    if(!state?.slide.index) return;
    const target=scope();
    // A queued change keeps its slide scope; it must never leak into the next slide.
    if(!liveQueue || JSON.stringify([liveQueue.source,liveQueue.presentation,liveQueue.index])!==JSON.stringify([target.source,target.presentation,target.index])) liveQueue=target;
    if(field==="font") {liveQueue.min_font_px=Number($("live-font").value);liveQueue.font_mode="fixed";$("live-auto-font").checked=false;}
    if(field==="font-mode") {
      liveQueue.font_mode=$("live-auto-font").checked ? "auto" : "fixed";
      if($("live-auto-font").checked) $("live-font").value=autoFontMinimum;
      liveQueue.min_font_px=Number($("live-font").value);
    }
    if(field==="speed") liveQueue.speed_px_s=Number($("live-speed").value);
    if(field==="scroll") liveQueue.auto_scroll=$("live-scroll").checked;
    clearTimeout(liveTimer);liveTimer=setTimeout(flushLive,100);renderLive();
  }
  $("live-font").addEventListener("input",()=>queueLive("font"));
  $("live-auto-font").addEventListener("change",()=>queueLive("font-mode"));
  $("live-speed").addEventListener("input",()=>queueLive("speed"));
  function wheelSpeed(id) {
    const slider=$(id);
    slider.addEventListener("wheel",event=>{
      if(slider.disabled || event.ctrlKey || !event.deltaY) return;
      event.preventDefault();
      slider.focus({preventScroll:true});
      const before=slider.value;
      slider.stepUp(event.deltaY < 0 ? 1 : -1);
      if(slider.value!==before) slider.dispatchEvent(new Event("input",{bubbles:true}));
    },{passive:false});
  }
  wheelSpeed("live-speed");
  wheelSpeed("speed");
  function markZero(id) {
    const slider=$(id);
    slider.closest(".speed-track").classList.toggle("at-zero",Number(slider.value)===0);
    slider.setAttribute("aria-valuetext",speedLabel(Number(slider.value)));
  }
  for(const id of ["live-speed","speed"]) {
    const slider=$(id);
    slider.addEventListener("pointerdown",()=>draggingSpeeds.add(slider));
    slider.addEventListener("keydown",()=>draggingSpeeds.delete(slider));
    slider.addEventListener("input",event=>{
      // Wheel/keyboard keep their exact 1 px/s steps; only pointer drags snap.
      if(event.isTrusted && draggingSpeeds.has(slider) && Math.abs(Number(slider.value))<=4) slider.value="0";
      markZero(id);
    },{capture:true});
  }
  for(const event of ["pointerup","pointercancel"]) document.addEventListener(event,()=>draggingSpeeds.clear());
  window.addEventListener("blur",()=>draggingSpeeds.clear());
  function playback(action) {
    const target=scope();
    mutate(async()=>render(await request("/api/admin/playback",jsonOptions("POST",{...target,action}))));
  }
  $("pause-scroll").addEventListener("click",()=>playback(state.playback?.paused ? "resume" : "pause"));
  $("restart-scroll").addEventListener("click",()=>playback("restart"));
  $("live-scroll").addEventListener("change",()=>queueLive("scroll"));
  $("save-live-slide").addEventListener("click",()=>{
    const target=scope();
    mutate(async()=>{render(await request("/api/admin/live-settings/save",jsonOptions("POST",target)));feedback(tr("Ajustes guardados para esta diapositiva del preset activo."));});
  });
  $("reset-live").addEventListener("click",()=>{
    const target=scope();
    mutate(async()=>{render(await request("/api/admin/live-settings/reset",jsonOptions("POST",target)));feedback(tr("Se han recuperado los ajustes programados."));});
  });
  $("auto-preset").addEventListener("change",()=>{
    const enabled=$("auto-preset").checked;
    mutate(async()=>{render(await request("/api/admin/automatic-preset",jsonOptions("PUT",{enabled})));feedback(enabled ? tr("Detección automática del preset activada.") : tr("Selección manual de preset activada."));});
  });
  $("choose-presentation-file").addEventListener("click",()=>$("presentation-file").click());
  $("presentation-file").addEventListener("change",()=>{
    const file=$("presentation-file").files[0]; if(!file) return;
    mutate(async()=>{
      const info=await request("/api/admin/presentations",{method:"POST",headers:{"Content-Type":"application/octet-stream","X-Presentation-Name":encodeURIComponent(file.name)},body:file});
      state=await request("/api/admin/state");renderPresentations();$("preset-presentation").value=info.name;metadataDirty=true;
      $("presentation-summary").textContent=tr("{0} · {1} diapositivas detectadas. Guarda la vinculación del preset.", info.name, info.total);
      feedback(tr("Detectadas {0} diapositivas. Pulsa Guardar nombre y PowerPoint.", info.total));
    });
    $("presentation-file").value="";
  });
  async function refresh() {
    if (loading || saving) return;
    loading=true; const currentRevision=revision;
    try {const data=await request("/api/admin/state"); if(currentRevision===revision && !saving) render(data);}
    catch {$("connection").textContent=tr("Sin conexión · Reintentando"); $("connection").classList.add("offline");}
    finally {loading=false;}
  }
  $("reading-form").addEventListener("input",()=>{dirty=true; labels(); if(state) $("activate-preset").disabled=true;});
  $("reading-form").addEventListener("submit",event=>{
    event.preventDefault(); const value=values(), item=preset(), index=ruleIndex;
    const activate=event.submitter?.id==="save-and-activate";
    mutate(async()=>{
      if (item) {
        const payload=presetPayload(item);
        if(index===null) payload.defaults=value; else payload.rules[index]=value;
        await request(`/api/admin/presets/${item.id}`,jsonOptions("PUT",payload));
        if(activate) await request("/api/admin/active-preset",jsonOptions("PUT",{preset_id:item.id}));
        const target=index===null ? tr("Valores por defecto") : tr("Diapositiva {0}", index);
        feedback(tr("{0} guardada en {1}.", target, payload.name) + (activate ? tr(" Preset activado; se usa cuando coincide el PowerPoint.") : item.id!==activeId() ? tr(" Este preset no está en uso: actívalo para aplicarlo.") : tr(" La programación de la diapositiva actual ya está aplicada.")));
      } else {
        await request("/api/admin/display-settings",jsonOptions("PUT",value));
        feedback(state.active_preset_id ? tr("Lectura general guardada. Actívala para usarla.") : tr("Lectura general guardada y aplicada."));
      }
      dirty=metadataDirty=false;
    });
  });
  $("preset-select").addEventListener("change",()=>{
    const next=$("preset-select").value;
    if (!guardChanges()) {$("preset-select").value=selectedPreset; return;}
    selectedPreset=next; ruleIndex=null; dirty=metadataDirty=false; renderPresets();
  });
  for(const id of ["preset-name","preset-presentation"]) $(id).addEventListener("input",()=>{metadataDirty=true; $("activate-preset").disabled=true;});
  $("preset-metadata").addEventListener("submit",event=>{
    event.preventDefault(); const item=preset(); if(!item) return;
    mutate(async()=>{await request(`/api/admin/presets/${item.id}`,jsonOptions("PUT",presetPayload(item))); metadataDirty=false; feedback(tr("Nombre y presentación guardados."));});
  });
  $("use-current-presentation").addEventListener("click",()=>{if(state.slide.presentation){$("preset-presentation").value=state.slide.presentation; metadataDirty=true; $("activate-preset").disabled=true;}});
  $("new-preset").addEventListener("click",()=>{
    if(!guardChanges()) return;
    mutate(async()=>{const item=await request("/api/admin/presets",jsonOptions("POST",{}));
      if(state.slide.presentation && state.slide.total) await request(`/api/admin/presets/${item.id}`,jsonOptions("PUT",{name:item.name,presentation:state.slide.presentation,presentation_total:state.slide.total,defaults:item.defaults,rules:{}}));
      selectedPreset=item.id; ruleIndex=null; dirty=metadataDirty=false; feedback(tr("Preset creado. Ponle un nombre y prepara sus diapositivas."));});
  });
  $("duplicate-preset").addEventListener("click",()=>{
    const item=preset(); if(!item || !guardChanges()) return;
    mutate(async()=>{const copy=await request("/api/admin/presets",jsonOptions("POST",{copy_from:item.id})); selectedPreset=copy.id; ruleIndex=null; dirty=metadataDirty=false; feedback(tr("Copia creada. Puedes ajustarla sin cambiar el preset original."));});
  });
  $("delete-preset").addEventListener("click",()=>{
    const item=preset(); if(!item || !window.confirm(tr("¿Eliminar el preset «{0}» y sus reglas guardadas?", item.name))) return;
    mutate(async()=>{await request(`/api/admin/presets/${item.id}`,{method:"DELETE"}); selectedPreset=null; ruleIndex=null; dirty=metadataDirty=false; feedback(tr("Preset eliminado. Si estaba activo se ha vuelto a la lectura general."));});
  });
  $("activate-preset").addEventListener("click",()=>mutate(async()=>{
    await request("/api/admin/active-preset",jsonOptions("PUT",{preset_id:selectedPreset || null}));
    feedback(selectedPreset ? tr("Preset activado. Las reglas se aplican automáticamente al cambiar de diapositiva.") : tr("Lectura general activada."));
  }));
  $("edit-slide").addEventListener("click",()=>selectRule(Number($("rule-slide").value)));
  $("edit-current-slide").addEventListener("click",()=>selectRule(state.slide.index));
  $("edit-defaults").addEventListener("click",()=>{if(guardChanges(false)){ruleIndex=null;dirty=false;renderPresets();}});
  $("apply-source").addEventListener("click",()=>mutate(async()=>{
    render(await request("/api/admin/source",jsonOptions("POST",{source:selectedSource})));
    feedback(tr("Origen actualizado. Las notas seguirán a este equipo."));
  }));
  refresh(); setInterval(refresh,2000);
})();
