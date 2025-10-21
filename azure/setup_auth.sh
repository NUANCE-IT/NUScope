#!/bin/bash
# Azure AD App Registration Automation

# Login to Azure
az login --tenant northwestern.edu

# Create app registration
APP_NAME="NUScope Web App"
REDIRECT_URI="http://localhost:8000/docs/oauth2-redirect"

APP_ID=$(az ad app create \
  --display-name "$APP_NAME" \
  --sign-in-audience AzureADMyOrg \
  --web-redirect-uris "$REDIRECT_URI" "http://localhost:8000/docs" \
  --query appId -o tsv)

# Create client secret
SECRET=$(az ad app credential reset \
  --id "$APP_ID" \
  --years 2 \
  --query password -o tsv)

# Add API permissions
az rest --method PATCH \
  --uri "https://graph.microsoft.com/v1.0/applications/$APP_ID" \
  --headers 'Content-Type=application/json' \
  --body '{
    "requiredResourceAccess": [
      {
        "resourceAppId": "00000003-0000-0000-c000-000000000000",
        "resourceAccess": [
          {
            "id": "e1fe6dd8-ba31-4d61-89e7-88639da4683d",
            "type": "Scope"
          },
          {
            "id": "37f7f235-527c-4136-accd-4a02d197296e",
            "type": "Scope"
          },
          {
            "id": "14dad69e-099b-42c9-810b-d002981feec1",
            "type": "Scope"
          }
        ]
      }
    ]
  }'

# Output environment variables
echo "=== Add these to your environment ==="
echo "export AZURE_CLIENT_ID=$APP_ID"
echo "export AZURE_CLIENT_SECRET=$SECRET"
echo "export AZURE_TENANT_ID=northwestern.edu"
