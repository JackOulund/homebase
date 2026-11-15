from mcp.server.mcpserver import MCPServer

from homebase.profile import ProfileStore


def register_profile_tools(server: MCPServer, store: ProfileStore) -> None:
    @server.tool()
    async def get_profile() -> dict[str, dict[str, str]]:
        """Get the home profile: lasting facts about the home.

        It holds things that help estimate how long tasks take, such as size in
        m2, number of rooms and floors, a garden, and equipment like a robot
        vacuum or a dishwasher.
        """
        return {"profile": await store.get_all()}

    @server.tool()
    async def set_profile_entry(key: str, value: str) -> dict[str, dict[str, str]]:
        """Save or update one lasting fact about the home in the profile.

        Save such facts whenever the user mentions them: size in m2, number of
        rooms and floors, garden, or equipment such as a robot vacuum or
        dishwasher. Use short keys like "size_m2" or "robot_vacuum". Setting an
        existing key replaces its value.
        """
        await store.set(key, value)
        return {"profile": await store.get_all()}

    @server.tool()
    async def remove_profile_entry(key: str) -> dict[str, dict[str, str]]:
        """Remove a fact from the home profile that is no longer true."""
        await store.remove(key)
        return {"profile": await store.get_all()}
