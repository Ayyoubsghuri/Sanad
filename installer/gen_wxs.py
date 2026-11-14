"""Writes the WiX source of the Sanad .msi from the staged application folder (every file becomes one component).

    python gen_wxs.py <stage_dir> <version> > sanad.wxs      then:  wixl -a x64 -o Sanad.msi sanad.wxs

Per-user install (no administrator rights) into %LOCALAPPDATA%\\Programs\\Sanad, with Start-menu and desktop shortcuts to Sanad.exe.
The models and the law pack are downloaded on the first start (Setup-Sanad.ps1), not by the .msi itself."""
from __future__ import annotations

import hashlib
import sys
import uuid
from pathlib import Path
from xml.sax.saxutils import quoteattr

UPGRADE_CODE = "6f0d4a52-3c0e-4c59-9b1c-5a1f0b7e2d11"  # never change: lets a new version replace the old one
NS = uuid.UUID("b1e0a0c4-7a53-4d0e-8f66-1d2c9a4e7f20")
REG = '<RegistryValue Root="HKCU" Key="Software\\Sanad\\Components" Name={n} Type="integer" Value="1" KeyPath="yes"/>'


def ident(prefix: str, rel: str) -> str:
    return prefix + hashlib.sha1(rel.encode()).hexdigest()[:24]


def guid(rel: str) -> str:
    return str(uuid.uuid5(NS, rel))


def walk(folder: Path, root: Path, comps: list[str], pad: str) -> list[str]:
    out = []
    for f in sorted(p for p in folder.iterdir() if p.is_file()):
        rel = f.relative_to(root).as_posix()
        cid = ident("c", rel)
        comps.append(cid)
        out += [f'{pad}<Component Id="{cid}" Guid="{guid(rel)}">',
                f"{pad}  " + REG.format(n=quoteattr(rel)),
                f'{pad}  <File Id="{ident("f", rel)}" Name={quoteattr(f.name)} Source={quoteattr(str(f))}/>',
                f"{pad}</Component>"]
    for d in sorted(p for p in folder.iterdir() if p.is_dir()):
        rel = d.relative_to(root).as_posix()
        cid = ident("r", rel)
        comps.append(cid)
        out += [f'{pad}<Directory Id="{ident("d", rel)}" Name={quoteattr(d.name)}>',
                f'{pad}  <Component Id="{cid}" Guid="{guid("dir:" + rel)}">',
                f"{pad}    " + REG.format(n=quoteattr("dir:" + rel)),
                f'{pad}    <RemoveFolder Id="{ident("x", rel)}" On="uninstall"/>',
                f"{pad}  </Component>"]
        out += walk(d, root, comps, pad + "  ")
        out.append(f"{pad}</Directory>")
    return out


def shortcut(sid: str, directory: str, name: str, arguments: str = "") -> str:
    args = f" Arguments={quoteattr(arguments)}" if arguments else ""
    return (f'<Shortcut Id="{sid}" Directory="{directory}" Name="{name}" Target="[INSTALLDIR]Sanad.exe"{args} '
            f'WorkingDirectory="INSTALLDIR" Icon="SanadIcon" Description="Sanad: Moroccan law assistant"/>')


def main() -> int:
    stage, version = Path(sys.argv[1]).resolve(), sys.argv[2]
    comps: list[str] = []
    files = "\n".join(walk(stage, stage, comps, "            "))
    refs = "\n".join(f'      <ComponentRef Id="{c}"/>' for c in comps + ["cShortcuts", "rInstallDir"])
    print(f"""<?xml version="1.0" encoding="utf-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Product Id="*" Name="Sanad" Language="1033" Version="{version}" Manufacturer="Sanad" UpgradeCode="{UPGRADE_CODE}">
    <Package InstallerVersion="500" Compressed="yes" InstallScope="perUser"
             Description="Sanad: Moroccan law assistant (local, source-verified)"/>
    <MajorUpgrade DowngradeErrorMessage="A newer version of Sanad is already installed."/>
    <MediaTemplate EmbedCab="yes"/>
    <Icon Id="SanadIcon" SourceFile={quoteattr(str(stage / "sanad.ico"))}/>
    <Property Id="ARPPRODUCTICON" Value="SanadIcon"/>
    <Property Id="ALLUSERS" Secure="yes"/>
    <Directory Id="TARGETDIR" Name="SourceDir">
      <Directory Id="LocalAppDataFolder">
        <Directory Id="ProgramsDir" Name="Programs">
          <Directory Id="INSTALLDIR" Name="Sanad">
            <Component Id="rInstallDir" Guid="{guid('dir:.')}">
              {REG.format(n=quoteattr('dir:.'))}
              <RemoveFolder Id="xInstallDir" On="uninstall"/>
            </Component>
{files}
          </Directory>
        </Directory>
      </Directory>
      <Directory Id="ProgramMenuFolder">
        <Directory Id="SanadMenu" Name="Sanad"/>
      </Directory>
      <Directory Id="DesktopFolder"/>
    </Directory>
    <DirectoryRef Id="SanadMenu">
      <Component Id="cShortcuts" Guid="{guid('shortcuts')}">
        {REG.format(n=quoteattr('shortcuts'))}
        {shortcut('sMenu', 'SanadMenu', 'Sanad')}
        {shortcut('sRepair', 'SanadMenu', 'Sanad - repair setup', '--setup')}
        {shortcut('sDesktop', 'DesktopFolder', 'Sanad')}
        <RemoveFolder Id="xSanadMenu" On="uninstall"/>
      </Component>
    </DirectoryRef>
    <Feature Id="Main" Title="Sanad" Level="1">
{refs}
    </Feature>
  </Product>
</Wix>""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
