# Maintainer: RAWM Control contributors
# Local build: run `makepkg -si` inside this repository.
pkgname=rawm-control
pkgver=0.1.0
pkgrel=1
pkgdesc="Native GTK4/libadwaita configuration tool for RAWM gaming mice"
arch=('any')
url="https://github.com/"
license=('MIT')
depends=('python' 'python-gobject' 'gtk4' 'libadwaita' 'python-cairo' 'python-dbus' 'hicolor-icon-theme')
options=('!strip')
source=()
sha256sums=()

package() {
    cd "$startdir"
    PREFIX=/usr DESTDIR="$pkgdir" ./install.sh
}
