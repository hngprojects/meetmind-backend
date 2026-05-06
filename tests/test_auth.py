import pytest
from unittest.mock import patch
from app.models.user import AccountState
from fastapi import HTTPException

@pytest.mark.asyncio
async def test_signin_returns_200_with_valid_credentials(client):
    """Signing in with correct credentials should return 200, an access token, and account state."""
    
    mock_result = {
        "access_token": "mock_access_token",
        "refresh_token": "mock_refresh_token",
        "account_state": AccountState.VERIFIED
    }
    
    with patch("app.api.v1.endpoints.auth.sign_in_user", return_value=mock_result):
        payload = {
            "email": "test@example.com",
            "password": "password123"
        }
       
        response = await client.post("/api/v1/auth/signin", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "access_token" in data
        assert data["account_state"] == "verified"

@pytest.mark.asyncio
async def test_signin_returns_401_with_invalid_credentials(client):
    """Signing in with wrong credentials should return 401 without leaking why."""
    
    with patch("app.api.v1.endpoints.auth.sign_in_user", side_effect=HTTPException(status_code=401, detail="Invalid email or password")):
        payload = {
            "email": "wrong@example.com",
            "password": "wrongpassword"
        }
        response = await client.post("/api/v1/auth/signin", json=payload)
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid email or password"

@pytest.mark.asyncio
async def test_signin_returns_422_with_missing_fields(client):
    """Signing in with missing email should return 422 validation error."""
    payload = {
        "password": "password123"
    }
    response = await client.post("/api/v1/auth/signin", json=payload)
    
    assert response.status_code == 422
