// Share the locked HyperFrames engine's browser resolver, launch policy and lease cleanup.
import {readFile,readdir} from 'node:fs/promises';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {pathToFileURL} from 'node:url';
import path from 'node:path';

export async function acquireLockedBrowser(packageFile,width=1400,height=1000){
 const pkg=JSON.parse(await readFile(packageFile,'utf8'));
 if(pkg.name!=='hyperframes'||pkg.version!=='0.9.44')throw new Error('Requires the pinned HyperFrames 0.9.44 runtime');
 const dist=path.join(path.dirname(packageFile),'dist');
 const {stdout}=await promisify(execFile)(process.execPath,[path.join(dist,'cli.js'),'browser','path'],{timeout:60000,env:process.env});
 const executable=stdout.trim().split('\n').at(-1);
 if(!path.isAbsolute(executable))throw new Error('HyperFrames did not resolve an absolute browser path');
 process.env.PRODUCER_HEADLESS_SHELL_PATH=executable;
 let modulePath;
 for(const name of (await readdir(dist)).filter(n=>n.startsWith('src-')&&n.endsWith('.js'))){
  const file=path.join(dist,name),text=await readFile(file,'utf8');
  if(text.includes('acquireBrowser')&&text.includes('buildChromeArgs')&&text.includes('releaseBrowser')){modulePath=file;break;}
 }
 if(!modulePath)throw new Error('Pinned engine browser exports missing; reinstall the pinned package, do not patch its cache');
 const runtime=await import(pathToFileURL(modulePath));
 if(!runtime.acquireBrowser||!runtime.buildChromeArgs)throw new Error('Pinned browser API mismatch');
 const lease=await runtime.acquireBrowser(runtime.buildChromeArgs({width,height},{browserGpuMode:'software'}),{enableBrowserPool:false});
 return {browser:lease.browser,close:()=>lease.release()};
}
