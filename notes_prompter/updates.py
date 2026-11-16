"""Opt-in installation of releases from the project's fixed GitHub repository.

Network and filesystem work belongs on a worker thread. The updater never reads
PowerPoint or presets. A detached copy of the current app waits for its parent
before replacing it; portable replacements keep a rollback copy.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import ssl

import certifi
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import uuid

from . import __version__
from .i18n import tr

REPOSITORY = 'mentirosodiyei/notes-prompter'
API_URL = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
RELEASES_URL = f'https://github.com/{REPOSITORY}/releases/latest'
MAX_DOWNLOAD = 512 * 1024 * 1024


class UpdateError(Exception):
    pass


def version_tuple(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', value)
    if not match:
        raise UpdateError(tr('La versión publicada no es válida.'))
    return tuple(map(int, match.groups()))


def installation_target() -> Path | None:
    if not getattr(sys, 'frozen', False):
        return None
    exe = Path(sys.executable).resolve()
    if sys.platform == 'win32':
        return exe
    if sys.platform == 'darwin' and exe.parent.name == 'MacOS' and exe.parent.parent.name == 'Contents':
        return exe.parents[2]
    return None


def asset_name(version: str, target: Path, system: str, architecture: str) -> str:
    if system == 'darwin' and architecture in ('arm64', 'x86_64'):
        return f'Notes-Prompter-{version}-macOS-{architecture}.dmg'
    if system == 'win32' and architecture.lower() in ('amd64', 'x86_64'):
        if any(target.parent.glob('unins*.exe')):
            return f'Notes-Prompter-Setup-{version}.exe'
        return f'notes-prompter-{version}.exe'
    raise UpdateError(tr('No hay un paquete compatible con este equipo.'))


def trusted_asset_url(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.scheme == 'https' and parsed.netloc == 'github.com'
            and parsed.path.startswith(f'/{REPOSITORY}/releases/download/')
            and not parsed.query and not parsed.fragment)


@dataclass(frozen=True)
class Release:
    version: str
    name: str
    url: str
    size: int
    sha256: str


def select_release(data: dict, current: str, target: Path, system: str, architecture: str) -> Release | None:
    if data.get('draft') or data.get('prerelease'):
        return None
    tag = data.get('tag_name', '')
    parsed = version_tuple(tag)
    if parsed <= version_tuple(current):
        return None
    version = '.'.join(map(str, parsed))
    name = asset_name(version, target, system, architecture)
    assets = [a for a in data.get('assets', []) if a.get('name') == name]
    if len(assets) != 1:
        raise UpdateError(tr('La publicación todavía no tiene el paquete de este equipo.'))
    asset = assets[0]
    digest = asset.get('digest', '')
    size = asset.get('size')
    if (not trusted_asset_url(asset.get('browser_download_url', ''))
            or not isinstance(size, int) or not 0 < size <= MAX_DOWNLOAD
            or not isinstance(digest, str) or not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', digest)):
        raise UpdateError(tr('No se puede verificar el paquete publicado.'))
    return Release(version, name, asset['browser_download_url'], size, digest.split(':')[1].lower())


def check_release(target: Path, current: str = __version__) -> Release | None:
    request = Request(API_URL, headers={'Accept': 'application/vnd.github+json',
                                       'User-Agent': f'Notes-Prompter/{current}'})
    with urlopen(request, timeout=15, context=ssl.create_default_context(cafile=certifi.where())) as response:
        content = response.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise UpdateError(tr('La respuesta de GitHub no es válida.'))
    data = json.loads(content)
    if not isinstance(data, dict):
        raise UpdateError(tr('La respuesta de GitHub no es válida.'))
    return select_release(data, current, target, sys.platform, platform.machine())


def download_release(release: Release, directory: Path, progress=lambda fraction: None) -> Path:
    if not trusted_asset_url(release.url) or Path(release.name).name != release.name:
        raise UpdateError(tr('No se puede verificar el paquete publicado.'))
    path = directory / release.name
    temporary = directory / (release.name + '.part')
    digest = hashlib.sha256()
    received = 0
    try:
        request = Request(release.url, headers={'User-Agent': f'Notes-Prompter/{__version__}'})
        with urlopen(request, timeout=20, context=ssl.create_default_context(cafile=certifi.where())) as response, temporary.open('xb') as stream:
            # GitHub redirects asset downloads to its HTTPS object storage.
            if urlparse(response.geturl()).scheme != 'https':
                raise UpdateError(tr('La descarga no utiliza una conexión segura.'))
            while chunk := response.read(256 * 1024):
                received += len(chunk)
                if received > min(MAX_DOWNLOAD, release.size):
                    raise UpdateError(tr('El tamaño de la descarga no coincide.'))
                stream.write(chunk)
                digest.update(chunk)
                progress(received / release.size)
        if received != release.size or digest.hexdigest() != release.sha256:
            raise UpdateError(tr('La descarga no supera la comprobación SHA256.'))
        temporary.replace(path)
        return path
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


@dataclass
class UpdatePreferences:
    enabled: bool = True
    days: int = 7
    last_checked: float = 0
    skipped: str = ''

    @classmethod
    def load(cls, path: Path):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            value = cls(**data)
            if (not isinstance(value.enabled, bool) or isinstance(value.days, bool) or value.days not in (7, 30)
                    or isinstance(value.last_checked, bool) or not isinstance(value.last_checked, (int, float))
                    or not 0 <= value.last_checked < float('inf')
                    or not isinstance(value.skipped, str)):
                raise ValueError()
            return value
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(asdict(self), stream)
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def run(command, **kwargs):
    """Arguments are never interpolated into a shell command."""
    if sys.platform == 'win32':
        kwargs.setdefault('creationflags', subprocess.CREATE_NO_WINDOW)
    return subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)


def validate_mac_app(app: Path, version: str, architecture: str):
    import plistlib
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    if (info.get('CFBundleIdentifier') != 'org.notesprompter.desktop'
            or info.get('CFBundleShortVersionString') != version):
        raise UpdateError(tr('El paquete no corresponde a esta aplicación y versión.'))
    run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(app)])
    arches = run(['/usr/bin/lipo', '-archs', str(app / 'Contents/MacOS/notes-prompter')]).stdout.decode().split()
    if architecture not in arches:
        raise UpdateError(tr('No hay un paquete compatible con este equipo.'))
    minimum = tuple(map(int, info.get('LSMinimumSystemVersion', '11.0').split('.')))
    current = tuple(map(int, platform.mac_ver()[0].split('.')))
    if current < minimum:
        raise UpdateError(tr('Esta actualización necesita una versión más reciente del sistema.'))


def validate_windows_exe(path: Path):
    with path.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise UpdateError(tr('El ejecutable descargado no es válido.'))
        stream.seek(0x3c)
        offset = struct.unpack('<I', stream.read(4))[0]
        stream.seek(offset)
        if stream.read(6) != b'PE\x00\x00\x64\x86':
            raise UpdateError(tr('No hay un paquete compatible con este equipo.'))


def prepare_plan(release: Release, target: Path, result_path: Path, progress=lambda fraction: None) -> Path:
    """Download and stage everything before exiting the current app."""
    stage = Path(tempfile.mkdtemp(prefix='notes-prompter-update-'))
    candidate = None
    try:
        result_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=result_path.parent) as probe:
            probe.write(b'update-result')
            probe.flush()
        download = download_release(release, stage, progress)
        kind = 'mac' if sys.platform == 'darwin' else 'installer' if release.name.startswith('Notes-Prompter-Setup-') else 'portable'
        helper = stage / ('helper.app' if kind == 'mac' else 'update-helper.exe')
        if kind == 'mac':
            mount = stage / 'volume'
            mount.mkdir()
            mounted = False
            sibling = None
            try:
                run(['/usr/bin/hdiutil', 'attach', '-nobrowse', '-readonly', '-mountpoint', str(mount), str(download)])
                mounted = True
                source = mount / 'Notes Prompter.app'
                validate_mac_app(source, release.version, platform.machine())
                # Staging beside the target proves write access before closing.
                sibling = Path(tempfile.mkdtemp(prefix='.notes-prompter-update-', dir=target.parent))
                candidate = sibling / 'Notes Prompter.app'
                run(['/usr/bin/ditto', '--norsrc', '--noextattr', str(source), str(candidate)])
                validate_mac_app(candidate, release.version, platform.machine())
                run(['/usr/bin/ditto', '--norsrc', '--noextattr', str(target), str(helper)])
            finally:
                if mounted:
                    run(['/usr/bin/hdiutil', 'detach', str(mount)])
        else:
            validate_windows_exe(download)
            # This also fails before quitting if a portable target directory is read-only.
            probe = tempfile.TemporaryFile(dir=target.parent)
            probe.close()
            shutil.copy2(sys.executable, helper)
        bootloader_pid = None
        if sys.platform == 'win32':
            import psutil
            try:
                parent = psutil.Process(os.getppid())
                if Path(parent.exe()).resolve() == target.resolve():
                    bootloader_pid = parent.pid
            except (psutil.Error, OSError):
                pass
        plan = {'pid': os.getpid(), 'bootloader_pid': bootloader_pid, 'kind': kind, 'target': str(target),
                'candidate': str(candidate or download), 'stage': str(stage),
                'version': release.version, 'sha256': release.sha256,
                'result': str(result_path), 'backup': str(target.with_name(target.stem + '.previous-' + uuid.uuid4().hex[:8] + target.suffix))}
        path = stage / 'plan.json'
        path.write_text(json.dumps(plan), encoding='utf-8')
        return path
    except BaseException:
        if candidate is not None and candidate.parent.name.startswith('.notes-prompter-update-'):
            shutil.rmtree(candidate.parent, ignore_errors=True)
        shutil.rmtree(stage, ignore_errors=True)
        raise


def launch_helper(plan_path: Path):
    data = json.loads(plan_path.read_text(encoding='utf-8'))
    stage = Path(data['stage'])
    executable = stage / ('helper.app/Contents/MacOS/notes-prompter' if data['kind'] == 'mac' else 'update-helper.exe')
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1')
    kwargs = {'start_new_session': True} if sys.platform != 'win32' else {'creationflags': subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    child = subprocess.Popen([str(executable), '--apply-update', str(plan_path)], env=env,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
    import time
    deadline = time.monotonic() + 15
    while not (stage / 'ready').exists():
        if child.poll() is not None or time.monotonic() >= deadline:
            raise UpdateError('Update helper did not start')
        time.sleep(.05)


def replace_with_backup(candidate: Path, target: Path, backup: Path):
    """Same-volume rename; restore the original on replacement failure."""
    import time
    # Windows' onefile bootloader may briefly retain its image after the UI exits.
    for attempt in range(60):
        try:
            target.rename(backup)
            break
        except PermissionError:
            if attempt == 59:
                raise
            time.sleep(.5)
    try:
        # Windows download lives on the temp volume; copy into the target volume first.
        if candidate.is_file():
            staged = target.with_name('.' + target.name + '.' + uuid.uuid4().hex + '.new')
            try:
                shutil.copy2(candidate, staged)
                staged.replace(target)
            finally:
                staged.unlink(missing_ok=True)
        else:
            candidate.rename(target)
    except BaseException:
        backup.rename(target)
        raise


def apply_update(plan_path: Path) -> int:
    """Entry point in a detached copy, before importing/creating the desktop UI."""
    import psutil
    data = json.loads(plan_path.read_text(encoding='utf-8'))
    target, candidate, backup = (Path(data[key]) for key in ('target', 'candidate', 'backup'))
    result = Path(data['result'])
    (plan_path.parent / 'ready').touch()
    try:
        for pid in (data['pid'], data.get('bootloader_pid')):
            if pid is None:
                continue
            try:
                psutil.Process(pid).wait(timeout=120)
            except psutil.NoSuchProcess:
                pass
        if data['kind'] == 'mac':
            if target.name != 'Notes Prompter.app' or not candidate.is_dir():
                raise ValueError('Invalid application target')
            validate_mac_app(candidate, data['version'], platform.machine())
            replace_with_backup(candidate, target, backup)
        else:
            if target.suffix.lower() != '.exe' or hashlib.sha256(candidate.read_bytes()).hexdigest() != data['sha256']:
                raise ValueError('Invalid executable target or checksum')
            validate_windows_exe(candidate)
            if data['kind'] == 'installer':
                shutil.copy2(target, backup)
                try:
                    run([str(candidate), '/SILENT', '/SP-', '/NORESTART', '/CURRENTUSER', '/DIR=' + str(target.parent)])
                except Exception:
                    shutil.copy2(backup, target)
                    raise
            elif data['kind'] == 'portable':
                replace_with_backup(candidate, target, backup)
            else:
                raise ValueError('Invalid update kind')
        ok = True
    except Exception:
        ok = False
    # Reporting must never prevent relaunch if the preferences disk became full.
    try:
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text(json.dumps({'ok': ok, 'version': data['version']}), encoding='utf-8')
    except OSError:
        pass
    # Relaunch the installed app, or the untouched/restored app after an error.
    if target.exists():
        env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1')
        if sys.platform == 'darwin':
            subprocess.Popen(['/usr/bin/open', '-n', str(target)], env=env)
        else:
            import ctypes
            ctypes.windll.kernel32.SetDllDirectoryW(None)
            subprocess.Popen([str(target)], env=env)
    return 0
