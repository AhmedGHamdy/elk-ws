terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
}

resource "azurerm_resource_group" "rg" {
  name     = "websocket-monitoring-rg"
  location = "westus"
}

# Virtual Network
resource "azurerm_virtual_network" "vnet" {
  name                = "monitoring-vnet"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
}

resource "azurerm_subnet" "subnet" {
  name                 = "monitoring-subnet"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.0.1.0/24"]
}

# Network Security Group
resource "azurerm_network_security_group" "nsg" {
  name                = "monitoring-nsg"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  security_rule {
    name                       = "SSH"
    priority                   = 1001
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range         = "*"
    destination_port_range    = "22"
    source_address_prefix     = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "Elasticsearch"
    priority                   = 1002
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range         = "*"
    destination_port_range    = "9200"
    source_address_prefix     = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "APM"
    priority                   = 1003
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range         = "*"
    destination_port_range    = "8200"
    source_address_prefix     = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "WebSocket"
    priority                   = 1004
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range         = "*"
    destination_port_range    = "8000"
    source_address_prefix     = "*"
    destination_address_prefix = "*"
  }
}

# Public IP
resource "azurerm_public_ip" "pip" {
  name                = "monitoring-pip"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  allocation_method   = "Static"
  sku                = "Standard"
}

# Network Interface
resource "azurerm_network_interface" "nic" {
  name                = "monitoring-nic"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.pip.id
  }
}

# Virtual Machine
resource "azurerm_linux_virtual_machine" "vm" {
  name                = "monitoring-vm"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  size                = "Standard_D2s_v3"
  admin_username      = "adminuser"

  network_interface_ids = [
    azurerm_network_interface.nic.id,
  ]

  admin_ssh_key {
    username   = "adminuser"
    public_key = file("~/.ssh/id_rsa.pub")
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "UbuntuServer"
    sku       = "18.04-LTS"
    version   = "latest"
  }
}

# App Service Plan
resource "azurerm_service_plan" "plan" {
  name                = "websocket-plan"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  os_type            = "Linux"
  sku_name           = "P1v2"
}

# App Service
resource "azurerm_linux_web_app" "app" {
  name                = "websockett-app"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  service_plan_id     = azurerm_service_plan.plan.id

  site_config {
    application_stack {
      python_version = "3.9"
    }
    websockets_enabled = true
  }

  app_settings = {
    "ELASTIC_APM_SERVER_URL" = "http://${azurerm_public_ip.pip.ip_address}:8200"
    "ELASTIC_APM_SERVICE_NAME" = "stock-stream-service"
    "WEBSITES_PORT" = "8000"
    "WEBSITES_WEBSOCKETS_ENABLED" = "1"
  }
}