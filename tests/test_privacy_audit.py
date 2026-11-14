import importlib.util
from pathlib import Path
import struct
import zlib

module_path=Path(__file__).resolve().parents[1]/'tools/privacy_audit.py'
spec=importlib.util.spec_from_file_location('privacy_audit',module_path)
privacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(privacy)


def test_audit_detects_home_path_and_secret_like_token(tmp_path):
    home='/'+'Users'+'/'+'demo'+'/project'
    (tmp_path/'example.py').write_text(home+'\n'+'ghp_'+'A'*40)
    count,problems=privacy.audit(tmp_path)
    assert count==1
    assert any('home path' in p for p in problems)
    assert any('credential-like' in p for p in problems)


def test_dll_imports_are_not_mistaken_for_personal_email(tmp_path):
    (tmp_path/'installer.iss').write_text("external 'CreateFileW"+'@'+'kernel32'+".dll stdcall';")
    assert privacy.audit(tmp_path)[1]==[]
    (tmp_path/'email.txt').write_text('private'+'@'+'example'+'.invalid')
    assert any('email address' in p for p in privacy.audit(tmp_path)[1])


def test_png_metadata_removal_keeps_pixel_chunks_identical(tmp_path):
    def chunk(kind,payload):return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload)&0xffffffff)
    header=b'\x89PNG\r\n\x1a\n'
    ihdr=chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,6,0,0,0))
    pixels=chunk(b'IDAT',zlib.compress(b'\0\0\0\0\xff'))
    end=chunk(b'IEND',b'')
    file=tmp_path/'demo.png';file.write_bytes(header+ihdr+chunk(b'tEXt',b'Author\0Synthetic')+pixels+end)
    assert privacy.audit(tmp_path)[1]
    privacy.strip_png_metadata(file)
    assert file.read_bytes()==header+ihdr+pixels+end
    assert privacy.audit(tmp_path)[1]==[]
