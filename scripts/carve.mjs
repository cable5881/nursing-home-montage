// Montage-specific bridge to the public @hyperframes/core audio analysis API.
import {readFileSync,writeFileSync} from 'node:fs';
import {execFileSync,spawnSync} from 'node:child_process';
import {createRequire} from 'node:module';
import {resolve,dirname} from 'node:path';
import {pathToFileURL} from 'node:url';
const options={};
for(let i=2;i<process.argv.length;i+=2) options[process.argv[i].replace(/^--/,'')]=process.argv[i+1];
const file=resolve(options.comp),base=dirname(file),rate=48000,strength=Number(options.strength??.8);
if(!(strength>=0&&strength<=1))throw Error('strength must be between 0 and 1');
const require=createRequire(pathToFileURL(resolve(options.core??base,'package.json')));
const pkgFile=require.resolve('@hyperframes/core/package.json'),pkg=JSON.parse(readFileSync(pkgFile,'utf8'));
async function api(name){const entry=pkg.exports['./'+name];const path=typeof entry==='string'?entry:entry.import??entry.default;return import(pathToFileURL(resolve(dirname(pkgFile),path)).href);}
const analysis=await api('audio-carve'),effects=await api('audio-fx');
const decode=s=>s.replace(/&quot;/g,'"').replace(/&#x27;|&#39;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
const encode=s=>s.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const attr=(tag,key)=>decode(tag.match(new RegExp('\\s'+key+'="([^"]*)"'))?.[1]??'');
const html=readFileSync(file,'utf8'),tags=[...html.matchAll(/<audio\b[^>]*>/g)].map(m=>m[0]);
const bedTag=tags.find(t=>attr(t,'id')===options.bed),voiceTag=tags.find(t=>attr(t,'id')===options.voice);
if(!bedTag||!voiceTag)throw Error('Named full narration and music tracks are required');
const hasRtk=spawnSync('rtk',['--version'],{stdio:'ignore'}).status===0;
function samples(tag){
 const args=['-v','error','-i',resolve(base,attr(tag,'src')),'-vn','-ac','1','-ar',String(rate),'-f','f32le','-'];
 const raw=execFileSync(hasRtk?'rtk':'ffmpeg',hasRtk?['proxy','ffmpeg',...args]:args,{maxBuffer:1<<30});
 const out=new Float32Array(raw.length/4);for(let i=0;i<out.length;i++)out[i]=raw.readFloatLE(i*4);return out;
}
const profile=analysis.carveProfile(strength);
const voice=analysis.mixCarveSources([{samples:samples(voiceTag),offsetSeconds:Number(attr(voiceTag,'data-start'))-Number(attr(bedTag,'data-start'))}],rate);
const bands=analysis.analyseCarveBands(voice,rate,profile);
const duck=profile.duckDb>0?analysis.analyseCarveDuck(voice,samples(bedTag),rate,profile,0):[];
const old=attr(bedTag,'data-fx-chain')?effects.parseAudioFxChain(attr(bedTag,'data-fx-chain')).nodes:[];
const kept=old.filter(n=>!n.fromCarve),removed=old.filter(n=>n.fromCarve&&n.id).map(n=>'fx.'+n.id+'.');
let allocated={version:1,nodes:[...kept]};
function add(node){const n={...node,id:effects.mintAudioFxNodeId(allocated),fromCarve:true};allocated.nodes.push(n);return n;}
const filters=bands.map(b=>add(analysis.carveBandsToChain([b]).nodes[0]));
const gain=duck.length?add({type:'gain',enabled:true,params:{...effects.defaultAudioFxParams('gain'),gain:0}}):null;
function lane(node,points){const timed=points.map(p=>({t:Number(p.t.toFixed(3)),v:p.v})).filter(p=>p.t>=0);if((timed[0]?.t??0)>0)timed.unshift({t:0,v:0});return timed.length>1?[{target:'fx.'+node.id+'.gain',points:timed}]:[];}
const generated=analysis.analyseCarveDynamics(voice,rate,bands).flatMap((b,i)=>lane(filters[i],b.points));
if(gain)generated.push(...lane(gain,duck));
const previous=attr(bedTag,'data-automation')?JSON.parse(attr(bedTag,'data-automation')).lanes:[];
const attrs={'data-fx-carve':{enabled:true,sources:[options.voice],strength},'data-fx-chain':JSON.parse(effects.serializeAudioFxChain({version:1,nodes:[...filters,...(gain?[gain]:[]),...kept]})),'data-automation':{version:1,lanes:[...previous.filter(l=>!removed.some(p=>String(l.target).startsWith(p))),...generated]}};
let updated=bedTag;
for(const [key,value] of Object.entries(attrs)){updated=updated.replace(new RegExp('\\s'+key+'="[^"]*"','g'),'');updated=updated.replace(/>$/,' '+key+'="'+encode(JSON.stringify(value))+'">');}
writeFileSync(file,html.replace(bedTag,updated));
console.log(JSON.stringify({carved:true,bands:bands.length,dynamics:generated.length}));
