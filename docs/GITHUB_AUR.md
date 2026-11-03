# GitHub, releases and the AUR

This repository is wired up for:

| Workflow | Trigger | What it does |
|---|---|---|
| `.github/workflows/ci.yml` | every push / PR | runs the 29 unit tests on Ubuntu |
| `.github/workflows/aur-git.yml` | every push to `main` | publishes the `rawm-control-git` AUR package |
| `.github/workflows/release.yml` | tags `v*` | builds source/AppImage/Flatpak, creates the GitHub release, publishes the stable `rawm-control` AUR package |

AUR package names `rawm-control` and `rawm-control-git` were free when this was
written. Both are built from this repository; no binaries are hosted.

---

## 1. Create the GitHub repository (one time)

The local repository is already initialised and committed. Create an empty
repository on GitHub (public, **no** README/gitignore), then:

```bash
cd ~/Dokumenter/Projects/RAWMLinuxApp
git remote add origin git@github.com:YOURNAME/rawm-control.git
git push -u origin main
```

If the commit author should be you instead of the placeholder:

```bash
git config user.name "Your Name"
git config user.email "you@example.com"
git commit --amend --reset-author --no-edit
git push -u origin main
```

With the GitHub CLI the whole thing is:

```bash
gh repo create YOURNAME/rawm-control --public --source=. --remote=origin --push
```

The workflows use `${{ github.repository }}` when rendering PKGBUILDs, so no
username is hardcoded anywhere.

## 2. AUR account and SSH key (one time)

1. Create an account at <https://aur.archlinux.org/register/> (or log in).
2. Generate a dedicated key and add the **public** half to your AUR account
   (`My Account → SSH Public Keys`):

```bash
ssh-keygen -t ed25519 -C "rawm-control AUR" -f ~/.ssh/aur_rawm -N ""
cat ~/.ssh/aur_rawm.pub
```

3. Store the **private** key and identity as GitHub Actions secrets:

```bash
gh secret set AUR_SSH_PRIVATE_KEY < ~/.ssh/aur_rawm
gh secret set AUR_USERNAME --body "your-aur-username"
gh secret set AUR_EMAIL    --body "you@example.com"
```

(or Settings → Secrets and variables → Actions in the GitHub UI.)

| Secret | Purpose |
|---|---|
| `AUR_SSH_PRIVATE_KEY` | private key authorised for `aur@aur.archlinux.org` |
| `AUR_USERNAME` | commit author name on AUR |
| `AUR_EMAIL` | commit author email on AUR |

Then create the repository variable that arms the workflows:

```bash
gh variable set AUR_ENABLED --body "true"
```

Until `AUR_ENABLED=true` exists, both AUR jobs are skipped (the CI and GitHub
release jobs still run), so the first push does not fail while you set things up.

## 3. Create the AUR packages (one time)

New AUR packages cannot always be created by the first `git push`; if the
deploy action fails with *repository not found*, submit the initial PKGBUILD
through the AUR web form once.

For `rawm-control-git`:

```bash
./scripts/render-pkgbuild.sh YOURNAME/rawm-control
# writes aur-build/rawm-control-git/{PKGBUILD,.SRCINFO}
```

Go to <https://aur.archlinux.org/submit/>, upload/submit that PKGBUILD
(or paste it), and let the AUR create the package. The next workflow run can
push updates.

The stable `rawm-control` package is created the same way after the first
release, or by the first successful `release.yml` run if the AUR accepts the
push.

## 4. Day-to-day: what happens on a change

- **Push to `main`** → CI runs. `aur-git.yml` also runs and republishes
  `rawm-control-git` if its packaging changed. Regular code changes do **not**
  need an AUR commit: the `-git` PKGBUILD clones `main` at build time and its
  `pkgver()` derives a new version, so `yay -Syu` rebuilds it with your latest
  code.
- **Tag `vX.Y.Z`** → `release.yml` checks that the tag matches
  `rawm_control/config.py`, builds the source tarball, AppImage and Flatpak,
  publishes a GitHub release with all three, renders the stable PKGBUILD with
  the tarball's SHA-256, and pushes it to AUR. See
  [DISTRIBUTION.md](DISTRIBUTION.md).

### Making a release

```bash
./scripts/bump-version.sh 0.2.0
git add -A
git commit -m "Release 0.2.0"
git tag v0.2.0
git push origin main --tags
```

The tag check fails if the tag and `VERSION` disagree, so the version cannot
drift from the release.

## 5. Workflow details

`aur-git.yml` renders this template:

```bash
packaging/aur/rawm-control-git/PKGBUILD.in
```

with `@REPO@` replaced by `owner/repo`, then calls
[`KSXGitHub/github-actions-deploy-aur@v4.2.0`](https://github.com/KSXGitHub/github-actions-deploy-aur)
with the AUR private key.

`release.yml` does the stable equivalent:

```bash
packaging/aur/rawm-control/PKGBUILD.in
```

The stable package downloads the GitHub release asset
`rawm-control-<version>.tar.gz`, whose SHA-256 is computed in the release job
and substituted into `sha256sums`.

## 6. Troubleshooting

- **`Permission denied (publickey)`** — the public key is not on the AUR
  account, or `AUR_SSH_PRIVATE_KEY` is not the matching private key.
- **`repository not found`** — the AUR package has not been created yet; do
  step 3 once.
- **`Tag v… does not match VERSION=…`** — run `scripts/bump-version.sh` before
  tagging.
- **AUR package didn't update** — `aur-git.yml` only pushes when
  `PKGBUILD`/`.SRCINFO` changes; code-only pushes are picked up by the `-git`
  build. Use *Run workflow* in the Actions tab to force it.
- **Workflow fails because a secret is missing** — add all three secrets from
  step 2.
