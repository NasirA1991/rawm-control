# Maintainer: Nasir A. <112448715+NasirA1991@users.noreply.github.com>
# Local build: run `makepkg -si` inside this repository.
pkgname=rawm-control
pkgver=0.1.10
pkgrel=1
pkgdesc="Native GTK4/libadwaita configuration tool for RAWM gaming mice"
arch=('any')
url="https://github.com/NasirA1991/rawm-control"
license=('MIT')
depends=('python' 'python-gobject' 'gtk4' 'libadwaita' 'python-cairo' 'python-dbus' 'hicolor-icon-theme')
options=('!strip')
source=()
sha256sums=()

package() {
    cd "$startdir"
    PREFIX=/usr DESTDIR="$pkgdir" ./install.sh
}
