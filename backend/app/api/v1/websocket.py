"""
WebSocket Router — /ws/{project_id}
Live streaming of agent events to connected browser clients.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import structlog

from app.services.auth_service import decode_token

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.websocket("/ws/{project_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    project_id: str,
    token: str = Query(..., description="JWT access token for auth"),
):
    """
    WebSocket endpoint for real-time agent activity.

    Authentication: Pass JWT as ?token= query parameter.
    Messages received are JSON with keys: type, data, timestamp
    """
    # Authenticate via token query param
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        await websocket.close(code=4001, reason="Unauthorized")
        return

    ws_manager = websocket.app.state.ws_manager
    await ws_manager.connect(project_id, websocket)

    # Send connection confirmation
    await ws_manager.send_personal_message(websocket, {
        "type": "connected",
        "data": {"project_id": project_id, "user_id": payload.get("sub")},
    })

    log = logger.bind(project_id=project_id, user=payload.get("email"))
    log.info("WebSocket client connected")

    try:
        # Keep connection alive; handle client messages (e.g., ping)
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type":"pong"}')

    except WebSocketDisconnect:
        log.info("WebSocket client disconnected")
    finally:
        ws_manager.disconnect(project_id, websocket)
