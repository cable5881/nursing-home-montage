from pathlib import Path
import hashlib,json,math,re
from workflow import *

def find_font(cfg):
    override=cfg['typography'].get('body_font')
    if override:
        if not Path(override).is_file():raise ValueError('Configured body font missing')
        return Path(override)
    return SKILL/'assets/NotoSansSC-Black.otf'
def caption_parts(s):
    if s.get('captions'):return s['captions']
    parts=[p for p in re.split('[，,、；;：:。！？!?]',s['text']) if clean(p)]
    result=[]
    for part in parts:
        # Draft only; the skill reviews line breaks semantically and keeps the locked size.
        chunks=[part[i:i+8] for i in range(0,len(part),8)]
        result.extend({'text':c,'lines':[c] if len(c)<=7 else [c[:4],c[4:]],'focus':''} for c in chunks)
    return result
def build(job):
    plan,files=validate_plan(job);setup(job);cfg=settings(job)
    v=read(job/'voice.json');source=Path(v['audio']);text=(job/'narration.txt').read_text(encoding='utf-8').strip()
    if sha(source)!=v['sha256'] or digest(text)!=v['textSha256']:raise RuntimeError('Stale voice; regenerate/realign before building')
    aligned=read(v['alignment'])
    if not aligned['passed'] or aligned['sha256']!=sha(source) or aligned['textSha256']!=digest(text):raise RuntimeError('Stale or failed word alignment')
    chars=[]
    words=[w for row in aligned['segments'] for w in row['words']]
    for wi,w in enumerate(words):
        letters=word_letters(w['word'],words[wi+1]['word'] if wi+1<len(words) else '')
        for i,c in enumerate(letters):chars.append({'c':c,'start':w['start']+(w['end']-w['start'])*i/len(letters),'end':w['start']+(w['end']-w['start'])*(i+1)/len(letters)})
    canonical=clean(text)
    if phonemes(''.join(c['c'] for c in chars))!=phonemes(canonical) or len(chars)!=len(canonical):raise RuntimeError('Cannot map source words one-to-one; resolve the alignment discrepancy first')
    offset=cfg['voice']['start'];fps=cfg['video']['fps'];duration=v['duration'];total=math.ceil((duration+offset)*fps)/fps
    ranges=[];cursor=0
    for s in plan['sentences']:
        n=len(clean(s['text']));ranges.append((cursor,cursor+n));cursor+=n
    assert cursor==len(chars)
    boundaries=[0]+[round(((chars[a-1]['end']+chars[a]['start'])/2+offset)*fps)/fps for a,b in ranges[1:]]+[total]
    voice_dir=job/'assets/voice';voice_dir.mkdir(exist_ok=True)
    raw=copy_asset(source,voice_dir/'narration.mp3')
    levels=run(['ffmpeg','-hide_banner','-i',raw,'-af','aformat=channel_layouts=stereo,loudnorm=I=-17:TP=-1.5:LRA=11:print_format=json','-f','null','-']).stderr
    levels=json.loads(levels[levels.rfind('{'):levels.rfind('}')+1]);gain=cfg['voice']['target_lufs']-float(levels['input_i'])
    run(['ffmpeg','-y','-v','error','-i',raw,'-af',f'volume={gain:.4f}dB','-ar','48000','-ac','2','-c:a','pcm_s16le',voice_dir/'narration-master.wav'])
    cues=[];cursor=0
    for s in plan['sentences']:
        for c in caption_parts(s):
            n=len(clean(c['text']))
            if clean(c['text'])!=canonical[cursor:cursor+n]:raise ValueError('Caption draft dropped/changed words; edit the plan')
            cues.append({**c,'focus':c.get('focus',''),'start':round(chars[cursor]['start']+offset,4),'speechEnd':round(chars[cursor+n-1]['end']+offset,4),'canonicalRange':[cursor,cursor+n]});cursor+=n
    for i,c in enumerate(cues):
        next_start=cues[i+1]['start'] if i+1<len(cues) else total
        c['end']=round(min(c['speechEnd']+.2,next_start-.025),6) if i+1<len(cues) else total
        c['duration']=round(c['end']-c['start'],6)
        if c['duration']<=.2:raise ValueError('Caption has too little reading time; merge its wording with a neighbour')
    write(job/'captions.json',cues)
    def stamp(t):
        ms=round(t*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000);return f'{h:02}:{m:02}:{s:02},{ms:03}'
    (job/'subtitles.srt').write_text('\n\n'.join(str(i+1)+'\n'+stamp(c['start'])+' --> '+stamp(c['end'])+'\n'+'\n'.join(c['lines']) for i,c in enumerate(cues))+'\n', encoding='utf-8')
    source_root=Path(read(job/'inventory.json')['source']);shots=[];ledger=[]
    for si,sentence in enumerate(plan['sentences']):
        selected=sentence['shots'];start_frame=round(boundaries[si]*fps);last_frame=round(boundaries[si+1]*fps);count=last_frame-start_frame
        if count<len(selected):raise ValueError('Too many shots for this sentence')
        weights=[s.get('weight',1) for s in selected];running=0
        for k,s in enumerate(selected):
            next_running=round(count*sum(weights[:k+1])/sum(weights)) if k+1<len(selected) else count
            st=(start_frame+running)/fps;end=(start_frame+next_running)/fps;running=next_running
            row=files[s['path']];orig=(source_root/s['path']).resolve()
            if sha(orig)!=row['sha256']:raise RuntimeError('Input changed since inventory: '+s['path'])
            ext=orig.suffix.lower();dest=job/'assets/footage'/(row['sha256'][:12]+ext)
            copy_asset(orig,dest)
            src_start=s.get('sourceStart',0)
            if row['kind']=='video' and src_start+end-st>row['duration']+.001:raise ValueError('Selected video window is too short; add another real shot or change its source start: '+s['path'])
            shot={'id':f'shot-{len(shots):02}','asset':str(dest.relative_to(job)),'start':st,'end':end,'duration':end-st,'sourceStart':src_start,'positionY':s.get('positionY',50),'description':s['description'],'sentenceIndex':si}
            shots.append(shot);ledger.append({'file':shot['asset'],'source':str(orig),'sha256':row['sha256'],'kind':row['kind'],'modified':False})
    write(job/'shot-list.json',shots);write(job/'asset-sources.json',ledger)
    (job/'source-description.txt').write_text(json.dumps(plan['institution'],ensure_ascii=False)+'\n'+(job/'source-text.txt').read_text(encoding='utf-8'), encoding='utf-8')
    inst=plan['institution'];reference=cfg['typography'].get('reference_identity')==inst and bool(cfg['typography'].get('reference_asset'))
    write(job/'institution.json',{**inst,'headerMode':'reference' if reference else 'dynamic'})
    font=find_font(cfg);match=[{'family':'Project body font' if cfg['typography'].get('body_font') else 'Noto Sans SC Black','file':str(font),'index':cfg['typography']['collection_index'],'stroke':3,'angle':3,'tracking':4}]
    write(job/'orange-font-match.json',match)
    # Fresh subsets must include the new institution and narration, not the previous project's glyph set.
    for f in ('OrangeRounded.woff2','OrangeLabel.woff2'):(job/'assets/fonts'/f).unlink(missing_ok=True)
    timeline={'duration':total,'voiceStart':offset,'voiceDuration':duration,'audio':'assets/voice/narration-master.wav','audioSha256':sha(voice_dir/'narration-master.wav'),'rawAudio':'assets/voice/narration.mp3','rawAudioSha256':sha(raw),'constantGainDB':gain,'speaker':cfg['voice']['speaker'],'speechRate':cfg['voice']['speech_rate'],'outroStart':total,'outroDuration':0,'holdLastCaption':True,'chapters':[[boundaries[i],boundaries[i+1]-boundaries[i],s['label']] for i,s in enumerate(plan['sentences'])]}
    write(job/'natural-timeline.json',timeline)
    if cfg['music'].get('enabled') and cfg['music'].get('resource'):
        music_path=cfg['music']['resource'];music_path=Path(music_path) if Path(music_path).is_absolute() else project_root()/music_path
        if not music_path.exists():raise RuntimeError('Configured music resource missing; select a local licensed track in settings.music.resource')
        if float(probe(music_path)['format']['duration'])<total:raise RuntimeError('Music is shorter than narration; choose a longer local track')
        (job/'assets/music').mkdir(exist_ok=True)
        run(['ffmpeg','-y','-v','error','-i',music_path,'-t',total,'-af',f"volume={cfg['music']['static_gain_db']}dB",'-ar','48000','-ac','2','-c:a','pcm_s16le',job/'assets/music/bed.wav'])
        bgm={'enabled':True,'audio':'assets/music/bed.wav','duration':total,'data-fx-chain':{'version':1,'nodes':[{'type':'gain','id':'outro-lift','params':{'gain':0}}]},'data-fx-carve':{'enabled':True,'sources':['female-narration'],'strength':cfg['music']['carve_strength']},'data-automation':{'version':1,'lanes':[{'target':'volume','points':[{'t':0,'v':0},{'t':cfg['music']['fade_in'],'v':1},{'t':max(cfg['music']['fade_in'],total-cfg['music']['fade_out']),'v':1},{'t':total,'v':0}]},{'target':'fx.outro-lift.gain','points':[{'t':0,'v':cfg['music']['speech_gain_db']},{'t':total,'v':cfg['music']['speech_gain_db']}]}]}}
    else:bgm={'enabled':False}
    write(job/'bgm-timeline.json',bgm)
    mode=cfg['avatar']['mode'];indices=[]
    if mode not in ('off','opening','closing','both'):raise ValueError('avatar.mode must be off/opening/closing/both')
    if mode in ('opening','both'):indices.append(0)
    if mode in ('closing','both') and len(ranges)-1 not in indices:indices.append(len(ranges)-1)
    avatars=[]
    for si in indices:
        first,last=ranges[si];prev_end=chars[first-1]['end'] if first else 0
        start=0 if si==0 else max(prev_end+.02,chars[first]['start']-cfg['avatar']['sentence_padding'])
        end=duration if si==len(ranges)-1 else min(math.ceil((chars[last-1]['end']+.16)*fps)/fps,chars[last]['start']-.02)
        start=math.floor(start*fps)/fps;ident='opening' if si==0 else 'closing';out=job/'assets'/('avatar-'+ident);out.mkdir(exist_ok=True)
        run(['ffmpeg','-y','-v','error','-ss',start,'-i',raw,'-t',end-start,'-vn','-ar','24000','-ac','1','-c:a','pcm_s16le',out/'driver.wav'])
        is_last=si==len(ranges)-1;display_end=total if is_last else offset+end
        avatars.append({'id':ident,'video':str((out/'avatar-outlined.webm').relative_to(job)),'audio':str((out/'driver.wav').relative_to(job)),'start':offset+start,'duration':display_end-offset-start,'x':cfg['avatar']['x'],'y':cfg['avatar']['bottom']-cfg['avatar']['height'],'width':cfg['avatar']['width'],'height':cfg['avatar']['height'],'fadeIn':cfg['avatar']['fade_in'],'fadeOut':0 if is_last else min(cfg['avatar']['fade_out'],max(.04,end-chars[last-1]['end'])),'text':plan['sentences'][si]['text'],'sourceNarrationStart':start})
    write(job/'avatars.json',avatars)
    write(job/'build-inputs.json',{'planSha256':sha(job/'plan.json'),'voiceSha256':v['sha256'],'sourceHashes':{p:r['sha256'] for p,r in files.items()},'noPostTtsTimeStretch':True})
    state(job,phase='timed',next='avatars',duration=total)
    compose(job)
    return {'duration':total,'shots':len(shots),'captions':len(cues),'avatarWindows':[[a['start'],a['start']+a['duration']] for a in avatars]}

def compose(job):
    run([sys.executable,SKILL/'scripts/compose_orange.py',job])
