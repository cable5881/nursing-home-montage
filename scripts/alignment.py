"""One numeral-aware mapping shared by speech QA, build and caption reflow."""
import re


def character_map(data, text, clean, phonemes):
    words=[w for row in data['segments'] for w in row.get('words',[])]
    groups=[];i=0
    while i<len(words):
        word=words[i];raw=word['word'];end=word['end'];j=i+1
        numeric=bool(re.search(r'\d',raw))
        if numeric:
            while j<len(words) and re.search(r'[\d.]\s*$',raw) and re.match(r'\s*[\d.]',words[j]['word']) and words[j]['start']-end<.35:
                raw=raw.strip()+words[j]['word'].strip();end=words[j]['end'];j+=1
        following=words[j]['word'] if j<len(words) else ''
        letters=clean(raw+'年')[:-1] if re.search(r'\d{4}\s*$',raw) and following.lstrip(' ,，、').startswith('年') else clean(raw)
        groups.append((letters,float(word['start']),float(end),numeric));i=j
    chars=[]
    for group,(letters,start,end,numeric) in enumerate(groups):
        for k,c in enumerate(letters):
            # Numerals retain their measured group interval, never invented intra-number timing.
            a,b=(start,end) if numeric else (start+(end-start)*k/len(letters),start+(end-start)*(k+1)/len(letters))
            chars.append({'c':c,'start':a,'end':b,'numberGroup':group if numeric else None})
    actual=''.join(c['c'] for c in chars);expected=clean(text)
    if len(actual)!=len(expected) or phonemes(actual)!=phonemes(expected):
        raise ValueError('词级映射与原稿不一致；查看 alignment-check.json 的 numericMapping，不删除数字或重配音绕过。')
    return chars


def safe_boundary(chars, index):
    return index<=0 or index>=len(chars) or chars[index].get('numberGroup') is None or chars[index].get('numberGroup')!=chars[index-1].get('numberGroup')
