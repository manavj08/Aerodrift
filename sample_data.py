resources = [
    {
        "id": "internet",
        "type": "internet",
        "name": "Internet",
        "exposure": "public",
        "cidr": "0.0.0.0/0"
    },
    {
        "id": "web-server",
        "type": "ec2",
        "name": "Web Server",
        "exposure": "public",
        "cidr": "10.0.1.0/24"
    },
    {
        "id": "database",
        "type": "rds",
        "name": "Private Database",
        "exposure": "private",
        "cidr": "10.0.2.0/24"
    }
]


connections = [
    {
        "source": "internet",
        "target": "web-server",
        "port": 80,
        "protocol": "TCP",
        "direction": "inbound"
    },
    {
        "source": "web-server",
        "target": "database",
        "port": 5432,
        "protocol": "TCP",
        "direction": "outbound"
    }
]