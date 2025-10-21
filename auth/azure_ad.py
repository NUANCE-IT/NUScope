from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2AuthorizationCodeBearer, SecurityScopes
from msal import ConfidentialClientApplication
from azure.identity import DefaultAzureCredential
import os

# Azure AD Configuration
CLIENT_ID = os.getenv('AZURE_CLIENT_ID')
TENANT_ID = "northwestern.edu"  # Northwestern tenant
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPE = ["User.Read"]

# MSAL client
app_msal = ConfidentialClientApplication(
    CLIENT_ID,
    authority=AUTHORITY,
    client_credential=os.getenv('AZURE_CLIENT_SECRET')
)

oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl=f"{AUTHORITY}/oauth2/v2.0/authorize",
    tokenUrl=f"{AUTHORITY}/oauth2/v2.0/token",
    scopes={
        "openid": "OpenID Connect scope",
        "profile": "User profile",
        "User.Read": "Read user profile"
    }
)

async def validate_token(security_scopes: SecurityScopes, token: str = Depends(oauth2_scheme)):
    """Validate Azure AD token with dynamic scopes from the OpenAPI request."""
    try:
        scopes = security_scopes.scopes or ["openid", "profile", "User.Read"]
        result = app_msal.acquire_token_on_behalf_of(
            user_assertion=token,
            scopes=scopes
        )
        if "access_token" not in result:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
