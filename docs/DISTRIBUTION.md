# Distribution formats

RAWM Control is a Python/PyGObject application. The release pipeline builds
several artifacts from the same tag; they differ in what they bundle and how
they obtain access to `/dev/hidraw*`.

| Artifact | Self-contained | Mouse access | Updates |
|---|---|---|---|
| `rawm-control-<v>.tar.gz` | no | host udev rule | source |
| `rawm-control-<v>-x86_64.AppImage` | app only | host udev rule | manual |
| `rawm-control-<v>-x86_64.flatpak` | yes (GNOME runtime) | `--device=all` + host udev | manual |
| AUR `rawm-control` | no (distro package) | packaged udev rule | package manager |
| AUR `rawm-control-git` | no (distro package) | packaged udev rule | `yay -Syu` rebuild |

## Source tarball

`git archive` of the tag, used by the stable AUR package and for auditing.
`install.sh` handles system or `--user` installs, the udev rule, desktop entry
and icons.

## AppImage (lean)

`packaging/appimage/build.sh <version>` creates an AppDir containing only
`rawm_control/`, `data/`, the launcher and the `.desktop`/icon/metainfo. The
AppRun runs the **host** `python3`; GTK4, libadwaita, PyGObject, pycairo and
dbus-python are not bundled.

This is deliberate: `appimage-builder` with GTK4/PyGObject pulls in a >1 GB
overlay on Arch, includes setuid helpers that break the build, and is still not
reliable across glibc versions. A small AppImage that uses the desktop's GTK4
stack is predictable on current Arch/CachyOS, Debian/Ubuntu and Fedora systems
that already have the dependencies. The Flatpak is the fully bundled
alternative.

Build:

```bash
./packaging/appimage/build.sh 0.1.1 dist
# -> dist/rawm-control-0.1.1-x86_64.AppImage
```

It downloads `appimagetool` to `/tmp` and uses
`--appimage-extract-and-run`, so FUSE is not required.

## Flatpak

`packaging/flatpak/io.github.rawmcontrol.RawmControl.yml` uses
`org.gnome.Platform//50`, which provides Python 3.13, PyGObject, GTK4 and
libadwaita. The only additional module is `dbus-python` (built from source;
the runtime does not include it).

The app is granted:

- `--device=all` — vendor HID collection (`/dev/hidraw*`). This is broad; it is
  required because Flatpak has no narrower hidraw permission.
- `--talk-name=org.kde.StatusNotifierWatcher` and
  `--own-name=io.github.rawmcontrol.RawmControl.StatusNotifierItem` — tray.
- Wayland/X11/ipc sockets and notifications.

Flatpak does not allow the conventional
`org.kde.StatusNotifierItem-<pid>-1` wildcard name, so inside the sandbox the
tray uses the app-ID-scoped name. The SNI host only needs a registered service,
not the `org.kde` naming convention.

Build (needs `flatpak-builder` and the GNOME 50 runtime/SDK):

```bash
./packaging/flatpak/build.sh 0.1.1 dist
# -> dist/rawm-control-0.1.1-x86_64.flatpak
```

Install:

```bash
flatpak install --user ./rawm-control-0.1.1-x86_64.flatpak
flatpak run io.github.rawmcontrol.RawmControl
```

### Flathub

The manifest is suitable for building a bundle, but this repository does not
submit to Flathub. Flathub has its own review process and content/AI policies;
whether this app is accepted is a separate decision from the build above. The
supported distribution path here is the GitHub release `.flatpak`.

## AUR

Templates live in `packaging/aur/`:

- `rawm-control-git/PKGBUILD.in` — VCS package, `pkgver()` derives from the
  commit count/hash; code changes are picked up by rebuilds without an AUR
  commit.
- `rawm-control/PKGBUILD.in` — stable package, source is the GitHub release
  tarball, SHA-256 injected by the release workflow.

Both install the udev rule to `/usr/lib/udev/rules.d` and the desktop entry and
icons via `install.sh`.

## CI jobs

| Workflow | Trigger | Output |
|---|---|---|
| `ci.yml` | push/PR | unit tests |
| `aur-git.yml` | push `main` | `rawm-control-git` AUR |
| `release.yml` | tag `v*` | source, AppImage, Flatpak, GitHub release, stable AUR |

The release workflow:

1. checks the tag against `rawm_control/config.py` (`VERSION`);
2. builds the source tarball and records its SHA-256;
3. builds the AppImage and Flatpak in parallel;
4. attaches all three to the GitHub release;
5. publishes the stable AUR package with the tarball SHA-256.

AUR jobs are gated behind the `AUR_ENABLED` repository variable; see
[GITHUB_AUR.md](GITHUB_AUR.md).

## Permissions by format

- **AUR / source install** — udev rule installed automatically.
- **Flatpak** — `--device=all` plus the host udev ACL; if the host lacks the
  rule, install `data/udev/71-rawm-hid.rules` on the host.
- **AppImage** — install the udev rule on the host once; AppImages cannot
  install udev rules.

## Reproducing locally

```bash
python3 -m unittest discover -s tests -v
./packaging/appimage/build.sh "$(python3 -c 'from rawm_control.config import VERSION; print(VERSION)')" dist
# Flatpak requires flatpak-builder + GNOME 50 runtime/SDK:
./packaging/flatpak/build.sh 0.1.1 dist
```


## Verification status

- **AUR templates** — `makepkg --printsrcinfo` succeeds for both packages
  (Arch/CachyOS).
- **AppImage** — built with `packaging/appimage/build.sh`, then launched with
  `--demo` under Xvfb; CLI (`--version`, `--cli status`) and the GUI both work.
- **Flatpak** — built against `org.gnome.Platform//50`, installed, and checked
  for Python/dbus imports, hidraw access and the StatusNotifierItem menu (KDE).
- **GitHub workflows** — validated with `actionlint` 1.7.12. They have not been
  executed on GitHub yet because the repository has not been pushed; the Flatpak
  job in particular is the first thing to watch on the initial tag build.

The AppImage is intentionally lean and therefore needs the host GTK4 stack; the
Flatpak is the only fully self-contained artifact.
