from pathlib import Path
import ezdxf

base = Path('sample-files')
for p in sorted(base.glob('Input_Sample_*.dxf')):
    print(f'===== {p.name} =====')
    try:
        doc = ezdxf.readfile(str(p))
    except Exception as e:
        print('read error:', e)
        continue

    layouts = [layout.name for layout in doc.layouts]
    print('layouts:', layouts)

    view_names = []
    try:
        view_names = [v.dxf.name for v in doc.views]
    except Exception:
        pass
    print('named_views:', view_names[:20], 'count=', len(view_names))

    msp = doc.modelspace()
    counts = {}
    for e in msp:
        t = e.dxftype()
        counts[t] = counts.get(t, 0) + 1
    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
    print('modelspace_top_entities:', top)

    for layout in doc.layouts:
        if layout.name.lower() == 'model':
            continue
        vp_count = 0
        for e in layout:
            if e.dxftype() == 'VIEWPORT':
                vp_count += 1
        if vp_count:
            print(f'layout {layout.name}: viewports={vp_count}')
    print()
