const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');
async function output(){
 let now=0,id=0,socket;const frames=new Map();let scroll=0;
 const note={clientHeight:500,clientWidth:1000,scrollHeight:10000,classList:{add(){},remove(){}},addEventListener(){},get scrollTop(){return scroll},set scrollTop(value){scroll=Math.max(0,Math.min(9500,value))}};
 const text={style:{},offsetHeight:10000,scrollWidth:900,textContent:''};
 const elements={note,text,pager:{addEventListener(){}},status:{dataset:{}}};
 const document={getElementById:id=>elements[id],addEventListener(){}};
 const context={document,performance:{now:()=>now},location:{protocol:'http:',host:'localhost'},requestAnimationFrame:fn=>{frames.set(++id,fn);return id},cancelAnimationFrame:i=>frames.delete(i),setTimeout(){},fetch:async()=>({ok:true,json:async()=>({auto_scroll:true,font_mode:'fixed',min_font_px:52,speed_px_s:100,start_delay_s:0})}),WebSocket:class{constructor(){socket=this}send(){}close(){}},window:{addEventListener(){}},JSON,Math};
 context.window.NPI18n={t:(message,...values)=>message.replace(/\{(\d+)\}/g,(_,i)=>values[i])};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../../notes_prompter/static/display.js'),'utf8'),context);
 await new Promise(setImmediate);
 const scope={source:'demo',presentation:'Demo',index:1};
 const send=message=>socket.onmessage({data:JSON.stringify(message)});
 send({type:'slide',presentation:'Demo',index:1,total:1,notes:'Synthetic notes',display_settings:{auto_scroll:true,font_mode:'fixed',min_font_px:52,speed_px_s:100,start_delay_s:0},playback:{...scope,paused:false,restart_id:0,revision:0}});
 return {position:()=>scroll,sendPlayback:(revision,paused,restart_id=0)=>send({type:'playback',...scope,revision,paused,restart_id}),advance(ms){for(let left=ms;left>0;){const dt=Math.min(left,1000/60);left-=dt;now+=dt;const callbacks=[...frames.values()];frames.clear();callbacks.forEach(fn=>fn(now))}return scroll}};
}
test('delayed pause/resume frame cannot override newer playback state',async()=>{
 const page=await output();assert(page.advance(1000)>90);page.sendPlayback(2,true);const before=page.position();page.sendPlayback(1,false);assert.equal(page.advance(1000),before);page.sendPlayback(3,false);assert(page.advance(500)>before+40);
});
test('delayed restart cannot rewind or unpause a newer restart',async()=>{
 const page=await output();page.advance(1000);page.sendPlayback(4,true,2);assert.equal(page.position(),0);page.sendPlayback(3,false,1);assert.equal(page.advance(4000),0);
});
