# -*- coding: utf-8 -*-
"""mercari-proxy 自签 HTTPS 证书（复用 mitmproxy 自带的 cryptography 依赖）。

局域网 IP / 域名访问必须走 https，否则浏览器不是安全上下文，crypto.subtle 不可用，
煤炉 DPoP 签不出 → 商品刷不出。证书仅用于本机/内网自用，浏览器会提示不受信任，点继续即可。
"""
from __future__ import annotations

import datetime
import ipaddress
import os
import socket
from typing import List, Optional, Tuple

DATA_DIRNAME = "mercari_proxy"


def _backend_root() -> str:
    # backend/src/mercari_proxy/cert.py → 上溯三级到 backend/
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def cert_dir() -> str:
    override = (os.environ.get("MERCARI_PROXY_CERT_DIR") or "").strip()
    root = os.path.abspath(override) if override else os.path.join(_backend_root(), "data", DATA_DIRNAME)
    os.makedirs(root, exist_ok=True)
    return root


def _local_ips() -> List[str]:
    ips = {"127.0.0.1"}
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None):
            ip = info[4][0]
            if ":" not in ip:  # 仅 IPv4
                ips.add(ip)
    except Exception:  # noqa: BLE001
        pass
    return sorted(ips)


def ensure_cert() -> Tuple[Optional[str], Optional[str]]:
    """确保自签证书存在，返回 (cert_path, key_path)；cryptography 不可用时返回 (None, None)。"""
    d = cert_dir()
    cert_path = os.path.join(d, "cert.pem")
    key_path = os.path.join(d, "key.pem")
    if os.path.isfile(cert_path) and os.path.isfile(key_path):
        return cert_path, key_path

    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
    except ImportError:
        return None, None

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "mercari-proxy")])

    san: List[x509.GeneralName] = [x509.DNSName("localhost")]
    try:
        san.append(x509.DNSName(socket.gethostname()))
    except Exception:  # noqa: BLE001
        pass
    for ip in _local_ips():
        try:
            san.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            pass

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .sign(key, hashes.SHA256())
    )

    with open(key_path, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path
