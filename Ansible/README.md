# Monitoring Stack Deployment

This project automates the deployment of Elasticsearch, Kibana, Filebeat, and APM Server on an existing Azure VM to monitor a Python WebSocket app with OpenTelemetry.

## Prerequisites
- Ansible installed on your control node
- Existing Azure VM running Ubuntu 20.04 or later
- SSH access to the VM
- Azure App Service with WebSocket app deployed

## Quick Start

1. Update the inventory file with your VM details:

