# Maintainer: GarudaAI Contributors <dev@garudaai.local>
pkgname=garudaai
pkgver=0.1.0
pkgrel=1
pkgdesc="A self-hosted, hardware-aware, phone-controlled local AI agent platform"
arch=('x86_64')
url="https://github.com/garudaai/garudaai"
license=('MIT')
depends=(
    'python>=3.10'
    'python-click'
    'python-fastapi'
    'python-uvicorn'
    'python-pydantic'
    'python-requests'
    'python-tomli'
    'python-tomli-w'
)
optdepends=(
    'avahi: For local network discovery (garudaai.local)'
    'openssl: For HTTPS certificates'
)
makedepends=('python-build' 'python-installer' 'python-wheel')
source=("$url/archive/refs/tags/v${pkgver}.tar.gz")
sha256sums=('SKIP')  # Will be filled in by maintainer

build() {
    cd "$srcdir/$pkgname-$pkgver"
    python -m build
}

package() {
    cd "$srcdir/$pkgname-$pkgver"
    python -m installer --destdir="$pkgdir" dist/*.whl

    # Install systemd services
    install -Dm644 "systemd/garudaai.service" "$pkgdir/usr/lib/systemd/user/garudaai.service"
    install -Dm644 "systemd/garudaai-ollama.service" "$pkgdir/usr/lib/systemd/user/garudaai-ollama.service"

    # Install config template
    install -Dm644 "config/config.toml.example" "$pkgdir/etc/garudaai/config.toml.example"

    # Install LICENSE and README
    install -Dm644 "README.md" "$pkgdir/usr/share/doc/$pkgname/README.md"
    install -Dm644 "LICENSE" "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}

post_install() {
    echo "GarudaAI installed successfully!"
    echo ""
    echo "Get started with: garudaai setup"
    echo ""
    echo "Optional dependencies for enhanced features:"
    echo "  - avahi: For local network discovery at garudaai.local"
    echo "  - openssl: For HTTPS support (recommended)"
}
