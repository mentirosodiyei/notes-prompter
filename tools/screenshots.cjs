/* npm install --no-save playwright; npx playwright install chromium */
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const path=require('node:path');
const fs=require('node:fs/promises');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const python=process.env.NP_DEMO_PYTHON || (process.platform==='win32'?path.join(root,'.venv/Scripts/python.exe'):path.join(root,'.venv/bin/python'));
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.NP_SCREENSHOT_CHANNEL ? {channel:process.env.NP_SCREENSHOT_CHANNEL} : {})});
 try {
  for(const [offset,language]of ['en','ca','es'].entries()){
   const port=19000+offset*2,base=`http://127.0.0.1:${port}`;
   const child=spawn(python,[path.join(__dirname,'demo.py'),'--port',String(port),'--language',language],{cwd:root,stdio:'ignore'});
   try{
    let ready=false;for(let i=0;i<150;i++){if(child.exitCode!==null)throw Error('Demo exited');try{if((await fetch(base+'/api/admin/state')).ok){ready=true;break}}catch{}await new Promise(r=>setTimeout(r,50))}assert(ready);
    const state=await (await fetch(base+'/api/admin/state')).json();
    assert.equal(state.computer,'Demo receiver');assert.equal(state.language,language);
    const scope={source:state.source,presentation:state.slide.presentation,index:state.slide.index};
    for(let i=0;!scope.index&&i<100;i++){Object.assign(scope,(await(await fetch(base+'/api/admin/state')).json()).slide);await new Promise(r=>setTimeout(r,20))}
    const current=await(await fetch(base+'/api/admin/state')).json();const target={source:current.source,presentation:current.slide.presentation,index:current.slide.index};
    assert.equal(current.slide.presentation,'Conference demo');
    await fetch(base+'/api/admin/playback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...target,action:'pause'})});
    const context=await browser.newContext({viewport:{width:1280,height:1000},locale:'fr-FR'});
    const panel=await context.newPage(),errors=[];panel.on('pageerror',e=>errors.push(e.message));
    await panel.goto(base);await panel.waitForFunction(()=>document.querySelector('#connection').classList.contains('offline')===false&&document.querySelector('#preset-select').options.length>1);
    assert.equal(await panel.locator('html').getAttribute('lang'),language);
    const heading={en:'Administration panel',ca:'Panell d’administració',es:'Panel de administración'};
    assert.equal(await panel.locator('h1').textContent(),heading[language]);
    const resume={en:'Resume',ca:'Reprendre',es:'Reanudar'};
    await panel.waitForFunction(text=>document.querySelector('#pause-scroll').textContent===text,resume[language]);
    await panel.screenshot({path:path.join(root,'docs/images',`panel-${language}.png`)});
    await panel.locator('#presets').evaluate(el=>el.scrollIntoView({block:'start',behavior:'instant'}));
    await panel.screenshot({path:path.join(root,'docs/images',`presets-${language}.png`)});
    const output=await context.newPage();output.on('pageerror',e=>errors.push(e.message));await output.goto(base+'/display');
    await output.waitForFunction(()=>document.querySelector('#text').textContent.includes('Welcome to the conference.'));
    assert.equal(await output.locator('#pause-scroll,#restart-scroll').count(),0);
    await output.screenshot({path:path.join(root,'docs/images',`output-${language}.png`)});
    // Newest playback wins even when a delayed frame arrives.
    await panel.locator('#pause-scroll').click();await panel.waitForFunction(text=>document.querySelector('#pause-scroll').textContent===text,{en:'Pause',ca:'Pausar',es:'Pausar'}[language]);
    await panel.locator('#pause-scroll').click();await panel.waitForFunction(text=>document.querySelector('#pause-scroll').textContent===text,resume[language]);
    assert.deepEqual(errors,[]);await context.close();console.log(language+': localized UI, preserved notes and remote controls passed');
   }finally{child.kill('SIGTERM');await new Promise(resolve=>{if(child.exitCode!==null)return resolve();const timer=setTimeout(()=>{child.kill('SIGKILL');resolve()},3000);child.once('exit',()=>{clearTimeout(timer);resolve()})})}
  }
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
