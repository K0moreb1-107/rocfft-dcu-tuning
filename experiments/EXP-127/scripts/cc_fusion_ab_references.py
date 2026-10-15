"""Independent full-length references with a noncommuting complex load callback."""
from pathlib import Path
import sys
import numpy as np
ROOT=Path('/public/home/zhangkewei/zr')
sys.path.insert(0,str(ROOT))
from tools.workspace_manager import manager as mgr
PATTERNS=('impulse','last','dc','nyquist','middle','tones','random')

def references(n,direction,callbacks,scratch):
    m=n//2;index=np.arange(n);rows=[];metadata=[]
    for pattern in PATTERNS:
        x=np.zeros(n)
        if pattern=='impulse':x[0]=0.5
        elif pattern=='last':x[-1]=-0.375
        elif pattern=='dc':x.fill(0.25)
        elif pattern=='nyquist':x=np.where(index%2,-0.375,0.375)
        elif pattern=='middle':x=0.5*np.cos(2*np.pi*(m//2)*index/n)
        elif pattern=='tones':
            x=0.5*np.cos(2*np.pi*7*index/n)+0.125*np.sin(2*np.pi*(m-3)*index/n)
            x+=0.25*np.cos(2*np.pi*(m//3)*index/n)
        else:x=np.random.default_rng(127+n).normal(size=n)
        value=x if direction=='d2z' else np.fft.rfft(x)
        if direction=='z2d' and pattern=='random':
            rng=np.random.default_rng(127+n)
            value=rng.normal(size=m+1)+1j*rng.normal(size=m+1)
            value[0]=value[0].real;value[-1]=value[-1].real
        complex_transform=direction in ('cforward','cinverse')
        if complex_transform:
            value=x.astype(np.complex128)+0.25j*np.roll(x,3)
            if pattern=='random':
                value+=1j*np.random.default_rng(127+n+1).normal(size=n)
        raw=np.ascontiguousarray(value,dtype='<f8' if direction=='d2z' else '<c16')
        input_path=scratch/(pattern+'-input.bin');raw.tofile(input_path)
        if callbacks:
            offsets=np.arange(len(value))
            value=value*0.75+(offsets%7)*0.03125
            if direction=='z2d':
                # A complex offset detects moving the callback after the
                # Hermitian conjugation; keep real-only endpoints unchanged.
                value[1:-1]+=1j*(offsets[1:-1]%11)*0.015625
        if complex_transform:
            transformed=np.fft.fft(value) if direction=='cforward' else np.fft.ifft(value)*n
        else:
            transformed=np.fft.rfft(value) if direction=='d2z' else np.fft.irfft(value,n=n)*n
        for scale in (1.0,0.375):
            expected=transformed*scale
            if callbacks:expected=expected*1.125+(np.arange(len(expected))%5)*0.015625
            path=scratch/(pattern+'-'+str(scale)+'-expected.bin')
            np.ascontiguousarray(expected,dtype='<c16' if direction!='z2d' else '<f8').tofile(path)
            rows.append('%s %.17g %s %s'%(pattern,scale,input_path,path))
            metadata.append(dict(pattern=pattern,scale=scale,input=str(input_path),expected=str(path),
                                 input_sha256=mgr.common.sha(input_path),
                                 expected_sha256=mgr.common.sha(path),seed=127+n))
    path=scratch/'reference-list.txt';path.write_text('\n'.join(rows)+'\n')
    return path,metadata

