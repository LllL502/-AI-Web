"""Windows 公网测试进程入口。

Waitress 仅监听本机 8010，由 Vite Preview 同源代理访问；公网流量必须先经过
Cloudflare Tunnel 与前端代理，MySQL、Django 和 Vite 端口均不直接暴露。
"""

import os

from waitress import serve

from config.wsgi import application


if __name__ == "__main__":
    serve(
        application,
        listen=os.environ.get("CAMPUS_TRACE_PUBLIC_BACKEND", "127.0.0.1:8010"),
        threads=6,
        trusted_proxy="127.0.0.1",
        trusted_proxy_count=1,
        trusted_proxy_headers={"x-forwarded-for", "x-forwarded-host", "x-forwarded-proto"},
        clear_untrusted_proxy_headers=True,
        expose_tracebacks=False,
        ident="CampusTrace",
    )
