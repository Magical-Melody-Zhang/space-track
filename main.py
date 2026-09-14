"""
main.py — Standalone entry-point for scrapy_space-track isolated testing.

Runs the spacetrack_gp spider with:
  * DB pipelines disabled (replaced by ConsolePrintPipeline).
  * Only 20 GP rows fetched from the API (each row → 3 Items, so we cap
    Scrapy at 60 items via CLOSESPIDER_ITEMCOUNT plus --limit=20).

Usage:
    python main.py                       # defaults: 20 rows, epoch=now-30
    python main.py --epoch-window now-7  # override epoch window
    python main.py --limit 50            # override row cap
"""
from __future__ import annotations

import argparse
import os
import site
import subprocess
import sys


_HERE = os.path.dirname(os.path.abspath(__file__))
_VENDOR = os.path.join(_HERE, '_vendor')
_PROJECT = os.path.join(_HERE, 'scrapy_space-track')


def _current_py_tag() -> str:
    """Return the CPython ABI tag used by extension modules, e.g. ``cp314``.

    Pure-Python packages work across versions; C extensions (lxml.etree,
    cryptography._rust, pydantic_core, …) are compiled against a specific
    CPython ABI and will raise ImportError / AttributeError ("cannot import
    name 'etree' from 'lxml'") when loaded by a different version.  We
    pre-flight the mismatch so the user gets an actionable message.
    """
    vi = sys.version_info
    return f'cp{vi.major}{vi.minor}'


def _scan_vendor_tags() -> tuple[set[str], dict[str, list[str]]]:
    """Walk ``_vendor`` and return ``({all_cp_tags_found}, {tag: [sample files]})``.

    Pure helper for downstream decisions; never raises.
    """
    tags: set[str] = set()
    samples: dict[str, list[str]] = {}
    if not os.path.isdir(_VENDOR):
        return tags, samples
    for root, _dirs, files in os.walk(_VENDOR):
        for name in files:
            if not name.endswith('.pyd'):
                continue
            stem = name[:-len('.pyd')]
            parts = stem.split('.')
            if len(parts) < 2:
                continue
            tag = parts[-1].split('-')[0]
            if not tag.startswith('cp'):
                continue
            tags.add(tag)
            rel = os.path.relpath(os.path.join(root, name), _HERE)
            samples.setdefault(tag, []).append(rel)
    return tags, samples


def _detect_vendor_abi_mismatch() -> tuple[str, set[str]] | None:
    """If *no* extension for the running interpreter exists, return the
    ``(wrong_tag, {files})`` tuple — otherwise ``None``.

    Mixed tags (e.g. leftover cp310 alongside good cp314 files) are tolerated
    because CPython will simply skip .pyd files whose ABI tag does not match
    the running interpreter; we only raise the alarm when the current tag is
    absent entirely.
    """
    tags, samples = _scan_vendor_tags()
    if not tags:
        return None
    expected = _current_py_tag()
    if expected in tags:
        return None
    # Pick the most-abundant wrong tag as the representative.
    ranked = sorted(samples.items(), key=lambda kv: -len(kv[1]))
    wrong_tag, sample_list = ranked[0]
    sample_set = set(sample_list[:5])
    return wrong_tag, sample_set


def _bootstrap_vendor() -> None:
    """Make ``_vendor/`` visible on sys.path before any third-party imports.

    Order is important: we add ``_vendor`` first (site.addsitedir handles
    .pth files / namespaces like ``zope.interface`` inside Twisted) and then
    force it to the *front* of ``sys.path`` so local copies win over any
    system-wide installs of the same package.
    """
    if os.path.isdir(_VENDOR):
        site.addsitedir(_VENDOR)
        try:
            sys.path.remove(_VENDOR)
        except ValueError:
            pass
        sys.path.insert(0, _VENDOR)
        # .pth files registered by site.addsitedir may have already been
        # loaded against stale package dirs; force fresh lookups.
        import importlib
        importlib.invalidate_caches()


def _wipe_and_reinstall(_logger=None) -> str | None:
    """Re-install dependencies cleanly into ``_vendor/``.

    We use a two-phase approach because a naive "delete-then-install" can
    leave the project in a worse state when the pip index is offline /
    filtered (e.g. an internal mirror that lacks scrapy wheels).  Strategy:

      1. Install into a TEMPORARY sibling directory.  If pip fails (no
         network, no matching wheel, …) we simply discard the temp dir —
         the user's existing ``_vendor/`` stays untouched.
      2. Only when pip returns successfully do we swap directories:
         rename the live ``_vendor`` to ``_vendor.old.<pid>``, move the
         installed temp dir into ``_vendor``, and finally delete the old
         tree on a best-effort basis.
    """
    import shutil
    import tempfile
    try:
        tmp_parent = tempfile.mkdtemp(prefix='_vendor_new_', dir=_HERE)
    except OSError as exc:
        return f'Cannot create temporary directory for clean install: {exc}'
    new_vendor = os.path.join(tmp_parent, '_vendor')
    try:
        os.makedirs(new_vendor, exist_ok=True)
    except OSError as exc:
        shutil.rmtree(tmp_parent, ignore_errors=True)
        return f'Cannot create staging _vendor directory: {exc}'

    cmd = [
        sys.executable, '-m', 'pip', 'install',
        '--disable-pip-version-check',
        '--no-cache-dir',
        '--upgrade', '--force-reinstall',
        '--target', new_vendor,
        'scrapy', 'pymysql', 'cryptography', 'pydantic',
    ]
    sys.stderr.write(
        f'[main.py] Installing fresh dependencies into a STAGING directory:\n'
        f'           {" ".join(cmd)}\n'
        f'           (this can take 30-120s on first run; be patient)\n'
    )
    try:
        subprocess.check_call(cmd, cwd=_HERE)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        shutil.rmtree(tmp_parent, ignore_errors=True)
        return (
            f'Staging install failed ({exc}). Your existing _vendor/ was '
            f'LEFT INTACT. Please either:\n'
            f'  1) Manually run:  {sys.executable} -m pip install '
            f'--no-cache-dir --upgrade --force-reinstall --target "{_VENDOR}" '
            f'scrapy pymysql cryptography pydantic\n'
            f'  2) Or point your pip at an index that has these packages '
            f'(--index-url / --extra-index-url). Current index can be seen '
            f'in the pip output a few lines above.'
        )
    # Pip succeeded — verify import works against the STAGING vendor before
    # we touch the user's real tree.  This guards against a "pip says OK but
    # wheel is corrupt / no C extensions for this ABI" scenario.
    _bootstrap_vendor_temp(new_vendor)
    try:
        import importlib, scrapy  # noqa: F401
        importlib.reload(scrapy)
    except ImportError as exc:
        shutil.rmtree(tmp_parent, ignore_errors=True)
        return (
            f'Staging install succeeded but import scrapy failed against '
            f'the new tree ({exc}). Your existing _vendor/ was LEFT INTACT. '
            f'Verify that your pip index provides wheels for '
            f'{_current_py_tag()}.'
        )

    # Swap atomically-ish: rename live _vendor → backup sibling, move
    # staging in its place, then delete the backup on a best-effort basis.
    old_bak: str | None = None
    try:
        if os.path.isdir(_VENDOR):
            import time
            old_bak = f'{_VENDOR}.old.{os.getpid()}.{int(time.time() * 1000)}'
            try:
                shutil.move(_VENDOR, old_bak)
            except OSError as exc:
                return (
                    f'Staging install OK but cannot move current _vendor/ '
                    f'out of the way: {exc}. Staging dir kept at '
                    f'{new_vendor!r}; rename it manually or delete '
                    f'{_VENDOR!r} then re-run.'
                )
        shutil.move(new_vendor, _VENDOR)
    finally:
        if old_bak and os.path.isdir(old_bak):
            shutil.rmtree(old_bak, ignore_errors=True)
        shutil.rmtree(tmp_parent, ignore_errors=True)
    return None


def _bootstrap_vendor_temp(path: str) -> None:
    """Add ``path`` to sys.path / site-packages *without* mutating _vendor globals.

    Used for the post-install verification step against the staging tree.
    """
    if not os.path.isdir(path):
        return
    site.addsitedir(path)
    try:
        sys.path.remove(path)
    except ValueError:
        pass
    sys.path.insert(0, path)
    import importlib
    importlib.invalidate_caches()


def _ensure_deps_installed(*, auto_reset: bool = False) -> str | None:
    """Ensure Scrapy (+friends) is importable from the local ``_vendor`` tree.

    Decision tree:
      1. ``auto_reset=True`` → always wipe & reinstall for the running
         interpreter (last-resort flag the user can pass to blow away a
         mismatched _vendor without manual deletion).
      2. _vendor has ≥1 extension built for *this* interpreter → try import,
         return None if OK; on any ImportError clean re-install.
      3. _vendor has extensions, but only for OTHER interpreters → do NOT
         silently overwrite; return an actionable "pick one interpreter /
         delete _vendor / --auto-reset-vendor" error message.
      4. _vendor is empty / missing → clean re-install.
    """
    if auto_reset:
        return _wipe_and_reinstall()
    mismatch = _detect_vendor_abi_mismatch()
    if mismatch is not None:
        wrong_tag, sample = mismatch
        expected = _current_py_tag()
        sample_list = '  - ' + '\n  - '.join(sorted(sample)[:3])
        return (
            f'_vendor/ contains C extensions compiled for {wrong_tag} but '
            f'you are running {expected} ({sys.executable}). Examples:\n'
            f'{sample_list}\n'
            f'Solution 1 (fastest): run with the matching interpreter, e.g.\n'
            f'            D:\\conda\\python.exe  "{os.path.abspath(__file__)}"\n'
            f'Solution 2: DELETE _vendor/ then re-run; main.py will '
            f're-install for {expected}:\n'
            f'            Remove-Item -Recurse -Force "{_VENDOR}"\n'
            f'Solution 3: Re-run this script with --auto-reset-vendor to '
            f'let main.py wipe and re-install _vendor for {expected}.'
        )
    _bootstrap_vendor()
    try:
        import scrapy  # noqa: F401
        return None
    except ImportError:
        pass
    # ImportError despite "no ABI mismatch" → tree is either empty, half
    # installed, or contains a mix of packages from multiple pip runs whose
    # .dist-info / namespace packages collide.  Clean re-install.
    return _wipe_and_reinstall()


if _PROJECT not in sys.path:
    sys.path.insert(0, _PROJECT)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Standalone SpaceTrack GP/TLE spider test (no DB; stdout only).',
    )
    parser.add_argument('--epoch-window', default='now-30',
                        help='Space-Track REST EPOCH filter (default: now-30).')
    parser.add_argument('--limit', type=int, default=0,
                        help='Number of GP rows to fetch (default: 20, 0 = unlimited).')
    parser.add_argument('--offset', type=int, default=0,
                        help='GP query offset (requires --limit > 0).')
    parser.add_argument('--no-limit', action='store_true',
                        help='Remove the 20-row cap (useful with a custom epoch window).')
    parser.add_argument('--compact', action='store_true',
                        help='Print each record as single-line JSON instead of pretty indented.')
    parser.add_argument('--auto-reset-vendor', action='store_true',
                        help='Wipe _vendor/ and re-install dependencies for the '
                             'running interpreter, even when the existing tree was '
                             'built for a different CPython ABI. '
                             '(Implied when _vendor is empty or scrapy fails to '
                             'import and the ABI tag matches.)')
    parser.add_argument('-o', '--output', default='',
                        help='Write the JSON records + summary to this file instead '
                             'of stdout. Relative paths are resolved against the '
                             'directory containing main.py (NOT the working dir) '
                             'so --output output.txt always lands next to main.py.')
    return parser.parse_args(argv)


def _configure_reactor():
    from scrapy.utils import reactor as _rm
    try:
        _rm.install_reactor('twisted.internet.asyncioreactor.AsyncioSelectorReactor')
    except Exception:
        pass


def _resolve_output_path(cli_output: str, setting_output: str | None = None) -> str:
    """Return an absolute output path.

    Priority (first wins):
      1. Explicit ``--output`` from the CLI.  If relative, anchor next to
         ``main.py`` (``_HERE``) so the file never ends up inside the
         ``scrapy_space-track/`` subdir after our ``os.chdir(_PROJECT)``.
      2. Value from ``CONSOLE_PRINT_OUTPUT_FILE`` in the settings module.
      3. Default: ``<HERE>/output.txt`` — exactly the path the user asked
         for in the latest round.
    """
    raw = (cli_output or '').strip() or (setting_output or '').strip()
    if not raw:
        raw = os.path.join(_HERE, 'output.txt')
    p = os.path.expandvars(os.path.expanduser(raw))
    if not os.path.isabs(p):
        p = os.path.abspath(os.path.join(_HERE, p))
    return p


def _build_settings(args):
    os.environ.setdefault('SCRAPY_SETTINGS_MODULE', 'setting')
    os.chdir(_PROJECT)
    from scrapy.utils.project import get_project_settings
    settings = get_project_settings()
    settings.set('GP_LATEST_PIPELINE_ENABLED', False, priority='cmdline')
    settings.set('HISTORY_TLE_PIPELINE_ENABLED', False, priority='cmdline')
    settings.set('SATCAT_TLE_PIPELINE_ENABLED', False, priority='cmdline')
    settings.set('CONSOLE_PRINT_ENABLED', True, priority='cmdline')
    settings.set('CONSOLE_PRINT_PRETTY', not args.compact, priority='cmdline')
    settings.set('CONSOLE_PRINT_OUTPUT_FILE',
                 _resolve_output_path(args.output,
                                      settings.get('CONSOLE_PRINT_OUTPUT_FILE', '')),
                 priority='cmdline')
    if args.no_limit or args.limit == 0:
        settings.set('CLOSESPIDER_ITEMCOUNT', 0, priority='cmdline')
    else:
        settings.set('CLOSESPIDER_ITEMCOUNT', int(args.limit) * 3, priority='cmdline')
    return settings


def _spider_kwargs(args):
    return {
        'epoch_window': args.epoch_window,
        'limit': '' if (args.no_limit or args.limit == 0) else str(args.limit),
        'offset': '' if (args.no_limit or args.limit == 0) else str(args.offset),
    }


def main(argv=None) -> int:
    args = _parse_args(argv)
    install_err = _ensure_deps_installed(auto_reset=args.auto_reset_vendor)
    if install_err is not None:
        mismatch = _detect_vendor_abi_mismatch()
        if mismatch is not None or args.auto_reset_vendor:
            sys.stderr.write(
                f'[main.py] ERROR: cannot provision local dependencies.\n'
                f'        {install_err}\n'
            )
            return 2
    try:
        _configure_reactor()
        from scrapy.crawler import CrawlerRunner
        from scrapy.utils.log import configure_logging
    except ImportError as exc:
        sys.stderr.write(
            f'[main.py] ERROR: scrapy package not importable: {exc}\n'
            f'        Install via:  {sys.executable} -m pip install '
            f'--no-cache-dir --upgrade --force-reinstall --target "{_VENDOR}" '
            f'scrapy pymysql cryptography pydantic\n'
            f'        Or re-run with:  --auto-reset-vendor\n'
        )
        if install_err:
            sys.stderr.write(f'        {install_err}\n')
        return 2

    settings = _build_settings(args)
    configure_logging(settings)

    try:
        from spiders.spacetrack_gp import SpacetrackGPSpider
    except ImportError as exc:
        sys.stderr.write(f'[main.py] ERROR: cannot import spider: {exc}\n')
        return 3

    from twisted.internet import reactor as _rx

    sys.stderr.write(f'[main.py] chdir={_PROJECT}\n')
    sys.stderr.write(
        f'[main.py] CrawlerRunner.crawl(SpacetrackGPSpider, '
        f'epoch_window={args.epoch_window}, '
        f'limit={args.limit if not args.no_limit else "UNLIMITED"}, '
        f'offset={args.offset}, '
        f'closespider_itemcount={settings.getint("CLOSESPIDER_ITEMCOUNT")})\n'
    )
    sys.stderr.flush()

    runner = CrawlerRunner(settings)
    d = runner.crawl(SpacetrackGPSpider, **_spider_kwargs(args))
    d.addBoth(lambda _result: _rx.stop())
    _rx.run()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
