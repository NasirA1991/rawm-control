#!/usr/bin/env bash
# Install RAWM Control from a verified GitHub release.
#
# The script is intentionally a single file: it is designed to be piped to
# bash.  All work happens in main(), which is called on the final line, so a
# truncated download cannot execute a partial installer.
set -euo pipefail

APP="rawm-control"
REPO="NasirA1991/rawm-control"
BRANCH="main"
AUR_PACKAGE="rawm-control"
FLATPAK_ID="io.github.rawmcontrol.RawmControl"
FLATPAK_RUNTIME="org.gnome.Platform//50"
RELEASES_URL="https://github.com/${REPO}/releases"
API_URL="https://api.github.com/repos/${REPO}/releases/latest"
SOURCE_INSTALL_URL="https://github.com/${REPO}/blob/${BRANCH}/docs/INSTALL.md#from-source"

METHOD=""
METHOD_EXPLICIT=0
VERSION_INPUT=""
ASSUME_YES=0
DRY_RUN=0
UNINSTALL=0
USER_FLAG=0

DISTRO=""
PRETTY_NAME="Linux"
ARCH=""
AUR_HELPER=""
AUR_MODE=""
UPGRADE=0

TAG=""
VERSION=""
SOURCE_URL=""
FLATPAK_URL=""
SUMS_URL=""
SOURCE_NAME=""
FLATPAK_NAME=""

TMP_DIR=""
STATE_FILE=""

usage() {
    cat <<'USAGE'
Install RAWM Control from the latest (or a pinned) verified GitHub release.

Usage:
  get.sh [options]

Options:
  --user             Install in the current user's home (source installs).
  --method <name>    Override automatic selection: aur, flatpak or source.
  --version <vX.Y.Z> Install a specific release instead of the latest.
  --yes              Do not ask for confirmation.
  --dry-run          Print the commands without running them.
  --uninstall        Remove the install recorded by get.sh.
  -h, --help         Show this help.

Detected automatically:
  Arch-based systems use the AUR (helper first, then makepkg).
  Other distributions use Flatpak when available, otherwise the source
  tarball.  The source and Flatpak methods add the per-product udev rule.

Environment:
  GET_SH_BASE_URL    Testing only: override the release-download base URL.
                     Requires --version.  Do not use for normal installs.

The app is installed with normal user permissions; sudo is used only for the
system udev rule and, on Arch, for the package manager.  Never run get.sh as
root.
USAGE
}

die() {
    printf 'get.sh: %s\n' "$*" >&2
    exit 1
}

usage_error() {
    printf 'get.sh: %s\n' "$*" >&2
    printf 'Try --help.\n' >&2
    exit 2
}

cleanup() {
    if [[ -n "${TMP_DIR:-}" && -d "$TMP_DIR" ]]; then
        rm -rf "$TMP_DIR"
    fi
}

parse_args() {
    while (($#)); do
        case "$1" in
            --user)
                USER_FLAG=1
                ;;
            --method)
                (($# >= 2)) || usage_error "--method requires a value"
                METHOD="${2:-}"
                METHOD_EXPLICIT=1
                shift
                ;;
            --version)
                (($# >= 2)) || usage_error "--version requires a value"
                VERSION_INPUT="${2:-}"
                shift
                ;;
            --yes)
                ASSUME_YES=1
                ;;
            --dry-run)
                DRY_RUN=1
                ;;
            --uninstall)
                UNINSTALL=1
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            --)
                shift
                break
                ;;
            -*)
                usage_error "unknown option: $1"
                ;;
            *)
                usage_error "unexpected argument: $1"
                ;;
        esac
        shift
    done

    if [[ -n "$VERSION_INPUT" ]]; then
        VERSION_INPUT="${VERSION_INPUT#v}"
        [[ "$VERSION_INPUT" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
            || usage_error "--version must look like vX.Y.Z"
    fi
    case "$METHOD" in
        ""|aur|flatpak|source) ;;
        *) usage_error "--method must be aur, flatpak or source" ;;
    esac
    if [[ -n "$METHOD" && "$METHOD" == aur && "$USER_FLAG" -eq 1 ]]; then
        usage_error "--user is not supported for AUR installs"
    fi
    if [[ -n "$METHOD" && "$METHOD" == aur && -n "$VERSION_INPUT" ]]; then
        usage_error "--version is not supported for AUR installs; use --method source"
    fi
}

detect_os() {
    local key=""
    local value=""
    local id=""
    local like=""
    local pretty=""

    if [[ -r /etc/os-release ]]; then
        while IFS='=' read -r key value; do
            value="${value%\"}"
            value="${value#\"}"
            case "$key" in
                ID) id="$value" ;;
                ID_LIKE) like="$value" ;;
                PRETTY_NAME) pretty="$value" ;;
            esac
        done < /etc/os-release
    fi

    PRETTY_NAME="${pretty:-${id:-Linux}}"
    case " ${id} ${like} " in
        *arch*) DISTRO="arch" ;;
        *debian*|*ubuntu*) DISTRO="debian" ;;
        *fedora*) DISTRO="fedora" ;;
        *opensuse*|*suse*) DISTRO="suse" ;;
        *) DISTRO="other" ;;
    esac
}

detect_arch() {
    ARCH="$(uname -m)"
    if [[ "$ARCH" != "x86_64" ]]; then
        die "Unsupported architecture: ${ARCH}. Only x86_64 release builds are published; use the source instructions at ${SOURCE_INSTALL_URL}."
    fi
}

install_tools_hint() {
    case "$DISTRO" in
        arch) echo "sudo pacman -S --needed curl tar coreutils" ;;
        debian) echo "sudo apt install curl tar coreutils" ;;
        fedora) echo "sudo dnf install curl tar coreutils" ;;
        suse) echo "sudo zypper install curl tar coreutils" ;;
        *) echo "Install curl (or wget), tar and coreutils/sha256sum with your package manager." ;;
    esac
}

check_tools() {
    local missing=()
    if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
        missing+=("curl (or wget)")
    fi
    command -v tar >/dev/null 2>&1 || missing+=("tar")
    command -v sha256sum >/dev/null 2>&1 || missing+=("sha256sum")
    if ((${#missing[@]})); then
        printf 'get.sh: missing required tools: %s\n' "${missing[*]}" >&2
        printf 'Install them with: %s\n' "$(install_tools_hint)" >&2
        exit 1
    fi
}

require_sudo() {
    command -v sudo >/dev/null 2>&1 || die "sudo is required for the system udev rule; install sudo or use --method aur when a helper is available."
}

require_flatpak() {
    command -v flatpak >/dev/null 2>&1 || die "Flatpak is not installed. Install it, or run: get.sh --method source"
}

confirm() {
    local prompt="$1"
    local reply=""
    if ((ASSUME_YES)); then
        return 0
    fi
    if [[ ! -r /dev/tty ]]; then
        die "No terminal available for confirmation; re-run with --yes."
    fi
    printf '%s [y/N] ' "$prompt" > /dev/tty
    IFS= read -r reply < /dev/tty || return 1
    case "$reply" in
        y|Y|yes|YES|Yes) return 0 ;;
        *) return 1 ;;
    esac
}

find_aur_helper() {
    if command -v paru >/dev/null 2>&1; then
        command -v paru
    elif command -v yay >/dev/null 2>&1; then
        command -v yay
    fi
}

has_base_devel() {
    command -v pacman >/dev/null 2>&1 \
        && command -v git >/dev/null 2>&1 \
        && command -v makepkg >/dev/null 2>&1 \
        && pacman -Qg base-devel >/dev/null 2>&1
}

choose_method() {
    if [[ -n "$METHOD" ]]; then
        if [[ "$METHOD" == "aur" && "$DISTRO" != "arch" ]]; then
            die "AUR installs are only available on Arch-based systems; use --method flatpak or --method source."
        fi
        if [[ "$METHOD" == "flatpak" ]]; then
            require_flatpak
        fi
        return
    fi

    if [[ "$DISTRO" == "arch" ]]; then
        METHOD="aur"
    elif command -v flatpak >/dev/null 2>&1; then
        METHOD="flatpak"
    else
        METHOD="source"
    fi

    if [[ "$METHOD" == "aur" && "$USER_FLAG" -eq 1 ]]; then
        die "--user is not supported for AUR installs; use --method source."
    fi
    if [[ "$METHOD" == "aur" && -n "$VERSION_INPUT" ]]; then
        die "--version is not supported for AUR installs; use --method source or --method flatpak."
    fi
}

method_label() {
    case "$METHOD" in
        aur)
            if ((UPGRADE)); then
                echo "AUR upgrade"
            elif [[ -n "$AUR_HELPER" ]]; then
                echo "AUR (helper)"
            elif [[ "$AUR_MODE" == "makepkg" ]]; then
                echo "AUR (makepkg)"
            else
                echo "AUR (manual)"
            fi
            ;;
        flatpak) echo "Flatpak + udev rule" ;;
        source) echo "source tarball + udev rule" ;;
        *) echo "unknown" ;;
    esac
}

download() {
    local url="$1"
    local out="$2"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --retry 2 --connect-timeout 20 -o "$out" "$url"
    else
        wget -q -O "$out" "$url"
    fi
    [[ -s "$out" ]]
}

download_stdout() {
    local url="$1"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --retry 2 --connect-timeout 20 "$url"
    else
        wget -q -O - "$url"
    fi
}

download_api() {
    local url="$1"
    if command -v curl >/dev/null 2>&1; then
        # Do not use -f: a GitHub rate-limit body is needed for a clear message.
        curl -sSL --retry 2 --connect-timeout 20 "$url"
    else
        wget -q -O - "$url"
    fi
}

make_temp() {
    TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/${APP}-get.XXXXXX")" \
        || die "Could not create a temporary directory."
    trap cleanup EXIT INT TERM
}

resolve_pinned() {
    VERSION="$VERSION_INPUT"
    TAG="v${VERSION}"
    local base=""
    if [[ -n "${GET_SH_BASE_URL:-}" ]]; then
        base="${GET_SH_BASE_URL%/}"
    else
        base="${RELEASES_URL}/download/${TAG}"
    fi
    SOURCE_URL="${base}/${APP}-${VERSION}.tar.gz"
    FLATPAK_URL="${base}/${APP}-${VERSION}-x86_64.flatpak"
    SUMS_URL="${base}/SHA256SUMS"
    SOURCE_NAME="${SOURCE_URL##*/}"
    FLATPAK_NAME="${FLATPAK_URL##*/}"
}

resolve_latest() {
    local json=""
    local urls=""
    local source_url=""
    local flatpak_url=""
    local sums_url=""

    if [[ -n "${GET_SH_BASE_URL:-}" ]]; then
        die "GET_SH_BASE_URL is for testing and requires --version."
    fi
    if ((DRY_RUN)); then
        TAG="latest"
        VERSION="latest"
        SUMS_URL="<latest-release>/SHA256SUMS"
        SOURCE_URL="<latest-release>/rawm-control-<version>.tar.gz"
        FLATPAK_URL="<latest-release>/rawm-control-<version>-x86_64.flatpak"
        SOURCE_NAME="rawm-control-<version>.tar.gz"
        FLATPAK_NAME="rawm-control-<version>-x86_64.flatpak"
        return
    fi
    json="$(download_api "$API_URL")" \
        || die "Could not query GitHub for the latest release. Check your network or use --version vX.Y.Z."
    if printf '%s\n' "$json" | grep -qi 'API rate limit exceeded'; then
        die "GitHub API rate limit reached. Try again later, or use --version vX.Y.Z with a known release."
    fi
    TAG="$(printf '%s\n' "$json" | sed -n 's/.*"tag_name":[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
    case "$TAG" in
        v[0-9]*) ;;
        *) die "Could not read the latest release tag from GitHub. Use --version vX.Y.Z." ;;
    esac
    VERSION="${TAG#v}"
    urls="$(printf '%s\n' "$json" \
        | grep -o '"browser_download_url"[[:space:]]*:[[:space:]]*"[^"]*"' \
        | grep -o 'https://[^"]*')"
    source_url="$(printf '%s\n' "$urls" | grep -E '/rawm-control-[^/]+\.tar\.gz$' | head -n 1 || true)"
    flatpak_url="$(printf '%s\n' "$urls" | grep -E '/rawm-control-[^/]+-x86_64\.flatpak$' | head -n 1 || true)"
    sums_url="$(printf '%s\n' "$urls" | grep -E '/SHA256SUMS$' | head -n 1 || true)"
    [[ -n "$source_url" ]] || die "Release ${TAG} has no source tarball; cannot install the udev rule."
    [[ -n "$sums_url" ]] || die "Release ${TAG} has no SHA256SUMS; refusing to install an unverified download."
    SOURCE_URL="$source_url"
    SUMS_URL="$sums_url"
    SOURCE_NAME="${SOURCE_URL##*/}"
    if [[ "$METHOD" == "flatpak" ]]; then
        if [[ -n "$flatpak_url" ]]; then
            FLATPAK_URL="$flatpak_url"
            FLATPAK_NAME="${FLATPAK_URL##*/}"
        elif ((METHOD_EXPLICIT)); then
            die "Release ${TAG} has no Flatpak bundle; use --method source."
        else
            printf 'No Flatpak bundle in release %s; using the source tarball.\n' "$TAG" >&2
            METHOD="source"
        fi
    fi
}

resolve_release() {
    if [[ "$METHOD" == "aur" ]]; then
        return
    fi
    if [[ -n "$VERSION_INPUT" ]]; then
        resolve_pinned
    else
        resolve_latest
    fi
}

ensure_sums() {
    [[ -n "$SUMS_URL" ]] || die "No SHA256SUMS URL available; refusing an unverified download."
    download "$SUMS_URL" "$TMP_DIR/SHA256SUMS" \
        || die "Could not download SHA256SUMS from ${SUMS_URL}"
}

verify_file() {
    local name="$1"
    local expected=""
    expected="$(awk -v n="$name" '
        {
            file=$2
            sub(/^\*/, "", file)
            if (file == n || file == "./" n) {
                print $1
                exit
            }
        }
    ' "$TMP_DIR/SHA256SUMS")"
    [[ -n "$expected" ]] \
        || die "SHA256SUMS has no entry for ${name}; aborting before extraction."
    printf '%s  %s\n' "$expected" "$name" \
        | (cd "$TMP_DIR" && sha256sum -c -) >/dev/null 2>&1 \
        || die "Checksum verification failed for ${name}; aborting before extraction."
}

download_asset() {
    local url="$1"
    local name="$2"
    [[ -n "$url" && -n "$name" ]] || die "Release asset URL is missing."
    download "$url" "$TMP_DIR/$name" \
        || die "Could not download ${url}"
    verify_file "$name"
}

fetch_source() {
    ensure_sums
    download_asset "$SOURCE_URL" "$SOURCE_NAME"
    mkdir -p "$TMP_DIR/src"
    tar -xzf "$TMP_DIR/$SOURCE_NAME" -C "$TMP_DIR/src" --strip-components=1 \
        || die "Could not extract the verified source tarball."
    if [[ ! -f "$TMP_DIR/src/install.sh" ]]; then
        die "Release ${TAG} has no install.sh; cannot install the udev rule."
    fi
    if [[ ! -x "$TMP_DIR/src/install.sh" ]]; then
        chmod +x "$TMP_DIR/src/install.sh"
    fi
    if ! grep -q -- '--udev-only' "$TMP_DIR/src/install.sh"; then
        die "Release ${TAG} is older than the installer requires; use --method aur or wait for the next release."
    fi
}

fetch_flatpak() {
    ensure_sums
    download_asset "$SOURCE_URL" "$SOURCE_NAME"
    download_asset "$FLATPAK_URL" "$FLATPAK_NAME"
    mkdir -p "$TMP_DIR/src"
    tar -xzf "$TMP_DIR/$SOURCE_NAME" -C "$TMP_DIR/src" --strip-components=1 \
        || die "Could not extract the verified source tarball."
    if [[ ! -f "$TMP_DIR/src/install.sh" ]]; then
        die "Release ${TAG} has no install.sh; cannot install the udev rule."
    fi
    if [[ ! -x "$TMP_DIR/src/install.sh" ]]; then
        chmod +x "$TMP_DIR/src/install.sh"
    fi
    if ! grep -q -- '--udev-only' "$TMP_DIR/src/install.sh"; then
        die "Release ${TAG} is older than the installer requires; use --method aur or wait for the next release."
    fi
}

run_udev_only() {
    require_sudo
    sudo "$TMP_DIR/src/install.sh" --udev-only
}

install_source() {
    fetch_source
    if ((USER_FLAG)); then
        "$TMP_DIR/src/install.sh" --user
        run_udev_only
    else
        require_sudo
        sudo "$TMP_DIR/src/install.sh"
    fi
    SCOPE="system"
    ((USER_FLAG)) && SCOPE="user"
    STATE_UDEV=1
}

install_flatpak() {
    fetch_flatpak
    require_sudo
    flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
    flatpak install --user --noninteractive flathub "$FLATPAK_RUNTIME"
    flatpak install --user --noninteractive "$TMP_DIR/$FLATPAK_NAME"
    run_udev_only
    SCOPE="user"
    STATE_UDEV=1
}

install_aur() {
    require_sudo
    if [[ -n "$AUR_HELPER" ]]; then
        "$AUR_HELPER" -S --needed --noconfirm "$AUR_PACKAGE"
    elif [[ "$AUR_MODE" == "makepkg" ]]; then
        git clone "https://aur.archlinux.org/${AUR_PACKAGE}.git" "$TMP_DIR/aur"
        (cd "$TMP_DIR/aur" && makepkg -si --noconfirm)
    else
        printf '\nAUR helper or build tools are unavailable. Install manually:\n'
        printf '  git clone https://aur.archlinux.org/%s.git\n' "$AUR_PACKAGE"
        printf '  cd %s && makepkg -si\n' "$AUR_PACKAGE"
        return 1
    fi
    SCOPE="system"
    STATE_UDEV=0
}

record_state() {
    local version="$1"
    local method="$2"
    local scope="$3"
    local udev="$4"
    local dir
    dir="$(dirname "$STATE_FILE")"
    mkdir -p "$dir"
    {
        printf 'method=%s\n' "$method"
        printf 'version=%s\n' "$version"
        printf 'scope=%s\n' "$scope"
        printf 'udev=%s\n' "$udev"
    } > "$STATE_FILE"
}

read_state() {
    [[ -f "$STATE_FILE" ]] || return 1
    STATE_METHOD="$(sed -n 's/^method=//p' "$STATE_FILE" | head -n 1)"
    STATE_VERSION="$(sed -n 's/^version=//p' "$STATE_FILE" | head -n 1)"
    STATE_SCOPE="$(sed -n 's/^scope=//p' "$STATE_FILE" | head -n 1)"
    STATE_UDEV="$(sed -n 's/^udev=//p' "$STATE_FILE" | head -n 1)"
    case "$STATE_METHOD" in
        aur|flatpak|source) ;;
        *) return 1 ;;
    esac
    [[ "$STATE_SCOPE" == "user" || "$STATE_SCOPE" == "system" ]] || return 1
    [[ "$STATE_UDEV" == "0" || "$STATE_UDEV" == "1" ]] || STATE_UDEV=0
    return 0
}

print_uninstall_commands() {
    printf 'No get.sh state file found at %s.\n' "$STATE_FILE"
    printf 'Use the uninstall command for the method you used:\n'
    printf '  AUR:     sudo pacman -R %s\n' "$AUR_PACKAGE"
    printf '  Flatpak: flatpak uninstall --user %s\n' "$FLATPAK_ID"
    printf '  Source:  download the source tarball and run ./uninstall.sh --user or sudo ./uninstall.sh\n'
}

uninstall_aur() {
    require_sudo
    sudo pacman -R --noconfirm "$AUR_PACKAGE"
}

uninstall_flatpak() {
    require_flatpak
    flatpak uninstall --user --noninteractive "$FLATPAK_ID"
    if [[ "${STATE_UDEV:-0}" == "1" ]]; then
        require_sudo
        sudo rm -f /etc/udev/rules.d/71-rawm-hid.rules
        sudo udevadm control --reload-rules
        sudo udevadm trigger --subsystem-match=hidraw
    fi
}

uninstall_source() {
    VERSION="${STATE_VERSION#v}"
    [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
        || die "The recorded source version is not usable; remove the install manually."
    VERSION_INPUT="$VERSION"
    resolve_pinned
    wrap_source_for_uninstall
    if [[ "${STATE_UDEV:-0}" == "1" ]]; then
        require_sudo
        sudo "$TMP_DIR/src/uninstall.sh"
    else
        "$TMP_DIR/src/uninstall.sh" --user
    fi
}

wrap_source_for_uninstall() {
    fetch_source
}

print_plan() {
    printf 'Detected: %s, %s.\n' "$PRETTY_NAME" "$ARCH"
    if ((UNINSTALL)); then
        printf 'Method: remove %s.\n' "$STATE_METHOD"
        printf 'Version: %s.\n' "${STATE_VERSION:-unknown}"
        printf 'Will run:\n'
        print_commands
        return
    fi
    printf 'Method: %s.\n' "$(method_label)"
    if [[ -n "$VERSION" ]]; then
        printf 'Version: %s.\n' "$VERSION"
    fi
    printf 'Will run:\n'
    print_commands
}

print_commands() {
    if ((UNINSTALL)); then
        case "$STATE_METHOD" in
            aur) printf '  sudo pacman -R --noconfirm %s\n' "$AUR_PACKAGE" ;;
            flatpak)
                printf '  flatpak uninstall --user --noninteractive %s\n' "$FLATPAK_ID"
                if [[ "$STATE_UDEV" == "1" ]]; then
                    printf '  sudo rm -f /etc/udev/rules.d/71-rawm-hid.rules\n'
                    printf '  sudo udevadm control --reload-rules\n'
                    printf '  sudo udevadm trigger --subsystem-match=hidraw\n'
                fi
                ;;
            source)
                printf '  download and verify %s-%s.tar.gz\n' "$APP" "${STATE_VERSION#v}"
                printf '  tar -xzf <verified tarball> -C <temp> --strip-components=1\n'
                if [[ "$STATE_UDEV" == "1" ]]; then
                    printf '  sudo <temp>/uninstall.sh\n'
                else
                    printf '  <temp>/uninstall.sh --user\n'
                fi
                ;;
        esac
        return
    fi

    case "$METHOD" in
        aur)
            if ((UPGRADE)); then
                if [[ -n "$AUR_HELPER" ]]; then
                    printf '  %s -S --needed --noconfirm %s\n' "$AUR_HELPER" "$AUR_PACKAGE"
                else
                    printf '  manual AUR upgrade with paru or yay\n'
                fi
            elif [[ -n "$AUR_HELPER" ]]; then
                printf '  %s -S --needed --noconfirm %s\n' "$AUR_HELPER" "$AUR_PACKAGE"
            elif [[ "$AUR_MODE" == "makepkg" ]]; then
                printf '  git clone https://aur.archlinux.org/%s.git <temp>/rawm-control\n' "$AUR_PACKAGE"
                printf '  (cd <temp>/rawm-control && makepkg -si --noconfirm)\n'
            else
                printf '  manual AUR install; see https://aur.archlinux.org/packages/%s\n' "$AUR_PACKAGE"
            fi
            ;;
        flatpak)
            printf '  curl -fsSL %s -o <temp>/SHA256SUMS\n' "$SUMS_URL"
            printf '  curl -fsSL %s -o <temp>/%s\n' "$SOURCE_URL" "$SOURCE_NAME"
            printf '  curl -fsSL %s -o <temp>/%s\n' "$FLATPAK_URL" "$FLATPAK_NAME"
            printf '  cd <temp> && sha256sum -c SHA256SUMS\n'
            printf '  tar -xzf %s -C <temp>/src --strip-components=1\n' "$SOURCE_NAME"
            printf '  flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo\n'
            printf '  flatpak install --user --noninteractive flathub %s\n' "$FLATPAK_RUNTIME"
            printf '  flatpak install --user --noninteractive <temp>/%s\n' "$FLATPAK_NAME"
            printf '  sudo <temp>/src/install.sh --udev-only\n'
            ;;
        source)
            if [[ -n "$SUMS_URL" ]]; then
                printf '  curl -fsSL %s -o <temp>/SHA256SUMS\n' "$SUMS_URL"
            fi
            if [[ -n "$SOURCE_URL" ]]; then
                printf '  curl -fsSL %s -o <temp>/%s\n' "$SOURCE_URL" "${SOURCE_NAME:-rawm-control-<version>.tar.gz}"
            fi
            printf '  cd <temp> && sha256sum -c SHA256SUMS\n'
            printf '  tar -xzf %s -C <temp>/src --strip-components=1\n' "${SOURCE_NAME:-rawm-control-<version>.tar.gz}"
            if ((USER_FLAG)); then
                printf '  <temp>/src/install.sh --user\n'
                printf '  sudo <temp>/src/install.sh --udev-only\n'
            else
                printf '  sudo <temp>/src/install.sh\n'
            fi
            ;;
    esac
}

detect_installed() {
    local bin=""
    local owner=""
    bin="$(command -v rawm-control 2>/dev/null || true)"
    if [[ -n "$bin" ]]; then
        case "$DISTRO" in
            arch)
                owner="$(pacman -Qqo "$bin" 2>/dev/null || true)"
                ;;
            debian)
                owner="$(dpkg -S "$bin" 2>/dev/null | head -n 1 | cut -d: -f1 || true)"
                ;;
            fedora)
                owner="$(rpm -qf "$bin" 2>/dev/null || true)"
                ;;
        esac
    fi
    if [[ -z "$owner" ]] && command -v flatpak >/dev/null 2>&1 \
        && flatpak info --user "$FLATPAK_ID" >/dev/null 2>&1; then
        owner="Flatpak (${FLATPAK_ID})"
    fi
    if [[ -z "$owner" && -f "$STATE_FILE" ]]; then
        owner="get.sh state"
    fi
    [[ -n "$owner" ]] || return 0

    printf 'RAWM Control is already installed by %s.\n' "$owner"
    if [[ "$DISTRO" == "arch" && "$METHOD_EXPLICIT" -eq 0 && -n "$(find_aur_helper)" ]]; then
        AUR_HELPER="$(find_aur_helper)"
        METHOD="aur"
        UPGRADE=1
        return 0
    fi
    printf 'Use your package manager to upgrade it, or remove it before installing another copy.\n'
    return 1
}

uninstall_flow() {
    if ! read_state; then
        print_uninstall_commands
        return 0
    fi
    print_plan
    if ! confirm "Remove RAWM Control?"; then
        printf 'Cancelled.\n'
        return 0
    fi
    if ((DRY_RUN)); then
        return 0
    fi
    make_temp
    case "$STATE_METHOD" in
        aur) uninstall_aur ;;
        flatpak) uninstall_flatpak ;;
        source) uninstall_source ;;
    esac
    rm -f "$STATE_FILE"
    printf 'Removed RAWM Control.\n'
}

install_flow() {
    if [[ "$METHOD" == "aur" ]]; then
        AUR_HELPER="$(find_aur_helper || true)"
        if [[ -n "$AUR_HELPER" ]]; then
            AUR_MODE="helper"
        elif has_base_devel; then
            AUR_MODE="makepkg"
        else
            AUR_MODE="manual"
        fi
        if ((UPGRADE)) && [[ -z "$AUR_HELPER" ]]; then
            printf 'RAWM Control is installed; upgrade it with paru or yay when available.\n'
            return 0
        fi
    fi

    resolve_release
    if [[ "$METHOD" == "flatpak" ]]; then
        require_flatpak
    fi
    print_plan
    if ! confirm "Continue with the installation?"; then
        printf 'Cancelled.\n'
        return 0
    fi
    if ((DRY_RUN)); then
        return 0
    fi
    if [[ "$METHOD" == "aur" && "$AUR_MODE" == "manual" ]]; then
        printf '\nInstall from the AUR manually:\n'
        printf '  git clone https://aur.archlinux.org/%s.git\n' "$AUR_PACKAGE"
        printf '  cd %s && makepkg -si\n' "$AUR_PACKAGE"
        return 1
    fi
    make_temp
    case "$METHOD" in
        aur) install_aur ;;
        flatpak) install_flatpak ;;
        source) install_source ;;
    esac
    local installed_version="$VERSION"
    if [[ "$METHOD" == "aur" ]]; then
        installed_version="$(pacman -Q "$AUR_PACKAGE" 2>/dev/null | awk '{print $2}' || true)"
        installed_version="${installed_version:-$VERSION}"
    fi
    if [[ -z "$installed_version" || "$installed_version" == "latest" ]]; then
        installed_version="unknown"
    fi
    record_state "$installed_version" "$METHOD" "${SCOPE:-system}" "${STATE_UDEV:-0}"
    printf '\nInstalled RAWM Control %s via %s.\n' "$installed_version" "$(method_label)"
    printf 'Replug the mouse or receiver once, then launch rawm-control.\n'
}

main() {
    umask 022
    if ((EUID == 0)); then
        printf 'Run as your normal user; get.sh uses sudo only for the steps that need it.\n' >&2
        exit 1
    fi
    parse_args "$@"
    detect_arch
    detect_os
    check_tools
    STATE_FILE="${XDG_STATE_HOME:-$HOME/.local/state}/${APP}/get-sh.state"

    if ((UNINSTALL)); then
        uninstall_flow
        return 0
    fi

    if ! detect_installed; then
        return 0
    fi
    choose_method
    install_flow
}

main "$@"
