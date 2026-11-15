"""Map measured app rectangles into native video coordinates; no platform constants."""
import math


def overlap(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def native_regions(profile, width=1080, height=1920):
    sw, sh = profile['screenshot_size']
    x, y, w, h = profile['viewport']
    if min(sw, sh, w, h) <= 0 or x < 0 or y < 0 or x+w > sw or y+h > sh:
        raise ValueError('UI viewport must fit the measured screenshot')
    mode = profile.get('fit', 'cover')
    if mode not in ('cover', 'contain'):raise ValueError('UI fit must be cover or contain')
    scale = (max if mode == 'cover' else min)(w/width, h/height)
    ox, oy = x+(w-width*scale)/2, y+(h-height*scale)/2
    gap = float(profile.get('gap_px', 32))/scale
    if gap < 0:raise ValueError('UI gap must be nonnegative')
    obstacles = []
    for item in profile['regions']:
        r = item['rect']
        if len(r)!=4 or not (0<=r[0]<r[2]<=sw and 0<=r[1]<r[3]<=sh):
            raise ValueError('UI region must use screenshot x0,y0,x1,y1 bounds')
        obstacles.append({'name':item['name'], 'rect':[(r[0]-ox)/scale, (r[1]-oy)/scale, (r[2]-ox)/scale, (r[3]-oy)/scale]})
    visible = [max(0, (x-ox)/scale), max(0, (y-oy)/scale), min(width, (x+w-ox)/scale), min(height, (y+h-oy)/scale)]
    return {'scale':scale, 'offset':[ox,oy], 'gap_native':gap, 'visible':visible, 'regions':obstacles}


def lowest_box(width, height, limits, profiles):
    """Find the lowest fitting axis-aligned box, considering every obstacle and viewport."""
    left, top, right, bottom = limits
    measured = {name:native_regions(p) for name,p in profiles.items()}
    obstacles = []
    for p in measured.values():
        v=p['visible'];left=max(left,v[0]);right=min(right,v[2]);top=max(top,v[1]);bottom=min(bottom,v[3])
        for item in p['regions']:
            r=item['rect'];g=p['gap_native']
            obstacles.append([r[0]-g,r[1]-g,r[2]+g,r[3]+g])
    if right-left < width or bottom-top < height:raise ValueError('Measured viewports leave no subtitle box at the locked font size')
    xs={left,right-width,(left+right-width)/2}
    ys={bottom-height}
    for r in obstacles:
        xs.update((r[0]-width,r[2]));ys.add(r[1]-height)
    candidates=[]
    for x in xs:
        for y in ys:
            box=[x,y,x+width,y+height]
            if x<left-1e-6 or x+width>right+1e-6 or y<top-1e-6 or y+height>bottom+1e-6:continue
            if not any(overlap(box,r) for r in obstacles):candidates.append(box)
    if not candidates:raise ValueError('No non-obscured subtitle placement; revise UI profiles or caption segmentation')
    return max(candidates,key=lambda b:(round(b[3],6),-abs((b[0]+b[2])/2-(left+right)/2)))


def select_profiles(config):
    profiles=config.get('profiles',{})
    mode=config.get('mode','common')
    if mode not in ('common','platform'):raise ValueError('platform_ui.mode must be common or platform')
    if mode=='platform':
        name=config.get('platform')
        if name not in profiles:raise ValueError('Selected platform has no measured UI profile')
        return {name:profiles[name]}
    return profiles


def audit(rects, profiles):
    results=[]
    for name,profile in profiles.items():
        p=native_regions(profile);hits=[]
        for i,r in enumerate(rects):
            if any(overlap(r,item['rect']) for item in p['regions']):hits.append(i)
            v=p['visible']
            if r[0]<v[0]-1e-6 or r[2]>v[2]+1e-6 or r[1]<v[1]-1e-6 or r[3]>v[3]+1e-6:hits.append(i)
        results.append({'platform':name,'overlappingOrClippedLines':sorted(set(hits)),'scale':p['scale'],'offset':p['offset']})
    return results
