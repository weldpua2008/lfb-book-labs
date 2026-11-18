#!/bin/sh
set -eu
cd "$(dirname "$0")"
case "${1:-}" in
 build) python3 scripts/fetch_dependencies.py; docker compose build ;;
 up) docker compose up -d ;;
 stage)
   case "${2:-}" in 00-legacy|01-price-attempt|01-price|02-shipping|03-replacement) ;; *) echo 'Unknown stage' >&2; exit 2;; esac
   STAGE="$2" docker compose up -d --no-deps --force-recreate app ;;
 worker) shift; docker compose exec -T app java -Xmx128m -cp 'havelblick.jar:lib/*' havelblick.shipping.OutboxWorker "$@" ;;
 sql) shift; docker compose exec -T db psql -X -v ON_ERROR_STOP=1 -U hb_admin -d havelblick "$@" ;;
 reset-data) docker compose exec -T db psql -X -v ON_ERROR_STOP=1 -U hb_admin -d havelblick < sql/reset-data.sql ;;
 reset) docker compose down -v; docker compose up -d ;;
 down) docker compose down ;;
 test) python3 scripts/run_scenarios.py ;;
 *) echo 'Usage: ./lab.sh build|up|stage STAGE|worker [--crash-after-send]|sql ARGS|reset-data|reset|down|test' >&2; exit 2 ;;
esac
