const fs=require('fs');
const html=fs.readFileSync(require('path').join(__dirname,'..','aegismesh','static','index.html'),'utf8');
const js=html.match(/<script>([\s\S]*)<\/script>/)[1];
const runs=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const els={};
function el(id){return els[id]||(els[id]={innerHTML:'',textContent:'',className:'',hidden:false,disabled:false,value:id==='#dom'?'it':'',checked:true,style:{},title:''})}
global.document={querySelector:s=>el(s),getElementById:()=>null,addEventListener(){}};
global.requestAnimationFrame=f=>f();
global.fetch=async()=>({ok:true,json:async()=>({scenarios:[],nebius:{configured:false},tavily:{available:false,status:'x'},missing:true})});
global.EventSource=function(){};
const src=js+';globalThis.__t={reduce,render,fresh,get S(){return S}}';
(0,eval)(src);
let n=0;
for(const evs of runs){__t.fresh();
  for(const e of evs){__t.reduce(e);}
  __t.render();
  const S=__t.S, o=S.obs;
  if(!els['#graph'].innerHTML.includes('<circle')) throw new Error('no graph');
  if(o.domain==='hospital'&&els['#clin'].hidden) throw new Error('clinical panel hidden');
  if(!els['#banner'].textContent) throw new Error('no banner');
  n++;
}
console.log('rendered',n,'runs OK; last banner:',els['#banner'].textContent);
