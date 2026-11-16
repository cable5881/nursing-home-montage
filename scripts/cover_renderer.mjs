// Reuse the exact locked HyperFrames browser environment; no image generation APIs.
import {createRequire} from 'node:module';
import {readFile,writeFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
import {acquireLockedBrowser} from './browser_runtime.mjs';
const [htmlPath,pngPath,reportPath,hyperframesPackage]=process.argv.slice(2);
if(!hyperframesPackage)throw new Error('Pass HTML, PNG, report and the locked HyperFrames package.json');
const pkg=JSON.parse(await readFile(hyperframesPackage,'utf8'));
if(pkg.name!=='hyperframes'||pkg.version!=='0.9.44')throw new Error('Cover requires HyperFrames 0.9.44 browser runtime');
const lease=await acquireLockedBrowser(hyperframesPackage);const browser=lease.browser;
try{
 const page=await browser.newPage();await page.setViewport({width:1400,height:1000,deviceScaleFactor:1});
 page.on('console',message=>{const t=message.text();if(t.startsWith('OTS parsing error'))process.stderr.write(t.slice(0,500)+'\n');});
 await page.goto(pathToFileURL(path.resolve(htmlPath)).href,{waitUntil:'load'});
 await page.waitForFunction(()=>window.coverApp?.ready===true||document.querySelector('#status')?.classList.contains('error'),{timeout:30000});
 if(!await page.evaluate(()=>window.coverApp?.ready===true))throw new Error(await page.$eval('#status',e=>e.textContent));
 const report=await page.evaluate(()=>window.coverApp.report());
 await writeFile(reportPath,JSON.stringify(report,null,2));
 if(report.errors.length)throw new Error(report.errors.join('; '));
 const png=await page.evaluate(()=>window.coverApp.png());
 await writeFile(pngPath,Buffer.from(png.split(',')[1],'base64'));
 process.stdout.write(JSON.stringify({png:pngPath,layout:reportPath}));
}finally{await lease.close();}
