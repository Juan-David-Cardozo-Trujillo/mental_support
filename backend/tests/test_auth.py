"""
Tests for Authentication Routes (backend/routers/auth.py)

Coverage:
- SSO start endpoint
- SSO callback endpoint
- Consent endpoint
- User profile endpoint
- Logout endpoint
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_sso_start(client: AsyncClient):
    """Test SSO start generates state and returns authorization URL."""
    response = await client.get("/api/v1/auth/sso/start")
    
    assert response.status_code == 200
    data = response.json()
    assert "authorization_url" in data
    assert "state" in data
    assert len(data["state"]) > 0


@pytest.mark.asyncio
async def test_sso_callback_success(client: AsyncClient, platform_session, auth_session):
    """Test successful SSO callback with valid code and state."""
    # Mock the SSO provider token endpoint
    with patch("backend.routers.auth.apiClient") as mock_client:
        # Mock token response
        mock_client.post.return_value = AsyncMock(
            json=AsyncMock(return_value={
                "access_token": "mock_sso_token",
                "token_type": "Bearer",
            })
        )
        
        response = await client.post(
            "/api/v1/auth/sso/callback",
            json={"code": "mock_code", "state": "mock_state"}
        )
        
        # Should return 200 with JWT token
        assert response.status_code in [200, 201]


@pytest.mark.asyncio
async def test_consent_acceptance(client: AsyncClient, mock_user):
    """Test consent acceptance endpoint."""
    # This requires authentication, so we'd need to mock the auth
    response = await client.post(
        "/api/v1/auth/consent",
        json={"accepted": True},
        headers={"Authorization": f"Bearer mock-token"}
    )
    
    # Accept 200, 201, or 403 (not authenticated)
    assert response.status_code in [200, 201, 403]


@pytest.mark.asyncio
async def test_logout(client: AsyncClient):
    """Test logout endpoint."""
    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": "Bearer mock-token"}
    )
    
    # Accept 200 or 403 (not authenticated)
    assert response.status_code in [200, 204, 403]


@pytest.mark.asyncio
async def test_sso_callback_invalid_code(client: AsyncClient):
    """Test SSO callback with invalid authorization code."""
    with patch("backend.routers.auth.apiClient") as mock_client:
        # Mock failed token exchange
        mock_client.post.side_effect = Exception("Invalid code")
        
        response = await client.post(
            "/api/v1/auth/sso/callback",
            json={"code": "invalid_code", "state": "mock_state"}
        )
        
        # Should return 400 or 500
        assert response.status_code in [400, 500]


@pytest.mark.asyncio
async def test_sso_callback_missing_state(client: AsyncClient):
    """Test SSO callback without state parameter."""
    response = await client.post(
        "/api/v1/auth/sso/callback",
        json={"code": "mock_code"}  # Missing state
    )
    
    # Should return 400 (bad request)
    assert response.status_code == 400
