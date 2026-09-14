// Subscription-scoped deployment: creates a resource group and the platform.
targetScope = 'subscription'

@description('Name prefix for all resources.')
param name string = 'agentquality'

@description('Azure region for all resources.')
param location string = deployment().location

@description('PostgreSQL administrator login.')
param dbAdmin string = 'aqpadmin'

@secure()
@description('PostgreSQL administrator password.')
param dbPassword string

@secure()
@description('Initial admin password for the app password gate.')
param adminPassword string

@description('Initial admin username for the app password gate.')
param adminUsername string = 'admin'

resource rg 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: 'rg-${name}'
  location: location
}

module resources 'resources.bicep' = {
  name: 'resources'
  scope: rg
  params: {
    name: name
    location: location
    dbAdmin: dbAdmin
    dbPassword: dbPassword
    adminUsername: adminUsername
    adminPassword: adminPassword
  }
}

output apiUrl string = resources.outputs.apiUrl
