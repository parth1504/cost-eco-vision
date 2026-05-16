#!/bin/bash
# Trigger a simulated incident for Engineering Intelligence to detect
# Usage: ./trigger_incident.sh [host] [incident_type]
set -euo pipefail

HOST=${1:-"http://localhost:8080"}
INCIDENT=${2:-"payment_cascade"}

echo "=== Triggering incident: $INCIDENT on $HOST ==="

case $INCIDENT in
    "payment_cascade")
        echo "Simulating payment gateway failure cascade..."
        echo "Phase 1: Flood with orders to exhaust payment connections"
        for i in $(seq 1 50); do
            curl -s -X POST "$HOST/api/v1/orders" \
                -H "Content-Type: application/json" \
                -d "{\"items\":[{\"sku\":\"SKU-001\",\"quantity\":1}],\"total\":$((RANDOM % 500 + 10)),\"payment_method\":\"card\",\"address\":{\"city\":\"NYC\"}}" &
        done
        wait
        echo ""
        echo "Phase 2: Rapid retries (client retry storm)"
        for i in $(seq 1 100); do
            curl -s -X POST "$HOST/api/v1/orders" \
                -H "Content-Type: application/json" \
                -d "{\"items\":[{\"sku\":\"SKU-002\",\"quantity\":$((RANDOM % 5 + 1))}],\"total\":$((RANDOM % 200 + 50)),\"payment_method\":\"card\"}" &
            if (( i % 20 == 0 )); then wait; fi
        done
        wait
        ;;

    "db_exhaustion")
        echo "Simulating database connection pool exhaustion..."
        for i in $(seq 1 200); do
            curl -s "$HOST/api/v1/inventory/SKU-$(printf '%03d' $((RANDOM % 5 + 1)))" &
            if (( i % 30 == 0 )); then wait; fi
        done
        wait
        ;;

    "shipping_outage")
        echo "Simulating shipping service outage..."
        # Create orders first
        for i in $(seq 1 10); do
            ORDER=$(curl -s -X POST "$HOST/api/v1/orders" \
                -H "Content-Type: application/json" \
                -d "{\"items\":[{\"sku\":\"SKU-004\",\"quantity\":1}],\"total\":25,\"payment_method\":\"card\",\"address\":{\"city\":\"SF\"}}")
            ORDER_ID=$(echo $ORDER | python3 -c "import sys,json; print(json.load(sys.stdin).get('order_id',''))" 2>/dev/null || echo "")
            if [ -n "$ORDER_ID" ]; then
                curl -s -X POST "$HOST/api/v1/orders/$ORDER_ID/ship" &
            fi
        done
        wait
        ;;

    "load_spike")
        echo "Simulating sudden traffic spike (10x normal)..."
        for wave in $(seq 1 5); do
            echo "  Wave $wave/5..."
            for i in $(seq 1 40); do
                curl -s "$HOST/api/v1/orders?page=$((RANDOM % 10 + 1))" &
                curl -s "$HOST/api/v1/metrics" &
                curl -s "$HOST/api/v1/inventory/SKU-$(printf '%03d' $((RANDOM % 5 + 1)))" &
            done
            wait
            sleep 2
        done
        ;;

    *)
        echo "Unknown incident type: $INCIDENT"
        echo "Available: payment_cascade, db_exhaustion, shipping_outage, load_spike"
        exit 1
        ;;
esac

echo ""
echo "=== Incident triggered. Check logs for error patterns. ==="
echo "The Engineering Intelligence system should detect this within the next log cycle."
