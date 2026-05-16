#!/bin/bash
set -euo pipefail

APP_NAME="${app_name}"
AWS_REGION="${aws_region}"
LOG_GROUP="${log_group}"
APP_ENV="${app_env}"

echo "=== Setting up $APP_NAME ==="

# System updates
dnf update -y
dnf install -y python3.11 python3.11-pip git

# Install CloudWatch agent
dnf install -y amazon-cloudwatch-agent

# Configure CloudWatch agent
cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<'CWCONFIG'
{
  "agent": {
    "metrics_collection_interval": 60,
    "run_as_user": "root"
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/app/order-api.log",
            "log_group_name": "${log_group}",
            "log_stream_name": "{instance_id}/app",
            "retention_in_days": 14,
            "timezone": "UTC"
          },
          {
            "file_path": "/var/log/app/access.log",
            "log_group_name": "${log_group}/access",
            "log_stream_name": "{instance_id}/access",
            "retention_in_days": 7,
            "timezone": "UTC"
          }
        ]
      }
    }
  },
  "metrics": {
    "namespace": "App/${app_name}",
    "metrics_collected": {
      "statsd": {
        "service_address": ":8125",
        "metrics_collection_interval": 30,
        "metrics_aggregation_interval": 60
      }
    }
  }
}
CWCONFIG

# Start CloudWatch agent
systemctl enable amazon-cloudwatch-agent
systemctl start amazon-cloudwatch-agent

# Create app directory
mkdir -p /opt/app /var/log/app
cd /opt/app

# Download application (from S3 or git — using inline for demo)
cat > /opt/app/requirements.txt <<'REQS'
fastapi==0.104.1
uvicorn[standard]==0.24.0
watchtower==3.0.1
boto3==1.34.0
REQS

python3.11 -m pip install -r requirements.txt

# Copy application files (in production these come from a deployment artifact)
# For demo, we create a minimal entrypoint that logs to file
cat > /opt/app/start.sh <<'STARTSCRIPT'
#!/bin/bash
export APP_ENV="${app_env}"
export AWS_DEFAULT_REGION="${aws_region}"
export LOG_GROUP="${log_group}"
export INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
export LOG_CYCLE_MINUTES=30
export FAILURE_MODE=normal

cd /opt/app
python3.11 -m uvicorn main:app --host 0.0.0.0 --port 8080 \
  --log-config /opt/app/log_config.yaml \
  2>&1 | tee -a /var/log/app/order-api.log
STARTSCRIPT
chmod +x /opt/app/start.sh

# Logging config for uvicorn
cat > /opt/app/log_config.yaml <<'LOGCFG'
version: 1
disable_existing_loggers: false
formatters:
  default:
    format: "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    datefmt: "%Y-%m-%dT%H:%M:%S"
handlers:
  file:
    class: logging.handlers.RotatingFileHandler
    filename: /var/log/app/order-api.log
    maxBytes: 52428800
    backupCount: 5
    formatter: default
  console:
    class: logging.StreamHandler
    formatter: default
root:
  level: INFO
  handlers: [file, console]
LOGCFG

# Systemd service
cat > /etc/systemd/system/order-api.service <<'SVCFILE'
[Unit]
Description=Order Processing API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/app
ExecStart=/opt/app/start.sh
Restart=always
RestartSec=5
Environment=APP_ENV=${app_env}

[Install]
WantedBy=multi-user.target
SVCFILE

systemctl daemon-reload
systemctl enable order-api
systemctl start order-api

echo "=== $APP_NAME setup complete ==="
