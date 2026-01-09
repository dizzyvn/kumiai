# Streaming Architecture Redesign

## Problem
Current implementation has complex polling logic with timeouts that causes streams to close before specialists complete.

## Root Cause
- Orchestrator's `receive_messages()` completes when orchestrator finishes
- Specialists run asynchronously via `call_agent` tool
- Stream closes when orchestrator iterator ends, even if specialists still running

## Solution: Two-Phase Streaming

### Phase 1: Active Orchestration
```python
async for msg in client.receive_messages():
    # Drain specialist queue (non-blocking)
    while specialist_msg := await get_specialist_message():
        process_specialist_message(specialist_msg)
        yield specialist_event

    # Process orchestrator message
    process_orchestrator_message(msg)
    yield orchestrator_event
```

### Phase 2: Specialist Completion
```python
# Orchestrator done, but specialists may still be running
# Keep polling specialist queue until all complete

while agents_active or time_since_last_activity < TIMEOUT:
    specialist_msg = await get_specialist_message()
    if specialist_msg:
        process_specialist_message(specialist_msg)
        yield specialist_event
        last_activity = now()
    else:
        await asyncio.sleep(0.1)  # Brief pause
```

### Tracking Active Specialists
```python
agents_active = set()

# When specialist starts
if msg_type == "agent_started":
    agents_active.add(agent_name)

# When specialist completes
if msg_type == "agent_completed":
    agents_active.discard(agent_name)
```

## Key Improvements
1. **Simple**: Use natural `async for` loop for orchestrator
2. **Complete**: Phase 2 ensures all specialist messages are delivered
3. **Timeout**: 30s timeout after last activity to prevent hanging
4. **Clean**: No complex asyncio.wait_for with timeouts

## Implementation Steps
1. Extract specialist message processing to helper function
2. Implement Phase 1 with simple async for loop
3. Implement Phase 2 with specialist tracking
4. Add timeout mechanism
