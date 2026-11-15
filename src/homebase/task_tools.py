from datetime import UTC, datetime

from mcp.server.mcpserver import MCPServer

from homebase.planning import plan
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

        For a better time estimate, get_time_history and get_profile can be consulted.
        """
        return await store.add(name, estimated_minutes, interval_days, room, notes)

    @server.tool()
    async def list_tasks() -> dict[str, list[Task]]:
        """List every open household task: all recurring chores and unfinished one-off jobs."""
        return {"tasks": await store.list_open()}

    @server.tool()
    async def complete_task(task_id: int, actual_minutes: int | None = None) -> dict:
        """Mark a task as done now.

        Pass actual_minutes when the user mentions how long it took; it is used
        to learn how long chores really take. Recurring chores stay on the list
        and come due again after their interval; one-off jobs disappear from it.
        Returns how often the task has been done and the average actual time.
        """
        return await store.complete(task_id, actual_minutes)

    @server.tool()
    async def update_task(
        task_id: int,
        name: str | None = None,
        estimated_minutes: int | None = None,
        interval_days: int | None = None,
        room: str | None = None,
        notes: str | None = None,
    ) -> Task:
        """Change details of an existing task. Only the fields you pass are changed.

        Use it to rename a task, correct its time estimate, or change how often
        it recurs.
        """
        return await store.update(
            task_id, name, estimated_minutes, interval_days, room, notes
        )

    @server.tool()
    async def remove_task(task_id: int) -> dict[str, Task]:
        """Remove a task from the list because it no longer applies.

        This is not the same as finishing it: use complete_task when the user
        has done the task.
        """
        return {"removed": await store.remove(task_id)}

    @server.tool()
    async def suggest_tasks(minutes: int, room: str | None = None) -> dict:
        """Suggest what to do with the time the user has, e.g. "I have 30 minutes".

        Use it whenever the user says how much time they have. Present the
        suggestions as a short list with the reason and planned minutes for each,
        and mention anything in due_but_too_long. Do not dump the full task list.
        Pass room to limit the suggestions to one room.
        """
        return plan(await store.list_open(), minutes, now=datetime.now(UTC), room=room)

    @server.tool()
    async def get_time_history() -> dict[str, list[dict]]:
        """Get how long tasks really took, per task, from the times the user reported.

        Use it, together with get_profile, when estimating minutes for a new
        task: similar tasks that took longer or shorter than estimated show how
        fast this household works.
        """
        return {"history": await store.time_history()}
