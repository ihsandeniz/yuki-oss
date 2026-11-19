#!/usr/bin/env bash
# Masaüstü Yuki — ekranın köşesinde baştan ayağa Yuki. Model KENDİ VRM dosyan: --model yol.vrm ya da YUKI_MASAUSTU_VRM.
# Sol tık: gülümser + el sallar · çift tık: yaz · sağ tık / Ctrl+C: kapanır. Seçenekler: --boyut 0.6 (ekran oranı)
# ya da 600 (px) · --monitor N · --katman overlay · --x PİKSEL · --zemin PİKSEL (bkz. python3 masaustu.py -h)
# GTK3 + WebKit2GTK (sistem Python'u, gi) gerekir. GPU: YUKI_GPU=mesa (varsayılan) | nvidia | software
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")" && exec python3 masaustu.py "$@"
