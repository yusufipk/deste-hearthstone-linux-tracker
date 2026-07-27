#!/usr/bin/env bash
# deste'yi kendi dizininden başlatır. Masaüstü kısayolu bunu çağırır.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
exec python3 main.py "$@"
