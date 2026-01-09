"""
SSE Manager Service

Manages active Server-Sent Events (SSE) connections for real-time event broadcasting.
Allows SessionExecutor to broadcast events to connected frontend clients.
"""

import asyncio
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class SSEManager:
    """Manage active SSE connections for real-time event broadcasting"""

    def __init__(self):
        self._connections: Dict[str, List[asyncio.Queue]] = {}
        self._sequence_counters: Dict[str, int] = {}  # Track sequence numbers per instance
        self._lock = asyncio.Lock()
        logger.info("[SSE_MANAGER] Initialized SSE manager")

    async def register(self, instance_id: str, event_queue: asyncio.Queue) -> None:
        """
        Register an SSE connection for an instance.

        Args:
            instance_id: Instance ID
            event_queue: Queue to receive events for this connection
        """
        async with self._lock:
            if instance_id not in self._connections:
                self._connections[instance_id] = []

            self._connections[instance_id].append(event_queue)
            connection_count = len(self._connections[instance_id])

            logger.info(
                f"[SSE_MANAGER] Registered SSE connection for instance {instance_id} "
                f"(total connections: {connection_count})"
            )

    async def unregister(self, instance_id: str, event_queue: asyncio.Queue) -> None:
        """
        Unregister an SSE connection.

        Args:
            instance_id: Instance ID
            event_queue: Queue to remove
        """
        async with self._lock:
            if instance_id in self._connections:
                try:
                    self._connections[instance_id].remove(event_queue)
                    connection_count = len(self._connections[instance_id])

                    logger.info(
                        f"[SSE_MANAGER] Unregistered SSE connection for instance {instance_id} "
                        f"(remaining connections: {connection_count})"
                    )

                    # Clean up empty connection lists and reset sequence counter
                    if not self._connections[instance_id]:
                        del self._connections[instance_id]
                        # Reset sequence counter when no more connections
                        if instance_id in self._sequence_counters:
                            del self._sequence_counters[instance_id]
                        logger.debug(f"[SSE_MANAGER] Removed connection list and reset sequence for instance {instance_id}")

                except ValueError:
                    logger.warning(
                        f"[SSE_MANAGER] Attempted to unregister non-existent connection for instance {instance_id}"
                    )

    async def broadcast(self, instance_id: str, event: dict) -> None:
        """
        Broadcast event to all connected SSE clients for an instance.

        Args:
            instance_id: Target instance ID
            event: Event dictionary to broadcast
        """
        import uuid
        from datetime import datetime

        async with self._lock:
            if instance_id not in self._connections:
                logger.debug(f"[SSE_MANAGER] No active connections for instance {instance_id}, skipping broadcast")
                return

            # Initialize sequence counter for this instance if not exists
            if instance_id not in self._sequence_counters:
                self._sequence_counters[instance_id] = 0

            # Increment sequence counter
            self._sequence_counters[instance_id] += 1
            sequence = self._sequence_counters[instance_id]

            # Add sequence number and event ID to event
            enriched_event = {
                **event,
                'sequence': sequence,
                'event_id': event.get('event_id') or f"{instance_id}-{sequence}-{uuid.uuid4().hex[:8]}",
                'timestamp': event.get('timestamp') or datetime.now().isoformat(),
            }

            connection_count = len(self._connections[instance_id])
            logger.debug(
                f"[SSE_MANAGER] Broadcasting {enriched_event.get('type', 'unknown')} event (seq={sequence}) to "
                f"{connection_count} connection(s) for instance {instance_id}"
            )

            # Send to all queues
            failed_queues = []
            for queue in self._connections[instance_id]:
                try:
                    # Non-blocking put with timeout to avoid blocking on full queues
                    await asyncio.wait_for(queue.put(enriched_event), timeout=1.0)
                except asyncio.TimeoutError:
                    logger.warning(
                        f"[SSE_MANAGER] Queue full for instance {instance_id}, dropping event {enriched_event.get('type')} (seq={sequence})"
                    )
                    failed_queues.append(queue)
                except Exception as e:
                    logger.error(
                        f"[SSE_MANAGER] Error broadcasting to SSE client for instance {instance_id}: {e}"
                    )
                    failed_queues.append(queue)

            # Remove failed queues
            if failed_queues:
                for queue in failed_queues:
                    try:
                        self._connections[instance_id].remove(queue)
                    except ValueError:
                        pass

    def get_connection_count(self, instance_id: str) -> int:
        """
        Get number of active SSE connections for an instance.

        Args:
            instance_id: Instance ID

        Returns:
            Number of active connections
        """
        if instance_id not in self._connections:
            return 0
        return len(self._connections[instance_id])

    def has_connections(self, instance_id: str) -> bool:
        """
        Check if instance has any active SSE connections.

        Args:
            instance_id: Instance ID

        Returns:
            True if instance has active connections, False otherwise
        """
        return self.get_connection_count(instance_id) > 0


# Global instance
sse_manager = SSEManager()
