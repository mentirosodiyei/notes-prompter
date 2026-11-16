"""Source-tree preflight: reject local artifacts, home paths, credentials and PNG text metadata.

This is a targeted release check, not a guarantee against every kind of sensitive data.
Review every added screenshot and fixture manually too.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import struct
import sys

SKIP={'.git','__pycache__','.pytest_cache','node_modules','build','dist','htmlcov'}
ARTIFACTS={'.dmg','.exe','.pkg','.zip','.tgz','.p12','.pfx','.pem','.key','.scpt','.log','.ppt','.pptx','.pptm'}
PATTERNS={
    'macOS home path':re.compile('/'+'Users'+r'/[^\s/\["\']+'),
    'Windows user path':re.compile(r'[A-Za-z]:\\'+'Users'+r'\\[^\s\\\["\']+'),
    'credential-like token':re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{24,}|AKIA[0-9A-Z]{16})'),
    'private key':re.compile(r'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----'),
    'email address':re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',re.I),
}

def audit(root: Path) -> tuple[int,list[str]]:
    count=0;problems=[]
    for path in sorted(root.rglob('*')):
        relative=path.relative_to(root)
        if any(part in SKIP or part.startswith('.venv') or part.endswith('.egg-info') for part in relative.parts):continue
        if path.is_symlink():problems.append(f'{relative}: symlinks are not part of the public source package');continue
        if not path.is_file():continue
        count+=1
        if path.suffix.lower() in ARTIFACTS or path.name.startswith('.env') or path.name in {'updates.json','update-result.json'} or path.name.startswith('settings') and path.suffix=='.json':
            problems.append(f'{relative}: local or sensitive artifact')
        data=path.read_bytes()
        if path.suffix.lower()=='.png':
            if not data.startswith(b'\x89PNG\r\n\x1a\n'):problems.append(f'{relative}: invalid PNG');continue
            offset=8
            while offset+12<=len(data):
                length=struct.unpack('>I',data[offset:offset+4])[0];kind=data[offset+4:offset+8]
                if kind in (b'tEXt',b'iTXt',b'zTXt',b'eXIf'):problems.append(f'{relative}: textual/image metadata must be reviewed and removed')
                offset+=12+length
            continue
        try:text=data.decode('utf-8-sig')
        except UnicodeDecodeError:continue
        for label,pattern in PATTERNS.items():
            matches=list(pattern.finditer(text))
            if label=='email address':
                matches=[match for match in matches if not re.fullmatch(r'(?:CreateFileW|CloseHandle)@kernel32[.]dll',match[0])]
            if matches:problems.append(f'{relative}: {label}')
    return count,problems

def strip_png_metadata(path: Path) -> None:
    """Remove non-pixel text/EXIF chunks without decoding or changing pixel data."""
    data=path.read_bytes()
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Not a PNG')
    result=bytearray(data[:8]);offset=8
    while offset+12<=len(data):
        length=struct.unpack('>I',data[offset:offset+4])[0]
        end=offset+12+length
        if end>len(data):raise ValueError('Truncated PNG')
        if data[offset+4:offset+8] not in (b'tEXt',b'iTXt',b'zTXt',b'eXIf'):
            result.extend(data[offset:end])
        offset=end
    path.write_bytes(result)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',nargs='?',type=Path,default=Path(__file__).resolve().parents[1]);args=parser.parse_args()
    count,problems=audit(args.root)
    for issue in problems:print(issue)
    print(f'Checked {count} source files; {len(problems)} issue(s).')
    sys.exit(bool(problems))
