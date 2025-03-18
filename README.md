# Stock Price Streaming with Elastic Stack Monitoring

This project implements a real-time stock price streaming service with comprehensive monitoring using the Elastic Stack (ELK) and OpenTelemetry.

## Architecture Overview

### Components

1. **Stock Streaming Application**
   - Python FastAPI WebSocket server
   - Real-time stock price updates using yfinance
   - Deployed on Azure VM
   - Instrumented with Elastic APM and OpenTelemetry

2. **Monitoring Stack**
   - Elasticsearch: Central data store and search engine
   - Kibana: Visualization and analysis platform
   - APM Server: Application performance monitoring
   - Logstash: Log processing pipeline
   - Filebeat: Log shipping agent
   - OpenTelemetry: Distributed tracing

### System Architecture

```plaintext
┌──────────────┐                ┌─────────────────────────────┐
│  WebSocket   │                │     Monitoring Stack        │
│   Server     │                │                            │
│  (FastAPI)   │                │  ┌─────────┐  ┌────────┐  │
│              │───APM(8200)────┼─►│   APM   │─►│Elastic │  │
│              │                │  │ Server  │  │Search  │  │
│              │───OTLP(4317)───┼─►│         │  │        │  │
│              │                │  └─────────┘  └────────┘  │
│              │                │       ▲          ▲        │
│              │                │       │          │        │
│              │                │  ┌─────────┐     │        │
│              │──Logs(5044)────┼─►│Filebeat │─────┘        │
│              │                │  └─────────┘              │
└──────────────┘                │       │                   │
                               │  ┌─────▼─────┐            │
                               │  │ Logstash  │────────────┘
                               │  └───────────┘            │
                               │        │                  │
                               │  ┌─────▼─────┐            │
                               │  │  Kibana   │            │
                               │  └───────────┘            │
                               └─────────────────────────────┘
```

## Project Structure

```plaintext
.
├── main.py                     # WebSocket application
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Container definition
├── playbook.yml               # Ansible configuration
└── templates/
    ├── elasticsearch.yml.j2    # Elasticsearch config
    ├── kibana.yml.j2          # Kibana config
    ├── apm-server.yml.j2      # APM Server config
    ├── logstash.yml.j2        # Logstash config
    ├── filebeat.yml.j2        # Filebeat config
    └── stock-stream.service.j2 # Systemd service
```

## Configuration Files

### 1. elasticsearch.yml
```yaml
cluster.name: monitoring-cluster
node.name: monitoring-node
path.data: /var/lib/elasticsearch
path.logs: /var/log/elasticsearch
network.host: 0.0.0.0
discovery.type: single-node

# Security settings
xpack.security.enabled: true
xpack.security.transport.ssl.enabled: true

# Memory settings
bootstrap.memory_lock: true

# Network settings
http.port: 9200
transport.port: 9300

# Index settings
action.auto_create_index: true
```

**Purpose**: Core configuration for Elasticsearch
- Defines cluster and node settings
- Configures security features
- Sets up memory and network parameters
- Manages index creation policies

### 2. kibana.yml
```yaml
server.host: "0.0.0.0"
server.port: 5601

elasticsearch.hosts: ["http://localhost:9200"]
elasticsearch.username: "${ELASTICSEARCH_USERNAME}"
elasticsearch.password: "${ELASTICSEARCH_PASSWORD}"

# Monitoring settings
monitoring.ui.container.elasticsearch.enabled: true

# Security settings
xpack.security.enabled: true
xpack.encryptedSavedObjects.encryptionKey: "${ENCRYPTION_KEY}"

# Logging settings
logging:
  appenders:
    file:
      type: file
      fileName: /var/log/kibana/kibana.log
      layout:
        type: json
  root:
    appenders: [file]
    level: info
```

**Purpose**: Kibana visualization platform configuration
- Sets up server connectivity
- Configures Elasticsearch connection
- Enables security features
- Manages logging settings

### 3. apm-server.yml
```yaml
apm-server:
  host: "0.0.0.0:8200"
  rum:
    enabled: true
  auth:
    secret_token: "${APM_SECRET_TOKEN}"

output.elasticsearch:
  hosts: ["localhost:9200"]
  protocol: "http"
  username: "${ELASTICSEARCH_USERNAME}"
  password: "${ELASTICSEARCH_PASSWORD}"

logging:
  level: info
  to_files: true
  files:
    path: /var/log/apm-server
    name: apm-server.log
    keepfiles: 7
    permissions: 0644

setup.kibana:
  host: "localhost:5601"
```

**Purpose**: APM Server configuration
- Configures APM server endpoints
- Sets up Elasticsearch output
- Manages logging settings
- Integrates with Kibana

### 4. logstash.yml
```yaml
http.host: "0.0.0.0"
path.config: /etc/logstash/conf.d
path.logs: /var/log/logstash

pipeline:
  batch.size: 125
  batch.delay: 50

# Queue settings
queue.type: persisted
queue.max_bytes: 1gb

# Performance settings
pipeline.workers: 2
pipeline.batch.size: 125
pipeline.batch.delay: 50

# Monitoring settings
xpack.monitoring.enabled: true
xpack.monitoring.elasticsearch.hosts: ["http://localhost:9200"]

# Pipeline configuration
input {
  beats {
    port => 5044
    ssl => false
  }
}

filter {
  if [type] == "websocket" {
    grok {
      match => { "message" => "%{TIMESTAMP_ISO8601:timestamp} %{LOGLEVEL:log_level} %{GREEDYDATA:message}" }
    }
    date {
      match => [ "timestamp", "ISO8601" ]
      target => "@timestamp"
    }
  }
}

output {
  elasticsearch {
    hosts => ["localhost:9200"]
    index => "logstash-%{+YYYY.MM.dd}"
  }
}
```

**Purpose**: Log processing configuration
- Defines input/output settings
- Configures pipeline behavior
- Sets up queue management
- Implements log parsing rules

### 5. filebeat.yml
```yaml
filebeat.inputs:
- type: log
  enabled: true
  paths:
    - /var/log/stock-stream/*.log
  fields:
    app: stock-stream
    type: application
  fields_under_root: true
  json.keys_under_root: true

- type: log
  enabled: true
  paths:
    - /var/log/apm-server/*.log
  fields:
    app: apm-server
    type: monitoring
  fields_under_root: true

processors:
- add_host_metadata: ~
- add_cloud_metadata: ~
- add_docker_metadata: ~

output.logstash:
  hosts: ["localhost:5044"]

logging.level: info
logging.to_files: true
logging.files:
  path: /var/log/filebeat
  name: filebeat.log
  keepfiles: 7
  permissions: 0644

setup.kibana:
  host: "localhost:5601"

setup.dashboards.enabled: true
```

**Purpose**: Log collection configuration
- Defines log sources
- Configures metadata enrichment
- Sets up output to Logstash
- Manages logging settings

### 6. stock-stream.service
```ini
[Unit]
Description=Stock Stream WebSocket Service
After=network.target

[Service]
User=adminuser
WorkingDirectory=/opt/stock-stream
Environment=PATH=/opt/stock-stream/venv/bin
Environment=ELASTIC_APM_SERVER_URL=http://localhost:8200
Environment=ELASTIC_APM_SERVICE_NAME=stock-stream-service
Environment=ELASTIC_APM_SECRET_TOKEN=${APM_SECRET_TOKEN}
Environment=OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
ExecStart=/opt/stock-stream/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Purpose**: Systemd service configuration
- Manages application lifecycle
- Sets environment variables
- Configures service dependencies
- Handles restart policies

## Monitoring Features

### 1. Application Performance Monitoring (APM)
- Request tracing
- Error tracking
- Performance metrics
- Service dependencies
- Custom transactions

### 2. Logging
- Centralized log collection
- Structured logging
- Log parsing and enrichment
- Log retention policies
- Search and analysis

### 3. Metrics
- System metrics (CPU, memory, disk)
- Application metrics
- Custom metrics
- Alerting thresholds
- Trend analysis

### 4. Tracing
- Distributed tracing
- Request context
- Service dependencies
- Performance bottlenecks
- Error correlation

## Security

### Authentication
- Elasticsearch security enabled
- APM server token authentication
- Kibana user authentication
- SSL/TLS encryption

### Authorization
- Role-based access control
- Index-level security
- Feature privileges
- API key management

## Maintenance

### Backup and Recovery
- Elasticsearch snapshots
- Configuration backups
- Log rotation
- Data retention policies

### Monitoring
- Stack monitoring
- Resource usage
- Performance metrics
- Error tracking
- Alerting

### Updates
- Version management
- Security patches
- Configuration updates
- Performance tuning

## Environment Variables

Required environment variables:
```bash
ELASTICSEARCH_USERNAME=elastic
ELASTICSEARCH_PASSWORD=<secure-password>
APM_SECRET_TOKEN=<apm-token>
ENCRYPTION_KEY=<32-character-key>
```

## Best Practices

### 1. Security
- Use strong passwords
- Enable SSL/TLS
- Implement proper authentication
- Regular security updates

### 2. Performance
- Optimize batch sizes
- Configure queues properly
- Monitor resource usage
- Regular performance tuning

### 3. Logging
- Structured logging
- Appropriate log levels
- Log rotation
- Regular cleanup

### 4. Maintenance
- Regular backups
- Monitor disk usage
- Update policies
- Health checks