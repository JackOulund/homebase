from mcp.server.mcpserver import MCPServer

from homebase.tasks import Task, TaskStore


def register_task_tools(server: MCPServer, store: TaskStore) -> None:
    @server.tool()
    async def add_task(
        name: str,
        estimated_minutes: int | None = None,
        interval_days: int | None = None,
        room: str | None = None,
        notes: str | None = None,
    ) -> Task:
        """Add a household task: a cleaning chore, a repair, or anything else to do at home.

        Capture quickly. Do not question the user before saving; fill in sensible
        values yourself and mention what you assumed.

        - estimated_minutes: your estimate of the hands-on time if the user gave none.
        - interval_days: set for recurring chores (7 weekly, 30 monthly, 365 yearly).
          Leave empty for one-off jobs such as a repair.
        - room: where in the home, in the user's own words.
        """
        return await store.add(name, estimated_minutes, interval_days, room, notes)

    @server.tool()
    async def list_tasks() -> dict[str, list[Task]]:
        """List every open household task: all recurring chores and unfinished one-off jobs."""
        return {"tasks": await store.list_open()}
